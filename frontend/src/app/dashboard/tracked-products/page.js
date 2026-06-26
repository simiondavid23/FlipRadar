"use client";
import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { trackedProductsAPI } from "@/lib/api";
import { Heart, Trash2, Bell, Package, ExternalLink, Activity } from "lucide-react";

// Pills de status + pills per magazin (sursa = domeniul salvat de scrapere).
const STATUS_FILTERS = [
  { label: "Toate", value: "all" },
  { label: "Monitorizate", value: "monitored" },
  { label: "Nemonitorizate", value: "unmonitored" },
];

const SOURCE_FILTERS = [
  { label: "Altex", value: "altex.ro" },
  { label: "eMAG", value: "emag.ro" },
  { label: "PCGarage", value: "pcgarage.ro" },
  { label: "Sole", value: "sole.ro" },
  { label: "FarmaciaTei", value: "farmaciatei.ro" },
];

const SOURCE_STYLES = {
  "altex.ro": { bg: "rgba(59,130,246,0.2)", fg: "#60a5fa" },
  "sole.ro": { bg: "rgba(236,72,153,0.2)", fg: "#f472b6" },
  "farmaciatei.ro": { bg: "rgba(34,197,94,0.2)", fg: "#4ade80" },
  "emag.ro": { bg: "rgba(250,204,21,0.2)", fg: "#facc15" },
  "pcgarage.ro": { bg: "rgba(168,85,247,0.2)", fg: "#c084fc" },
};

