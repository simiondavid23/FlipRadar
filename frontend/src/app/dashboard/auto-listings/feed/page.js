"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { autoListingsAPI, autoAPI, mlAPI } from "@/lib/api";
import { Car, RefreshCw, ExternalLink, Bookmark, EyeOff, Trash2, X, ImageOff, Loader2, AlertTriangle, Info, FileSpreadsheet } from "lucide-react";
import { GRADE_COLORS, selectStyle, tabPillStyle, inputStyle, labelStyle } from "@/lib/uiStyles";
import StatCardsRow from "@/components/shared/StatCardsRow";
import ScanNowButton from "@/components/shared/ScanNowButton";
import SelectFiniteControl from "@/components/shared/SelectFiniteControl";
import SearchResultCard from "@/components/AutoListingCard";
import AutoAiModal from "@/components/AutoAiModal";

const PLATFORM_LABELS = {
  autovit: "Autovit", olx_auto: "OLX Auto", mobile_de: "Mobile.de",
  autoscout24: "AutoScout24", facebook_auto: "Facebook Auto", kleinanzeigen_auto: "Kleinanzeigen",
};
const IMPORT_PLATFORMS = ["mobile_de", "autoscout24", "kleinanzeigen_auto"];

// Opțiuni status pentru <select> (identic cu Radar — valorile active/saved/ignored).
const STATUS_OPTIONS = [
  { label: "Active", value: "active" },
  { label: "Salvate", value: "saved" },
  { label: "Ignorate", value: "ignored" },
];

function gradeCfg(g) { return GRADE_COLORS[g] || GRADE_COLORS.C; }
function eurRonOf(listing) {
  return listing.import_score_json?.pe_roti?.eur_ron_rate
    || listing.import_score_json?.pe_platforma?.eur_ron_rate || 5.0;
}

