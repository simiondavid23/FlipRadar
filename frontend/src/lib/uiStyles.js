// Stiluri UI comune pentru clusterul Radar / Auto Anunturi / Imobiliare Monitor.
// Aliniate la design system-ul "Prism Obsidian" (vezi globals.css).
// Nu edita valorile local in pagini — importa de aici.

// GRADE_COLORS — badge-uri de scor A/B/C/D.
export const GRADE_COLORS = {
  A: { bg: "rgba(74,222,128,0.14)", border: "rgba(74,222,128,0.45)", text: "#4ade80" },
  B: { bg: "rgba(96,165,250,0.14)", border: "rgba(96,165,250,0.45)", text: "#60a5fa" },
  C: { bg: "rgba(250,204,21,0.14)", border: "rgba(250,204,21,0.45)", text: "#fde047" },
  D: { bg: "rgba(251,146,60,0.14)", border: "rgba(251,146,60,0.45)", text: "#fb923c" },
};

// PLATFORM_CHIPS — chip-uri mono 8.5px pentru platforma sursa a unui anunt.
// Cheile sunt EXACT valorile `platform` returnate de API (lowercase).
const chip = (rgb, text) => ({
  bg: `rgba(${rgb},0.14)`,
  border: `rgba(${rgb},0.4)`,
  text,
});

export const PLATFORM_CHIPS = {
  olx: chip("37,99,235", "#8fb5f7"),
  vinted: chip("147,51,234", "#c4b5fd"),
  okazii: chip("74,222,128", "#4ade80"),
  facebook: chip("30,58,138", "#93c5fd"),
  facebook_marketplace: chip("30,58,138", "#93c5fd"),
  facebook_groups: chip("30,58,138", "#93c5fd"),
  lajumate: chip("251,146,60", "#fdba74"),
  publi24: chip("74,222,128", "#86efac"),
  storia: chip("147,51,234", "#c4b5fd"),
  imobiliare_ro: chip("34,211,238", "#7ee7f8"),
  autovit: chip("251,146,60", "#fdba74"),
  olx_auto: chip("37,99,235", "#8fb5f7"),
  facebook_auto: chip("30,58,138", "#93c5fd"),
  mobile_de: chip("129,140,248", "#a5b4fc"),
  autoscout24: chip("129,140,248", "#a5b4fc"),
  kleinanzeigen_auto: chip("129,140,248", "#a5b4fc"),
  ebay_kleinanzeigen: chip("129,140,248", "#a5b4fc"),
  iaai: chip("236,72,153", "#f9a8d4"),
  copart: chip("236,72,153", "#f9a8d4"),
  emag: chip("236,72,153", "#f9a8d4"),
};

const CHIP_FALLBACK = chip("148,163,184", "#cbd5e1");

/** Stil inline complet pentru un chip de platforma (mono 8.5px, radius 7). */
export function platformChipStyle(platform) {
  const c = PLATFORM_CHIPS[String(platform || "").toLowerCase()] || CHIP_FALLBACK;
  return {
    display: "inline-flex",
    alignItems: "center",
    fontFamily: "var(--font-mono)",
    fontSize: "8.5px",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    padding: "2.5px 7px",
    borderRadius: "7px",
    background: c.bg,
    border: `1px solid ${c.border}`,
    color: c.text,
    whiteSpace: "nowrap",
  };
}

/** Stil inline pentru badge-ul de scor A/B/C/D. */
export function gradeBadgeStyle(grade) {
  const c = GRADE_COLORS[grade] || GRADE_COLORS.D;
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    fontWeight: 700,
    padding: "2px 8px",
    borderRadius: "7px",
    background: c.bg,
    border: `1px solid ${c.border}`,
    color: c.text,
  };
}

/** Culoarea unei marje/procent. Praguri implicite 25/10 (imobiliare: 12/7). */
export function marginColorOf(pct, high = 25, mid = 10) {
  const v = Number(pct);
  if (!Number.isFinite(v)) return "var(--text-tertiary)";
  if (v >= high) return "#4ade80";
  if (v >= mid) return "#fde047";
  return "#fb923c";
}

