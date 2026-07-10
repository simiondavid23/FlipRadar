"use client";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { autoListingsAPI, autoAPI, mlAPI, radarAPI } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Car, RefreshCw, Loader2, AlertTriangle, Info, FileSpreadsheet, X, ImageOff, Check, Bookmark, EyeOff } from "lucide-react";
import { GRADE_COLORS, selectStyle, tabPillStyle, inputStyle, labelStyle } from "@/lib/uiStyles";
import StatCardsRow from "@/components/shared/StatCardsRow";
import ScanNowButton from "@/components/shared/ScanNowButton";
import SelectFiniteControl from "@/components/shared/SelectFiniteControl";
import SearchResultCard from "@/components/AutoListingCard";
import AutoAiModal from "@/components/AutoAiModal";
import ListingFeedCard from "@/components/shared/ListingFeedCard";
import ListingDetailModal from "@/components/shared/ListingDetailModal";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import ActionBanner from "@/components/shared/ActionBanner";

const PLATFORM_LABELS = {
  autovit: "Autovit", olx_auto: "OLX Auto", mobile_de: "Mobile.de",
  autoscout24: "AutoScout24", facebook_auto: "Facebook Auto", kleinanzeigen_auto: "Kleinanzeigen",
};
const IMPORT_PLATFORMS = ["mobile_de", "autoscout24", "kleinanzeigen_auto"];

function gradeCfg(g) { return GRADE_COLORS[g] || GRADE_COLORS.C; }
function eurRonOf(listing) {
  return listing.import_score_json?.pe_roti?.eur_ron_rate
    || listing.import_score_json?.pe_platforma?.eur_ron_rate || 5.0;
}
// Doar URL-uri http reale sunt imagini valide; placeholderele (relative/"no_thumbnail" OLX)
// sau valorile goale -> null, ca sa se afiseze fallback-ul ImageOff. Garda generica (toate platformele).
const validImg = (u) => (typeof u === "string" && u.startsWith("http")) ? u : null;
// Explicatie grad — adaptat din Radar (D nu mai zice "AI"; Auto foloseste pragul de marja setat).
const SCORE_EXPLANATIONS = {
  A: "Marjă excelentă — deal prioritar",
  B: "Marjă bună — merită urmărit",
  C: "Marjă acceptabilă — analizează cu atenție",
  D: "Marjă slabă — sub pragul tău minim",
};

