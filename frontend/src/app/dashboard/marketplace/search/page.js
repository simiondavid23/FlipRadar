"use client";
// FlipRadar — Modulul 1 Marketplace: cautare anunturi live pe mai multe platforme.
import { useState, useMemo } from "react";
import { marketplaceAPI } from "@/lib/api";
import MarketplaceListingCard from "@/components/MarketplaceListingCard";
import {
  MARKETPLACE_PLATFORMS, CONDITION_BY_PLATFORM, FACEBOOK_DISTANCES,
  KLEIN_RADIUS, KLEIN_OFFER_TYPES, JUDETE, platformLabel,
} from "@/lib/marketplaceConstants";
import { Search, SlidersHorizontal, Loader2, AlertTriangle } from "lucide-react";

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const wlabel = { display: "block", fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.25rem" };

const saveKey = (l) => `${l.source || l.platform}:${l.platform_id || l.source_url}`;

export default function MarketplaceSearchPage() {
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState(["olx", "vinted"]);
  const [common, setCommon] = useState({ price_min: "", price_max: "", state: "" });
  const [platformFilters, setPlatformFilters] = useState({});
  const [showFilters, setShowFilters] = useState(false);

  const [results, setResults] = useState({});   // { platform: {loading, results, error} }
  const [activeTab, setActiveTab] = useState("all");
  const [sortBy, setSortBy] = useState("relevance");
  const [hasSearched, setHasSearched] = useState(false);
  // MODIFICARE 17 — query-ul efectiv cautat (pentru "Încarcă mai multe").
  const [searchedQ, setSearchedQ] = useState("");

  const [savedKeys, setSavedKeys] = useState(new Set());
  const [savingKey, setSavingKey] = useState(null);

  const togglePlatform = (p) => {
    setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  };
  const setPF = (platform, key, value) =>
    setPlatformFilters((prev) => ({ ...prev, [platform]: { ...(prev[platform] || {}), [key]: value } }));
  const togglePFCondition = (platform, value) =>
    setPlatformFilters((prev) => {
      const cur = Array.isArray(prev[platform]?.condition) ? prev[platform].condition : [];
      const next = cur.includes(value) ? cur.filter((c) => c !== value) : [...cur, value];
      return { ...prev, [platform]: { ...(prev[platform] || {}), condition: next } };
    });

  const buildFilters = (platform) => {
    const out = {};
    if (common.price_min !== "") out.price_min = parseFloat(common.price_min);
    if (common.price_max !== "") out.price_max = parseFloat(common.price_max);
    if (common.state) out.state = common.state;
    const pf = platformFilters[platform] || {};
    for (const [k, v] of Object.entries(pf)) {
      if (v == null || v === "") continue;
      if (Array.isArray(v) && v.length === 0) continue;
      out[k] = v;
    }
    return out;
  };

  // MODIFICARE 17 — opts = { page, per_page } transmise scraperelor (paginare).
  const callPlatform = (platform, q, filters, opts = {}) => {
    switch (platform) {
      case "olx": return marketplaceAPI.olxGeneral(q, "", filters, opts);
      case "vinted": return marketplaceAPI.vinted(q, filters, opts);
      case "lajumate": return marketplaceAPI.lajumate(q, filters, opts);
      case "publi24": return marketplaceAPI.publi24(q, filters, opts);
      case "okazii": return marketplaceAPI.okazii(q, filters, opts);
      case "kleinanzeigen": return marketplaceAPI.kleinanzeigen(q, "", filters, opts);
      case "facebook":
        return Promise.reject({ response: { data: { detail: "Facebook Marketplace necesita autentificare — indisponibil momentan." } } });
      default:
        return Promise.reject({ response: { data: { detail: "Platforma necunoscuta." } } });
    }
  };

  const fetchPlatform = async (platform, q, page = 1, append = false) => {
    if (append) {
      setResults((prev) => ({ ...prev, [platform]: { ...prev[platform], loadingMore: true } }));
    }
    try {
      const res = await callPlatform(platform, q, buildFilters(platform), { page, per_page: 20 });
      const newResults = res.data?.results || [];
      setResults((prev) => ({
        ...prev,
        [platform]: {
          loading: false, loadingMore: false,
          results: append ? [...(prev[platform]?.results || []), ...newResults] : newResults,
          error: null, page, hasMore: !!res.data?.has_more,
        },
      }));
    } catch (e) {
      setResults((prev) => ({
        ...prev,
        [platform]: {
          loading: false, loadingMore: false,
          results: append ? (prev[platform]?.results || []) : [],
          error: e.response?.data?.detail || "Eroare la cautare.",
          page: append ? (prev[platform]?.page || 1) : 1, hasMore: false,
        },
      }));
    }
  };

  const loadMore = (platform) => {
    const cur = results[platform];
    if (!cur || cur.loadingMore || !cur.hasMore) return;
    fetchPlatform(platform, searchedQ, (cur.page || 1) + 1, true);
  };

  const doSearch = (e) => {
    e?.preventDefault();
    const q = keyword.trim();
    if (!q) { alert("Introdu un cuvant cheie pentru cautare."); return; }
    if (selected.length === 0) { alert("Selecteaza cel putin o platforma."); return; }
    setHasSearched(true);
    setSearchedQ(q);
    setActiveTab("all");
    const init = {};
    selected.forEach((p) => { init[p] = { loading: true, results: [], error: null, page: 1, hasMore: false }; });
    setResults(init);
    selected.forEach((p) => fetchPlatform(p, q, 1, false));
  };

  const handleSave = async (listing) => {
    const key = saveKey(listing);
    setSavingKey(key);
    try {
      await marketplaceAPI.saveListing({
        platform: listing.source || listing.platform,
        external_id: listing.platform_id || listing.external_id || null,
        title: listing.title,
        price: listing.price,
        currency: listing.currency || "RON",
        source_url: listing.source_url,
        thumbnail_url: listing.thumbnail_url,
      });
      setSavedKeys((prev) => new Set(prev).add(key));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSavingKey(null);
    }
  };

  // Rezultate combinate + sortare
  const allResults = useMemo(
    () => selected.flatMap((p) => (results[p]?.results || [])),
    [results, selected]
  );
  const sorted = useMemo(() => {
    const base = activeTab === "all" ? allResults : (results[activeTab]?.results || []);
    const arr = [...base];
    if (sortBy === "price_asc") arr.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
    else if (sortBy === "price_desc") arr.sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
    return arr;
  }, [activeTab, allResults, results, sortBy]);

  // Filtre specifice per platforma (Pas 3)
  const renderPlatformFilters = (platform) => {
    const pf = platformFilters[platform] || {};
    const cond = (
      <div>
        <label style={wlabel}>Stare ({platformLabel(platform)})</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
          {(CONDITION_BY_PLATFORM[platform] || []).map((c) => {
            const checked = Array.isArray(pf.condition) && pf.condition.includes(c);
            return (
              <label key={c} style={{
                display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem",
                color: checked ? "var(--blue-light)" : "var(--text-secondary)", cursor: "pointer",
                padding: "0.2rem 0.5rem", border: `1px solid ${checked ? "var(--blue-primary)" : "var(--border-color)"}`,
                borderRadius: "0.4rem", backgroundColor: checked ? "var(--blue-dim)" : "transparent",
              }}>
                <input type="checkbox" checked={checked} onChange={() => togglePFCondition(platform, c)} />
                {c}
              </label>
            );
          })}
        </div>
      </div>
    );
    const judet = (
      <div>
        <label style={wlabel}>Judet</label>
        <select value={pf.location_county || ""} onChange={(e) => setPF(platform, "location_county", e.target.value)} style={inputStyle}>
          <option value="">Toate judetele</option>
          {JUDETE.map((j) => <option key={j} value={j}>{j}</option>)}
        </select>
      </div>
    );

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
        {cond}
        {platform === "olx" && (<>
          {judet}
          <div><label style={wlabel}>Oras</label><input value={pf.location_city || ""} onChange={(e) => setPF(platform, "location_city", e.target.value)} placeholder="ex: Cluj-Napoca" style={inputStyle} /></div>
        </>)}
        {platform === "vinted" && (
          <div><label style={wlabel}>Marime</label><input value={pf.size || ""} onChange={(e) => setPF(platform, "size", e.target.value)} placeholder="ex: M, 42" style={inputStyle} /></div>
        )}
        {platform === "facebook" && (<>
          <div><label style={wlabel}>Locatie (oras)</label><input value={pf.location_city || ""} onChange={(e) => setPF(platform, "location_city", e.target.value)} placeholder="ex: Bucuresti" style={inputStyle} /></div>
          <div><label style={wlabel}>Distanta</label>
            <select value={pf.distance_km || ""} onChange={(e) => setPF(platform, "distance_km", e.target.value)} style={inputStyle}>
              <option value="">Oricare</option>{FACEBOOK_DISTANCES.map((d) => <option key={d} value={d}>{d} km</option>)}
            </select>
          </div>
        </>)}
        {(platform === "lajumate" || platform === "publi24" || platform === "okazii") && judet}
        {platform === "kleinanzeigen" && (<>
          <div><label style={wlabel}>Tip oferta</label>
            <div style={{ display: "flex", gap: "0.375rem" }}>
              {KLEIN_OFFER_TYPES.map((t) => {
                const active = pf.offer_type === t;
                return (
                  <button key={t} type="button" onClick={() => setPF(platform, "offer_type", t)}
                    style={{ flex: 1, padding: "0.4rem", borderRadius: "0.4rem", cursor: "pointer", fontSize: "0.75rem", fontWeight: 600,
                      backgroundColor: active ? "var(--blue-dim)" : "var(--bg-dark)", color: active ? "var(--blue-light)" : "var(--text-primary)",
                      border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}` }}>{t}</button>
                );
              })}
            </div>
          </div>
          <div><label style={wlabel}>PLZ</label><input value={pf.plz || ""} maxLength={5} onChange={(e) => setPF(platform, "plz", e.target.value.replace(/\D/g, "").slice(0, 5))} placeholder="ex: 10115" style={inputStyle} /></div>
          <div><label style={wlabel}>Raza</label>
            <select value={pf.radius_km || ""} onChange={(e) => setPF(platform, "radius_km", e.target.value)} style={inputStyle}>
              <option value="">Oricare</option>{KLEIN_RADIUS.map((r) => <option key={r} value={r}>{r} km</option>)}
            </select>
          </div>
        </>)}
      </div>
    );
  };

  const cardBox = { backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem" };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Search style={{ width: "22px", height: "22px", color: "#2563eb" }} />
          Cauta Anunturi
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Cauta pe OLX, Vinted, Facebook si alte platforme
        </p>
      </div>

      <div style={{ ...cardBox, marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.875rem" }}>
        {/* Rand 1: keyword + cauta */}
        <form onSubmit={doSearch} style={{ display: "flex", gap: "0.5rem" }}>
          <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="ex: iPhone 14 Pro" style={{ ...inputStyle, flex: 1 }} />
          <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600, cursor: "pointer" }}>
            <Search style={{ width: "16px", height: "16px" }} /> Cauta
          </button>
        </form>

        {/* Rand 2: platforme */}
        <div>
          <label style={wlabel}>Platforme</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {MARKETPLACE_PLATFORMS.map((p) => {
              const active = selected.includes(p.value);
              return (
                <label key={p.value} style={{
                  display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem", cursor: "pointer",
                  padding: "0.3rem 0.625rem", borderRadius: "0.5rem", fontWeight: 600,
                  color: active ? "var(--blue-light)" : "var(--text-secondary)",
                  border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
                  backgroundColor: active ? "var(--blue-dim)" : "transparent",
                }}>
                  <input type="checkbox" checked={active} onChange={() => togglePlatform(p.value)} style={{ display: "none" }} />
                  {p.label}
                </label>
              );
            })}
          </div>
        </div>

        {/* Rand 3: filtre comune */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
          <div><label style={wlabel}>Pret min</label><input type="number" value={common.price_min} onChange={(e) => setCommon({ ...common, price_min: e.target.value })} placeholder="ex: 100" style={inputStyle} /></div>
          <div><label style={wlabel}>Pret max</label><input type="number" value={common.price_max} onChange={(e) => setCommon({ ...common, price_max: e.target.value })} placeholder="ex: 2000" style={inputStyle} /></div>
          <div><label style={wlabel}>Stare</label>
            <select value={common.state} onChange={(e) => setCommon({ ...common, state: e.target.value })} style={inputStyle}>
              <option value="">Toate</option>
              <option value="nou">Nou</option>
              <option value="folosit">Folosit</option>
            </select>
          </div>
        </div>

        {/* Rand 4: filtre specifice per platforma (expandabil) */}
        {selected.length > 0 && (
          <div>
            <button type="button" onClick={() => setShowFilters((s) => !s)}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.375rem 0.75rem", borderRadius: "0.5rem", border: "1px solid var(--border-color)", backgroundColor: "transparent", color: "var(--text-secondary)", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>
              <SlidersHorizontal style={{ width: "14px", height: "14px" }} /> Filtre specifice platformei
            </button>
            {showFilters && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem", marginTop: "0.75rem" }}>
                {selected.map((p) => (
                  <div key={p} style={{ border: "1px solid var(--border-color)", borderRadius: "0.625rem", padding: "0.75rem" }}>
                    <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>{platformLabel(p)}</div>
                    {renderPlatformFilters(p)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <button type="button" onClick={doSearch}
            style={{ padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--green-primary)", color: "white", border: "none", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer" }}>
            Aplica filtre
          </button>
        </div>
      </div>

      {/* Rezultate */}
      {hasSearched && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            {/* Pills per platforma */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              <button onClick={() => setActiveTab("all")} style={pillStyle(activeTab === "all")}>
                Toate ({allResults.length})
              </button>
              {selected.map((p) => {
                const st = results[p] || {};
                return (
                  <button key={p} onClick={() => setActiveTab(p)} style={pillStyle(activeTab === p)}>
                    {platformLabel(p)}{" "}
                    {st.loading ? <Loader2 style={{ width: "12px", height: "12px", display: "inline", animation: "spin 1s linear infinite" }} />
                      : st.error ? <AlertTriangle style={{ width: "12px", height: "12px", display: "inline", color: "#fb923c" }} />
                      : `(${st.results?.length || 0})`}
                  </button>
                );
              })}
            </div>
            {/* Sortare */}
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ ...inputStyle, width: "auto" }}>
              <option value="relevance">Relevanta</option>
              <option value="price_asc">Pret crescator</option>
              <option value="price_desc">Pret descrescator</option>
            </select>
          </div>

          {/* Erori per platforma (inline) */}
          {selected.filter((p) => results[p]?.error).map((p) => (
            <div key={p} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.625rem 0.875rem", marginBottom: "0.5rem", borderRadius: "0.5rem", backgroundColor: "rgba(251,146,60,0.08)", border: "1px solid rgba(251,146,60,0.3)", fontSize: "0.8125rem", color: "#fb923c" }}>
              <AlertTriangle style={{ width: "16px", height: "16px", flexShrink: 0 }} />
              <span><strong>{platformLabel(p)}:</strong> {results[p].error}</span>
            </div>
          ))}

          {/* Grid carduri */}
          {sorted.length > 0 ? (
            <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
              {sorted.map((l, i) => (
                <MarketplaceListingCard
                  key={`${saveKey(l)}-${i}`}
                  listing={l}
                  onSave={handleSave}
                  isSaved={savedKeys.has(saveKey(l))}
                  busy={savingKey === saveKey(l)}
                />
              ))}
            </div>
            {/* MODIFICARE 17 — "Încarcă mai multe" pe tab-ul unei platforme cu has_more */}
            {activeTab !== "all" && results[activeTab]?.hasMore && (
              <div style={{ display: "flex", justifyContent: "center", marginTop: "1.25rem" }}>
                <button
                  onClick={() => loadMore(activeTab)}
                  disabled={results[activeTab]?.loadingMore}
                  style={{
                    padding: "0.5rem 1.5rem", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600,
                    cursor: results[activeTab]?.loadingMore ? "not-allowed" : "pointer",
                    border: "1px solid var(--border-color)", backgroundColor: "var(--bg-card)", color: "var(--text-primary)",
                  }}
                >
                  {results[activeTab]?.loadingMore ? "Se încarcă..." : "Încarcă mai multe"}
                </button>
              </div>
            )}
            </>
          ) : (
            selected.some((p) => results[p]?.loading) ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
                <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
              </div>
            ) : (
              <div style={{ ...cardBox, textAlign: "center", color: "var(--text-secondary)", padding: "2.5rem" }}>
                Niciun rezultat. Incearca alt cuvant cheie sau alte platforme.
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}

function pillStyle(active) {
  return {
    padding: "0.375rem 0.75rem", borderRadius: "999px", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
    border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
    backgroundColor: active ? "var(--blue-primary)" : "transparent",
    color: active ? "white" : "var(--text-secondary)",
  };
}