// Suprafete reutilizabile (echivalentele inline ale claselor din globals.css,
// pentru locurile unde stilul se compune dinamic in JS).
export const glassPanel = {
  background: "rgba(8,14,27,0.6)",
  backdropFilter: "blur(20px)",
  border: "1px solid rgba(94,140,255,0.13)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05)",
  borderRadius: "16px",
};

export const glassCardGradient = {
  background:
    "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, " +
    "linear-gradient(135deg, rgba(34,211,238,.38), rgba(59,130,246,.12) 45%, rgba(59,130,246,.02)) border-box",
  border: "1px solid transparent",
  backdropFilter: "blur(20px)",
  borderRadius: "16px",
};

// Bordura-gradient discreta — chip-uri de filtrare, dropdown-uri, input-uri.
export const gradientBorderBg =
  "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, " +
  "linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box";

// selectStyle — dropdown-uri de filtrare (bara de filtre glass).
export const selectStyle = {
  background: gradientBorderBg,
  border: "1px solid transparent",
  borderRadius: "10px",
  padding: "7px 11px",
  color: "var(--text-secondary)",
  fontSize: "12px",
  fontFamily: "var(--font-sans)",
  outline: "none",
  cursor: "pointer",
  minWidth: "160px",
};

// inputStyle / labelStyle — campuri din formulare si modale.
export const inputStyle = {
  width: "100%",
  background: gradientBorderBg,
  border: "1px solid transparent",
  borderRadius: "10px",
  padding: "8px 12px",
  color: "var(--text-primary)",
  fontSize: "12.5px",
  fontFamily: "var(--font-sans)",
  outline: "none",
};

export const labelStyle = {
  display: "block",
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: "0.15em",
  textTransform: "uppercase",
  fontWeight: 400,
  color: "var(--text-mono)",
  marginBottom: "6px",
};

// tabPillStyle — pereche de tab-uri pill (ex. Feed Automat / Cautare Manuala).
export function tabPillStyle(active) {
  return {
    padding: "7px 16px",
    borderRadius: "999px",
    fontSize: "12px",
    fontWeight: 600,
    fontFamily: "var(--font-sans)",
    cursor: "pointer",
    border: `1px solid ${active ? "rgba(34,211,238,.28)" : "rgba(94,140,255,.13)"}`,
    background: active ? "rgba(255,255,255,.08)" : "transparent",
    boxShadow: active
      ? "inset 0 1px 0 rgba(255,255,255,.12), 0 0 18px rgba(34,211,238,.14)"
      : "none",
    color: active ? "#fff" : "var(--text-dim)",
    transition: "all 0.15s ease",
    whiteSpace: "nowrap",
  };
}

// modalFooterStyle — footer sticky al modalelor de keyword (Radar + Auto identice).
export const modalFooterStyle = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "0.5rem",
  padding: "1rem 1.25rem",
  borderTop: "1px solid rgba(94,140,255,0.1)",
  position: "sticky",
  bottom: 0,
  background: "rgba(6,11,22,0.96)",
  backdropFilter: "blur(20px)",
};

// modalOverlayStyle / modalPanelStyle — invelisul comun al modalelor.
export const modalOverlayStyle = {
  position: "fixed",
  inset: 0,
  background: "rgba(2,5,12,0.72)",
  backdropFilter: "blur(6px)",
  zIndex: 100,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "1.5rem",
};

export const modalPanelStyle = {
  background: "rgba(8,14,27,0.94)",
  backdropFilter: "blur(24px)",
  border: "1px solid rgba(34,211,238,0.16)",
  borderRadius: "18px",
  boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
  width: "100%",
  maxHeight: "90vh",
  overflowY: "auto",
};

// STATUS_TABS — identice in auto-listings/feed si real-estate-monitor/feed.
export const STATUS_TABS = [
  { value: "active", label: "Active" },
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];
