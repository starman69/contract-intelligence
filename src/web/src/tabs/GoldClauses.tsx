import { useEffect, useState } from "react";
import { listGoldClauses } from "../api";
import { MarkdownAnswer } from "../components/MarkdownAnswer";
import type { GoldClause } from "../types";

export default function GoldClauses() {
  const [gold, setGold] = useState<GoldClause[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    listGoldClauses()
      .then(setGold)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return <p className="text-[--color-muted-fg] italic">Loading…</p>;
  if (err)
    return (
      <div
        className="rounded-lg px-3 py-2 text-sm"
        style={{
          background: "var(--color-danger-bg)",
          color: "var(--color-danger-fg)",
        }}
      >
        Error: {err}
      </div>
    );
  if (gold.length === 0)
    return (
      <p className="text-[--color-muted-fg] italic">
        No gold clauses seeded yet.
      </p>
    );

  // Latest version per type already comes first from the server.
  const seen = new Set<string>();
  const latest = gold.filter((g) => {
    if (seen.has(g.ClauseType)) return false;
    seen.add(g.ClauseType);
    return true;
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-[--color-muted-fg]">
        {latest.length} approved clause types · click to view the full text.
        Multi-contract comparison lives on the Contracts tab.
      </p>
      <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
        {latest.map((g) => {
          const expanded = open === g.StandardClauseId;
          return (
          <article
            key={g.StandardClauseId}
            className={`surface-card flex flex-col gap-3 p-4 transition-[grid-column] duration-200 ${
              expanded ? "md:col-span-2" : ""
            }`}
          >
            <header className="flex items-baseline justify-between gap-2">
              <h3 className="m-0 text-base font-semibold capitalize">
                {g.ClauseType}
              </h3>
              <span className="text-xs text-[--color-muted-fg]">
                v{g.Version}
              </span>
            </header>
            <dl className="m-0 flex flex-wrap gap-x-6 gap-y-2 text-xs">
              <span className="flex flex-col">
                <dt className="text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]">
                  jurisdiction
                </dt>
                <dd className="m-0">{g.Jurisdiction ?? "—"}</dd>
              </span>
              <span className="flex flex-col">
                <dt className="text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]">
                  effective
                </dt>
                <dd className="m-0">{g.EffectiveFrom?.slice(0, 10)}</dd>
              </span>
              <span className="flex flex-col">
                <dt className="text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]">
                  owner
                </dt>
                <dd className="m-0">{g.ReviewOwner ?? "—"}</dd>
              </span>
            </dl>
            <button
              type="button"
              onClick={() =>
                setOpen(open === g.StandardClauseId ? null : g.StandardClauseId)
              }
              className="btn btn-ghost self-start"
            >
              {open === g.StandardClauseId ? "Hide text" : "Show text"}
            </button>
            {open === g.StandardClauseId && (
              // Gold clauses are loaded straight from samples/gold-clauses/*.md
              // (markdown source preserved into dbo.StandardClause.ApprovedText),
              // so render through MarkdownAnswer to honour headings, lists, **bold**.
              // Same component as the chat answer + CompareModal gold panel.
              <div
                className="max-h-96 overflow-y-auto rounded-md px-3 py-2 text-sm"
                style={{
                  background: "var(--color-card-2)",
                  borderLeft: "3px solid var(--color-border-strong)",
                }}
              >
                <MarkdownAnswer text={g.ApprovedText} />
              </div>
            )}
            {g.RiskPolicy && (
              <p className="m-0 text-xs text-[--color-muted-fg]">
                <strong className="text-[--color-fg]">Policy:</strong>{" "}
                {g.RiskPolicy}
              </p>
            )}
          </article>
          );
        })}
      </div>
    </div>
  );
}
