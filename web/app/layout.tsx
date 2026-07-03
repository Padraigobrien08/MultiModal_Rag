import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted so the production build never reaches out to Google Fonts,
// which hangs in network-restricted build environments. These are the latin
// variable woff2 files for Space Grotesk / JetBrains Mono.
const spaceGrotesk = localFont({
  src: "./fonts/SpaceGrotesk-latin.woff2",
  variable: "--font-sans",
  weight: "300 700",
  display: "swap",
});

const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMono-latin.woff2",
  variable: "--font-mono",
  weight: "300 600",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Stepwise",
  description: "Turn tutorial videos and screenshots into structured, queryable knowledge",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full`}>
      <body className="h-full bg-background text-foreground font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
