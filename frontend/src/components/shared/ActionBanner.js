"use client";
import { useState } from "react";
import { GitCompareArrows } from "lucide-react";

// Extras din dashboard/radar/page.js (AA-2) ca sa fie refolosit si de feed-ul Auto Anunturi,
// FARA schimbari vizuale in Radar. Sectiunile cu handler optional se ascund cand handler-ul
// lipseste (comparare: onCompareOpen; export: onBulkExport). Radar paseaza ambele -> randare
// identica cu varianta locala de dinainte.
export default function ActionBanner({
  comparisonCount = 0, bulkCount, totalVisible,
  onCompareOpen, onCompareClear,
  onBulkSave, onBulkIgnore, onBulkDelete, onBulkExport, onBulkClear,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  return (
    <div
      className="glass-panel"
      style={{
        padding: "11px 13px",
        display: "flex", flexWrap: "wrap",
        alignItems: "center", gap: "8px",
        borderRadius: "14px",
      }}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".14em", color: "var(--text-mono)", padding: "0 4px" }}>
        ACȚIUNI ÎN MASĂ
      </span>

      {onCompareOpen && comparisonCount >= 1 && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 500 }}>
            {comparisonCount} listing(uri) selectate pentru comparare
          </span>
          {comparisonCount >= 2 && (
            <button onClick={onCompareOpen} style={primaryBannerBtn}>
              <GitCompareArrows style={{ width: "12px", height: "12px", display: "inline", marginRight: "5px", verticalAlign: "-2px" }} />
              Compară
            </button>
          )}
          <button onClick={onCompareClear} style={ghostBtn}>Golește selecția</button>
        </div>
      )}

      {bulkCount > 0 && (
        <div style={{
          marginLeft: comparisonCount > 0 ? "auto" : 0,
          display: "inline-flex", alignItems: "center", gap: "8px", flexWrap: "wrap",
        }}>
          <span style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 500 }}>
            {bulkCount} anunțuri selectate
          </span>
          {confirmDelete ? (
            <>
              <span style={{ fontSize: "11.5px", color: "#fca5a5" }}>
                Sigur vrei să ștergi {bulkCount} anunțuri? Acțiunea nu poate fi anulată.
              </span>
              <button onClick={() => { onBulkDelete(); setConfirmDelete(false); }} style={dangerBtn}>
                Confirmă ștergerea
              </button>
              <button onClick={() => setConfirmDelete(false)} style={ghostBtn}>Anulează</button>
            </>
          ) : (
            <>
              <button onClick={onBulkSave} style={primaryBannerBtn}>Salvează</button>
              <button onClick={onBulkIgnore} style={ghostBtn}>Ignoră</button>
              <button onClick={() => setConfirmDelete(true)} style={dangerBtn}>Șterge</button>
              {onBulkExport && (
                <button onClick={onBulkExport} style={ghostBtn}>Exportă selecția</button>
              )}
              <button onClick={onBulkClear} style={ghostBtn}>Golește selecția</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const btnBase = {
  padding: "6px 13px",
  borderRadius: "9px",
  fontFamily: "var(--font-sans)",
  fontSize: "11.5px",
  fontWeight: 500,
  cursor: "pointer",
  transition: "all .15s ease",
  whiteSpace: "nowrap",
};

const primaryBannerBtn = {
  ...btnBase,
  fontWeight: 600,
  border: "1px solid rgba(34,211,238,.42)",
  background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)",
  color: "#7ee7f8",
  boxShadow: "0 0 18px rgba(34,211,238,.14)",
};

const ghostBtn = {
  ...btnBase,
  background:
    "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.26), rgba(59,130,246,.08) 55%, transparent) border-box",
  border: "1px solid transparent",
  color: "var(--text-secondary)",
};

const dangerBtn = {
  ...btnBase,
  fontWeight: 600,
  background: "linear-gradient(135deg, rgba(248,113,113,.14), rgba(248,113,113,.03) 60%, transparent)",
  border: "1px solid rgba(248,113,113,.36)",
  color: "#fca5a5",
};
