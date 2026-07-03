"use client";
// MODIFICARE 18 — modal de confirmare stergere keyword, cu impactul mentionat
// (cate listinguri + anunturi vazute asociate). Refolosit de cele 3 module.
export default function DeleteKeywordModal({ data, onCancel, onConfirm }) {
  if (!data) return null;
  return (
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1.5rem", maxWidth: "440px", width: "90%",
        }}
      >
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)" }}>
          Confirmare ștergere
        </h3>
        <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.6, margin: "0 0 1.25rem" }}>
          Ștergerea keyword-ului <strong style={{ color: "var(--text-primary)" }}>„{data.keywordName}”</strong> va
          elimina și cele <strong style={{ color: "var(--text-primary)" }}>{data.listingCount} listing-uri</strong> și{" "}
          <strong style={{ color: "var(--text-primary)" }}>{data.seenCount} anunțuri văzute</strong> asociate.
          Acțiunea este ireversibilă.
        </p>
        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "1px solid var(--border-color)", background: "transparent", color: "var(--text-secondary)", cursor: "pointer", fontWeight: 600 }}
          >
            Anulează
          </button>
          <button
            onClick={onConfirm}
            style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", background: "var(--fill-danger, #dc2626)", color: "var(--on-danger, #fff)", cursor: "pointer", fontWeight: 600 }}
          >
            Șterge definitiv
          </button>
        </div>
      </div>
    </div>
  );
}
