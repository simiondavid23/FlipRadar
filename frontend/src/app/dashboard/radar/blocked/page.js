"use client";
import { useState, useEffect } from "react";
import { radarAPI } from "@/lib/api";
import { ShieldOff, Trash2 } from "lucide-react";

export default function BlockedSellersPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const r = await radarAPI.getBlockedSellers();
      setItems(r.data || []);
    } catch (e) {
      console.error("[BlockedSellers]", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const unblock = async (id) => {
    if (!confirm("Deblochezi acest vânzător? Anunțurile lui vor reapărea în feed.")) return;
    try {
      await radarAPI.unblockSeller(id);
      setItems(items.filter((x) => x.id !== id));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la deblocare.");
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
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <ShieldOff style={{ width: "22px", height: "22px", color: "#f87171" }} />
          Vânzători Blocați
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Anunțurile lor sunt ignorate automat la scanare.
        </p>
      </div>

      {items.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "2.5rem",
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          color: "var(--text-secondary)",
        }}>
          Nu ai blocat niciun vânzător.
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          overflow: "hidden",
        }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)" }}>
                  <th style={th}>Vânzător</th>
                  <th style={th}>Platformă</th>
                  <th style={th}>Data blocării</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                    <td style={td}>{s.seller_name || s.seller_id}</td>
                    <td style={td}>{s.platform.toUpperCase()}</td>
                    <td style={td}>{s.blocked_at ? new Date(s.blocked_at).toLocaleString("ro-RO") : "-"}</td>
                    <td style={td}>
                      <button
                        onClick={() => unblock(s.id)}
                        style={{
                          padding: "0.375rem 0.75rem",
                          backgroundColor: "rgba(22,163,74,0.15)",
                          color: "#4ade80",
                          border: "1px solid rgba(22,163,74,0.3)",
                          borderRadius: "0.375rem",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                        }}
                      >
                        <Trash2 style={{ width: "12px", height: "12px" }} />
                        Deblochează
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

const th = { textAlign: "left", padding: "0.625rem 0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" };
const td = { padding: "0.625rem 0.75rem", color: "var(--text-primary)" };
