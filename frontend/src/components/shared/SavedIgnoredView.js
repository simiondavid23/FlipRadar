"use client";
// Pagină reutilizabilă "Salvate & Ignorate" per modul (Radar / Auto / Imobiliare).
// Tab-uri Salvate|Ignorate → fetch cu status; toggle (re-apăsare) trece anunțul pe "active"
// și îl scoate din listă. Randare cu ListingFeedCard/ListingDetailModal ale modulului,
// injectate prin render-props (`renderCard`/`renderModal`) ca să rămână identice cu feed-ul.
import { useState, useEffect, useCallback } from "react";
import TopBar from "./TopBar";
import PageHeading, { Hl } from "./PageHeading";

const TABS = [
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];

export default function SavedIgnoredView({
  title, icon: Icon, breadcrumb = ["SALVATE"], fetchList, updateStatus, deleteListing, renderCard, renderModal,
}) {
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
    <div>
      <TopBar path={breadcrumb} />

      <PageHeading
        icon={Icon}
        title={title}
        subtitle={
          loading
            ? "Anunțuri salvate și ignorate. Re-apasă acțiunea pentru a le readuce în feed."
            : <>Anunțuri salvate și ignorate — <Hl>{listings.length} {tab === "saved" ? "salvate" : "ignorate"}</Hl>. Re-apasă acțiunea pentru a le readuce în feed.</>
        }
      />

      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "16px" }}>
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => { setTab(t.value); setSelectedBulk(new Set()); }}
            className={`tab-pill${tab === t.value ? " active" : ""}`}
            style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
          >
            {tab === t.value && <span className="pill-nav-dot" />}
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : listings.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px", color: "var(--text-dim)", fontSize: "12.5px" }}>
          {tab === "saved" ? "Niciun anunț salvat." : "Niciun anunț ignorat."}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(305px, 1fr))", gap: "14px", marginTop: "14px" }}>
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
    </div>
  );
}
