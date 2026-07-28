import { Space_Grotesk, Space_Mono } from "next/font/google";
import "./globals.css";

// Fonturile design system-ului "Prism Obsidian". next/font le self-hosteaza la
// build, deci aplicatia impachetata functioneaza si fara internet.
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin", "latin-ext"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const spaceMono = Space_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});

export const metadata = {
  title: "FlipRadar - Product Research Tool",
  description: "Aplicatie pentru automatizarea research-ului de produse profitabile in comertul online",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ro" className={`${spaceGrotesk.variable} ${spaceMono.variable}`} suppressHydrationWarning>
      <body style={{ WebkitFontSmoothing: "antialiased", MozOsxFontSmoothing: "grayscale" }}>
        {children}
      </body>
    </html>
  );
}
