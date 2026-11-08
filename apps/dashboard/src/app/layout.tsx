import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "FetchDeck Dashboard", description: "Local FetchDeck transfer statistics" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
