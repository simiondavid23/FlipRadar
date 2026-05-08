"use client";
import { useState } from "react";
import { scrapingAPI, productsAPI, favoritesAPI } from "@/lib/api";
import { Globe, Search, Plus, Heart, ExternalLink, ShoppingBag } from "lucide-react";

const SOURCE_STYLES = {
  "altex.ro": { bg: "rgba(59,130,246,0.2)", fg: "#60a5fa" },
  "sole.ro": { bg: "rgba(236,72,153,0.2)", fg: "#f472b6" },
  "farmaciatei.ro": { bg: "rgba(34,197,94,0.2)", fg: "#4ade80" },
  "emag.ro": { bg: "rgba(250,204,21,0.2)", fg: "#facc15" },
  "pcgarage.ro": { bg: "rgba(168,85,247,0.2)", fg: "#c084fc" },
};

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
    setLoading(true);
    setResults(null);
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
      });
      alert(buildSaveMessage(res.data, product.name));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare");
    }
  };

  const addToFavorites = async (product) => {
    try {
      const saved = await productsAPI.createProduct({
        name: product.name, current_price: product.price, currency: product.currency || "RON",
        source: product.source, source_url: product.source_url, image_url: product.image_url,
        ean: product.ean || null, sku: product.sku || null,
      });
      await favoritesAPI.addFavorite({ product_id: saved.data.id, is_blacklisted: false });
      const status = saved.data.is_new
        ? "Produs nou salvat si adaugat la favorite!"
        : (saved.data.price_changed
            ? `Produsul exista deja — pretul a fost actualizat (${Number(saved.data.previous_price).toFixed(2)} -> ${Number(saved.data.current_price).toFixed(2)} ${saved.data.currency}) si adaugat la favorite.`
            : "Produsul exista deja in baza de date si a fost adaugat la favorite.");
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
  const inputStyle = { backgroundColor: "#0f172a", border: "1px solid #334155" };
  const cardStyle = { backgroundColor: "#1e293b", border: "1px solid #334155" };

  return (
    <div>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "white", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Globe style={{ width: "2rem", height: "2rem", color: "#06b6d4" }} />
          Web Scraping
        </h1>
        <p style={{ color: "#94a3b8", marginTop: "0.5rem" }}>Cauta produse pe Altex.ro, Sole.ro, Farmacia Tei, eMAG.ro si PCGarage.ro</p>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "stretch" }}>
          <select value={searchType} onChange={(e) => setSearchType(e.target.value)}
            title="Tipul codului dupa care cautam"
            style={{ ...inputStyle, padding: "0.75rem 1rem", borderRadius: "0.5rem", color: "white", fontSize: "0.875rem", minWidth: "150px" }}>
            <option value="name">Cauta dupa: Nume</option>
            <option value="ean">Cauta dupa: EAN</option>
            <option value="sku">Cauta dupa: SKU</option>
          </select>
          <div style={{ flex: 1, minWidth: "200px", position: "relative" }}>
            <Search style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", width: "1.25rem", height: "1.25rem", color: "#94a3b8" }} />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={SEARCH_TYPE_PLACEHOLDERS[searchType]}
              inputMode={searchType === "ean" ? "numeric" : "text"}
              style={{ ...inputStyle, width: "100%", padding: "0.75rem 1rem 0.75rem 2.5rem", borderRadius: "0.5rem", color: "white", fontSize: "0.875rem", outline: "none" }} />
          </div>
          <select value={source} onChange={(e) => setSource(e.target.value)}
            style={{ ...inputStyle, padding: "0.75rem 1rem", borderRadius: "0.5rem", color: "white", fontSize: "0.875rem" }}>
            <option value="all">Toate sursele</option>
            <option value="altex">Altex.ro</option>
            <option value="sole">Sole.ro</option>
            <option value="farmaciatei">Farmacia Tei</option>
            <option value="emag">eMAG.ro</option>
            <option value="pcgarage">PCGarage.ro</option>
          </select>
          <button type="submit" disabled={loading}
            style={{ padding: "0.75rem 1.5rem", borderRadius: "0.5rem", backgroundColor: "#06b6d4", color: "white", fontWeight: 500, border: "none", cursor: "pointer", opacity: loading ? 0.5 : 1 }}>
            {loading ? "Se cauta..." : "Cauta"}
          </button>
        </div>
        {eanHint && (
          <p style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#facc15" }}>
            {eanHint}
          </p>
        )}
        {searchType !== "name" && !eanHint && (
          <p style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#94a3b8" }}>
            Nu toate magazinele indexeaza dupa {searchType === "ean" ? "EAN" : "SKU"}. Sursele care nu o fac vor returna 0 rezultate.
          </p>
        )}
      </form>

      {/* Results */}
      {loading && (
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "3rem", textAlign: "center" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid #06b6d4", borderTop: "4px solid transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto 1rem" }} />
          <p style={{ color: "#94a3b8" }}>Se cauta produse pe {source === "all" ? "toate sursele" : source}...</p>
        </div>
      )}

      {results && !loading && (
        <div>
          <p style={{ color: "#94a3b8", marginBottom: "1rem", fontSize: "0.875rem" }}>
            {allResults.length} produse gasite {results.query ? `pentru "${results.query}"` : ""}
          </p>

          {allResults.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {allResults.map((product, i) => {
                const style = SOURCE_STYLES[product.source] || { bg: "rgba(148,163,184,0.2)", fg: "#cbd5e1" };
                const cur = product.currency || "RON";
                return (
                  <div key={i} style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem", flexWrap: "wrap" }}>
                          <h3 style={{ fontWeight: 600, color: "white", fontSize: "1rem" }}>{product.name}</h3>
                          <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: style.bg, color: style.fg }}>{product.source}</span>
                          {product.ean && (
                            <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(250,204,21,0.15)", color: "#facc15" }}>
                              EAN: {product.ean}
                            </span>
                          )}
                          {!product.ean && product.sku && (
                            <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(148,163,184,0.1)", color: "#94a3b8" }}>
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
                                  color: "#94a3b8",
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
                          style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "none", backgroundColor: "transparent", color: "#94a3b8", cursor: "pointer" }}>
                          <Plus style={{ width: "1.25rem", height: "1.25rem" }} />
                        </button>
                        <button onClick={() => addToFavorites(product)} title="Adauga la favorite"
                          style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "none", backgroundColor: "transparent", color: "#94a3b8", cursor: "pointer" }}>
                          <Heart style={{ width: "1.25rem", height: "1.25rem" }} />
                        </button>
                        {product.source_url && (
                          <a href={product.source_url} target="_blank" rel="noopener noreferrer"
                            style={{ padding: "0.5rem", borderRadius: "0.5rem", color: "#94a3b8" }}>
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
            <div style={{ ...cardStyle, borderRadius: "1rem", padding: "3rem", textAlign: "center" }}>
              <ShoppingBag style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "#475569" }} />
              <p style={{ color: "white", marginBottom: "0.5rem" }}>Nu s-au gasit produse</p>
              <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Incearca alt termen de cautare sau alta sursa.</p>
            </div>
          )}
        </div>
      )}

      {!results && !loading && (
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "3rem", textAlign: "center" }}>
          <Globe style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "#475569" }} />
          <p style={{ color: "white", fontSize: "1.125rem", marginBottom: "0.5rem" }}>Cauta produse pe magazinele online</p>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Introdu un termen de cautare pentru a gasi produse pe Altex.ro, Sole.ro, Farmacia Tei, eMAG.ro si PCGarage.ro</p>
        </div>
      )}
    </div>
  );
}
