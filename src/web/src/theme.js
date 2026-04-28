import { useEffect, useState } from "react";
export const THEME_STORAGE_KEY = "contracts.theme";
export function loadTheme() {
    try {
        const t = localStorage.getItem(THEME_STORAGE_KEY);
        if (t === "light" || t === "dark")
            return t;
    }
    catch {
        /* localStorage unavailable */
    }
    return "dark";
}
export function applyTheme(t) {
    const root = document.documentElement;
    if (t === "dark")
        root.classList.add("dark");
    else
        root.classList.remove("dark");
}
export function useTheme() {
    const [theme, setThemeState] = useState(loadTheme);
    useEffect(() => {
        applyTheme(theme);
        try {
            localStorage.setItem(THEME_STORAGE_KEY, theme);
        }
        catch {
            /* ignore */
        }
    }, [theme]);
    const setTheme = (t) => setThemeState(t);
    const toggle = () => setThemeState((t) => (t === "dark" ? "light" : "dark"));
    return [theme, setTheme, toggle];
}
