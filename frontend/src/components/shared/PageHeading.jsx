"use client";

// Antetul comun al paginilor: titlu 24px/600 cu icon cyan 21px + subtitlu 13px,
// iar in dreapta un mic marker mono (ex. "ULTIMA SCANARE · 13:40").
export default function PageHeading({ icon: Icon, title, subtitle, meta, children }) {
  return (
    <div
      style={{
        display: "flex", alignItems: "flex-end", justifyContent: "space-between",
        marginTop: "20px", flexWrap: "wrap", gap: "8px",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <h1
          style={{
            margin: 0, fontSize: "24px", fontWeight: 600, letterSpacing: "-.4px",
            display: "flex", alignItems: "center", gap: "10px", color: "var(--text-primary)",
          }}
        >
          {Icon ? <Icon style={{ width: "21px", height: "21px", color: "#22d3ee", flexShrink: 0 }} strokeWidth={1.8} /> : null}
          {title}
        </h1>
        {subtitle ? (
          <p style={{ margin: "5px 0 0", fontSize: "13px", color: "var(--text-dim)" }}>{subtitle}</p>
        ) : null}
      </div>
      {meta ? (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".1em", color: "var(--text-mono)", textTransform: "uppercase" }}>
          {meta}
        </div>
      ) : null}
      {children}
    </div>
  );
}

/** Numarul evidentiat din subtitlu (ex. „<Hl>8 active</Hl> în vizualizare"). */
export function Hl({ children }) {
  return <span style={{ color: "#7ee7f8", fontWeight: 500 }}>{children}</span>;
}
