"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { radarAPI } from "@/lib/api";
import {
  Radar, RefreshCw, ImageOff, ExternalLink, Bookmark, EyeOff,
  X, Sparkles, ShieldOff, Tag, MapPin, Calendar, FileSpreadsheet,
  GitCompareArrows, MessageSquare, Copy, Check
} from "lucide-react";

const PLATFORMS = [
  { value: "", label: "Toate platformele" },
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "Lajumate" },
  { value: "publi24", label: "Publi24" },
  { value: "autovit", label: "Autovit" },
  { value: "mobilede", label: "Mobile.de" },
];

const SCORES = [
  { value: "", label: "Toate scorurile" },
  { value: "A", label: "A — Excelent" },
  { value: "B", label: "B — Bun" },
  { value: "C", label: "C — Ok" },
  { value: "D", label: "D — Slab" },
];

const STATUS_OPTIONS = [
  { value: "", label: "Active + Salvate" },
  { value: "active", label: "Doar active" },
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];

const PLATFORM_COLORS = {
  olx: { bg: "rgba(37,99,235,0.15)", border: "#2563eb", text: "#60a5fa" },
  vinted: { bg: "rgba(147,51,234,0.15)", border: "#9333ea", text: "#c4b5fd" },
  okazii: { bg: "rgba(22,163,74,0.15)", border: "#16a34a", text: "#4ade80" },
  facebook: { bg: "rgba(30,58,138,0.25)", border: "#1e40af", text: "#93c5fd" },
  lajumate: { bg: "rgba(249,115,22,0.15)", border: "#f97316", text: "#fdba74" },
  publi24: { bg: "rgba(21,128,61,0.18)", border: "#15803d", text: "#86efac" },
  autovit: { bg: "rgba(220,38,38,0.15)", border: "#dc2626", text: "#fca5a5" },
  mobilede: { bg: "rgba(30,64,175,0.20)", border: "#1e40af", text: "#93c5fd" },
};

const SCORE_COLORS = {
  A: { bg: "rgba(22,163,74,0.18)", border: "#16a34a", text: "#4ade80" },
  B: { bg: "rgba(59,130,246,0.18)", border: "#3b82f6", text: "#60a5fa" },
  C: { bg: "rgba(250,204,21,0.18)", border: "#facc15", text: "#fde047" },
  D: { bg: "rgba(249,115,22,0.18)", border: "#f97316", text: "#fb923c" },
};

const SCORE_EXPLANATIONS = {
  A: "Marjă excelentă — deal prioritar",
  B: "Marjă bună — merită urmărit",
  C: "Marjă acceptabilă — analizează cu atenție",
  D: "Marjă slabă — sub pragul tău AI",
};

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "acum câteva secunde";
  if (diff < 3600) return `acum ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `acum ${Math.floor(diff / 3600)} h`;
  return `acum ${Math.floor(diff / 86400)} zile`;
}

function formatListedDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  const yest = new Date(now.getTime() - 86400000);
  const isYesterday = d.getFullYear() === yest.getFullYear() && d.getMonth() === yest.getMonth() && d.getDate() === yest.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `azi ${hh}:${mm}`;
  if (isYesterday) return `ieri ${hh}:${mm}`;
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mo}.${d.getFullYear()} ${hh}:${mm}`;
}

function marginColor(pct) {
  if (pct === null || pct === undefined) return "var(--text-secondary)";
  if (pct >= 25) return "#4ade80";
  if (pct >= 10) return "#facc15";
  return "#fb923c";
}

