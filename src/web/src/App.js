import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import Chat from "./tabs/Chat";
import Contracts from "./tabs/Contracts";
import GoldClauses from "./tabs/GoldClauses";
import { Logo } from "./components/Logo";
import { ThemeToggle } from "./components/ThemeToggle";
import { useTheme } from "./theme";
const TAB_STORAGE_KEY = "contracts.activeTab";
function loadTab() {
    try {
        const t = localStorage.getItem(TAB_STORAGE_KEY);
        if (t === "chat" || t === "contracts" || t === "gold")
            return t;
    }
    catch {
        /* localStorage unavailable */
    }
    return "chat";
}
const TABS = [
    ["chat", "Chat"],
    ["contracts", "Contracts"],
    ["gold", "Gold Clauses"],
];
export default function App() {
    const [tab, setTab] = useState(loadTab);
    const [theme, , toggleTheme] = useTheme();
    useEffect(() => {
        try {
            localStorage.setItem(TAB_STORAGE_KEY, tab);
        }
        catch {
            /* ignore */
        }
    }, [tab]);
    return (_jsxs("main", { className: "mx-auto w-full max-w-[1100px] px-4 py-8", children: [_jsxs("header", { className: "flex flex-col gap-3", children: [_jsxs("div", { className: "flex items-center justify-between gap-4", children: [_jsxs("div", { className: "flex items-center gap-2.5", children: [_jsx(Logo, { className: "h-7 w-7 text-[--color-fg]" }), _jsx("h1", { className: "text-2xl font-semibold tracking-tight", children: "Contract Intelligence" })] }), _jsx(ThemeToggle, { theme: theme, onToggle: toggleTheme })] }), _jsx("nav", { className: "flex gap-1 border-b border-[--color-border]", role: "tablist", children: TABS.map(([id, label]) => {
                            const active = tab === id;
                            return (_jsxs("button", { role: "tab", "aria-selected": active, onClick: () => setTab(id), className: `relative cursor-pointer border-0 bg-transparent px-4 py-2.5 text-sm font-medium leading-none transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 rounded-t-md ${active
                                    ? "text-[--color-accent]"
                                    : "text-[--color-muted-fg] hover:text-[--color-fg]"}`, style: {
                                    // ring colours via CSS vars — Tailwind arbitrary ring colours
                                    // resolve at compile time, but CSS-var rings need this fallback.
                                    ["--tw-ring-color"]: "var(--color-ring)",
                                    ["--tw-ring-offset-color"]: "var(--color-bg)",
                                }, children: [label, _jsx("span", { "aria-hidden": "true", className: `absolute inset-x-2 -bottom-px h-[2px] rounded-full transition-transform duration-200 ${active ? "scale-x-100" : "scale-x-0"}`, style: { background: "var(--color-accent)" } })] }, id));
                        }) })] }), _jsxs("div", { className: "mt-6", children: [tab === "chat" && _jsx(Chat, {}), tab === "contracts" && _jsx(Contracts, {}), tab === "gold" && _jsx(GoldClauses, {})] })] }));
}
