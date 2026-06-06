"use client";
// FlipRadar — ITEM 16: pagina de setari utilizator cu pragul pentru alertele Flash Deal.
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { usersAPI } from "@/lib/api";
import { Zap, Save } from "lucide-react";

// Pragul se stocheaza ca fractie (0.05-0.50) in backend; UI-ul lucreaza in procente (5-30).
function thresholdToPct(value) {
  const pct = Math.round((Number(value) || 0.15) * 100);
  if (pct < 5) return 5;
  if (pct > 30) return 30;
  return Math.round(pct / 5) * 5;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const [enabled, setEnabled] = useState(true);
  const [pct, setPct] = useState(15);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (user && user.flash_deal_threshold != null) {
      setPct(thresholdToPct(user.flash_deal_threshold));
    }
  }, [user]);

  const handleSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      await usersAPI.updateSettings({ flash_deal_threshold: pct / 100 });
      setMsg("Setarile au fost salvate.");
      setTimeout(() => setMsg(""), 3000);
    } catch (error) {
      setMsg(error.response?.data?.detail || "Eroare la salvarea setarilor.");
    } finally {
      setSaving(false);
    }
  };

  const cardStyle = {
    backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
    borderRadius: "1rem", padding: "1.5rem",
  };

  return (
    <div style={{ maxWidth: "720px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#ea580c", display: "flex" }}>
            <Zap style={{ width: "20px", height: "20px", color: "var(--text-primary)" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Setari</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Preferintele contului tau
        </p>
      </div>

      {/* Flash Deal section */}
      <div style={cardStyle}>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
          Alerte Flash Deal
        </h2>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
          Vei fi notificat cand un produs din catalogul tau sau din Radar Preturi scade cu cel putin {pct}%
          intr-o singura verificare automata.
        </p>

        {/* Toggle "Primesc alerte Flash Deal" */}
        <label style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "1.25rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            style={{ width: "18px", height: "18px", cursor: "pointer", accentColor: "#ea580c" }}
          />
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 500 }}>
            Primesc alerte Flash Deal
          </span>
        </label>

        {/* Range prag */}
        <div style={{ opacity: enabled ? 1 : 0.5, pointerEvents: enabled ? "auto" : "none" }}>
          <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)", marginBottom: "0.625rem" }}>
            Prag minim scadere pret: <strong style={{ color: "#fb923c" }}>{pct}%</strong>
          </label>
          <input
            type="range"
            min={5}
            max={30}
            step={5}
            value={pct}
            onChange={(e) => setPct(parseInt(e.target.value, 10))}
            disabled={!enabled}
            style={{ width: "100%", accentColor: "#ea580c", cursor: enabled ? "pointer" : "not-allowed" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            <span>5%</span><span>15%</span><span>30%</span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem", marginTop: "1.5rem" }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              display: "flex", alignItems: "center", gap: "0.5rem",
              padding: "0.625rem 1.25rem", borderRadius: "0.625rem",
              backgroundColor: saving ? "var(--bg-elevated)" : "#ea580c",
              color: "white", border: "none", cursor: saving ? "wait" : "pointer",
              fontSize: "0.875rem", fontWeight: 600,
            }}
          >
            <Save style={{ width: "16px", height: "16px" }} />
            {saving ? "Se salveaza..." : "Salveaza"}
          </button>
          {msg && (
            <span style={{ fontSize: "0.8125rem", color: msg.includes("salvate") ? "#4ade80" : "#f87171" }}>
              {msg}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
