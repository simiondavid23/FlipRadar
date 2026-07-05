"use client";
import { useState } from "react";

// Control „Selectează: Toate / Primele N / Custom" pentru selecția în masă a anunțurilor
// vizibile. Extras din dashboard/radar/page.js ca sursă unică (Radar + Auto + Imobiliare).
// Props: totalVisible (nr. anunțuri vizibile), selectedCount (câte sunt selectate acum),
// onSelect(count) — apelat cu numărul de selectat (0 = golește).
export default function SelectFiniteControl({ totalVisible, selectedCount, onSelect }) {
  const [customOpen, setCustomOpen] = useState(false);
  const [customN, setCustomN] = useState("");
  const quickBtn = (label, n) => (
    <button
      type="button"
      onClick={() => onSelect(Math.min(n, totalVisible))}
      style={{
        padding: "0.3rem 0.5rem",
        backgroundColor: "var(--bg-dark)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.375rem",
        color: "var(--text-primary)",
        fontSize: "0.7rem", fontWeight: 500, cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
  return (
    <div style={{
      marginLeft: "auto",
      display: "inline-flex", alignItems: "center", gap: "0.375rem",
      padding: "0.375rem 0.625rem",
      border: "1px solid var(--border-color)", borderRadius: "0.5rem",
      backgroundColor: "var(--bg-card)",
      flexWrap: "wrap",
    }}>
      <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", fontWeight: 600 }}>Selectează:</span>
      {quickBtn("Toate", totalVisible)}
      {quickBtn("Primele 10", 10)}
      {quickBtn("Primele 25", 25)}
      {quickBtn("Primele 50", 50)}
      <button type="button" onClick={() => setCustomOpen(!customOpen)} style={{
        padding: "0.3rem 0.5rem", backgroundColor: customOpen ? "var(--blue-primary)" : "var(--bg-dark)",
        color: customOpen ? "white" : "var(--text-primary)",
        border: "1px solid var(--border-color)", borderRadius: "0.375rem",
        fontSize: "0.7rem", fontWeight: 500, cursor: "pointer",
      }}>Custom</button>
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
            width: "70px", padding: "0.3rem 0.5rem",
            backgroundColor: "var(--bg-dark)", color: "var(--text-primary)",
            border: "1px solid var(--border-color)", borderRadius: "0.375rem",
            fontSize: "0.7rem",
          }}
          placeholder="N"
          autoFocus
        />
      )}
      <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.25rem" }}>
        {selectedCount} / {totalVisible} selectate
      </span>
    </div>
  );
}
