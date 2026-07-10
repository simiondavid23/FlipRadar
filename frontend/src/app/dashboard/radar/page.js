"use client";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { radarAPI, mlAPI } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Radar, RefreshCw, ImageOff, ExternalLink, Bookmark, EyeOff,
  X, FileSpreadsheet, Check
} from "lucide-react";
import StatCardsRow from "@/components/shared/StatCardsRow";
import ScanNowButton from "@/components/shared/ScanNowButton";
import SelectFiniteControl from "@/components/shared/SelectFiniteControl";
import ListingFeedCard from "@/components/shared/ListingFeedCard";
import ListingDetailModal from "@/components/shared/ListingDetailModal";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import ActionBanner from "@/components/shared/ActionBanner";

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

export const PLATFORM_COLORS = {
  olx: { bg: "rgba(37,99,235,0.15)", border: "#2563eb", text: "#60a5fa" },
  vinted: { bg: "rgba(147,51,234,0.15)", border: "#9333ea", text: "#c4b5fd" },
  okazii: { bg: "rgba(22,163,74,0.15)", border: "#16a34a", text: "#4ade80" },
  facebook: { bg: "rgba(30,58,138,0.25)", border: "#1e40af", text: "#93c5fd" },
  lajumate: { bg: "rgba(249,115,22,0.15)", border: "#f97316", text: "#fdba74" },
  publi24: { bg: "rgba(21,128,61,0.18)", border: "#15803d", text: "#86efac" },
};

