"use client";
// Grila de carduri statistice, refolosita in feed-urile Auto si Imobiliare.
// props: cards — array de { label, value, color }.
export default function StatCardsRow({ cards }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.875rem", marginBottom: "1.25rem" }}>
      {cards.map((c) => (
        <div key={c.label} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem" }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, color: c.color }}>{c.value}</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.125rem" }}>{c.label}</div>
        </div>
      ))}
    </div>
  );
}
