import { FormEvent, useEffect, useRef, useState } from "react";
import { queryApi } from "../api";
import { CompareSelectedButton } from "../components/CompareModal";
import { ContractDrawer } from "../components/ContractDrawer";
import { MarkdownAnswer } from "../components/MarkdownAnswer";
import { STATUS_BADGE, displayStatus } from "../statusBadge";
import { SUGGESTIONS } from "../suggestions";
import type { ChatMessage, Citation, QueryResponse, TokenUsage } from "../types";

const INTENT_BADGE: Record<string, string> = {
  reporting: "badge-ok",
  search: "badge-info",
  clause_comparison: "badge-warn",
  relationship: "badge-danger",
  out_of_scope: "badge-danger",
};

export default function Chat() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Track AbortController for the currently-in-flight message (if any).
  // Only one question can be busy at a time: pressing Ask again — or hitting
  // Stop — aborts whatever is in flight.
  const inFlight = useRef<{ idx: number; ctrl: AbortController } | null>(null);

  function pickSuggestion(s: string) {
    setQuestion(s);
    // Defer focus so React commits the value first.
    setTimeout(() => textareaRef.current?.focus(), 0);
  }

  // Cancel any in-flight request on unmount.
  useEffect(() => () => inFlight.current?.ctrl.abort(), []);

  function cancelCurrent(reason: "user" | "superseded" = "user") {
    const inf = inFlight.current;
    if (!inf) return;
    inf.ctrl.abort();
    setMessages((m) =>
      m.map((msg, i) =>
        i === inf.idx
          ? {
              ...msg,
              busy: false,
              cancelled: true,
              error:
                reason === "user"
                  ? "cancelled by user"
                  : "cancelled — superseded by new question",
            }
          : msg,
      ),
    );
    inFlight.current = null;
  }

  async function ask(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    if (inFlight.current) cancelCurrent("superseded");

    const ctrl = new AbortController();
    let idx = 0;
    setMessages((m) => {
      idx = m.length;
      return [...m, { question: trimmed, busy: true }];
    });
    setQuestion("");
    await Promise.resolve();
    inFlight.current = { idx, ctrl };

    try {
      const response = await queryApi(trimmed, ctrl.signal);
      setMessages((m) =>
        m.map((msg, i) =>
          i === idx ? { ...msg, busy: false, response } : msg,
        ),
      );
      inFlight.current = null;
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setMessages((m) =>
        m.map((msg, i) =>
          i === idx
            ? { ...msg, busy: false, error: (err as Error).message }
            : msg,
        ),
      );
      inFlight.current = null;
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await ask(question);
  }

  function clearConversation() {
    if (inFlight.current) cancelCurrent("user");
    setMessages([]);
  }

  const someBusy = inFlight.current !== null;

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit}>
        <div className="composer">
          <textarea
            ref={textareaRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about contracts, clauses, or comparisons…"
            rows={3}
            className="composer-input"
          />
          <div className="composer-actions">
            {messages.length > 0 && (
              <button
                type="button"
                onClick={clearConversation}
                className="btn btn-ghost px-3 py-1.5 text-sm"
              >
                Clear
              </button>
            )}
            {someBusy && (
              <button
                type="button"
                onClick={() => cancelCurrent("user")}
                title="Stops waiting locally. The server still finishes the LLM call."
                className="btn btn-ghost px-3 py-1.5 text-sm"
              >
                Stop
              </button>
            )}
            <button
              type="submit"
              disabled={!question.trim()}
              className="btn btn-primary"
            >
              {someBusy && question.trim() ? "Ask (cancel current)" : "Ask"}
            </button>
          </div>
        </div>
      </form>

      <div
        role="list"
        className="grid gap-2 [grid-template-columns:repeat(3,minmax(0,1fr))] sm:[grid-template-columns:repeat(3,minmax(0,1fr))] [@media(max-width:640px)]:[grid-template-columns:1fr]"
      >
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            role="listitem"
            onClick={() => pickSuggestion(s)}
            title={s}
            className="suggestion-card"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-4">
        {messages.length === 0 && (
          <p className="text-sm italic text-[--color-muted-fg]">
            No questions yet. Try a suggestion above.
          </p>
        )}
        {messages.map((m, i) => (
          <Message key={i} m={m} />
        ))}
      </div>
    </div>
  );
}

