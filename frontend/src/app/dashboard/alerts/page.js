"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { alertsAPI } from "@/lib/api";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import { Trash2, Bell, BellOff, CheckCircle } from "lucide-react";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAlerts();
  }, []);

  const loadAlerts = async () => {
    try {
      const response = await alertsAPI.getAlerts();
      setAlerts(response.data);
      setError(null);
    } catch (err) {
      console.error("Error loading alerts:", err);
      setError("Nu am putut incarca alertele. Reincearca.");
    } finally {
      setLoading(false);
    }
  };

  // Dupa toggle/delete reincarcam din server (fara update optimist cu closure stale).
  const handleToggle = async (alertId) => {
    try {
      await alertsAPI.toggleAlert(alertId);
      await loadAlerts();
    } catch (err) {
      console.error("Error toggling alert:", err);
      setError("Nu am putut actualiza alerta. Reincearca.");
    }
  };

  const handleDelete = async (alertId) => {
    if (!confirm("Esti sigur ca vrei sa stergi aceasta alerta?")) return;
    try {
      await alertsAPI.deleteAlert(alertId);
      await loadAlerts();
    } catch (err) {
      console.error("Error deleting alert:", err);
      setError("Nu am putut sterge alerta. Reincearca.");
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const triggeredCount = alerts.filter((a) => a.is_triggered).length;

  return (
    <div>
      <TopBar path={["MONITORIZARE", "ALERTE PREȚ"]} />

      <PageHeading
        icon={Bell}
        title="Alerte de Preț"
        subtitle={<>Gestionează alertele tale de preț — <Hl>{alerts.length} alerte</Hl>, {triggeredCount} declanșate.</>}
      />

      <FeedErrorBanner message={error} onRetry={loadAlerts} />

      {alerts.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "16px" }}>
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="glass-panel"
              style={{
                border: alert.is_triggered ? "1px solid rgba(74,222,128,0.45)" : "1px solid rgba(94,140,255,.13)",
                boxShadow: alert.is_triggered
                  ? "inset 0 1px 0 rgba(255,255,255,.05), 0 0 22px rgba(74,222,128,.1)"
                  : "inset 0 1px 0 rgba(255,255,255,.05)",
                padding: "16px 18px",
                transition: "all 0.15s ease",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.375rem" }}>
                    <Link
                      href={`/dashboard/products/detail?id=${alert.product_id}`}
                      className="row-link"
                      style={{ textDecoration: "none", color: "inherit", display: "inline-flex", alignItems: "center" }}
                    >
                      <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                        {alert.product?.name || `Produs #${alert.product_id}`}
                      </h3>
                    </Link>
                    {alert.is_triggered && (
                      <span style={{
                        display: "inline-flex", alignItems: "center", gap: "4px",
                        padding: "2.5px 8px", borderRadius: "7px",
                        fontFamily: "var(--font-mono)", fontSize: "8.5px", fontWeight: 700, letterSpacing: ".08em",
                        background: "rgba(74,222,128,0.14)", border: "1px solid rgba(74,222,128,0.45)", color: "#4ade80",
                      }}>
                        <CheckCircle style={{ width: "9px", height: "9px" }} strokeWidth={2.4} /> DECLANȘATĂ
                      </span>
                    )}
                    {!alert.is_active && !alert.is_triggered && (
                      <span style={{
                        padding: "2.5px 8px", borderRadius: "7px",
                        fontFamily: "var(--font-mono)", fontSize: "8.5px", fontWeight: 700, letterSpacing: ".08em",
                        background: "rgba(148,163,184,0.12)", border: "1px solid rgba(148,163,184,0.3)", color: "var(--text-dim)",
                      }}>
                        INACTIVĂ
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
                      Pret tinta: <span style={{ color: "#fde047", fontWeight: 600 }}>{alert.target_price} {alert.currency || "EUR"}</span>
                    </span>
                    {alert.product && alert.product.current_price != null && (
                      <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
                        Curent: <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{alert.product.current_price} {alert.product.currency}</span>
                      </span>
                    )}
                    <span style={{
                      padding: "2.5px 8px", borderRadius: "7px",
                      fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase",
                      background: alert.alert_type === "price_rise" ? "rgba(248,113,113,0.14)" : "rgba(37,99,235,0.14)",
                      border: `1px solid ${alert.alert_type === "price_rise" ? "rgba(248,113,113,0.4)" : "rgba(37,99,235,0.4)"}`,
                      color: alert.alert_type === "price_rise" ? "#fca5a5" : "#8fb5f7",
                    }}>
                      {alert.alert_type === "price_rise" ? "Crestere pret" : "Scadere pret"}
                    </span>
                  </div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".08em", marginTop: "8px", color: "var(--text-mono)" }}>
                    Creata la: {new Date(alert.created_at).toLocaleDateString("ro-RO")}
                  </p>
                  {alert.is_triggered && alert.triggered_at && (
                    <p style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".08em", marginTop: "3px", color: "#4ade80" }}>
                      Declansata la {new Date(alert.triggered_at).toLocaleString("ro-RO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <button
                    onClick={() => handleToggle(alert.id)}
                    title={alert.is_triggered ? "Rearmeaza" : alert.is_active ? "Dezactiveaza" : "Activeaza"}
                    className={`toggle-cyan${alert.is_active ? " on" : ""}`}
                  />
                  <button
                    onClick={() => handleDelete(alert.id)}
                    title="Sterge alerta"
                    className="btn-icon danger"
                  >
                    <Trash2 style={{ width: "13px", height: "13px" }} strokeWidth={1.8} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "16px" }}>
          <BellOff style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 14px", color: "var(--text-mono)", display: "block" }} strokeWidth={1.5} />
          <p style={{ fontSize: "13px", color: "var(--text-primary)", marginBottom: "6px" }}>Nu ai alerte configurate</p>
          <p style={{ fontSize: "12.5px", color: "var(--text-dim)" }}>
            Alertele pot fi create din pagina de detalii a unui produs.
          </p>
        </div>
      )}
    </div>
  );
}
