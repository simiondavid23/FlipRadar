import "./globals.css";

export const metadata = {
  title: "FlipRadar - Product Research Tool",
  description: "Aplicatie pentru automatizarea research-ului de produse profitabile in comertul online",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ro">
      <body style={{ WebkitFontSmoothing: "antialiased", MozOsxFontSmoothing: "grayscale" }}>
        {children}
      </body>
    </html>
  );
}
