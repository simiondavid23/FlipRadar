"use client";
import { useState, useMemo } from "react";
import { scrapingAPI, productsAPI, trackedProductsAPI } from "@/lib/api";
import { Globe, Search, Plus, Heart, ExternalLink, ShoppingBag } from "lucide-react";
import AddByLinkWizard from "@/components/AddByLinkWizard";
import { styleFor } from "@/lib/sourceStyles";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";

const SEARCH_TYPE_PLACEHOLDERS = {
  name: "ex: MacBook Pro 14, crema hidratanta",
  ean: "ex: 5901234567890 (8 sau 13 cifre)",
  sku: "ex: MDE14ROA",
};

export default function ScrapingPage() {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState("name");
  const [source, setSource] = useState("all");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortOrder, setSortOrder] = useState("default");
  // RETAIL-4 — link lipit in campul de cautare: deschide asistentul de adaugare.
  const [linkUrl, setLinkUrl] = useState(null);

  const eanHint = (() => {
    if (searchType !== "ean" || !query.trim()) return "";
    const v = query.trim();
    if (!/^\d+$/.test(v)) return "EAN-ul contine doar cifre.";
    if (v.length !== 8 && v.length !== 13) return "EAN standard are 8 sau 13 cifre.";
    return "";
  })();

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    // RETAIL-4 — un URL nu e un termen de cautare: deschide asistentul in loc sa
    // trimita link-ul catre scraperele de cautare (ar returna 0 rezultate).
    const trimmed = query.trim();
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      setLinkUrl(trimmed);
      return;
    }
    setLoading(true);
    setResults(null);
    setSortOrder("default");
    try {
      let res;
      if (source === "altex") res = await scrapingAPI.searchAltex(query, undefined, searchType);
      else if (source === "sole") res = await scrapingAPI.searchSole(query, undefined, searchType);
      else if (source === "farmaciatei") res = await scrapingAPI.searchFarmaciatei(query, undefined, searchType);
      else if (source === "emag") res = await scrapingAPI.searchEmag(query, undefined, searchType);
      else if (source === "pcgarage") res = await scrapingAPI.searchPcgarage(query, undefined, searchType);
      else res = await scrapingAPI.searchAll(query, undefined, searchType);
      setResults(res.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const buildSaveMessage = (data, productName) => {
    if (data.is_new) {
      return `Produs nou adaugat in baza de date:\n"${productName}"\n\nPret: ${data.current_price} ${data.currency}`;
    }
    // Produsul exista deja
    if (data.price_changed && data.previous_price != null) {
      const oldP = Number(data.previous_price).toFixed(2);
      const newP = Number(data.current_price).toFixed(2);
      const diff = Number(data.current_price) - Number(data.previous_price);
      const direction = diff < 0 ? "a SCAZUT" : "a CRESCUT";
      return `Produsul exista deja in baza de date.\n"${productName}"\n\nPretul ${direction}:\n${oldP} ${data.currency}  ->  ${newP} ${data.currency}\n(diferenta: ${diff > 0 ? "+" : ""}${diff.toFixed(2)} ${data.currency})`;
    }
    return `Produsul exista deja in baza de date.\n"${productName}"\n\nPretul a ramas neschimbat: ${data.current_price} ${data.currency}`;
  };

  const saveProduct = async (product) => {
    try {
      const res = await productsAPI.createProduct({
        name: product.name,
        current_price: product.price,
        currency: product.currency || "RON",
        source: product.source,
        source_url: product.source_url,
        image_url: product.image_url,
        ean: product.ean || null,
        sku: product.sku || null,
        category: product.category || null,
        subcategory: product.subcategory || null,
      });
      alert(buildSaveMessage(res.data, product.name));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare");
    }
  };

  const saveAndTrack = async (product) => {
    try {
      const saved = await productsAPI.createProduct({
        name: product.name, current_price: product.price, currency: product.currency || "RON",
        source: product.source, source_url: product.source_url, image_url: product.image_url,
        ean: product.ean || null, sku: product.sku || null,
        category: product.category || null, subcategory: product.subcategory || null,
      });
      await trackedProductsAPI.toggleMonitoring(saved.data.id, true, null);
      const status = saved.data.is_new
        ? "Produs nou salvat si adaugat in Produse Urmarite!"
        : (saved.data.price_changed
            ? `Produsul exista deja — pretul a fost actualizat (${Number(saved.data.previous_price).toFixed(2)} -> ${Number(saved.data.current_price).toFixed(2)} ${saved.data.currency}) si adaugat in Produse Urmarite.`
            : "Produsul exista deja in baza de date si a fost adaugat in Produse Urmarite.");
      alert(status);
    } catch (e) { alert(e.response?.data?.detail || "Eroare"); }
  };

  const getAllResults = () => {
    if (!results) return [];
    if (results.results) return results.results;
    if (results.sources) {
      const all = [];
      Object.values(results.sources).forEach(s => { if (s.results) all.push(...s.results); });
      return all;
    }
    return [];
  };

  const allResults = getAllResults().filter(r => !r.error && !r.message);
  const sortedResults = useMemo(() => {
    if (sortOrder === "price_asc")
      return [...allResults].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
    if (sortOrder === "price_desc")
      return [...allResults].sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
    return allResults;
  }, [allResults, sortOrder]);
  const inputStyle = {
    background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
    border: "1px solid transparent",
    fontFamily: "var(--font-sans)",
    outline: "none",
  };

  return (
    <div>
      <TopBar path={["CATALOG", "SCANARE MAGAZINE"]} />

      <PageHeading
        icon={Globe}
        title="Scanare Magazine"
        subtitle={results
          ? <>Caută produse pe 5 magazine — <Hl>{allResults.length} rezultate</Hl> pentru căutarea curentă.</>
          : "Cauta produse pe Altex.ro, Sole.ro, Farmacia Tei, eMAG.ro si PCGarage.ro"}
      />

      {/* Search */}
      <form onSubmit={handleSearch} style={{ marginTop: "16px" }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "stretch" }}>
          <select value={searchType} onChange={(e) => setSearchType(e.target.value)}
            title="Tipul codului dupa care cautam"
            style={{ ...inputStyle, padding: "10px 13px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12.5px", minWidth: "150px", cursor: "pointer" }}>
            <option value="name">Cauta dupa: Nume</option>
            <option value="ean">Cauta dupa: EAN</option>
            <option value="sku">Cauta dupa: SKU</option>
          </select>
          <div style={{ flex: 1, minWidth: "200px", position: "relative" }}>
            <Search style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", width: "15px", height: "15px", color: "var(--text-muted)" }} strokeWidth={1.8} />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={SEARCH_TYPE_PLACEHOLDERS[searchType]}
              inputMode={searchType === "ean" ? "numeric" : "text"}
              style={{ ...inputStyle, width: "100%", padding: "10px 13px 10px 34px", borderRadius: "10px", color: "var(--text-primary)", fontSize: "12.5px" }} />
          </div>
          <select value={source} onChange={(e) => setSource(e.target.value)}
            style={{ ...inputStyle, padding: "10px 13px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12.5px", cursor: "pointer" }}>
            <option value="all">Toate sursele</option>
            <option value="altex">Altex.ro</option>
            <option value="sole">Sole.ro</option>
            <option value="farmaciatei">Farmacia Tei</option>
            <option value="emag">eMAG.ro</option>
            <option value="pcgarage">PCGarage.ro</option>
          </select>
          <button type="submit" disabled={loading} className="btn-cyan">
            {loading ? "Se cauta…" : "Cauta"}
          </button>
        </div>
        {eanHint && (
          <p style={{ marginTop: "8px", fontSize: "11.5px", color: "#fde047" }}>
            {eanHint}
          </p>
        )}
        {searchType !== "name" && !eanHint && (
          <p style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--text-dim)" }}>
            Nu toate magazinele indexeaza dupa {searchType === "ean" ? "EAN" : "SKU"}. Sursele care nu o fac vor returna 0 rezultate.
          </p>
        )}
        <p style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--text-muted)" }}>
          Poti lipi direct link-ul unei pagini de produs — se deschide asistentul de adaugare.
        </p>
      </form>

      {linkUrl && <AddByLinkWizard url={linkUrl} onClose={() => setLinkUrl(null)} />}

      {/* Results */}
      {loading && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "16px" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto 14px" }} />
          <p style={{ color: "var(--text-dim)", fontSize: "12.5px" }}>Se cauta produse pe {source === "all" ? "toate sursele" : source}…</p>
        </div>
      )}

      {results && !loading && (
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", margin: "16px 0 14px", flexWrap: "wrap" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--text-mono)", margin: 0 }}>
              {allResults.length} produse gasite {results.query ? `pentru "${results.query}"` : ""}
            </p>
            {allResults.length > 0 && (
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
                style={{ ...inputStyle, padding: "7px 11px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12px", cursor: "pointer" }}
              >
                <option value="default">Sorteaza: Implicit</option>
                <option value="price_asc">Pret: crescator</option>
                <option value="price_desc">Pret: descrescator</option>
              </select>
            )}
          </div>

          {allResults.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {sortedResults.map((product, i) => {
                const style = styleFor(product.source);
                const cur = product.currency || "RON";
                return (
                  <div key={i} className="glass-panel lift-hover" style={{ padding: "16px 18px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem", flexWrap: "wrap" }}>
                          <h3 style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "14px", margin: 0 }}>{product.name}</h3>
                          <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase", background: style.bg, border: `1px solid ${style.fg}55`, color: style.fg }}>{product.source}</span>
                          {product.ean && (
                            <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", background: "rgba(253,224,71,0.14)", border: "1px solid rgba(253,224,71,0.4)", color: "#fde047" }}>
                              EAN: {product.ean}
                            </span>
                          )}
                          {!product.ean && product.sku && (
                            <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", background: "rgba(148,163,184,0.12)", border: "1px solid rgba(148,163,184,0.3)", color: "var(--text-dim)" }}>
                              SKU: {product.sku}
                            </span>
                          )}
                        </div>
                        {product.in_stock === false ? (
                          <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "#f87171" }}>
                            Stoc epuizat
                          </span>
                        ) : product.price > 0 ? (
                          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
                            <span style={{ fontSize: "1.25rem", fontWeight: 700, color: product.is_on_sale ? "#f87171" : "#4ade80" }}>
                              {product.price.toFixed(2)} {cur}
                            </span>
                            {product.is_on_sale && product.original_price > 0 && (
                              <>
                                <span style={{
                                  fontSize: "0.875rem",
                                  color: "var(--text-secondary)",
                                  textDecoration: "line-through",
                                }}>
                                  {product.original_price.toFixed(2)} {cur}
                                </span>
                                {(() => {
                                  const pct = Math.round(((product.original_price - product.price) / product.original_price) * 100);
                                  return (
                                    <span style={{
                                      padding: "0.125rem 0.5rem",
                                      borderRadius: "0.25rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 700,
                                      backgroundColor: "rgba(248,113,113,0.2)",
                                      color: "#f87171",
                                    }}>
                                      Reducere -{pct}%
                                    </span>
                                  );
                                })()}
                              </>
                            )}
                          </div>
                        ) : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.375rem" }}>
                        <button onClick={() => saveProduct(product)} title="Salveaza in baza de date"
                          style={{ padding: "0.5rem", borderRadius: "10px", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
                          <Plus style={{ width: "1.25rem", height: "1.25rem" }} />
                        </button>
                        <button onClick={() => saveAndTrack(product)} title="Salveaza si urmareste"
                          style={{ padding: "0.5rem", borderRadius: "10px", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
                          <Heart style={{ width: "1.25rem", height: "1.25rem" }} />
                        </button>
                        {product.source_url && (
                          <a href={product.source_url} target="_blank" rel="noopener noreferrer"
                            style={{ padding: "0.5rem", borderRadius: "10px", color: "var(--text-secondary)" }}>
                            <ExternalLink style={{ width: "1.25rem", height: "1.25rem" }} />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
              <ShoppingBag style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
              <p style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>Nu s-au gasit produse</p>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Incearca alt termen de cautare sau alta sursa.</p>
            </div>
          )}
        </div>
      )}

      {!results && !loading && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <Globe style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
          <p style={{ color: "var(--text-primary)", fontSize: "1.125rem", marginBottom: "0.5rem" }}>Cauta produse pe magazinele online</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Introdu un termen de cautare pentru a gasi produse pe Altex.ro, Sole.ro, Farmacia Tei, eMAG.ro si PCGarage.ro</p>
        </div>
      )}
    </div>
  );
}
