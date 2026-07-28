"use client";
// Bara de pill-uri Active / Salvate / Ignorate, refolosita in feed-urile Auto si Imobiliare.
// props: tabs — array de { value, label }; active — value-ul selectat; onChange(value).
export default function StatusTabsBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
      {tabs.map((t) => {
        const isActive = active === t.value;
        return (
          <button
            key={t.value}
            onClick={() => onChange(t.value)}
            className={`tab-pill${isActive ? " active" : ""}`}
            style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
          >
            {isActive && <span className="pill-nav-dot" />}
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
