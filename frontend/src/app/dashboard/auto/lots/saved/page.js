"use client";
// FlipRadar — Automobile Loturi: loturi salvate.
import { useState, useEffect } from "react";
import { autoAPI } from "@/lib/api";
import AutoLotCard from "@/components/AutoLotCard";
import { Heart, Loader2 } from "lucide-react";

export default function AutoLotsSavedPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await autoAPI.getSavedLots();
      setItems(res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const handleDelete = async (lot) => {
    setBusyId(lot.id);
    try {
      await autoAPI.deleteSavedLot(lot.id);
      setItems((prev) => prev.filter((x) => x.id !== lot.id));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere.");
    } finally { setBusyId(null); }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Heart style={{ width: "22px", height: "22px", color: "#f472b6" }} /> Loturi Salvate
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>{items.length} loturi salvate</p>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
          Nu ai loturi salvate. Salveaza loturi din „Cauta Loturi”.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1rem" }}>
          {items.map((lot) => (
            <AutoLotCard key={lot.id} lot={lot} onDelete={handleDelete} busy={busyId === lot.id} />
          ))}
        </div>
      )}
    </div>
  );
}
