// Stiluri UI comune pentru clusterul Radar / Auto Anunturi / Imobiliare Monitor.
// Sursa unica de adevar: extrase din dashboard/radar/page.js (Faza 1).
// Nu edita valorile local in pagini — importa de aici.

// GRADE_COLORS — sursa: SCORE_COLORS din radar/page.js (chei bg / border / text).
export const GRADE_COLORS = {
  A: { bg: "rgba(22,163,74,0.18)", border: "#16a34a", text: "#4ade80" },
  B: { bg: "rgba(59,130,246,0.18)", border: "#3b82f6", text: "#60a5fa" },
  C: { bg: "rgba(250,204,21,0.18)", border: "#facc15", text: "#fde047" },
  D: { bg: "rgba(249,115,22,0.18)", border: "#f97316", text: "#fb923c" },
};

// selectStyle — sursa: varianta din radar/page.js (cea mai completa:
// include cursor:pointer si minWidth:160px fata de variantele Auto/Imobiliare).
export const selectStyle = {
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  padding: "0.5rem 0.75rem",
  color: "var(--text-primary)",
  fontSize: "0.8125rem",
  outline: "none",
  cursor: "pointer",
  minWidth: "160px",
};

// inputStyle / labelStyle — identice in tot clusterul radar
// (radar ManualSearchTab, auto-listings/keywords, real-estate-monitor/keywords,
// real-estate-monitor/groups). Variantele din login/register/ai-* difera si tin
// de alte zone functionale — nu sunt sursa aici.
export const inputStyle = {
  width: "100%",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  padding: "0.5rem 0.75rem",
  color: "var(--text-primary)",
  fontSize: "0.875rem",
  outline: "none",
};

export const labelStyle = {
  display: "block",
  fontSize: "0.75rem",
  fontWeight: 600,
  color: "var(--text-secondary)",
  marginBottom: "0.375rem",
};

// tabPillStyle — sursa: functia din radar/page.js. Pentru orice pereche de tab-uri
// tip pill (ex. Feed Automat / Cautare Manuala).
export function tabPillStyle(active) {
  return {
    padding: "0.5rem 1.25rem",
    borderRadius: "999px",
    fontSize: "0.875rem",
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid var(--border-color)",
    backgroundColor: active ? "var(--blue-primary)" : "transparent",
    color: active ? "white" : "var(--text-secondary)",
    transition: "all 0.15s ease",
  };
}

// STATUS_TABS — identice in auto-listings/feed si real-estate-monitor/feed.
export const STATUS_TABS = [
  { value: "active", label: "Active" },
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];