// FIX 7 — eticheta dinamica pentru butonul "Deschide" in functie de platforma.
export const PLATFORM_LABELS = {
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

export const SCORE_COLORS = {
  A: { bg: "rgba(22,163,74,0.18)", border: "#16a34a", text: "#4ade80" },
  B: { bg: "rgba(59,130,246,0.18)", border: "#3b82f6", text: "#60a5fa" },
  C: { bg: "rgba(250,204,21,0.18)", border: "#facc15", text: "#fde047" },
  D: { bg: "rgba(249,115,22,0.18)", border: "#f97316", text: "#fb923c" },
};

export const SCORE_EXPLANATIONS = {
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
  const { user } = useAuth();
  const reviewEnabled = user?.ai_features_config?.ai_radar_review !== false;
  const [listings, setListings] = useState([]);
  const [feedTotal, setFeedTotal] = useState(0);
  const [feedPage, setFeedPage] = useState(1);
  const [keywords, setKeywords] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const reqIdRef = useRef(0);
  const [feedError, setFeedError] = useState(null);
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
  // RP-1 — filtre/sortare client-side pe lista deja incarcata.
  const [hideRisky, setHideRisky] = useState(false);
  const [sortBy, setSortBy] = useState("");  // "" = ordinea din server; "listed_desc" = data postarii

  const displayedListings = useMemo(() => {
    let arr = listings;
    if (hideRisky) arr = arr.filter((l) => !l.seller_risk);
    if (sortBy === "listed_desc") {
      arr = [...arr].sort((a, b) => {
        const ta = a.listed_at ? new Date(a.listed_at).getTime() : -Infinity;  // null la coada
        const tb = b.listed_at ? new Date(b.listed_at).getTime() : -Infinity;
        return tb - ta;  // recente intai
      });
    }
    return arr;
  }, [listings, hideRisky, sortBy]);

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
    const rid = ++reqIdRef.current;
    setRefreshing(true);
    setFeedError(null);
    try {
      const r = await radarAPI.getListings(_listingParams(1));
      if (rid !== reqIdRef.current) return;
      setListings(r.data?.items || []);
      setFeedTotal(r.data?.total || 0);
      setFeedPage(1);
    } catch (e) {
      console.error("[Radar] listings:", e);
      if (rid === reqIdRef.current) setFeedError("Nu am putut încărca feed-ul. Reîncearcă.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [_listingParams]);

  const loadMoreListings = useCallback(async () => {
    const next = feedPage + 1;
    const rid = ++reqIdRef.current;
    setRefreshing(true);
    try {
      const r = await radarAPI.getListings(_listingParams(next));
      if (rid !== reqIdRef.current) return;
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
          {activeTab === "auto" && (
            <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
              Anunțuri găsite în timp real ({listings.length} active în vizualizare)
            </p>
          )}
        </div>
      </div>

      {/* FIX 2 — Tab-uri: Feed Automat / Căutare Manuală */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button onClick={() => setActiveTab("auto")} style={tabPillStyle(activeTab === "auto")}>Feed Automat</button>
        <button onClick={() => setActiveTab("manual")} style={tabPillStyle(activeTab === "manual")}>Căutare Manuală</button>
      </div>

      {activeTab === "manual" && <ManualSearchTab />}

      {/* Faza 2 — scanare manuală + statistici (sub tab-uri, mirror Auto/Imobiliare) */}
      {activeTab === "auto" && (
        <>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: "1rem" }}>
            <ScanNowButton onScan={handleScanNow} scanning={scanning} />
          </div>
          <StatCardsRow cards={statCards} />
        </>
      )}

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
                  {k.name}{platformLabel ? ` (${platformLabel})` : ""}
                </option>
              );
            })}
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
        {/* RP-1 — ascunde vanzatorii riscanti (client-side) */}
        <label style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          padding: "0.5rem 0.75rem", border: "1px solid var(--border-color)",
          borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)",
          color: "var(--text-primary)", fontSize: "0.8125rem", cursor: "pointer",
        }}>
          <input
            type="checkbox"
            checked={hideRisky}
            onChange={(e) => setHideRisky(e.target.checked)}
            style={{ width: "auto", margin: 0 }}
          />
          Ascunde vânzătorii riscanți
        </label>
        {/* RP-1 — sortare */}
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={selectStyle}>
          <option value="">Sortare: implicită</option>
          <option value="listed_desc">Data postării (recente)</option>
        </select>

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

      <FeedErrorBanner message={feedError} onRetry={loadListings} />

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
          {displayedListings.map((l) => (
            <ListingFeedCard
              key={l.id}
              listing={l}
              scoreCfg={SCORE_COLORS[l.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" }}
              scoreBadge={l.score}
              platformCfg={PLATFORM_COLORS[l.platform] || PLATFORM_COLORS.olx}
              platformBadge={l.platform}
              image={l.images?.[0]}
              openLabel={PLATFORM_LABELS[l.platform?.toLowerCase()] || "Deschide anunțul"}
              onOpen={() => setSelected(l)}
              onSave={() => updateStatus(l.id, l.status === "saved" ? "active" : "saved")}
              onIgnore={() => updateStatus(l.id, l.status === "ignored" ? "active" : "ignored")}
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
        <ListingDetailModal
          listing={selected}
          images={selected.images || []}
          scoreCfg={SCORE_COLORS[selected.score] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" }}
          scoreBadge={selected.score}
          scoreExplanation={SCORE_EXPLANATIONS[selected.score]}
          platformCfg={PLATFORM_COLORS[selected.platform] || PLATFORM_COLORS.olx}
          platformBadge={selected.platform}
          platformUpper={selected.platform.toUpperCase()}
          openLabel={PLATFORM_LABELS[selected.platform?.toLowerCase()] || "Deschide anunțul"}
          onClose={() => setSelected(null)}
          onSave={() => updateStatus(selected.id, selected.status === "saved" ? "active" : "saved")}
          onIgnore={() => updateStatus(selected.id, selected.status === "ignored" ? "active" : "ignored")}
          showReview
          reviewEnabled={reviewEnabled}
          onGenerateAI={() => generateAIReview(selected.id)}
          generatingAI={generatingAI}
          reviewSettingsHref="/dashboard/settings"
          showTemplates
          templates={templates}
          onRenderTemplate={radarAPI.renderTemplate}
          templatesHref="/dashboard/settings"
          detailBannerSlot={<RadarDetailBanner listing={selected} onLoadVintedDetail={loadVintedDetail} onLoadFacebookDetail={loadFacebookDetail} />}
          mlSlot={<RadarMLSection listing={selected} />}
        />
      )}

      {/* Fereastră comparare */}
      {showCompare && selectedForComparison.length >= 2 && (
        <CompareModal
          listings={selectedForComparison}
          onClose={() => setShowCompare(false)}
          onSave={async (id) => { const cur = selectedForComparison.find((l) => l.id === id); const ns = cur?.status === "saved" ? "active" : "saved"; await updateStatus(id, ns); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: ns } : l)); }}
          onIgnore={async (id) => { const cur = selectedForComparison.find((l) => l.id === id); const ns = cur?.status === "ignored" ? "active" : "ignored"; await updateStatus(id, ns); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: ns } : l)); }}
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

