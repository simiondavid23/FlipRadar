"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { reportsAPI, productsAPI } from "@/lib/api";
import {
  BarChart2, TrendingUp, Euro, ShoppingCart, Target, AlertTriangle,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend,
} from "recharts";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import KpiCard from "@/components/shared/KpiCard";

// Tooltip glass + axe mono, comune graficelor din pagina.
const tooltipStyle = {
  background: "rgba(4,9,18,.9)",
  backdropFilter: "blur(14px)",
  border: "1px solid rgba(34,211,238,.3)",
  borderRadius: "12px",
  fontSize: "11px",
  fontFamily: "var(--font-sans)",
  boxShadow: "0 12px 30px rgba(0,0,0,.5)",
};
const axisTick = { fill: "#2b3a5c", fontSize: 8, fontFamily: "var(--font-mono)" };

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
  const [lowRoiCount, setLowRoiCount] = useState(0);

  useEffect(() => {
    load();
  }, []); // initial load with 30-day preset

  // FlipRadar — B: numara produsele din CATALOG cu ROI <= 10% (filtrare server-side prin roi_max, GE-2).
  useEffect(() => {
    let active = true;
    productsAPI.getProducts({ roi_max: 10, limit: 500 })
      .then((res) => { if (active) setLowRoiCount((res.data || []).length); })
      .catch(() => { if (active) setLowRoiCount(0); });
    return () => { active = false; };
  }, []);

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
        className={`tab-pill${active ? " active" : ""}`}
      >
        {label}
      </button>
    );
  };

  const inputStyle = {
    background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
    border: "1px solid transparent",
    borderRadius: "10px", padding: "7px 11px", color: "var(--text-primary)",
    fontSize: "12px", fontFamily: "var(--font-sans)", outline: "none",
  };

  // Stiluri pentru tabelul "Top 3 produse dupa profit"
  const thLeft = { textAlign: "left", padding: "8px 6px", fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".15em", textTransform: "uppercase", color: "var(--text-mono)", fontWeight: 400, borderBottom: "1px solid rgba(94,140,255,.1)" };
  const thRight = { ...thLeft, textAlign: "right" };
  const tdLeft = { padding: "10px 6px", fontSize: "12.5px", color: "var(--text-secondary)", borderBottom: "1px solid rgba(94,140,255,.07)" };
  const tdRight = { ...tdLeft, textAlign: "right" };

  return (
    <div>
      <TopBar path={["GESTIUNE", "STATISTICI"]} />

      <PageHeading
        icon={BarChart2}
        title="Statistici & Profit"
        subtitle={summary
          ? <>Analiza performanței portofoliului tău — <Hl>{summary.total_vanzari || 0} vânzări</Hl> în interval.</>
          : "Analiza performanței portofoliului tău."}
      />

      {/* Date range selector */}
      <div className="glass-panel" style={{
        padding: "13px 15px", marginTop: "16px",
        display: "flex", alignItems: "center", gap: "9px", flexWrap: "wrap",
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
            <span style={{ color: "var(--text-mono)", fontSize: "12px" }}>—</span>
            <input
              type="date" value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              style={inputStyle}
            />
            <button onClick={handleApplyCustom} className="btn-cyan" style={{ padding: "8px 15px", borderRadius: "10px", fontSize: "12px" }}>
              Aplica
            </button>
          </>
        )}
      </div>

      {error && (
        <p style={{ color: "#f87171", fontSize: "12.5px", marginTop: "14px", padding: "11px 14px", borderRadius: "12px", background: "rgba(248,113,113,0.09)", border: "1px solid rgba(248,113,113,0.3)" }}>
          {error}
        </p>
      )}

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : summary ? (
        <>
          {/* FlipRadar — B: sectiunea "Rezumat Profitabilitate" (deasupra graficului pe zile) */}
          <h2 style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)", margin: "24px 0 0" }}>
            Rezumat Profitabilitate
          </h2>

          {/* 4 KPI cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(225px,1fr))", gap: "14px", marginTop: "14px" }}>
            <KpiCard
              idx="01"
              icon={Euro}
              label="Venituri totale"
              value={(summary.venit_total || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              unit="EUR"
              note="suma incasarilor brute"
            />
            <KpiCard
              idx="02"
              icon={TrendingUp}
              label="Profit total"
              value={(summary.profit_total || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              unit="EUR"
              chip={summary.vanzari_fara_cost > 0 ? `${summary.vanzari_fara_cost} fără cost` : null}
              chipTone="warn"
              note="dupa scaderea costurilor"
            />
            <KpiCard
              idx="03"
              icon={Target}
              label="ROI"
              value={(summary.roi_mediu || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              unit="%"
              note="profit / cost declarat"
            />
            <KpiCard
              idx="04"
              icon={ShoppingCart}
              label="Nr. vânzări"
              value={summary.total_vanzari || 0}
              note="tranzactii inregistrate"
            />
          </div>

          {/* FlipRadar — B: callout produse cu profit estimat sub 10% (link spre catalog filtrat) */}
          {lowRoiCount > 0 && (
            <Link
              href="/dashboard/products?roi_max=10"
              style={{
                display: "flex", alignItems: "center", gap: "12px", textDecoration: "none",
                background: "rgba(251,146,60,0.07)", border: "1px solid rgba(251,146,60,0.3)",
                borderLeft: "3px solid #fb923c", borderRadius: "14px",
                padding: "14px 18px", marginTop: "14px",
              }}
            >
              <AlertTriangle style={{ width: "20px", height: "20px", color: "#fb923c", flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: "13px", fontWeight: 600, color: "#fb923c", margin: 0 }}>
                  {lowRoiCount} {lowRoiCount === 1 ? "produs din catalog are" : "produse din catalog au"} profit estimat sub 10%
                </p>
                <p style={{ fontSize: "11.5px", color: "var(--text-dim)", margin: "4px 0 0" }}>
                  Vezi produsele cu marja mica si ajusteaza preturile de revanzare →
                </p>
              </div>
            </Link>
          )}

          {/* FlipRadar — B: Top 3 produse dupa profit + Categorii dupa ROI mediu */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginTop: "14px" }}>
            {/* Top 3 produse dupa profit */}
            <div className="glass-panel" style={{ padding: "18px" }}>
              <h2 style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                Top 3 produse dupa profit
              </h2>
              {(() => {
                const top3 = (summary.top_produse || []).slice(0, 3);
                if (top3.length === 0) {
                  return (
                    <p style={{ textAlign: "center", color: "var(--text-dim)", fontSize: "12.5px", paddingTop: "1rem" }}>
                      Nicio vanzare inregistrata in interval.
                    </p>
                  );
                }
                return (
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={thLeft}>Produs</th>
                        <th style={thRight}>Profit net</th>
                        <th style={thRight}>ROI%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top3.map((p, i) => (
                        <tr key={i}>
                          <td style={tdLeft}>{p.name}</td>
                          <td style={{ ...tdRight, color: p.profit >= 0 ? "#4ade80" : "#f87171", fontWeight: 600 }}>
                            {Number(p.profit).toFixed(2)} EUR
                          </td>
                          <td style={tdRight}>{Number(p.roi).toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              })()}
            </div>

            {/* Categorii dupa ROI mediu */}
            <div className="glass-panel" style={{ padding: "18px" }}>
              <h2 style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                Categorii dupa ROI mediu
              </h2>
              {(() => {
                const cats = [...(summary.top_categorii || [])]
                  .map((c) => ({ categorie: c.categorie, roi: Number(c.roi || 0) }))
                  .sort((a, b) => b.roi - a.roi);
                if (cats.length === 0) {
                  return (
                    <p style={{ textAlign: "center", color: "var(--text-dim)", fontSize: "12.5px", paddingTop: "1rem" }}>
                      Nu exista vanzari in intervalul selectat.
                    </p>
                  );
                }
                return (
                  <div style={{ width: "100%", height: 240 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cats} layout="vertical" margin={{ top: 5, right: 28, left: 0, bottom: 0 }}>
                        <CartesianGrid stroke="rgba(94,140,255,.07)" strokeDasharray="4 6" horizontal={false} />
                        <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} unit="%" />
                        <YAxis type="category" dataKey="categorie" tick={{ fill: "#7d90b5", fontSize: 10, fontFamily: "var(--font-sans)" }} tickLine={false} axisLine={false} width={110} />
                        <Tooltip
                          contentStyle={tooltipStyle}
                          labelStyle={{ color: "#41547a", fontSize: "10px" }}
                          itemStyle={{ color: "var(--text-primary)" }}
                          formatter={(v) => [`${Number(v).toFixed(2)}%`, "ROI mediu"]}
                        />
                        {/* maxBarSize: cu o singura categorie bara ar umple toata banda si ar arata ca un bloc */}
                        <Bar dataKey="roi" fill="#22d3ee" fillOpacity={0.75} radius={[0, 4, 4, 0]} maxBarSize={22} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                );
              })()}
            </div>
          </div>

          {/* Time series chart */}
          <div className="glass-panel" style={{ padding: "18px", marginTop: "14px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
              <h2 style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                Evolutie venit si profit
              </h2>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".13em", color: "var(--text-mono)" }}>VALORI ÎN EUR</span>
            </div>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={summary.vanzari_pe_zi || []}>
                  <CartesianGrid stroke="rgba(94,140,255,.07)" strokeDasharray="4 6" vertical={false} />
                  <XAxis dataKey="data" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis tick={axisTick} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: "#41547a", fontSize: "10px" }}
                    itemStyle={{ color: "var(--text-primary)" }}
                    formatter={(v, name) => [`${Number(v).toFixed(2)} EUR`, name === "venit" ? "Venit" : "Profit"]}
                  />
                  <Legend
                    iconType="circle"
                    formatter={(value) => value === "venit" ? "Venit" : "Profit"}
                    wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".1em", textTransform: "uppercase" }}
                  />
                  <Line type="monotone" dataKey="venit" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="profit" stroke="#2563eb" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
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
