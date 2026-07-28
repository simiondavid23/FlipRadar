"use client";
import { useState, useEffect } from "react";
import { productsAPI, trackedProductsAPI } from "@/lib/api";
import Link from "next/link";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import { Search, Plus, Eye, ExternalLink, Package, X, ChevronRight, Trash2, Pencil, Tag, Save, Filter, RefreshCcw } from "lucide-react";

// FlipRadar — ITEM 9: optiuni fixe pentru selectorul de sursa. Valorile trebuie
// sa coincida exact cu cele salvate de scrapere (domeniul magazinului).
const STORE_SOURCES = [
  { label: "Toate", value: "" },
  { label: "Altex", value: "altex.ro" },
  { label: "eMAG", value: "emag.ro" },
  { label: "PCGarage", value: "pcgarage.ro" },
  { label: "Sole", value: "sole.ro" },
  { label: "FarmaciaTei", value: "farmaciatei.ro" },
];

function computeRoi(price, resale) {
  if (resale == null || price == null) return null;
  const p = Number(price), r = Number(resale);
  if (!isFinite(p) || !isFinite(r) || p <= 0) return null;
  return ((r - p) / p) * 100;
}

function RoiBadge({ price, resale }) {
  const roi = computeRoi(price, resale);
  if (roi == null) return null;
  let rgb, color, label;
  if (roi >= 30) { rgb = "74,222,128"; color = "#4ade80"; label = `ROI ridicat ${roi.toFixed(1)}%`; }
  else if (roi >= 15) { rgb = "253,224,71"; color = "#fde047"; label = `ROI mediu ${roi.toFixed(1)}%`; }
  else if (roi >= 0) { rgb = "251,146,60"; color = "#fb923c"; label = `ROI scazut ${roi.toFixed(1)}%`; }
  else { rgb = "248,113,113"; color = "#f87171"; label = "Neprofitabil"; }
  return (
    <span style={{
      padding: "2.5px 7px", borderRadius: "7px",
      fontFamily: "var(--font-mono)", fontSize: "8.5px", fontWeight: 700, letterSpacing: ".08em",
      textTransform: "uppercase",
      background: `rgba(${rgb},0.14)`, border: `1px solid rgba(${rgb},0.4)`, color,
    }}>
      {label}
    </span>
  );
}