export default function RadarFeedPage() {
  const [listings, setListings] = useState([]);
  const [keywords, setKeywords] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState(null);
  const [generatingAI, setGeneratingAI] = useState(false);
  const [selectedForComparison, setSelectedForComparison] = useState([]);
  const [selectedBulk, setSelectedBulk] = useState([]);
  const [showCompare, setShowCompare] = useState(false);
  const [toast, setToast] = useState(null);

  const [filters, setFilters] = useState({
    platform: "",
    score: "",
    keyword_id: "",
    status: "",
    hide_filtered: true,
  });

  const loadKeywords = useCallback(async () => {
    try {
      const r = await radarAPI.getKeywords();
      setKeywords(r.data || []);
    } catch (e) {
      console.error("[Radar] keywords:", e);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const r = await radarAPI.getTemplates();
      setTemplates(r.data || []);
    } catch (e) {
      console.error("[Radar] templates:", e);
    }
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const loadListings = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = { hide_filtered: filters.hide_filtered };
      if (filters.platform) params.platform = filters.platform;
      if (filters.score) params.score = filters.score;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      if (filters.status) params.status = filters.status;
      const r = await radarAPI.getListings(params);
      setListings(r.data?.items || []);
    } catch (e) {
      console.error("[Radar] listings:", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filters]);

  useEffect(() => {
    loadKeywords();
    loadTemplates();
  }, [loadKeywords, loadTemplates]);

  useEffect(() => {
    loadListings();
  }, [loadListings]);

  const updateStatus = async (listingId, newStatus) => {
    try {
      await radarAPI.updateListingStatus(listingId, newStatus);
      setListings((prev) => prev.filter((l) => l.id !== listingId));
      if (selected?.id === listingId) setSelected(null);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
    }
  };

  const blockSeller = async (listingId) => {
    if (!confirm("Blochezi acest vânzător pentru toate viitoarele anunțuri?")) return;
    try {
      await radarAPI.blockSeller(listingId);
      alert("Vânzător blocat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la blocare.");
    }
  };

  const generateAIReview = async (listingId) => {
    setGeneratingAI(true);
    try {
      const r = await radarAPI.generateListingAIReview(listingId);
      setSelected((prev) => prev ? { ...prev, ai_review: r.data.ai_review } : prev);
    } catch (e) {
      alert(e.response?.data?.detail || "Nu am putut genera review-ul.");
    } finally {
      setGeneratingAI(false);
    }
  };

  const toggleCompare = (listing) => {
    setSelectedForComparison((prev) => {
      const exists = prev.find((l) => l.id === listing.id);
      if (exists) return prev.filter((l) => l.id !== listing.id);
      if (prev.length >= 3) {
        showToast("Maxim 3 listinguri pentru comparare.");
        return prev;
      }
      return [...prev, listing];
    });
  };

  const toggleBulk = (id) => {
    setSelectedBulk((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };

  const toggleSelectAllBulk = (e) => {
    if (e.target.checked) {
      setSelectedBulk(listings.map((l) => l.id));
    } else {
      setSelectedBulk([]);
    }
  };

  const applyBulkAction = async (action) => {
    if (selectedBulk.length === 0) return;
    try {
      const r = await radarAPI.bulkAction(selectedBulk, action);
      showToast(r.data?.message || `${r.data?.updated || 0} listinguri actualizate.`);
      setSelectedBulk([]);
      loadListings();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la acțiune în masă.");
    }
  };

  const downloadExcel = async () => {
    try {
      const params = { hide_filtered: filters.hide_filtered };
      if (filters.platform) params.platform = filters.platform;
      if (filters.score) params.score = filters.score;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      if (filters.status) params.status = filters.status;
      const r = await radarAPI.exportListings(params);
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `radar_dealuri_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la export Excel.");
    }
  };

  const selectStyle = {
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.5rem",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.8125rem",
    outline: "none",
    cursor: "pointer",
    minWidth: "160px",
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Radar style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Feed Anunțuri
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Anunțuri găsite în timp real ({listings.length} active în vizualizare)
          </p>
        </div>
      </div>

      {/* Bară filtre */}
      <div style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        padding: "1rem",
        marginBottom: "1.25rem",
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "0.625rem",
      }}>
        <select value={filters.platform} onChange={(e) => setFilters({ ...filters, platform: e.target.value })} style={selectStyle}>
          {PLATFORMS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={filters.score} onChange={(e) => setFilters({ ...filters, score: e.target.value })} style={selectStyle}>
          {SCORES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={filters.keyword_id} onChange={(e) => setFilters({ ...filters, keyword_id: e.target.value })} style={selectStyle}>
          <option value="">Toate keyword-urile</option>
          {keywords.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} style={selectStyle}>
          {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>

        <label style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.5rem",
          padding: "0.5rem 0.75rem",
          border: "1px solid var(--border-color)",
          borderRadius: "0.5rem",
          backgroundColor: "var(--bg-dark)",
          color: "var(--text-primary)",
          fontSize: "0.8125rem",
          cursor: "pointer",
        }}>
          <input
            type="checkbox"
            checked={filters.hide_filtered}
            onChange={(e) => setFilters({ ...filters, hide_filtered: e.target.checked })}
            style={{ width: "auto", margin: 0 }}
          />
          Ascunde sub prag AI
        </label>

        <SelectFiniteControl
          totalVisible={listings.length}
          selectedCount={selectedBulk.length}
          onSelect={(count) => {
            if (count === 0) {
              setSelectedBulk([]);
              return;
            }
            setSelectedBulk(listings.slice(0, count).map((l) => l.id));
          }}
        />

        <button
          onClick={loadListings}
          disabled={refreshing}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 0.875rem",
            backgroundColor: "var(--blue-primary)",
            color: "white",
            border: "none",
            borderRadius: "0.5rem",
            fontSize: "0.8125rem",
            fontWeight: 600,
            cursor: refreshing ? "wait" : "pointer",
            opacity: refreshing ? 0.7 : 1,
          }}
        >
          <RefreshCw style={{ width: "14px", height: "14px", animation: refreshing ? "spin 1s linear infinite" : undefined }} />
          Actualizează
        </button>

        <button
          onClick={downloadExcel}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 0.875rem",
            backgroundColor: "rgba(22,163,74,0.15)",
            color: "#4ade80",
            border: "1px solid rgba(22,163,74,0.3)",
            borderRadius: "0.5rem",
            fontSize: "0.8125rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <FileSpreadsheet style={{ width: "14px", height: "14px" }} />
          Export Excel
        </button>
      </div>

      {/* Grilă listinguri */}
      {listings.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "3rem",
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          color: "var(--text-secondary)",
        }}>
          Niciun anunț în feed. Verifică să ai keyword-uri active și platforme activate.
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "1rem",
          }}
        >
          {listings.map((l) => (
            <ListingCard
              key={l.id}
              listing={l}
              onOpen={() => setSelected(l)}
              onSave={() => updateStatus(l.id, "saved")}
              onIgnore={() => updateStatus(l.id, "ignored")}
              compareSelected={!!selectedForComparison.find((x) => x.id === l.id)}
              bulkSelected={selectedBulk.includes(l.id)}
              onToggleCompare={() => toggleCompare(l)}
              onToggleBulk={() => toggleBulk(l.id)}
            />
          ))}
        </div>
      )}

      {/* Fereastră detalii */}
      {selected && (
        <ListingModal
          listing={selected}
          templates={templates}
          onClose={() => setSelected(null)}
          onSave={() => updateStatus(selected.id, "saved")}
          onIgnore={() => updateStatus(selected.id, "ignored")}
          onBlockSeller={() => blockSeller(selected.id)}
          onGenerateAI={() => generateAIReview(selected.id)}
          generatingAI={generatingAI}
        />
      )}

      {/* Banner fix jos — comparare + acțiuni în masă */}
      {(selectedForComparison.length > 0 || selectedBulk.length > 0) && (
        <ActionBanner
          comparisonCount={selectedForComparison.length}
          bulkCount={selectedBulk.length}
          totalVisible={listings.length}
          onCompareOpen={() => setShowCompare(true)}
          onCompareClear={() => setSelectedForComparison([])}
          onBulkSave={() => applyBulkAction("saved")}
          onBulkIgnore={() => applyBulkAction("ignored")}
          onBulkDelete={() => applyBulkAction("deleted")}
          onBulkExport={async () => {
            try {
              const r = await radarAPI.exportListings({ ids: selectedBulk.join(",") });
              const url = URL.createObjectURL(new Blob([r.data]));
              const a = document.createElement("a");
              a.href = url;
              a.download = `radar_selectie_${new Date().toISOString().slice(0, 10)}.xlsx`;
              document.body.appendChild(a); a.click(); a.remove();
              URL.revokeObjectURL(url);
            } catch (e) {
              alert(e.response?.data?.detail || "Eroare la export Excel.");
            }
          }}
          onBulkClear={() => setSelectedBulk([])}
        />
      )}

      {/* Fereastră comparare */}
      {showCompare && selectedForComparison.length >= 2 && (
        <CompareModal
          listings={selectedForComparison}
          onClose={() => setShowCompare(false)}
          onSave={async (id) => { await updateStatus(id, "saved"); }}
          onIgnore={async (id) => { await updateStatus(id, "ignored"); }}
        />
      )}

      {/* Notificare toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: "5rem", left: "50%", transform: "translateX(-50%)",
          backgroundColor: "var(--bg-card)", color: "var(--text-primary)",
          border: "1px solid var(--border-color)", borderRadius: "0.5rem",
          padding: "0.5rem 0.875rem", fontSize: "0.8125rem",
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          zIndex: 200,
        }}>{toast}</div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function ListingCard({ listing, onOpen, onSave, onIgnore, compareSelected, bulkSelected, onToggleCompare, onToggleBulk }) {
  const scoreCfg = SCORE_COLORS[listing.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" };
  const platformCfg = PLATFORM_COLORS[listing.platform] || PLATFORM_COLORS.olx;
  const margin = listing.margin_pct;
  const marginValue = listing.margin_value;
  const image = listing.images?.[0];

  const baseBorder = compareSelected ? "var(--blue-primary)" : bulkSelected ? "#94a3b8" : "var(--border-color)";

  return (
    <div
      onClick={onOpen}
      style={{
        backgroundColor: bulkSelected ? "rgba(148,163,184,0.05)" : "var(--bg-card)",
        border: `1px solid ${baseBorder}`,
        borderRadius: "0.75rem",
        overflow: "hidden",
        cursor: "pointer",
        transition: "all 0.15s ease",
        display: "flex",
        flexDirection: "column",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = scoreCfg.border;
        e.currentTarget.style.boxShadow = `0 4px 14px ${scoreCfg.bg}`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = baseBorder;
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Checkbox comparare stânga-sus (peste imagine) */}
      <div
        onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
        title="Selectează pentru comparare"
        style={{
          position: "absolute", top: "6px", left: "6px", zIndex: 5,
          width: "20px", height: "20px",
          backgroundColor: compareSelected ? "var(--blue-primary)" : "rgba(15,23,42,0.7)",
          border: `1px solid ${compareSelected ? "var(--blue-primary)" : "rgba(255,255,255,0.5)"}`,
          borderRadius: "0.25rem",
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer",
        }}
      >
        {compareSelected ? <Check style={{ width: "12px", height: "12px", color: "white" }} /> : null}
      </div>

      {/* Imagine */}
      <div style={{ position: "relative", height: "180px", backgroundColor: "var(--bg-dark)" }}>
        {image ? (
          <img
            src={image}
            alt={listing.title}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "36px", height: "36px" }} />
          </div>
        )}

        {/* Insignă scor */}
        {listing.score && (
          <div style={{
            position: "absolute", top: "0.5rem", left: "0.5rem",
            padding: "0.25rem 0.625rem",
            backgroundColor: scoreCfg.bg,
            border: `1px solid ${scoreCfg.border}`,
            borderRadius: "0.375rem",
            color: scoreCfg.text,
            fontSize: "0.75rem",
            fontWeight: 700,
          }}>
            {listing.score}
          </div>
        )}

        {/* Insignă platformă */}
        <div style={{
          position: "absolute", top: "0.5rem", right: "0.5rem",
          padding: "0.25rem 0.625rem",
          backgroundColor: platformCfg.bg,
          border: `1px solid ${platformCfg.border}`,
          borderRadius: "0.375rem",
          color: platformCfg.text,
          fontSize: "0.6875rem",
          fontWeight: 600,
          textTransform: "uppercase",
        }}>
          {listing.platform}
        </div>
      </div>

      {/* Conținut card */}
      <div style={{ padding: "0.875rem", display: "flex", flexDirection: "column", gap: "0.5rem", flex: 1 }}>
        <h3 style={{
          fontSize: "0.875rem",
          fontWeight: 600,
          color: "var(--text-primary)",
          margin: 0,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          textOverflow: "ellipsis",
          minHeight: "2.6em",
          lineHeight: "1.3",
        }}>
          {listing.title}
        </h3>

        <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
          {Math.round(listing.price)} {listing.currency}
        </div>

        <div style={{ fontSize: "0.75rem", color: marginColor(margin) }}>
          → {Math.round(listing.resale_price || 0)} RON revânzare
          {marginValue !== null && marginValue !== undefined && (
            <span> | Marjă: <strong>{Math.round(marginValue)} RON ({Math.round(margin || 0)}%)</strong></span>
          )}
        </div>

        {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            Preț maxim recomandat: {Math.round(listing.fee_ceiling)} RON
          </div>
        )}

        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          {(listing.platform === "autovit" || listing.platform === "mobilede") && (
            <AutoSpecsLine listing={listing} />
          )}
          {listing.location && <span>{listing.location}</span>}
          <span>
            {listing.listed_at && formatListedDate(listing.listed_at) ? (
              <>Postat: {formatListedDate(listing.listed_at)} · Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            ) : (
              <>Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            )}
          </span>
        </div>

        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem" }}>
          <button
            onClick={(e) => { e.stopPropagation(); onSave(); }}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "rgba(22,163,74,0.15)", color: "#4ade80", border: "1px solid rgba(22,163,74,0.3)", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title="Salvează"
          >
            <Bookmark style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            Salvează
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onIgnore(); }}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "rgba(100,116,139,0.15)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title="Ignoră"
          >
            <EyeOff style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            Ignoră
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onOpen(); }}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title="Deschide"
          >
            <ExternalLink style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            Deschide
          </button>
        </div>
      </div>
    </div>
  );
}

function ListingModal({ listing, templates = [], onClose, onSave, onIgnore, onBlockSeller, onGenerateAI, generatingAI }) {
  const scoreCfg = SCORE_COLORS[listing.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" };
  const platformCfg = PLATFORM_COLORS[listing.platform] || PLATFORM_COLORS.olx;
  const images = listing.images || [];
  const [mainImg, setMainImg] = useState(images[0] || null);
  useEffect(() => { setMainImg(images[0] || null); }, [listing.id]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 100, padding: "1.5rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.875rem",
          maxWidth: "900px",
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Antet modal */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "1rem 1.25rem", borderBottom: "1px solid var(--border-color)",
          gap: "0.75rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
            {listing.score && (
              <span style={{
                padding: "0.25rem 0.625rem",
                backgroundColor: scoreCfg.bg,
                border: `1px solid ${scoreCfg.border}`,
                borderRadius: "0.375rem",
                color: scoreCfg.text,
                fontSize: "0.75rem",
                fontWeight: 700,
              }}>{listing.score}</span>
            )}
            <span style={{
              padding: "0.2rem 0.5rem",
              backgroundColor: platformCfg.bg,
              border: `1px solid ${platformCfg.border}`,
              borderRadius: "0.375rem",
              color: platformCfg.text,
              fontSize: "0.7rem",
              fontWeight: 600,
              textTransform: "uppercase",
            }}>{listing.platform}</span>
            <h2 style={{
              fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)",
              margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>{listing.title}</h2>
          </div>
          <button
            onClick={onClose}
            style={{
              backgroundColor: "transparent", border: "none", color: "var(--text-secondary)",
              cursor: "pointer", padding: "0.25rem",
            }}
          >
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        {/* Corp modal */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: "1.25rem",
          padding: "1.25rem",
        }}>
          {/* Stânga: galerie imagini */}
          <div>
            <div style={{
              width: "100%", aspectRatio: "1",
              backgroundColor: "var(--bg-dark)",
              borderRadius: "0.625rem",
              overflow: "hidden",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid var(--border-color)",
            }}>
              {mainImg ? (
                <img src={mainImg} alt={listing.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <ImageOff style={{ width: "48px", height: "48px", color: "var(--text-muted)" }} />
              )}
            </div>
            {images.length > 1 && (
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                {images.slice(0, 6).map((img, idx) => (
                  <img
                    key={idx}
                    src={img}
                    onClick={() => setMainImg(img)}
                    style={{
                      width: "64px", height: "64px", objectFit: "cover",
                      borderRadius: "0.375rem", cursor: "pointer",
                      border: mainImg === img ? "2px solid var(--blue-primary)" : "1px solid var(--border-color)",
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Dreapta: detalii */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț cerut</div>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {Math.round(listing.price)} {listing.currency}
              </div>
            </div>

            {listing.resale_price && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț estimat revânzare</div>
                <div style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.resale_price)} RON
                </div>
              </div>
            )}

            {listing.margin_pct !== null && listing.margin_pct !== undefined && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Marjă</div>
                <div style={{ fontSize: "1rem", fontWeight: 600, color: marginColor(listing.margin_pct) }}>
                  {Math.round(listing.margin_value || 0)} RON ({Math.round(listing.margin_pct)}%)
                </div>
              </div>
            )}

            {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț maxim recomandat</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.fee_ceiling)} RON
                </div>
              </div>
            )}

            {listing.score && (
              <div style={{ padding: "0.625rem", backgroundColor: scoreCfg.bg, border: `1px solid ${scoreCfg.border}`, borderRadius: "0.5rem" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: scoreCfg.text }}>Scor {listing.score}</div>
                <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{SCORE_EXPLANATIONS[listing.score]}</div>
              </div>
            )}

            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <div><Tag style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {listing.platform.toUpperCase()}</div>
              {listing.location && <div><MapPin style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {listing.location}</div>}
              {listing.condition && <div>Condiție: {listing.condition}</div>}
              {listing.seller_name && <div>Vânzător: {listing.seller_name}</div>}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem", marginTop: "0.25rem" }}>
                <span>
                  <Calendar style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
                  <strong>Postat pe platformă:</strong>{" "}
                  {formatListedDate(listing.listed_at) || "Necunoscut"}
                </span>
                <span>
                  <Calendar style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
                  <strong>Găsit de FlipRadar:</strong>{" "}
                  {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Descriere */}
        {listing.description && (
          <div style={{ padding: "0 1.25rem 1rem" }}>
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Descriere</div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{listing.description}</div>
          </div>
        )}

        {/* Review AI */}
        <div style={{ padding: "0 1.25rem 1.25rem" }}>
          <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <Sparkles style={{ width: "14px", height: "14px", color: "#a78bfa" }} />
            Review AI
          </div>
          {listing.ai_review ? (
            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontStyle: "italic", lineHeight: 1.5, padding: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem" }}>
              {listing.ai_review}
            </div>
          ) : (
            <button
              onClick={onGenerateAI}
              disabled={generatingAI}
              style={{
                padding: "0.5rem 0.875rem",
                backgroundColor: "rgba(147,51,234,0.15)",
                color: "#c4b5fd",
                border: "1px solid rgba(147,51,234,0.3)",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: generatingAI ? "wait" : "pointer",
              }}
            >
              {generatingAI ? "Se generează..." : "Generează review AI"}
            </button>
          )}
        </div>

        {/* Mesaje rapide */}
        <MessageTemplateBlock listing={listing} templates={templates} />

        {/* Acțiuni */}
        <div style={{ padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={onSave} style={btn("#4ade80", "rgba(22,163,74,0.15)", "rgba(22,163,74,0.3)")}>
            <Bookmark style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            Salvează
          </button>
          <button onClick={onIgnore} style={btn("var(--text-secondary)", "rgba(100,116,139,0.15)", "var(--border-color)")}>
            <EyeOff style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            Ignoră
          </button>
          <button onClick={onBlockSeller} style={btn("#fb923c", "rgba(249,115,22,0.15)", "rgba(249,115,22,0.3)")}>
            <ShieldOff style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            Blochează vânzătorul
          </button>
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ ...btn("white", "var(--blue-primary)", "var(--blue-primary)"), textDecoration: "none", marginLeft: "auto" }}
          >
            <ExternalLink style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            Deschide pe {listing.platform}
          </a>
        </div>
      </div>
    </div>
  );
}

function btn(color, bg, border) {
  return {
    padding: "0.5rem 0.875rem",
    backgroundColor: bg,
    color: color,
    border: `1px solid ${border}`,
    borderRadius: "0.5rem",
    fontSize: "0.8125rem",
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
  };
}


function SelectFiniteControl({ totalVisible, selectedCount, onSelect }) {
  const [customOpen, setCustomOpen] = useState(false);
  const [customN, setCustomN] = useState("");
  const quickBtn = (label, n) => (
    <button
      type="button"
      onClick={() => onSelect(Math.min(n, totalVisible))}
      style={{
        padding: "0.3rem 0.5rem",
        backgroundColor: "var(--bg-dark)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.375rem",
        color: "var(--text-primary)",
        fontSize: "0.7rem", fontWeight: 500, cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
  return (
    <div style={{
      marginLeft: "auto",
      display: "inline-flex", alignItems: "center", gap: "0.375rem",
      padding: "0.375rem 0.625rem",
      border: "1px solid var(--border-color)", borderRadius: "0.5rem",
      backgroundColor: "var(--bg-card)",
      flexWrap: "wrap",
    }}>
      <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", fontWeight: 600 }}>Selectează:</span>
      {quickBtn("Toate", totalVisible)}
      {quickBtn("Primele 10", 10)}
      {quickBtn("Primele 25", 25)}
      {quickBtn("Primele 50", 50)}
      <button type="button" onClick={() => setCustomOpen(!customOpen)} style={{
        padding: "0.3rem 0.5rem", backgroundColor: customOpen ? "var(--blue-primary)" : "var(--bg-dark)",
        color: customOpen ? "white" : "var(--text-primary)",
        border: "1px solid var(--border-color)", borderRadius: "0.375rem",
        fontSize: "0.7rem", fontWeight: 500, cursor: "pointer",
      }}>Custom</button>
      {customOpen && (
        <input
          type="number" min="1" max={totalVisible}
          value={customN}
          onChange={(e) => setCustomN(e.target.value)}
          onBlur={() => {
            const n = parseInt(customN);
            if (!Number.isNaN(n) && n > 0) onSelect(Math.min(n, totalVisible));
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const n = parseInt(customN);
              if (!Number.isNaN(n) && n > 0) onSelect(Math.min(n, totalVisible));
            }
          }}
          style={{
            width: "70px", padding: "0.3rem 0.5rem",
            backgroundColor: "var(--bg-dark)", color: "var(--text-primary)",
            border: "1px solid var(--border-color)", borderRadius: "0.375rem",
            fontSize: "0.7rem",
          }}
          placeholder="N"
          autoFocus
        />
      )}
      <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.25rem" }}>
        {selectedCount} / {totalVisible} selectate
      </span>
    </div>
  );
}


function ActionBanner({
  comparisonCount, bulkCount, totalVisible,
  onCompareOpen, onCompareClear,
  onBulkSave, onBulkIgnore, onBulkDelete, onBulkExport, onBulkClear,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  return (
    <div style={{
      position: "fixed", bottom: 0, left: "240px", right: 0,
      backgroundColor: "var(--bg-card)",
      borderTop: "2px solid var(--blue-primary)",
      padding: "0.625rem 1rem",
      display: "flex", flexWrap: "wrap",
      alignItems: "center", gap: "0.75rem",
      zIndex: 60,
      boxShadow: "0 -4px 12px rgba(0,0,0,0.25)",
    }}>
      {comparisonCount >= 1 && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 600 }}>
            {comparisonCount} listing(uri) selectate pentru comparare
          </span>
          {comparisonCount >= 2 && (
            <button onClick={onCompareOpen} style={primaryBannerBtn}>
              <GitCompareArrows style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.25rem" }} />
              Compară
            </button>
          )}
          <button onClick={onCompareClear} style={ghostBtn}>Golește selecția</button>
        </div>
      )}

      {bulkCount > 0 && (
        <div style={{
          marginLeft: comparisonCount > 0 ? "auto" : 0,
          display: "inline-flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap",
        }}>
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 600 }}>
            {bulkCount} anunțuri selectate
          </span>
          {confirmDelete ? (
            <>
              <span style={{ fontSize: "0.75rem", color: "#fca5a5" }}>
                Sigur vrei să ștergi {bulkCount} anunțuri? Acțiunea nu poate fi anulată.
              </span>
              <button onClick={() => { onBulkDelete(); setConfirmDelete(false); }} style={dangerBtn}>
                Confirmă ștergerea
              </button>
              <button onClick={() => setConfirmDelete(false)} style={ghostBtn}>Anulează</button>
            </>
          ) : (
            <>
              <button onClick={onBulkSave} style={primaryBannerBtn}>💾 Salvează</button>
              <button onClick={onBulkIgnore} style={ghostBtn}>👁 Ignoră</button>
              <button onClick={() => setConfirmDelete(true)} style={dangerBtn}>🗑 Șterge</button>
              <button onClick={onBulkExport} style={ghostBtn}>📋 Exportă selecția</button>
              <button onClick={onBulkClear} style={ghostBtn}>✕ Golește selecția</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const primaryBannerBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "var(--blue-primary)",
  color: "white", border: "none",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
  cursor: "pointer",
};

const ghostBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "var(--bg-dark)",
  color: "var(--text-secondary)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 500,
  cursor: "pointer",
};

const dangerBtn = {
  padding: "0.4rem 0.75rem",
  backgroundColor: "rgba(239,68,68,0.15)",
  color: "#fca5a5",
  border: "1px solid rgba(239,68,68,0.3)",
  borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
  cursor: "pointer",
};


function CompareModal({ listings, onClose, onSave, onIgnore }) {
  // Determinare evidențieri
  const prices = listings.map((l) => Number(l.price) || 0);
  const margins = listings.map((l) => Number(l.margin_pct) || 0);
  const founds = listings.map((l) => l.listed_at ? new Date(l.listed_at).getTime() : Number.MAX_SAFE_INTEGER);
  const lowestPriceIdx = prices.indexOf(Math.min(...prices));
  const highestMarginIdx = margins.indexOf(Math.max(...margins));
  const oldestIdx = founds.indexOf(Math.min(...founds));

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 110, padding: "1.5rem",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.875rem",
        maxWidth: "1100px", width: "100%",
        maxHeight: "90vh", overflowY: "auto",
        padding: "1.25rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Comparare listinguri
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${listings.length}, 1fr)`, gap: "0.875rem" }}>
          {listings.map((l, idx) => {
            const sc = SCORE_COLORS[l.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" };
            const pc = PLATFORM_COLORS[l.platform] || PLATFORM_COLORS.olx;
            return (
              <div key={l.id} style={{
                backgroundColor: "var(--bg-dark)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.625rem", padding: "0.75rem",
                display: "flex", flexDirection: "column", gap: "0.5rem",
              }}>
                <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", minHeight: "2.4rem" }}>
                  {l.title}
                </div>
                <div style={{ display: "flex", gap: "0.375rem" }}>
                  {l.score && (
                    <span style={{ padding: "0.125rem 0.5rem", backgroundColor: sc.bg, border: `1px solid ${sc.border}`, borderRadius: "0.375rem", color: sc.text, fontSize: "0.7rem", fontWeight: 700 }}>{l.score}</span>
                  )}
                  <span style={{ padding: "0.125rem 0.5rem", backgroundColor: pc.bg, border: `1px solid ${pc.border}`, borderRadius: "0.375rem", color: pc.text, fontSize: "0.65rem", fontWeight: 600, textTransform: "uppercase" }}>{l.platform}</span>
                </div>
                <div style={{ width: "100%", height: "160px", overflow: "hidden", backgroundColor: "var(--bg-card)", borderRadius: "0.375rem", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {l.images?.[0] ? (
                    <img src={l.images[0]} alt={l.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    <ImageOff style={{ width: "32px", height: "32px", color: "var(--text-muted)" }} />
                  )}
                </div>
                <CompareRow label="Preț cerut" value={`${Math.round(l.price)} ${l.currency}`} highlight={idx === lowestPriceIdx} good />
                <CompareRow label="Preț revânzare" value={l.resale_price ? `${Math.round(l.resale_price)} RON` : "—"} />
                <CompareRow label="Marjă"
                  value={l.margin_value !== null && l.margin_value !== undefined ? `${Math.round(l.margin_value)} RON (${Math.round(l.margin_pct || 0)}%)` : "—"}
                  highlight={idx === highestMarginIdx} good />
                <CompareRow label="Fee ceiling" value={l.fee_ceiling !== null && l.fee_ceiling !== undefined ? `${Math.round(l.fee_ceiling)} RON` : "—"} />
                <CompareRow label="Locație" value={l.location || "—"} />
                <CompareRow label="Condiție" value={l.condition || "—"} />
                <CompareRow label="Postat" value={l.listed_at ? formatListedDate(l.listed_at) : "Necunoscut"} highlight={idx === oldestIdx} bad />
                <CompareRow label="Vânzător" value={l.seller_name || "—"} />
                {l.ai_review && (
                  <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)", fontStyle: "italic", marginTop: "0.25rem" }}>
                    {l.ai_review.slice(0, 140)}{l.ai_review.length > 140 ? "…" : ""}
                  </div>
                )}
                <div style={{ display: "flex", gap: "0.25rem", marginTop: "auto" }}>
                  <button onClick={() => onSave(l.id)} style={smallActionBtn("#4ade80", "rgba(22,163,74,0.15)", "rgba(22,163,74,0.3)")}>💾</button>
                  <button onClick={() => onIgnore(l.id)} style={smallActionBtn("var(--text-secondary)", "var(--bg-card)", "var(--border-color)")}>👁</button>
                  <a href={l.url} target="_blank" rel="noopener noreferrer" style={{ ...smallActionBtn("white", "var(--blue-primary)", "var(--blue-primary)"), textDecoration: "none", marginLeft: "auto" }}>↗ Deschide</a>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function CompareRow({ label, value, highlight, good, bad }) {
  const color = highlight ? (good ? "#4ade80" : bad ? "#fca5a5" : "var(--text-primary)") : "var(--text-primary)";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", gap: "0.5rem" }}>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ color, fontWeight: highlight ? 700 : 500, textAlign: "right" }}>{value}</span>
    </div>
  );
}

function smallActionBtn(color, bg, border) {
  return {
    padding: "0.3rem 0.5rem",
    backgroundColor: bg, color,
    border: `1px solid ${border}`,
    borderRadius: "0.375rem", fontSize: "0.7rem",
    fontWeight: 600, cursor: "pointer",
    display: "inline-flex", alignItems: "center",
  };
}


function AutoSpecsLine({ listing }) {
  // Backend pune year, mileage in items + specs in dict; ne folosim de ce-i la indemana.
  const specs = listing.specs || {};
  const parts = [];
  const year = listing.year || specs.an || specs.An;
  const mileage = listing.mileage || specs.km || specs.Km;
  const fuel = specs.Combustibil || specs.combustibil || specs.fuel || specs.Fuel;
  const gearbox = specs.Cutie || specs.cutie || specs.transmission;
  if (year) parts.push(year);
  if (mileage) parts.push(`${Number(mileage).toLocaleString("ro-RO")} km`);
  if (fuel) parts.push(fuel);
  if (gearbox) parts.push(gearbox);
  if (parts.length === 0) return null;
  return <span style={{ color: "var(--text-secondary)" }}>{parts.join(" · ")}</span>;
}


function MessageTemplateBlock({ listing, templates }) {
  const compat = templates.filter((t) => t.platform === "all" || t.platform === listing.platform);
  const [templateId, setTemplateId] = useState(compat[0]?.id || "");
  const defaultPretOferit = Math.round(listing.fee_ceiling || listing.price * 0.9);
  const [pret, setPret] = useState(defaultPretOferit);
  const [rendered, setRendered] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (compat[0]?.id && !templateId) setTemplateId(compat[0].id);
    setPret(Math.round(listing.fee_ceiling || listing.price * 0.9));
  }, [listing.id]);

  if (templates.length === 0) {
    return (
      <div style={{ padding: "0 1.25rem 1rem" }}>
        <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
          <MessageSquare style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
          Mesaje rapide
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
          Configurează șabloane în <a href="/dashboard/radar/templates" style={{ color: "var(--blue-light)" }}>Șabloane Mesaje</a>.
        </div>
      </div>
    );
  }

  const render = async () => {
    if (!templateId) return;
    setBusy(true);
    try {
      const r = await radarAPI.renderTemplate(templateId, {
        listing_id: listing.id,
        pret_oferit: parseFloat(pret) || null,
      });
      setRendered(r.data?.rendered_text || "");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la randare șablon.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!rendered) return;
    try {
      await navigator.clipboard.writeText(rendered);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      alert("Nu am putut copia. Selectează manual textul.");
    }
  };

  const ctlStyle = {
    backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.375rem", padding: "0.4rem 0.5rem",
    color: "var(--text-primary)", fontSize: "0.75rem", outline: "none",
  };

  return (
    <div style={{ padding: "0 1.25rem 1rem" }}>
      <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
        <MessageSquare style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
        Mesaje rapide
      </div>
      <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
        <select
          value={templateId}
          onChange={(e) => setTemplateId(parseInt(e.target.value) || "")}
          style={{ ...ctlStyle, minWidth: "200px" }}
        >
          {compat.length === 0 && <option value="">Niciun șablon pentru această platformă</option>}
          {compat.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <input
          type="number"
          value={pret}
          onChange={(e) => setPret(e.target.value)}
          style={{ ...ctlStyle, width: "120px" }}
          placeholder="Preț oferit"
        />
        <button onClick={render} disabled={busy || !templateId} style={{
          padding: "0.4rem 0.625rem",
          backgroundColor: "var(--blue-primary)", color: "white",
          border: "none", borderRadius: "0.375rem",
          fontSize: "0.75rem", fontWeight: 600,
          cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1,
        }}>
          {busy ? "..." : "Randează"}
        </button>
      </div>
      {rendered && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <textarea
            readOnly
            value={rendered}
            rows={4}
            style={{
              width: "100%",
              backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
              borderRadius: "0.375rem", padding: "0.5rem 0.625rem",
              color: "var(--text-primary)", fontSize: "0.8125rem",
              fontFamily: "inherit", resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: "0.375rem" }}>
            <button onClick={copy} style={{
              padding: "0.375rem 0.625rem",
              backgroundColor: copied ? "rgba(22,163,74,0.15)" : "var(--bg-dark)",
              color: copied ? "#4ade80" : "var(--text-primary)",
              border: `1px solid ${copied ? "rgba(22,163,74,0.3)" : "var(--border-color)"}`,
              borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
              cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.25rem",
            }}>
              {copied ? <Check style={{ width: "12px", height: "12px" }} /> : <Copy style={{ width: "12px", height: "12px" }} />}
              {copied ? "Copiat!" : "Copiază"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
