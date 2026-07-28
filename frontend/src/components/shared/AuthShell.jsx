"use client";
import Image from "next/image";
import { TrendingUp, ShieldCheck, Zap } from "lucide-react";

// Invelisul comun al ecranelor neautentificate (Login + Activare):
// fundal cu grila mascata + glow-uri, header cu logo, layout split
// (stanga branding + beneficii + statistici, dreapta card glass).

const FEATURES = [
  { icon: TrendingUp, text: "Analiză automată a profitabilității" },
  { icon: Zap, text: "Alerte în timp real pentru oportunități" },
  { icon: ShieldCheck, text: "Date verificate din surse multiple" },
];

const STATS = [
  { value: "6", label: "PLATFORME" },
  { value: "12.8k", label: "PREȚURI / ZI" },
  { value: "24/7", label: "MONITORIZARE" },
];

export default function AuthShell({ children }) {
  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "#04070e", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Fundal */}
      <div
        aria-hidden="true"
        style={{
          position: "fixed", inset: 0, pointerEvents: "none",
          backgroundImage:
            "linear-gradient(rgba(59,130,246,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,.04) 1px, transparent 1px)",
          backgroundSize: "52px 52px",
          WebkitMaskImage: "radial-gradient(ellipse at 30% 50%, black 30%, transparent 75%)",
          maskImage: "radial-gradient(ellipse at 30% 50%, black 30%, transparent 75%)",
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: "fixed", top: "50%", left: "26%", transform: "translate(-50%,-50%)",
          width: "640px", height: "640px", borderRadius: "50%", pointerEvents: "none",
          background: "radial-gradient(circle, rgba(34,211,238,.13) 0%, rgba(37,99,235,.08) 45%, transparent 70%)",
          filter: "blur(30px)",
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: "fixed", bottom: "-220px", right: "-140px",
          width: "560px", height: "460px", pointerEvents: "none",
          background: "radial-gradient(ellipse at center, rgba(37,99,235,.12), transparent 70%)",
          filter: "blur(56px)",
        }}
      />
      <div className="fx-topline" aria-hidden="true" />

      {/* Logo */}
      <div style={{ position: "relative", zIndex: 2, display: "flex", alignItems: "center", gap: "10px", padding: "22px 30px" }}>
        <Image
          src="/flipradar-icon.svg"
          alt="FlipRadar"
          width={32}
          height={32}
          priority
          style={{ borderRadius: "9px", boxShadow: "0 4px 14px rgba(34,211,238,.3)" }}
        />
        <div>
          <div style={{ fontSize: "15px", fontWeight: 700, letterSpacing: "-.2px", color: "#e6edf9" }}>
            Flip<span style={{ color: "#7ee7f8" }}>Radar</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "7.5px", letterSpacing: ".22em", color: "#38bdf8", marginTop: "1px" }}>
            PRODUCT RESEARCH
          </div>
        </div>
      </div>

      <div className="auth-grid">
        {/* Stânga — branding */}
        <div className="auth-branding">
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".24em", color: "#38bdf8" }}>
            RADAR PENTRU FLIPPERI · 6 PLATFORME LIVE
          </div>
          <h1 style={{ margin: 0, fontSize: "38px", fontWeight: 600, letterSpacing: "-1px", lineHeight: 1.15, color: "#e6edf9" }}>
            Descoperă produse <span className="text-gradient-hero">profitabile</span> pentru revânzare
          </h1>
          <p style={{ margin: 0, fontSize: "15px", color: "#8b9cbd", lineHeight: 1.6 }}>
            Analizează piața, monitorizează prețurile și găsește cele mai bune oportunități — automat, în timp real.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "11px", marginTop: "6px" }}>
            {FEATURES.map(({ icon: Icon, text }) => (
              <div key={text} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div
                  style={{
                    width: "36px", height: "36px", borderRadius: "11px", flexShrink: 0,
                    background:
                      "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, linear-gradient(135deg, rgba(34,211,238,.35), rgba(59,130,246,.1) 55%, transparent) border-box",
                    border: "1px solid transparent",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}
                >
                  <Icon style={{ width: "15px", height: "15px", color: "#7ee7f8" }} strokeWidth={1.8} />
                </div>
                <span style={{ fontSize: "13px", color: "#a9b8d6" }}>{text}</span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: "22px", marginTop: "8px" }}>
            {STATS.map((s, i) => (
              <div key={s.label} style={{ display: "flex", gap: "22px" }}>
                {i > 0 && <div style={{ width: "1px", background: "rgba(94,140,255,.14)" }} />}
                <div>
                  <div style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-.5px", color: "#7ee7f8" }}>{s.value}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".12em", color: "#41547a", marginTop: "2px" }}>
                    {s.label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dreapta — card glass */}
        <div className="auth-card-wrap">
          <div className="auth-card">{children}</div>
        </div>
      </div>

      <style>{`
        .auth-grid {
          position: relative;
          z-index: 1;
          flex: 1;
          display: grid;
          grid-template-columns: 1.15fr 1fr;
          align-items: center;
          gap: 20px;
          padding: 0 30px 40px;
        }
        .auth-branding {
          display: flex;
          flex-direction: column;
          gap: 22px;
          max-width: 520px;
          margin: 0 auto;
          padding: 20px;
        }
        .auth-card-wrap {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }
        .auth-card {
          width: 100%;
          max-width: 410px;
          border-radius: 22px;
          background: rgba(10,17,32,.6);
          backdrop-filter: blur(26px);
          border: 1px solid rgba(34,211,238,.15);
          box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 30px 70px rgba(0,0,0,.5);
          padding: 32px 34px;
        }
        @media (max-width: 1024px) {
          .auth-grid { grid-template-columns: 1fr; padding: 0 16px 32px; }
          .auth-branding { display: none; }
        }
      `}</style>
    </div>
  );
}

/** Titlul + subtitlul centrat din capul cardului. */
export function AuthCardHeader({ title, subtitle }) {
  return (
    <div style={{ textAlign: "center", marginBottom: "26px" }}>
      <h2 style={{ margin: 0, fontSize: "23px", fontWeight: 600, letterSpacing: "-.4px", color: "#e6edf9" }}>{title}</h2>
      <p style={{ margin: "8px 0 0", fontSize: "13px", color: "#8b9cbd" }}>{subtitle}</p>
    </div>
  );
}

export const authLabelStyle = {
  display: "block",
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: ".15em",
  textTransform: "uppercase",
  color: "#41547a",
  marginBottom: "7px",
};

export const authFieldStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  padding: "13px 14px",
  borderRadius: "12px",
  background:
    "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.1) 55%, transparent) border-box",
  border: "1px solid transparent",
};

export const authInputStyle = {
  flex: 1,
  minWidth: 0,
  background: "transparent",
  border: "none",
  outline: "none",
  color: "#e6edf9",
  fontSize: "13px",
  fontFamily: "var(--font-sans)",
  padding: 0,
};

// Butonul principal al cardului foloseste clasa .btn-auth din globals.css
// (hover-ul e pseudo-clasa, nu handler JS).