// Chip mono pentru codurile copiabile (SKU / EAN / sursa) din randul de produs.
function codeChipStyle(rgb, color, copied) {
  return {
    padding: "2.5px 7px", borderRadius: "7px",
    fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".08em",
    background: `rgba(${rgb},${copied ? 0.28 : 0.14})`,
    border: `1px solid rgba(${rgb},0.4)`,
    color, cursor: "pointer",
  };
}

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [filters, setFilters] = useState({
    source: "", brand: "", category: "", price_min: "", price_max: "", roi_min: "", roi_max: "",
  });
  // FlipRadar — input brand cu autocomplete (sugestii filtrate din filterOptions.brands)
  const [brandInput, setBrandInput] = useState("");
  const [showBrandDropdown, setShowBrandDropdown] = useState(false);
  // FlipRadar — branduri + categorii reale din DB (GET /api/products/filter-options),
  // optional filtrate dupa sursa selectata.
  const [filterOptions, setFilterOptions] = useState({ brands: [], categories: [] });

  const [newProduct, setNewProduct] = useState({
    name: "", sku: "", ean: "", category: "", source: "", source_url: "",
    current_price: "", resale_price: "", currency: "EUR", image_url: "", description: "",
  });
  const [editingId, setEditingId] = useState(null);
  const [editValues, setEditValues] = useState({
    name: "", sku: "", ean: "", category: "", source: "", source_url: "",
    current_price: "", resale_price: "", currency: "EUR",
  });
  const [editSaving, setEditSaving] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);

  const [inlineResaleId, setInlineResaleId] = useState(null);
  const [inlineResaleValue, setInlineResaleValue] = useState("");
  const [inlineResaleSaving, setInlineResaleSaving] = useState(false);

  const copyToClipboard = async (value, key) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(String(value));
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((curr) => (curr === key ? null : curr)), 1200);
    } catch {
      alert("Nu am putut copia in clipboard. Verifica permisiunile browser-ului.");
    }
  };

  useEffect(() => {
    // FlipRadar — GE-2: deep-link ?roi_min= / ?roi_max= (ex. callout-ul din Statistici & Profit).
    // Citire one-shot din window.location la mount — pagina nu foloseste useSearchParams
    // (ar cere Suspense la build); nu reactionam la schimbari ulterioare de URL fara remount.
    let initial = null;
    try {
      const sp = new URLSearchParams(window.location.search);
      const overrides = {};
      for (const key of ["roi_min", "roi_max"]) {
        const raw = sp.get(key);
        if (raw !== null && raw !== "" && isFinite(parseFloat(raw))) overrides[key] = String(parseFloat(raw));
      }
      if (Object.keys(overrides).length > 0) initial = { ...filters, ...overrides };
    } catch { /* URL invalid — ignoram, incarcam normal */ }

    if (initial) {
      setFilters(initial);
      setShowFilters(true); // panoul deschis, ca filtrul aplicat sa fie vizibil utilizatorului
      loadProducts({ filtersOverride: initial }); // pattern BUG 1: evita race-ul setState/request
    } else {
      loadProducts();
    }
    loadFilterOptions(filters.source);
  }, []);

  // FlipRadar — incarca brandurile si categoriile reale din DB pentru sursa
  // selectata; la schimbarea magazinului lista se actualizeaza corespunzator.
  const loadFilterOptions = async (selectedSource = null) => {
    try {
      const params = {};
      if (selectedSource) params.source = selectedSource;
      const res = await productsAPI.getFilterOptions(params);
      setFilterOptions({
        brands: res.data.brands || [],
        categories: res.data.categories || [],
      });
    } catch (err) {
      console.error("Filter options error:", err);
    }
  };

  // FlipRadar — BUG 1: loadProducts accepta overrides ca sa evite race condition-ul
  // dintre setState (asincron) si request (overrides.sortBy / overrides.filtersOverride).
  const loadProducts = async (overrides = {}) => {
    setLoading(true);
    try {
      const f = overrides.filtersOverride ?? filters;
      const effectiveSortBy = overrides.sortBy ?? sortBy;
      const params = {};
      if (search.trim()) params.search = search.trim();
      if (f.source) params.source = f.source;
      if (f.brand) params.brand = f.brand;
      if (f.category) params.category = f.category;
      if (f.price_min !== "" && f.price_min != null) params.price_min = parseFloat(f.price_min);
      if (f.price_max !== "" && f.price_max != null) params.price_max = parseFloat(f.price_max);
      if (f.roi_min !== "" && f.roi_min != null) params.roi_min = parseFloat(f.roi_min);
      if (f.roi_max !== "" && f.roi_max != null) params.roi_max = parseFloat(f.roi_max);
      if (effectiveSortBy) params.sort_by = effectiveSortBy;
      const response = await productsAPI.getProducts(params);
      setProducts(response.data);
    } catch (error) {
      console.error("Eroare la incarcarea produselor:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    loadProducts();
  };

  const handleApplyFilters = () => loadProducts();

  const handleResetFilters = () => {
    const cleared = { source: "", brand: "", category: "", price_min: "", price_max: "", roi_min: "", roi_max: "" };
    setFilters(cleared);
    setBrandInput("");
    setShowBrandDropdown(false);
    setSearch("");
    loadFilterOptions("");
    loadProducts({ filtersOverride: cleared });
  };

  // FlipRadar — schimbarea sursei reseteaza brand + categorie si reincarca
  // brandurile/categoriile reale din DB pentru magazinul selectat.
  const handleSourceChange = (value) => {
    setFilters((prev) => ({ ...prev, source: value, brand: "", category: "" }));
    setBrandInput("");
    setShowBrandDropdown(false);
    loadFilterOptions(value);
  };

  // FlipRadar — BUG 1: schimbarea sortarii trimite valoarea direct in request,
  // fara sa astepte re-render-ul state-ului sortBy.
  const handleSortChange = (value) => {
    setSortBy(value);
    loadProducts({ sortBy: value });
  };

  const handleAddProduct = async (e) => {
    e.preventDefault();
    try {
      const productData = {
        ...newProduct,
        current_price: newProduct.current_price ? parseFloat(newProduct.current_price) : null,
        resale_price: newProduct.resale_price ? parseFloat(newProduct.resale_price) : null,
      };
      await productsAPI.createProduct(productData);
      setShowAddForm(false);
      setNewProduct({ name: "", sku: "", ean: "", category: "", source: "", source_url: "", current_price: "", resale_price: "", currency: "EUR", image_url: "", description: "" });
      loadProducts();
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la adaugare produs");
    }
  };

  const handleTrackProduct = async (productId) => {
    try {
      await trackedProductsAPI.toggleMonitoring(productId, true, null);
      alert("Produs adaugat in Produse Urmarite — monitorizare activata!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare");
    }
  };

  const startEdit = (product) => {
    setEditingId(product.id);
    setEditValues({
      name: product.name || "",
      sku: product.sku || "",
      ean: product.ean || "",
      category: product.category || "",
      source: product.source || "",
      source_url: product.source_url || "",
      current_price: product.current_price ?? "",
      resale_price: product.resale_price ?? "",
      currency: product.currency || "EUR",
    });
  };

  const cancelEdit = () => setEditingId(null);

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingId) return;
    if (!editValues.name.trim()) {
      alert("Numele produsului nu poate fi gol");
      return;
    }
    setEditSaving(true);
    try {
      const payload = {
        name: editValues.name.trim(),
        sku: editValues.sku || null,
        ean: editValues.ean || null,
        category: editValues.category || null,
        source: editValues.source || null,
        source_url: editValues.source_url || null,
        current_price: editValues.current_price === "" ? null : parseFloat(editValues.current_price),
        resale_price: editValues.resale_price === "" ? null : parseFloat(editValues.resale_price),
        currency: editValues.currency || "EUR",
      };
      const response = await productsAPI.updateProduct(editingId, payload);
      setProducts((prev) => prev.map((p) => (p.id === editingId ? { ...p, ...response.data } : p)));
      setEditingId(null);
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la actualizarea produsului");
    } finally {
      setEditSaving(false);
    }
  };

  const startInlineResale = (product) => {
    setInlineResaleId(product.id);
    setInlineResaleValue(product.resale_price ?? "");
  };

  const cancelInlineResale = () => {
    setInlineResaleId(null);
    setInlineResaleValue("");
  };

  const saveInlineResale = async (product) => {
    if (inlineResaleValue === "" || inlineResaleValue == null) {
      alert("Introdu o valoare valida pentru pretul de revanzare");
      return;
    }
    const parsed = parseFloat(inlineResaleValue);
    if (!isFinite(parsed) || parsed < 0) {
      alert("Pretul de revanzare trebuie sa fie un numar pozitiv");
      return;
    }
    setInlineResaleSaving(true);
    try {
      const response = await productsAPI.updateProduct(product.id, { resale_price: parsed });
      setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, ...response.data } : p)));
      cancelInlineResale();
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la salvarea pretului de revanzare");
    } finally {
      setInlineResaleSaving(false);
    }
  };

  const handleDeleteProduct = async (product) => {
    const ok = window.confirm(
      `Esti sigur ca vrei sa stergi produsul "${product.name}"?\n\nAceasta actiune este ireversibila si va sterge si:\n- Istoricul de preturi\n- Alertele asociate\n- Intrarea din Produse Urmarite`
    );
    if (!ok) return;
    try {
      await productsAPI.deleteProduct(product.id);
      setProducts((prev) => prev.filter((p) => p.id !== product.id));
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la stergere");
    }
  };

  const inputBaseStyle = {
    background: "rgba(4,9,18,.45)",
    border: "1px solid var(--border-color)",
    borderRadius: "10px",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    width: "100%",
    outline: "none",
  };

  const labelSmall = {
    display: "block", fontSize: "0.75rem", fontWeight: 500,
    marginBottom: "0.375rem", color: "var(--text-secondary)",
  };

  const hasActiveFilters =
    filters.source || filters.brand || filters.category ||
    filters.price_min !== "" || filters.price_max !== "" ||
    filters.roi_min !== "" || filters.roi_max !== "";

  // FlipRadar — sugestii brand din filterOptions.brands (filtrate dupa textul tastat).
  const brandSuggestions = (filterOptions.brands || [])
    .filter((b) => b.toLowerCase().includes(brandInput.trim().toLowerCase()))
    .slice(0, 8);

  return (
    <div>
      <TopBar path={["CATALOG", "OPORTUNITĂȚI"]}>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className={showAddForm ? "btn-neutral" : "btn-cyan"}
        >
          {showAddForm ? <><X style={{ width: "13px", height: "13px" }} strokeWidth={2} /> Închide</> : <><Plus style={{ width: "13px", height: "13px" }} strokeWidth={2.2} /> Adaugă produs</>}
        </button>
      </TopBar>

      <PageHeading
        icon={Search}
        title="Descoperă Oportunități"
        subtitle={<>Caută produse și identifică oportunități de revânzare — <Hl>{products.length} produse</Hl> în vizualizare.</>}
      >
        <select
          value={sortBy}
          onChange={(e) => handleSortChange(e.target.value)}
          style={{ ...inputBaseStyle, width: "auto", cursor: "pointer", padding: "8px 12px" }}
        >
          <option value="newest">Sorteaza: Implicit</option>
          <option value="price_asc">Pret: crescator</option>
          <option value="price_desc">Pret: descrescator</option>
          <option value="roi_desc">ROI: descrescator</option>
          <option value="name_asc">Nume: A-Z</option>
        </select>
      </PageHeading>

      {/* Search bar + filter toggle */}
      <form onSubmit={handleSearch} style={{ marginTop: "16px" }}>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <div style={{ flex: 1, position: "relative" }}>
            <Search
              style={{
                position: "absolute", left: "0.75rem", top: "50%",
                transform: "translateY(-50%)", width: "18px", height: "18px",
                color: "var(--text-secondary)",
              }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cauta dupa nume, SKU, EAN, categorie..."
              style={{
                ...inputBaseStyle,
                paddingLeft: "2.5rem",
                paddingTop: "0.625rem",
                paddingBottom: "0.625rem",
              }}
            />
          </div>
          <button
            type="button"
            onClick={() => setShowFilters((s) => !s)}
            className={hasActiveFilters || showFilters ? "btn-cyan" : "btn-neutral"}
          >
            <Filter style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /> Filtre
          </button>
          <button type="submit" className="btn-cyan">
            Cauta
          </button>
        </div>
      </form>

      {/* Filter panel */}
      {showFilters && (
        <div
          style={{
            background: "var(--bg-card)", backdropFilter: "blur(20px)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-card)",
            padding: "1.25rem",
            marginBottom: "1.5rem",
          }}
        >
          {/* Rand 1: sursa magazin — reseteaza brand+categorie si reincarca optiunile din DB */}
          <div style={{ marginBottom: "1rem" }}>
            <label style={labelSmall}>Sursa (magazin)</label>
            <select
              value={filters.source}
              onChange={(e) => handleSourceChange(e.target.value)}
              style={inputBaseStyle}
            >
              {STORE_SOURCES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Rand 2: brand cu autocomplete (dropdown pozitionat absolut) */}
          <div style={{ marginBottom: "1rem", position: "relative" }}>
            <label style={labelSmall}>Brand</label>
            <input
              type="text"
              value={brandInput}
              onChange={(e) => {
                setBrandInput(e.target.value);
                setFilters((prev) => ({ ...prev, brand: e.target.value }));
                setShowBrandDropdown(true);
              }}
              onFocus={() => setShowBrandDropdown(true)}
              onBlur={() => setTimeout(() => setShowBrandDropdown(false), 150)}
              placeholder="ex: Samsung, Apple, Sony..."
              style={inputBaseStyle}
            />
            {showBrandDropdown && brandSuggestions.length > 0 && (
              <div style={{
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20,
                marginTop: "0.25rem", background: "var(--bg-card)", backdropFilter: "blur(20px)",
                border: "1px solid var(--border-color)", borderRadius: "10px",
                overflow: "hidden", boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
              }}>
                {brandSuggestions.map((b) => (
                  <button
                    key={b}
                    type="button"
                    onMouseDown={() => {
                      setFilters((prev) => ({ ...prev, brand: b }));
                      setBrandInput(b);
                      setShowBrandDropdown(false);
                    }}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "0.5rem 0.75rem", backgroundColor: "transparent",
                      border: "none", color: "var(--text-primary)", fontSize: "0.8125rem",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    {b}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Rand 3: categorie — valori reale din DB (GET /api/products/filter-options) */}
          <div style={{ marginBottom: "1rem" }}>
            <label style={labelSmall}>Categorie</label>
            <select
              value={filters.category || ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, category: e.target.value }))}
              style={inputBaseStyle}
            >
              <option value="">Toate categoriile</option>
              {(filterOptions.categories || []).map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          {/* Rand 4: pret min / max */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={labelSmall}>Pret minim</label>
              <input
                type="number" step="0.01" value={filters.price_min}
                onChange={(e) => setFilters((prev) => ({ ...prev, price_min: e.target.value }))}
                placeholder="ex: 50"
                style={inputBaseStyle}
              />
            </div>
            <div>
              <label style={labelSmall}>Pret maxim</label>
              <input
                type="number" step="0.01" value={filters.price_max}
                onChange={(e) => setFilters((prev) => ({ ...prev, price_max: e.target.value }))}
                placeholder="ex: 1000"
                style={inputBaseStyle}
              />
            </div>
          </div>

          {/* Rand 5: ROI min / max (%) — GE-2 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={labelSmall}>ROI minim (%)</label>
              <input
                type="number" step="0.1" value={filters.roi_min}
                onChange={(e) => setFilters((prev) => ({ ...prev, roi_min: e.target.value }))}
                placeholder="ex: 15"
                style={inputBaseStyle}
              />
            </div>
            <div>
              <label style={labelSmall}>ROI maxim (%)</label>
              <input
                type="number" step="0.1" value={filters.roi_max}
                onChange={(e) => setFilters((prev) => ({ ...prev, roi_max: e.target.value }))}
                placeholder="ex: 10"
                style={inputBaseStyle}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={handleApplyFilters} style={{
              padding: "9px 18px", borderRadius: "12px", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              display: "flex", alignItems: "center", gap: "0.375rem",
            }}>
              <Filter style={{ width: "14px", height: "14px" }} /> Aplica filtre
            </button>
            <button onClick={handleResetFilters} style={{
              padding: "0.5rem 1.25rem", borderRadius: "10px", backgroundColor: "transparent",
              color: "var(--text-secondary)", border: "1px solid var(--border-color)",
              cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              display: "flex", alignItems: "center", gap: "0.375rem",
            }}>
              <RefreshCcw style={{ width: "14px", height: "14px" }} /> Reseteaza
            </button>
          </div>
        </div>
      )}

      {/* Add product form */}
      {showAddForm && (
        <div
          style={{
            background: "var(--bg-card)", backdropFilter: "blur(20px)",
            border: "1px solid var(--border-color)",
            borderRadius: "12px",
            padding: "1.5rem",
            marginBottom: "1.5rem",
          }}
        >
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1.25rem" }}>
            Adauga produs nou
          </h2>
          <form onSubmit={handleAddProduct}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.25rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Nume produs *
                </label>
                <input type="text" value={newProduct.name} onChange={(e) => setNewProduct({...newProduct, name: e.target.value})}
                  required style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  SKU
                </label>
                <input type="text" value={newProduct.sku} onChange={(e) => setNewProduct({...newProduct, sku: e.target.value})}
                  placeholder="ex: MDE14ROA" style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  EAN (cod de bare)
                </label>
                <input type="text" value={newProduct.ean} onChange={(e) => setNewProduct({...newProduct, ean: e.target.value})}
                  style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Categorie
                </label>
                <input type="text" value={newProduct.category} onChange={(e) => setNewProduct({...newProduct, category: e.target.value})}
                  placeholder="ex: electronics" style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Sursa (magazin)
                </label>
                <input type="text" value={newProduct.source} onChange={(e) => setNewProduct({...newProduct, source: e.target.value})}
                  placeholder="ex: emag, altex" style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  URL sursa
                </label>
                <input type="url" value={newProduct.source_url} onChange={(e) => setNewProduct({...newProduct, source_url: e.target.value})}
                  placeholder="https://..." style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Pret achizitie
                </label>
                <input type="number" step="0.01" value={newProduct.current_price} onChange={(e) => setNewProduct({...newProduct, current_price: e.target.value})}
                  style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Pret estimat revanzare
                </label>
                <input type="number" step="0.01" value={newProduct.resale_price} onChange={(e) => setNewProduct({...newProduct, resale_price: e.target.value})}
                  placeholder="(optional)" style={inputBaseStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                  Moneda
                </label>
                <select value={newProduct.currency} onChange={(e) => setNewProduct({...newProduct, currency: e.target.value})}
                  style={inputBaseStyle}>
                  <option value="EUR">EUR</option>
                  <option value="RON">RON</option>
                </select>
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <button type="submit" style={{
                padding: "9px 18px", borderRadius: "12px", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", border: "none", cursor: "pointer", fontSize: "0.875rem", fontWeight: 500,
              }}>
                Salveaza
              </button>
              <button type="button" onClick={() => setShowAddForm(false)} style={{
                padding: "0.5rem 1.25rem", borderRadius: "10px", backgroundColor: "transparent",
                color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.875rem",
              }}>
                Anuleaza
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Products list */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "8rem" }}>
          <div style={{ width: "2rem", height: "2rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : products.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {products.map((product) => (
            <div
              key={product.id}
              style={{
                background: "var(--bg-card)", backdropFilter: "blur(20px)",
                border: "1px solid var(--border-color)",
                borderRadius: "12px",
                padding: "1.25rem",
                transition: "border-color 0.15s ease",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(59,130,246,0.3)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-color)"; }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
                    <Link href={`/dashboard/products/detail?id=${product.id}`} style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, textDecoration: "none" }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = "var(--blue-light)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
                    >{product.name}</Link>
                    {product.sku && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard(product.sku, `sku-${product.id}`)}
                        title="Click pentru a copia SKU-ul"
                        style={codeChipStyle("74,222,128", "#4ade80", copiedKey === `sku-${product.id}`)}
                      >
                        {copiedKey === `sku-${product.id}` ? "Copiat!" : `SKU: ${product.sku}`}
                      </button>
                    )}
                    {product.ean && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard(product.ean, `ean-${product.id}`)}
                        title="Click pentru a copia EAN-ul"
                        style={codeChipStyle("253,224,71", "#fde047", copiedKey === `ean-${product.id}`)}
                      >
                        {copiedKey === `ean-${product.id}` ? "Copiat!" : `EAN: ${product.ean}`}
                      </button>
                    )}
                    {product.source && (
                      product.source_url ? (
                        <button
                          type="button"
                          onClick={() => copyToClipboard(product.source_url, `url-${product.id}`)}
                          title="Click pentru a copia linkul sursei"
                          style={codeChipStyle("147,51,234", "#c4b5fd", copiedKey === `url-${product.id}`)}
                        >
                          {copiedKey === `url-${product.id}` ? "Copiat!" : product.source}
                        </button>
                      ) : (
                        <span style={{ ...codeChipStyle("147,51,234", "#c4b5fd", false), cursor: "default" }}>
                          {product.source}
                        </span>
                      )
                    )}
                    <RoiBadge price={product.current_price} resale={product.resale_price} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                    {product.current_price != null && (
                      <span style={{ fontSize: "18px", fontWeight: 700, letterSpacing: "-.4px", color: "#ffffff" }}>
                        {product.current_price} <span style={{ fontSize: "11.5px", fontWeight: 500, color: "var(--text-tertiary)" }}>{product.currency}</span>
                      </span>
                    )}
                    {/* Resale price inline edit */}
                    {inlineResaleId === product.id ? (
                      <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                        <Tag style={{ width: "14px", height: "14px", color: "var(--text-secondary)" }} />
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Pret revanzare:</span>
                        <input
                          type="number" step="0.01"
                          value={inlineResaleValue}
                          onChange={(e) => setInlineResaleValue(e.target.value)}
                          autoFocus
                          style={{
                            ...inputBaseStyle, width: "120px", padding: "0.25rem 0.5rem",
                            fontSize: "0.8125rem",
                          }}
                        />
                        <button
                          type="button"
                          disabled={inlineResaleSaving}
                          onClick={() => saveInlineResale(product)}
                          style={{
                            padding: "0.25rem 0.625rem", borderRadius: "8px",
                            backgroundColor: "var(--green-primary)", color: "var(--text-primary)",
                            border: "none", cursor: "pointer", fontSize: "0.75rem",
                            display: "flex", alignItems: "center", gap: "0.25rem",
                          }}
                        >
                          <Save style={{ width: "12px", height: "12px" }} /> Salveaza
                        </button>
                        <button
                          type="button"
                          onClick={cancelInlineResale}
                          style={{
                            padding: "0.25rem 0.5rem", borderRadius: "8px",
                            backgroundColor: "transparent", color: "var(--text-secondary)",
                            border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.75rem",
                          }}
                        >
                          Anuleaza
                        </button>
                      </span>
                    ) : product.resale_price != null ? (
                      <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                        <Tag style={{ width: "14px", height: "14px", color: "#a78bfa" }} />
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Pret revanzare:</span>
                        <span style={{ fontSize: "0.9375rem", fontWeight: 600, color: "#a78bfa" }}>
                          {product.resale_price} {product.currency}
                        </span>
                        <button
                          type="button"
                          onClick={() => startInlineResale(product)}
                          title="Editeaza pretul de revanzare"
                          style={{
                            padding: "0.125rem", borderRadius: "0.25rem",
                            backgroundColor: "transparent", border: "none",
                            cursor: "pointer", color: "var(--text-secondary)",
                            display: "flex",
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-secondary)"; }}
                        >
                          <Pencil style={{ width: "12px", height: "12px" }} />
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startInlineResale(product)}
                        style={{
                          padding: "0.25rem 0.625rem", borderRadius: "8px",
                          backgroundColor: "transparent",
                          color: "#8fb5f7", border: "1px dashed var(--border-color)",
                          cursor: "pointer", fontSize: "0.75rem",
                          display: "flex", alignItems: "center", gap: "0.25rem",
                        }}
                      >
                        <Plus style={{ width: "12px", height: "12px" }} /> Adauga pret revanzare
                      </button>
                    )}
                    {product.category && (
                      <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        Categorie: {product.category}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <button
                    onClick={() => handleTrackProduct(product.id)}
                    title="Urmareste produsul (monitorizare pret)"
                    style={{
                      padding: "0.5rem", borderRadius: "10px", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "#a78bfa"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Eye style={{ width: "18px", height: "18px" }} />
                  </button>
                  {product.source_url && (
                    <a
                      href={product.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Deschide sursa"
                      style={{
                        padding: "0.5rem", borderRadius: "10px", display: "flex",
                        color: "var(--text-secondary)", transition: "all 0.15s ease", textDecoration: "none",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "var(--blue-light)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                    >
                      <ExternalLink style={{ width: "18px", height: "18px" }} />
                    </a>
                  )}
                  <button
                    onClick={() => (editingId === product.id ? cancelEdit() : startEdit(product))}
                    title={editingId === product.id ? "Anuleaza editarea" : "Editeaza produs"}
                    style={{
                      padding: "0.5rem", borderRadius: "10px",
                      backgroundColor: editingId === product.id ? "rgba(96,165,250,0.15)" : "transparent",
                      border: "none", cursor: "pointer",
                      color: editingId === product.id ? "var(--blue-light)" : "var(--text-secondary)",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { if (editingId !== product.id) { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "var(--blue-light)"; } }}
                    onMouseLeave={(e) => { if (editingId !== product.id) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; } }}
                  >
                    <Pencil style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleDeleteProduct(product)}
                    title="Sterge produs din baza de date"
                    style={{
                      padding: "0.5rem", borderRadius: "10px", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(248,113,113,0.1)"; e.currentTarget.style.color = "#f87171"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Trash2 style={{ width: "18px", height: "18px" }} />
                  </button>
                  <Link
                    href={`/dashboard/products/detail?id=${product.id}`}
                    title="Vezi detalii"
                    style={{ padding: "0.5rem", borderRadius: "10px", display: "flex", color: "var(--text-secondary)", textDecoration: "none", transition: "all 0.15s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text-primary)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <ChevronRight style={{ width: "18px", height: "18px" }} />
                  </Link>
                </div>
              </div>

              {editingId === product.id && (
                <form
                  onSubmit={handleSaveEdit}
                  style={{
                    marginTop: "1rem",
                    paddingTop: "1rem",
                    borderTop: "1px solid var(--border-color)",
                  }}
                >
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.875rem" }}>
                    <div style={{ gridColumn: "1 / span 2" }}>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Nume produs *
                      </label>
                      <input type="text" value={editValues.name}
                        onChange={(e) => setEditValues({ ...editValues, name: e.target.value })}
                        required style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        SKU
                      </label>
                      <input type="text" value={editValues.sku}
                        onChange={(e) => setEditValues({ ...editValues, sku: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        EAN (cod de bare)
                      </label>
                      <input type="text" value={editValues.ean}
                        onChange={(e) => setEditValues({ ...editValues, ean: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Categorie
                      </label>
                      <input type="text" value={editValues.category}
                        onChange={(e) => setEditValues({ ...editValues, category: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Sursa (magazin)
                      </label>
                      <input type="text" value={editValues.source}
                        onChange={(e) => setEditValues({ ...editValues, source: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div style={{ gridColumn: "1 / span 2" }}>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        URL sursa
                      </label>
                      <input type="url" value={editValues.source_url}
                        onChange={(e) => setEditValues({ ...editValues, source_url: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Pret achizitie
                      </label>
                      <input type="number" step="0.01" value={editValues.current_price}
                        onChange={(e) => setEditValues({ ...editValues, current_price: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Pret estimat revanzare
                      </label>
                      <input type="number" step="0.01" value={editValues.resale_price}
                        onChange={(e) => setEditValues({ ...editValues, resale_price: e.target.value })}
                        style={inputBaseStyle} />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.25rem", color: "var(--text-secondary)" }}>
                        Moneda
                      </label>
                      <select value={editValues.currency}
                        onChange={(e) => setEditValues({ ...editValues, currency: e.target.value })}
                        style={inputBaseStyle}>
                        <option value="EUR">EUR</option>
                        <option value="RON">RON</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button type="submit" disabled={editSaving} style={{
                      padding: "9px 16px", borderRadius: "12px", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", border: "none", cursor: editSaving ? "wait" : "pointer",
                      fontSize: "0.8125rem", fontWeight: 500, opacity: editSaving ? 0.7 : 1,
                    }}>
                      {editSaving ? "Se salveaza..." : "Salveaza modificarile"}
                    </button>
                    <button type="button" onClick={cancelEdit} style={{
                      padding: "0.5rem 1rem", borderRadius: "10px", backgroundColor: "transparent",
                      color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem",
                    }}>
                      Anuleaza
                    </button>
                  </div>
                </form>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div
          style={{
            background: "var(--bg-card)", backdropFilter: "blur(20px)",
            border: "1px solid var(--border-color)",
            borderRadius: "12px",
            padding: "3rem",
            textAlign: "center",
          }}
        >
          <Package style={{ width: "3rem", height: "3rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>Niciun produs gasit</p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Adauga produse folosind butonul de mai sus, ajusteaza filtrele sau cauta dupa un alt termen.
          </p>
        </div>
      )}
    </div>
  );
}
