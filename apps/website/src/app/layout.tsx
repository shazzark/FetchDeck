import type { Metadata } from "next";
import "./globals.css";
const publicSiteUrl = process.env.NEXT_PUBLIC_SITE_URL;
export const metadata: Metadata = {
  ...(publicSiteUrl ? { metadataBase: new URL(publicSiteUrl), alternates: { canonical: "/" } } : {}),
  title: { default: "FetchDeck — Downloads, under control", template: "%s | FetchDeck" },
  description: "Queue, monitor, and resume large downloads with FetchDeck, a Windows-first download manager powered by aria2.",
  openGraph: {
    title: "FetchDeck — Downloads, under control",
    description: "A focused Windows download manager for large files.",
    ...(publicSiteUrl ? { images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "FetchDeck downloads, under control" }] } : {}),
  },
  twitter: {
    card: "summary_large_image",
    title: "FetchDeck — Downloads, under control",
    description: "A focused Windows download manager for large files.",
    ...(publicSiteUrl ? { images: ["/og-image.png"] } : {}),
  },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
