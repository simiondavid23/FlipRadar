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
    <div style={{
      backgroundColor: "rgba(37,99,235,0.1)",
      border: "0.5px solid rgba(37,99,235,0.3)",
      borderRadius: "0.5rem",
      padding: "0.625rem 1rem",
      display: "flex", flexWrap: "wrap",
      alignItems: "center", gap: "0.75rem",
      backdropFilter: "blur(8px)",
    }}>
      {onCompareOpen && comparisonCount >= 1 && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 600 }}>
            {comparisonCount} listing(uri) selectate pentru comparare
          </span>
          {comparisonCount >= 2 && (
            <button onClick={onCompareOpen} style={primaryBannerBtn}>
              <GitCompareArrows style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.25rem" }} />
              Compară
            </button>
          )}
          <button onClick={onCompareClear} style={ghostBtn}>Golește selecția</button>
        </div>
      )}

      {bulkCount > 0 && (
        <div style={{
          marginLeft: comparisonCount > 0 ? "auto" : 0,
          display: "inline-flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap",
        }}>
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 600 }}>
            {bulkCount} anunțuri selectate
          </span>
          {confirmDelete ? (
            <>
              <span style={{ fontSize: "0.75rem", color: "#fca5a5" }}>
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

const primaryBannerBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "var(--blue-primary)",
  color: "white", border: "none",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
  cursor: "pointer",
};

const ghostBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "var(--bg-dark)",
  color: "var(--text-secondary)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 500,
  cursor: "pointer",
};

const dangerBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "rgba(239,68,68,0.15)",
  color: "#fca5a5",
  border: "1px solid rgba(239,68,68,0.3)",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
  cursor: "pointer",
};
