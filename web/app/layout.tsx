import type { Metadata, Viewport } from "next";
import "./globals.css";
import Motion from "@/components/Motion";

export const metadata: Metadata = {
  title: "NexTrade: research assistant for Indian stocks",
  description: "Source-linked facts, stated gaps, peer scores and plain-English explanations for NSE and BSE companies. Education only, not financial advice.",
};
export const viewport: Viewport = { themeColor: "#0b1a14" };

const FONTS = "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,300..700,0..100,0..1;1,9..144,300..700,0..100,0..1&family=Geist:wght@300..700&family=Geist+Mono:wght@400..600&display=swap";
// Sets the motion class before first paint so reveals never flash; absent under reduced motion.
const BOOT = `try{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("motion")}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href={FONTS} rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body suppressHydrationWarning>{children}<Motion /></body>
    </html>
  );
}
