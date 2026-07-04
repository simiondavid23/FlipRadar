"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { radarAPI, mlAPI } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Radar, RefreshCw, ImageOff, ExternalLink, Bookmark, EyeOff,
  X, Sparkles, ShieldOff, Tag, MapPin, Calendar, FileSpreadsheet,
  GitCompareArrows, MessageSquare, Copy, Check, Trash2, Scale
} from "lucide-react";
import StatCardsRow from "@/components/shared/StatCardsRow";
import ScanNowButton from "@/components/shared/ScanNowButton";

// ── ML Predictor: detectie categorie + construire features din anunt ──
function detectMLCategory(title = "") {
  const t = title.toLowerCase();
  if (/iphone|ipad|macbook|airpod/.test(t)) return "electronics_apple";
  if (/\bbmw\b/.test(t)) return "auto_bmw";
  return null;
}

function buildFeaturesFromListing(listing, category) {
  const title = listing.title || "";
  if (category === "electronics_apple") {
    return {
      product_line: /iphone/i.test(title) ? "iPhone"
        : /ipad/i.test(title) ? "iPad"
          : /macbook/i.test(title) ? "MacBook"
            : "iPhone",
      price: listing.price,
      platform: listing.platform,
    };
  }
  if (category === "auto_bmw") {
    return { make: "BMW", price: listing.price, platform: listing.platform };
  }
  return {};
}

const PLATFORMS = [
  { value: "", label: "Toate platformele" },
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "Lajumate" },
  { value: "publi24", label: "Publi24" },
];

const SCORES = [
  { value: "", label: "Toate scorurile" },
  { value: "A", label: "A — Excelent" },
  { value: "B", label: "B — Bun" },
  { value: "C", label: "C — Ok" },
  { value: "D", label: "D — Slab" },
];

const STATUS_OPTIONS = [
  { label: "Active", value: "active" },
  { label: "Salvate", value: "saved" },
  { label: "Ignorate", value: "ignored" },
];

const PLATFORM_COLORS = {
  olx: { bg: "rgba(37,99,235,0.15)", border: "#2563eb", text: "#60a5fa" },
  vinted: { bg: "rgba(147,51,234,0.15)", border: "#9333ea", text: "#c4b5fd" },
  okazii: { bg: "rgba(22,163,74,0.15)", border: "#16a34a", text: "#4ade80" },
  facebook: { bg: "rgba(30,58,138,0.25)", border: "#1e40af", text: "#93c5fd" },
  lajumate: { bg: "rgba(249,115,22,0.15)", border: "#f97316", text: "#fdba74" },
  publi24: { bg: "rgba(21,128,61,0.18)", border: "#15803d", text: "#86efac" },
};

// FIX 7 — eticheta dinamica pentru butonul "Deschide" in functie de platforma.
const PLATFORM_LABELS = {
  olx: "Deschide pe OLX",
  vinted: "Deschide pe Vinted",
  okazii: "Deschide pe Okazii",
  facebook: "Deschide pe Facebook",
  lajumate: "Deschide pe LaJumate",
  publi24: "Deschide pe Publi24",
};

// FIX 2 — tab-uri pill (Feed Automat / Căutare Manuală).
function tabPillStyle(active) {
  return {
    padding: "0.5rem 1.25rem",
    borderRadius: "999px",
    fontSize: "0.875rem",
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid var(--border-color)",
    backgroundColor: active ? "var(--blue-primary)" : "transparent",
    color: active ? "white" : "var(--text-secondary)",
    transition: "all 0.15s ease",
  };
}

// MODULE 4 — platforme pentru cautarea manuala (single-select, ca in modalul keyword).
const SEARCH_PLATFORMS = [
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "LaJumate" },
  { value: "publi24", label: "Publi24" },
];

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

const FEED_PER_PAGE = 100;

