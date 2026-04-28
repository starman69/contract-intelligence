import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { compare, listGoldClauses } from "../api";
import { MarkdownAnswer } from "./MarkdownAnswer";
// Compact thousands formatter mirroring Chat's helper.
function compact(n) {
    if (n < 1000)
        return String(n);
    return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
}
function ErrorBox({ children }) {
    return (_jsx("div", { className: "rounded-lg px-3 py-2 text-sm", style: {
            background: "var(--color-danger-bg)",
            color: "var(--color-danger-fg)",
        }, children: children }));
}
function CloseButton({ onClick }) {
    return (_jsx("button", { type: "button", onClick: onClick, "aria-label": "Close", className: "btn btn-ghost btn-icon text-lg", children: "\u00D7" }));
}
export function CompareSelectedButton({ ids, label, }) {
    const [open, setOpen] = useState(false);
    return (_jsxs(_Fragment, { children: [_jsx("button", { type: "button", onClick: () => setOpen(true), className: "btn btn-primary", children: label ?? `Compare ${ids.length} to gold…` }), open && _jsx(CompareModal, { ids: ids, onClose: () => setOpen(false) })] }));
}
export function CompareModal({ ids, onClose, }) {
    const [gold, setGold] = useState([]);
    const [pickedTypes, setPickedTypes] = useState(new Set());
    const [results, setResults] = useState({});
    const [running, setRunning] = useState(false);
    const [err, setErr] = useState(null);
    useEffect(() => {
        listGoldClauses().then(setGold).catch((e) => setErr(e.message));
    }, []);
    const uniqueTypes = Array.from(new Set(gold.map((g) => g.ClauseType)));
    function toggle(t) {
        setPickedTypes((p) => {
            const n = new Set(p);
            if (n.has(t))
                n.delete(t);
            else
                n.add(t);
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
            const all = {};
            for (const id of ids) {
                all[id] = await compare(id, types);
                setResults({ ...all });
            }
        }
        catch (e) {
            setErr(e.message);
        }
        finally {
            setRunning(false);
        }
    }
    return (_jsx("div", { className: "fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto p-8 backdrop-blur-sm", style: { background: "var(--color-overlay)" }, onClick: onClose, children: _jsxs("div", { className: "surface-card flex w-full max-w-[900px] flex-col gap-3 p-5 shadow-xl", onClick: (e) => e.stopPropagation(), children: [_jsxs("header", { className: "flex items-center justify-between gap-3 border-b border-[--color-border] pb-3", children: [_jsxs("h2", { className: "m-0 text-base font-semibold", children: ["Compare ", ids.length, " contract(s) to gold clauses"] }), _jsx(CloseButton, { onClick: onClose })] }), _jsxs("div", { className: "flex items-center justify-between gap-3", children: [_jsx("p", { className: "m-0 text-sm text-[--color-muted-fg]", children: "Pick which clause types to compare:" }), uniqueTypes.length > 0 && (_jsx("button", { type: "button", onClick: toggleAll, className: "btn btn-ghost px-3 py-1.5 text-xs", children: allPicked ? "Unselect all" : `Select all (${uniqueTypes.length})` }))] }), _jsx("div", { className: "grid gap-2 grid-cols-1 sm:grid-cols-2", children: uniqueTypes.map((t) => (_jsxs("label", { className: "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-[--color-accent-soft]", children: [_jsx("input", { type: "checkbox", checked: pickedTypes.has(t), onChange: () => toggle(t), className: "cursor-pointer accent-[--color-accent]" }), t] }, t))) }), _jsx("div", { className: "flex flex-wrap gap-2", children: _jsx("button", { type: "button", onClick: run, disabled: running || pickedTypes.size === 0, className: "btn btn-primary", children: running ? "Comparing…" : `Compare to ${pickedTypes.size} clause(s)` }) }), err && _jsxs(ErrorBox, { children: ["Error: ", err] }), Object.entries(results).map(([id, r]) => (_jsx(ComparisonResultBlock, { contractId: id, resp: r }, id)))] }) }));
}
function ComparisonResultBlock({ contractId, resp, }) {
    const title = resp.contract_title || contractId;
    const usage = resp.token_usage;
    return (_jsxs("section", { className: "mt-2 border-t border-[--color-border] pt-3", children: [_jsxs("header", { className: "mb-2 flex flex-col gap-1", children: [_jsx("h3", { className: "m-0 text-sm font-semibold", children: title }), _jsxs("div", { className: "flex flex-wrap items-center gap-2 text-xs text-[--color-muted-fg]", children: [_jsx("span", { className: "font-mono text-[0.7rem]", title: "Contract ID (dbo.Contract.ContractId)", children: contractId }), typeof resp.elapsed_ms === "number" && (_jsxs("span", { children: ["\u00B7 ", resp.elapsed_ms, " ms"] })), usage && (usage.prompt_tokens > 0 || usage.completion_tokens > 0) && (_jsxs("span", { title: `${usage.prompt_tokens} prompt / ${usage.completion_tokens} completion tokens`, children: ["\u00B7 llm (", compact(usage.prompt_tokens), "/", compact(usage.completion_tokens), ")"] })), usage && usage.estimated_cost_usd > 0 && (_jsxs("span", { title: "Estimated USD cost based on per-model list price", children: ["\u00B7 $", usage.estimated_cost_usd.toFixed(4)] })), usage && usage.calls && usage.calls.length > 0 && (_jsxs("span", { title: "LLM model used for the diff", children: ["\u00B7 ", usage.calls[0].model] }))] })] }), _jsx("div", { className: "flex flex-col gap-2", children: resp.comparisons.map((c) => (_jsxs("details", { className: "surface-card group px-3 py-2 [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden", style: { background: "var(--color-card-2)" }, children: [_jsxs("summary", { className: "flex cursor-pointer items-center gap-2 text-sm select-none", children: [_jsx("svg", { className: "h-4 w-4 shrink-0 text-[--color-muted-fg] transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", children: _jsx("polyline", { points: "9 6 15 12 9 18" }) }), _jsx("span", { className: "font-medium", children: c.clause_type }), c.available ? (_jsx("span", { className: "badge badge-ok", children: "compared" })) : c.applicable === false ? (_jsx("span", { className: "badge badge-info", children: c.reason ?? "not applicable" })) : (_jsx("span", { className: "badge badge-warn", children: c.reason }))] }), c.available && (_jsxs("div", { className: "mt-2 flex flex-col gap-2", children: [_jsx("h4", { className: "m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: "Difference" }), _jsx("div", { className: "rounded-md px-3 py-2 text-sm", style: {
                                        background: "var(--color-card)",
                                        borderLeft: "3px solid var(--color-accent)",
                                    }, children: _jsx(MarkdownAnswer, { text: c.diff ?? "" }) }), _jsxs("h4", { className: "m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: ["Contract clause (page ", c.contract_page ?? "?", ")"] }), _jsx("blockquote", { className: "m-0 border-l-[3px] border-[--color-border-strong] pl-3 text-sm text-[--color-muted-fg]", children: c.contract_clause_text }), _jsxs("h4", { className: "m-0 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]", children: ["Gold ", c.gold_clause_id, " (v", c.gold_version, ")"] }), _jsx("div", { className: "rounded-md border-l-[3px] border-[--color-border-strong] bg-[--color-card] px-3 py-2 text-sm", children: _jsx(MarkdownAnswer, { text: c.gold_text ?? "" }) })] }))] }, c.clause_type))) })] }));
}
