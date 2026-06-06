"use client";
import { useEffect, useState } from "react";
import { reportsAPI } from "@/lib/api";
import {
  BarChart2, TrendingUp, Euro, ShoppingCart, Target, AlertTriangle,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend,
} from "recharts";

function StatCard({ title, value, icon: Icon, color, subtitle, valueColor }) {
  return (
    <div
      style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "1rem",
        padding: "1.25rem",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
        <div style={{
          padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: color,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <Icon style={{ width: "16px", height: "16px", color: "var(--text-primary)" }} />
        </div>
        <p style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)", margin: 0 }}>{title}</p>
      </div>
      <p style={{ fontSize: "1.75rem", fontWeight: 700, color: valueColor || "var(--text-primary)", lineHeight: 1, margin: 0 }}>
        {value}
      </p>
      {subtitle && (
        <p style={{ fontSize: "0.75rem", marginTop: "0.5rem", color: "var(--text-secondary)" }}>{subtitle}</p>
      )}
    </div>
  );
}

function toIsoDate(d) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function rangeForPreset(preset) {
  const today = new Date();
  const to = toIsoDate(today);
  const from = new Date(today);
  const days = preset === "7" ? 6 : preset === "30" ? 29 : preset === "90" ? 89 : 0;
  from.setDate(today.getDate() - days);
  return { date_from: toIsoDate(from), date_to: to };
}

export default function ReportsPage() {
  const [preset, setPreset] = useState("30");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []); // initial load with 30-day preset

  const load = async (params = null) => {
    setLoading(true);
    setError("");
    try {
      const effective = params ?? rangeForPreset(preset);
      const res = await reportsAPI.getSummary(effective);
      setSummary(res.data);
    } catch (e) {
      console.error(e);
      setError("Nu am putut incarca raportul. Incearca din nou.");
    } finally {
      setLoading(false);
    }
  };

  const handlePreset = (value) => {
    setPreset(value);
    if (value === "custom") return;
    load(rangeForPreset(value));
  };

  const handleApplyCustom = () => {
    if (!customFrom || !customTo) {
      setError("Selecteaza un interval complet pentru raport.");
      return;
    }
    load({ date_from: customFrom, date_to: customTo });
  };

  const presetBtn = (value, label) => {
    const active = preset === value;
    return (
      <button
        key={value}
        onClick={() => handlePreset(value)}
        style={{
          padding: "0.5rem 1rem", borderRadius: "0.5rem",
          backgroundColor: active ? "var(--blue-primary)" : "transparent",
          color: active ? "white" : "var(--text-secondary)",
          border: active ? "none" : "1px solid var(--border-color)",
          cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
        }}
      >
        {label}
      </button>
    );
  };

  const inputStyle = {
    backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
    fontSize: "0.8125rem", outline: "none",
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#9333ea", display: "flex" }}>
            <BarChart2 style={{ width: "20px", height: "20px", color: "var(--text-primary)" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Statistici & Profit
          </h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Analiza performantei portofoliului tau
        </p>
      </div>

      {/* Date range selector */}
      <div style={{
        backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-card)", padding: "1rem", marginBottom: "1.5rem",
        display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap",
      }}>
        {presetBtn("7", "7 zile")}
        {presetBtn("30", "30 zile")}
        {presetBtn("90", "90 zile")}
        {presetBtn("custom", "Custom")}
        {preset === "custom" && (
          <>
            <input
              type="date" value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              style={inputStyle}
            />
            <span style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>—</span>
            <input
              type="date" value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              style={inputStyle}
            />
            <button
              onClick={handleApplyCustom}
              style={{
                padding: "0.5rem 1rem", borderRadius: "0.5rem",
                backgroundColor: "var(--blue-primary)", color: "var(--text-primary)",
                border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              }}
            >
              Aplica
            </button>
          </>
        )}
      </div>

      {error && (
        <p style={{ color: "#f87171", fontSize: "0.8125rem", marginBottom: "1rem", padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239,68,68,0.1)" }}>
          {error}
        </p>
      )}

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid var(--blue-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : summary ? (
        <>
          {/* Stat cards 2x2 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
            <StatCard
              title="Venituri totale"
              value={`${(summary.venit_total || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR`}
              icon={Euro}
              color="#2563eb"
              subtitle="Suma incasarilor brute"
              valueColor="var(--blue-light)"
            />
            <StatCard
              title="Profit total"
              value={`${(summary.profit_total || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR`}
              icon={TrendingUp}
              color="#16a34a"
              subtitle="Dupa scaderea costurilor"
              valueColor={summary.profit_total >= 0 ? "#4ade80" : "#f87171"}
            />
            <StatCard
              title="ROI mediu"
              value={`${(summary.roi_mediu || 0).toFixed(2)}%`}
              icon={Target}
              color="#9333ea"
              subtitle="Marja medie pe vanzare"
              valueColor="#a78bfa"
            />
            <StatCard
              title="Nr. vanzari"
              value={summary.total_vanzari || 0}
              icon={ShoppingCart}
              color="#ca8a04"
              subtitle="Tranzactii inregistrate"
              valueColor="#facc15"
            />
          </div>

          {/* FlipRadar — ITEM 12: Rezumat Profitabilitate. KPI-urile (mai sus),
              tabelul "Top produse" si graficul pe categorii (mai jos) sunt deja
              randate; aici adaugam alerta pentru produsele cu marja mica. */}
          {(() => {
            const lowMargin = (summary.top_produse || []).filter((p) => Number(p.roi) < 10);
            if (lowMargin.length === 0) return null;
            return (
              <div style={{
                backgroundColor: "rgba(234,88,12,0.08)", border: "1px solid rgba(234,88,12,0.3)",
                borderLeft: "3px solid #ea580c", borderRadius: "1rem",
                padding: "1rem 1.25rem", marginBottom: "1.5rem",
                display: "flex", alignItems: "center", gap: "0.75rem",
              }}>
                <AlertTriangle style={{ width: "20px", height: "20px", color: "#fb923c", flexShrink: 0 }} />
                <div>
                  <p style={{ fontSize: "0.875rem", fontWeight: 600, color: "#fb923c", margin: 0 }}>
                    Atentie: verifica produsele cu marja mica
                  </p>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
                    {lowMargin.length} {lowMargin.length === 1 ? "produs are" : "produse au"} ROI sub 10% in intervalul selectat.
                  </p>
                </div>
              </div>
            );
          })()}

          {/* Time series chart */}
          <div
            style={{
              backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
              borderRadius: "1rem", padding: "1.5rem", marginBottom: "1.5rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                Evolutie venit si profit
              </h2>
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Valori in EUR</span>
            </div>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={summary.vanzari_pe_zi || []}>
                  <CartesianGrid stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="data" stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                    labelStyle={{ color: "var(--text-secondary)" }}
                    itemStyle={{ color: "var(--text-primary)" }}
                    formatter={(v, name) => [`${Number(v).toFixed(2)} EUR`, name === "venit" ? "Venit" : "Profit"]}
                  />
                  <Legend
                    iconType="circle"
                    formatter={(value) => value === "venit" ? "Venit" : "Profit"}
                    wrapperStyle={{ fontSize: "0.75rem" }}
                  />
                  <Line type="monotone" dataKey="venit" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="profit" stroke="#22c55e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Top categories bar chart + Top products table */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div
              style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
                borderRadius: "1rem", padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
                Top 5 categorii dupa profit
              </h2>
              <div style={{ width: "100%", height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={summary.top_categorii || []} layout="vertical" margin={{ top: 5, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-color)" horizontal={false} />
                    <XAxis type="number" stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis type="category" dataKey="categorie" stroke="var(--text-secondary)" fontSize={11} tickLine={false} axisLine={false} width={110} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                      labelStyle={{ color: "var(--text-secondary)" }}
                      itemStyle={{ color: "var(--text-primary)" }}
                      formatter={(v) => [`${Number(v).toFixed(2)} EUR`, "Profit"]}
                    />
                    <Bar dataKey="profit" fill="#9333ea" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {(!summary.top_categorii || summary.top_categorii.length === 0) && (
                <p style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: "0.8125rem", marginTop: "0.75rem" }}>
                  Nu exista vanzari in intervalul selectat.
                </p>
              )}
            </div>

            <div
              style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
                borderRadius: "1rem", padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
                Top 5 produse cele mai profitabile
              </h2>
              {(summary.top_produse || []).length === 0 ? (
                <p style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: "0.8125rem", paddingTop: "1rem" }}>
                  Nicio vanzare inregistrata in interval.
                </p>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: "0.5rem 0.375rem", color: "var(--text-secondary)", fontWeight: 600, borderBottom: "1px solid var(--border-color)" }}>Produs</th>
                      <th style={{ textAlign: "right", padding: "0.5rem 0.375rem", color: "var(--text-secondary)", fontWeight: 600, borderBottom: "1px solid var(--border-color)" }}>Profit</th>
                      <th style={{ textAlign: "right", padding: "0.5rem 0.375rem", color: "var(--text-secondary)", fontWeight: 600, borderBottom: "1px solid var(--border-color)" }}>ROI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.top_produse.map((p, i) => (
                      <tr key={i}>
                        <td style={{ padding: "0.625rem 0.375rem", color: "var(--text-primary)", borderBottom: "1px solid var(--border-color)" }}>
                          {p.name}
                        </td>
                        <td style={{ padding: "0.625rem 0.375rem", color: p.profit >= 0 ? "#4ade80" : "#f87171", fontWeight: 600, textAlign: "right", borderBottom: "1px solid var(--border-color)" }}>
                          {Number(p.profit).toFixed(2)} EUR
                        </td>
                        <td style={{ padding: "0.625rem 0.375rem", color: "var(--text-primary)", textAlign: "right", borderBottom: "1px solid var(--border-color)" }}>
                          {Number(p.roi).toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      ) : null}

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
