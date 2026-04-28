import { useEffect, useRef, useState } from "react";
import { listContracts } from "../api";
import { CompareSelectedButton } from "../components/CompareModal";
import { ContractDrawer } from "../components/ContractDrawer";
import { STATUS_BADGE, displayStatus } from "../statusBadge";
import type { ContractSummary } from "../types";

// Whitelist of server-sortable columns. Mirrors `_CONTRACTS_SORTABLE` in
// src/shared/api.py — keep them in sync.
type SortKey =
  | "ContractTitle"
  | "Counterparty"
  | "ContractType"
  | "EffectiveDate"
  | "ExpirationDate"
  | "GoverningLaw"
  | "Status"
  | "UpdatedAt";
type SortDir = "asc" | "desc";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 250;

function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-sm"
      style={{
        background: "var(--color-danger-bg)",
        color: "var(--color-danger-fg)",
      }}
    >
      {children}
    </div>
  );
}

export default function Contracts() {
  const [rows, setRows] = useState<ContractSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "ExpirationDate",
    dir: "asc",
  });
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(searchInput);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  const reqRef = useRef<AbortController | null>(null);
  useEffect(() => {
    reqRef.current?.abort();
    const ac = new AbortController();
    reqRef.current = ac;
    setLoading(true);
    listContracts(
      { q, sort: sort.key, dir: sort.dir, limit: PAGE_SIZE, offset },
      ac.signal,
    )
      .then((resp) => {
        setRows(resp.rows);
        setTotal(resp.total);
        setError(null);
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e.message);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [q, sort, offset]);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function setSortKey(k: SortKey) {
    setSort((s) => ({
      key: k,
      dir: s.key === k && s.dir === "asc" ? "desc" : "asc",
    }));
    setOffset(0);
  }

  const lastIndex = Math.min(offset + rows.length, total);
  const firstIndex = total === 0 ? 0 : offset + 1;
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="search title / counterparty / type…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="field flex-1 min-w-[16rem]"
        />
        {selected.size > 0 && (
          <CompareSelectedButton ids={Array.from(selected)} />
        )}
        <span className="text-sm text-[--color-muted-fg]">
          {total === 0
            ? loading
              ? "loading…"
              : "no contracts match"
            : `${firstIndex}–${lastIndex} of ${total}`}
        </span>
        <span className="ml-auto inline-flex gap-1">
          <button
            type="button"
            disabled={!hasPrev || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="btn btn-ghost px-3 py-1.5 text-sm"
          >
            ← Prev
          </button>
          <button
            type="button"
            disabled={!hasNext || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="btn btn-ghost px-3 py-1.5 text-sm"
          >
            Next →
          </button>
        </span>
      </div>

      {error && <ErrorBox>Error: {error}</ErrorBox>}

      <div
        className="surface-card overflow-x-auto p-0 transition-opacity duration-150 aria-busy:opacity-60"
        aria-busy={loading}
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="border-b border-[--color-border] px-2 py-2"></th>
              <SortHeader k="ContractTitle" sort={sort} onClick={setSortKey}>
                Title
              </SortHeader>
              <SortHeader k="Counterparty" sort={sort} onClick={setSortKey}>
                Counterparty
              </SortHeader>
              <SortHeader k="ContractType" sort={sort} onClick={setSortKey}>
                Type
              </SortHeader>
              <SortHeader k="EffectiveDate" sort={sort} onClick={setSortKey}>
                Effective
              </SortHeader>
              <SortHeader k="ExpirationDate" sort={sort} onClick={setSortKey}>
                Expires
              </SortHeader>
              <SortHeader k="GoverningLaw" sort={sort} onClick={setSortKey}>
                Governing Law
              </SortHeader>
              <SortHeader k="Status" sort={sort} onClick={setSortKey}>
                Status
              </SortHeader>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const isOpen = openId === c.ContractId;
              return (
                <tr
                  key={c.ContractId}
                  onClick={() => setOpenId(c.ContractId)}
                  className={`cursor-pointer transition-colors duration-100 ${
                    isOpen
                      ? "bg-[--color-accent-soft]"
                      : "hover:bg-[--color-accent-soft]/50"
                  }`}
                >
                  <td
                    onClick={(e) => e.stopPropagation()}
                    className="border-b border-[--color-border] px-2 py-2 align-middle"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(c.ContractId)}
                      onChange={() => toggle(c.ContractId)}
                      className="cursor-pointer accent-[--color-accent]"
                    />
                  </td>
                  <Cell>{c.ContractTitle ?? "—"}</Cell>
                  <Cell>{c.Counterparty ?? "—"}</Cell>
                  <Cell>{c.ContractType ?? "—"}</Cell>
                  <Cell nowrap>{c.EffectiveDate?.slice(0, 10) ?? "—"}</Cell>
                  <Cell nowrap>{c.ExpirationDate?.slice(0, 10) ?? "—"}</Cell>
                  <Cell>{c.GoverningLaw ?? "—"}</Cell>
                  <Cell>
                    {(() => {
                      const s = displayStatus(c.Status, c.ExpirationDate);
                      return (
                        <span className={`badge ${STATUS_BADGE[s] ?? "badge-info"}`}>
                          {s}
                        </span>
                      );
                    })()}
                  </Cell>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {openId && (
        <ContractDrawer id={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function Cell({
  children,
  nowrap,
}: {
  children: React.ReactNode;
  nowrap?: boolean;
}) {
  return (
    <td
      className={`border-b border-[--color-border] px-2.5 py-2 align-middle ${
        nowrap ? "whitespace-nowrap" : ""
      }`}
    >
      {children}
    </td>
  );
}

function SortHeader({
  k,
  sort,
  onClick,
  children,
}: {
  k: SortKey;
  sort: { key: SortKey; dir: SortDir };
  onClick: (k: SortKey) => void;
  children: React.ReactNode;
}) {
  const active = sort.key === k;
  const arrow = active ? (sort.dir === "asc" ? "▲" : "▼") : "";
  return (
    <th
      onClick={() => onClick(k)}
      className={`cursor-pointer select-none whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider transition-colors duration-100 hover:text-[--color-accent] ${
        active ? "text-[--color-accent]" : "text-[--color-muted-fg]"
      }`}
    >
      {children}
      {arrow && <span className="ml-1 text-[0.7em]">{arrow}</span>}
    </th>
  );
}

