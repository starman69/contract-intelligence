import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { queryApi } from "../api";
import { CompareSelectedButton } from "../components/CompareModal";
import { ContractDrawer } from "../components/ContractDrawer";
import { MarkdownAnswer } from "../components/MarkdownAnswer";
import { STATUS_BADGE, displayStatus } from "../statusBadge";
import { SUGGESTIONS } from "../suggestions";
const INTENT_BADGE = {
    reporting: "badge-ok",
    search: "badge-info",
    clause_comparison: "badge-warn",
    relationship: "badge-danger",
    out_of_scope: "badge-danger",
};
export default function Chat() {
    const [question, setQuestion] = useState("");
    const [messages, setMessages] = useState([]);
    const textareaRef = useRef(null);
    // Track AbortController for the currently-in-flight message (if any).
    // Only one question can be busy at a time: pressing Ask again — or hitting
    // Stop — aborts whatever is in flight.
    const inFlight = useRef(null);
    function pickSuggestion(s) {
        setQuestion(s);
        // Defer focus so React commits the value first.
        setTimeout(() => textareaRef.current?.focus(), 0);
    }
    // Cancel any in-flight request on unmount.
    useEffect(() => () => inFlight.current?.ctrl.abort(), []);
    function cancelCurrent(reason = "user") {
        const inf = inFlight.current;
        if (!inf)
            return;
        inf.ctrl.abort();
        setMessages((m) => m.map((msg, i) => i === inf.idx
            ? {
                ...msg,
                busy: false,
                cancelled: true,
                error: reason === "user"
                    ? "cancelled by user"
                    : "cancelled — superseded by new question",
            }
            : msg));
        inFlight.current = null;
    }
    async function ask(q) {
        const trimmed = q.trim();
        if (!trimmed)
            return;
        if (inFlight.current)
            cancelCurrent("superseded");
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
            setMessages((m) => m.map((msg, i) => i === idx ? { ...msg, busy: false, response } : msg));
            inFlight.current = null;
        }
        catch (err) {
            if (err.name === "AbortError")
                return;
            setMessages((m) => m.map((msg, i) => i === idx
                ? { ...msg, busy: false, error: err.message }
                : msg));
            inFlight.current = null;
        }
    }
    async function onSubmit(e) {
        e.preventDefault();
        await ask(question);
    }
    function clearConversation() {
        if (inFlight.current)
            cancelCurrent("user");
        setMessages([]);
    }
    const someBusy = inFlight.current !== null;
    return (_jsxs("div", { className: "flex flex-col gap-6", children: [_jsx("form", { onSubmit: onSubmit, children: _jsxs("div", { className: "composer", children: [_jsx("textarea", { ref: textareaRef, value: question, onChange: (e) => setQuestion(e.target.value), placeholder: "Ask about contracts, clauses, or comparisons\u2026", rows: 3, className: "composer-input" }), _jsxs("div", { className: "composer-actions", children: [messages.length > 0 && (_jsx("button", { type: "button", onClick: clearConversation, className: "btn btn-ghost px-3 py-1.5 text-sm", children: "Clear" })), someBusy && (_jsx("button", { type: "button", onClick: () => cancelCurrent("user"), title: "Stops waiting locally. The server still finishes the LLM call.", className: "btn btn-ghost px-3 py-1.5 text-sm", children: "Stop" })), _jsx("button", { type: "submit", disabled: !question.trim(), className: "btn btn-primary", children: someBusy && question.trim() ? "Ask (cancel current)" : "Ask" })] })] }) }), _jsx("div", { role: "list", className: "grid gap-2 [grid-template-columns:repeat(3,minmax(0,1fr))] sm:[grid-template-columns:repeat(3,minmax(0,1fr))] [@media(max-width:640px)]:[grid-template-columns:1fr]", children: SUGGESTIONS.map((s) => (_jsx("button", { type: "button", role: "listitem", onClick: () => pickSuggestion(s), title: s, className: "suggestion-card", children: s }, s))) }), _jsxs("div", { className: "flex flex-col gap-4", children: [messages.length === 0 && (_jsx("p", { className: "text-sm italic text-[--color-muted-fg]", children: "No questions yet. Try a suggestion above." })), messages.map((m, i) => (_jsx(Message, { m: m }, i)))] })] }));
}
function Message({ m }) {
    return (_jsxs("article", { className: "surface-card flex flex-col gap-3 p-4", children: [_jsxs("div", { className: "flex flex-col gap-1", children: [_jsx(RoleLabel, { children: "You" }), _jsx("p", { className: "m-0 leading-relaxed", children: m.question })] }), _jsxs("div", { className: "flex flex-col gap-2 border-t border-dashed border-[--color-border] pt-3", children: [_jsx(RoleLabel, { children: "Assistant" }), m.busy && (_jsx("p", { className: "m-0 text-sm italic text-[--color-muted-fg]", children: "Asking\u2026" })), m.cancelled && !m.response && (_jsxs("p", { className: "m-0 flex items-center gap-2 text-sm text-[--color-muted-fg]", children: [_jsx("span", { className: "badge badge-warn", children: "cancelled" }), " ", m.error] })), !m.cancelled && m.error && (_jsxs("div", { className: "rounded-md px-3 py-2 text-sm", style: {
                            background: "var(--color-danger-bg)",
                            color: "var(--color-danger-fg)",
                        }, children: ["Error: ", m.error] })), m.response && _jsx(ResponseBody, { r: m.response })] })] }));
}
// Compact thousands formatter — 1234 → "1.2k", values <1000 stay as-is.
function compactTokens(n) {
    if (n < 1000)
        return String(n);
    return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
}
// Render one data-source label with token counts inline when applicable.
// llm  → (prompt/completion) e.g. "llm (899/562)"
// embeddings / *_index → (embedding_tokens) e.g. "embeddings (13)"
// SQL / gold_clauses / graph → no count.
function SourceTag({ source, usage, }) {
    if (!usage)
        return _jsx("span", { children: source });
    if (source === "llm" && (usage.prompt_tokens || usage.completion_tokens)) {
        return (_jsxs("span", { title: `${usage.prompt_tokens} prompt / ${usage.completion_tokens} completion tokens`, children: [source, " (", compactTokens(usage.prompt_tokens), "/", compactTokens(usage.completion_tokens), ")"] }));
    }
    if (source === "embeddings" && usage.embedding_tokens) {
        return (_jsxs("span", { title: `${usage.embedding_tokens} embedding tokens`, children: [source, " (", compactTokens(usage.embedding_tokens), ")"] }));
    }
    return _jsx("span", { children: source });
}
function RoleLabel({ children }) {
    return (_jsx("span", { className: "text-[0.65rem] font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: children }));
}
function ResponseBody({ r }) {
    const intentClass = INTENT_BADGE[r.intent] ?? "badge-info";
    const usage = r.token_usage;
    return (_jsxs(_Fragment, { children: [_jsxs("div", { className: "flex flex-wrap items-center gap-2 text-xs text-[--color-muted-fg]", children: [_jsx("span", { className: `badge ${intentClass}`, children: r.intent }), _jsxs("span", { title: r.fallback_reason ?? "matched by deterministic rules", children: [r.fallback_reason === "llm-classified" ? "llm-routed" : "rule-routed", " ", "\u00B7 conf ", r.confidence.toFixed(2)] }), _jsx("span", { className: "flex flex-wrap items-center gap-1.5", children: r.data_sources.map((src) => (_jsx(SourceTag, { source: src, usage: usage }, src))) }), _jsxs("span", { children: [r.elapsed_ms, " ms"] }), usage && usage.estimated_cost_usd > 0 && (_jsxs("span", { title: "Estimated cost in USD based on per-model list price", children: ["$", usage.estimated_cost_usd.toFixed(4)] }))] }), r.subject_contracts && r.subject_contracts.length > 0 && (_jsxs("div", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-[0.65rem] font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: "Compared against" }), _jsx(RowsTable, { rows: r.subject_contracts })] })), _jsx(MarkdownAnswer, { text: r.answer, italic: r.out_of_scope }), r.rows && r.rows.length > 0 && _jsx(RowsTable, { rows: r.rows }), r.citations.length > 0 && _jsx(CitationList, { cites: r.citations })] }));
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
function findIdColumn(cols) {
    // Reporting rows from src/shared/sql_builder.build_reporting_sql project
    // ContractId. Tolerate snake_case in case other handlers add rows later.
    const lc = (s) => s.toLowerCase().replace(/_/g, "");
    return cols.find((c) => lc(c) === "contractid") ?? null;
}
function RowsTable({ rows }) {
    const cols = Object.keys(rows[0]);
    const idCol = findIdColumn(cols);
    const [selected, setSelected] = useState(new Set());
    const [openId, setOpenId] = useState(null);
    function toggle(id) {
        setSelected((s) => {
            const n = new Set(s);
            if (n.has(id))
                n.delete(id);
            else
                n.add(id);
            return n;
        });
    }
    function toggleAll() {
        if (!idCol)
            return;
        setSelected((s) => {
            const all = rows
                .map((r) => String(r[idCol] ?? ""))
                .filter(Boolean);
            const allSelected = all.every((id) => s.has(id));
            return allSelected ? new Set() : new Set(all);
        });
    }
    return (_jsxs("div", { className: "flex flex-col gap-2", children: [idCol && selected.size > 0 && (_jsxs("div", { className: "flex items-center gap-3", children: [_jsx(CompareSelectedButton, { ids: Array.from(selected) }), _jsx("button", { type: "button", onClick: () => setSelected(new Set()), className: "btn btn-ghost px-3 py-1.5 text-sm", children: "Clear selection" })] })), _jsx("div", { className: "-mx-4 overflow-x-auto px-4", children: _jsxs("table", { className: "w-full border-collapse text-sm", children: [_jsx("thead", { children: _jsxs("tr", { children: [idCol && (_jsx("th", { className: "border-b border-[--color-border] px-2 py-2 text-left", children: _jsx("input", { type: "checkbox", "aria-label": "Select all", checked: selected.size > 0 &&
                                                rows.every((r) => selected.has(String(r[idCol] ?? ""))), onChange: toggleAll, className: "cursor-pointer accent-[--color-accent]" }) })), cols.map((c) => (_jsx("th", { className: "whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]", children: c }, c)))] }) }), _jsx("tbody", { children: rows.map((row, i) => {
                                const id = idCol ? String(row[idCol] ?? "") : null;
                                const isSelected = id != null && selected.has(id);
                                const isOpen = id != null && openId === id;
                                return (_jsxs("tr", { onClick: id ? () => setOpenId(id) : undefined, className: `transition-colors duration-100 ${id ? "cursor-pointer" : ""} ${isOpen
                                        ? "bg-[--color-accent-soft]"
                                        : isSelected
                                            ? "bg-[--color-accent-soft]"
                                            : id
                                                ? "hover:bg-[--color-accent-soft]/50"
                                                : ""}`, children: [idCol && (_jsx("td", { onClick: (e) => e.stopPropagation(), className: "border-b border-[--color-border] px-2 py-2 align-middle", children: id && (_jsx("input", { type: "checkbox", checked: isSelected, onChange: () => toggle(id), className: "cursor-pointer accent-[--color-accent]" })) })), cols.map((c) => {
                                            let content = String(row[c] ?? "");
                                            if (c === "Status") {
                                                const s = displayStatus(row[c], row["ExpirationDate"]);
                                                content = (_jsx("span", { className: `badge ${STATUS_BADGE[s] ?? "badge-info"}`, children: s }));
                                            }
                                            return (_jsx("td", { className: `border-b border-[--color-border] px-2.5 py-2 align-middle ${DATE_COLS.has(c) ? "whitespace-nowrap" : ""}`, children: content }, c));
                                        })] }, i));
                            }) })] }) }), openId && (_jsx(ContractDrawer, { id: openId, onClose: () => setOpenId(null) }))] }));
}
function CitationList({ cites }) {
    return (_jsxs("aside", { className: "mt-2", children: [_jsx("h3", { className: "m-0 mb-2 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: "Citations" }), _jsx("ul", { className: "m-0 flex list-none flex-col gap-3 p-0", children: cites.map((c, i) => (_jsxs("li", { className: "flex flex-col gap-1", children: [_jsxs("div", { className: "text-sm", children: [_jsx("strong", { children: c.contract_title ?? c.contract_id }), c.page != null && (_jsxs("span", { className: "text-[--color-muted-fg]", children: [" \u2014 p.", c.page] }))] }), _jsx("blockquote", { className: "m-0 whitespace-pre-wrap rounded-md border-l-[3px] border-[--color-accent] px-3 py-2 text-sm leading-relaxed", style: { background: "var(--color-card-2)" }, children: c.quote })] }, i))) })] }));
}
