"use client";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { realEstateMonitorAPI } from "@/lib/api";
import { Home, AlertTriangle, RefreshCw, FileSpreadsheet } from "lucide-react";
import { GRADE_COLORS, selectStyle, tabPillStyle } from "@/lib/uiStyles";
import { eurRonOf } from "@/lib/currency";
import StatCardsRow from "@/components/shared/StatCardsRow";
import ScanNowButton from "@/components/shared/ScanNowButton";
import SelectFiniteControl from "@/components/shared/SelectFiniteControl";
import ActionBanner from "@/components/shared/ActionBanner";
import ListingFeedCard from "@/components/shared/ListingFeedCard";
import ListingDetailModal from "@/components/shared/ListingDetailModal";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import REManualSearch from "@/components/REManualSearch";

const PLATFORM_LABELS = {
  olx: "OLX", storia: "Storia", imobiliare_ro: "Imobiliare.ro",
  facebook_marketplace: "FB Marketplace", facebook_groups: "Grupuri FB",
};

const gradeCfg = (g) => GRADE_COLORS[g] || GRADE_COLORS.C;
// Culori platformă neutre (RE nu are branding per-sursă în card, ca Auto).
const RE_PLATFORM_CFG = { bg: "var(--bg-dark)", border: "var(--border-color)", text: "var(--text-secondary)" };
// eurRonOf mutat in @/lib/currency (REF-1) — sortarea pe pret normalizeaza EUR->RON cu el.

