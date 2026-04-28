"""One-shot local stack bootstrap.

Idempotent. Safe to re-run. Order:
  1. wait for SQL Server, create database if missing, apply scripts/sql/*.sql
  2. wait for Azurite, create blob containers
  3. wait for Qdrant, create collections sized to EMBEDDING_DIM
  4. wait for Ollama, pull each OLLAMA_MODELS entry

Exits 0 on success so docker compose `service_completed_successfully`
unblocks the function containers.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable

import pyodbc
import requests
from azure.storage.blob import BlobServiceClient

CONTAINERS = ["raw", "processed-text", "processed-layout", "processed-clauses", "audit"]
COLLECTIONS = ["contracts-index", "clauses-index"]
SCHEMA_FILES = ["001-schema.sql", "002-seed-gold-clauses.sql", "003-views.sql"]
GOLD_CLAUSES_DIR = "/gold-clauses"


def wait(check: Callable[[], None], label: str, attempts: int = 60, delay: float = 2.0) -> None:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            check()
            print(f"✓ {label}")
            return
        except Exception as e:
            last_err = e
            if i == 0:
                print(f"… waiting for {label}: {e}")
            time.sleep(delay)
    raise RuntimeError(f"timeout waiting for {label}: {last_err}")


# --- SQL ---

def _master_conn_str() -> str:
    host = os.environ["MSSQL_HOST"]
    pw = os.environ["MSSQL_SA_PASSWORD"]
    return (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={host};Database=master;UID=sa;PWD={pw};"
        "Encrypt=no;TrustServerCertificate=yes;Connection Timeout=10;"
    )


def _db_conn_str(db: str) -> str:
    host = os.environ["MSSQL_HOST"]
    pw = os.environ["MSSQL_SA_PASSWORD"]
    return (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={host};Database={db};UID=sa;PWD={pw};"
        "Encrypt=no;TrustServerCertificate=yes;Connection Timeout=30;"
    )


def bootstrap_sql() -> None:
    db = os.environ.get("MSSQL_DB", "sqldb-contracts")

    def check_master() -> None:
        with pyodbc.connect(_master_conn_str(), timeout=5) as c:
            c.cursor().execute("SELECT 1").fetchone()

    wait(check_master, "SQL Server (master)")

    print(f"==> Ensuring database {db!r}")
    # SQL Server forbids CREATE DATABASE inside an implicit transaction, so
    # we split the existence check from the CREATE and force autocommit on
    # the connection (passing autocommit=True to connect() isn't enough on
    # all driver versions).
    conn = pyodbc.connect(_master_conn_str())
    conn.autocommit = True
    try:
        cur = conn.cursor()
        exists = cur.execute("SELECT DB_ID(?)", db).fetchval()
        if exists is None:
            cur.execute(f"CREATE DATABASE [{db}]")
    finally:
        conn.close()

    for fname in SCHEMA_FILES:
        path = f"/sql/{fname}"
        if not os.path.exists(path):
            print(f"   (skip {path} — not present)")
            continue
        print(f"==> Applying {path}")
        sql = open(path).read()
        # T-SQL batches are separated by GO on its own line.
        batches = [b.strip() for b in sql.replace("\r\n", "\n").split("\nGO\n") if b.strip()]
        with pyodbc.connect(_db_conn_str(db), autocommit=True) as c:
            cur = c.cursor()
            for b in batches:
                # Strip leading 'GO' on a line by itself if it slipped through.
                if b.upper() == "GO":
                    continue
                try:
                    cur.execute(b)
                except pyodbc.Error as e:
                    msg = str(e)
                    # Idempotency: ignore "already exists" style errors.
                    if "already exists" in msg or "is already" in msg:
                        continue
                    print(f"   ! batch failed: {msg[:200]}")
                    raise

    _load_gold_clause_text(db)


def _parse_gold_md(path: str) -> tuple[str | None, str]:
    """Return (standard_clause_id, body_text). Body is the markdown after the
    YAML frontmatter, with frontmatter stripped."""
    raw = open(path, encoding="utf-8").read()
    sid: str | None = None
    body = raw
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            front = raw[4:end]
            body = raw[end + 5:].lstrip("\n")
            for line in front.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    if k.strip() == "standard_clause_id":
                        sid = v.strip()
                        break
    return sid, body


def _load_gold_clause_text(db: str) -> None:
    """Replace placeholder ApprovedText in dbo.StandardClause with the real
    clause body parsed from samples/gold-clauses/*.md (mounted at /gold-clauses).

    Idempotent: re-runs cheaply, always reflects the markdown on disk."""
    if not os.path.isdir(GOLD_CLAUSES_DIR):
        print(f"   (skip gold-clause loader — {GOLD_CLAUSES_DIR} not mounted)")
        return
    files = sorted(
        os.path.join(GOLD_CLAUSES_DIR, f)
        for f in os.listdir(GOLD_CLAUSES_DIR)
        if f.endswith(".md")
    )
    if not files:
        print(f"   (skip gold-clause loader — no .md files in {GOLD_CLAUSES_DIR})")
        return
    print(f"==> Loading {len(files)} gold clause bodies into dbo.StandardClause")
    matched = 0
    with pyodbc.connect(_db_conn_str(db), autocommit=True) as c:
        cur = c.cursor()
        for path in files:
            sid, body = _parse_gold_md(path)
            if not sid:
                print(f"   ! {os.path.basename(path)}: no standard_clause_id in frontmatter — skipped")
                continue
            # rowcount is unreliable under autocommit; use a SELECT to confirm
            # the seed row exists, then UPDATE it.
            exists = cur.execute(
                "SELECT 1 FROM dbo.StandardClause WHERE StandardClauseId = ?", sid,
            ).fetchone()
            if not exists:
                print(f"   ! {sid}: no row in dbo.StandardClause — seed SQL out of sync?")
                continue
            cur.execute(
                "UPDATE dbo.StandardClause SET ApprovedText = ? WHERE StandardClauseId = ?",
                body, sid,
            )
            matched += 1
            print(f"   ✓ {sid} ({len(body)} chars)")
    print(f"==> Gold clause text loaded ({matched}/{len(files)})")


# --- Azurite ---

def bootstrap_blob() -> None:
    conn = os.environ["AZURITE_CONN_STRING"]
    bsc = BlobServiceClient.from_connection_string(conn)

    def check() -> None:
        # list_containers is cheap and confirms the service is reachable
        list(bsc.list_containers(results_per_page=1))

    wait(check, "Azurite blob")

    for name in CONTAINERS:
        try:
            bsc.create_container(name)
            print(f"✓ blob container {name}")
        except Exception as e:
            if "ContainerAlreadyExists" in str(e) or "already exists" in str(e).lower():
                print(f"= blob container {name} (exists)")
            else:
                raise


# --- Qdrant ---

def bootstrap_qdrant() -> None:
    url = os.environ["QDRANT_URL"].rstrip("/")
    dim = int(os.environ.get("EMBEDDING_DIM", "768"))

    def check() -> None:
        requests.get(f"{url}/collections", timeout=5).raise_for_status()

    wait(check, "Qdrant")

    for col in COLLECTIONS:
        body = {"vectors": {"size": dim, "distance": "Cosine"}}
        r = requests.put(f"{url}/collections/{col}", json=body, timeout=15)
        if r.status_code in (200, 409):
            print(f"✓ qdrant collection {col} (dim={dim})")
        else:
            print(f"× qdrant collection {col}: {r.status_code} {r.text}", file=sys.stderr)
            r.raise_for_status()


# --- Ollama ---

def bootstrap_ollama() -> None:
    url = os.environ["OLLAMA_URL"].rstrip("/")
    raw = os.environ.get("OLLAMA_MODELS", "").strip()
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if not models:
        print("(no OLLAMA_MODELS — skipping pulls)")
        return

    def check() -> None:
        requests.get(f"{url}/api/tags", timeout=5).raise_for_status()

    wait(check, "Ollama")

    for model in models:
        print(f"==> pulling {model} (this can take several minutes on first run)")
        with requests.post(
            f"{url}/api/pull", json={"name": model, "stream": True}, stream=True, timeout=None
        ) as r:
            r.raise_for_status()
            last_status = ""
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = msg.get("status", "")
                if status and status != last_status:
                    print(f"   {model}: {status}")
                    last_status = status
                if msg.get("error"):
                    raise RuntimeError(f"ollama pull {model} failed: {msg['error']}")
        print(f"✓ {model}")


def main() -> int:
    print("===== Bootstrap starting =====")
    bootstrap_sql()
    bootstrap_blob()
    bootstrap_qdrant()
    bootstrap_ollama()
    print("===== Bootstrap complete =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
