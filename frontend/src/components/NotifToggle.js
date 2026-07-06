"use client";

// Toggle switch 44×24px cu thumb animat pentru canalele de notificare (email/discord).
// Sursa unica de adevar pentru clusterul Radar / Auto Anunturi / Imobiliare Monitor
// (extras din radar/keywords/page.js — Faza 4). Nu duplica local; importa de aici.
export default function NotifToggle({ label, subtitle, value, onChange }) {
  const on = !!value;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.8125rem", color: "var(--text-primary)", fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{subtitle}</div>
      </div>
      <button
        type="button"
        onClick={() => onChange(!on)}
        aria-pressed={on}
        style={{
          width: 44, height: 24, borderRadius: 12,
          backgroundColor: on ? "var(--blue-primary)" : "var(--border-color)",
          border: "none", padding: 2, cursor: "pointer",
          position: "relative",
          transition: "background-color 0.15s ease",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? 22 : 2,
            width: 20, height: 20, borderRadius: "50%",
            backgroundColor: "#ffffff",
            transition: "left 0.15s ease",
            boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          }}
        />
      </button>
    </div>
  );
}
