// Inline SVG logo: a document with an AI sparkle. currentColor on the
// outline + accent var on the spark so the icon themes automatically with
// light/dark mode. Self-contained — no icon library dependency.
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* Document with a folded top-right corner */}
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      {/* AI sparkle (4-point star) inside the document, in the accent colour */}
      <path
        d="M11.6 11.4 L12.5 13.3 L14.4 14.2 L12.5 15.1 L11.6 17 L10.7 15.1 L8.8 14.2 L10.7 13.3 Z"
        fill="var(--color-accent)"
        stroke="var(--color-accent)"
        strokeWidth="0.5"
      />
      {/* Small companion sparkle */}
      <circle cx="16" cy="12" r="0.85" fill="var(--color-accent)" stroke="none" />
    </svg>
  );
}
