import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NexTrade: research assistant for Indian stocks",
  description: "Source-linked facts, stated gaps, peer scores and plain-English explanations for NSE and BSE companies. Education only, not financial advice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@600&family=Red+Hat+Text:wght@400;500&family=Red+Hat+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}