export default function AutoFeedPage() {
  const [listings, setListings] = useState([]);
  const [keywords, setKeywords] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: "", grade: "", status: "active", keyword_id: "" });
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState("auto");
  const [selectedBulk, setSelectedBulk] = useState(new Set());

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: filters.status, limit: 100 };
      if (filters.platform) params.platform = filters.platform;
      if (filters.grade) params.grade = filters.grade;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      const r = await autoListingsAPI.getFeed(params);
      setListings(r.data?.items || []);
    } catch (e) {
      console.error("[AutoFeed]", e);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadStats = useCallback(async () => {
    try { const r = await autoListingsAPI.getStats(); setStats(r.data || {}); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    autoListingsAPI.getKeywords().then((r) => setKeywords(r.data || [])).catch(() => {});
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

  const byGrade = stats.by_grade || {};
  const statCards = [
    { label: "Anunțuri găsite", value: stats.total_listings ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Grade A", value: byGrade.A || 0, color: "#4ade80" },
    { label: "Grade B", value: byGrade.B || 0, color: "#60a5fa" },
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
        <select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} style={selectStyle}>
          {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
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
          {keywords.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
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

      {/* Grid */}
      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : listings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          Niciun anunț în această categorie. Adaugă keyword-uri și așteaptă scanarea automată (la 10 min).
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
          {listings.map((l) => <AutoListingCard key={l.id} listing={l} onClick={() => setSelected(l)} />)}
        </div>
      )}

      {selected && (
        <AutoListingModal
          listing={selected}
          onClose={() => setSelected(null)}
          onSave={() => setStatus(selected.id, "saved")}
          onIgnore={() => setStatus(selected.id, "ignored")}
          onDelete={() => remove(selected.id)}
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

function AutoListingCard({ listing, onClick }) {
  const g = gradeCfg(listing.grade);
  const img = listing.image_url || (Array.isArray(listing.images_json) ? listing.images_json[0] : null);
  const isImport = IMPORT_PLATFORMS.includes(listing.platform);
  return (
    <div onClick={onClick} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden", cursor: "pointer", display: "flex", flexDirection: "column" }}>
      <div style={{ position: "relative", height: "160px", backgroundColor: "var(--bg-dark)" }}>
        {img ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={img} alt={listing.title || ""} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "28px", height: "28px" }} />
          </div>
        )}
        <span style={{ position: "absolute", top: "0.5rem", left: "0.5rem", fontSize: "0.6875rem", fontWeight: 700, color: g.text, backgroundColor: g.bg, padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>
          {listing.grade}
        </span>
        <span style={{ position: "absolute", top: "0.5rem", right: "0.5rem", fontSize: "0.625rem", fontWeight: 600, color: "white", backgroundColor: "rgba(0,0,0,0.6)", padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>
          {PLATFORM_LABELS[listing.platform] || listing.platform}
        </span>
        {isImport && (
          <span style={{ position: "absolute", bottom: "0.5rem", left: "0.5rem", fontSize: "0.625rem", fontWeight: 600, color: "#a78bfa", backgroundColor: "rgba(124,58,237,0.2)", padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>
            Import
          </span>
        )}
      </div>
      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.375rem", flex: 1 }}>
        <div style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-primary)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {listing.title || "—"}
        </div>
        <div style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)" }}>{priceLine(listing)}</div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>
          {[listing.year && `${listing.year}`, listing.km != null && `${listing.km.toLocaleString("ro-RO")} km`,
            listing.fuel_type && `${listing.fuel_type}`, listing.transmission && `${listing.transmission}`]
            .filter(Boolean).join(" · ")}
        </div>
        {listing.location && <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{listing.location}</div>}
      </div>
    </div>
  );
}

function AutoListingModal({ listing, onClose, onSave, onIgnore, onDelete }) {
  const [importMode, setImportMode] = useState("pe_platforma");
  const [mlPrediction, setMlPrediction] = useState(null);
  const [mlLoading, setMlLoading] = useState(false);
  // Imbogatire on-demand (poze/descriere/vanzator/data), o data per anunt (cache in DB).
  const [detail, setDetail] = useState(null);
  const [imgIndex, setImgIndex] = useState(0);
  const enriched = detail || listing;
  const g = gradeCfg(listing.grade);
  const gallery = (Array.isArray(enriched.images_json) && enriched.images_json.length)
    ? enriched.images_json
    : (listing.image_url ? [listing.image_url] : []);
  const img = gallery[Math.min(imgIndex, Math.max(gallery.length - 1, 0))] || null;
  const importData = listing.import_score_json;
  const isBmw = /\bbmw\b/i.test(listing.title || "");

  useEffect(() => {
    setDetail(null); setImgIndex(0);
    autoListingsAPI.getListingDetail(listing.id).then((r) => setDetail(r.data)).catch(() => {});
  }, [listing.id]);

  useEffect(() => {
    if (!isBmw) { setMlPrediction(null); return; }
    setMlLoading(true);
    mlAPI.predict({
      category: "auto_bmw",
      features: { make: "BMW", price: listing.price, year: listing.year, km: listing.km, platform: listing.platform },
    })
      .then((r) => setMlPrediction(r.data))
      .catch((err) => {
        const msg = err.response?.data?.detail;
        setMlPrediction(msg === "model_not_trained" ? { error: "model_not_trained" }
          : msg === "features_incomplete" ? { error: "features_incomplete" } : { error: "unavailable" });
      })
      .finally(() => setMlLoading(false));
  }, [listing.id, isBmw, listing.price, listing.year, listing.km, listing.platform]);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "560px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ position: "relative", height: "240px", backgroundColor: "var(--bg-dark)" }}>
          {img ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={img} alt={listing.title || ""} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : (
            <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}><ImageOff style={{ width: "32px", height: "32px" }} /></div>
          )}
          {gallery.length > 1 && (
            <>
              <button onClick={() => setImgIndex((i) => (i - 1 + gallery.length) % gallery.length)} style={galleryNav(true)} aria-label="Poza anterioară">‹</button>
              <button onClick={() => setImgIndex((i) => (i + 1) % gallery.length)} style={galleryNav(false)} aria-label="Poza următoare">›</button>
              <span style={{ position: "absolute", bottom: "0.5rem", right: "0.5rem", background: "rgba(0,0,0,0.6)", color: "white", fontSize: "0.6875rem", padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>{imgIndex + 1}/{gallery.length}</span>
            </>
          )}
          <button onClick={onClose} style={{ position: "absolute", top: "0.625rem", right: "0.625rem", background: "rgba(0,0,0,0.6)", border: "none", borderRadius: "0.375rem", padding: "0.25rem", cursor: "pointer", color: "white", display: "flex" }}><X style={{ width: "18px", height: "18px" }} /></button>
          <span style={{ position: "absolute", top: "0.625rem", left: "0.625rem", fontSize: "0.75rem", fontWeight: 700, color: g.text, backgroundColor: g.bg, padding: "0.125rem 0.625rem", borderRadius: "0.375rem" }}>Grad {listing.grade} · {listing.score}</span>
        </div>

        <div style={{ padding: "1.25rem" }}>
          <div style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>{listing.title || "—"}</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>{priceLine(listing, true)}</div>
          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.375rem" }}>
            {[listing.year && `${listing.year}`, listing.km != null && `${listing.km.toLocaleString("ro-RO")} km`,
              listing.fuel_type && `${listing.fuel_type}`, listing.transmission && `${listing.transmission}`,
              listing.location && `${listing.location}`].filter(Boolean).join(" · ")}
          </div>
          {(enriched.seller_name || enriched.listed_at) && (
            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
              {[enriched.seller_name && `${enriched.seller_name}`, enriched.listed_at && `Postat ${formatListedDate(enriched.listed_at)}`].filter(Boolean).join(" · ")}
            </div>
          )}

          {/* Import score */}
          {IMPORT_PLATFORMS.includes(listing.platform) && importData && (
            <div style={{ backgroundColor: "rgba(124,58,237,0.07)", border: "0.5px solid rgba(124,58,237,0.25)", borderRadius: "0.625rem", padding: "0.875rem 1rem", marginTop: "1rem" }}>
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
          )}

          {/* ML prediction (BMW) */}
          {isBmw && (
            <div style={{ backgroundColor: "rgba(124,58,237,0.07)", border: "0.5px solid rgba(124,58,237,0.25)", borderRadius: "0.625rem", padding: "0.875rem 1rem", marginTop: "1rem" }}>
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
          )}

          {enriched.description && (
            <div style={{ marginTop: "1rem" }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Descriere</div>
              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{enriched.description}</div>
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "1.25rem" }}>
            <button onClick={onSave} style={actBtn("#60a5fa")}><Bookmark style={{ width: "14px", height: "14px" }} /> Salvează</button>
            <button onClick={onIgnore} style={actBtn("var(--text-secondary)")}><EyeOff style={{ width: "14px", height: "14px" }} /> Ignoră</button>
            {listing.url && <a href={listing.url} target="_blank" rel="noopener noreferrer" style={{ ...actBtn("#4ade80"), textDecoration: "none" }}><ExternalLink style={{ width: "14px", height: "14px" }} /> Deschide pe {PLATFORM_LABELS[listing.platform] || listing.platform}</a>}
            <button onClick={onDelete} style={{ ...actBtn("#f87171"), marginLeft: "auto" }}><Trash2 style={{ width: "14px", height: "14px" }} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}

function actBtn(color) {
  return {
    display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
    backgroundColor: "var(--bg-dark)", color, border: `1px solid ${color === "var(--text-secondary)" ? "var(--border-color)" : color + "55"}`,
    borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
  };
}

function galleryNav(left) {
  return {
    position: "absolute", top: "50%", transform: "translateY(-50%)",
    [left ? "left" : "right"]: "0.5rem",
    background: "rgba(0,0,0,0.55)", color: "white", border: "none", borderRadius: "50%",
    width: "28px", height: "28px", cursor: "pointer", fontSize: "1.1rem", lineHeight: 1,
    display: "flex", alignItems: "center", justifyContent: "center",
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

function ManualMobileDeWarning() {
  return (
    <span title="Funcționează doar de pe IP rezidential (pe server/datacenter: 403 Imperva)."
      style={{ display: "inline-flex", alignItems: "center", gap: "0.2rem", marginLeft: "0.375rem", fontSize: "10px", padding: "0.125rem 0.4rem", borderRadius: "4px", background: "var(--bg-warning)", color: "var(--text-warning)", verticalAlign: "middle", cursor: "help", fontWeight: 500 }}>
      <AlertTriangle style={{ width: "11px", height: "11px" }} /> IP local
    </span>
  );
}

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
                }}>{p.label}{p.value === "mobile_de" && <ManualMobileDeWarning />}</button>
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