function Message({ m }: { m: ChatMessage }) {
  return (
    <article className="surface-card flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-1">
        <RoleLabel>You</RoleLabel>
        <p className="m-0 leading-relaxed">{m.question}</p>
      </div>
      <div className="flex flex-col gap-2 border-t border-dashed border-[--color-border] pt-3">
        <RoleLabel>Assistant</RoleLabel>
        {m.busy && (
          <p className="m-0 text-sm italic text-[--color-muted-fg]">
            Asking…
          </p>
        )}
        {m.cancelled && !m.response && (
          <p className="m-0 flex items-center gap-2 text-sm text-[--color-muted-fg]">
            <span className="badge badge-warn">cancelled</span> {m.error}
          </p>
        )}
        {!m.cancelled && m.error && (
          <div
            className="rounded-md px-3 py-2 text-sm"
            style={{
              background: "var(--color-danger-bg)",
              color: "var(--color-danger-fg)",
            }}
          >
            Error: {m.error}
          </div>
        )}
        {m.response && <ResponseBody r={m.response} />}
      </div>
    </article>
  );
}

// Compact thousands formatter — 1234 → "1.2k", values <1000 stay as-is.
function compactTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
}

// Render one data-source label with token counts inline when applicable.
// llm  → (prompt/completion) e.g. "llm (899/562)"
// embeddings / *_index → (embedding_tokens) e.g. "embeddings (13)"
// SQL / gold_clauses / graph → no count.
function SourceTag({
  source,
  usage,
}: {
  source: string;
  usage?: TokenUsage | null;
}) {
  if (!usage) return <span>{source}</span>;
  if (source === "llm" && (usage.prompt_tokens || usage.completion_tokens)) {
    return (
      <span title={`${usage.prompt_tokens} prompt / ${usage.completion_tokens} completion tokens`}>
        {source} ({compactTokens(usage.prompt_tokens)}/{compactTokens(usage.completion_tokens)})
      </span>
    );
  }
  if (source === "embeddings" && usage.embedding_tokens) {
    return (
      <span title={`${usage.embedding_tokens} embedding tokens`}>
        {source} ({compactTokens(usage.embedding_tokens)})
      </span>
    );
  }
  return <span>{source}</span>;
}

function RoleLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-[--color-muted-fg]">
      {children}
    </span>
  );
}

function ResponseBody({ r }: { r: QueryResponse }) {
  const intentClass = INTENT_BADGE[r.intent] ?? "badge-info";
  const usage = r.token_usage;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-xs text-[--color-muted-fg]">
        <span className={`badge ${intentClass}`}>{r.intent}</span>
        <span title={r.fallback_reason ?? "matched by deterministic rules"}>
          {r.fallback_reason === "llm-classified" ? "llm-routed" : "rule-routed"}
          {" "}· conf {r.confidence.toFixed(2)}
        </span>
        <span className="flex flex-wrap items-center gap-1.5">
          {r.data_sources.map((src) => (
            <SourceTag key={src} source={src} usage={usage} />
          ))}
        </span>
        <span>{r.elapsed_ms} ms</span>
        {usage && usage.estimated_cost_usd > 0 && (
          <span title="Estimated cost in USD based on per-model list price">
            ${usage.estimated_cost_usd.toFixed(4)}
          </span>
        )}
      </div>
      {r.subject_contracts && r.subject_contracts.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-[--color-muted-fg]">
            Compared against
          </span>
          <RowsTable rows={r.subject_contracts} />
        </div>
      )}
      <MarkdownAnswer text={r.answer} italic={r.out_of_scope} />
      {r.rows && r.rows.length > 0 && <RowsTable rows={r.rows} />}
      {r.citations.length > 0 && <CitationList cites={r.citations} />}
    </>
  );
}

// Date-like column names get the same nowrap treatment as the Contracts tab
// so dates don't wrap awkwardly in the result table.
const DATE_COLS = new Set([
  "EffectiveDate",
  "ExpirationDate",
  "RenewalDate",
  "UpdatedAt",
  "CreatedAt",
]);

