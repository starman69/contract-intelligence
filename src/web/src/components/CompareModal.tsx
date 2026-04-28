import { useEffect, useState } from "react";
import { compare, listGoldClauses } from "../api";
import type { CompareResponse, GoldClause } from "../types";
import { MarkdownAnswer } from "./MarkdownAnswer";

// Compact thousands formatter mirroring Chat's helper.
function compact(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
}

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

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Close"
      className="btn btn-ghost btn-icon text-lg"
    >
      ×
    </button>
  );
}

export function CompareSelectedButton({
  ids,
  label,
}: {
  ids: string[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-primary"
      >
        {label ?? `Compare ${ids.length} to gold…`}
      </button>
      {open && <CompareModal ids={ids} onClose={() => setOpen(false)} />}
    </>
  );
}

export function CompareModal({
  ids,
  onClose,
}: {
  ids: string[];
  onClose: () => void;
}) {
  const [gold, setGold] = useState<GoldClause[]>([]);
  const [pickedTypes, setPickedTypes] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<Record<string, CompareResponse>>({});
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listGoldClauses().then(setGold).catch((e) => setErr(e.message));
  }, []);

  const uniqueTypes = Array.from(new Set(gold.map((g) => g.ClauseType)));

  function toggle(t: string) {
    setPickedTypes((p) => {
      const n = new Set(p);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });
  }

  const allPicked = uniqueTypes.length > 0 && pickedTypes.size === uniqueTypes.length;
  function toggleAll() {
    setPickedTypes(allPicked ? new Set() : new Set(uniqueTypes));
  }

  async function run() {
    setRunning(true);
    setErr(null);
    setResults({});
    const types = Array.from(pickedTypes);
    try {
      const all: Record<string, CompareResponse> = {};
      for (const id of ids) {
        all[id] = await compare(id, types);
        setResults({ ...all });
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto p-8 backdrop-blur-sm"
      style={{ background: "var(--color-overlay)" }}
      onClick={onClose}
    >
      <div
        className="surface-card flex w-full max-w-[900px] flex-col gap-3 p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-[--color-border] pb-3">
          <h2 className="m-0 text-base font-semibold">
            Compare {ids.length} contract(s) to gold clauses
          </h2>
          <CloseButton onClick={onClose} />
        </header>
        <div className="flex items-center justify-between gap-3">
          <p className="m-0 text-sm text-[--color-muted-fg]">
            Pick which clause types to compare:
          </p>
          {uniqueTypes.length > 0 && (
            <button
              type="button"
              onClick={toggleAll}
              className="btn btn-ghost px-3 py-1.5 text-xs"
            >
              {allPicked ? "Unselect all" : `Select all (${uniqueTypes.length})`}
            </button>
          )}
        </div>
        <div className="grid gap-2 grid-cols-1 sm:grid-cols-2">
          {uniqueTypes.map((t) => (
            <label
              key={t}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-[--color-accent-soft]"
            >
              <input
                type="checkbox"
                checked={pickedTypes.has(t)}
                onChange={() => toggle(t)}
                className="cursor-pointer accent-[--color-accent]"
              />
              {t}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={run}
            disabled={running || pickedTypes.size === 0}
            className="btn btn-primary"
          >
            {running ? "Comparing…" : `Compare to ${pickedTypes.size} clause(s)`}
          </button>
        </div>
        {err && <ErrorBox>Error: {err}</ErrorBox>}
        {Object.entries(results).map(([id, r]) => (
          <ComparisonResultBlock key={id} contractId={id} resp={r} />
        ))}
      </div>
    </div>
  );
}

function ComparisonResultBlock({
  contractId,
  resp,
}: {
  contractId: string;
  resp: CompareResponse;
}) {
  const title = resp.contract_title || contractId;
  const usage = resp.token_usage;
  return (
    <section className="mt-2 border-t border-[--color-border] pt-3">
      <header className="mb-2 flex flex-col gap-1">
        <h3 className="m-0 text-sm font-semibold">{title}</h3>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[--color-muted-fg]">
          <span
            className="font-mono text-[0.7rem]"
            title="Contract ID (dbo.Contract.ContractId)"
          >
            {contractId}
          </span>
          {typeof resp.elapsed_ms === "number" && (
            <span>· {resp.elapsed_ms} ms</span>
          )}
          {usage && (usage.prompt_tokens > 0 || usage.completion_tokens > 0) && (
            <span title={`${usage.prompt_tokens} prompt / ${usage.completion_tokens} completion tokens`}>
              · llm ({compact(usage.prompt_tokens)}/{compact(usage.completion_tokens)})
            </span>
          )}
          {usage && usage.estimated_cost_usd > 0 && (
            <span title="Estimated USD cost based on per-model list price">
              · ${usage.estimated_cost_usd.toFixed(4)}
            </span>
          )}
          {usage && usage.calls && usage.calls.length > 0 && (
            <span title="LLM model used for the diff">
              · {usage.calls[0].model}
            </span>
          )}
        </div>
      </header>
      <div className="flex flex-col gap-2">
        {resp.comparisons.map((c) => (
          <details
            key={c.clause_type}
            className="surface-card group px-3 py-2 [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden"
            style={{ background: "var(--color-card-2)" }}
          >
            <summary className="flex cursor-pointer items-center gap-2 text-sm select-none">
              <svg
                className="h-4 w-4 shrink-0 text-[--color-muted-fg] transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="9 6 15 12 9 18" />
              </svg>
              <span className="font-medium">{c.clause_type}</span>
              {c.available ? (
                <span className="badge badge-ok">compared</span>
              ) : c.applicable === false ? (
                <span className="badge badge-info">{c.reason ?? "not applicable"}</span>
              ) : (
                <span className="badge badge-warn">{c.reason}</span>
              )}
            </summary>
            {c.available && (
              <div className="mt-2 flex flex-col gap-2">
                <h4 className="m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]">
                  Difference
                </h4>
                {/*
                  c.diff is the LLM's markdown analysis (summary paragraph +
                  ### Material differences bullets + ### Conclusion per
                  _COMPARE_SYSTEM in src/shared/api.py), not a unified diff.
                  Render through MarkdownAnswer so headings, bullets and
                  blockquoted clause text format correctly — same component
                  as the chat path uses. Keep the accent left-border so it's
                  visually anchored as the "diff result" surface.
                */}
                <div
                  className="rounded-md px-3 py-2 text-sm"
                  style={{
                    background: "var(--color-card)",
                    borderLeft: "3px solid var(--color-accent)",
                  }}
                >
                  <MarkdownAnswer text={c.diff ?? ""} />
                </div>
                <h4 className="m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]">
                  Contract clause (page {c.contract_page ?? "?"})
                </h4>
                <blockquote className="m-0 border-l-[3px] border-[--color-border-strong] pl-3 text-sm text-[--color-muted-fg]">
                  {c.contract_clause_text}
                </blockquote>
                <h4 className="m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]">
                  Gold {c.gold_clause_id} (v{c.gold_version})
                </h4>
                <div className="rounded-md border-l-[3px] border-[--color-border-strong] bg-[--color-card] px-3 py-2 text-sm">
                  <MarkdownAnswer text={c.gold_text ?? ""} />
                </div>
              </div>
            )}
          </details>
        ))}
      </div>
    </section>
  );
}
