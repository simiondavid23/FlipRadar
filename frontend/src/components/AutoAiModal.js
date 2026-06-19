"use client";
// FlipRadar — modal "Analiza AI descriere" pentru anunturi auto.
import { useState, useEffect } from "react";
import { autoAPI } from "@/lib/api";
import { X, Sparkles, AlertTriangle } from "lucide-react";

const FIELD_LABELS = {
  itp_valid_until: "ITP valabil pana la",
  timing_belt_changed_at_km: "Curea distributie schimbata la (km)",
  oil_change_at_km: "Ulei schimbat la (km)",
  brake_pads_changed: "Placute frana schimbate",
  tires_info: "Anvelope",
  num_owners: "Numar proprietari",
  service_history: "Istoric service",
  accidents_denied: "Fara accidente (declarat)",
  defects_mentioned: "Defecte mentionate",
  recent_works: "Lucrari recente",
  import_from: "Importat din",
  urgent_sale: "Vanzare urgenta",
  warranty_months: "Garantie (luni)",
  aftermarket_modifications: "Modificari aftermarket",
  reason_for_sale: "Motiv vanzare",
  allows_test_drive: "Permite test drive",
};

function fmtValue(v) {
  if (typeof v === "boolean") return v ? "Da" : "Nu";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.8125rem", outline: "none",
};

export default function AutoAiModal({ open, onClose, listing }) {
  const [description, setDescription] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setDescription(listing?.descriere || "");
      setResult(null);
      setError("");
    }
  }, [open, listing]);

  if (!open) return null;

  const analyze = async () => {
    if (description.trim().length < 50) {
      setError("Introdu o descriere de minim 50 de caractere.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await autoAPI.extractDescription({
        description: description.trim(),
        km: listing?.km ?? null,
        year: listing?.year ?? null,
      });
      setResult(res.data?.extracted || {});
    } catch (e) {
      setError(e.response?.data?.detail || "Eroare la analiza AI.");
    } finally {
      setLoading(false);
    }
  };

  const warnings = result?._warnings || [];
  const fields = result
    ? Object.entries(result).filter(([k, v]) => k !== "_warnings" && v != null && v !== "")
    : [];

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "3rem 1rem", overflowY: "auto",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "100%", maxWidth: "560px", backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Sparkles style={{ width: "18px", height: "18px", color: "#a78bfa" }} /> Analiza AI descriere
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        {listing?.titlu && (
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: 0, marginBottom: "0.75rem" }}>{listing.titlu}</p>
        )}

        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" }}>
          Descriere anunt (lipeste textul din anunt)
        </label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={6}
          placeholder="Lipeste aici descrierea completa a anuntului auto..."
          style={{ ...inputStyle, resize: "vertical", fontFamily: "inherit" }} />

        <button onClick={analyze} disabled={loading}
          style={{ marginTop: "0.75rem", padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "#7c3aed", color: "white", border: "none", cursor: loading ? "wait" : "pointer", fontSize: "0.8125rem", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
          <Sparkles style={{ width: "14px", height: "14px" }} /> {loading ? "Se analizeaza..." : "Analizeaza"}
        </button>

        {error && <p style={{ color: "#f87171", fontSize: "0.8125rem", marginTop: "0.75rem" }}>{error}</p>}

        {result && (
          <div style={{ marginTop: "1rem" }}>
            {warnings.length > 0 && (
              <div style={{ marginBottom: "0.75rem" }}>
                {warnings.map((w, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", color: "#fb923c", backgroundColor: "rgba(251,146,60,0.1)", border: "1px solid rgba(251,146,60,0.3)", borderRadius: "0.5rem", padding: "0.375rem 0.625rem", marginBottom: "0.375rem" }}>
                    <AlertTriangle style={{ width: "13px", height: "13px", flexShrink: 0 }} /> {w}
                  </div>
                ))}
              </div>
            )}
            {fields.length === 0 ? (
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                AI nu a gasit informatii explicite in descriere.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {fields.map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "1rem", fontSize: "0.8125rem", padding: "0.375rem 0", borderBottom: "1px solid var(--border-color)" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{FIELD_LABELS[k] || k}</span>
                    <span style={{ color: "var(--text-primary)", fontWeight: 600, textAlign: "right" }}>{fmtValue(v)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
