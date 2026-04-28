import { useEffect, useState } from "react";
import { getContract } from "../api";
import type { ContractDetail } from "../types";

const RISK_BADGE: Record<string, string> = {
  low: "badge-ok",
  medium: "badge-warn",
  high: "badge-danger",
};

// Inline-renderable in browsers vs. download-only. Mirrors the server-side
// _MIME_BY_EXT map in src/local/api_server.py — keep them in sync. The link
// label flips between "Open" and "Download" so users aren't surprised when
// clicking pulls a Word doc instead of opening one.
const _INLINE_EXTS = new Set(["pdf", "txt", "html", "htm"]);

function sourceLinkLabel(blobUri: string | null | undefined): string {
  if (!blobUri) return "Open source ↗";
  const filename = blobUri.split("/").pop() ?? "";
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (_INLINE_EXTS.has(ext)) return `Open ${ext.toUpperCase()} ↗`;
  if (ext) return `Download ${ext.toUpperCase()} ↓`;
  return "Open source ↗";
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

export function ContractDrawer({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [tab, setTab] = useState<"meta" | "clauses" | "obligations" | "audit">(
    "meta",
  );
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    getContract(id)
      .then(setDetail)
      .catch((e) => setErr(e.message));
  }, [id]);

  return (
    <div
      className="fixed inset-0 z-[100] flex justify-end backdrop-blur-sm"
      style={{ background: "var(--color-overlay)" }}
      onClick={onClose}
    >
      <div
        className="flex h-full w-[min(720px,100%)] flex-col gap-3 overflow-y-auto p-5 shadow-2xl animate-[slideIn_220ms_ease-out]"
        style={{ background: "var(--color-card)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <style>{`@keyframes slideIn { from { transform: translateX(24px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }`}</style>
        <header className="flex items-center justify-between gap-3 border-b border-[--color-border] pb-3">
          <h2 className="m-0 truncate text-base font-semibold">
            {detail?.ContractTitle ?? id}
          </h2>
          <CloseButton onClick={onClose} />
        </header>
        {err && <ErrorBox>Error: {err}</ErrorBox>}
        {!detail && !err && (
          <p className="text-sm italic text-[--color-muted-fg]">Loading…</p>
        )}
        {detail && (
          <>
            <nav className="flex gap-1 border-b border-[--color-border]">
              {(["meta", "clauses", "obligations", "audit"] as const).map((t) => {
                const active = tab === t;
                return (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`relative cursor-pointer border-0 bg-transparent px-3 py-2 text-sm font-medium leading-none transition-colors duration-150 ${
                      active
                        ? "text-[--color-accent]"
                        : "text-[--color-muted-fg] hover:text-[--color-fg]"
                    }`}
                  >
                    {t}
                    {t === "clauses" && ` (${detail.Clauses.length})`}
                    {t === "obligations" && ` (${detail.Obligations.length})`}
                    {t === "audit" && ` (${detail.Audit.length})`}
                    <span
                      aria-hidden="true"
                      className={`absolute inset-x-2 -bottom-px h-[2px] rounded-full transition-transform duration-200 ${
                        active ? "scale-x-100" : "scale-x-0"
                      }`}
                      style={{ background: "var(--color-accent)" }}
                    />
                  </button>
                );
              })}
            </nav>
            {tab === "meta" && <MetaTab d={detail} />}
            {tab === "clauses" && <ClausesTab d={detail} />}
            {tab === "obligations" && <ObligationsTab d={detail} />}
            {tab === "audit" && <AuditTab d={detail} />}
          </>
        )}
      </div>
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

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]">
      {children}
    </th>
  );
}

