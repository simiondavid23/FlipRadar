"use client";
import Link from "next/link";

// 28px e dimensiunea gandita pentru cifre; valorile-text lungi (ex. numele unei
// categorii) s-ar rupe urat pe latimea cardului, asa ca scad progresiv.
function valueFontSize(value) {
  const len = String(value ?? "").length;
  if (len <= 9) return "28px";
  if (len <= 13) return "22px";
  if (len <= 20) return "18px";
  return "15px";
}

// Cardul KPI mare: bordura-gradient, index mono in colt, eticheta mono,
// valoare cu gradient hero + unitate, chip de delta si linia decorativa de jos.
export default function KpiCard({ idx, icon: Icon, label, value, unit, chip, chipTone = "neutral", note, href }) {
  const tones = {
    good: { bg: "rgba(74,222,128,.1)", color: "#4ade80", border: "rgba(74,222,128,.25)" },
    warn: { bg: "rgba(253,224,71,.1)", color: "#fde047", border: "rgba(253,224,71,.25)" },
    bad: { bg: "rgba(248,113,113,.1)", color: "#f87171", border: "rgba(248,113,113,.25)" },
    neutral: { bg: "rgba(148,163,184,.1)", color: "#a9b8d6", border: "rgba(148,163,184,.2)" },
    cyan: { bg: "rgba(34,211,238,.1)", color: "#7ee7f8", border: "rgba(34,211,238,.25)" },
  };
  const t = tones[chipTone] || tones.neutral;

  const body = (
    <>
      {idx ? (
        <div style={{ position: "absolute", top: "8px", right: "11px", fontFamily: "var(--font-mono)", fontSize: "7.5px", color: "var(--text-faint)" }}>
          {idx}
        </div>
      ) : null}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
        {Icon ? <Icon style={{ width: "14px", height: "14px", color: "#7ee7f8", opacity: 0.9, flexShrink: 0 }} strokeWidth={1.8} /> : null}
        <span className="mono-label">{label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "5px", flexWrap: "wrap" }}>
        <span className="text-gradient-hero" style={{ fontSize: valueFontSize(value), fontWeight: 700, letterSpacing: "-.6px", lineHeight: 1.1 }}>
          {value}
        </span>
        {unit ? <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-tertiary)" }}>{unit}</span> : null}
      </div>
      {(chip || note) && (
        <div style={{ display: "flex", alignItems: "center", gap: "7px", marginTop: "11px", flexWrap: "wrap" }}>
          {chip ? (
            <span
              style={{
                fontFamily: "var(--font-mono)", fontSize: "9px", fontWeight: 700, padding: "2.5px 8px",
                borderRadius: "99px", background: t.bg, color: t.color, border: `1px solid ${t.border}`,
              }}
            >
              {chip}
            </span>
          ) : null}
          {note ? <span style={{ fontSize: "10.5px", color: "var(--text-mono)" }}>{note}</span> : null}
        </div>
      )}
    </>
  );

  const base = {
    position: "relative",
    padding: "17px 18px 15px",
    overflow: "hidden",
    display: "block",
    color: "inherit",
    textDecoration: "none",
  };

  if (!href) {
    return <div className="glass-card-gradient kpi-underline" style={base}>{body}</div>;
  }
  return (
    <Link href={href} className="glass-card-gradient kpi-underline lift-hover" style={{ ...base, cursor: "pointer" }}>
      {body}
    </Link>
  );
}

/** Varianta compacta pentru statisticile de feed (valoare colorata, fara gradient). */
export function StatTile({ value, label, color = "var(--text-primary)" }) {
  return (
    <div
      className="glass-card-gradient"
      style={{ position: "relative", padding: "14px 16px", overflow: "hidden", borderRadius: "14px" }}
    >
      <div style={{ fontSize: "23px", fontWeight: 700, letterSpacing: "-.5px", color, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--text-mono)", marginTop: "4px" }}>
        {label}
      </div>
      <div style={{ position: "absolute", bottom: 0, left: "16px", right: "16px", height: "1px", background: "linear-gradient(90deg,rgba(34,211,238,.3),transparent)" }} />
    </div>
  );
}