export default function RadarFeedPage() {
  const [listings, setListings] = useState([]);
  const [feedTotal, setFeedTotal] = useState(0);
  const [feedPage, setFeedPage] = useState(1);
  const [keywords, setKeywords] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState(null);
  const [generatingAI, setGeneratingAI] = useState(false);
  const [selectedForComparison, setSelectedForComparison] = useState([]);
  const [selectedBulk, setSelectedBulk] = useState(new Set());
  const [showCompare, setShowCompare] = useState(false);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("auto");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [stats, setStats] = useState({});
  const [scanning, setScanning] = useState(false);

  const [filters, setFilters] = useState({
    platform: "",
    score: "",
    keyword_id: "",
    status: "active",
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

  const loadStats = useCallback(async () => {
    try {
      const r = await radarAPI.getStats();
      setStats(r.data || {});
    } catch (e) {
      console.error("[Radar] stats:", e);
    }
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const _listingParams = useCallback((page) => {
    const params = { hide_filtered: filters.hide_filtered, per_page: FEED_PER_PAGE, page };
    if (filters.platform) params.platform = filters.platform;
    if (filters.score) params.score = filters.score;
    if (filters.keyword_id) params.keyword_id = filters.keyword_id;
    if (filters.status) params.status = filters.status;
    return params;
  }, [filters]);

  const loadListings = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await radarAPI.getListings(_listingParams(1));
      setListings(r.data?.items || []);
      setFeedTotal(r.data?.total || 0);
      setFeedPage(1);
    } catch (e) {
      console.error("[Radar] listings:", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [_listingParams]);

  const loadMoreListings = useCallback(async () => {
    const next = feedPage + 1;
    setRefreshing(true);
    try {
      const r = await radarAPI.getListings(_listingParams(next));
      setListings((prev) => [...prev, ...(r.data?.items || [])]);
      setFeedTotal(r.data?.total || 0);
      setFeedPage(next);
    } catch (e) {
      console.error("[Radar] loadMore:", e);
    } finally {
      setRefreshing(false);
    }
  }, [_listingParams, feedPage]);

  const handleScanNow = async () => {
    setScanning(true);
    try {
      await radarAPI.scanNow();
      // Lăsăm scannerul de fundal să lucreze, apoi reîmprospătăm feed + statistici.
      setTimeout(() => { loadListings(); loadStats(); setScanning(false); }, 15000);
    } catch {
      setScanning(false);
    }
  };

  useEffect(() => {
    loadKeywords();
    loadTemplates();
    loadStats();
  }, [loadKeywords, loadTemplates, loadStats]);

  useEffect(() => {
    loadListings();
  }, [loadListings]);

  const updateStatus = async (listingId, newStatus) => {
    try {
      await radarAPI.updateListingStatus(listingId, newStatus);
      setListings((prev) =>
        prev.map((l) => l.id === listingId ? { ...l, status: newStatus } : l)
      );
      if (selected?.id === listingId) {
        setSelected((prev) => prev ? { ...prev, status: newStatus } : null);
      }
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
    }
  };

  const deleteListing = async (listingId) => {
    try {
      await radarAPI.deleteListing(listingId);
      setListings((prev) => prev.filter((l) => l.id !== listingId));
      if (selected?.id === listingId) setSelected(null);
      setConfirmDeleteId(null);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la ștergere.");
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

  const loadVintedDetail = async (listingId) => {
    try {
      const r = await radarAPI.getVintedDetail(listingId);
      setSelected((prev) => (prev && prev.id === listingId ? { ...prev, ...r.data } : prev));
      return !!r.data.vinted_detail_fetched;
    } catch (e) {
      console.error("Eroare la încărcarea detaliilor Vinted:", e);
      return false;
    }
  };

  const loadFacebookDetail = async (listingId) => {
    try {
      const r = await radarAPI.getFacebookDetail(listingId);
      setSelected((prev) => (prev && prev.id === listingId ? { ...prev, ...r.data } : prev));
      return !!r.data.facebook_detail_fetched;
    } catch (e) {
      console.error("Eroare la încărcarea detaliilor Facebook:", e);
      return false;
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
    setSelectedBulk((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAllBulk = (e) => {
    if (e.target.checked) {
      setSelectedBulk(new Set(listings.map((l) => l.id)));
    } else {
      setSelectedBulk(new Set());
    }
  };

  const applyBulkAction = async (action) => {
    if (selectedBulk.size === 0) return;
    try {
      const r = await radarAPI.bulkAction(Array.from(selectedBulk), action);
      showToast(r.data?.message || `${r.data?.updated || 0} listinguri actualizate.`);
      setSelectedBulk(new Set());
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

  const byScore = stats.listings_by_score || {};
  const statCards = [
    { label: "Anunțuri găsite", value: stats.total_listings_found ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Grad A", value: byScore.A ?? 0, color: "#4ade80" },
    { label: "Grad B", value: byScore.B ?? 0, color: "#60a5fa" },
  ];

  return (
    <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
      {/* Header permanent (vizibil pe ambele tab-uri) */}
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

      {/* Faza 2 — scanare manuală + statistici (deasupra tab-urilor) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <ScanNowButton onScan={handleScanNow} scanning={scanning} />
      </div>
      <StatCardsRow cards={statCards} />

      {/* FIX 2 — Tab-uri: Feed Automat / Căutare Manuală */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button onClick={() => setActiveTab("auto")} style={tabPillStyle(activeTab === "auto")}>Feed Automat</button>
        <button onClick={() => setActiveTab("manual")} style={tabPillStyle(activeTab === "manual")}>Căutare Manuală</button>
      </div>

      {activeTab === "manual" && <ManualSearchTab />}

      {activeTab === "auto" && (loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : (
      <>
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
          {[...keywords]
            .sort((a, b) => a.name.localeCompare(b.name, "ro"))
            .map((k) => {
              const platformValue = k.platform || (Array.isArray(k.platforms) && k.platforms.length === 1 ? k.platforms[0] : null);
              const platformLabel = platformValue ? (PLATFORMS.find((p) => p.value === platformValue)?.label || platformValue) : null;
              return (
                <option key={k.id} value={k.id}>
                  {k.name}{platformLabel ? ` — ${platformLabel}` : ""}
                </option>
              );
            })}
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
          selectedCount={selectedBulk.size}
          onSelect={(count) => {
            if (count === 0) {
              setSelectedBulk(new Set());
              return;
            }
            setSelectedBulk(new Set(listings.slice(0, count).map((l) => l.id)));
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

      {/* MODULE 3b — bara de acțiuni sticky (sub controale, deasupra grilei) */}
      <div style={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        marginBottom: (selectedBulk.size > 0 || selectedForComparison.length > 0) ? "0.75rem" : 0,
      }}>
        <div style={{
          maxHeight: (selectedBulk.size > 0 || selectedForComparison.length > 0) ? "160px" : "0px",
          overflow: "hidden",
          opacity: (selectedBulk.size > 0 || selectedForComparison.length > 0) ? 1 : 0,
          transition: "max-height 0.2s ease, opacity 0.15s ease",
        }}>
          <ActionBanner
            comparisonCount={selectedForComparison.length}
            bulkCount={selectedBulk.size}
            totalVisible={listings.length}
            onCompareOpen={() => setShowCompare(true)}
            onCompareClear={() => setSelectedForComparison([])}
            onBulkSave={() => applyBulkAction("saved")}
            onBulkIgnore={() => applyBulkAction("ignored")}
            onBulkDelete={() => applyBulkAction("deleted")}
            onBulkExport={async () => {
              try {
                const r = await radarAPI.exportListings({ ids: Array.from(selectedBulk).join(",") });
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
            onBulkClear={() => setSelectedBulk(new Set())}
          />
        </div>
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
              bulkSelected={selectedBulk.has(l.id)}
              isSelected={selectedBulk.has(l.id)}
              onToggleSelect={() => toggleBulk(l.id)}
              onToggleCompare={() => toggleCompare(l)}
              onToggleBulk={() => toggleBulk(l.id)}
              onDelete={() => setConfirmDeleteId(l.id)}
              confirmingDelete={confirmDeleteId === l.id}
              onConfirmDelete={() => deleteListing(l.id)}
              onCancelDelete={() => setConfirmDeleteId(null)}
            />
          ))}
        </div>
      )}

      {listings.length > 0 && listings.length < feedTotal && (
        <div style={{ textAlign: "center", marginTop: "1.25rem" }}>
          <button
            onClick={loadMoreListings}
            disabled={refreshing}
            style={{
              padding: "0.6rem 1.5rem",
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.5rem",
              color: "var(--text-primary)",
              cursor: refreshing ? "default" : "pointer",
              opacity: refreshing ? 0.6 : 1,
              fontSize: "0.875rem",
            }}
          >
            {refreshing ? "Se încarcă…" : `Încarcă mai multe (${feedTotal - listings.length} rămase)`}
          </button>
        </div>
      )}
      </>
      ))}

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
          onLoadVintedDetail={loadVintedDetail}
          onLoadFacebookDetail={loadFacebookDetail}
        />
      )}

      {/* Fereastră comparare */}
      {showCompare && selectedForComparison.length >= 2 && (
        <CompareModal
          listings={selectedForComparison}
          onClose={() => setShowCompare(false)}
          onSave={async (id) => { await updateStatus(id, "saved"); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: "saved" } : l)); }}
          onIgnore={async (id) => { await updateStatus(id, "ignored"); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: "ignored" } : l)); }}
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

function ListingCard({ listing, onOpen, onSave, onIgnore, compareSelected, bulkSelected, isSelected, onToggleSelect, onToggleCompare, onToggleBulk, onDelete, confirmingDelete, onConfirmDelete, onCancelDelete }) {
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
        position: "relative",
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
      {/* MODULE 2 — strip de selecție deasupra imaginii */}
      <div
        onClick={(e) => { e.stopPropagation(); onToggleSelect(); }}
        style={{
          display: "flex", alignItems: "center", gap: "0.5rem",
          padding: "0.3rem 0.625rem",
          borderBottom: "0.5px solid var(--border-color)",
          borderRadius: "0.75rem 0.75rem 0 0",
          backgroundColor: isSelected ? "rgba(37,99,235,0.08)" : "transparent",
          cursor: "pointer",
          transition: "background-color 0.12s",
          flexShrink: 0,
        }}
      >
        <div style={{
          width: "14px", height: "14px", borderRadius: "3px", flexShrink: 0,
          border: isSelected ? "2px solid #2563eb" : "1.5px solid rgba(100,116,139,0.45)",
          backgroundColor: isSelected ? "#2563eb" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.1s",
        }}>
          {isSelected && <span style={{ color: "white", fontSize: "9px", fontWeight: 700 }}>✓</span>}
        </div>
        <span style={{ fontSize: "0.6875rem", color: isSelected ? "#60a5fa" : "var(--text-secondary)", userSelect: "none" }}>
          {isSelected ? "Selectat" : "Selectează"}
        </span>
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
          {listing.location && <span>{listing.location}</span>}
          <span>
            {listing.listed_at && formatListedDate(listing.listed_at) ? (
              <>Postat: {formatListedDate(listing.listed_at)} · Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            ) : (
              <>Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            )}
          </span>
        </div>

        {confirmingDelete ? (
          <div onClick={(e) => e.stopPropagation()} style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            marginTop: "auto",
            padding: "0.5rem 0.75rem",
            borderTop: "1px solid rgba(239,68,68,0.3)",
            backgroundColor: "rgba(239,68,68,0.05)",
          }}>
            <span style={{ fontSize: "0.75rem", color: "#fca5a5", flex: 1 }}>
              Ștergi acest anunț definitiv?
            </span>
            <button onClick={onConfirmDelete} style={{ padding: "0.25rem 0.625rem", backgroundColor: "rgba(239,68,68,0.2)", color: "#f87171", border: "1px solid rgba(239,68,68,0.4)", borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer" }}>
              Confirmă
            </button>
            <button onClick={onCancelDelete} style={{ padding: "0.25rem 0.625rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", fontSize: "0.75rem", cursor: "pointer" }}>
              Anulează
            </button>
          </div>
        ) : (
        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem", alignItems: "center" }}>
          <button
            onClick={(e) => { e.stopPropagation(); if (listing.status !== "saved") onSave(); }}
            disabled={listing.status === "saved"}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
              padding: "0.375rem 0.75rem",
              backgroundColor: listing.status === "saved" ? "rgba(22,163,74,0.2)" : "rgba(22,163,74,0.08)",
              color: "#4ade80",
              border: "1px solid rgba(22,163,74,0.35)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem", fontWeight: 600,
              cursor: listing.status === "saved" ? "default" : "pointer",
            }}
          >
            <Bookmark style={{ width: "12px", height: "12px" }} />
            {listing.status === "saved" ? "✓ Salvat" : "Salvează"}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); if (listing.status !== "ignored") onIgnore(); }}
            disabled={listing.status === "ignored"}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
              padding: "0.375rem 0.75rem",
              backgroundColor: listing.status === "ignored" ? "rgba(100,116,139,0.2)" : "rgba(100,116,139,0.08)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem", fontWeight: 600,
              cursor: listing.status === "ignored" ? "default" : "pointer",
            }}
          >
            <EyeOff style={{ width: "12px", height: "12px" }} />
            {listing.status === "ignored" ? "✓ Ignorat" : "Ignoră"}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); window.open(listing.url, "_blank", "noopener,noreferrer"); }}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title={PLATFORM_LABELS[listing.platform?.toLowerCase()] || "Deschide anunțul"}
          >
            <ExternalLink style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            {PLATFORM_LABELS[listing.platform?.toLowerCase()] || "Deschide anunțul"}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
            title={compareSelected ? "Scoate din comparare" : "Adaugă la comparare"}
            style={{
              background: "transparent", border: "none", cursor: "pointer",
              padding: "0.25rem", borderRadius: "0.375rem",
              color: compareSelected ? "#60a5fa" : "var(--text-secondary)",
              backgroundColor: compareSelected ? "rgba(37,99,235,0.12)" : "transparent",
              display: "inline-flex", alignItems: "center",
              transition: "all 0.12s",
            }}
          >
            <Scale style={{ width: "14px", height: "14px" }} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title="Șterge anunțul"
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "#f87171",
              display: "inline-flex",
              alignItems: "center",
              padding: "0.25rem",
              borderRadius: "0.375rem",
            }}
          >
            <Trash2 style={{ width: "14px", height: "14px" }} />
          </button>
        </div>
        )}
      </div>
    </div>
  );
}

