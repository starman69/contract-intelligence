import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { listContracts } from "../api";
import { CompareSelectedButton } from "../components/CompareModal";
import { ContractDrawer } from "../components/ContractDrawer";
import { STATUS_BADGE, displayStatus } from "../statusBadge";
const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 250;
function ErrorBox({ children }) {
    return (_jsx("div", { className: "rounded-lg px-3 py-2 text-sm", style: {
            background: "var(--color-danger-bg)",
            color: "var(--color-danger-fg)",
        }, children: children }));
}
export default function Contracts() {
    const [rows, setRows] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [openId, setOpenId] = useState(null);
    const [selected, setSelected] = useState(new Set());
    const [searchInput, setSearchInput] = useState("");
    const [q, setQ] = useState("");
    const [sort, setSort] = useState({
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
    const reqRef = useRef(null);
    useEffect(() => {
        reqRef.current?.abort();
        const ac = new AbortController();
        reqRef.current = ac;
        setLoading(true);
        listContracts({ q, sort: sort.key, dir: sort.dir, limit: PAGE_SIZE, offset }, ac.signal)
            .then((resp) => {
            setRows(resp.rows);
            setTotal(resp.total);
            setError(null);
        })
            .catch((e) => {
            if (e.name === "AbortError")
                return;
            setError(e.message);
        })
            .finally(() => {
            if (!ac.signal.aborted)
                setLoading(false);
        });
        return () => ac.abort();
    }, [q, sort, offset]);
    function toggle(id) {
        setSelected((s) => {
            const next = new Set(s);
            if (next.has(id))
                next.delete(id);
            else
                next.add(id);
            return next;
        });
    }
    function setSortKey(k) {
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
    return (_jsxs("div", { className: "flex flex-col gap-3", children: [_jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsx("input", { type: "search", placeholder: "search title / counterparty / type\u2026", value: searchInput, onChange: (e) => setSearchInput(e.target.value), className: "field flex-1 min-w-[16rem]" }), selected.size > 0 && (_jsx(CompareSelectedButton, { ids: Array.from(selected) })), _jsx("span", { className: "text-sm text-[--color-muted-fg]", children: total === 0
                            ? loading
                                ? "loading…"
                                : "no contracts match"
                            : `${firstIndex}–${lastIndex} of ${total}` }), _jsxs("span", { className: "ml-auto inline-flex gap-1", children: [_jsx("button", { type: "button", disabled: !hasPrev || loading, onClick: () => setOffset(Math.max(0, offset - PAGE_SIZE)), className: "btn btn-ghost px-3 py-1.5 text-sm", children: "\u2190 Prev" }), _jsx("button", { type: "button", disabled: !hasNext || loading, onClick: () => setOffset(offset + PAGE_SIZE), className: "btn btn-ghost px-3 py-1.5 text-sm", children: "Next \u2192" })] })] }), error && _jsxs(ErrorBox, { children: ["Error: ", error] }), _jsx("div", { className: "surface-card overflow-x-auto p-0 transition-opacity duration-150 aria-busy:opacity-60", "aria-busy": loading, children: _jsxs("table", { className: "w-full border-collapse text-sm", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { className: "border-b border-[--color-border] px-2 py-2" }), _jsx(SortHeader, { k: "ContractTitle", sort: sort, onClick: setSortKey, children: "Title" }), _jsx(SortHeader, { k: "Counterparty", sort: sort, onClick: setSortKey, children: "Counterparty" }), _jsx(SortHeader, { k: "ContractType", sort: sort, onClick: setSortKey, children: "Type" }), _jsx(SortHeader, { k: "EffectiveDate", sort: sort, onClick: setSortKey, children: "Effective" }), _jsx(SortHeader, { k: "ExpirationDate", sort: sort, onClick: setSortKey, children: "Expires" }), _jsx(SortHeader, { k: "GoverningLaw", sort: sort, onClick: setSortKey, children: "Governing Law" }), _jsx(SortHeader, { k: "Status", sort: sort, onClick: setSortKey, children: "Status" })] }) }), _jsx("tbody", { children: rows.map((c) => {
                                const isOpen = openId === c.ContractId;
                                return (_jsxs("tr", { onClick: () => setOpenId(c.ContractId), className: `cursor-pointer transition-colors duration-100 ${isOpen
                                        ? "bg-[--color-accent-soft]"
                                        : "hover:bg-[--color-accent-soft]/50"}`, children: [_jsx("td", { onClick: (e) => e.stopPropagation(), className: "border-b border-[--color-border] px-2 py-2 align-middle", children: _jsx("input", { type: "checkbox", checked: selected.has(c.ContractId), onChange: () => toggle(c.ContractId), className: "cursor-pointer accent-[--color-accent]" }) }), _jsx(Cell, { children: c.ContractTitle ?? "—" }), _jsx(Cell, { children: c.Counterparty ?? "—" }), _jsx(Cell, { children: c.ContractType ?? "—" }), _jsx(Cell, { nowrap: true, children: c.EffectiveDate?.slice(0, 10) ?? "—" }), _jsx(Cell, { nowrap: true, children: c.ExpirationDate?.slice(0, 10) ?? "—" }), _jsx(Cell, { children: c.GoverningLaw ?? "—" }), _jsx(Cell, { children: (() => {
                                                const s = displayStatus(c.Status, c.ExpirationDate);
                                                return (_jsx("span", { className: `badge ${STATUS_BADGE[s] ?? "badge-info"}`, children: s }));
                                            })() })] }, c.ContractId));
                            }) })] }) }), openId && (_jsx(ContractDrawer, { id: openId, onClose: () => setOpenId(null) }))] }));
}
function Cell({ children, nowrap, }) {
    return (_jsx("td", { className: `border-b border-[--color-border] px-2.5 py-2 align-middle ${nowrap ? "whitespace-nowrap" : ""}`, children: children }));
}
function SortHeader({ k, sort, onClick, children, }) {
    const active = sort.key === k;
    const arrow = active ? (sort.dir === "asc" ? "▲" : "▼") : "";
    return (_jsxs("th", { onClick: () => onClick(k), className: `cursor-pointer select-none whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider transition-colors duration-100 hover:text-[--color-accent] ${active ? "text-[--color-accent]" : "text-[--color-muted-fg]"}`, children: [children, arrow && _jsx("span", { className: "ml-1 text-[0.7em]", children: arrow })] }));
}