function findIdColumn(cols: string[]): string | null {
  // Reporting rows from src/shared/sql_builder.build_reporting_sql project
  // ContractId. Tolerate snake_case in case other handlers add rows later.
  const lc = (s: string) => s.toLowerCase().replace(/_/g, "");
  return cols.find((c) => lc(c) === "contractid") ?? null;
}

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Object.keys(rows[0]);
  const idCol = findIdColumn(cols);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function toggleAll() {
    if (!idCol) return;
    setSelected((s) => {
      const all = rows
        .map((r) => String(r[idCol] ?? ""))
        .filter(Boolean);
      const allSelected = all.every((id) => s.has(id));
      return allSelected ? new Set() : new Set(all);
    });
  }

  return (
    <div className="flex flex-col gap-2">
      {idCol && selected.size > 0 && (
        <div className="flex items-center gap-3">
          <CompareSelectedButton ids={Array.from(selected)} />
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="btn btn-ghost px-3 py-1.5 text-sm"
          >
            Clear selection
          </button>
        </div>
      )}
      <div className="-mx-4 overflow-x-auto px-4">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              {idCol && (
                <th className="border-b border-[--color-border] px-2 py-2 text-left">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={
                      selected.size > 0 &&
                      rows.every((r) => selected.has(String(r[idCol] ?? "")))
                    }
                    onChange={toggleAll}
                    className="cursor-pointer accent-[--color-accent]"
                  />
                </th>
              )}
              {cols.map((c) => (
                <th
                  key={c}
                  className="whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const id = idCol ? String(row[idCol] ?? "") : null;
              const isSelected = id != null && selected.has(id);
              const isOpen = id != null && openId === id;
              return (
                <tr
                  key={i}
                  onClick={id ? () => setOpenId(id) : undefined}
                  className={`transition-colors duration-100 ${
                    id ? "cursor-pointer" : ""
                  } ${
                    isOpen
                      ? "bg-[--color-accent-soft]"
                      : isSelected
                        ? "bg-[--color-accent-soft]"
                        : id
                          ? "hover:bg-[--color-accent-soft]/50"
                          : ""
                  }`}
                >
                  {idCol && (
                    <td
                      onClick={(e) => e.stopPropagation()}
                      className="border-b border-[--color-border] px-2 py-2 align-middle"
                    >
                      {id && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggle(id)}
                          className="cursor-pointer accent-[--color-accent]"
                        />
                      )}
                    </td>
                  )}
                  {cols.map((c) => {
                    let content: React.ReactNode = String(row[c] ?? "");
                    if (c === "Status") {
                      const s = displayStatus(
                        row[c] as string | null | undefined,
                        row["ExpirationDate"] as string | null | undefined,
                      );
                      content = (
                        <span className={`badge ${STATUS_BADGE[s] ?? "badge-info"}`}>
                          {s}
                        </span>
                      );
                    }
                    return (
                      <td
                        key={c}
                        className={`border-b border-[--color-border] px-2.5 py-2 align-middle ${
                          DATE_COLS.has(c) ? "whitespace-nowrap" : ""
                        }`}
                      >
                        {content}
                      </td>
                    );
                  })}
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

function CitationList({ cites }: { cites: Citation[] }) {
  return (
    <aside className="mt-2">
      <h3 className="m-0 mb-2 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]">
        Citations
      </h3>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {cites.map((c, i) => (
          <li key={i} className="flex flex-col gap-1">
            <div className="text-sm">
              <strong>{c.contract_title ?? c.contract_id}</strong>
              {c.page != null && (
                <span className="text-[--color-muted-fg]"> — p.{c.page}</span>
              )}
            </div>
            {/*
              Citation text is rendered as plain text in a styled blockquote
              (NOT through MarkdownAnswer). Reason: c.quote is post-extraction
              prose pulled from dbo.ContractClause.ClauseText — the source
              markdown was lost at PDF render time, so any markdown chars in
              the text are accidental. Markdown-rendering would invent
              formatting the contract never had.
            */}
            <blockquote
              className="m-0 whitespace-pre-wrap rounded-md border-l-[3px] border-[--color-accent] px-3 py-2 text-sm leading-relaxed"
              style={{ background: "var(--color-card-2)" }}
            >
              {c.quote}
            </blockquote>
          </li>
        ))}
      </ul>
    </aside>
  );
}