// FIX 2 — tab-ul de căutare manuală (live, fără salvare în DB).
function ManualSearchTab() {
  const [keyword, setKeyword] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [searchPlatform, setSearchPlatform] = useState("");
  const [searchMainCat, setSearchMainCat] = useState("");
  const [searchSubCat, setSearchSubCat] = useState("");
  const [allCategories, setAllCategories] = useState({});
  const [results, setResults] = useState(null); // null = încă nu s-a căutat
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    radarAPI.getCategories()
      .then((r) => setAllCategories(r.data || {}))
      .catch(() => {});
  }, []);

  const runSearch = async () => {
    if (!keyword.trim()) { alert("Introdu un keyword pentru căutare."); return; }
    if (!maxPrice || parseFloat(maxPrice) <= 0) { alert("Introdu un preț maxim valid."); return; }
    if (!searchPlatform) { alert("Selectează o platformă."); return; }
    const derivedCategory = searchSubCat || searchMainCat || "";
    setLoading(true);
    try {
      const r = await radarAPI.searchManual({
        keyword: keyword.trim(),
        max_price: parseFloat(maxPrice),
        min_price: minPrice ? parseFloat(minPrice) : null,
        platform: searchPlatform,
        platforms: [searchPlatform],
        category: derivedCategory || null,
        exclude_words: [],
      });
      setResults(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la căutare.");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: "100%",
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.5rem",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    outline: "none",
  };
  const labelStyle = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };

  return (
    <div>
      {/* Formular căutare */}
      <div style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        padding: "1.25rem",
        marginBottom: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.875rem",
      }}>
        <div>
          <label style={labelStyle}>Keyword *</label>
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
            placeholder="ex: iPhone 13 Pro"
            style={inputStyle}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
          <div>
            <label style={labelStyle}>Preț maxim (RON)</label>
            <input type="number" min="0" step="any" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="ex: 2000" style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Preț minim (RON) — opțional</label>
            <input type="number" min="0" step="any" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} placeholder="ex: 100" style={inputStyle} />
          </div>
        </div>

        <div>
          <label style={labelStyle}>Platformă</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {SEARCH_PLATFORMS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => { setSearchPlatform(p.value); setSearchMainCat(""); setSearchSubCat(""); }}
                style={{
                  padding: "0.375rem 0.875rem", borderRadius: "0.5rem", fontSize: "0.8125rem",
                  fontWeight: searchPlatform === p.value ? 600 : 400, cursor: "pointer",
                  border: searchPlatform === p.value ? "2px solid #2563eb" : "1px solid var(--border-color)",
                  backgroundColor: searchPlatform === p.value ? "rgba(37,99,235,0.15)" : "var(--bg-dark)",
                  color: searchPlatform === p.value ? "#60a5fa" : "var(--text-secondary)",
                }}
              >{p.label}</button>
            ))}
          </div>
        </div>

        {searchPlatform && (() => {
          const currentPlatformCats = allCategories[searchPlatform] || [];
          const selectedMain = currentPlatformCats.find((c) => c.value === searchMainCat);
          const hasSubs = (selectedMain?.subcategories?.length || 0) > 0;
          return (
            <div style={{ display: "grid", gridTemplateColumns: hasSubs ? "1fr 1fr" : "1fr", gap: "0.75rem" }}>
              <div>
                <label style={labelStyle}>Categorie principală</label>
                <select value={searchMainCat} onChange={(e) => { setSearchMainCat(e.target.value); setSearchSubCat(""); }} style={inputStyle}>
                  <option value="">Toate categoriile</option>
                  {currentPlatformCats.map((c) => (
                    <option key={c.value ?? c.label} value={c.value ?? ""}>{c.label}</option>
                  ))}
                </select>
              </div>
              {hasSubs && (
                <div>
                  <label style={labelStyle}>Subcategorie</label>
                  <select value={searchSubCat} onChange={(e) => setSearchSubCat(e.target.value)} style={inputStyle}>
                    <option value="">Toate</option>
                    {selectedMain.subcategories.map((s) => (
                      <option key={s.value ?? s.label} value={s.value ?? ""}>{s.label}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })()}

        <div>
          <button
            onClick={runSearch}
            disabled={loading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem 1.25rem",
              backgroundColor: "var(--blue-primary)",
              color: "white",
              border: "none",
              borderRadius: "0.5rem",
              fontSize: "0.875rem",
              fontWeight: 600,
              cursor: loading ? "wait" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            <Radar style={{ width: "16px", height: "16px" }} />
            {loading ? "Se caută..." : "Caută"}
          </button>
        </div>
      </div>

      {/* Rezultate */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "12rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : results === null ? null : results.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "3rem",
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          color: "var(--text-secondary)",
        }}>
          Niciun rezultat găsit pentru această căutare.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
          {results.map((listing, idx) => (
            <ManualResultCard key={`${listing.url || "r"}-${idx}`} listing={listing} />
          ))}
        </div>
      )}
    </div>
  );
}

// FIX 2 — card pentru rezultatele căutării manuale (stil identic cu feed-ul).
function ManualResultCard({ listing }) {
  const platformCfg = PLATFORM_COLORS[listing.platform?.toLowerCase()] || PLATFORM_COLORS.olx;
  const image = listing.images?.[0];
  const margin = listing.margin_pct;

  return (
    <div
      style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
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

        {margin !== null && margin !== undefined && (
          <div style={{ fontSize: "0.75rem", color: marginColor(margin) }}>
            Marjă estimată: <strong>{Math.round(margin)}%</strong>
          </div>
        )}

        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          {listing.location && <span>{listing.location}</span>}
          {listing.condition && <span>Condiție: {listing.condition}</span>}
        </div>

        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem" }}>
          <button
            onClick={() => window.open(listing.url, "_blank", "noopener,noreferrer")}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title={PLATFORM_LABELS[listing.platform?.toLowerCase()] || "Deschide anunțul"}
          >
            <ExternalLink style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            {PLATFORM_LABELS[listing.platform?.toLowerCase()] || "Deschide anunțul"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ListingModal({ listing, templates = [], onClose, onSave, onIgnore, onBlockSeller, onGenerateAI, generatingAI, onLoadVintedDetail, onLoadFacebookDetail }) {
  const { user } = useAuth();
  const reviewEnabled = user?.ai_features_config?.ai_radar_review !== false;
  const scoreCfg = SCORE_COLORS[listing.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" };
  const platformCfg = PLATFORM_COLORS[listing.platform] || PLATFORM_COLORS.olx;
  const images = listing.images || [];
  const [mainImg, setMainImg] = useState(images[0] || null);
  useEffect(() => { setMainImg(images[0] || null); }, [listing.id]);

  // ── Predictie ML (separata de pretul de revanzare manual) ──
  const [mlPrediction, setMlPrediction] = useState(null);
  const [mlLoading, setMlLoading] = useState(false);
  const [mlCategory, setMlCategory] = useState(null);
  const [vintedDetailStatus, setVintedDetailStatus] = useState(null);
  const [facebookDetailStatus, setFacebookDetailStatus] = useState(null);
  // valori posibile: null (nu e nevoie) | "loading" | "success" | "failed"

  useEffect(() => {
    if (!listing) { setMlPrediction(null); return; }
    const cat = detectMLCategory(listing.title);
    setMlCategory(cat);
    if (!cat) { setMlPrediction(null); return; }
    setMlLoading(true);
    mlAPI.predict({
      category: cat,
      features: buildFeaturesFromListing(listing, cat),
    })
      .then((r) => setMlPrediction(r.data))
      .catch((err) => {
        const msg = err.response?.data?.detail;
        setMlPrediction(
          msg === "model_not_trained" ? { error: "model_not_trained" }
            : msg === "features_incomplete" ? { error: "features_incomplete" }
              : { error: "unavailable" }
        );
      })
      .finally(() => setMlLoading(false));
  }, [listing?.id]);

  // PARTEA A — fetch on-demand al detaliului Vinted complet (poze/descriere/data)
  // cand anuntul are doar thumbnail-ul unic din cautare. O singura data (cache DB).
  useEffect(() => {
    if (!listing || listing.platform !== "vinted") return;
    if (listing.vinted_detail_fetched) return; // deja cache-uit, nu mai apelam
    const needsDetail = (listing.images || []).length <= 1 || !listing.description;
    if (!needsDetail) return;
    let cancelled = false;
    setVintedDetailStatus("loading");
    Promise.resolve(onLoadVintedDetail?.(listing.id)).then((ok) => {
      if (cancelled) return;
      setVintedDetailStatus(ok ? "success" : "failed");
    });
    return () => { cancelled = true; };
  }, [listing.id]);

  // Facebook — mirror pe Vinted: fetch on-demand descriere + galerie completa
  // cand anuntul are doar thumbnail-ul unic din cautare. O singura data (cache DB).
  useEffect(() => {
    if (!listing || listing.platform !== "facebook") return;
    if (listing.facebook_detail_fetched) return; // deja cache-uit, nu mai apelam
    const needsDetail = (listing.images || []).length <= 1 || !listing.description;
    if (!needsDetail) return;
    let cancelled = false;
    setFacebookDetailStatus("loading");
    Promise.resolve(onLoadFacebookDetail?.(listing.id)).then((ok) => {
      if (cancelled) return;
      setFacebookDetailStatus(ok ? "success" : "failed");
    });
    return () => { cancelled = true; };
  }, [listing.id]);

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

        {listing.platform === "vinted" && vintedDetailStatus === "loading" && (
          <div style={{ padding: "0 1.25rem", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Se încarcă poze și descriere complete de pe Vinted...
          </div>
        )}
        {listing.platform === "vinted" && vintedDetailStatus === "failed" && (
          <div style={{ padding: "0 1.25rem", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Detalii suplimentare indisponibile momentan (limitare temporară Vinted) — vor fi reîncercate la următoarea deschidere.
          </div>
        )}
        {listing.platform === "facebook" && facebookDetailStatus === "loading" && (
          <div style={{ padding: "0 1.25rem", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Se încarcă descriere și galerie complete de pe Facebook...
          </div>
        )}
        {listing.platform === "facebook" && facebookDetailStatus === "failed" && (
          <div style={{ padding: "0 1.25rem", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Detalii suplimentare indisponibile momentan — vor fi reîncercate la următoarea deschidere.
          </div>
        )}

        {/* Descriere */}
        {listing.description && (
          <div style={{ padding: "0 1.25rem 1rem" }}>
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Descriere</div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{listing.description}</div>
          </div>
        )}

        {/* Predictie ML — apare intre informatiile de pret si Review AI */}
        {mlCategory && (
          <div style={{ margin: "0 1.25rem 1rem" }}>
            <div style={{
              padding: "0.875rem 1rem",
              backgroundColor: "rgba(124,58,237,0.07)",
              border: "0.5px solid rgba(124,58,237,0.25)",
              borderRadius: "0.625rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <span style={{ fontSize: "0.75rem", color: "#a78bfa", fontWeight: 600, letterSpacing: "0.04em" }}>
                  PREDICȚIE ML
                </span>
              </div>

              {mlLoading && (
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                  Se calculează...
                </p>
              )}

              {!mlLoading && mlPrediction && !mlPrediction.error && (
                <div>
                  <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                    Estimat: {mlPrediction.price?.toLocaleString("ro-RO")} RON
                    {mlPrediction.days && (
                      <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 400, marginLeft: "0.5rem" }}>
                        · vândut în ~{mlPrediction.days} zile
                      </span>
                    )}
                  </p>
                  <p style={{ fontSize: "0.7rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                    Predicție separată de prețul de revânzare introdus manual.
                  </p>
                </div>
              )}

              {!mlLoading && mlPrediction?.error === "model_not_trained" && (
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                  Model neantrenat — date insuficiente.{" "}
                  <a href="/dashboard/ml-predictor" style={{ color: "#a78bfa" }}>
                    Vezi progresul →
                  </a>
                </p>
              )}

              {!mlLoading && mlPrediction?.error === "features_incomplete" && (
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                  Features insuficiente pentru predicție (titlu prea vag).
                </p>
              )}
            </div>
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
            <>
            <button
              onClick={reviewEnabled ? onGenerateAI : undefined}
              disabled={generatingAI}
              style={{
                padding: "0.5rem 0.875rem",
                backgroundColor: "rgba(147,51,234,0.15)",
                color: "#c4b5fd",
                border: "1px solid rgba(147,51,234,0.3)",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: reviewEnabled ? (generatingAI ? "wait" : "pointer") : "default",
                opacity: reviewEnabled ? 1 : 0.4,
              }}
            >
              {generatingAI ? "Se generează..." : "Generează review AI"}
            </button>
            {!reviewEnabled && (
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                Feature dezactivat · <a href="/dashboard/settings" style={{ color: "#60a5fa" }}>Activează din Setări</a>
              </p>
            )}
            </>
          )}
        </div>

        {/* Mesaje rapide */}
        <MessageTemplateBlock listing={listing} templates={templates} />

        {/* Acțiuni */}
        <div style={{ padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            onClick={listing.status !== "saved" ? onSave : undefined}
            disabled={listing.status === "saved"}
            style={btn(
              listing.status === "saved" ? "#4ade80" : "#4ade80",
              listing.status === "saved" ? "rgba(22,163,74,0.25)" : "rgba(22,163,74,0.15)",
              "rgba(22,163,74,0.3)"
            )}
          >
            <Bookmark style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            {listing.status === "saved" ? "✓ Salvat" : "Salvează"}
          </button>
          <button
            onClick={listing.status !== "ignored" ? onIgnore : undefined}
            disabled={listing.status === "ignored"}
            style={btn(
              "var(--text-secondary)",
              listing.status === "ignored" ? "rgba(100,116,139,0.2)" : "rgba(100,116,139,0.15)",
              "var(--border-color)"
            )}
          >
            <EyeOff style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            {listing.status === "ignored" ? "✓ Ignorat" : "Ignoră"}
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
            {PLATFORM_LABELS[listing.platform?.toLowerCase()] || "Deschide anunțul"}
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
      backgroundColor: "rgba(37,99,235,0.1)",
      border: "0.5px solid rgba(37,99,235,0.3)",
      borderRadius: "0.5rem",
      padding: "0.625rem 1rem",
      display: "flex", flexWrap: "wrap",
      alignItems: "center", gap: "0.75rem",
      backdropFilter: "blur(8px)",
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
                  <button
                    onClick={() => { if (l.status !== "saved") onSave(l.id); }}
                    disabled={l.status === "saved"}
                    title="Salvează"
                    style={smallActionBtn("#4ade80", l.status === "saved" ? "rgba(22,163,74,0.3)" : "rgba(22,163,74,0.15)", "rgba(22,163,74,0.3)")}
                  >
                    {l.status === "saved" ? "✓ Salvat" : "💾"}
                  </button>
                  <button
                    onClick={() => { if (l.status !== "ignored") onIgnore(l.id); }}
                    disabled={l.status === "ignored"}
                    title="Ignoră"
                    style={smallActionBtn("var(--text-secondary)", l.status === "ignored" ? "rgba(100,116,139,0.3)" : "var(--bg-card)", "var(--border-color)")}
                  >
                    {l.status === "ignored" ? "✓ Ignorat" : "👁"}
                  </button>
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
          {busy ? "..." : "Generează"}
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