function MetaTab({ d }: { d: ContractDetail }) {
  // Tuple: [display label, value, optional API field key for inheritance lookup].
  // When the API key is present and the value is null, we check d.Inherited
  // for a sibling-contract value to surface alongside the literal null.
  const fields: [string, string | number | null | boolean, string?][] = [
    ["Counterparty", d.Counterparty],
    ["Type", d.ContractType],
    ["Effective", d.EffectiveDate],
    ["Expiration", d.ExpirationDate],
    ["Renewal", d.RenewalDate],
    ["Auto-renewal", d.AutoRenewalFlag],
    ["Governing Law", d.GoverningLaw, "GoverningLaw"],
    ["Jurisdiction", d.Jurisdiction, "Jurisdiction"],
    ["Value", d.ContractValue],
    ["Currency", d.Currency],
    ["Business Owner", d.BusinessOwner],
    ["Legal Owner", d.LegalOwner],
    ["Status", d.Status],
    ["Review status", d.ReviewStatus],
    ["Extraction confidence", d.ExtractionConfidence],
  ];
  return (
    <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
      {fields.map(([k, v, apiKey]) => {
        const inherited = apiKey ? d.Inherited?.[apiKey] : undefined;
        return (
          <div key={k} className="flex flex-col">
            <dt className="text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]">
              {k}
            </dt>
            <dd className="m-0 break-words text-sm">
              {v == null || v === "" ? (
                inherited ? (
                  <>
                    <span>{String(inherited.value)}</span>{" "}
                    <span
                      className="text-xs italic text-[--color-muted-fg]"
                      title={`Inherited from ${inherited.source_contract_title ?? "sibling contract"}`}
                    >
                      (inherited from {inherited.source_contract_title ?? "sibling contract"})
                    </span>
                  </>
                ) : (
                  <span className="text-[--color-muted-fg]">—</span>
                )
              ) : (
                String(v)
              )}
            </dd>
          </div>
        );
      })}
      {d.BlobUri && (
        <div className="flex flex-col sm:col-span-2">
          <dt className="text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]">
            Source file
          </dt>
          <dd className="m-0 text-sm">
            {d.FileUrl ? (
              <a
                href={d.FileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[--color-accent] underline underline-offset-2 hover:no-underline"
              >
                {sourceLinkLabel(d.BlobUri)}
              </a>
            ) : (
              <span className="text-[--color-muted-fg] break-all">
                {d.BlobUri}
              </span>
            )}
            <span className="ml-3 text-[--color-muted-fg] break-all">
              {d.BlobUri}
            </span>
          </dd>
        </div>
      )}
    </dl>
  );
}

function ClausesTab({ d }: { d: ContractDetail }) {
  if (d.Clauses.length === 0)
    return (
      <p className="text-sm italic text-[--color-muted-fg]">
        No clauses extracted.
      </p>
    );
  return (
    <div className="flex flex-col gap-2">
      {d.Clauses.map((c) => (
        <details
          key={c.ClauseId}
          className="group rounded-md border border-[--color-border] px-3 py-2 [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden"
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
            <strong className="font-medium">
              {c.ClauseType ?? "(unclassified)"}
            </strong>
            {c.PageNumber != null && (
              <span className="text-[--color-muted-fg]">· p.{c.PageNumber}</span>
            )}
            {c.RiskLevel && (
              <span className={`badge ${RISK_BADGE[c.RiskLevel] ?? "badge-info"}`}>
                {c.RiskLevel}
              </span>
            )}
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
            {c.ClauseText}
          </p>
          {c.SectionHeading && (
            <p className="mt-1 text-xs text-[--color-muted-fg]">
              Section: {c.SectionHeading}
            </p>
          )}
        </details>
      ))}
    </div>
  );
}

function ObligationsTab({ d }: { d: ContractDetail }) {
  if (d.Obligations.length === 0)
    return (
      <p className="text-sm italic text-[--color-muted-fg]">
        No obligations extracted.
      </p>
    );
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <Th>Party</Th>
            <Th>Text</Th>
            <Th>Due</Th>
            <Th>Frequency</Th>
            <Th>Risk</Th>
          </tr>
        </thead>
        <tbody>
          {d.Obligations.map((o) => (
            <tr key={o.ObligationId}>
              <Cell>{o.Party ?? "—"}</Cell>
              <Cell>{o.ObligationText}</Cell>
              <Cell nowrap>{o.DueDate?.slice(0, 10) ?? "—"}</Cell>
              <Cell>{o.Frequency ?? "—"}</Cell>
              <Cell>
                {o.RiskLevel ? (
                  <span
                    className={`badge ${
                      RISK_BADGE[o.RiskLevel] ?? "badge-info"
                    }`}
                  >
                    {o.RiskLevel}
                  </span>
                ) : (
                  "—"
                )}
              </Cell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTab({ d }: { d: ContractDetail }) {
  if (d.Audit.length === 0)
    return (
      <p className="text-sm italic text-[--color-muted-fg]">No audit history.</p>
    );
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <Th>Field</Th>
            <Th>Value</Th>
            <Th>Method</Th>
            <Th>Model</Th>
            <Th>Confidence</Th>
            <Th>When</Th>
          </tr>
        </thead>
        <tbody>
          {d.Audit.map((a) => (
            <tr key={a.AuditId}>
              <Cell>{a.FieldName}</Cell>
              <Cell>{a.FieldValue ?? "—"}</Cell>
              <Cell>{a.ExtractionMethod ?? "—"}</Cell>
              <Cell>{a.ModelName ?? "—"}</Cell>
              <Cell>{a.Confidence ?? "—"}</Cell>
              <Cell nowrap>{a.CreatedAt?.slice(0, 19).replace("T", " ")}</Cell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
