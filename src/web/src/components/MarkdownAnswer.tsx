import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Themed markdown renderer for chat answers. Plain text passes through
// unchanged, so reporting handlers ("3 contracts found.") still render fine.
//
// Custom component overrides apply Tailwind utilities + CSS-variable colours
// so the rendered output matches the rest of the app in both light and dark.
export function MarkdownAnswer({
  text,
  italic = false,
}: {
  text: string;
  italic?: boolean;
}) {
  return (
    <div
      className={`markdown-body flex flex-col gap-2 leading-relaxed ${
        italic ? "italic" : ""
      }`}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h3 className="m-0 mt-1 text-base font-semibold" {...p} />,
          h2: (p) => <h4 className="m-0 mt-1 text-sm font-semibold" {...p} />,
          h3: (p) => (
            <h4
              className="m-0 mt-1 text-xs font-semibold uppercase tracking-wider text-[--color-muted-fg]"
              {...p}
            />
          ),
          h4: (p) => (
            <h5
              className="m-0 mt-1 text-xs font-semibold text-[--color-muted-fg]"
              {...p}
            />
          ),
          p: (p) => <p className="m-0" {...p} />,
          strong: (p) => <strong className="font-semibold" {...p} />,
          em: (p) => <em className="italic" {...p} />,
          a: (p) => (
            <a
              className="underline underline-offset-2 hover:text-[--color-accent]"
              target="_blank"
              rel="noreferrer"
              {...p}
            />
          ),
          ul: (p) => (
            <ul className="m-0 ml-5 flex list-disc flex-col gap-1" {...p} />
          ),
          ol: (p) => (
            <ol className="m-0 ml-5 flex list-decimal flex-col gap-1" {...p} />
          ),
          li: (p) => <li className="" {...p} />,
          blockquote: (p) => (
            <blockquote
              className="m-0 border-l-[3px] border-[--color-border-strong] pl-3 text-sm text-[--color-muted-fg]"
              {...p}
            />
          ),
          code: (props) => {
            const { className, children, ...rest } = props as {
              className?: string;
              children?: React.ReactNode;
            };
            const isBlock = /language-/.test(className ?? "");
            if (isBlock) {
              return (
                <code className={className} {...rest}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="rounded px-1 py-0.5 text-[0.85em]"
                style={{
                  background: "var(--color-card-2)",
                  fontFamily: "var(--font-mono)",
                }}
                {...rest}
              >
                {children}
              </code>
            );
          },
          pre: (p) => (
            <pre
              className="m-0 overflow-x-auto whitespace-pre-wrap rounded-md px-3 py-2 text-[0.85rem] leading-snug"
              style={{
                background: "var(--color-card-2)",
                borderLeft: "3px solid var(--color-border-strong)",
                fontFamily: "var(--font-mono)",
              }}
              {...p}
            />
          ),
          hr: () => <hr className="my-2 border-[--color-border]" />,
          table: (p) => (
            <div className="-mx-1 overflow-x-auto">
              <table
                className="w-full border-collapse text-sm"
                {...p}
              />
            </div>
          ),
          thead: (p) => <thead {...p} />,
          th: (p) => (
            <th
              className="whitespace-nowrap border-b border-[--color-border] px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider text-[--color-muted-fg]"
              {...p}
            />
          ),
          td: (p) => (
            <td
              className="border-b border-[--color-border] px-2.5 py-2 align-top"
              {...p}
            />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
