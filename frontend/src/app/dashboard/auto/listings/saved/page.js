"use client";
// FlipRadar — Automobile Anunturi: anunturi auto salvate.
import { useState, useEffect } from "react";
import { autoAPI } from "@/lib/api";
import AutoListingCard from "@/components/AutoListingCard";
import AutoAiModal from "@/components/AutoAiModal";
import { Heart, Loader2 } from "lucide-react";

export default function AutoListingsSavedPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [aiListing, setAiListing] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await autoAPI.getSavedListings();
      setItems(res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const handleDelete = async (listing) => {
    setBusyId(listing.id);
    try {
      await autoAPI.deleteSavedListing(listing.id);
      setItems((prev) => prev.filter((x) => x.id !== listing.id));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere.");
    } finally { setBusyId(null); }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Heart style={{ width: "22px", height: "22px", color: "#f472b6" }} /> Anunturi Auto Salvate
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>{items.length} anunturi salvate</p>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
          Nu ai anunturi auto salvate. Salveaza anunturi din „Piata Auto”.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
          {items.map((l) => (
            <AutoListingCard key={l.id} listing={l} onDelete={handleDelete} onAnalyze={setAiListing} busy={busyId === l.id} />
          ))}
        </div>
      )}

      <AutoAiModal open={!!aiListing} onClose={() => setAiListing(null)} listing={aiListing} />
    </div>
  );
}