// Slot ML pentru modalul partajat — mutat 1:1 din ListingModal (hooks + JSX identice).
export function RadarMLSection({ listing }) {
  // mlCategory e pur derivat din titlu; mlState reține DOAR rezultatul fetch-ului
  // (etichetat cu id-ul listing-ului). loading/prediction se derivă în render, deci
  // singurul setState e în .then/.catch (asincron), nu sincron în efect.
  const mlCategory = listing ? detectMLCategory(listing.title) : null;
  const [mlState, setMlState] = useState({ id: null, data: null });

  useEffect(() => {
    if (!listing || !mlCategory) return;
    let cancelled = false;
    mlAPI.predict({
      category: mlCategory,
      features: buildFeaturesFromListing(listing, mlCategory),
    })
      .then((r) => { if (!cancelled) setMlState({ id: listing.id, data: r.data }); })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail;
        setMlState({ id: listing.id, data:
          msg === "model_not_trained" ? { error: "model_not_trained" }
            : msg === "features_incomplete" ? { error: "features_incomplete" }
              : { error: "unavailable" }
        });
      });
    return () => { cancelled = true; };
  }, [listing?.id, mlCategory]);

  if (!mlCategory) return null;
  const mlLoading = mlState.id !== listing.id;
  const mlPrediction = mlState.id === listing.id ? mlState.data : null;
  return (
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
  );
}

// Slot bannere detaliu on-demand Vinted/Facebook — mutat 1:1 din ListingModal.
export function RadarDetailBanner({ listing, onLoadVintedDetail, onLoadFacebookDetail }) {
  // Reținem DOAR rezultatul fetch-ului (per id). Statusul "loading" e derivat cât
  // timp fetch-ul pentru id-ul curent nu a revenit, deci singurul setState e în
  // .then (asincron). "success" nu are UI (ca și null) — vezi randarea de mai jos.
  const [vintedResult, setVintedResult] = useState({ id: null, ok: null });
  const [facebookResult, setFacebookResult] = useState({ id: null, ok: null });

  const needsExtraDetail = (listing.images || []).length <= 1 || !listing.description;
  const vintedNeedsFetch = listing.platform === "vinted" && !listing.vinted_detail_fetched && needsExtraDetail;
  const facebookNeedsFetch = listing.platform === "facebook" && !listing.facebook_detail_fetched && needsExtraDetail;

  useEffect(() => {
    if (!vintedNeedsFetch) return;
    let cancelled = false;
    Promise.resolve(onLoadVintedDetail?.(listing.id)).then((ok) => {
      if (!cancelled) setVintedResult({ id: listing.id, ok: !!ok });
    });
    return () => { cancelled = true; };
  }, [listing.id, vintedNeedsFetch]);

  useEffect(() => {
    if (!facebookNeedsFetch) return;
    let cancelled = false;
    Promise.resolve(onLoadFacebookDetail?.(listing.id)).then((ok) => {
      if (!cancelled) setFacebookResult({ id: listing.id, ok: !!ok });
    });
    return () => { cancelled = true; };
  }, [listing.id, facebookNeedsFetch]);

  const vintedDetailStatus = !vintedNeedsFetch ? null
    : vintedResult.id === listing.id ? (vintedResult.ok ? "success" : "failed")
    : "loading";
  const facebookDetailStatus = !facebookNeedsFetch ? null
    : facebookResult.id === listing.id ? (facebookResult.ok ? "success" : "failed")
    : "loading";

  return (
    <>
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
    </>
  );
}


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
                    onClick={() => onSave(l.id)}
                    title="Salvează"
                    style={smallActionBtn("#4ade80", l.status === "saved" ? "rgba(22,163,74,0.3)" : "rgba(22,163,74,0.15)", "rgba(22,163,74,0.3)")}
                  >
                    {l.status === "saved"
                      ? <><Check style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem", verticalAlign: "middle" }} />Salvat</>
                      : <Bookmark style={{ width: "12px", height: "12px", display: "inline", verticalAlign: "middle" }} />}
                  </button>
                  <button
                    onClick={() => onIgnore(l.id)}
                    title="Ignoră"
                    style={smallActionBtn("var(--text-secondary)", l.status === "ignored" ? "rgba(100,116,139,0.3)" : "var(--bg-card)", "var(--border-color)")}
                  >
                    {l.status === "ignored"
                      ? <><Check style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem", verticalAlign: "middle" }} />Ignorat</>
                      : <EyeOff style={{ width: "12px", height: "12px", display: "inline", verticalAlign: "middle" }} />}
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

