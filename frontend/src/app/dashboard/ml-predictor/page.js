"use client";
import { useState, useEffect, useCallback } from "react";
import { Brain, RefreshCw } from "lucide-react";
import { mlAPI } from "@/lib/api";

const CATEGORIES = [
  { key: "auto_bmw", name: "BMW Auto", icon: "🚗" },
  { key: "electronics_apple", name: "Apple Electronics", icon: "📱" },
];

function fmt(n) {
  return (n ?? 0).toLocaleString("ro-RO");
}

export default function MLPredictorPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retraining, setRetraining] = useState(false);
  const [detectingSold, setDetectingSold] = useState(false);
  const [soldResult, setSoldResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await mlAPI.getStats();
      setStats(r.data || {});
    } catch (e) {
      console.error("[MLPredictor]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const retrain = async () => {
    setRetraining(true);
    try {
      await mlAPI.retrain();
      await load();
      alert("Reantrenare finalizată.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la reantrenare.");
    } finally {
      setRetraining(false);
    }
  };

  const handleSoldDetection = async () => {
    setDetectingSold(true);
    setSoldResult(null);
    try {
      const r = await mlAPI.runSoldDetection();
      setSoldResult(r.data);
      await load();
    } catch {
      setSoldResult({ error: true });
    } finally {
      setDetectingSold(false);
    }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#7c3aed", display: "flex" }}>
            <Brain style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>ML Predictor</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Predicție de prețuri bazată pe date reale de piață
        </p>
        <div style={{ marginLeft: "3rem", marginTop: "0.75rem" }}>
          <button
            onClick={handleSoldDetection}
            disabled={detectingSold}
            style={{
              padding: "0.5rem 1rem",
              backgroundColor: "rgba(34,197,94,0.12)",
              color: "#4ade80",
              border: "1px solid rgba(34,197,94,0.3)",
              borderRadius: "0.5rem",
              fontSize: "0.8125rem",
              fontWeight: 500,
              cursor: detectingSold ? "default" : "pointer",
              opacity: detectingSold ? 0.7 : 1,
              marginTop: "0.5rem",
            }}
          >
            {detectingSold ? "Se verifică..." : "🔍 Detectează vândute acum"}
          </button>

          {soldResult && !soldResult.error && (
            <p style={{
              fontSize: "0.8125rem",
              color: "var(--text-secondary)",
              marginTop: "0.375rem",
            }}>
              Verificate: {soldResult.checked} ·
              Vândute: <span style={{ color: "#4ade80" }}>
                {soldResult.sold}
              </span> ·
              Erori: {soldResult.errors}
            </p>
          )}
          {soldResult?.error && (
            <p style={{ fontSize: "0.8125rem", color: "#f87171",
                        marginTop: "0.375rem" }}>
              Eroare la rulare.
            </p>
          )}
        </div>
      </div>

      {loading || !stats ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #7c3aed", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "1.25rem",
        }}>
          {CATEGORIES.map((cat) => (
            <CategoryCard
              key={cat.key}
              meta={cat}
              data={stats[cat.key] || {}}
              retraining={retraining}
              onRetrain={retrain}
            />
          ))}
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function CategoryCard({ meta, data, retraining, onRetrain }) {
  const total = data.total_collected ?? 0;
  const sold = data.sold_labeled ?? 0;
  const minSamples = data.min_samples ?? 500;
  const readyPct = data.ready_pct ?? 0;
  const hasModel = !!data.has_model;
  const canTrain = sold >= 50; // permite antrenare timpurie pentru testare

  const barColor = readyPct >= 100 ? "#4ade80" : "#2563eb";

  return (
    <section style={{
      backgroundColor: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderRadius: "0.75rem",
      padding: "1.25rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.875rem",
    }}>
      {/* Titlu */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ fontSize: "1.25rem" }}>{meta.icon}</span>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{meta.name}</h2>
      </div>

      {/* Progres date colectate */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.375rem" }}>
          <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Date colectate</span>
          <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{readyPct}%</span>
        </div>
        <div style={{ height: "8px", backgroundColor: "var(--bg-dark)", borderRadius: "999px", overflow: "hidden", border: "1px solid var(--border-color)" }}>
          <div style={{ width: `${Math.min(100, readyPct)}%`, height: "100%", backgroundColor: barColor, transition: "width 0.3s ease" }} />
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>
          {fmt(sold)} / {fmt(minSamples)} (vândute)
        </div>
      </div>

      {/* MODIFICARE 19 — indicator calitate date antrenare (features complete) */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
          <span>Calitate date antrenare</span>
          <span>{fmt(data.complete ?? 0)}/{fmt(data.total ?? 0)} complete</span>
        </div>
        <div style={{ height: 6, background: "var(--bg-dark)", borderRadius: 99, overflow: "hidden", border: "1px solid var(--border-color)" }}>
          <div style={{
            height: "100%",
            width: `${data.completeness_pct || 0}%`,
            background: (data.completeness_pct ?? 0) >= 90 ? "#4ade80" : (data.completeness_pct ?? 0) >= 70 ? "#f59e0b" : "#ef4444",
            borderRadius: 99,
            transition: "width 0.3s",
          }} />
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
          {data.completeness_pct ?? 0}% utilizabile pentru antrenare
        </div>
      </div>

      {/* Total + status model */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
        <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
          Total anunțuri: <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{fmt(total)}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
          <span>Model:</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: hasModel ? "#4ade80" : "#f59e0b" }} />
            {hasModel ? "Antrenat · MAE calculat la antrenare" : "Neantrenat (date insuficiente)"}
          </span>
        </div>
        {hasModel && data.trained_at && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            Antrenat ultima dată: {new Date(data.trained_at * 1000).toLocaleString("ro-RO")}
          </div>
        )}
      </div>

      {/* Buton antrenare */}
      <div style={{ marginTop: "auto", display: "flex", justifyContent: "flex-end" }}>
        <button
          onClick={onRetrain}
          disabled={!canTrain || retraining}
          title={canTrain ? "" : "Sunt necesare cel puțin 50 de exemple vândute"}
          style={{
            padding: "0.5rem 0.875rem",
            backgroundColor: (!canTrain || retraining) ? "var(--bg-dark)" : "#7c3aed",
            color: (!canTrain || retraining) ? "var(--text-muted)" : "white",
            border: (!canTrain || retraining) ? "1px solid var(--border-color)" : "none",
            borderRadius: "0.5rem",
            fontSize: "0.8125rem",
            fontWeight: 600,
            cursor: (!canTrain || retraining) ? "not-allowed" : "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
          }}
        >
          <RefreshCw style={{ width: "14px", height: "14px", animation: retraining ? "spin 1s linear infinite" : "none" }} />
          {retraining ? "Se antrenează..." : "Declanșează antrenare"}
        </button>
      </div>
    </section>
  );
}
