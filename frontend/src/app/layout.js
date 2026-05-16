import "./globals.css";
import { ThemeProvider } from "@/lib/theme";

export const metadata = {
  title: "FlipRadar - Product Research Tool",
  description: "Aplicatie pentru automatizarea research-ului de produse profitabile in comertul online",
};

const themeInitScript = `(function(){try{var t=localStorage.getItem('flipradar-theme');if(t!=='light'&&t!=='dark'){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({ children }) {
  return (
    <html lang="ro" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body style={{ WebkitFontSmoothing: "antialiased", MozOsxFontSmoothing: "grayscale" }}>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
