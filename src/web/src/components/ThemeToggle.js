import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function ThemeToggle({ theme, onToggle, }) {
    const isDark = theme === "dark";
    return (_jsxs("button", { type: "button", onClick: onToggle, "aria-label": `Switch to ${isDark ? "light" : "dark"} mode`, "aria-pressed": isDark, title: `Switch to ${isDark ? "light" : "dark"} mode`, className: "btn btn-ghost btn-icon group relative overflow-hidden", children: [_jsx(SunIcon, { className: `absolute h-5 w-5 transition-all duration-300 ease-out motion-reduce:transition-none ${isDark
                    ? "rotate-90 scale-0 opacity-0"
                    : "rotate-0 scale-100 opacity-100"}` }), _jsx(MoonIcon, { className: `absolute h-5 w-5 transition-all duration-300 ease-out motion-reduce:transition-none ${isDark
                    ? "rotate-0 scale-100 opacity-100"
                    : "-rotate-90 scale-0 opacity-0"}` })] }));
}
function SunIcon({ className }) {
    return (_jsxs("svg", { className: className, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.75", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", children: [_jsx("circle", { cx: "12", cy: "12", r: "4" }), _jsx("path", { d: "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" })] }));
}
function MoonIcon({ className }) {
    return (_jsx("svg", { className: className, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.75", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", children: _jsx("path", { d: "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" }) }));
}
