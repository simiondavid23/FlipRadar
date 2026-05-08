"use client";
import { useState, useEffect, useMemo } from "react";
import { productsAPI, watchlistAPI, favoritesAPI } from "@/lib/api";
import Link from "next/link";
import { Search, Plus, Eye, ExternalLink, Package, X, ChevronRight, Trash2, Heart, Ban, Pencil } from "lucide-react";

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProduct, setNewProduct] = useState({
    name: "", sku: "", ean: "", category: "", source: "", source_url: "",
    current_price: "", currency: "EUR", image_url: "", description: "",
  });
  const [editingId, setEditingId] = useState(null);
  const [editValues, setEditValues] = useState({
    name: "", sku: "", ean: "", category: "", source: "", source_url: "",
    current_price: "", currency: "EUR",
  });
  const [editSaving, setEditSaving] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);

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
  }, []);

  const loadProducts = async (searchQuery = "") => {
    setLoading(true);
    try {
      const params = searchQuery ? { search: searchQuery } : {};
      const response = await productsAPI.getProducts(params);
      setProducts(response.data);
    } catch (error) {
      console.error("Error loading products:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    loadProducts(search);
  };

  const handleAddProduct = async (e) => {
    e.preventDefault();
    try {
      const productData = {
        ...newProduct,
        current_price: newProduct.current_price ? parseFloat(newProduct.current_price) : null,
      };
      await productsAPI.createProduct(productData);
      setShowAddForm(false);
      setNewProduct({ name: "", sku: "", ean: "", category: "", source: "", source_url: "", current_price: "", currency: "EUR", image_url: "", description: "" });
      loadProducts();
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la adaugare produs");
    }
  };

  const handleAddToWatchlist = async (productId) => {
    try {
      await watchlistAPI.addToWatchlist({ product_id: productId });
      alert("Produs adaugat in watchlist!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare");
    }
  };

  const handleAddToFavorites = async (productId) => {
    try {
      await favoritesAPI.addFavorite({ product_id: productId, is_blacklisted: false });
      alert("Produs adaugat la favorite!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la adaugarea in favorite");
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
      currency: product.currency || "EUR",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

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

  const handleDeleteProduct = async (product) => {
    const ok = window.confirm(
      `Esti sigur ca vrei sa stergi produsul "${product.name}"?\n\nAceasta actiune este ireversibila si va sterge si:\n- Istoricul de preturi\n- Alertele asociate\n- Intrarile din watchlist ale tuturor utilizatorilor`
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
    color: "white",
    fontSize: "0.875rem",
    width: "100%",
    outline: "none",
  };

  const sortedProducts = useMemo(() => {
    return [...products].sort((a, b) => {
      switch (sortBy) {
        case "name_asc": return (a.name || "").localeCompare(b.name || "");
        case "name_desc": return (b.name || "").localeCompare(a.name || "");
        case "price_asc": return (a.current_price || 0) - (b.current_price || 0);
        case "price_desc": return (b.current_price || 0) - (a.current_price || 0);
        default: return 0;
      }
    });
  }, [products, sortBy]);

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>Cauta Produse</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Cauta, adauga si analizeaza produse
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 1rem",
            borderRadius: "0.5rem",
            backgroundColor: showAddForm ? "transparent" : "#2563eb",
            color: showAddForm ? "#94a3b8" : "white",
            border: showAddForm ? "1px solid var(--border-color)" : "none",
            cursor: "pointer",
            fontSize: "0.875rem",
            fontWeight: 500,
            transition: "all 0.15s ease",
          }}
        >
          {showAddForm ? <><X style={{ width: "16px", height: "16px" }} /> Inchide</> : <><Plus style={{ width: "16px", height: "16px" }} /> Adauga Produs</>}
        </button>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSearch} style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <div style={{ flex: 1, position: "relative" }}>
            <Search
              style={{
                position: "absolute",
                left: "0.75rem",
                top: "50%",
                transform: "translateY(-50%)",
                width: "18px",
                height: "18px",
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
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            style={{
              ...inputBaseStyle,
              width: "auto",
              paddingTop: "0.625rem",
              paddingBottom: "0.625rem",
              cursor: "pointer",
            }}
          >
            <option value="newest">Cele mai noi</option>
            <option value="name_asc">Nume A-Z</option>
            <option value="name_desc">Nume Z-A</option>
            <option value="price_asc">Pret crescator</option>
            <option value="price_desc">Pret descrescator</option>
          </select>
          <button
            type="submit"
            style={{
              padding: "0.625rem 1.25rem",
              borderRadius: "0.5rem",
              backgroundColor: "#2563eb",
              color: "white",
              border: "none",
              cursor: "pointer",
              fontSize: "0.875rem",
              fontWeight: 500,
            }}
          >
            Cauta
          </button>
        </div>
      </form>

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
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "white", marginBottom: "1.25rem" }}>
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
                  Pret curent
                </label>
                <input type="number" step="0.01" value={newProduct.current_price} onChange={(e) => setNewProduct({...newProduct, current_price: e.target.value})}
                  style={inputBaseStyle} />
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
                padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "#2563eb",
                color: "white", border: "none", cursor: "pointer", fontSize: "0.875rem", fontWeight: 500,
              }}>
                Salveaza
              </button>
              <button type="button" onClick={() => setShowAddForm(false)} style={{
                padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                color: "#94a3b8", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.875rem",
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
          <div style={{ width: "2rem", height: "2rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : sortedProducts.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {sortedProducts.map((product) => (
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
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.5rem" }}>
                    <Link href={`/dashboard/products/${product.id}`} style={{ fontSize: "0.9375rem", fontWeight: 600, color: "white", margin: 0, textDecoration: "none" }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = "#60a5fa"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = "white"; }}
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
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    {product.current_price && (
                      <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "#4ade80" }}>
                        {product.current_price} {product.currency}
                      </span>
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
                    title="Adauga in watchlist"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#a78bfa"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                  >
                    <Eye style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleAddToFavorites(product.id)}
                    title="Adauga la favorite"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#f472b6"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                  >
                    <Heart style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleAddToBlacklist(product.id)}
                    title="Adauga in blacklist"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#fb923c"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
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
                        color: "#94a3b8", transition: "all 0.15s ease", textDecoration: "none",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#60a5fa"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
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
                      color: editingId === product.id ? "#60a5fa" : "#94a3b8",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { if (editingId !== product.id) { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#60a5fa"; } }}
                    onMouseLeave={(e) => { if (editingId !== product.id) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; } }}
                  >
                    <Pencil style={{ width: "18px", height: "18px" }} />
                  </button>
                  <button
                    onClick={() => handleDeleteProduct(product)}
                    title="Sterge produs din baza de date"
                    style={{
                      padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(248,113,113,0.1)"; e.currentTarget.style.color = "#f87171"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                  >
                    <Trash2 style={{ width: "18px", height: "18px" }} />
                  </button>
                  <Link
                    href={`/dashboard/products/${product.id}`}
                    title="Vezi detalii"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", display: "flex", color: "#94a3b8", textDecoration: "none", transition: "all 0.15s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "white"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
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
                        Pret curent
                      </label>
                      <input type="number" step="0.01" value={editValues.current_price}
                        onChange={(e) => setEditValues({ ...editValues, current_price: e.target.value })}
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
                      padding: "0.5rem 1rem", borderRadius: "0.5rem", backgroundColor: "#2563eb",
                      color: "white", border: "none", cursor: editSaving ? "wait" : "pointer",
                      fontSize: "0.8125rem", fontWeight: 500, opacity: editSaving ? 0.7 : 1,
                    }}>
                      {editSaving ? "Se salveaza..." : "Salveaza modificarile"}
                    </button>
                    <button type="button" onClick={cancelEdit} style={{
                      padding: "0.5rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent",
                      color: "#94a3b8", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem",
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
          <p style={{ fontSize: "1rem", color: "white", marginBottom: "0.375rem" }}>Niciun produs gasit</p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Adauga produse folosind butonul de mai sus sau cauta dupa un alt termen.
          </p>
        </div>
      )}
    </div>
  );
}
