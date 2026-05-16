"use client";
import { useState, useEffect } from "react";
import { productsAPI, watchlistAPI, favoritesAPI } from "@/lib/api";
import Link from "next/link";
import { Search, Plus, Eye, ExternalLink, Package, X, ChevronRight, Trash2, Heart, Ban, Pencil, Tag, Save, Filter, RefreshCcw } from "lucide-react";

function computeRoi(price, resale) {
  if (resale == null || price == null) return null;
  const p = Number(price), r = Number(resale);
  if (!isFinite(p) || !isFinite(r) || p <= 0) return null;
  return ((r - p) / p) * 100;
}

function RoiBadge({ price, resale }) {
  const roi = computeRoi(price, resale);
  if (roi == null) return null;
  let bg, color, label;
  if (roi >= 30) { bg = "rgba(22,163,74,0.15)"; color = "#4ade80"; label = `ROI ridicat ${roi.toFixed(1)}%`; }
  else if (roi >= 15) { bg = "rgba(234,179,8,0.15)"; color = "#facc15"; label = `ROI mediu ${roi.toFixed(1)}%`; }
  else if (roi >= 0) { bg = "rgba(251,146,60,0.15)"; color = "#fb923c"; label = `ROI scazut ${roi.toFixed(1)}%`; }
  else { bg = "rgba(239,68,68,0.15)"; color = "#f87171"; label = "Neprofitabil"; }
  return (
    <span style={{
      padding: "2px 8px", borderRadius: "20px",
      fontSize: "11px", fontWeight: 600,
      backgroundColor: bg, color,
    }}>
      {label}
    </span>
  );
}

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [filterOptions, setFilterOptions] = useState({ brands: [], categories: [] });
  const [filters, setFilters] = useState({
    brand: "", category: "", price_min: "", price_max: "", roi_min: "",
  });

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
    loadProducts();
    loadFilterOptions();
  }, []);

  const loadFilterOptions = async () => {
    try {
      const res = await productsAPI.getFilterOptions();
      setFilterOptions(res.data || { brands: [], categories: [] });
    } catch (e) {
      console.error("Eroare la incarcarea optiunilor de filtrare:", e);
    }
  };

  const loadProducts = async (overrides = null) => {
    setLoading(true);
    try {
      const f = overrides ?? filters;
      const params = {};
      if (search.trim()) params.search = search.trim();
      if (f.brand) params.brand = f.brand;
      if (f.category) params.category = f.category;
      if (f.price_min !== "" && f.price_min != null) params.price_min = parseFloat(f.price_min);
      if (f.price_max !== "" && f.price_max != null) params.price_max = parseFloat(f.price_max);
      if (f.roi_min !== "" && f.roi_min != null) params.roi_min = parseFloat(f.roi_min);
      if (sortBy) params.sort_by = sortBy;
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
    const cleared = { brand: "", category: "", price_min: "", price_max: "", roi_min: "" };
    setFilters(cleared);
    setSearch("");
    loadProducts(cleared);
  };

  const handleSortChange = (value) => {
    setSortBy(value);
    setTimeout(() => loadProducts(), 0);
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
      loadFilterOptions();
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la adaugare produs");
    }
  };

  const handleAddToWatchlist = async (productId) => {
    try {
      await watchlistAPI.addToWatchlist({ product_id: productId });
      alert("Produs adaugat in Radar Preturi!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare");
    }
  };

  const handleAddToFavorites = async (productId) => {
    try {
      await favoritesAPI.addFavorite({ product_id: productId, is_blacklisted: false });
      alert("Produs adaugat la oportunitati salvate!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la salvare");
    }
  };

  const handleAddToBlacklist = async (productId) => {
    if (!window.confirm("Adaugi produsul in blacklist? Acesta nu va mai aparea in recomandari.")) return;
    try {
      await favoritesAPI.addFavorite({ product_id: productId, is_blacklisted: true });
      alert("Produs adaugat in blacklist!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la adaugarea in blacklist");
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
      `Esti sigur ca vrei sa stergi produsul "${product.name}"?\n\nAceasta actiune este ireversibila si va sterge si:\n- Istoricul de preturi\n- Alertele asociate\n- Intrarile din Radar Preturi ale tuturor utilizatorilor`
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
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.5rem",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    width: "100%",
    outline: "none",
  };

  const hasActiveFilters =
    filters.brand || filters.category ||
    filters.price_min !== "" || filters.price_max !== "" ||
    filters.roi_min !== "";

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Descopera Oportunitati</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Cauta produse si identifica oportunitati de revanzare
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <select
            value={sortBy}
            onChange={(e) => handleSortChange(e.target.value)}
            style={{ ...inputBaseStyle, width: "auto", cursor: "pointer", paddingTop: "0.5rem", paddingBottom: "0.5rem" }}
          >
            <option value="newest">Sorteaza: Implicit</option>
            <option value="price_asc">Pret: crescator</option>
            <option value="price_desc">Pret: descrescator</option>
            <option value="roi_desc">ROI: descrescator</option>
            <option value="name_asc">Nume: A-Z</option>
          </select>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              display: "flex", alignItems: "center", gap: "0.5rem",
              padding: "0.5rem 1rem", borderRadius: "0.5rem",
              backgroundColor: showAddForm ? "transparent" : "var(--blue-primary)",
              color: showAddForm ? "var(--text-secondary)" : "white",
              border: showAddForm ? "1px solid var(--border-color)" : "none",
              cursor: "pointer", fontSize: "0.875rem", fontWeight: 500,
              transition: "all 0.15s ease",
            }}
          >
            {showAddForm ? <><X style={{ width: "16px", height: "16px" }} /> Inchide</> : <><Plus style={{ width: "16px", height: "16px" }} /> Adauga Produs</>}
          </button>
        </div>
      </div>

      {/* Search bar + filter toggle */}
      <form onSubmit={handleSearch} style={{ marginBottom: "1rem" }}>
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
            style={{
              padding: "0.625rem 1rem", borderRadius: "0.5rem",
              backgroundColor: hasActiveFilters || showFilters ? "var(--blue-dim)" : "transparent",
              color: hasActiveFilters || showFilters ? "var(--blue-light)" : "var(--text-secondary)",
              border: "1px solid var(--border-color)", cursor: "pointer",
              fontSize: "0.875rem", fontWeight: 500,
              display: "flex", alignItems: "center", gap: "0.5rem",
            }}
          >
            <Filter style={{ width: "16px", height: "16px" }} /> Filtre
          </button>
          <button
            type="submit"
            style={{
              padding: "0.625rem 1.25rem", borderRadius: "0.5rem",
              backgroundColor: "var(--blue-primary)", color: "var(--text-primary)",
              border: "none", cursor: "pointer",
              fontSize: "0.875rem", fontWeight: 500,
            }}
          >
            Cauta
          </button>
        </div>
      </form>

      {/* Filter panel */}
      {showFilters && (
        <div
          style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-card)",
            padding: "1.25rem",
            marginBottom: "1.5rem",
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                Brand
              </label>
              <select
                value={filters.brand}
                onChange={(e) => setFilters({ ...filters, brand: e.target.value })}
                style={inputBaseStyle}
              >
                <option value="">Toate brandurile</option>
                {filterOptions.brands.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                Categorie
              </label>
              <select
                value={filters.category}
                onChange={(e) => setFilters({ ...filters, category: e.target.value })}
                style={inputBaseStyle}
              >
                <option value="">Toate categoriile</option>
                {filterOptions.categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                Pret minim (RON)
              </label>
              <input
                type="number" step="0.01" value={filters.price_min}
                onChange={(e) => setFilters({ ...filters, price_min: e.target.value })}
                placeholder="ex: 50"
                style={inputBaseStyle}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                Pret maxim (RON)
              </label>
              <input
                type="number" step="0.01" value={filters.price_max}
                onChange={(e) => setFilters({ ...filters, price_max: e.target.value })}
                placeholder="ex: 1000"
                style={inputBaseStyle}
              />
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.375rem", color: "var(--text-secondary)" }}>
                ROI minim (%)
              </label>
              <input
                type="number" step="0.1" value={filters.roi_min}
                onChange={(e) => setFilters({ ...filters, roi_min: e.target.value })}
                placeholder="ex: 20"
                style={inputBaseStyle}
              />
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={handleApplyFilters} style={{
              padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)",
              color: "var(--text-primary)", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              display: "flex", alignItems: "center", gap: "0.375rem",
            }}>
              <Filter style={{ width: "14px", height: "14px" }} /> Aplica filtre
            </button>
            <button onClick={handleResetFilters} style={{
              padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent",
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
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "0.75rem",
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
                padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)",
                color: "var(--text-primary)", border: "none", cursor: "pointer", fontSize: "0.875rem", fontWeight: 500,
              }}>
                Salveaza
              </button>
              <button type="button" onClick={() => setShowAddForm(false)} style={{
                padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent",
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
          <div style={{ width: "2rem", height: "2rem", border: "3px solid var(--blue-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : products.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {products.map((product) => (
            <div
              key={product.id}
              style={{
                backgroundColor: "var(--bg-card)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.75rem",
                padding: "1.25rem",
                transition: "border-color 0.15s ease",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(59,130,246,0.3)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-color)"; }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
                    <Link href={`/dashboard/products/${product.id}`} style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, textDecoration: "none" }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = "var(--blue-light)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
                    >{product.name}</Link>
                    {product.sku && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard(product.sku, `sku-${product.id}`)}
                        title="Click pentru a copia SKU-ul"
                        style={{
                          padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                          backgroundColor: copiedKey === `sku-${product.id}` ? "rgba(34,197,94,0.35)" : "rgba(34,197,94,0.15)",
                          color: "#4ade80", fontFamily: "monospace",
                          border: "none", cursor: "pointer",
                        }}
                      >
                        {copiedKey === `sku-${product.id}` ? "Copiat!" : `SKU: ${product.sku}`}
                      </button>
                    )}
                    {product.ean && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard(product.ean, `ean-${product.id}`)}
                        title="Click pentru a copia EAN-ul"
                        style={{
                          padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                          backgroundColor: copiedKey === `ean-${product.id}` ? "rgba(234,179,8,0.35)" : "rgba(234,179,8,0.15)",
                          color: "#facc15", fontFamily: "monospace",
                          border: "none", cursor: "pointer",
                        }}
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
                          style={{
                            padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                            backgroundColor: copiedKey === `url-${product.id}` ? "rgba(147,51,234,0.35)" : "rgba(147,51,234,0.15)",
                            color: "#a78bfa", border: "none", cursor: "pointer",
                          }}
                        >
                          {copiedKey === `url-${product.id}` ? "Copiat!" : product.source}
                        </button>
                      ) : (
                        <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(147,51,234,0.15)", color: "#a78bfa" }}>
                          {product.source}
                        </span>
                      )
                    )}
                    <RoiBadge price={product.current_price} resale={product.resale_price} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                    {product.current_price != null && (
                      <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "#4ade80" }}>
                        {product.current_price} {product.currency}
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
                            padding: "0.25rem 0.625rem", borderRadius: "0.375rem",
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
                            padding: "0.25rem 0.5rem", borderRadius: "0.375rem",
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
                          padding: "0.25rem 0.625rem", borderRadius: "0.375rem",
                          backgroundColor: "transparent",
                          color: "var(--blue-light)", border: "1px dashed var(--border-color)",
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
                    onClick={() => handleAddToWatchlist(product.id)}
                    title="Adauga in Radar Preturi"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "#a78bfa"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Eye style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleAddToFavorites(product.id)}
                    title="Salveaza oportunitatea"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "#f472b6"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Heart style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleAddToBlacklist(product.id)}
                    title="Adauga in blacklist"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--bg-hover)"; e.currentTarget.style.color = "#fb923c"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Ban style={{ width: "18px", height: "18px" }} />
                  </button>
                  {product.source_url && (
                    <a
                      href={product.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Deschide sursa"
                      style={{
                        padding: "0.5rem", borderRadius: "0.5rem", display: "flex",
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
                      padding: "0.5rem", borderRadius: "0.5rem",
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
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "var(--text-secondary)", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(248,113,113,0.1)"; e.currentTarget.style.color = "#f87171"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; }}
                  >
                    <Trash2 style={{ width: "18px", height: "18px" }} />
                  </button>
                  <Link
                    href={`/dashboard/products/${product.id}`}
                    title="Vezi detalii"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", display: "flex", color: "var(--text-secondary)", textDecoration: "none", transition: "all 0.15s ease" }}
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
                      padding: "0.5rem 1rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)",
                      color: "var(--text-primary)", border: "none", cursor: editSaving ? "wait" : "pointer",
                      fontSize: "0.8125rem", fontWeight: 500, opacity: editSaving ? 0.7 : 1,
                    }}>
                      {editSaving ? "Se salveaza..." : "Salveaza modificarile"}
                    </button>
                    <button type="button" onClick={cancelEdit} style={{
                      padding: "0.5rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent",
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
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "0.75rem",
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
