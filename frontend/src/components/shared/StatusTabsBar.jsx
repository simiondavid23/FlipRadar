"use client";
// Bara de pill-uri Active / Salvate / Ignorate, refolosita in feed-urile Auto si Imobiliare.
// props: tabs — array de { value, label }; active — value-ul selectat; onChange(value).
export default function StatusTabsBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "inline-flex", gap: "0.25rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", padding: "0.25rem" }}>
      {tabs.map((t) => {
        const isActive = active === t.value;
        return (
          <button
            key={t.value}
            onClick={() => onChange(t.value)}
            style={{
              padding: "0.375rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", border: "none",
              backgroundColor: isActive ? "rgba(37,99,235,0.15)" : "transparent", color: isActive ? "#60a5fa" : "var(--text-secondary)",
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
