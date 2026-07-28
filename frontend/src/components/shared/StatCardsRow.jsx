"use client";
import { StatTile } from "./KpiCard";

// Grila de carduri statistice de feed (Radar / Auto / Imobiliare).
// props: cards — array de { label, value, color }.
export default function StatCardsRow({ cards }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px", marginTop: "16px" }}>
      {cards.map((c) => (
        <StatTile key={c.label} value={c.value} label={c.label} color={c.color} />
      ))}
    </div>
  );
}
