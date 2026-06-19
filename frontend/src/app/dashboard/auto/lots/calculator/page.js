"use client";
// FlipRadar — Automobile Loturi: calculator cost import (live, client-side).
import { useState, useMemo } from "react";
import { Calculator } from "lucide-react";

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };

const eur = (n) => `${Number(n || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EUR`;
const num = (v, d = 0) => { const n = parseFloat(v); return Number.isFinite(n) ? n : d; };

function Row({ label, value, sign = "+", strong, color }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", fontSize: strong ? "0.95rem" : "0.8125rem", fontWeight: strong ? 700 : 400, borderBottom: strong ? "none" : "1px solid var(--border-color)" }}>
      <span style={{ color: strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{label}</span>
      <span style={{ color: color || "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{sign ? `${sign} ` : ""}{eur(value)}</span>
    </div>
  );
}

export default function ImportCalculatorPage() {
  const [bidUsd, setBidUsd] = useState("");
  const [feePct, setFeePct] = useState("10");
  const [transport, setTransport] = useState("1200");
  const [repair, setRepair] = useState("0");
  const [registration, setRegistration] = useState("300");
  const [rate, setRate] = useState("0.92");
  const [resale, setResale] = useState("");

  const calc = useMemo(() => {
    const bid = num(bidUsd);
    const r = num(rate, 0.92);
    const bidEur = bid * r;
    const buyersFee = bidEur * (num(feePct, 10) / 100);
    const subtotal = bidEur + buyersFee + num(transport, 1200);
    const customs = subtotal * 0.065;
    const vat = (subtotal + customs) * 0.19;
    const total = subtotal + customs + vat + num(repair, 0) + num(registration, 300);
    return { bidEur, buyersFee, transport: num(transport, 1200), subtotal, customs, vat, repair: num(repair, 0), registration: num(registration, 300), total };
  }, [bidUsd, feePct, transport, repair, registration, rate]);

  const profit = num(resale) ? num(resale) - calc.total : null;

  return (
    <div style={{ maxWidth: "760px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Calculator style={{ width: "22px", height: "22px", color: "#2563eb" }} /> Calculator Import
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Estimeaza costul real de import al unui vehicul din licitatie (SUA → RO)
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem", alignItems: "start" }}>
        {/* Formular */}
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1.25rem", display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div><label style={lbl}>Pret bid (USD)</label><input type="number" value={bidUsd} onChange={(e) => setBidUsd(e.target.value)} placeholder="ex: 8000" style={inputStyle} autoFocus /></div>
          <div><label style={lbl}>Buyer&apos;s fee (%)</label><input type="number" value={feePct} onChange={(e) => setFeePct(e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Transport estimat (EUR)</label><input type="number" value={transport} onChange={(e) => setTransport(e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Cost reparatii (EUR)</label><input type="number" value={repair} onChange={(e) => setRepair(e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Cost inmatriculare (EUR)</label><input type="number" value={registration} onChange={(e) => setRegistration(e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Curs USD/EUR</label><input type="number" step="0.01" value={rate} onChange={(e) => setRate(e.target.value)} style={inputStyle} /></div>
        </div>

        {/* Rezultate */}
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1.25rem" }}>
          <h2 style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)", marginTop: 0, marginBottom: "0.75rem" }}>Defalcare costuri</h2>
          <Row label={`Pret bid (${num(bidUsd).toLocaleString("ro-RO")} USD)`} value={calc.bidEur} sign="=" />
          <Row label={`Buyer's fee (${num(feePct, 10)}%)`} value={calc.buyersFee} />
          <Row label="Transport" value={calc.transport} />
          <Row label="Subtotal inainte vama" value={calc.subtotal} sign="=" />
          <Row label="Taxa vamala (6.5%)" value={calc.customs} />
          <Row label="TVA (19%)" value={calc.vat} />
          <Row label="Cost reparatii" value={calc.repair} />
          <Row label="Inmatriculare" value={calc.registration} />
          <div style={{ borderTop: "2px solid var(--border-color)", marginTop: "0.375rem", paddingTop: "0.375rem" }}>
            <Row label="TOTAL COST REAL" value={calc.total} sign="=" strong color="#4ade80" />
          </div>

          <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px dashed var(--border-color)" }}>
            <label style={lbl}>Pret revanzare estimat (EUR)</label>
            <input type="number" value={resale} onChange={(e) => setResale(e.target.value)} placeholder="ex: 16000" style={inputStyle} />
            {profit != null && (
              <div style={{ marginTop: "0.625rem", display: "flex", justifyContent: "space-between", fontSize: "0.95rem", fontWeight: 700 }}>
                <span style={{ color: "var(--text-primary)" }}>Profit brut estimat</span>
                <span style={{ color: profit >= 0 ? "#4ade80" : "#f87171", fontVariantNumeric: "tabular-nums" }}>
                  {profit >= 0 ? "+" : ""}{eur(profit)}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`@media (max-width: 720px) { div[style*="grid-template-columns: 1fr 1fr"] { grid-template-columns: 1fr !important; } }`}</style>
    </div>
  );
}
