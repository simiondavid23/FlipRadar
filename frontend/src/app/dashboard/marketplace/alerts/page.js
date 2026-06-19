"use client";
// FlipRadar — Modulul 1 Marketplace: alerte keyword (wizard 3 pasi).
import { useState, useEffect } from "react";
import { marketplaceAPI } from "@/lib/api";
import MarketplaceKeywordWizard from "@/components/MarketplaceKeywordWizard";
import { platformLabel } from "@/lib/marketplaceConstants";
import { Bell, Plus, Trash2, ToggleLeft, ToggleRight, Loader2, Car } from "lucide-react";

function filtersSummary(filters) {
  const f = filters || {};
  const parts = [];
  if (Array.isArray(f.condition) && f.condition.length) parts.push(f.condition.join("/"));
  if (f.price_min != null || f.price_max != null) parts.push(`${f.price_min ?? "?"}-${f.price_max ?? "?"} RON`);
  if (f.location_county) parts.push(f.location_county);
  if (f.location_city) parts.push(f.location_city);
  if (f.size) parts.push(`marime ${f.size}`);
  if (f.distance_km) parts.push(`${f.distance_km} km`);
  if (f.offer_type) parts.push(f.offer_type);
  if (f.plz) parts.push(`PLZ ${f.plz}`);
  if (f.radius_km) parts.push(`${f.radius_km} km`);
  return parts.join(" · ");
}

export default function MarketplaceAlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await marketplaceAPI.getKeywordAlerts();
      setAlerts(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (config) => {
    await marketplaceAPI.createKeywordAlert(config);
    setShowWizard(false);
    await load();
  };

  const toggle = async (a) => {
    try {
      const res = await marketplaceAPI.updateKeywordAlert(a.id, { is_active: !a.is_active });
      setAlerts((prev) => prev.map((x) => (x.id === a.id ? res.data : x)));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
    }
  };

  const remove = async (a) => {
    if (!confirm("Stergi alerta?")) return;
    try {
      await marketplaceAPI.deleteKeywordAlert(a.id);
      setAlerts((prev) => prev.filter((x) => x.id !== a.id));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere.");
    }
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", gap: "0.75rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Bell style={{ width: "22px", height: "22px", color: "#fbbf24" }} />
            Alerte Keyword
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Monitorizeaza automat anunturi noi pe platformele de marketplace
          </p>
        </div>
        <button onClick={() => setShowWizard(true)} style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem",
          backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem",
          fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
        }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Adauga alerta
        </button>
      </div>

      {/* Nota: cautarea de automobile se face din modulul dedicat Automobile. */}
      <div style={{
        display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1.25rem",
        padding: "0.625rem 0.875rem", borderRadius: "0.5rem", fontSize: "0.8125rem",
        backgroundColor: "rgba(37,99,235,0.08)", border: "1px solid rgba(37,99,235,0.25)", color: "var(--blue-light)",
      }}>
        <Car style={{ width: "16px", height: "16px", flexShrink: 0 }} />
        Pentru cautare de automobile foloseste modulul Automobile, iar pentru imobiliare foloseste modulul Imobiliare din meniu.
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : alerts.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)",
        }}>
          Nu ai alerte configurate. Apasa „Adauga alerta” ca sa incepi.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          {alerts.map((a) => {
            const summary = filtersSummary(a.filters);
            const cat = [a.category, a.subcategory].filter(Boolean).join(" › ");
            return (
              <div key={a.id} style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem",
                padding: "0.875rem 1rem", display: "flex", alignItems: "center", gap: "0.875rem", opacity: a.is_active ? 1 : 0.6,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.25rem" }}>
                    <span style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>{a.keyword}</span>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: "var(--blue-light)", backgroundColor: "var(--blue-dim)", padding: "0.0625rem 0.5rem", borderRadius: "0.375rem" }}>
                      {platformLabel(a.platform)}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {cat ? `${cat}` : ""}{cat && summary ? " · " : ""}{summary}
                    {!cat && !summary ? "Fara filtre suplimentare" : ""}
                  </div>
                </div>
                <button onClick={() => toggle(a)} title={a.is_active ? "Dezactiveaza" : "Activeaza"}
                  style={{ background: "none", border: "none", cursor: "pointer", color: a.is_active ? "#4ade80" : "var(--text-muted)", display: "flex" }}>
                  {a.is_active ? <ToggleRight style={{ width: "28px", height: "28px" }} /> : <ToggleLeft style={{ width: "28px", height: "28px" }} />}
                </button>
                <button onClick={() => remove(a)} title="Sterge"
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#f87171", display: "flex" }}>
                  <Trash2 style={{ width: "18px", height: "18px" }} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <MarketplaceKeywordWizard open={showWizard} onClose={() => setShowWizard(false)} onSubmit={handleCreate} />
    </div>
  );
}
