"use client";
// FlipRadar — Imobiliare: tab "Căutare Manuală" (migrat din real-estate/search).
// O SINGURĂ platformă selectată (pill-uri), spre deosebire de vechea pagină multi-select.
// Facebook Marketplace e exclus aici: endpoint-ul /api/real-estate/search îl apelează sincron
// (rupe asyncio.gather) — rămâne disponibil prin monitorizarea cu keyword.
import { useState, useMemo } from "react";
import { realEstateAPI, realEstateMonitorAPI } from "@/lib/api";
import RealEstateCard from "@/components/RealEstateCard";
import { TIP_ANUNT, TIP_PROPRIETATE, ROOMS, FACILITIES, JUDETE } from "@/lib/realEstateConstants";
import { Home, Loader2, SlidersHorizontal } from "lucide-react";

const PLATFORMS = [
  { value: "olx", label: "OLX Imobiliare" },
  { value: "storia", label: "Storia.ro" },
  { value: "imobiliare", label: "Imobiliare.ro" },
];

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.25rem" };
const liKey = (l) => `${l.platform}:${l.external_id || l.source_url}`;

function Chip({ active, onClick, children }) {
  return (
    <label onClick={onClick} style={{
      display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem", cursor: "pointer",
      padding: "0.3rem 0.625rem", borderRadius: "0.5rem", fontWeight: 600,
      color: active ? "var(--blue-light)" : "var(--text-secondary)",
      border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
      backgroundColor: active ? "var(--blue-dim)" : "transparent",
    }}>{children}</label>
  );
}

