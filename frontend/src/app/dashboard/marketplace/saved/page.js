"use client";
// FlipRadar — Modulul 1 Marketplace: anunturi salvate.
import { useState, useEffect } from "react";
import { marketplaceAPI } from "@/lib/api";
import MarketplaceListingCard from "@/components/MarketplaceListingCard";
import { Heart, Loader2 } from "lucide-react";

export default function MarketplaceSavedPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await marketplaceAPI.getSaved();
      setItems(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (listing) => {
    setBusyId(listing.id);
    try {
      await marketplaceAPI.deleteSaved(listing.id);
      setItems((prev) => prev.filter((x) => x.id !== listing.id));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Heart style={{ width: "22px", height: "22px", color: "#f472b6" }} />
          Anunturi Salvate
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          {items.length} anunturi salvate din marketplace
        </p>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)",
        }}>
          Nu ai anunturi salvate. Salveaza anunturi din pagina „Cauta Anunturi”.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
          {items.map((it) => (
            <MarketplaceListingCard key={it.id} listing={it} onDelete={handleDelete} busy={busyId === it.id} />
          ))}
        </div>
      )}
    </div>
  );
}
