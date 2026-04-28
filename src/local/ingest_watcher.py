"""Local ingest watcher — polls the Azurite `raw/` container under `contracts/`
and calls pipeline.process_blob_event for each new blob.

Production uses Event Grid → src/functions/ingestion/function_app.py blob
trigger. This is the docker-compose equivalent — same downstream call into
pipeline.process_blob_event, just with a polling loop instead of a push trigger.

Tracks processed blob names in memory; on container restart it re-checks the
SQL `IngestionJob` table to avoid reprocessing blobs that already have a
successful job row.

Run with:
  python -m local.ingest_watcher
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# pipeline.py lives next to function_app.py inside src/functions/ingestion/
# (it isn't currently a package). Add that dir to sys.path so we can import it
# without restructuring the existing Functions deploy.
_PIPELINE_DIR = (
    Path(__file__).resolve().parents[1] / "functions" / "ingestion"
)
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from pipeline import process_blob_event  # noqa: E402
from shared import clients  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("local.ingest_watcher")

POLL_INTERVAL = float(os.environ.get("INGEST_POLL_INTERVAL", "5.0"))
BLOB_PREFIX = "contracts/"


def _already_processed_uris() -> set[str]:
    """Return blob URIs that already have a successful IngestionJob row.
    Defensive against container restart so we don't re-ingest the corpus."""
    try:
        with clients.sql_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT BlobUri FROM dbo.IngestionJob WHERE Status = 'success'"
            )
            return {row[0] for row in cur.fetchall()}
    except Exception:
        LOG.exception("Could not load IngestionJob history; starting empty")
        return set()


def main() -> int:
    LOG.info(
        "Ingest watcher starting; poll=%.1fs prefix=%s", POLL_INTERVAL, BLOB_PREFIX
    )
    s = clients.settings()
    bsc = clients.blob_service()
    container = bsc.get_container_client(s.blob_raw_container)
    seen: set[str] = _already_processed_uris()
    LOG.info("Loaded %d previously-successful URIs from IngestionJob", len(seen))

    while True:
        try:
            for blob in container.list_blobs(name_starts_with=BLOB_PREFIX):
                # Reconstruct the full URI in the same shape pipeline expects
                # (Azurite-style with the dev account in the path).
                blob_url = f"{bsc.url.rstrip('/')}/{s.blob_raw_container}/{blob.name}"
                if blob_url in seen:
                    continue
                LOG.info("Processing new blob: %s", blob.name)
                try:
                    process_blob_event(blob_url=blob_url, event_id=blob.name)
                    seen.add(blob_url)
                except Exception:
                    LOG.exception(
                        "Ingestion failed for %s (will retry next poll)", blob.name
                    )
        except Exception:
            LOG.exception("Watcher loop error")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
