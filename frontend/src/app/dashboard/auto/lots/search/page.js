"use client";
// FlipRadar — Automobile Loturi: cautare loturi licitatie.
import { useState } from "react";
import { autoAPI } from "@/lib/api";
import AutoLotCard from "@/components/AutoLotCard";
import { Search, Loader2 } from "lucide-react";

const PLATFORMS = [
  { value: "copart", label: "Copart" },
  { value: "iaai", label: "IAAI" },
  { value: "sca", label: "SCA Auctions" },
  { value: "openlane", label: "OpenLane" },
];
const DAMAGE_OPTIONS = ["", "FRONT_END", "REAR_END", "SIDE", "ROLLOVER", "FIRE", "FLOOD", "MECHANICAL", "MINOR"];

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.25rem" };
const lotKey = (l) => `${l.platform}:${l.lot_number || l.source_url}`;

export default function AutoLotsSearchPage() {
  const [selected, setSelected] = useState(["copart", "iaai"]);
  const [f, setF] = useState({ make: "", model: "", year_min: "", year_max: "", bid_min: "", bid_max: "", damage: "" });
  const [results, setResults] = useState(null);
  const [byPlatform, setByPlatform] = useState({});
  const [loading, setLoading] = useState(false);
  const [savedKeys, setSavedKeys] = useState(new Set());
  const [savingKey, setSavingKey] = useState(null);

  const toggle = (p) => setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  const set = (k, v) => setF((prev) => ({ ...prev, [k]: v }));

  const doSearch = async (e) => {
    e?.preventDefault();
    if (selected.length === 0) { alert("Selecteaza cel putin o platforma."); return; }
    const q = `${f.make} ${f.model}`.trim();
    const filters = {};
    if (f.make) filters.make = [f.make];
    if (f.model) filters.model = [f.model];
    if (f.year_min) filters.year_min = parseInt(f.year_min);
    if (f.year_max) filters.year_max = parseInt(f.year_max);
    if (f.bid_min) filters.bid_min = parseFloat(f.bid_min);
    if (f.bid_max) filters.bid_max = parseFloat(f.bid_max);
    if (f.damage) filters.damage = f.damage;

    setLoading(true);
    setResults(null);
    try {
      const res = await autoAPI.searchLots(q, selected.join(","), filters);
      setResults(res.data?.results || []);
      setByPlatform(res.data?.by_platform || {});
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la cautare.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (lot) => {
    const key = lotKey(lot);
    setSavingKey(key);
    try {
      await autoAPI.saveLot(lot);
      setSavedKeys((prev) => new Set(prev).add(key));
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Search style={{ width: "22px", height: "22px", color: "#0a4d8c" }} /> Cauta Loturi
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Loturi din licitatiile auto din SUA (date publice)
        </p>
      </div>

      <form onSubmit={doSearch} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.875rem" }}>
        <div>
          <label style={lbl}>Platforme</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {PLATFORMS.map((p) => {
              const active = selected.includes(p.value);
              return (
                <label key={p.value} style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem", cursor: "pointer", padding: "0.3rem 0.625rem", borderRadius: "0.5rem", fontWeight: 600, color: active ? "var(--blue-light)" : "var(--text-secondary)", border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`, backgroundColor: active ? "var(--blue-dim)" : "transparent" }}>
                  <input type="checkbox" checked={active} onChange={() => toggle(p.value)} style={{ display: "none" }} /> {p.label}
                </label>
              );
            })}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "0.75rem" }}>
          <div><label style={lbl}>Marca</label><input value={f.make} onChange={(e) => set("make", e.target.value)} placeholder="ex: BMW" style={inputStyle} /></div>
          <div><label style={lbl}>Model</label><input value={f.model} onChange={(e) => set("model", e.target.value)} placeholder="ex: X5" style={inputStyle} /></div>
          <div><label style={lbl}>An min</label><input type="number" value={f.year_min} onChange={(e) => set("year_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>An max</label><input type="number" value={f.year_max} onChange={(e) => set("year_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Bid min (USD)</label><input type="number" value={f.bid_min} onChange={(e) => set("bid_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Bid max (USD)</label><input type="number" value={f.bid_max} onChange={(e) => set("bid_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Tip daune</label>
            <select value={f.damage} onChange={(e) => set("damage", e.target.value)} style={inputStyle}>
              {DAMAGE_OPTIONS.map((d) => <option key={d} value={d}>{d || "Toate"}</option>)}
            </select>
          </div>
        </div>

        <div>
          <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600, cursor: "pointer" }}>
            <Search style={{ width: "16px", height: "16px" }} /> Cauta
          </button>
        </div>
      </form>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : results != null && (
        results.length > 0 ? (
          <>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
              {results.length} loturi gasite
              {Object.keys(byPlatform).length > 0 && ` (${Object.entries(byPlatform).map(([p, n]) => `${p}: ${n}`).join(", ")})`}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1rem" }}>
              {results.map((lot, i) => (
                <AutoLotCard key={`${lotKey(lot)}-${i}`} lot={lot} onSave={handleSave} isSaved={savedKeys.has(lotKey(lot))} busy={savingKey === lotKey(lot)} />
              ))}
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "2.5rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
            Niciun lot gasit. Incearca alta marca/model sau alte platforme.
          </div>
        )
      )}
    </div>
  );
}
