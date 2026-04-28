import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { getContract } from "../api";
const RISK_BADGE = {
    low: "badge-ok",
    medium: "badge-warn",
    high: "badge-danger",
};
// Inline-renderable in browsers vs. download-only. Mirrors the server-side
// _MIME_BY_EXT map in src/local/api_server.py — keep them in sync. The link
// label flips between "Open" and "Download" so users aren't surprised when
// clicking pulls a Word doc instead of opening one.
const _INLINE_EXTS = new Set(["pdf", "txt", "html", "htm"]);
function sourceLinkLabel(blobUri) {
    if (!blobUri)
        return "Open source ↗";
    const filename = blobUri.split("/").pop() ?? "";
    const ext = filename.split(".").pop()?.toLowerCase() ?? "";
    if (_INLINE_EXTS.has(ext))
        return `Open ${ext.toUpperCase()} ↗`;
    if (ext)
        return `Download ${ext.toUpperCase()} ↓`;
    return "Open source ↗";
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
export function ContractDrawer({ id, onClose, }) {
    const [detail, setDetail] = useState(null);
    const [tab, setTab] = useState("meta");
    const [err, setErr] = useState(null);
    useEffect(() => {
        setDetail(null);
        getContract(id)
            .then(setDetail)
            .catch((e) => setErr(e.message));
    }, [id]);
    return (_jsx("div", { className: "fixed inset-0 z-[100] flex justify-end backdrop-blur-sm", style: { background: "var(--color-overlay)" }, onClick: onClose, children: _jsxs("div", { className: "flex h-full w-[min(720px,100%)] flex-col gap-3 overflow-y-auto p-5 shadow-2xl animate-[slideIn_220ms_ease-out]", style: { background: "var(--color-card)" }, onClick: (e) => e.stopPropagation(), children: [_jsx("style", { children: `@keyframes slideIn { from { transform: translateX(24px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }` }), _jsxs("header", { className: "flex items-center justify-between gap-3 border-b border-[--color-border] pb-3", children: [_jsx("h2", { className: "m-0 truncate text-base font-semibold", children: detail?.ContractTitle ?? id }), _jsx(CloseButton, { onClick: onClose })] }), err && _jsxs(ErrorBox, { children: ["Error: ", err] }), !detail && !err && (_jsx("p", { className: "text-sm italic text-[--color-muted-fg]", children: "Loading\u2026" })), detail && (_jsxs(_Fragment, { children: [_jsx("nav", { className: "flex gap-1 border-b border-[--color-border]", children: ["meta", "clauses", "obligations", "audit"].map((t) => {
                                const active = tab === t;
                                return (_jsxs("button", { onClick: () => setTab(t), className: `relative cursor-pointer border-0 bg-transparent px-3 py-2 text-sm font-medium leading-none transition-colors duration-150 ${active
                                        ? "text-[--color-accent]"
                                        : "text-[--color-muted-fg] hover:text-[--color-fg]"}`, children: [t, t === "clauses" && ` (${detail.Clauses.length})`, t === "obligations" && ` (${detail.Obligations.length})`, t === "audit" && ` (${detail.Audit.length})`, _jsx("span", { "aria-hidden": "true", className: `absolute inset-x-2 -bottom-px h-[2px] rounded-full transition-transform duration-200 ${active ? "scale-x-100" : "scale-x-0"}`, style: { background: "var(--color-accent)" } })] }, t));
                            }) }), tab === "meta" && _jsx(MetaTab, { d: detail }), tab === "clauses" && _jsx(ClausesTab, { d: detail }), tab === "obligations" && _jsx(ObligationsTab, { d: detail }), tab === "audit" && _jsx(AuditTab, { d: detail })] }))] }) }));
}
function Cell({ children, nowrap, }) {
    return (_jsx("td", { className: `border-b border-[--color-border] px-2.5 py-2 align-middle ${nowrap ? "whitespace-nowrap" : ""}`, children: children }));
}
function Th({ children }) {
    return (_jsx("th", { className: "border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]", children: children }));
}
function MetaTab({ d }) {
    // Tuple: [display label, value, optional API field key for inheritance lookup].
    // When the API key is present and the value is null, we check d.Inherited
    // for a sibling-contract value to surface alongside the literal null.
    const fields = [
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
    return (_jsxs("dl", { className: "m-0 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2", children: [fields.map(([k, v, apiKey]) => {
                const inherited = apiKey ? d.Inherited?.[apiKey] : undefined;
                return (_jsxs("div", { className: "flex flex-col", children: [_jsx("dt", { className: "text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]", children: k }), _jsx("dd", { className: "m-0 break-words text-sm", children: v == null || v === "" ? (inherited ? (_jsxs(_Fragment, { children: [_jsx("span", { children: String(inherited.value) }), " ", _jsxs("span", { className: "text-xs italic text-[--color-muted-fg]", title: `Inherited from ${inherited.source_contract_title ?? "sibling contract"}`, children: ["(inherited from ", inherited.source_contract_title ?? "sibling contract", ")"] })] })) : (_jsx("span", { className: "text-[--color-muted-fg]", children: "\u2014" }))) : (String(v)) })] }, k));
            }), d.BlobUri && (_jsxs("div", { className: "flex flex-col sm:col-span-2", children: [_jsx("dt", { className: "text-[0.65rem] uppercase tracking-wider text-[--color-muted-fg]", children: "Source file" }), _jsxs("dd", { className: "m-0 text-sm", children: [d.FileUrl ? (_jsx("a", { href: d.FileUrl, target: "_blank", rel: "noopener noreferrer", className: "text-[--color-accent] underline underline-offset-2 hover:no-underline", children: sourceLinkLabel(d.BlobUri) })) : (_jsx("span", { className: "text-[--color-muted-fg] break-all", children: d.BlobUri })), _jsx("span", { className: "ml-3 text-[--color-muted-fg] break-all", children: d.BlobUri })] })] }))] }));
}
function ClausesTab({ d }) {
    if (d.Clauses.length === 0)
        return (_jsx("p", { className: "text-sm italic text-[--color-muted-fg]", children: "No clauses extracted." }));
    return (_jsx("div", { className: "flex flex-col gap-2", children: d.Clauses.map((c) => (_jsxs("details", { className: "group rounded-md border border-[--color-border] px-3 py-2 [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden", style: { background: "var(--color-card-2)" }, children: [_jsxs("summary", { className: "flex cursor-pointer items-center gap-2 text-sm select-none", children: [_jsx("svg", { className: "h-4 w-4 shrink-0 text-[--color-muted-fg] transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", children: _jsx("polyline", { points: "9 6 15 12 9 18" }) }), _jsx("strong", { className: "font-medium", children: c.ClauseType ?? "(unclassified)" }), c.PageNumber != null && (_jsxs("span", { className: "text-[--color-muted-fg]", children: ["\u00B7 p.", c.PageNumber] })), c.RiskLevel && (_jsx("span", { className: `badge ${RISK_BADGE[c.RiskLevel] ?? "badge-info"}`, children: c.RiskLevel }))] }), _jsx("p", { className: "mt-2 whitespace-pre-wrap text-sm leading-relaxed", children: c.ClauseText }), c.SectionHeading && (_jsxs("p", { className: "mt-1 text-xs text-[--color-muted-fg]", children: ["Section: ", c.SectionHeading] }))] }, c.ClauseId))) }));
}
function ObligationsTab({ d }) {
    if (d.Obligations.length === 0)
        return (_jsx("p", { className: "text-sm italic text-[--color-muted-fg]", children: "No obligations extracted." }));
    return (_jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "w-full border-collapse text-sm", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx(Th, { children: "Party" }), _jsx(Th, { children: "Text" }), _jsx(Th, { children: "Due" }), _jsx(Th, { children: "Frequency" }), _jsx(Th, { children: "Risk" })] }) }), _jsx("tbody", { children: d.Obligations.map((o) => (_jsxs("tr", { children: [_jsx(Cell, { children: o.Party ?? "—" }), _jsx(Cell, { children: o.ObligationText }), _jsx(Cell, { nowrap: true, children: o.DueDate?.slice(0, 10) ?? "—" }), _jsx(Cell, { children: o.Frequency ?? "—" }), _jsx(Cell, { children: o.RiskLevel ? (_jsx("span", { className: `badge ${RISK_BADGE[o.RiskLevel] ?? "badge-info"}`, children: o.RiskLevel })) : ("—") })] }, o.ObligationId))) })] }) }));
}
function AuditTab({ d }) {
    if (d.Audit.length === 0)
        return (_jsx("p", { className: "text-sm italic text-[--color-muted-fg]", children: "No audit history." }));
    return (_jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "w-full border-collapse text-sm", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx(Th, { children: "Field" }), _jsx(Th, { children: "Value" }), _jsx(Th, { children: "Method" }), _jsx(Th, { children: "Model" }), _jsx(Th, { children: "Confidence" }), _jsx(Th, { children: "When" })] }) }), _jsx("tbody", { children: d.Audit.map((a) => (_jsxs("tr", { children: [_jsx(Cell, { children: a.FieldName }), _jsx(Cell, { children: a.FieldValue ?? "—" }), _jsx(Cell, { children: a.ExtractionMethod ?? "—" }), _jsx(Cell, { children: a.ModelName ?? "—" }), _jsx(Cell, { children: a.Confidence ?? "—" }), _jsx(Cell, { nowrap: true, children: a.CreatedAt?.slice(0, 19).replace("T", " ") })] }, a.AuditId))) })] }) }));
}
