"use client";

// Toggle cyan (30×16) cu etichetă + subtitlu pentru canalele de notificare (email/discord).
// Sursa unica de adevar pentru clusterul Radar / Auto Anunturi / Imobiliare Monitor.
// Nu duplica local; importa de aici.
export default function NotifToggle({ label, subtitle, value, onChange }) {
  const on = !!value;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "12.5px", color: "var(--text-primary)", fontWeight: 500 }}>{label}</div>
        {subtitle ? (
          <div style={{ fontSize: "10.5px", color: "var(--text-muted)", marginTop: "2px" }}>{subtitle}</div>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => onChange(!on)}
        aria-pressed={on}
        aria-label={label}
        className={`toggle-cyan${on ? " on" : ""}`}
      />
    </div>
  );
}
