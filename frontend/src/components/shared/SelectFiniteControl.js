"use client";
import { useState } from "react";

// Control „Selectează: Toate / Primele N / Custom" pentru selecția în masă a anunțurilor
// vizibile. Extras din dashboard/radar/page.js ca sursă unică (Radar + Auto + Imobiliare).
// Props: totalVisible (nr. anunțuri vizibile), selectedCount (câte sunt selectate acum),
// onSelect(count) — apelat cu numărul de selectat (0 = golește).
const chipBtn = {
  padding: "5px 9px",
  background:
    "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.24), rgba(59,130,246,.07) 55%, transparent) border-box",
  border: "1px solid transparent",
  borderRadius: "8px",
  color: "var(--text-secondary)",
  fontFamily: "var(--font-sans)",
  fontSize: "10.5px",
  fontWeight: 500,
  cursor: "pointer",
  transition: "all .15s ease",
};

export default function SelectFiniteControl({ totalVisible, selectedCount, onSelect }) {
  const [customOpen, setCustomOpen] = useState(false);
  const [customN, setCustomN] = useState("");
  const quickBtn = (label, n) => (
    <button type="button" onClick={() => onSelect(Math.min(n, totalVisible))} style={chipBtn}>
      {label}
    </button>
  );
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: "6px",
      padding: "6px 10px",
      border: "1px solid rgba(94,140,255,.13)", borderRadius: "10px",
      background: "rgba(4,9,18,.4)",
      flexWrap: "wrap",
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--text-mono)" }}>
        Selectează
      </span>
      {quickBtn("Toate", totalVisible)}
      {quickBtn("Primele 10", 10)}
      {quickBtn("Primele 25", 25)}
      {quickBtn("Primele 50", 50)}
      <button
        type="button"
        onClick={() => setCustomOpen(!customOpen)}
        style={customOpen
          ? { ...chipBtn, background: "rgba(34,211,238,.14)", border: "1px solid rgba(34,211,238,.4)", color: "#7ee7f8" }
          : chipBtn}
      >
        Custom
      </button>
      {customOpen && (
        <input
          type="number" min="1" max={totalVisible}
          value={customN}
          onChange={(e) => setCustomN(e.target.value)}
          onBlur={() => {
            const n = parseInt(customN);
            if (!Number.isNaN(n) && n > 0) onSelect(Math.min(n, totalVisible));
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const n = parseInt(customN);
              if (!Number.isNaN(n) && n > 0) onSelect(Math.min(n, totalVisible));
            }
          }}
          style={{
            width: "62px", padding: "5px 8px",
            background: "rgba(4,9,18,.6)", color: "var(--text-primary)",
            border: "1px solid rgba(94,140,255,.18)", borderRadius: "8px",
            fontSize: "10.5px", fontFamily: "var(--font-mono)", outline: "none",
          }}
          placeholder="N"
          autoFocus
        />
      )}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--text-mono)", marginLeft: "2px" }}>
        {selectedCount}/{totalVisible}
      </span>
    </div>
  );
}
