"use client";
import { useState, useEffect } from "react";
import { favoritesAPI } from "@/lib/api";
import { Heart, Ban, Trash2, ExternalLink, Package } from "lucide-react";

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState([]);
  const [blacklist, setBlacklist] = useState([]);
  const [activeTab, setActiveTab] = useState("favorites");
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [favRes, blRes] = await Promise.all([
        favoritesAPI.getFavorites(),
        favoritesAPI.getBlacklist(),
      ]);
      setFavorites(favRes.data);
      setBlacklist(blRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const handleRemove = async (id) => {
    try {
      await favoritesAPI.removeFavorite(id);
      setFavorites(favorites.filter(f => f.id !== id));
      setBlacklist(blacklist.filter(b => b.id !== id));
    } catch (e) { console.error(e); }
  };

  const items = activeTab === "favorites" ? favorites : blacklist;
  const cardStyle = { backgroundColor: "#1e293b", border: "1px solid #334155" };
  const headerColStyle = {
    fontSize: "0.6875rem",
    fontWeight: 600,
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid #3b82f6", borderTop: "4px solid transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "white", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Heart style={{ width: "2rem", height: "2rem", color: "#f87171" }} />
          Favorite & Blacklist
        </h1>
        <p style={{ color: "#94a3b8", marginTop: "0.5rem" }}>Gestioneaza produsele favorite si cele blocate</p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <button onClick={() => setActiveTab("favorites")}
          style={{ padding: "0.625rem 1.5rem", borderRadius: "0.5rem", fontWeight: 500, fontSize: "0.875rem", cursor: "pointer", border: "none",
            backgroundColor: activeTab === "favorites" ? "#2563eb" : "#334155", color: activeTab === "favorites" ? "white" : "#94a3b8" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Heart style={{ width: "1rem", height: "1rem" }} /> Favorite ({favorites.length})
          </span>
        </button>
        <button onClick={() => setActiveTab("blacklist")}
          style={{ padding: "0.625rem 1.5rem", borderRadius: "0.5rem", fontWeight: 500, fontSize: "0.875rem", cursor: "pointer", border: "none",
            backgroundColor: activeTab === "blacklist" ? "#dc2626" : "#334155", color: activeTab === "blacklist" ? "white" : "#94a3b8" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Ban style={{ width: "1rem", height: "1rem" }} /> Blacklist ({blacklist.length})
          </span>
        </button>
      </div>

      {/* Items */}
      {items.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", padding: "0 1rem 0.5rem", gap: "0.875rem" }}>
            <span style={{ ...headerColStyle, flex: 1 }}>Produs</span>
            <span style={{ ...headerColStyle, width: "100px" }}>Pret</span>
            <span style={{ ...headerColStyle, width: "90px" }}>Adaugat</span>
            <span style={{ width: "72px" }} />
          </div>

          {items.map((item) => (
            <div key={item.id} style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1rem 1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h3
                    title={item.product?.name || "Produs #" + item.product_id}
                    style={{ fontSize: "0.9375rem", fontWeight: 600, color: "white", marginBottom: "0.25rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                  >
                    {item.product?.name || "Produs #" + item.product_id}
                  </h3>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    {item.product?.source && (
                      <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                        backgroundColor: "rgba(168,85,247,0.2)", color: "#c084fc" }}>{item.product.source}</span>
                    )}
                    {item.notes && (
                      <span style={{ fontSize: "0.75rem", fontStyle: "italic", color: "#94a3b8" }}>&quot;{item.notes}&quot;</span>
                    )}
                  </div>
                </div>
                <div style={{ width: "100px", fontSize: "0.9375rem", fontWeight: 700, color: "#4ade80" }}>
                  {item.product?.current_price
                    ? `${item.product.current_price} ${item.product.currency || ""}`
                    : <span style={{ color: "#64748b", fontWeight: 400 }}>—</span>}
                </div>
                <div style={{ width: "90px", fontSize: "0.75rem", color: "#94a3b8" }}>
                  {new Date(item.added_at).toLocaleDateString("ro-RO")}
                </div>
                <div style={{ width: "72px", display: "flex", gap: "0.25rem", justifyContent: "flex-end" }}>
                  {item.product?.source_url && (
                    <a href={item.product.source_url} target="_blank" rel="noopener noreferrer"
                      style={{ padding: "0.375rem", borderRadius: "0.5rem", color: "#94a3b8", cursor: "pointer", textDecoration: "none", display: "flex" }}>
                      <ExternalLink style={{ width: "1rem", height: "1rem" }} />
                    </a>
                  )}
                  <button onClick={() => handleRemove(item.id)}
                    style={{ padding: "0.375rem", borderRadius: "0.5rem", color: "#94a3b8", cursor: "pointer", border: "none", backgroundColor: "transparent", display: "flex" }}>
                    <Trash2 style={{ width: "1rem", height: "1rem" }} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "3rem", textAlign: "center" }}>
          <Package style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "#475569" }} />
          <p style={{ fontSize: "1.125rem", color: "white", marginBottom: "0.5rem" }}>
            {activeTab === "favorites" ? "Nu ai produse favorite" : "Blacklist-ul este gol"}
          </p>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>
            Adauga produse din pagina de cautare.
          </p>
        </div>
      )}
    </div>
  );
}