export default function REManualSearch() {
  const [platform, setPlatform] = useState("olx");   // SINGLE platform (pill-uri)
  const [tipAnunt, setTipAnunt] = useState("vanzare");
  const [tipProp, setTipProp] = useState("apartament");
  const [rooms, setRooms] = useState([]);
  const [pretMin, setPretMin] = useState("");
  const [pretMax, setPretMax] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [showAdv, setShowAdv] = useState(false);
  const [adv, setAdv] = useState({ suprafata_min: "", suprafata_max: "", etaj: "", an_min: "", judet: "", oras: "" });
  const [facilities, setFacilities] = useState([]);

  const [results, setResults] = useState(null);
  const [byPlatform, setByPlatform] = useState({});
  const [loading, setLoading] = useState(false);
  const [savedKeys, setSavedKeys] = useState(new Set());
  const [savingKey, setSavingKey] = useState(null);

  const toggleRoom = (r) => setRooms((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  const toggleFacility = (k) => setFacilities((prev) => (prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k]));
  const setA = (k, v) => setAdv((prev) => ({ ...prev, [k]: v }));

  const doSearch = async (e) => {
    e?.preventDefault();
    const roomNums = rooms.filter((r) => r !== "4+").map(Number);
    const has4 = rooms.includes("4+");
    const params = { platforms: platform, tip_anunt: tipAnunt, tip_proprietate: tipProp };
    if (rooms.length) {
      params.camere_min = Math.min(...roomNums, ...(has4 ? [4] : []));
      if (!has4 && roomNums.length) params.camere_max = Math.max(...roomNums);
    }
    if (pretMin) params.pret_min = parseFloat(pretMin);
    if (pretMax) params.pret_max = parseFloat(pretMax);
    const loc = adv.oras || adv.judet;
    if (loc) params.locatie = loc;
    if (adv.suprafata_min) params.suprafata_min = parseFloat(adv.suprafata_min);

    setLoading(true);
    setResults(null);
    try {
      const res = await realEstateAPI.search(params);
      setResults(res.data?.results || []);
      setByPlatform(res.data?.by_platform || {});
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la căutare.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Rafinare client-side pentru filtrele neaplicate uniform server-side.
  const shown = useMemo(() => {
    if (!results) return [];
    return results.filter((l) => {
      if (rooms.length && l.camere != null) {
        const match = rooms.some((r) => (r === "4+" ? l.camere >= 4 : Number(r) === l.camere));
        if (!match) return false;
      }
      if (adv.suprafata_max && l.suprafata_mp != null && Number(l.suprafata_mp) > parseFloat(adv.suprafata_max)) return false;
      if (adv.etaj && l.etaj && !String(l.etaj).toLowerCase().includes(adv.etaj.toLowerCase())) return false;
      if (adv.an_min && l.an_constructie && l.an_constructie < parseInt(adv.an_min)) return false;
      if (facilities.length && l.facilitati && Object.keys(l.facilitati).length) {
        for (const k of facilities) { if (!l.facilitati[k]) return false; }
      }
      return true;
    });
  }, [results, rooms, adv, facilities]);

  const handleSave = async (listing) => {
    const key = liKey(listing);
    setSavingKey(key);
    try {
      // IM-5: salvarea intra in tabelul monitor (status="saved") -> apare in Salvate & Ignorate.
      await realEstateMonitorAPI.saveManualListing(listing);
      setSavedKeys((prev) => new Set(prev).add(key));
    } catch (err) {
      alert(err.response?.data?.detail || "Eroare la salvare.");
    } finally { setSavingKey(null); }
  };

  return (
    <div>
      <form onSubmit={doSearch} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {/* Platformă — o singură selecție */}
        <div>
          <label style={lbl}>Platformă</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {PLATFORMS.map((p) => (
              <Chip key={p.value} active={platform === p.value} onClick={() => setPlatform(p.value)}>{p.label}</Chip>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.875rem", alignItems: "end" }}>
          <div>
            <label style={lbl}>Tip anunț</label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {TIP_ANUNT.map((t) => (
                <Chip key={t.value} active={tipAnunt === t.value} onClick={() => setTipAnunt(t.value)}>{t.label}</Chip>
              ))}
            </div>
          </div>
          <div>
            <label style={lbl}>Tip proprietate</label>
            <select value={tipProp} onChange={(e) => setTipProp(e.target.value)} style={inputStyle}>
              {TIP_PROPRIETATE.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Camere</label>
            <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
              {ROOMS.map((r) => (
                <Chip key={r} active={rooms.includes(r)} onClick={() => toggleRoom(r)}>{r}</Chip>
              ))}
            </div>
          </div>
          <div>
            <label style={lbl}>Preț ({currency})</label>
            <div style={{ display: "flex", gap: "0.375rem" }}>
              <input type="number" value={pretMin} onChange={(e) => setPretMin(e.target.value)} placeholder="min" style={inputStyle} />
              <input type="number" value={pretMax} onChange={(e) => setPretMax(e.target.value)} placeholder="max" style={inputStyle} />
              <select value={currency} onChange={(e) => setCurrency(e.target.value)} style={{ ...inputStyle, width: "auto" }}>
                <option value="EUR">EUR</option>
                <option value="RON">RON</option>
              </select>
            </div>
          </div>
        </div>

        <div>
          <button type="button" onClick={() => setShowAdv((s) => !s)}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.375rem 0.75rem", borderRadius: "0.5rem", border: "1px solid var(--border-color)", backgroundColor: "transparent", color: "var(--text-secondary)", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>
            <SlidersHorizontal style={{ width: "14px", height: "14px" }} /> Filtre avansate
          </button>
          {showAdv && (
            <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.75rem" }}>
                <div><label style={lbl}>Suprafață min (mp)</label><input type="number" value={adv.suprafata_min} onChange={(e) => setA("suprafata_min", e.target.value)} style={inputStyle} /></div>
                <div><label style={lbl}>Suprafață max (mp)</label><input type="number" value={adv.suprafata_max} onChange={(e) => setA("suprafata_max", e.target.value)} style={inputStyle} /></div>
                <div><label style={lbl}>Etaj</label><input value={adv.etaj} onChange={(e) => setA("etaj", e.target.value)} placeholder="ex: 2, parter" style={inputStyle} /></div>
                <div><label style={lbl}>An construcție min</label><input type="number" value={adv.an_min} onChange={(e) => setA("an_min", e.target.value)} placeholder="ex: 2000" style={inputStyle} /></div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.75rem" }}>
                <div><label style={lbl}>Județ</label>
                  <select value={adv.judet} onChange={(e) => setA("judet", e.target.value)} style={inputStyle}>
                    <option value="">Toate județele</option>
                    {JUDETE.map((j) => <option key={j} value={j}>{j}</option>)}
                  </select>
                </div>
                <div><label style={lbl}>Oraș</label><input value={adv.oras} onChange={(e) => setA("oras", e.target.value)} placeholder="ex: Cluj-Napoca" style={inputStyle} /></div>
              </div>
              <div>
                <label style={lbl}>Facilități</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                  {FACILITIES.map((fac) => (
                    <Chip key={fac.key} active={facilities.includes(fac.key)} onClick={() => toggleFacility(fac.key)}>{fac.label}</Chip>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div>
          <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.5rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600, cursor: "pointer" }}>
            <Home style={{ width: "16px", height: "16px" }} /> Caută
          </button>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem", margin: "0.5rem 0 0" }}>
            Anunțurile salvate apar în Salvate &amp; Ignorate.
          </p>
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
              {shown.length} anunțuri
              {Object.keys(byPlatform).length > 0 && ` (${Object.entries(byPlatform).map(([p, n]) => `${p}: ${n}`).join(", ")})`}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
              {shown.map((l, i) => (
                <RealEstateCard key={`${liKey(l)}-${i}`} listing={l} onSave={handleSave} isSaved={savedKeys.has(liKey(l))} busy={savingKey === liKey(l)} />
              ))}
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "2.5rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
            Niciun anunț găsit pentru filtrele selectate.
          </div>
        )
      )}
    </div>
  );
}
