import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { listGoldClauses } from "../api";
import { MarkdownAnswer } from "../components/MarkdownAnswer";
export default function GoldClauses() {
    const [gold, setGold] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null);
    const [open, setOpen] = useState(null);
    useEffect(() => {
        listGoldClauses()
            .then(setGold)
            .catch((e) => setErr(e.message))
            .finally(() => setLoading(false));
    }, []);
    if (loading)
        return _jsx("p", { className: "text-[--color-muted-fg] italic", children: "Loading\u2026" });
    if (err)
        return (_jsxs("div", { className: "rounded-lg px-3 py-2 text-sm", style: {
                background: "var(--color-danger-bg)",
                color: "var(--color-danger-fg)",
            }, children: ["Error: ", err] }));
    if (gold.length === 0)
        return (_jsx("p", { className: "text-[--color-muted-fg] italic", children: "No gold clauses seeded yet." }));
    // Latest version per type already comes first from the server.
    const seen = new Set();
    const latest = gold.filter((g) => {
        if (seen.has(g.ClauseType))
            return false;
        seen.add(g.ClauseType);
        return true;
    });
    return (_jsxs("div", { className: "flex flex-col gap-3", children: [_jsxs("p", { className: "text-sm text-[--color-muted-fg]", children: [latest.length, " approved clause types \u00B7 click to view the full text. Multi-contract comparison lives on the Contracts tab."] }), _jsx("div", { className: "grid gap-4 grid-cols-1 md:grid-cols-2", children: latest.map((g) => {
                    const expanded = open === g.StandardClauseId;
                    return (_jsxs("article", { className: `surface-card flex flex-col gap-3 p-4 transition-[grid-column] duration-200 ${expanded ? "md:col-span-2" : ""}`, children: [_jsxs("header", { className: "flex items-baseline justify-between gap-2", children: [_jsx("h3", { className: "m-0 text-base font-semibold capitalize", children: g.ClauseType }), _jsxs("span", { className: "text-xs text-[--color-muted-fg]", children: ["v", g.Version] })] }), _jsxs("dl", { className: "m-0 flex flex-wrap gap-x-6 gap-y-2 text-xs", children: [_jsxs("span", { className: "flex flex-col", children: [_jsx("dt", { className: "text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]", children: "jurisdiction" }), _jsx("dd", { className: "m-0", children: g.Jurisdiction ?? "—" })] }), _jsxs("span", { className: "flex flex-col", children: [_jsx("dt", { className: "text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]", children: "effective" }), _jsx("dd", { className: "m-0", children: g.EffectiveFrom?.slice(0, 10) })] }), _jsxs("span", { className: "flex flex-col", children: [_jsx("dt", { className: "text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]", children: "owner" }), _jsx("dd", { className: "m-0", children: g.ReviewOwner ?? "—" })] })] }), _jsx("button", { type: "button", onClick: () => setOpen(open === g.StandardClauseId ? null : g.StandardClauseId), className: "btn btn-ghost self-start", children: open === g.StandardClauseId ? "Hide text" : "Show text" }), open === g.StandardClauseId && (
                            // Gold clauses are loaded straight from samples/gold-clauses/*.md
                            // (markdown source preserved into dbo.StandardClause.ApprovedText),
                            // so render through MarkdownAnswer to honour headings, lists, **bold**.
                            // Same component as the chat answer + CompareModal gold panel.
                            _jsx("div", { className: "max-h-96 overflow-y-auto rounded-md px-3 py-2 text-sm", style: {
                                    background: "var(--color-card-2)",
                                    borderLeft: "3px solid var(--color-border-strong)",
                                }, children: _jsx(MarkdownAnswer, { text: g.ApprovedText }) })), g.RiskPolicy && (_jsxs("p", { className: "m-0 text-xs text-[--color-muted-fg]", children: [_jsx("strong", { className: "text-[--color-fg]", children: "Policy:" }), " ", g.RiskPolicy] }))] }, g.StandardClauseId));
                }) })] }));
}
