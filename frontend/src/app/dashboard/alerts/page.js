"use client";
import { useState, useEffect } from "react";
import { alertsAPI } from "@/lib/api";
import { Trash2, ToggleLeft, ToggleRight, BellOff, CheckCircle } from "lucide-react";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAlerts();
  }, []);

  const loadAlerts = async () => {
    try {
      const response = await alertsAPI.getAlerts();
      setAlerts(response.data);
    } catch (error) {
      console.error("Error loading alerts:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (alertId) => {
    try {
      await alertsAPI.toggleAlert(alertId);
      setAlerts(alerts.map((a) =>
        a.id === alertId ? { ...a, is_active: !a.is_active } : a
      ));
    } catch (error) {
      console.error("Error toggling alert:", error);
    }
  };

  const handleDelete = async (alertId) => {
    if (!confirm("Esti sigur ca vrei sa stergi aceasta alerta?")) return;
    try {
      await alertsAPI.deleteAlert(alertId);
      setAlerts(alerts.filter((a) => a.id !== alertId));
    } catch (error) {
      console.error("Error deleting alert:", error);
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>Alerte de Pret</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Gestioneaza alertele tale de pret ({alerts.length} alerte)
          </p>
        </div>
      </div>

      {alerts.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {alerts.map((alert) => (
            <div
              key={alert.id}
              style={{
                backgroundColor: "var(--bg-card)",
                border: alert.is_triggered ? "1px solid rgba(34,197,94,0.3)" : "1px solid var(--border-color)",
                borderRadius: "0.75rem",
                padding: "1.25rem",
                transition: "border-color 0.15s ease",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.375rem" }}>
                    <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "white", margin: 0 }}>
                      {alert.product?.name || `Produs #${alert.product_id}`}
                    </h3>
                    {alert.is_triggered && (
                      <span style={{
                        display: "inline-flex", alignItems: "center", gap: "0.25rem",
                        padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                        backgroundColor: "rgba(34,197,94,0.15)", color: "#4ade80",
                      }}>
                        <CheckCircle style={{ width: "10px", height: "10px" }} /> Declansata
                      </span>
                    )}
                    {!alert.is_active && !alert.is_triggered && (
                      <span style={{
                        padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                        backgroundColor: "rgba(148,163,184,0.15)", color: "#94a3b8",
                      }}>
                        Inactiva
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Pret tinta: <span style={{ color: "#facc15", fontWeight: 600 }}>{alert.target_price} {alert.currency || "EUR"}</span>
                    </span>
                    <span style={{
                      padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                      backgroundColor: alert.alert_type === "price_rise" ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)",
                      color: alert.alert_type === "price_rise" ? "#fca5a5" : "#60a5fa",
                    }}>
                      {alert.alert_type === "price_rise" ? "Crestere pret" : "Scadere pret"}
                    </span>
                  </div>
                  <p style={{ fontSize: "0.75rem", marginTop: "0.375rem", color: "var(--text-secondary)" }}>
                    Creata la: {new Date(alert.created_at).toLocaleDateString("ro-RO")}
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <button
                    onClick={() => handleToggle(alert.id)}
                    title={alert.is_active ? "Dezactiveaza" : "Activeaza"}
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent", border: "none", cursor: "pointer", transition: "all 0.15s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    {alert.is_active ? (
                      <ToggleRight style={{ width: "22px", height: "22px", color: "#4ade80" }} />
                    ) : (
                      <ToggleLeft style={{ width: "22px", height: "22px", color: "#64748b" }} />
                    )}
                  </button>
                  <button
                    onClick={() => handleDelete(alert.id)}
                    title="Sterge alerta"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent", border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(239,68,68,0.1)"; e.currentTarget.style.color = "#f87171"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                  >
                    <Trash2 style={{ width: "18px", height: "18px" }} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          padding: "3rem",
          textAlign: "center",
        }}>
          <BellOff style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1rem", color: "white", marginBottom: "0.375rem" }}>Nu ai alerte configurate</p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Alertele pot fi create din pagina de detalii a unui produs.
          </p>
        </div>
      )}
    </div>
  );
}
