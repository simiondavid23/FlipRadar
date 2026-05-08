"use client";
import { useState, useEffect, useMemo } from "react";
import { watchlistAPI } from "@/lib/api";
import { Eye, Trash2, ExternalLink, Pencil, Check, X } from "lucide-react";

export default function WatchlistPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState("newest");
  const [editingId, setEditingId] = useState(null);
  const [noteDraft, setNoteDraft] = useState("");

  useEffect(() => {
    loadWatchlist();
  }, []);

  const loadWatchlist = async () => {
    try {
      const response = await watchlistAPI.getWatchlist();
      setItems(response.data);
    } catch (error) {
      console.error("Error loading watchlist:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (itemId) => {
    if (!confirm("Esti sigur ca vrei sa elimini acest produs din watchlist?")) return;
    try {
      await watchlistAPI.removeFromWatchlist(itemId);
      setItems(items.filter((item) => item.id !== itemId));
    } catch (error) {
      console.error("Error removing item:", error);
    }
  };

  const startEdit = (item) => {
    setEditingId(item.id);
    setNoteDraft(item.notes || "");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setNoteDraft("");
  };

  const saveNote = async (itemId) => {
    try {
      const res = await watchlistAPI.updateWatchlist(itemId, { notes: noteDraft });
      setItems(items.map((it) => (it.id === itemId ? { ...it, notes: res.data.notes } : it)));
      setEditingId(null);
      setNoteDraft("");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la salvare");
    }
  };

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      switch (sortBy) {
        case "name_asc": return (a.product?.name || "").localeCompare(b.product?.name || "");
        case "name_desc": return (b.product?.name || "").localeCompare(a.product?.name || "");
        case "price_asc": return (a.product?.current_price || 0) - (b.product?.current_price || 0);
        case "price_desc": return (b.product?.current_price || 0) - (a.product?.current_price || 0);
        default: return 0;
      }
    });
  }, [items, sortBy]);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const selectStyle = {
    backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.5rem", padding: "0.375rem 0.625rem", color: "white",
    fontSize: "0.8125rem", outline: "none", cursor: "pointer",
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>Watchlist</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Produsele pe care le urmaresti ({items.length} produse)
          </p>
        </div>
        {items.length > 0 && (
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={selectStyle}>
            <option value="newest">Cele mai noi</option>
            <option value="name_asc">Nume A-Z</option>
            <option value="name_desc">Nume Z-A</option>
            <option value="price_asc">Pret crescator</option>
            <option value="price_desc">Pret descrescator</option>
          </select>
        )}
      </div>

      {sortedItems.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {sortedItems.map((item) => (
            <div
              key={item.id}
              style={{
                backgroundColor: "var(--bg-card)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.75rem",
                padding: "1.25rem",
                transition: "border-color 0.15s ease",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(147,51,234,0.3)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-color)"; }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.375rem" }}>
                    <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "white", margin: 0 }}>
                      {item.product?.name || `Produs #${item.product_id}`}
                    </h3>
                    {item.product?.source && (
                      <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(147,51,234,0.15)", color: "#a78bfa" }}>
                        {item.product.source}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                    {item.product?.current_price && (
                      <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "#4ade80" }}>
                        {item.product.current_price} {item.product.currency}
                      </span>
                    )}
                    {editingId === item.id ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flex: 1, minWidth: "200px" }}>
                        <input
                          type="text"
                          value={noteDraft}
                          onChange={(e) => setNoteDraft(e.target.value)}
                          placeholder="Adauga o nota..."
                          autoFocus
                          style={{
                            flex: 1, backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                            borderRadius: "0.375rem", padding: "0.375rem 0.625rem", color: "white",
                            fontSize: "0.8125rem", outline: "none",
                          }}
                        />
                        <button
                          onClick={() => saveNote(item.id)}
                          title="Salveaza"
                          style={{ padding: "0.375rem", borderRadius: "0.375rem", backgroundColor: "rgba(34,197,94,0.15)", color: "#4ade80", border: "none", cursor: "pointer" }}
                        >
                          <Check style={{ width: "14px", height: "14px" }} />
                        </button>
                        <button
                          onClick={cancelEdit}
                          title="Anuleaza"
                          style={{ padding: "0.375rem", borderRadius: "0.375rem", backgroundColor: "rgba(148,163,184,0.15)", color: "#94a3b8", border: "none", cursor: "pointer" }}
                        >
                          <X style={{ width: "14px", height: "14px" }} />
                        </button>
                      </div>
                    ) : (
                      <>
                        {item.notes ? (
                          <span style={{ fontSize: "0.8125rem", fontStyle: "italic", color: "var(--text-secondary)" }}>
                            &ldquo;{item.notes}&rdquo;
                          </span>
                        ) : (
                          <span style={{ fontSize: "0.8125rem", fontStyle: "italic", color: "#475569" }}>
                            Fara nota
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  <p style={{ fontSize: "0.75rem", marginTop: "0.375rem", color: "var(--text-secondary)" }}>
                    Adaugat la: {new Date(item.added_at).toLocaleDateString("ro-RO")}
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  {editingId !== item.id && (
                    <button
                      onClick={() => startEdit(item)}
                      title="Editeaza nota"
                      style={{ padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent", border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease" }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(59,130,246,0.1)"; e.currentTarget.style.color = "#60a5fa"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                    >
                      <Pencil style={{ width: "18px", height: "18px" }} />
                    </button>
                  )}
                  {item.product?.source_url && (
                    <a
                      href={item.product.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Deschide sursa"
                      style={{ padding: "0.5rem", borderRadius: "0.5rem", display: "flex", color: "#94a3b8", textDecoration: "none", transition: "all 0.15s ease" }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "#60a5fa"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                    >
                      <ExternalLink style={{ width: "18px", height: "18px" }} />
                    </a>
                  )}
                  <button
                    onClick={() => handleRemove(item.id)}
                    title="Elimina din watchlist"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", backgroundColor: "transparent", border: "none", cursor: "pointer", color: "#94a3b8", transition: "all 0.15s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(239,68,68,0.1)"; e.currentTarget.style.color = "#f87171"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                  >
                    <Trash2 style={{ width: "18px", height: "18px" }} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          padding: "3rem",
          textAlign: "center",
        }}>
          <Eye style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1rem", color: "white", marginBottom: "0.375rem" }}>Watchlist-ul este gol</p>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Adauga produse din pagina de cautare pentru a le urmari aici.
          </p>
        </div>
      )}
    </div>
  );
}
