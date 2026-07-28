"use client";
import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { trackedProductsAPI } from "@/lib/api";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import { styleFor } from "@/lib/sourceStyles";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
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

export default function TrackedProductsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [activeFilter, setActiveFilter] = useState("all");
  // Valori draft pentru inputul "Alerta pret", per produs.
  const [alertDrafts, setAlertDrafts] = useState({});
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await trackedProductsAPI.getAll();
      setItems(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Tracked products error:", err);
      setLoadError("Nu am putut încărca datele. Reîncearcă.");
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

  const monitoredCount = items.filter((p) => p.monitoring_active).length;

  return (
    <div>
      <TopBar path={["CATALOG", "PRODUSE URMĂRITE"]} />

      <PageHeading
        icon={Heart}
        title="Produse Urmărite"
        subtitle={<>Produsele tale salvate — <Hl>{items.length} urmărite</Hl>, {monitoredCount} cu monitorizare activă.</>}
      />

      {/* Filtre rapide (pills) */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px", marginTop: "16px" }}>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setActiveFilter(f.value)}
            className={`tab-pill${activeFilter === f.value ? " active" : ""}`}
            style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
          >
            {activeFilter === f.value && <span className="pill-nav-dot" />}
            {f.label}
          </button>
        ))}
        <span style={{ width: "1px", height: "18px", background: "rgba(94,140,255,.16)", margin: "0 4px" }} />
        {SOURCE_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setActiveFilter(f.value)}
            className={`tab-pill${activeFilter === f.value ? " active" : ""}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <FeedErrorBanner message={loadError} onRetry={loadItems} />

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "8rem" }}>
          <div style={{ width: "2rem", height: "2rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : filtered.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(305px, 1fr))", gap: "14px", marginTop: "14px" }}>
          {filtered.map((product) => {
            const style = styleFor(product.source);
            const cur = product.currency || "RON";
            const hasDiscount = product.original_price != null && product.current_price != null && product.original_price > product.current_price;
            const draftValue = alertDrafts[product.id] !== undefined
              ? alertDrafts[product.id]
              : (product.alert_threshold ?? "");
            const busy = busyId === product.id;
            const history = Array.isArray(product.price_history)
              ? product.price_history.slice(-7).map((h) => Number(h?.price ?? h)).filter((n) => isFinite(n))
              : [];
            // RETAIL-4 — variatia fata de penultimul punct (istoricul vine ASC).
            // Sub 0.5% e zgomot de rotunjire, nu o miscare de pret.
            const variation = (() => {
              if (history.length < 2) return null;
              const prev = history[history.length - 2];
              const last = history[history.length - 1];
              if (!prev || prev === last) return null;
              const pct = ((last - prev) / prev) * 100;
              return Math.abs(pct) < 0.5 ? null : pct;
            })();
            // RETAIL-4 — pretul curent a atins deja pragul setat pe monitorizare.
            const underTarget = product.monitoring_active
              && product.alert_threshold != null
              && product.current_price != null
              && product.current_price <= product.alert_threshold;
            return (
              <div key={product.id} className="glass-panel lift-hover" style={{
                padding: "14px 16px", display: "flex", flexDirection: "column", gap: "10px",
              }}>
                {/* Imagine + nume */}
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Link href={`/dashboard/products/detail?id=${product.id}`} style={{
                      fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", textDecoration: "none",
                      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                      lineHeight: 1.35,
                    }}>
                      {product.name}
                    </Link>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginTop: "0.375rem", flexWrap: "wrap" }}>
                      {product.source && (
                        <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase", background: style.bg, border: `1px solid ${style.fg}55`, color: style.fg }}>
                          {product.source}
                        </span>
                      )}
                      {variation != null && (
                        <span style={{
                          padding: "2px 7px", borderRadius: "7px", fontFamily: "var(--font-mono)", fontSize: "9px", fontWeight: 700,
                          background: variation < 0 ? "rgba(74,222,128,0.14)" : "rgba(248,113,113,0.14)",
                          border: `1px solid ${variation < 0 ? "rgba(74,222,128,0.4)" : "rgba(248,113,113,0.4)"}`,
                          color: variation < 0 ? "#4ade80" : "#f87171",
                        }}>
                          {variation < 0 ? "▼" : "▲"} {variation > 0 ? "+" : ""}{variation.toFixed(1)}%
                        </span>
                      )}
                      {underTarget && (
                        <span style={{
                          padding: "2px 7px", borderRadius: "7px", fontFamily: "var(--font-mono)", fontSize: "9px", fontWeight: 700,
                          background: "rgba(74,222,128,0.14)", color: "#4ade80",
                          border: "1px solid rgba(74,222,128,0.45)",
                        }}>
                          Sub tinta
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Pret */}
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", flexWrap: "wrap" }}>
                  {product.current_price != null && (
                    <span style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-.4px", color: "#ffffff" }}>
                      {product.current_price} <span style={{ fontSize: "11.5px", fontWeight: 500, color: "var(--text-tertiary)" }}>{cur}</span>
                    </span>
                  )}
                  {hasDiscount && (
                    <span style={{ fontSize: "12px", color: "var(--text-muted)", textDecoration: "line-through" }}>
                      {product.original_price} {cur}
                    </span>
                  )}
                </div>

                {/* Categorie + subcategorie */}
                {(product.category || product.subcategory) && (
                  <p style={{ fontSize: "11.5px", color: "var(--text-dim)", margin: 0 }}>
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
                  <span className={`toggle-cyan${product.monitoring_active ? " on" : ""}`} aria-hidden="true" />
                  <span style={{ fontSize: "12px", fontWeight: 500, color: product.monitoring_active ? "#7ee7f8" : "var(--text-dim)" }}>
                    {product.monitoring_active ? "Monitorizat activ" : "Monitorizare inactiva"}
                  </span>
                </button>

                {/* Sectiune monitorizare activa */}
                {product.monitoring_active && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", paddingTop: "10px", borderTop: "1px solid rgba(94,140,255,.1)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--text-muted)" }}>
                      <Activity style={{ width: "13px", height: "13px" }} />
                      Pretul este verificat automat periodic
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                      <Bell style={{ width: "13px", height: "13px", color: "var(--text-mono)" }} strokeWidth={1.8} />
                      <input
                        type="number" step="0.01" min="0"
                        value={draftValue}
                        onChange={(e) => setAlertDrafts((prev) => ({ ...prev, [product.id]: e.target.value }))}
                        placeholder="Alerta pret"
                        style={{
                          flex: 1, minWidth: 0,
                          background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
                          border: "1px solid transparent",
                          borderRadius: "9px", padding: "6px 10px", color: "var(--text-primary)",
                          fontSize: "12px", fontFamily: "var(--font-sans)", outline: "none",
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => setAlert(product)}
                        disabled={busy}
                        className="btn-cyan"
                        style={{ padding: "6px 12px", borderRadius: "9px", fontSize: "11px" }}
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
                            // maxWidth: cu un singur punct, flex:1 ar intinde bara pe tot randul
                            <div key={idx} style={{
                              flex: 1, maxWidth: "26px", height: `${6 + ((pr - min) / range) * 26}px`,
                              background: "linear-gradient(180deg,#22d3ee,#2563eb)", borderRadius: "2px", opacity: 0.75,
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
                      style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-dim)", textDecoration: "none" }}>
                      <ExternalLink style={{ width: "13px", height: "13px" }} /> Deschide sursa
                    </a>
                  ) : <span />}
                  <button
                    type="button"
                    onClick={() => removeItem(product)}
                    disabled={busy}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px",
                      fontFamily: "var(--font-sans)",
                      background: "transparent", border: "none", cursor: busy ? "wait" : "pointer", color: "#f87171",
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
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Package style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 14px", color: "var(--text-mono)", display: "block" }} strokeWidth={1.5} />
          <p style={{ fontSize: "13px", color: "var(--text-primary)", marginBottom: "6px" }}>
            Nu ai niciun produs salvat.
          </p>
          <p style={{ fontSize: "12.5px", color: "var(--text-dim)" }}>
            Adauga produse din{" "}
            <Link href="/dashboard/products">Descopera Oportunitati</Link>.
          </p>
        </div>
      )}
    </div>
  );
}
