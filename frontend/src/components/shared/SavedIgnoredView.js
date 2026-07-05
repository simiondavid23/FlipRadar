"use client";
// Pagină reutilizabilă "Salvate & Ignorate" per modul (Radar / Auto / Imobiliare).
// Tab-uri Salvate|Ignorate → fetch cu status; toggle (re-apăsare) trece anunțul pe "active"
// și îl scoate din listă. Randare cu ListingFeedCard/ListingDetailModal ale modulului,
// injectate prin render-props (`renderCard`/`renderModal`) ca să rămână identice cu feed-ul.
import { useState, useEffect, useCallback } from "react";

const TABS = [
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];

function tabPill(active) {
  return {
    padding: "0.5rem 1.25rem", borderRadius: "999px", fontSize: "0.875rem", fontWeight: 600,
    cursor: "pointer", border: "1px solid var(--border-color)",
    backgroundColor: active ? "var(--blue-primary)" : "transparent",
    color: active ? "white" : "var(--text-secondary)", transition: "all 0.15s ease",
  };
}

export default function SavedIgnoredView({ title, icon: Icon, fetchList, updateStatus, deleteListing, renderCard, renderModal }) {
  const [tab, setTab] = useState("saved");
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [selectedBulk, setSelectedBulk] = useState(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try { setListings(await fetchList(tab)); }
    catch (e) { console.error("[SavedIgnored]", e); setListings([]); }
    finally { setLoading(false); }
  }, [tab, fetchList]);

  useEffect(() => { load(); }, [load]);

  const toggleBulk = (id) => setSelectedBulk((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  // Orice schimbare de status scoate anunțul din tab-ul curent (Salvate/Ignorate).
  const changeStatus = async (id, newStatus) => {
    try {
      await updateStatus(id, newStatus);
      setListings((prev) => prev.filter((l) => l.id !== id));
      setSelected((prev) => (prev?.id === id ? null : prev));
    } catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const removeListing = async (id) => {
    if (!confirm("Ștergi acest anunț?")) return;
    try {
      await deleteListing(id);
      setListings((prev) => prev.filter((l) => l.id !== id));
      setSelected((prev) => (prev?.id === id ? null : prev));
    } catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  // Toggle: pe tab-ul "Salvate", l.status === "saved" → "active"; analog "Ignorate".
  const onSave = (l) => changeStatus(l.id, l.status === "saved" ? "active" : "saved");
  const onIgnore = (l) => changeStatus(l.id, l.status === "ignored" ? "active" : "ignored");

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {Icon && <Icon style={{ width: "22px", height: "22px", color: "#2563eb" }} />}
          {title}
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Anunțuri salvate și ignorate. Re-apasă acțiunea pentru a le readuce în feed.
        </p>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        {TABS.map((t) => (
          <button key={t.value} onClick={() => { setTab(t.value); setSelectedBulk(new Set()); }} style={tabPill(tab === t.value)}>{t.label}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : listings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          {tab === "saved" ? "Niciun anunț salvat." : "Niciun anunț ignorat."}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
          {listings.map((l) => renderCard(l, {
            onOpen: () => setSelected(l),
            onSave: () => onSave(l),
            onIgnore: () => onIgnore(l),
            onDelete: () => removeListing(l.id),
            isSelected: selectedBulk.has(l.id),
            onToggleSelect: () => toggleBulk(l.id),
          }))}
        </div>
      )}

      {selected && renderModal(selected, {
        onClose: () => setSelected(null),
        onSave: () => onSave(selected),
        onIgnore: () => onIgnore(selected),
      })}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
