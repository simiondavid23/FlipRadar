"use client";
import { useState } from "react";
import { aiAPI } from "@/lib/api";
import { Sparkles, Target, BarChart3, Package, Calendar, CheckCircle, XCircle, MinusCircle, AlertTriangle, ShoppingBag, Euro, Clock, TrendingUp, Lock } from "lucide-react";
import { useAuth } from "@/lib/auth";

const PLATFORM_COLORS = {
  "OLX":                  { bg: "rgba(96,165,250,0.15)",  color: "#60a5fa" },
  "Vinted":               { bg: "rgba(167,139,250,0.15)", color: "#a78bfa" },
  "Facebook Marketplace": { bg: "rgba(74,222,128,0.15)",  color: "#4ade80" },
};

function platformBadgeStyle(name) {
  const lower = (name || "").toLowerCase();
  if (lower.includes("vinted")) return PLATFORM_COLORS["Vinted"];
  if (lower.includes("facebook")) return PLATFORM_COLORS["Facebook Marketplace"];
  if (lower.includes("olx")) return PLATFORM_COLORS["OLX"];
  return { bg: "rgba(148,163,184,0.15)", color: "var(--text-secondary)" };
}

export default function AIAnalyzePage() {
  const { user } = useAuth();
  const featureDisabled = user?.ai_features_config?.ai_advisor === false;
  const [formData, setFormData] = useState({ product_name: "", category: "", price: "", source: "", resale_price: "" });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await aiAPI.analyzeProduct({
        product_name: formData.product_name,
        category: formData.category,
        price: formData.price ? parseFloat(formData.price) : 0,
        source: formData.source,
        resale_price: formData.resale_price ? parseFloat(formData.resale_price) : null,
      });

      const raw = res.data.result;
      let parsed;
      try {
        parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      } catch {
        setError("Raspunsul AI nu a putut fi procesat. Incearca din nou.");
        return;
      }
      if (parsed.error) {
        setError(parsed.error);
        return;
      }
      setResult(parsed);
    } catch (e) {
      setError("Eroare la analiza. Verifica conexiunea si incearca din nou.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getVerdictInfo = (verdict) => {
    if (!verdict) return { color: "var(--text-secondary)", bg: "rgba(148,163,184,0.1)", icon: MinusCircle };
    if (verdict.includes("RECOMANDAT") && !verdict.includes("NE")) return { color: "#4ade80", bg: "rgba(34,197,94,0.1)", icon: CheckCircle };
    if (verdict.includes("NERECOMANDAT")) return { color: "#f87171", bg: "rgba(239,68,68,0.1)", icon: XCircle };
    return { color: "#facc15", bg: "rgba(250,204,21,0.1)", icon: MinusCircle };
  };

  const getScoreColor = (score) => {
    if (score >= 7) return "#4ade80";
    if (score >= 4) return "#facc15";
    return "#f87171";
  };

  const labelStyle = { display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" };
  const inputStyle = {
    width: "100%", padding: "0.75rem 1rem", borderRadius: "0.625rem",
    backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
  };
  const cardStyle = {
    backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
    borderRadius: "1rem", padding: "1.5rem",
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#ca8a04", display: "flex" }}>
            <Sparkles style={{ width: "20px", height: "20px", color: "var(--text-primary)" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Consilier AI</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Analizeaza profitabilitatea unui produs inainte sa il cumperi
        </p>
      </div>

      {featureDisabled && (
        <div style={{
          backgroundColor: "rgba(100,116,139,0.1)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          padding: "1rem 1.25rem",
          display: "flex", alignItems: "center", gap: "0.75rem",
          marginBottom: "1.5rem",
        }}>
          <Lock style={{ width: "18px", height: "18px", color: "var(--text-secondary)", flexShrink: 0 }} />
          <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Această funcționalitate este dezactivată.{" "}
            <a href="/dashboard/settings" style={{ color: "#60a5fa", fontWeight: 600 }}>Activează din Setări →</a>
          </span>
        </div>
      )}

      <div style={{ opacity: featureDisabled ? 0.4 : 1, pointerEvents: featureDisabled ? "none" : "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Form */}
        <div style={cardStyle}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1.25rem" }}>Detalii produs</h2>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={labelStyle}>Nume produs *</label>
              <input type="text" value={formData.product_name}
                onChange={(e) => setFormData({...formData, product_name: e.target.value})}
                placeholder="ex: Apple AirPods Pro 2" required style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Categorie</label>
              <input type="text" value={formData.category}
                onChange={(e) => setFormData({...formData, category: e.target.value})}
                placeholder="ex: Electronics" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Pret sursa (EUR)</label>
              <input type="number" step="0.01" value={formData.price}
                onChange={(e) => setFormData({...formData, price: e.target.value})}
                placeholder="ex: 199.99" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Magazin sursa</label>
              <input type="text" value={formData.source}
                onChange={(e) => setFormData({...formData, source: e.target.value})}
                placeholder="ex: eMag, Altex" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Pret estimat revanzare (opt.)</label>
              <input type="number" step="0.01" value={formData.resale_price}
                onChange={(e) => setFormData({...formData, resale_price: e.target.value})}
                placeholder="ex: 299.99 - lasa gol pentru sugestie AI" style={inputStyle} />
            </div>
            <button type="submit" disabled={loading}
              style={{
                width: "100%", padding: "0.75rem", borderRadius: "0.625rem",
                backgroundColor: loading ? "#374151" : "#ca8a04",
                border: "none", color: loading ? "white" : "black", fontWeight: 600, fontSize: "0.875rem",
                cursor: loading ? "not-allowed" : "pointer", transition: "all 0.15s ease",
                opacity: loading ? 0.7 : 1,
              }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#a16207"; }}
              onMouseLeave={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#ca8a04"; }}
            >
              {loading ? "Se analizeaza..." : "Analizeaza cu AI"}
            </button>
          </form>
          {error && (
            <p style={{ color: "#f87171", fontSize: "0.8125rem", marginTop: "1rem", padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239,68,68,0.1)" }}>
              {error}
            </p>
          )}
        </div>

        {/* Results */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {result ? (
            <>
              {/* Verdict */}
              {(() => {
                const vi = getVerdictInfo(result.verdict);
                const VerdictIcon = vi.icon;
                return (
                  <div style={{ ...cardStyle, border: `1px solid ${vi.color}33` }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                      <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Verdict</h3>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.375rem 0.875rem", borderRadius: "1rem", backgroundColor: vi.bg }}>
                        <VerdictIcon style={{ width: "16px", height: "16px", color: vi.color }} />
                        <span style={{ fontSize: "0.875rem", fontWeight: 700, color: vi.color }}>{result.verdict}</span>
                      </div>
                    </div>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.6, margin: 0 }}>
                      {result.explicatie_verdict || result.recomandare_finala || result.sumar || result.explicatie}
                    </p>
                  </div>
                );
              })()}

              {/* Quick summary row (viteza + concurenta) */}
              {(result.viteza_vanzare || result.nivel_concurenta) && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                  {result.viteza_vanzare && (
                    <div style={cardStyle}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                        <Clock style={{ width: "14px", height: "14px", color: "#22d3ee" }} />
                        <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Viteza de vanzare</span>
                      </div>
                      <p style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, textTransform: "capitalize" }}>
                        {result.viteza_vanzare}
                      </p>
                    </div>
                  )}
                  {result.nivel_concurenta && (
                    <div style={cardStyle}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                        <TrendingUp style={{ width: "14px", height: "14px", color: "#fb923c" }} />
                        <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Concurenta OLX/Vinted</span>
                      </div>
                      <p style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, textTransform: "capitalize" }}>
                        {result.nivel_concurenta}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Sfat pret revanzare */}
              {result.sfat_pret_revanzare && (
                <div style={{ ...cardStyle, border: "1px solid rgba(96,165,250,0.3)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <Euro style={{ width: "16px", height: "16px", color: "#60a5fa" }} />
                    <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Sfat pret revanzare</h3>
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.6 }}>
                    {result.sfat_pret_revanzare}
                  </p>
                </div>
              )}

              {/* Scores Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <Target style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Scor Profitabilitate</span>
                  </div>
                  <p style={{ fontSize: "2rem", fontWeight: 700, color: getScoreColor(result.scor_profitabilitate), margin: 0 }}>
                    {result.scor_profitabilitate}/10
                  </p>
                </div>
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <BarChart3 style={{ width: "14px", height: "14px", color: "#a78bfa" }} />
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Demand Score</span>
                  </div>
                  <p style={{ fontSize: "2rem", fontWeight: 700, color: getScoreColor(result.demand_score), margin: 0 }}>
                    {result.demand_score}/10
                  </p>
                  {result.explicatie_demand && (
                    <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.375rem", lineHeight: 1.4 }}>
                      {result.explicatie_demand}
                    </p>
                  )}
                </div>
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <Package style={{ width: "14px", height: "14px", color: "#4ade80" }} />
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Competitie</span>
                  </div>
                  <p style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, textTransform: "capitalize" }}>{result.nivel_competitie}</p>
                  {result.explicatie_competitie && (
                    <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.375rem", lineHeight: 1.4 }}>
                      {result.explicatie_competitie}
                    </p>
                  )}
                </div>
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <Calendar style={{ width: "14px", height: "14px", color: "#fb923c" }} />
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Sezonalitate</span>
                  </div>
                  <p style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{result.sezonalitate}</p>
                  {result.explicatie_sezonalitate && (
                    <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.375rem", lineHeight: 1.4 }}>
                      {result.explicatie_sezonalitate}
                    </p>
                  )}
                </div>
              </div>

              {/* Financial breakdown */}
              <div style={cardStyle}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.875rem" }}>
                  <Euro style={{ width: "16px", height: "16px", color: "#4ade80" }} />
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Detalii financiare</h3>
                </div>
                <div>
                  {[
                    { label: "Pret achizitie", value: result.pret_achizitie_eur != null ? `${Number(result.pret_achizitie_eur).toFixed(2)} EUR` : "-", color: "var(--text-secondary)" },
                    { label: "Pret vanzare estimat", value: result.pret_vanzare_estimat != null ? `${Number(result.pret_vanzare_estimat).toFixed(2)} EUR` : "-", color: "var(--text-primary)" },
                    { label: "Profit brut", value: result.profit_brut_eur != null ? `${Number(result.profit_brut_eur).toFixed(2)} EUR` : "-", color: "var(--text-secondary)" },
                    { label: "Costuri operationale", value: result.costuri_operationale_eur != null ? `${Number(result.costuri_operationale_eur).toFixed(2)} EUR` : "-", color: "#fb923c" },
                    { label: "Profit net", value: result.profit_net_eur != null ? `${Number(result.profit_net_eur).toFixed(2)} EUR` : "-", color: result.profit_net_eur >= 0 ? "#4ade80" : "#f87171", bold: true },
                    { label: "Marja neta", value: result.marja_neta_pct != null ? `${Number(result.marja_neta_pct).toFixed(1)}%` : "-", color: "#4ade80" },
                    { label: "ROI", value: result.roi_pct != null ? `${Number(result.roi_pct).toFixed(1)}%` : "-", color: "#4ade80" },
                  ].map((item, i, arr) => (
                    <div key={i} style={{
                      display: "flex", justifyContent: "space-between", padding: "0.5rem 0",
                      borderBottom: i < arr.length - 1 ? "1px solid var(--border-color)" : "none",
                    }}>
                      <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{item.label}</span>
                      <span style={{ fontSize: "0.875rem", fontWeight: item.bold ? 700 : 600, color: item.color }}>{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risk factors */}
              {result.factori_risc?.length > 0 && (
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                    <AlertTriangle style={{ width: "16px", height: "16px", color: "#fb923c" }} />
                    <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Factori de risc</h3>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {result.factori_risc.map((risc, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "rgba(251,146,60,0.08)", border: "1px solid rgba(251,146,60,0.2)" }}>
                        <AlertTriangle style={{ width: "14px", height: "14px", color: "#fb923c", marginTop: "2px", flexShrink: 0 }} />
                        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{risc}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommended platforms */}
              {result.platforme_recomandate?.length > 0 && (
                <div style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                    <ShoppingBag style={{ width: "16px", height: "16px", color: "#60a5fa" }} />
                    <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Platforme recomandate</h3>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {result.platforme_recomandate.map((p, i) => {
                      const s = platformBadgeStyle(p);
                      return (
                        <span key={i} style={{
                          padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
                          fontSize: "0.8125rem", backgroundColor: s.bg, color: s.color, fontWeight: 600,
                        }}>
                          {p}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Tips */}
              <div style={cardStyle}>
                <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Sfaturi AI</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {result.sfaturi?.map((sfat, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }}>
                      <Sparkles style={{ width: "14px", height: "14px", color: "#facc15", marginTop: "2px", flexShrink: 0 }} />
                      <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{sfat}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div style={{ ...cardStyle, padding: "3rem", textAlign: "center" }}>
              <Sparkles style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "var(--text-secondary)" }} />
              <p style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>Introdu datele produsului</p>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                AI-ul va analiza potentialul de profitabilitate si va oferi recomandari.
              </p>
            </div>
          )}
        </div>
      </div>
      </div>

      <style>{`
        @media (max-width: 768px) {
          div[style*="grid-template-columns: 1fr 1fr"] {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}
