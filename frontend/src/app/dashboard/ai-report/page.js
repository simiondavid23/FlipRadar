"use client";
import { useState } from "react";
import { aiAPI } from "@/lib/api";
import { FileBarChart, RefreshCw, TrendingUp, AlertCircle, Lightbulb, Activity } from "lucide-react";

export default function AIReportPage() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const generateReport = async () => {
    setLoading(true);
    setError("");
    setReport(null);

    try {
      const res = await aiAPI.getReport();
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
      setReport({ ...parsed, user_data: res.data.user_data });
    } catch (e) {
      setError("Eroare la generarea raportului. Incearca din nou.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const cardStyle = {
    backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
    borderRadius: "1rem", padding: "1.5rem",
  };

  const getScoreColor = (score) => {
    if (score >= 70) return "#4ade80";
    if (score >= 40) return "#facc15";
    return "#f87171";
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
            <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#0891b2", display: "flex" }}>
              <FileBarChart style={{ width: "20px", height: "20px", color: "var(--text-primary)" }} />
            </div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Raport Piata</h1>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
            Analiza de piata generata automat pentru categoria ta de produse
          </p>
        </div>
        <button onClick={generateReport} disabled={loading}
          style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            padding: "0.625rem 1.25rem", borderRadius: "0.625rem",
            backgroundColor: loading ? "#374151" : "#0891b2",
            border: "none", color: "var(--text-primary)", fontWeight: 600, fontSize: "0.875rem",
            cursor: loading ? "not-allowed" : "pointer", transition: "all 0.15s ease",
            opacity: loading ? 0.7 : 1,
          }}
          onMouseEnter={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#0e7490"; }}
          onMouseLeave={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#0891b2"; }}
        >
          {loading ? (
            <><RefreshCw style={{ width: "16px", height: "16px", animation: "spin 1s linear infinite" }} /> Se genereaza...</>
          ) : (
            <><FileBarChart style={{ width: "16px", height: "16px" }} /> Genereaza Raport</>
          )}
        </button>
      </div>

      {error && (
        <div style={{
          display: "flex", alignItems: "center", gap: "0.75rem",
          padding: "1rem", borderRadius: "0.75rem", marginBottom: "1.5rem",
          backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
        }}>
          <AlertCircle style={{ width: "18px", height: "18px", color: "#f87171", flexShrink: 0 }} />
          <p style={{ color: "#f87171", fontSize: "0.875rem", margin: 0 }}>{error}</p>
        </div>
      )}

      {report ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Activity Score */}
          <div style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>Scor de Activitate</h3>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>Bazat pe utilizarea platformei</p>
              </div>
              <div style={{ textAlign: "center" }}>
                <p style={{ fontSize: "3rem", fontWeight: 700, color: getScoreColor(report.scor_activitate), margin: 0, lineHeight: 1 }}>
                  {report.scor_activitate}
                </p>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>din 100</p>
              </div>
            </div>
          </div>

          {/* Summary */}
          <div style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <Activity style={{ width: "16px", height: "16px", color: "#60a5fa" }} />
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Rezumat General</h3>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.7, margin: 0 }}>{report.rezumat_general}</p>
          </div>

          {/* Key Stats */}
          <div style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <TrendingUp style={{ width: "16px", height: "16px", color: "#4ade80" }} />
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Statistici Cheie</h3>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {report.statistici_cheie?.map((stat, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }}>
                  <div style={{ width: "22px", height: "22px", borderRadius: "50%", backgroundColor: "rgba(59,130,246,0.2)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "1px" }}>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: "#60a5fa" }}>{i + 1}</span>
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{stat}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Two columns: Products + Alerts */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={cardStyle}>
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Analiza Produse</h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.7, margin: 0 }}>{report.produse_recomandate}</p>
            </div>
            <div style={cardStyle}>
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Status Alerte</h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.7, margin: 0 }}>{report.alerte_status}</p>
            </div>
          </div>

          {/* Trends */}
          <div style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <TrendingUp style={{ width: "16px", height: "16px", color: "#a78bfa" }} />
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Tendinte</h3>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.7, margin: 0 }}>{report.tendinte}</p>
          </div>

          {/* Recommendations */}
          <div style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <Lightbulb style={{ width: "16px", height: "16px", color: "#facc15" }} />
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Recomandari</h3>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {report.recomandari?.map((rec, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.625rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }}>
                  <Lightbulb style={{ width: "14px", height: "14px", color: "#facc15", marginTop: "2px", flexShrink: 0 }} />
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>{rec}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Next Step */}
          <div style={{
            ...cardStyle,
            backgroundColor: "rgba(59,130,246,0.08)",
            border: "1px solid rgba(59,130,246,0.25)",
          }}>
            <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>Urmatorul Pas Recomandat</h3>
            <p style={{ color: "#93c5fd", fontSize: "0.875rem", margin: 0 }}>{report.urmatorul_pas}</p>
          </div>
        </div>
      ) : !loading && (
        <div style={{ ...cardStyle, padding: "3rem", textAlign: "center" }}>
          <FileBarChart style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>Genereaza un raport AI</p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Apasa butonul de mai sus pentru a primi o analiza completa a activitatii tale.
          </p>
        </div>
      )}
    </div>
  );
}