export default function TrackedProductsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState("all");
  // Valori draft pentru inputul "Alerta pret", per produs.
  const [alertDrafts, setAlertDrafts] = useState({});
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    try {
      const res = await trackedProductsAPI.getAll();
      setItems(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Tracked products error:", err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = useMemo(() => {
    if (activeFilter === "all") return items;
    if (activeFilter === "monitored") return items.filter((p) => p.monitoring_active);
    if (activeFilter === "unmonitored") return items.filter((p) => !p.monitoring_active);
    return items.filter((p) => p.source === activeFilter);
  }, [items, activeFilter]);

  const toggleMonitoring = async (product) => {
    const next = !product.monitoring_active;
    setBusyId(product.id);
    try {
      const draft = alertDrafts[product.id];
      const raw = next ? (draft !== undefined ? draft : product.alert_threshold) : null;
      const threshold = raw === "" || raw == null ? null : parseFloat(raw);
      await trackedProductsAPI.toggleMonitoring(product.id, next, threshold);
      setItems((prev) =>
        prev.map((p) =>
          p.id === product.id
            ? { ...p, monitoring_active: next, alert_threshold: next ? (threshold ?? p.alert_threshold) : null }
            : p
        )
      );
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la actualizarea monitorizarii");
    } finally {
      setBusyId(null);
    }
  };

  const setAlert = async (product) => {
    const draft = alertDrafts[product.id];
    const value = draft !== undefined ? draft : product.alert_threshold;
    if (value === "" || value == null) {
      alert("Introdu o valoare valida pentru alerta de pret");
      return;
    }
    const parsed = parseFloat(value);
    if (!isFinite(parsed) || parsed < 0) {
      alert("Alerta de pret trebuie sa fie un numar pozitiv");
      return;
    }
    setBusyId(product.id);
    try {
      await trackedProductsAPI.toggleMonitoring(product.id, true, parsed);
      setItems((prev) =>
        prev.map((p) =>
          p.id === product.id ? { ...p, monitoring_active: true, alert_threshold: parsed } : p
        )
      );
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la setarea alertei de pret");
    } finally {
      setBusyId(null);
    }
  };

  const removeItem = async (product) => {
    if (!window.confirm("Esti sigur ca vrei sa elimini acest produs din lista?")) return;
    setBusyId(product.id);
    try {
      await trackedProductsAPI.remove(product.id);
      setItems((prev) => prev.filter((p) => p.id !== product.id));
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la eliminare");
    } finally {
      setBusyId(null);
    }
  };

  const pillStyle = (active) => ({
    padding: "0.375rem 0.875rem",
    borderRadius: "999px",
    fontSize: "0.8125rem",
    fontWeight: 500,
    cursor: "pointer",
    border: "1px solid var(--border-color)",
    backgroundColor: active ? "var(--blue-dim)" : "transparent",
    color: active ? "var(--blue-light)" : "var(--text-secondary)",
    transition: "all 0.15s ease",
  });

  return (
    <div style={{ maxWidth: "1080px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <Heart style={{ width: "1.5rem", height: "1.5rem", color: "#f472b6" }} />
          Produse Urmarite
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.375rem", fontSize: "0.875rem" }}>
          Produsele tale salvate. Activeaza monitorizarea pentru a urmari evolutia pretului si a primi alerte.
        </p>
      </div>

      {/* Filtre rapide (pills) */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1.5rem" }}>
        {STATUS_FILTERS.map((f) => (
          <button key={f.value} onClick={() => setActiveFilter(f.value)} style={pillStyle(activeFilter === f.value)}>
            {f.label}
          </button>
        ))}
        <span style={{ width: "1px", backgroundColor: "var(--border-color)", margin: "0.25rem 0.25rem" }} />
        {SOURCE_FILTERS.map((f) => (
          <button key={f.value} onClick={() => setActiveFilter(f.value)} style={pillStyle(activeFilter === f.value)}>
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "8rem" }}>
          <div style={{ width: "2rem", height: "2rem", border: "3px solid var(--blue-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : filtered.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
          {filtered.map((product) => {
            const style = SOURCE_STYLES[product.source] || { bg: "rgba(148,163,184,0.2)", fg: "#cbd5e1" };
            const cur = product.currency || "RON";
            const hasDiscount = product.original_price != null && product.current_price != null && product.original_price > product.current_price;
            const draftValue = alertDrafts[product.id] !== undefined
              ? alertDrafts[product.id]
              : (product.alert_threshold ?? "");
            const busy = busyId === product.id;
            const history = Array.isArray(product.price_history)
              ? product.price_history.slice(-7).map((h) => Number(h?.price ?? h)).filter((n) => isFinite(n))
              : [];
            return (
              <div key={product.id} style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
                borderRadius: "0.75rem", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem",
              }}>
                {/* Imagine + nume */}
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Link href={`/dashboard/products/${product.id}`} style={{
                      fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", textDecoration: "none",
                      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                    }}>
                      {product.name}
                    </Link>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginTop: "0.375rem", flexWrap: "wrap" }}>
                      {product.source && (
                        <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: style.bg, color: style.fg }}>
                          {product.source}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Pret */}
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", flexWrap: "wrap" }}>
                  {product.current_price != null && (
                    <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "#4ade80" }}>
                      {product.current_price} {cur}
                    </span>
                  )}
                  {hasDiscount && (
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", textDecoration: "line-through" }}>
                      {product.original_price} {cur}
                    </span>
                  )}
                </div>

                {/* Categorie + subcategorie */}
                {(product.category || product.subcategory) && (
                  <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: 0 }}>
                    {[product.category, product.subcategory].filter(Boolean).join(" · ")}
                  </p>
                )}

                {/* Toggle monitorizare */}
                <button
                  type="button"
                  onClick={() => toggleMonitoring(product)}
                  disabled={busy}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: "0.5rem",
                    background: "transparent", border: "none", padding: 0,
                    cursor: busy ? "wait" : "pointer",
                  }}
                >
                  <span style={{
                    width: "36px", height: "20px", borderRadius: "999px", flexShrink: 0, position: "relative",
                    backgroundColor: product.monitoring_active ? "var(--green-primary)" : "var(--border-color)",
                    transition: "background-color 0.15s ease",
                  }}>
                    <span style={{
                      position: "absolute", top: "2px", left: product.monitoring_active ? "18px" : "2px",
                      width: "16px", height: "16px", borderRadius: "50%", backgroundColor: "#fff",
                      transition: "left 0.15s ease",
                    }} />
                  </span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 500, color: product.monitoring_active ? "#4ade80" : "var(--text-secondary)" }}>
                    {product.monitoring_active ? "Monitorizat activ" : "Monitorizare inactiva"}
                  </span>
                </button>

                {/* Sectiune monitorizare activa */}
                {product.monitoring_active && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-color)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      <Activity style={{ width: "13px", height: "13px" }} />
                      Pretul este verificat automat periodic
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                      <Bell style={{ width: "14px", height: "14px", color: "var(--text-secondary)" }} />
                      <input
                        type="number" step="0.01" min="0"
                        value={draftValue}
                        onChange={(e) => setAlertDrafts((prev) => ({ ...prev, [product.id]: e.target.value }))}
                        placeholder="Alerta pret"
                        style={{
                          flex: 1, minWidth: 0, backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                          borderRadius: "0.375rem", padding: "0.3125rem 0.5rem", color: "var(--text-primary)",
                          fontSize: "0.8125rem", outline: "none",
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => setAlert(product)}
                        disabled={busy}
                        style={{
                          padding: "0.3125rem 0.75rem", borderRadius: "0.375rem", backgroundColor: "var(--blue-primary)",
                          color: "var(--text-primary)", border: "none", cursor: busy ? "wait" : "pointer", fontSize: "0.75rem", fontWeight: 500,
                        }}
                      >
                        Seteaza
                      </button>
                    </div>
                    {/* Sparkline ultimele 7 preturi (daca exista price_history in date) */}
                    {history.length > 0 && (() => {
                      const max = Math.max(...history);
                      const min = Math.min(...history);
                      const range = max - min || 1;
                      return (
                        <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "32px" }}>
                          {history.map((pr, idx) => (
                            <div key={idx} style={{
                              flex: 1, height: `${6 + ((pr - min) / range) * 26}px`,
                              backgroundColor: "var(--blue-primary)", borderRadius: "2px", opacity: 0.7,
                            }} />
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                )}

                {/* Actiuni */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "auto", paddingTop: "0.5rem" }}>
                  {product.source_url ? (
                    <a href={product.source_url} target="_blank" rel="noopener noreferrer"
                      style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem", color: "var(--text-secondary)", textDecoration: "none" }}>
                      <ExternalLink style={{ width: "13px", height: "13px" }} /> Deschide sursa
                    </a>
                  ) : <span />}
                  <button
                    type="button"
                    onClick={() => removeItem(product)}
                    disabled={busy}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem",
                      backgroundColor: "transparent", border: "none", cursor: busy ? "wait" : "pointer", color: "#f87171",
                    }}
                  >
                    <Trash2 style={{ width: "13px", height: "13px" }} /> Elimina
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "3rem", textAlign: "center",
        }}>
          <Package style={{ width: "3rem", height: "3rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>
            Nu ai niciun produs salvat.
          </p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Adauga produse din{" "}
            <Link href="/dashboard/products" style={{ color: "var(--blue-light)", textDecoration: "none" }}>
              Descopera Oportunitati
            </Link>.
          </p>
        </div>
      )}
    </div>
  );
}
