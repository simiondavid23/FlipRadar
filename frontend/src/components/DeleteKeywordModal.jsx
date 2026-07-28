"use client";
import { modalOverlayStyle, modalPanelStyle } from "@/lib/uiStyles";

// MODIFICARE 18 — modal de confirmare stergere keyword, cu impactul mentionat
// (cate listinguri + anunturi vazute asociate). Refolosit de cele 3 module.
export default function DeleteKeywordModal({ data, onCancel, onConfirm }) {
  if (!data) return null;
  return (
    <div onClick={onCancel} style={{ ...modalOverlayStyle, zIndex: 1000 }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ ...modalPanelStyle, maxWidth: "440px", padding: "22px", overflowY: "visible" }}
      >
        <h3 style={{ margin: "0 0 10px", fontSize: "16px", fontWeight: 600, color: "var(--text-primary)" }}>
          Confirmare ștergere
        </h3>
        <p style={{ fontSize: "12.5px", color: "var(--text-secondary)", lineHeight: 1.6, margin: "0 0 18px" }}>
          Ștergerea keyword-ului <strong style={{ color: "var(--text-primary)" }}>„{data.keywordName}”</strong> va
          elimina și cele <strong style={{ color: "var(--text-primary)" }}>{data.listingCount} listing-uri</strong> și{" "}
          <strong style={{ color: "var(--text-primary)" }}>{data.seenCount} anunțuri văzute</strong> asociate.
          Acțiunea este ireversibilă.
        </p>
        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button onClick={onCancel} className="btn-neutral">Anulează</button>
          <button onClick={onConfirm} className="btn-danger">Șterge definitiv</button>
        </div>
      </div>
    </div>
  );
}
