"use client";
// FlipRadar — Automobile Anunturi: Piata Auto (cautare anunturi).
import { useState, useMemo } from "react";
import { autoAPI } from "@/lib/api";
import AutoListingCard from "@/components/AutoListingCard";
import AutoAiModal from "@/components/AutoAiModal";
import { Car, Loader2 } from "lucide-react";

const PLATFORMS = [
  { value: "olx_auto", label: "OLX Auto" },
  { value: "autovit", label: "AutoVit" },
  { value: "mobile_de", label: "Mobile.de" },
  { value: "autoscout24", label: "AutoScout24" },
  { value: "facebook_auto", label: "FB Marketplace Auto" },
  { value: "kleinanzeigen_auto", label: "eBay KA Auto" },
];
const FUELS = [["", "Toate"], ["benzina", "Benzina"], ["diesel", "Diesel"], ["hibrid", "Hibrid"], ["electric", "Electric"]];
const GEARBOXES = [["", "Toate"], ["manuala", "Manuala"], ["automata", "Automata"]];

// MODIFICARE 14 — badge avertisment Mobile.de (functioneaza doar de pe IP rezidential).
function MobileDeWarning() {
  return (
    <span
      title="Funcționează doar de pe IP rezidential. Pe server sau datacenter returnează 403 (blocat Imperva). 0 rezultate pe server = comportament normal."
      style={{
        marginLeft: "0.375rem", fontSize: "10px", padding: "0.125rem 0.4rem",
        borderRadius: "4px", background: "var(--bg-warning)", color: "var(--text-warning)",
        verticalAlign: "middle", cursor: "help", fontWeight: 500,
      }}
    >
      ⚠ IP local
    </span>
  );
}

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.25rem" };
const liKey = (l) => `${l.platform}:${l.external_id || l.source_url}`;

export default function AutoListingsSearchPage() {
  const [selected, setSelected] = useState(["olx_auto", "autovit"]);
  const [f, setF] = useState({ make: "", model: "", year_min: "", year_max: "", km_max: "", fuel: "", gearbox: "", price_min: "", price_max: "" });
  const [results, setResults] = useState(null);
  const [byPlatform, setByPlatform] = useState({});
  const [loading, setLoading] = useState(false);
  const [savedKeys, setSavedKeys] = useState(new Set());
  const [savingKey, setSavingKey] = useState(null);
  const [aiListing, setAiListing] = useState(null);

  const toggle = (p) => setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  const set = (k, v) => setF((prev) => ({ ...prev, [k]: v }));

  const doSearch = async (e) => {
    e?.preventDefault();
    if (selected.length === 0) { alert("Selecteaza cel putin o platforma."); return; }
    const q = `${f.make} ${f.model}`.trim();
    const filters = {};
    if (f.make) filters.make = f.make;
    if (f.model) filters.model = f.model;
    if (f.year_min) filters.year_min = parseInt(f.year_min);
    if (f.price_min) filters.price_min = parseFloat(f.price_min);
    if (f.price_max) filters.price_max = parseFloat(f.price_max);
    if (f.km_max) filters.km_max = parseInt(f.km_max);

    setLoading(true);
    setResults(null);
    try {
      const res = await autoAPI.searchListings(q, selected.join(","), filters);
      setResults(res.data?.results || []);
      setByPlatform(res.data?.by_platform || {});
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la cautare.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Filtrare client-side suplimentara (combustibil/cutie/km/an/pret nu sunt
  // aplicate uniform server-side de toate scraperele).
  const shown = useMemo(() => {
    if (!results) return [];
    return results.filter((l) => {
      if (f.fuel && l.engine_type !== f.fuel) return false;
      if (f.gearbox && l.gearbox !== f.gearbox) return false;
      if (f.year_min && l.year && l.year < parseInt(f.year_min)) return false;
      if (f.year_max && l.year && l.year > parseInt(f.year_max)) return false;
      if (f.km_max && l.km && l.km > parseInt(f.km_max)) return false;
      if (f.price_min && l.pret != null && l.pret < parseFloat(f.price_min)) return false;
      if (f.price_max && l.pret != null && l.pret > parseFloat(f.price_max)) return false;
      return true;
    });
  }, [results, f]);

  const handleSave = async (listing) => {
    const key = liKey(listing);
    setSavingKey(key);
    try {
      await autoAPI.saveListing(listing);
      setSavedKeys((prev) => new Set(prev).add(key));
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la salvare.");
    } finally { setSavingKey(null); }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Car style={{ width: "22px", height: "22px", color: "#2563eb" }} /> Piata Auto
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Cauta anunturi auto pe OLX Auto, AutoVit, Mobile.de, AutoScout24 si altele
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
                  {p.value === "mobile_de" && <MobileDeWarning />}
                </label>
              );
            })}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "0.75rem" }}>
          <div><label style={lbl}>Marca</label><input value={f.make} onChange={(e) => set("make", e.target.value)} placeholder="ex: Audi" style={inputStyle} /></div>
          <div><label style={lbl}>Model</label><input value={f.model} onChange={(e) => set("model", e.target.value)} placeholder="ex: A4" style={inputStyle} /></div>
          <div><label style={lbl}>An min</label><input type="number" value={f.year_min} onChange={(e) => set("year_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>An max</label><input type="number" value={f.year_max} onChange={(e) => set("year_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Km max</label><input type="number" value={f.km_max} onChange={(e) => set("km_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Combustibil</label>
            <select value={f.fuel} onChange={(e) => set("fuel", e.target.value)} style={inputStyle}>
              {FUELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div><label style={lbl}>Cutie</label>
            <select value={f.gearbox} onChange={(e) => set("gearbox", e.target.value)} style={inputStyle}>
              {GEARBOXES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div><label style={lbl}>Pret min (EUR)</label><input type="number" value={f.price_min} onChange={(e) => set("price_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={lbl}>Pret max (EUR)</label><input type="number" value={f.price_max} onChange={(e) => set("price_max", e.target.value)} style={inputStyle} /></div>
        </div>

        <div>
          <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600, cursor: "pointer" }}>
            <Car style={{ width: "16px", height: "16px" }} /> Cauta
          </button>
        </div>
      </form>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : results != null && (
        shown.length > 0 ? (
          <>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
              {shown.length} anunturi
              {Object.keys(byPlatform).length > 0 && ` (${Object.entries(byPlatform).map(([p, n]) => `${p}: ${n}`).join(", ")})`}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
              {shown.map((l, i) => (
                <AutoListingCard key={`${liKey(l)}-${i}`} listing={l} onSave={handleSave} onAnalyze={setAiListing} isSaved={savedKeys.has(liKey(l))} busy={savingKey === liKey(l)} />
              ))}
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "2.5rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
            Niciun anunt gasit pentru filtrele selectate.
          </div>
        )
      )}

      <AutoAiModal open={!!aiListing} onClose={() => setAiListing(null)} listing={aiListing} />
    </div>
  );
}
