import type { ReactNode } from "react";

export function BrandMark({ className = "" }: { className?: string }) {
  return <svg aria-hidden="true" className={className} viewBox="0 0 40 40" fill="none"><rect x="2" y="2" width="36" height="36" rx="12" fill="#C6F36A"/><path d="M11 13h18v4H16v4h11v4H16v7h-5V13Z" fill="#101F2B"/><path d="M24 27h6l-3 5-3-5Z" fill="#101F2B"/></svg>;
}

export function Wordmark({ children }: { children?: ReactNode }) {
  return <span className="fd-wordmark"><BrandMark className="fd-mark"/><span>FetchDeck</span>{children}</span>;
}