export default function AutoFeedPage() {
  const { user } = useAuth();
  const reviewEnabled = user?.ai_features_config?.ai_radar_review !== false;
  const [listings, setListings] = useState([]);
  const [feedTotal, setFeedTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [keywords, setKeywords] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: "", grade: "", status: "active", keyword_id: "" });
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState("auto");
  const [selectedBulk, setSelectedBulk] = useState(new Set());
  const toggleBulk = (id) => setSelectedBulk((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const reqIdRef = useRef(0);
  const [feedError, setFeedError] = useState(null);
  const [sortBy, setSortBy] = useState("");  // "" = ordinea serverului (found_at desc)
  // Compară (max 3, obiecte întregi) — mirror pe radar/page.js::selectedForComparison/toggleCompare.
  const [selectedForComparison, setSelectedForComparison] = useState([]);
  const [showCompare, setShowCompare] = useState(false);
  const toggleCompare = (listing) => {
    setSelectedForComparison((prev) => {
      const exists = prev.find((l) => l.id === listing.id);
      if (exists) return prev.filter((l) => l.id !== listing.id);
      if (prev.length >= 3) return prev;  // plafon 3 — la depășire nu adaugă (fără toast: nu există infra aici)
      return [...prev, listing];
    });
  };

  const _feedParams = useCallback((offset) => {
    const params = { status: filters.status, limit: 100, offset };
    if (filters.platform) params.platform = filters.platform;
    if (filters.grade) params.grade = filters.grade;
    if (filters.keyword_id) params.keyword_id = filters.keyword_id;
    return params;
  }, [filters]);

  const loadFeed = useCallback(async () => {
    const rid = ++reqIdRef.current;
    setLoading(true);
    setFeedError(null);
    try {
      const r = await autoListingsAPI.getFeed(_feedParams(0));
      if (rid !== reqIdRef.current) return;
      setListings(r.data?.items || []);
      setFeedTotal(r.data?.total || 0);
    } catch (e) {
      console.error("[AutoFeed]", e);
      if (rid === reqIdRef.current) setFeedError("Nu am putut încărca feed-ul. Reîncearcă.");
    } finally {
      setLoading(false);
    }
  }, [_feedParams]);

  const loadMoreListings = useCallback(async () => {
    const rid = ++reqIdRef.current;
    setLoadingMore(true);
    try {
      const r = await autoListingsAPI.getFeed(_feedParams(listings.length));
      if (rid !== reqIdRef.current) return;
      setListings((prev) => [...prev, ...(r.data?.items || [])]);
      setFeedTotal(r.data?.total || 0);
    } catch (e) {
      console.error("[AutoFeed] loadMore", e);
    } finally {
      setLoadingMore(false);
    }
  }, [_feedParams, listings.length]);

  const loadStats = useCallback(async () => {
    try { const r = await autoListingsAPI.getStats(); setStats(r.data || {}); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    autoListingsAPI.getKeywords().then((r) => setKeywords(r.data || [])).catch(() => {});
    radarAPI.getTemplates().then((r) => setTemplates(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { loadFeed(); loadStats(); }, [loadFeed, loadStats]);

  const setStatus = async (id, status) => {
    try { await autoListingsAPI.updateStatus(id, status); setSelected(null); await loadFeed(); await loadStats(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const remove = async (id) => {
    if (!confirm("Ștergi acest anunț?")) return;
    try { await autoListingsAPI.deleteListing(id); setSelected(null); await loadFeed(); await loadStats(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  // Actiuni in masa pe selectie (saved/ignored/active/deleted) — mirror pe Radar::applyBulkAction.
  // Fara toast (nu exista infra aici); reincarcarea feed-ului e feedback-ul de succes.
  const applyBulkAction = async (action) => {
    if (selectedBulk.size === 0) return;
    try {
      await autoListingsAPI.bulkAction(Array.from(selectedBulk), action);
      setSelectedBulk(new Set());
      await loadFeed();
      await loadStats();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la acțiune în masă.");
    }
  };
  const downloadExcel = async () => {
    try {
      const params = {};
      if (filters.platform) params.platform = filters.platform;
      if (filters.grade) params.grade = filters.grade;
      if (filters.status) params.status = filters.status;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      const r = await autoListingsAPI.exportListings(params);
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `auto_anunturi_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la export Excel.");
    }
  };

  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState(null);

  const handleScanNow = async () => {
    setScanning(true);
    setScanMsg(null);
    try {
      await autoListingsAPI.scanNow();
      setScanMsg("Scanare pornită — rezultatele apar în câteva momente.");
      // Auto-refresh feed dupa 15s ca sa prinda anunturile noi.
      setTimeout(() => { loadFeed(); setScanMsg(null); }, 15000);
    } catch {
      setScanMsg("Eroare la pornirea scanării.");
    } finally {
      setScanning(false);
    }
  };

  // Sortare client-side pe lista deja încărcată (nu mută elemente între pagini, nu resetează
  // selecțiile) — mirror pe radar/page.js::displayedListings. Preț normalizat în RON (eurRonOf),
  // null la coadă indiferent de direcție.
  const sortedListings = useMemo(() => {
    if (!sortBy) return listings;
    const priceRon = (l) => (l.price == null ? null : l.price * (l.currency === "EUR" ? eurRonOf(l) : 1));
    const nullsLast = (av, bv, cmp) => {
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return cmp(av, bv);
    };
    return [...listings].sort((a, b) => {
      if (sortBy === "price_asc")  return nullsLast(priceRon(a), priceRon(b), (x, y) => x - y);
      if (sortBy === "price_desc") return nullsLast(priceRon(a), priceRon(b), (x, y) => y - x);
      if (sortBy === "year_desc")  return nullsLast(a.year, b.year, (x, y) => y - x);
      if (sortBy === "km_asc")     return nullsLast(a.km, b.km, (x, y) => x - y);
      return 0;
    });
  }, [listings, sortBy]);

  const byGrade = stats.by_grade || {};
  const statCards = [
    { label: "Anunțuri găsite", value: stats.total_listings ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Grade A", value: byGrade.A || 0, color: "#4ade80" },
  ];

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      {/* Header — structură identică cu Radar (iconiță simplă în h1, fără badge colorat) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Car style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Feed Anunțuri Auto
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>Anunțuri monitorizate, scorate și cu calcul de import</p>
        </div>
      </div>

      {/* Tab-uri Feed Automat / Căutare Manuală (stil identic cu Radar) */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button onClick={() => setActiveTab("auto")} style={tabPillStyle(activeTab === "auto")}>Feed Automat</button>
        <button onClick={() => setActiveTab("manual")} style={tabPillStyle(activeTab === "manual")}>Căutare Manuală</button>
      </div>

      {activeTab === "manual" && <ManualSearchTab />}

      {activeTab === "auto" && (
      <>
      {/* Scanare manuală — rând dedicat aliniat dreapta (ca la Radar) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <ScanNowButton onScan={handleScanNow} scanning={scanning} />
      </div>

      {/* Facebook session expired banner */}
      {stats.has_facebook_keywords && stats.facebook_session_valid === false && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.75rem 1rem", marginBottom: "1.25rem", backgroundColor: "rgba(245,158,11,0.08)", border: "0.5px solid rgba(245,158,11,0.3)", borderRadius: "0.625rem" }}>
          <AlertTriangle style={{ width: "18px", height: "18px", color: "#fbbf24", flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "#fbbf24", margin: 0 }}>Sesiunea Facebook a expirat</p>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.125rem 0 0" }}>
              Keyword-urile de tip Facebook Auto nu vor returna rezultate. Reautentifică-te din{" "}
              <a href="/dashboard/settings" style={{ color: "#fbbf24", fontWeight: 500 }}>Setări → Facebook</a>
              {" "}pentru a reactiva scanarea.
            </p>
          </div>
        </div>
      )}

      {scanMsg && (
        <p style={{ fontSize: "0.8125rem", color: "#60a5fa", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
          <Info style={{ width: "15px", height: "15px", flexShrink: 0 }} /> {scanMsg}
        </p>
      )}

      {/* Stats */}
      <StatCardsRow cards={statCards} />

      {/* Filter bar */}
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
        <select value={filters.platform} onChange={(e) => setFilters((f) => ({ ...f, platform: e.target.value }))} style={selectStyle}>
          <option value="">Toate platformele</option>
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={filters.grade} onChange={(e) => setFilters((f) => ({ ...f, grade: e.target.value }))} style={selectStyle}>
          <option value="">Toate gradele</option>
          {["A", "B", "C", "D"].map((g) => <option key={g} value={g}>Grad {g}</option>)}
        </select>
        <select value={filters.keyword_id} onChange={(e) => setFilters((f) => ({ ...f, keyword_id: e.target.value }))} style={selectStyle}>
          <option value="">Toate keyword-urile</option>
          {keywords.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}{k.platform ? ` (${PLATFORM_LABELS[k.platform] || k.platform})` : ""}
            </option>
          ))}
        </select>

        {/* AA-3 — sortare client-side pe lista deja încărcată */}
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={selectStyle}>
          <option value="">Sortare: implicită</option>
          <option value="price_asc">Preț crescător</option>
          <option value="price_desc">Preț descrescător</option>
          <option value="year_desc">An: noile întâi</option>
          <option value="km_asc">Km: puținii întâi</option>
        </select>

        <SelectFiniteControl
          totalVisible={listings.length}
          selectedCount={selectedBulk.size}
          onSelect={(count) => {
            if (count === 0) { setSelectedBulk(new Set()); return; }
            setSelectedBulk(new Set(listings.slice(0, count).map((l) => l.id)));
          }}
        />

        <button
          onClick={() => { loadFeed(); loadStats(); }}
          disabled={loading}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: loading ? "wait" : "pointer", opacity: loading ? 0.7 : 1 }}
        >
          <RefreshCw style={{ width: "14px", height: "14px", animation: loading ? "spin 1s linear infinite" : undefined }} />
          Actualizează
        </button>

        <button
          onClick={downloadExcel}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem", backgroundColor: "rgba(22,163,74,0.15)", color: "#4ade80", border: "1px solid rgba(22,163,74,0.3)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer" }}
        >
          <FileSpreadsheet style={{ width: "14px", height: "14px" }} />
          Export Excel
        </button>
      </div>

      {/* Bara de acțiuni sticky (sub controale, deasupra grilei) — mirror pe Radar.
          Vizibilă când există selecție bulk SAU selecție de comparare (AA-3). */}
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
              // Mirror pe radar/page.js (~631): export .xlsx doar pe selectie (param ids).
              try {
                const r = await autoListingsAPI.exportListings({ ids: Array.from(selectedBulk).join(",") });
                const url = URL.createObjectURL(new Blob([r.data]));
                const a = document.createElement("a");
                a.href = url;
                a.download = `auto_selectie_${new Date().toISOString().slice(0, 10)}.xlsx`;
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

      <FeedErrorBanner message={feedError} onRetry={loadFeed} />

      {/* Grid */}
      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : listings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          Niciun anunț în această categorie. Adaugă keyword-uri și așteaptă scanarea automată (la 10 min).
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
          {sortedListings.map((l) => (
            <AutoListingCard
              key={l.id}
              listing={l}
              onOpen={() => setSelected(l)}
              onSave={() => setStatus(l.id, l.status === "saved" ? "active" : "saved")}
              onIgnore={() => setStatus(l.id, l.status === "ignored" ? "active" : "ignored")}
              onDelete={() => remove(l.id)}
              isSelected={selectedBulk.has(l.id)}
              onToggleSelect={() => toggleBulk(l.id)}
              compareSelected={!!selectedForComparison.find((x) => x.id === l.id)}
              onToggleCompare={() => toggleCompare(l)}
            />
          ))}
        </div>
      )}

      {!loading && listings.length > 0 && listings.length < feedTotal && (
        <div style={{ textAlign: "center", marginTop: "1.25rem" }}>
          <button
            onClick={loadMoreListings}
            disabled={loadingMore}
            style={{ padding: "0.6rem 1.5rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", color: "var(--text-primary)", cursor: loadingMore ? "default" : "pointer", opacity: loadingMore ? 0.6 : 1, fontSize: "0.875rem" }}
          >
            {loadingMore ? "Se încarcă…" : `Încarcă mai multe (${feedTotal - listings.length} rămase)`}
          </button>
        </div>
      )}

      {selected && (
        <AutoListingModal
          listing={selected}
          onClose={() => setSelected(null)}
          onSave={() => setStatus(selected.id, selected.status === "saved" ? "active" : "saved")}
          onIgnore={() => setStatus(selected.id, selected.status === "ignored" ? "active" : "ignored")}
          templates={templates}
          reviewEnabled={reviewEnabled}
        />
      )}

      {/* Compară (max 3) — mirror pe radar/page.js: se deschide doar la ≥2 selectate. */}
      {showCompare && selectedForComparison.length >= 2 && (
        <AutoCompareModal
          listings={selectedForComparison}
          onClose={() => setShowCompare(false)}
          onSave={async (id) => { const cur = selectedForComparison.find((l) => l.id === id); const ns = cur?.status === "saved" ? "active" : "saved"; await setStatus(id, ns); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: ns } : l)); }}
          onIgnore={async (id) => { const cur = selectedForComparison.find((l) => l.id === id); const ns = cur?.status === "ignored" ? "active" : "ignored"; await setStatus(id, ns); setSelectedForComparison((prev) => prev.map((l) => l.id === id ? { ...l, status: ns } : l)); }}
        />
      )}
      </>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function priceLine(listing, big = false) {
  const price = listing.price;
  if (!price) return "Preț la cerere";
  const cur = listing.currency || "RON";
  const main = `${Math.round(price).toLocaleString("ro-RO")} ${cur}`;
  if (cur === "EUR") {
    const ron = Math.round(price * eurRonOf(listing)).toLocaleString("ro-RO");
    return (
      <>
        {main}
        <span style={{ fontSize: big ? "0.8rem" : "0.7rem", color: "var(--text-secondary)", fontWeight: 400, marginLeft: "0.375rem" }}>(≈ {ron} RON)</span>
      </>
    );
  }
  return main;
}

const AUTO_PLATFORM_CFG = { bg: "var(--bg-dark)", border: "var(--border-color)", text: "var(--text-secondary)" };

// Overlay peste imaginea cardului: badge Import (mutat 1:1 din vechiul card).
function AutoCardOverlay({ listing }) {
  const isImport = IMPORT_PLATFORMS.includes(listing.platform);
  return (
    <>
      {isImport && (
        <span style={{ position: "absolute", bottom: "0.5rem", left: "0.5rem", fontSize: "0.625rem", fontWeight: 600, color: "#a78bfa", backgroundColor: "rgba(124,58,237,0.2)", padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>
          Import
        </span>
      )}
    </>
  );
}

// Specificatii auto (an/km/combustibil/cutie) — pentru card si modal.
function AutoSpecs({ listing, size = "0.7rem", mt }) {
  const parts = [listing.year && `${listing.year}`, listing.km != null && `${listing.km.toLocaleString("ro-RO")} km`,
    listing.fuel_type && `${listing.fuel_type}`, listing.transmission && `${listing.transmission}`].filter(Boolean);
  if (!parts.length) return null;
  return <div style={{ fontSize: size, color: "var(--text-secondary)", marginTop: mt }}>{parts.join(" · ")}</div>;
}

export function AutoListingCard({ listing, onOpen, onSave, onIgnore, onDelete, isSelected, onToggleSelect, compareSelected, onToggleCompare }) {
  const img = validImg(listing.image_url) || validImg(Array.isArray(listing.images_json) ? listing.images_json[0] : null);
  const label = PLATFORM_LABELS[listing.platform] || listing.platform;
  return (
    <ListingFeedCard
      listing={listing}
      scoreCfg={gradeCfg(listing.grade)}
      scoreBadge={listing.grade}
      platformCfg={AUTO_PLATFORM_CFG}
      platformBadge={label}
      image={img}
      openLabel={`Deschide pe ${label}`}
      showMarginLine={listing.margin_value !== null && listing.margin_value !== undefined}
      priceNode={priceLine(listing)}
      specsNode={<AutoSpecs listing={listing} />}
      imageOverlaySlot={<AutoCardOverlay listing={listing} />}
      isSelected={isSelected}
      onToggleSelect={onToggleSelect}
      compareSelected={compareSelected}
      onToggleCompare={onToggleCompare}
      onOpen={onOpen}
      onSave={onSave}
      onIgnore={onIgnore}
      onDelete={onDelete}
    />
  );
}

// Slot ML BMW (mutat 1:1 din vechiul modal Auto).
function AutoMLSection({ listing }) {
  // mlState reține DOAR rezultatul fetch-ului, etichetat cu id-ul listing-ului pentru
  // care a fost calculat. loading/prediction se derivă în render (fără setState sincron
  // în efect); rezultatul vechi cade automat când se schimbă listing-ul.
  const [mlState, setMlState] = useState({ id: null, data: null });
  const isBmw = /\bbmw\b/i.test(listing.title || "");
  useEffect(() => {
    if (!isBmw) return;
    let cancelled = false;
    mlAPI.predict({
      category: "auto_bmw",
      features: { make: "BMW", price: listing.price, year: listing.year, km: listing.km, platform: listing.platform },
    })
      .then((r) => { if (!cancelled) setMlState({ id: listing.id, data: r.data }); })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail;
        setMlState({ id: listing.id, data: msg === "model_not_trained" ? { error: "model_not_trained" }
          : msg === "features_incomplete" ? { error: "features_incomplete" } : { error: "unavailable" } });
      });
    return () => { cancelled = true; };
  }, [listing.id, isBmw, listing.price, listing.year, listing.km, listing.platform]);
  if (!isBmw) return null;
  const mlLoading = mlState.id !== listing.id;
  const mlPrediction = mlState.id === listing.id ? mlState.data : null;
  return (
    <div style={{ backgroundColor: "rgba(124,58,237,0.07)", border: "0.5px solid rgba(124,58,237,0.25)", borderRadius: "0.625rem", padding: "0.875rem 1rem", margin: "0 1.25rem 1rem" }}>
      <div style={{ fontSize: "0.75rem", color: "#a78bfa", fontWeight: 600, marginBottom: "0.5rem" }}>PREDICȚIE ML</div>
      {mlLoading && <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>Se calculează...</p>}
      {!mlLoading && mlPrediction && !mlPrediction.error && (
        <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
          Estimat ML: {mlPrediction.price?.toLocaleString("ro-RO")} RON
          {mlPrediction.days && <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 400, marginLeft: "0.5rem" }}>· ~{mlPrediction.days} zile</span>}
        </p>
      )}
      {!mlLoading && mlPrediction?.error === "model_not_trained" && (
        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
          Date insuficiente.{" "}<a href="/dashboard/ml-predictor" style={{ color: "#a78bfa" }}>Vezi progresul →</a>
        </p>
      )}
      {!mlLoading && (mlPrediction?.error === "features_incomplete" || mlPrediction?.error === "unavailable") && (
        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>Date insuficiente pentru predicție.</p>
      )}
    </div>
  );
}

// Import Score (breakdown RAR/ITP/transport) — mutat 1:1 din vechiul modal Auto. La FINAL (children).
function AutoImportScore({ listing }) {
  const [importMode, setImportMode] = useState("pe_platforma");
  const importData = listing.import_score_json;
  if (!IMPORT_PLATFORMS.includes(listing.platform) || !importData) return null;
  return (
    <div style={{ backgroundColor: "rgba(124,58,237,0.07)", border: "0.5px solid rgba(124,58,237,0.25)", borderRadius: "0.625rem", padding: "0.875rem 1rem", margin: "0 1.25rem 1.25rem" }}>
      <div style={{ fontSize: "0.75rem", color: "#a78bfa", fontWeight: 600, marginBottom: "0.625rem" }}>IMPORT SCORE</div>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
        {["pe_platforma", "pe_roti"].map((mode) => (
          <button key={mode} onClick={() => setImportMode(mode)} style={{
            padding: "0.25rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 500, cursor: "pointer",
            backgroundColor: importMode === mode ? "rgba(124,58,237,0.2)" : "var(--bg-dark)",
            color: importMode === mode ? "#a78bfa" : "var(--text-secondary)",
            border: importMode === mode ? "1px solid rgba(124,58,237,0.4)" : "1px solid var(--border-color)",
          }}>
            {mode === "pe_platforma" ? "Pe platformă" : "Pe roți"}
          </button>
        ))}
      </div>
      {(() => {
        const d = importData[importMode];
        if (!d) return null;
        const rows = importMode === "pe_roti" ? [
          ["Preț mașină", d.price_ron, "RON"],
          ["Numere Zoll + asig.", d.breakdown_ron.zoll_eur, "RON", "~est."],
          ["Combustibil + viniete", d.breakdown_ron.combustibil_eur, "RON", "~est."],
          ["RAR", d.breakdown_ron.rar_ron, "RON"],
          ["ITP", d.breakdown_ron.itp_ron, "RON"],
          ["Înmatriculare", d.breakdown_ron.inmatriculare_ron, "RON"],
        ] : [
          ["Preț mașină", d.price_ron, "RON"],
          ["Transport platformă", d.breakdown_ron.transport_eur, "RON", "~est."],
          ["RAR", d.breakdown_ron.rar_ron, "RON"],
          ["ITP", d.breakdown_ron.itp_ron, "RON"],
          ["Înmatriculare", d.breakdown_ron.inmatriculare_ron, "RON"],
        ];
        return (
          <div>
            {rows.map(([label, val, unit, note]) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8125rem", marginBottom: "0.25rem" }}>
                <span style={{ color: "var(--text-secondary)" }}>
                  {label} {note && <span style={{ fontSize: "0.7rem", color: "#a78bfa" }}>{note}</span>}
                </span>
                <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{Math.round(val).toLocaleString("ro-RO")} {unit}</span>
              </div>
            ))}
            <div style={{ borderTop: "0.5px solid rgba(124,58,237,0.2)", marginTop: "0.5rem", paddingTop: "0.5rem", display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Total România</span>
              <span style={{ fontWeight: 700, color: "#a78bfa" }}>{Math.round(d.total_ron).toLocaleString("ro-RO")} RON</span>
            </div>
            {d.saving_ron !== null && d.saving_ron !== undefined && (
              <div style={{ marginTop: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, color: d.is_profitable ? "#4ade80" : "#f87171" }}>
                {d.is_profitable
                  ? `Import rentabil — economie estimată ${Math.round(d.saving_ron).toLocaleString("ro-RO")} RON față de Autovit`
                  : `Import mai scump față de piața locală cu ${Math.abs(Math.round(d.saving_ron)).toLocaleString("ro-RO")} RON`}
              </div>
            )}
            <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)", marginTop: "0.375rem" }}>
              Curs BNR: 1 EUR = {d.eur_ron_rate} RON · Estimări marcate cu ~ pot varia
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export function AutoListingModal({ listing, onClose, onSave, onIgnore, templates, reviewEnabled }) {
  const [detail, setDetail] = useState(null);
  const [generatingAI, setGeneratingAI] = useState(false);
  // Imbogatire on-demand (poze/descriere/vanzator/data). Merge cu base ca sa pastram campurile
  // derivate din feed (_d): resale_price/margin_pct — pe care detail-ul (dump de coloane) NU le are.
  useEffect(() => {
    setDetail(null);
    autoListingsAPI.getListingDetail(listing.id).then((r) => setDetail(r.data)).catch(() => {});
  }, [listing.id]);
  const enriched = detail ? { ...listing, ...detail } : listing;
  const gallery = ((Array.isArray(enriched.images_json) && enriched.images_json.length)
    ? enriched.images_json
    : (enriched.image_url ? [enriched.image_url] : [])).filter(validImg);
  const label = PLATFORM_LABELS[enriched.platform] || enriched.platform;

  const generateAI = async () => {
    setGeneratingAI(true);
    try {
      const r = await autoListingsAPI.generateReview(listing.id);
      setDetail((d) => ({ ...(d || listing), ai_review: r.data.ai_review }));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la generarea review-ului.");
    } finally {
      setGeneratingAI(false);
    }
  };

  return (
    <ListingDetailModal
      listing={enriched}
      images={gallery}
      scoreCfg={gradeCfg(enriched.grade)}
      scoreBadge={enriched.grade}
      scoreExplanation={SCORE_EXPLANATIONS[enriched.grade]}
      platformCfg={AUTO_PLATFORM_CFG}
      platformBadge={label}
      platformUpper={label}
      openLabel={`Deschide pe ${label}`}
      priceNode={priceLine(enriched, true)}
      specsNode={<AutoSpecs listing={enriched} size="0.8125rem" mt="0.375rem" />}
      onClose={onClose}
      onSave={onSave}
      onIgnore={onIgnore}
      showReview
      reviewEnabled={reviewEnabled}
      onGenerateAI={generateAI}
      generatingAI={generatingAI}
      reviewSettingsHref="/dashboard/settings"
      showTemplates
      templates={templates}
      onRenderTemplate={(tid, body) => autoListingsAPI.renderTemplate(body.listing_id, { template_id: tid, pret_oferit: body.pret_oferit })}
      templatesHref="/dashboard/settings"
      detailBannerSlot={!enriched.detail_fetched ? (
        <div style={{ padding: "0 1.25rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
          <Info style={{ width: "12px", height: "12px", flexShrink: 0 }} />
          Unele detalii (poze, descriere, vânzător) se pot completa la prima deschidere.
        </div>
      ) : null}
      mlSlot={<AutoMLSection listing={enriched} />}
    >
      <AutoImportScore listing={listing} />
    </ListingDetailModal>
  );
}

// AutoCompareModal — mirror VIZUAL pe CompareModal din radar/page.js (~1243), adaptat la
// câmpurile auto din serializarea feed-ului (_d = dump la toate coloanele). Nu extragem
// componentă partajată acum: coloanele sunt specifice domeniului (an/km/combustibil/cutie/caroserie).
function AutoCompareModal({ listings, onClose, onSave, onIgnore }) {
  // Evidențieri verzi (ca la Radar): cel mai mic preț RON-normalizat + cea mai mare marjă.
  const pricesRon = listings.map((l) => (l.price == null ? Infinity : l.price * (l.currency === "EUR" ? eurRonOf(l) : 1)));
  const margins = listings.map((l) => (l.margin_pct == null ? -Infinity : Number(l.margin_pct)));
  const lowestPriceIdx = pricesRon.indexOf(Math.min(...pricesRon));
  const highestMarginIdx = margins.indexOf(Math.max(...margins));
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
            Comparare anunțuri
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${listings.length}, 1fr)`, gap: "0.875rem" }}>
          {listings.map((l, idx) => {
            const sc = gradeCfg(l.grade);
            const label = PLATFORM_LABELS[l.platform] || l.platform;
            const img = validImg(l.image_url) || validImg(Array.isArray(l.images_json) ? l.images_json[0] : null);
            return (
              <div key={l.id} style={{
                backgroundColor: "var(--bg-dark)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.625rem", padding: "0.75rem",
                display: "flex", flexDirection: "column", gap: "0.5rem",
              }}>
                <div style={{ display: "flex", gap: "0.375rem" }}>
                  {l.grade && (
                    <span style={{ padding: "0.125rem 0.5rem", backgroundColor: sc.bg, border: `1px solid ${sc.border}`, borderRadius: "0.375rem", color: sc.text, fontSize: "0.7rem", fontWeight: 700 }}>{l.grade}</span>
                  )}
                </div>
                <div style={{ width: "100%", height: "160px", overflow: "hidden", backgroundColor: "var(--bg-card)", borderRadius: "0.375rem", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {img ? (
                    <img src={img} alt={l.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    <ImageOff style={{ width: "32px", height: "32px", color: "var(--text-muted)" }} />
                  )}
                </div>
                <CompareRow label="Titlu" value={l.title || "—"} />
                <CompareRow label="Preț" value={priceLine(l)} highlight={idx === lowestPriceIdx} good />
                <CompareRow label="An" value={l.year != null ? `${l.year}` : "—"} />
                <CompareRow label="Km" value={l.km != null ? `${l.km.toLocaleString("ro-RO")} km` : "—"} />
                <CompareRow label="Combustibil" value={l.fuel_type || "—"} />
                <CompareRow label="Cutie" value={l.transmission || "—"} />
                <CompareRow label="Caroserie" value={l.body_type || "—"} />
                <CompareRow label="Locație" value={l.location || "—"} />
                <CompareRow label="Platformă" value={label} />
                <CompareRow label="Găsit la" value={l.found_at ? (formatListedDate(l.found_at) || "—") : "—"} />
                {l.margin_pct != null && l.resale_price != null && (
                  <CompareRow label="Marjă estimată"
                    value={`${l.margin_pct}% · revânzare ${Math.round(l.resale_price).toLocaleString("ro-RO")} RON`}
                    highlight={idx === highestMarginIdx} good />
                )}
                <div style={{ display: "flex", gap: "0.25rem", marginTop: "auto" }}>
                  <button onClick={() => onSave(l.id)} title="Salvează"
                    style={smallActionBtn("#4ade80", l.status === "saved" ? "rgba(22,163,74,0.3)" : "rgba(22,163,74,0.15)", "rgba(22,163,74,0.3)")}>
                    {l.status === "saved"
                      ? <><Check style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem", verticalAlign: "middle" }} />Salvat</>
                      : <Bookmark style={{ width: "12px", height: "12px", display: "inline", verticalAlign: "middle" }} />}
                  </button>
                  <button onClick={() => onIgnore(l.id)} title="Ignoră"
                    style={smallActionBtn("var(--text-secondary)", l.status === "ignored" ? "rgba(100,116,139,0.3)" : "var(--bg-card)", "var(--border-color)")}>
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

// CompareRow / smallActionBtn — reproduse local din radar/page.js (~1347/1357), folosite doar
// de AutoCompareModal (nicăieri altundeva în pagină).
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

function actBtn(color) {
  return {
    display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
    backgroundColor: "var(--bg-dark)", color, border: `1px solid ${color === "var(--text-secondary)" ? "var(--border-color)" : color + "55"}`,
    borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
  };
}

// Formatare data postarii — aceeasi logica ca formatListedDate din radar/page.js (reuse).
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

// ── Tab "Căutare Manuală" (înlocuiește pagina separată "Piața Auto") ─────────────
const MANUAL_PLATFORMS = [
  { value: "olx_auto", label: "OLX Auto" }, { value: "autovit", label: "AutoVit" },
  { value: "mobile_de", label: "Mobile.de" }, { value: "autoscout24", label: "AutoScout24" },
  { value: "facebook_auto", label: "FB Marketplace" }, { value: "kleinanzeigen_auto", label: "eBay KA" },
];
const MANUAL_FIELD_LABELS = {
  fuel_type: "Combustibil", gearbox: "Cutie", body_type: "Caroserie", condition: "Stare",
  seller_type: "Vânzător", drivetrain: "Tracțiune", engine_capacity_min: "Capacitate min (cmc)",
  engine_capacity_max: "Capacitate max (cmc)", engine_power_min: "Putere min", power_unit: "Unitate putere",
  mileage_max: "Km max", make: "Marcă", year: "An",
};
const mcap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function ManualSearchTab() {
  const [catData, setCatData] = useState({ categories: {}, technical_fields: {} });
  const [platform, setPlatform] = useState("olx_auto");
  const [category, setCategory] = useState("");
  const [tech, setTech] = useState({});
  const [f, setF] = useState({ make: "", model: "", year_min: "", year_max: "", km_max: "", price_min: "", price_max: "" });
  const [results, setResults] = useState(null);
  const [byPlatform, setByPlatform] = useState({});
  const [loading, setLoading] = useState(false);
  const [savedKeys, setSavedKeys] = useState(new Set());
  const [savingKey, setSavingKey] = useState(null);
  const [aiListing, setAiListing] = useState(null);

  useEffect(() => {
    autoListingsAPI.getCategories()
      .then((r) => setCatData(r.data || { categories: {}, technical_fields: {} }))
      .catch(() => {});
  }, []);

  const liKey = (l) => `${l.platform}:${l.external_id || l.source_url}`;
  const validCats = ((catData.categories || {})[platform] || []).filter((c) => c.value != null);
  const techFields = Object.entries((catData.technical_fields || {})[platform] || {})
    .filter(([, s]) => s && typeof s === "object" && s.confirmed === true);
  const setF1 = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const changePlatform = (v) => { setPlatform(v); setCategory(""); setTech({}); };

  const doSearch = async (e) => {
    e?.preventDefault();
    const q = `${f.make} ${f.model}`.trim();
    const filters = {};
    if (f.make) filters.make = f.make;
    if (f.model) filters.model = f.model;
    if (f.year_min) filters.year_min = parseInt(f.year_min);
    if (f.price_min) filters.price_min = parseFloat(f.price_min);
    if (f.price_max) filters.price_max = parseFloat(f.price_max);
    if (f.km_max) filters.km_max = parseInt(f.km_max);
    if (category) filters.category = category;
    Object.entries(tech).forEach(([k, v]) => { if (v !== "" && v != null) filters[k] = v; });
    setLoading(true); setResults(null);
    try {
      const res = await autoAPI.searchListings(q, platform, filters);
      setResults(res.data?.results || []);
      setByPlatform(res.data?.by_platform || {});
    } catch (err) { alert(err.response?.data?.detail || "Eroare la căutare."); setResults([]); }
    finally { setLoading(false); }
  };

  // Filtrare client-side suplimentara (an/km/pret nu sunt aplicate uniform de toate scraperele).
  const shown = useMemo(() => {
    if (!results) return [];
    return results.filter((l) => {
      if (f.year_min && l.year && l.year < parseInt(f.year_min)) return false;
      if (f.year_max && l.year && l.year > parseInt(f.year_max)) return false;
      if (f.km_max && l.km && l.km > parseInt(f.km_max)) return false;
      if (f.price_min && l.pret != null && l.pret < parseFloat(f.price_min)) return false;
      if (f.price_max && l.pret != null && l.pret > parseFloat(f.price_max)) return false;
      return true;
    });
  }, [results, f]);

  const handleSave = async (listing) => {
    const key = liKey(listing); setSavingKey(key);
    try { await autoAPI.saveListing(listing); setSavedKeys((prev) => new Set(prev).add(key)); }
    catch (err) { alert(err.response?.data?.detail || "Eroare la salvare."); }
    finally { setSavingKey(null); }
  };

  return (
    <div>
      <form onSubmit={doSearch} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.875rem" }}>
        {/* Platformă — o singură (pill-uri, ca la Radar) */}
        <div>
          <label style={labelStyle}>Platformă</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {MANUAL_PLATFORMS.map((p) => {
              const active = platform === p.value;
              return (
                <button key={p.value} type="button" onClick={() => changePlatform(p.value)} style={{
                  padding: "0.375rem 0.875rem", borderRadius: "0.5rem", fontSize: "0.8125rem",
                  fontWeight: active ? 600 : 400, cursor: "pointer",
                  border: active ? "2px solid #2563eb" : "1px solid var(--border-color)",
                  backgroundColor: active ? "rgba(37,99,235,0.15)" : "var(--bg-dark)",
                  color: active ? "#60a5fa" : "var(--text-secondary)",
                }}>{p.label}</button>
              );
            })}
          </div>
        </div>

        {/* Categorie dinamică (doar dacă platforma are categorii confirmate) */}
        {validCats.length > 0 && (
          <div>
            <label style={labelStyle}>Categorie</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)} style={inputStyle}>
              <option value="">Toate</option>
              {validCats.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
        )}

        {/* Câmpuri de bază */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "0.75rem" }}>
          <div><label style={labelStyle}>Marcă</label><input value={f.make} onChange={(e) => setF1("make", e.target.value)} placeholder="ex: Audi" style={inputStyle} /></div>
          <div><label style={labelStyle}>Model</label><input value={f.model} onChange={(e) => setF1("model", e.target.value)} placeholder="ex: A4" style={inputStyle} /></div>
          <div><label style={labelStyle}>An min</label><input type="number" value={f.year_min} onChange={(e) => setF1("year_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>An max</label><input type="number" value={f.year_max} onChange={(e) => setF1("year_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>Km max</label><input type="number" value={f.km_max} onChange={(e) => setF1("km_max", e.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>Preț min</label><input type="number" value={f.price_min} onChange={(e) => setF1("price_min", e.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>Preț max</label><input type="number" value={f.price_max} onChange={(e) => setF1("price_max", e.target.value)} style={inputStyle} /></div>
        </div>

        {/* Câmpuri tehnice confirmate — doar dacă platforma are (Facebook: nu apar) */}
        {techFields.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.75rem" }}>
            {techFields.map(([key, spec]) => (
              <div key={key}>
                <label style={labelStyle}>{MANUAL_FIELD_LABELS[key] || key}</label>
                {spec.values ? (
                  <select value={tech[key] || ""} onChange={(e) => setTech((p) => ({ ...p, [key]: e.target.value }))} style={inputStyle}>
                    <option value="">Toate</option>
                    {Object.keys(spec.values).map((k) => <option key={k} value={k}>{mcap(k)}</option>)}
                  </select>
                ) : (
                  <input type="number" value={tech[key] || ""} onChange={(e) => setTech((p) => ({ ...p, [key]: e.target.value }))} placeholder="—" style={inputStyle} />
                )}
              </div>
            ))}
          </div>
        )}

        <div>
          <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.875rem", fontWeight: 600, cursor: "pointer" }}>
            <Car style={{ width: "16px", height: "16px" }} /> Caută
          </button>
        </div>
      </form>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : results != null && (
        shown.length > 0 ? (
          <>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
              {shown.length} anunțuri
              {Object.keys(byPlatform).length > 0 && ` (${Object.entries(byPlatform).map(([p, n]) => `${p}: ${n}`).join(", ")})`}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
              {shown.map((l, i) => (
                <SearchResultCard key={`${liKey(l)}-${i}`} listing={l} onSave={handleSave} onAnalyze={setAiListing} isSaved={savedKeys.has(liKey(l))} busy={savingKey === liKey(l)} />
              ))}
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "2.5rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
            Niciun anunț găsit pentru filtrele selectate.
          </div>
        )
      )}

      <AutoAiModal open={!!aiListing} onClose={() => setAiListing(null)} listing={aiListing} />
    </div>
  );
}
