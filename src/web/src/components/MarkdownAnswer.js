import { jsx as _jsx } from "react/jsx-runtime";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
// Themed markdown renderer for chat answers. Plain text passes through
// unchanged, so reporting handlers ("3 contracts found.") still render fine.
//
// Custom component overrides apply Tailwind utilities + CSS-variable colours
// so the rendered output matches the rest of the app in both light and dark.
export function MarkdownAnswer({ text, italic = false, }) {
    return (_jsx("div", { className: `markdown-body flex flex-col gap-2 leading-relaxed ${italic ? "italic" : ""}`, children: _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], components: {
                h1: (p) => _jsx("h3", { className: "m-0 mt-1 text-base font-semibold", ...p }),
                h2: (p) => _jsx("h4", { className: "m-0 mt-1 text-sm font-semibold", ...p }),
                h3: (p) => (_jsx("h4", { className: "m-0 mt-1 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]", ...p })),
                h4: (p) => (_jsx("h5", { className: "m-0 mt-1 text-xs font-semibold text-[--color-muted-fg]", ...p })),
                p: (p) => _jsx("p", { className: "m-0", ...p }),
                strong: (p) => _jsx("strong", { className: "font-semibold", ...p }),
                em: (p) => _jsx("em", { className: "italic", ...p }),
                a: (p) => (_jsx("a", { className: "underline underline-offset-2 hover:text-[--color-accent]", target: "_blank", rel: "noreferrer", ...p })),
                ul: (p) => (_jsx("ul", { className: "m-0 ml-5 flex list-disc flex-col gap-1", ...p })),
                ol: (p) => (_jsx("ol", { className: "m-0 ml-5 flex list-decimal flex-col gap-1", ...p })),
                li: (p) => _jsx("li", { className: "", ...p }),
                blockquote: (p) => (_jsx("blockquote", { className: "m-0 border-l-[3px] border-[--color-border-strong] pl-3 text-sm text-[--color-muted-fg]", ...p })),
                code: (props) => {
                    const { className, children, ...rest } = props;
                    const isBlock = /language-/.test(className ?? "");
                    if (isBlock) {
                        return (_jsx("code", { className: className, ...rest, children: children }));
                    }
                    return (_jsx("code", { className: "rounded px-1 py-0.5 text-[0.85em]", style: {
                            background: "var(--color-card-2)",
                            fontFamily: "var(--font-mono)",
                        }, ...rest, children: children }));
                },
                pre: (p) => (_jsx("pre", { className: "m-0 overflow-x-auto whitespace-pre-wrap rounded-md px-3 py-2 text-[0.85rem] leading-snug", style: {
                        background: "var(--color-card-2)",
                        borderLeft: "3px solid var(--color-border-strong)",
                        fontFamily: "var(--font-mono)",
                    }, ...p })),
                hr: () => _jsx("hr", { className: "my-2 border-[--color-border]" }),
                table: (p) => (_jsx("div", { className: "-mx-1 overflow-x-auto", children: _jsx("table", { className: "w-full border-collapse text-sm", ...p }) })),
                thead: (p) => _jsx("thead", { ...p }),
                th: (p) => (_jsx("th", { className: "whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]", ...p })),
                td: (p) => (_jsx("td", { className: "border-b border-[--color-border] px-2.5 py-2 align-top", ...p })),
            }, children: text }) }));
}