export default function REFeedPage() {
  const [listings, setListings] = useState([]);
  const [feedTotal, setFeedTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [keywords, setKeywords] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: "", grade: "", status: "active", rooms: "", zone: "", city: "", keyword_id: "" });
  const [selected, setSelected] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [tab, setTab] = useState("feed");   // "feed" | "manual" (Căutare Manuală)
  const [selectedBulk, setSelectedBulk] = useState(new Set());
  const toggleBulk = (id) => setSelectedBulk((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const reqIdRef = useRef(0);
  const [feedError, setFeedError] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);   // stergere inline din card
  const [sortBy, setSortBy] = useState("");   // "" = ordinea serverului (found_at desc)
  const [filterOptions, setFilterOptions] = useState({ zones: [], cities: [] });   // dropdown zonă/oraș
  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2500); };

  // Serverul filtrează acum tot: platform/grade/rooms/zone/oraș/keyword (IM-3 a mutat orașul
  // pe server; paginarea offset/limit rămâne corectă pentru toate filtrele).
  const _feedParams = useCallback((offset) => {
    const params = { status: filters.status, limit: 100, offset };
    if (filters.platform) params.platform = filters.platform;
    if (filters.grade) params.grade = filters.grade;
    if (filters.rooms) params.rooms = filters.rooms;
    if (filters.zone) params.zone = filters.zone;
    if (filters.city) params.city = filters.city;
    if (filters.keyword_id) params.keyword_id = filters.keyword_id;
    return params;
  }, [filters]);

  const loadFeed = useCallback(async () => {
    const rid = ++reqIdRef.current;
    setLoading(true);
    setFeedError(null);
    try {
      const r = await realEstateMonitorAPI.getFeed(_feedParams(0));
      if (rid !== reqIdRef.current) return;
      setListings(r.data?.items || []);
      setFeedTotal(r.data?.total || 0);
    } catch (e) {
      console.error("[REFeed]", e);
      if (rid === reqIdRef.current) setFeedError("Nu am putut încărca feed-ul. Reîncearcă.");
    }
    finally { setLoading(false); }
  }, [_feedParams]);

  const loadMoreListings = useCallback(async () => {
    const rid = ++reqIdRef.current;
    setLoadingMore(true);
    try {
      const r = await realEstateMonitorAPI.getFeed(_feedParams(listings.length));
      if (rid !== reqIdRef.current) return;
      setListings((prev) => [...prev, ...(r.data?.items || [])]);
      setFeedTotal(r.data?.total || 0);
    } catch (e) { console.error("[REFeed] loadMore", e); }
    finally { setLoadingMore(false); }
  }, [_feedParams, listings.length]);

  const loadStats = useCallback(async () => {
    try { const r = await realEstateMonitorAPI.getStats(); setStats(r.data || {}); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    realEstateMonitorAPI.getKeywords().then((r) => setKeywords(r.data || [])).catch(() => {});
    realEstateMonitorAPI.getFilterOptions().then((r) => setFilterOptions(r.data || { zones: [], cities: [] })).catch(() => {});
  }, []);
  useEffect(() => { loadFeed(); loadStats(); }, [loadFeed, loadStats]);

  // Sortare client-side pe lista deja încărcată (orașul e filtrat acum pe server, IM-3 — nu mai
  // există filtru client-side). Nu mută elemente între pagini — paginarea offset/limit rămâne pe
  // `listings` brute (aceeași limitare asumată ca RP-1/AA-3). Prețul se normalizează în RON
  // (eurRonOf, mirror AA-3) pentru comparație corectă EUR/RON; null ajunge mereu la coadă.
  const displayedListings = useMemo(() => {
    if (!sortBy) return listings;
    const priceRon = (l) => (l.price == null ? null : l.price * (l.currency === "EUR" ? eurRonOf(l) : 1));
    const ts = (l) => (l.listed_at ? new Date(l.listed_at).getTime() : null);
    const nullsLast = (av, bv, cmp) => {
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return cmp(av, bv);
    };
    return [...listings].sort((a, b) => {
      if (sortBy === "price_asc")   return nullsLast(priceRon(a), priceRon(b), (x, y) => x - y);
      if (sortBy === "price_desc")  return nullsLast(priceRon(a), priceRon(b), (x, y) => y - x);
      if (sortBy === "ppm_asc")     return nullsLast(a.price_per_sqm, b.price_per_sqm, (x, y) => x - y);
      if (sortBy === "score_desc")  return nullsLast(a.score, b.score, (x, y) => y - x);
      if (sortBy === "listed_desc") return nullsLast(ts(a), ts(b), (x, y) => y - x);
      return 0;
    });
  }, [listings, sortBy]);

  const setStatus = async (id, status) => {
    try { await realEstateMonitorAPI.updateStatus(id, status); setSelected(null); await loadFeed(); await loadStats(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  // Ștergere reală (după confirmarea inline din card) — fără window.confirm.
  const doDelete = async (id) => {
    try {
      await realEstateMonitorAPI.deleteListing(id);
      setConfirmDeleteId(null);
      setSelected(null);
      await loadFeed(); await loadStats();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere."); }
  };

  const applyBulkAction = async (action) => {
    if (selectedBulk.size === 0) return;
    try {
      const r = await realEstateMonitorAPI.bulkAction(Array.from(selectedBulk), action);
      showToast(r.data?.message || `${r.data?.updated || 0} listinguri actualizate.`);
      setSelectedBulk(new Set());
      await loadFeed(); await loadStats();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la acțiune în masă.");
    }
  };
  const handleScanNow = async () => {
    setScanning(true);
    try { await realEstateMonitorAPI.scanNow(); setTimeout(() => { loadFeed(); setScanning(false); }, 15000); }
    catch { setScanning(false); }
  };

  const downloadExcel = async () => {
    try {
      const params = {};
      if (filters.platform) params.platform = filters.platform;
      if (filters.grade) params.grade = filters.grade;
      if (filters.status) params.status = filters.status;
      if (filters.city) params.city = filters.city;
      if (filters.zone) params.zone = filters.zone;
      if (filters.rooms) params.rooms = filters.rooms;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      const r = await realEstateMonitorAPI.exportListings(params);
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `imobiliare_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la export Excel.");
    }
  };

  const byGrade = stats.by_grade || {};
  const statCards = [
    { label: "Total listinguri", value: stats.total_listings ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Grade A", value: byGrade.A || 0, color: "#4ade80" },
  ];

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      {/* Header — structură identică cu Radar (iconiță simplă în h1, fără badge colorat) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Home style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Feed Imobiliare
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>Chirii scorate, cu zone normalizate</p>
        </div>
      </div>

      {/* Tab-uri: Feed automat / Căutare Manuală (pill-uri, ca la Auto/Radar) */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button onClick={() => setTab("feed")} style={tabPillStyle(tab === "feed")}>Feed</button>
        <button onClick={() => setTab("manual")} style={tabPillStyle(tab === "manual")}>Căutare Manuală</button>
      </div>

      {tab === "manual" && <REManualSearch />}

      {tab === "feed" && (<>
      {/* Scanare manuală — rând dedicat aliniat dreapta (ca la Radar) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <ScanNowButton onScan={handleScanNow} scanning={scanning} />
      </div>

      {stats.has_facebook_keywords && stats.facebook_session_valid === false && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.75rem 1rem", marginBottom: "1.25rem", backgroundColor: "rgba(245,158,11,0.08)", border: "0.5px solid rgba(245,158,11,0.3)", borderRadius: "0.625rem" }}>
          <AlertTriangle style={{ width: "18px", height: "18px", color: "#fbbf24", flexShrink: 0 }} />
          <div>
            <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "#fbbf24", margin: 0 }}>Sesiunea Facebook a expirat</p>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.125rem 0 0" }}>
              Keyword-urile Facebook nu vor returna rezultate. Reautentifică-te din <a href="/dashboard/settings" style={{ color: "#fbbf24", fontWeight: 500 }}>Setări → Facebook</a>.
            </p>
          </div>
        </div>
      )}

      <StatCardsRow cards={statCards} />

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
          <option value="">Toate sursele</option>
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={filters.grade} onChange={(e) => setFilters((f) => ({ ...f, grade: e.target.value }))} style={selectStyle}>
          <option value="">Toate gradele</option>
          {["A", "B", "C", "D"].map((g) => <option key={g} value={g}>Grad {g}</option>)}
        </select>
        <select value={filters.rooms} onChange={(e) => setFilters((f) => ({ ...f, rooms: e.target.value }))} style={selectStyle}>
          <option value="">Camere</option>
          {[1, 2, 3, 4].map((r) => <option key={r} value={r}>{r}{r === 4 ? "+" : ""} cam</option>)}
        </select>
        {/* Zona: dropdown din zonele normalizate reale ale userului (egalitate exactă sigură). */}
        <select value={filters.zone} onChange={(e) => setFilters((f) => ({ ...f, zone: e.target.value }))} style={selectStyle}>
          <option value="">Toate zonele</option>
          {filterOptions.zones.map((z) => <option key={z} value={z}>{z}</option>)}
        </select>
        <select value={filters.city} onChange={(e) => setFilters((f) => ({ ...f, city: e.target.value }))} style={selectStyle}>
          <option value="">Toate orașele</option>
          {filterOptions.cities.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filters.keyword_id} onChange={(e) => setFilters((f) => ({ ...f, keyword_id: e.target.value }))} style={selectStyle}>
          <option value="">Toate keyword-urile</option>
          {keywords.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}{k.platform ? ` (${PLATFORM_LABELS[k.platform] || k.platform})` : ""}
            </option>
          ))}
        </select>

        {/* Sortare client-side pe lista deja încărcată (mirror AA-3/RP-1). */}
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={selectStyle}>
          <option value="">Sortare: implicită</option>
          <option value="price_asc">Preț crescător</option>
          <option value="price_desc">Preț descrescător</option>
          <option value="ppm_asc">Preț/mp crescător</option>
          <option value="score_desc">Scor descrescător</option>
          <option value="listed_desc">Data postării (recente)</option>
        </select>

        <SelectFiniteControl
          totalVisible={displayedListings.length}
          selectedCount={selectedBulk.size}
          onSelect={(count) => {
            if (count === 0) { setSelectedBulk(new Set()); return; }
            setSelectedBulk(new Set(displayedListings.slice(0, count).map((l) => l.id)));
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

      {/* Bară de acțiuni în masă — apare animat când există selecție (mirror radar/page.js). */}
      <div style={{ position: "sticky", top: 0, zIndex: 20, marginBottom: selectedBulk.size > 0 ? "0.75rem" : 0 }}>
        <div style={{
          maxHeight: selectedBulk.size > 0 ? "160px" : "0px",
          overflow: "hidden",
          opacity: selectedBulk.size > 0 ? 1 : 0,
          transition: "max-height 0.2s ease, opacity 0.15s ease",
        }}>
          <ActionBanner
            bulkCount={selectedBulk.size}
            totalVisible={displayedListings.length}
            onBulkSave={() => applyBulkAction("saved")}
            onBulkIgnore={() => applyBulkAction("ignored")}
            onBulkDelete={() => applyBulkAction("deleted")}
            onBulkExport={async () => {
              try {
                const r = await realEstateMonitorAPI.exportListings({ ids: Array.from(selectedBulk).join(",") });
                const url = URL.createObjectURL(new Blob([r.data]));
                const a = document.createElement("a");
                a.href = url;
                a.download = `imobiliare_selectie_${new Date().toISOString().slice(0, 10)}.xlsx`;
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

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : displayedListings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          Niciun anunț. Adaugă keyword-uri și așteaptă scanarea (la 30 min) sau apasă „Scanează acum”.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
          {displayedListings.map((l) => (
            <REListingCard
              key={l.id}
              listing={l}
              onOpen={() => setSelected(l)}
              onSave={() => setStatus(l.id, l.status === "saved" ? "active" : "saved")}
              onIgnore={() => setStatus(l.id, l.status === "ignored" ? "active" : "ignored")}
              onDelete={() => setConfirmDeleteId(l.id)}
              confirmingDelete={confirmDeleteId === l.id}
              onConfirmDelete={() => doDelete(l.id)}
              onCancelDelete={() => setConfirmDeleteId(null)}
              isSelected={selectedBulk.has(l.id)}
              onToggleSelect={() => toggleBulk(l.id)}
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
        <REListingModal
          listing={selected}
          onClose={() => setSelected(null)}
          onSave={() => setStatus(selected.id, selected.status === "saved" ? "active" : "saved")}
          onIgnore={() => setStatus(selected.id, selected.status === "ignored" ? "active" : "ignored")}
        />
      )}
      </>)}

      {/* Notificare toast (succes bulk) — mirror pe radar/page.js; erorile rămân pe alert. */}
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

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function priceLine(listing) {
  if (!listing.price) return "Preț la cerere";
  return `${Math.round(listing.price).toLocaleString("ro-RO")} ${listing.currency || "EUR"}/lună`;
}
function priceDropPct(listing) {
  const h = listing.price_history;
  if (!Array.isArray(h) || h.length === 0 || !listing.price) return null;
  const first = h[0]?.price;
  if (!first || first <= listing.price) return null;
  return Math.round((first - listing.price) / first * 100);
}

// Preț + „↓ drop%” (reutilizat în card + modal via priceNode).
function rePriceNode(listing) {
  const drop = priceDropPct(listing);
  return (
    <>
      {priceLine(listing)}
      {drop !== null && <span style={{ fontSize: "0.7rem", color: "#fb923c", marginLeft: "0.375rem" }}>↓ {drop}%</span>}
    </>
  );
}

// Specificații imobiliar (camere/mp/etaj + zonă normalizată + oraș + preț/mp) — mirror pe AutoSpecs.
function RESpecs({ listing, size = "0.7rem", mt }) {
  const rooms = [listing.rooms && `${listing.rooms} cam`, listing.area_sqm && `${listing.area_sqm} mp`, listing.floor && `Etaj ${listing.floor}`].filter(Boolean).join(" · ");
  const zoneDiffers = listing.zone_normalized && listing.zone_raw && listing.zone_raw.trim() !== listing.zone_normalized.trim();
  const locLine = [listing.zone_normalized || listing.zone_raw, listing.city].filter(Boolean).join(" · ");
  return (
    <div style={{ fontSize: size, color: "var(--text-secondary)", marginTop: mt, display: "flex", flexDirection: "column", gap: "0.2rem" }}>
      {listing.zone_normalized && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{listing.zone_normalized}</span>
          {zoneDiffers && <span style={{ color: "var(--text-muted)" }}>← {listing.zone_raw}</span>}
        </div>
      )}
      {rooms && <div>{rooms}</div>}
      {locLine && <div style={{ color: "var(--text-muted)" }}>{locLine}</div>}
      {listing.price_per_sqm && <div>{Number(listing.price_per_sqm).toFixed(1)} {listing.currency}/mp</div>}
      {listing.listed_at && <div style={{ color: "var(--text-muted)" }}>Postat: {new Date(listing.listed_at).toLocaleDateString("ro-RO")}</div>}
    </div>
  );
}

// Istoricul prețului — fără echivalent generic în modalul shared → slot `children`, la final (ca AutoImportScore).
function REPriceHistory({ listing }) {
  const history = Array.isArray(listing.price_history) ? listing.price_history : [];
  if (history.length === 0) return null;
  return (
    <div style={{ padding: "0 1.25rem 1.25rem" }}>
      <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Istoricul prețului</div>
      {history.map((h, i) => (
        <div key={i} style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
          {h.date ? new Date(h.date).toLocaleDateString("ro-RO") : "—"}: {Math.round(h.price).toLocaleString("ro-RO")} {h.currency}
        </div>
      ))}
    </div>
  );
}

// Card imobiliar peste ListingFeedCard (mirror pe AutoListingCard). Props de confirmare inline
// la ștergere sunt OPȚIONALE și se forwardează către ListingFeedCard (care le suportă deja) —
// pagina Salvate & Ignorate nu le trimite, deci acolo comportamentul rămâne neschimbat.
export function REListingCard({ listing, onOpen, onSave, onIgnore, onDelete, isSelected, onToggleSelect,
  confirmingDelete, onConfirmDelete, onCancelDelete }) {
  const label = PLATFORM_LABELS[listing.platform] || listing.platform;
  const img = listing.image_url || (Array.isArray(listing.images_json) ? listing.images_json[0] : null);
  return (
    <ListingFeedCard
      listing={listing}
      scoreCfg={gradeCfg(listing.grade)}
      scoreBadge={listing.grade}
      platformCfg={RE_PLATFORM_CFG}
      platformBadge={label}
      image={img}
      openLabel={`Deschide pe ${label}`}
      showMarginLine={false}
      priceNode={rePriceNode(listing)}
      specsNode={<RESpecs listing={listing} />}
      isSelected={isSelected}
      onToggleSelect={onToggleSelect}
      onOpen={onOpen}
      onSave={onSave}
      onIgnore={onIgnore}
      onDelete={onDelete}
      confirmingDelete={confirmingDelete}
      onConfirmDelete={onConfirmDelete}
      onCancelDelete={onCancelDelete}
    />
  );
}

// Modal imobiliar peste ListingDetailModal (mirror pe AutoListingModal). Istoricul prețului
// merge ca `children` (slot final), preț/mp + zonă rămân în specsNode, scorul /100 în scoreExplanation.
export function REListingModal({ listing, onClose, onSave, onIgnore }) {
  const label = PLATFORM_LABELS[listing.platform] || listing.platform;
  const gallery = (Array.isArray(listing.images_json) && listing.images_json.length)
    ? listing.images_json
    : (listing.image_url ? [listing.image_url] : []);
  return (
    <ListingDetailModal
      listing={listing}
      images={gallery}
      scoreCfg={gradeCfg(listing.grade)}
      scoreBadge={listing.grade}
      scoreExplanation={listing.score != null ? `Scor ${listing.score}/100` : ""}
      platformCfg={RE_PLATFORM_CFG}
      platformBadge={label}
      platformUpper={label}
      openLabel={`Deschide pe ${label}`}
      priceNode={rePriceNode(listing)}
      specsNode={<RESpecs listing={listing} size="0.8125rem" mt="0.375rem" />}
      onClose={onClose}
      onSave={onSave}
      onIgnore={onIgnore}
    >
      <REPriceHistory listing={listing} />
    </ListingDetailModal>
  );
}
