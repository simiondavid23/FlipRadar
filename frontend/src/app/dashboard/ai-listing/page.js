"use client";
import { useState } from "react";
import { aiAPI } from "@/lib/api";
import { FileText, Copy, Check, Sparkles } from "lucide-react";

export default function AIListingPage() {
  const [formData, setFormData] = useState({
    product_name: "",
    category: "",
    features: "",
    price: "",
    product_condition: "Nou",
    target_platform: "OLX",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await aiAPI.generateListing({
        product_name: formData.product_name,
        category: formData.category,
        features: formData.features,
        price: formData.price ? parseFloat(formData.price) : 0,
        product_condition: formData.product_condition,
        target_platform: formData.target_platform,
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
      setError("Eroare la generare. Verifica conexiunea si incearca din nou.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, field) => {
    navigator.clipboard.writeText(text);
    setCopied(field);
    setTimeout(() => setCopied(""), 2000);
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
  const copyBtnBase = {
    display: "flex", alignItems: "center", gap: "0.375rem",
    padding: "0.375rem 0.75rem", borderRadius: "0.5rem", fontSize: "0.75rem",
    border: "1px solid var(--border-color)", backgroundColor: "transparent",
    color: "var(--text-secondary)", cursor: "pointer", transition: "all 0.15s ease",
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#16a34a", display: "flex" }}>
            <FileText style={{ width: "20px", height: "20px", color: "var(--text-primary)" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Creator Anunturi</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Genereaza anunturi optimizate pentru OLX, Vinted sau Facebook Marketplace
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Form */}
        <div style={cardStyle}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1.25rem" }}>Informatii produs</h2>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={labelStyle}>Nume produs *</label>
              <input type="text" value={formData.product_name}
                onChange={(e) => setFormData({...formData, product_name: e.target.value})}
                placeholder="ex: Casti Bluetooth Wireless" required style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Categorie</label>
              <input type="text" value={formData.category}
                onChange={(e) => setFormData({...formData, category: e.target.value})}
                placeholder="ex: Electronics, Audio" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Caracteristici produsului</label>
              <textarea value={formData.features}
                onChange={(e) => setFormData({...formData, features: e.target.value})}
                placeholder="ex: Bluetooth 5.3, ANC, 30h baterie, rezistent la apa IPX5"
                rows={3} style={{ ...inputStyle, resize: "none" }} />
            </div>
            <div>
              <label style={labelStyle}>Pret (EUR)</label>
              <input type="number" step="0.01" value={formData.price}
                onChange={(e) => setFormData({...formData, price: e.target.value})}
                placeholder="ex: 49.99" style={inputStyle} />
            </div>

            <div>
              <label style={labelStyle}>Stare produs</label>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {["Nou", "Second hand", "Negociabil"].map((opt) => {
                  const active = formData.product_condition === opt;
                  return (
                    <label
                      key={opt}
                      style={{
                        flex: 1, minWidth: "100px",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        gap: "0.375rem",
                        padding: "0.625rem 0.75rem",
                        borderRadius: "0.5rem",
                        cursor: "pointer",
                        backgroundColor: active ? "var(--green-dim)" : "var(--bg-dark)",
                        border: active ? "1px solid var(--green-primary)" : "1px solid var(--border-color)",
                        color: active ? "var(--green-bright)" : "var(--text-secondary)",
                        fontSize: "0.8125rem",
                        fontWeight: active ? 600 : 500,
                        transition: "all 0.15s ease",
                      }}
                    >
                      <input
                        type="radio"
                        name="product_condition"
                        value={opt}
                        checked={active}
                        onChange={() => setFormData({ ...formData, product_condition: opt })}
                        style={{ display: "none" }}
                      />
                      {opt}
                    </label>
                  );
                })}
              </div>
            </div>

            <div>
              <label style={labelStyle}>Platforma tinta</label>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {[
                  { v: "OLX", color: "#60a5fa", dim: "rgba(96,165,250,0.15)" },
                  { v: "Vinted", color: "#a78bfa", dim: "rgba(167,139,250,0.15)" },
                  { v: "Facebook Marketplace", color: "#4ade80", dim: "rgba(74,222,128,0.15)" },
                ].map((opt) => {
                  const active = formData.target_platform === opt.v;
                  return (
                    <label
                      key={opt.v}
                      style={{
                        flex: 1, minWidth: "100px",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        gap: "0.375rem",
                        padding: "0.625rem 0.75rem",
                        borderRadius: "0.5rem",
                        cursor: "pointer",
                        backgroundColor: active ? opt.dim : "var(--bg-dark)",
                        border: active ? `1px solid ${opt.color}` : "1px solid var(--border-color)",
                        color: active ? opt.color : "var(--text-secondary)",
                        fontSize: "0.8125rem",
                        fontWeight: active ? 600 : 500,
                        transition: "all 0.15s ease",
                        textAlign: "center",
                      }}
                    >
                      <input
                        type="radio"
                        name="target_platform"
                        value={opt.v}
                        checked={active}
                        onChange={() => setFormData({ ...formData, target_platform: opt.v })}
                        style={{ display: "none" }}
                      />
                      {opt.v}
                    </label>
                  );
                })}
              </div>
            </div>

            <button type="submit" disabled={loading}
              style={{
                width: "100%", padding: "0.75rem", borderRadius: "0.625rem",
                backgroundColor: loading ? "#374151" : "#16a34a",
                border: "none", color: "var(--text-primary)", fontWeight: 600, fontSize: "0.875rem",
                cursor: loading ? "not-allowed" : "pointer", transition: "all 0.15s ease",
                opacity: loading ? 0.7 : 1,
              }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#15803d"; }}
              onMouseLeave={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#16a34a"; }}
            >
              {loading ? "Se genereaza..." : "Genereaza Listing"}
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
              {/* Title */}
              <div style={cardStyle}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Titlu listing</h3>
                  <button onClick={() => copyToClipboard(result.titlu, "titlu")} style={copyBtnBase}>
                    {copied === "titlu" ? <Check style={{ width: "12px", height: "12px", color: "#4ade80" }} /> : <Copy style={{ width: "12px", height: "12px" }} />}
                    {copied === "titlu" ? "Copiat!" : "Copiaza"}
                  </button>
                </div>
                <p style={{ color: "var(--text-primary)", fontSize: "0.875rem", lineHeight: 1.6 }}>{result.titlu}</p>
              </div>

              {/* Bullet Points */}
              <div style={cardStyle}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Bullet Points</h3>
                  <button onClick={() => copyToClipboard(result.bullet_points?.join("\n"), "bullets")} style={copyBtnBase}>
                    {copied === "bullets" ? <Check style={{ width: "12px", height: "12px", color: "#4ade80" }} /> : <Copy style={{ width: "12px", height: "12px" }} />}
                    {copied === "bullets" ? "Copiat!" : "Copiaza"}
                  </button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {result.bullet_points?.map((bp, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }}>
                      <span style={{ color: "#4ade80", fontWeight: 700, marginTop: "1px" }}>•</span>
                      <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{bp}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div style={cardStyle}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Descriere</h3>
                  <button onClick={() => copyToClipboard(result.descriere, "desc")} style={copyBtnBase}>
                    {copied === "desc" ? <Check style={{ width: "12px", height: "12px", color: "#4ade80" }} /> : <Copy style={{ width: "12px", height: "12px" }} />}
                    {copied === "desc" ? "Copiat!" : "Copiaza"}
                  </button>
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", whiteSpace: "pre-wrap", lineHeight: 1.7, margin: 0 }}>{result.descriere}</p>
              </div>

              {/* Keywords */}
              <div style={cardStyle}>
                <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Cuvinte cheie SEO</h3>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {result.cuvinte_cheie?.map((kw, i) => (
                    <span key={i} style={{ padding: "0.25rem 0.75rem", borderRadius: "1rem", fontSize: "0.75rem", backgroundColor: "rgba(59,130,246,0.15)", color: "#60a5fa" }}>
                      {kw}
                    </span>
                  ))}
                </div>
              </div>

              {/* Tips */}
              {result.sfaturi_listing && (
                <div style={cardStyle}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Sfaturi optimizare</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {result.sfaturi_listing.map((tip, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }}>
                        <Sparkles style={{ width: "14px", height: "14px", color: "#facc15", marginTop: "2px", flexShrink: 0 }} />
                        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{tip}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ ...cardStyle, padding: "3rem", textAlign: "center" }}>
              <FileText style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "var(--text-secondary)" }} />
              <p style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>Introdu informatiile produsului</p>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                AI-ul va genera un listing complet optimizat pentru marketplace-uri.
              </p>
            </div>
          )}
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
