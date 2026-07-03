"use client";
import { useState, useEffect, useCallback } from "react";
import { realEstateMonitorAPI } from "@/lib/api";
import { Home, RefreshCw, ExternalLink, Bookmark, EyeOff, Trash2, X, ImageOff } from "lucide-react";

const PLATFORM_LABELS = {
  olx: "OLX", storia: "Storia", imobiliare_ro: "Imobiliare.ro",
  facebook_marketplace: "FB Marketplace", facebook_groups: "Grupuri FB",
};
const GRADE_COLORS = {
  A: { bg: "rgba(34,197,94,0.15)", fg: "#4ade80" },
  B: { bg: "rgba(37,99,235,0.15)", fg: "#60a5fa" },
  C: { bg: "rgba(245,158,11,0.15)", fg: "#fbbf24" },
  D: { bg: "rgba(239,68,68,0.15)", fg: "#f87171" },
};
const STATUS_TABS = [
  { value: "active", label: "Active" },
  { value: "saved", label: "Salvate" },
  { value: "ignored", label: "Ignorate" },
];
const CITIES = ["București", "Cluj-Napoca", "Iași", "Timișoara", "Brașov", "Constanța", "Sibiu", "Oradea", "Arad", "Pitești"];

const gradeCfg = (g) => GRADE_COLORS[g] || GRADE_COLORS.C;
const selStyle = {
  backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.5rem",
  padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none",
};

export default function REFeedPage() {
  const [listings, setListings] = useState([]);
  const [keywords, setKeywords] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: "", grade: "", status: "active", rooms: "", zone: "", city: "", keyword_id: "" });
  const [selected, setSelected] = useState(null);
  const [scanning, setScanning] = useState(false);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: filters.status, limit: 100 };
      if (filters.platform) params.platform = filters.platform;
      if (filters.grade) params.grade = filters.grade;
      if (filters.rooms) params.rooms = filters.rooms;
      if (filters.zone) params.zone = filters.zone;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      const r = await realEstateMonitorAPI.getFeed(params);
      let items = r.data?.items || [];
      if (filters.city) items = items.filter((i) => (i.city || "") === filters.city);
      setListings(items);
    } catch (e) { console.error("[REFeed]", e); }
    finally { setLoading(false); }
  }, [filters]);

  const loadStats = useCallback(async () => {
    try { const r = await realEstateMonitorAPI.getStats(); setStats(r.data || {}); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => { realEstateMonitorAPI.getKeywords().then((r) => setKeywords(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { loadFeed(); loadStats(); }, [loadFeed, loadStats]);

  const setStatus = async (id, status) => {
    try { await realEstateMonitorAPI.updateStatus(id, status); setSelected(null); await loadFeed(); await loadStats(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const remove = async (id) => {
    if (!confirm("Ștergi acest anunț?")) return;
    try { await realEstateMonitorAPI.deleteListing(id); setSelected(null); await loadFeed(); await loadStats(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const handleConfirmDuplicate = async (listingId, matchId) => {
    try {
      await realEstateMonitorAPI.flagDuplicate(listingId, matchId);
      setListings((prev) => prev.map((l) => (l.id === listingId ? { ...l, duplicate_level: 2 } : l)));
      if (selected?.id === listingId) setSelected((prev) => (prev ? { ...prev, duplicate_level: 2 } : null));
    } catch {
      alert("Eroare la confirmare duplicat.");
    }
  };

  const handleDismissDuplicate = async (listingId) => {
    try {
      setListings((prev) => prev.map((l) => (l.id === listingId ? { ...l, duplicate_level: null, duplicate_match_id: null } : l)));
      if (selected?.id === listingId) setSelected((prev) => (prev ? { ...prev, duplicate_level: null, duplicate_match_id: null } : null));
    } catch {
      alert("Eroare.");
    }
  };
  const handleScanNow = async () => {
    setScanning(true);
    try { await realEstateMonitorAPI.scanNow(); setTimeout(() => { loadFeed(); setScanning(false); }, 15000); }
    catch { setScanning(false); }
  };

  const byGrade = stats.by_grade || {};
  const statCards = [
    { label: "Total listinguri", value: stats.total_listings ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Grade A", value: byGrade.A || 0, color: "#4ade80" },
    { label: "Grupuri duplicate", value: stats.duplicate_groups ?? 0, color: "#fbbf24" },
  ];

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Home style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Feed Imobiliare</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>Chirii scorate, cu zone normalizate și detecție duplicate</p>
          </div>
        </div>
        <button onClick={handleScanNow} disabled={scanning} style={{
          display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem",
          backgroundColor: scanning ? "rgba(37,99,235,0.08)" : "rgba(37,99,235,0.15)", color: "#60a5fa",
          border: "1px solid rgba(37,99,235,0.3)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500,
          cursor: scanning ? "default" : "pointer", opacity: scanning ? 0.7 : 1,
        }}>
          <RefreshCw style={{ width: "14px", height: "14px", animation: scanning ? "spin 1s linear infinite" : "none" }} />
          {scanning ? "Se scanează..." : "Scanează acum"}
        </button>
      </div>

      {stats.has_facebook_keywords && stats.facebook_session_valid === false && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.75rem 1rem", marginBottom: "1.25rem", backgroundColor: "rgba(245,158,11,0.08)", border: "0.5px solid rgba(245,158,11,0.3)", borderRadius: "0.625rem" }}>
          <span style={{ fontSize: "1.125rem" }}>⚠️</span>
          <div>
            <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "#fbbf24", margin: 0 }}>Sesiunea Facebook a expirat</p>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.125rem 0 0" }}>
              Keyword-urile Facebook nu vor returna rezultate. Reautentifică-te din <a href="/dashboard/settings" style={{ color: "#fbbf24", fontWeight: 500 }}>Setări → Facebook</a>.
            </p>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.875rem", marginBottom: "1.25rem" }}>
        {statCards.map((c) => (
          <div key={c.label} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: c.color }}>{c.value}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.125rem" }}>{c.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.625rem", marginBottom: "1.25rem" }}>
        <div style={{ display: "inline-flex", gap: "0.25rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", padding: "0.25rem" }}>
          {STATUS_TABS.map((t) => {
            const active = filters.status === t.value;
            return <button key={t.value} onClick={() => setFilters((f) => ({ ...f, status: t.value }))} style={{ padding: "0.375rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", border: "none", backgroundColor: active ? "rgba(37,99,235,0.15)" : "transparent", color: active ? "#60a5fa" : "var(--text-secondary)" }}>{t.label}</button>;
          })}
        </div>
        <select value={filters.platform} onChange={(e) => setFilters((f) => ({ ...f, platform: e.target.value }))} style={selStyle}>
          <option value="">Toate sursele</option>
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={filters.grade} onChange={(e) => setFilters((f) => ({ ...f, grade: e.target.value }))} style={selStyle}>
          <option value="">Toate gradele</option>
          {["A", "B", "C", "D"].map((g) => <option key={g} value={g}>Grad {g}</option>)}
        </select>
        <select value={filters.rooms} onChange={(e) => setFilters((f) => ({ ...f, rooms: e.target.value }))} style={selStyle}>
          <option value="">Camere</option>
          {[1, 2, 3, 4].map((r) => <option key={r} value={r}>{r}{r === 4 ? "+" : ""} cam</option>)}
        </select>
        <input placeholder="Zonă" value={filters.zone} onChange={(e) => setFilters((f) => ({ ...f, zone: e.target.value }))} style={{ ...selStyle, width: "120px" }} />
        <select value={filters.city} onChange={(e) => setFilters((f) => ({ ...f, city: e.target.value }))} style={selStyle}>
          <option value="">Toate orașele</option>
          {CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filters.keyword_id} onChange={(e) => setFilters((f) => ({ ...f, keyword_id: e.target.value }))} style={selStyle}>
          <option value="">Toate keyword-urile</option>
          {keywords.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
      </div>

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : listings.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          Niciun anunț. Adaugă keyword-uri și așteaptă scanarea (la 30 min) sau apasă „Scanează acum”.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
          {listings.map((l) => <RECard key={l.id} listing={l} onClick={() => setSelected(l)} />)}
        </div>
      )}

      {selected && (
        <REModal listing={selected} onClose={() => setSelected(null)}
          onSave={() => setStatus(selected.id, "saved")} onIgnore={() => setStatus(selected.id, "ignored")}
          onConfirmDup={handleConfirmDuplicate} onDismissDup={handleDismissDuplicate} onDelete={() => remove(selected.id)} />
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

function RECard({ listing, onClick }) {
  const g = gradeCfg(listing.grade);
  const img = listing.image_url || (Array.isArray(listing.images_json) ? listing.images_json[0] : null);
  const drop = priceDropPct(listing);
  return (
    <div onClick={onClick} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden", cursor: "pointer", display: "flex", flexDirection: "column" }}>
      <div style={{ position: "relative", height: "150px", backgroundColor: "var(--bg-dark)" }}>
        {img ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={img} alt={listing.title || ""} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}><ImageOff style={{ width: "26px", height: "26px" }} /></div>
        )}
        <span style={{ position: "absolute", top: "0.5rem", left: "0.5rem", fontSize: "0.6875rem", fontWeight: 700, color: g.fg, backgroundColor: g.bg, padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>{listing.grade}</span>
        <span style={{ position: "absolute", top: "0.5rem", right: "0.5rem", fontSize: "0.625rem", fontWeight: 600, color: "white", backgroundColor: "rgba(0,0,0,0.6)", padding: "0.125rem 0.5rem", borderRadius: "0.375rem" }}>{PLATFORM_LABELS[listing.platform] || listing.platform}</span>
        {listing.duplicate_level === 3 && (
          <span style={{ position: "absolute", bottom: "0.5rem", left: "0.5rem", background: "rgba(37,99,235,0.15)", color: "#60a5fa", fontSize: "9.5px", padding: "2px 6px", borderRadius: "4px" }}>Anunț similar detectat →</span>
        )}
        {listing.duplicate_group_id && listing.duplicate_level && listing.duplicate_level <= 2 && (
          <span style={{ position: "absolute", bottom: "0.5rem", left: "0.5rem", background: "rgba(124,58,237,0.2)", color: "#a78bfa", fontSize: "9.5px", padding: "2px 6px", borderRadius: "4px" }}>🔗 Grup duplicate</span>
        )}
      </div>
      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.375rem", flex: 1 }}>
        <div style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-primary)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{listing.title || "—"}</div>
        {/* MODIFICARE 16 — zona normalizata vizibila (cu adresa bruta cand difera) */}
        {listing.zone_normalized && (
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{listing.zone_normalized}</span>
            {listing.zone_raw && listing.zone_raw.trim() !== listing.zone_normalized.trim() && (
              <span style={{ color: "var(--text-muted)" }}>← {listing.zone_raw}</span>
            )}
          </div>
        )}
        <div style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)" }}>
          {priceLine(listing)}
          {drop !== null && <span style={{ fontSize: "0.7rem", color: "#fb923c", marginLeft: "0.375rem" }}>↓ {drop}%</span>}
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>
          {[listing.rooms && `🛏 ${listing.rooms} cam`, listing.area_sqm && `📐 ${listing.area_sqm} mp`, listing.floor && `🏢 Etaj ${listing.floor}`].filter(Boolean).join(" · ")}
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
          {[listing.zone_normalized || listing.zone_raw, listing.city].filter(Boolean).join(" · ")}
        </div>
        {listing.price_per_sqm && <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>{Number(listing.price_per_sqm).toFixed(1)} {listing.currency}/mp</div>}
      </div>
    </div>
  );
}

function REModal({ listing, onClose, onSave, onIgnore, onConfirmDup, onDismissDup, onDelete }) {
  const g = gradeCfg(listing.grade);
  const img = listing.image_url || (Array.isArray(listing.images_json) ? listing.images_json[0] : null);
  const history = Array.isArray(listing.price_history) ? listing.price_history : [];

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "560px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ position: "relative", height: "220px", backgroundColor: "var(--bg-dark)" }}>
          {img ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={img} alt={listing.title || ""} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : (
            <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}><ImageOff style={{ width: "32px", height: "32px" }} /></div>
          )}
          <button onClick={onClose} style={{ position: "absolute", top: "0.625rem", right: "0.625rem", background: "rgba(0,0,0,0.6)", border: "none", borderRadius: "0.375rem", padding: "0.25rem", cursor: "pointer", color: "white", display: "flex" }}><X style={{ width: "18px", height: "18px" }} /></button>
          <span style={{ position: "absolute", top: "0.625rem", left: "0.625rem", fontSize: "0.75rem", fontWeight: 700, color: g.fg, backgroundColor: g.bg, padding: "0.125rem 0.625rem", borderRadius: "0.375rem" }}>Grad {listing.grade} · {listing.score}/100</span>
        </div>

        <div style={{ padding: "1.25rem" }}>
          <div style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>{listing.title || "—"}</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>{priceLine(listing)}</div>
          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.375rem" }}>
            {[listing.rooms && `🛏 ${listing.rooms} cam`, listing.area_sqm && `📐 ${listing.area_sqm} mp`, listing.floor && `🏢 Etaj ${listing.floor}`,
              (listing.zone_normalized || listing.zone_raw), listing.city].filter(Boolean).join(" · ")}
          </div>

          {/* Scoring */}
          <div style={{ backgroundColor: "rgba(37,99,235,0.06)", border: "0.5px solid rgba(37,99,235,0.2)", borderRadius: "0.625rem", padding: "0.75rem 1rem", marginTop: "1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
            <div style={{ fontWeight: 600, color: "#60a5fa", marginBottom: "0.25rem" }}>Scor: {listing.score}/100 ({listing.grade})</div>
            {listing.price_per_sqm && <div>Preț/mp: {Number(listing.price_per_sqm).toFixed(2)} {listing.currency}</div>}
            {listing.zone_normalized && <div>Zonă normalizată: {listing.zone_normalized}</div>}
          </div>

          {/* Price history */}
          {history.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Istoricul prețului</div>
              {history.map((h, i) => (
                <div key={i} style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                  {h.date ? new Date(h.date).toLocaleDateString("ro-RO") : "—"}: {Math.round(h.price).toLocaleString("ro-RO")} {h.currency}
                </div>
              ))}
            </div>
          )}

          {/* Duplicate — auto-populat cu match-ul detectat de sistem */}
          {listing.duplicate_level === 3 && listing.duplicate_match_id && (
            <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", backgroundColor: "rgba(37,99,235,0.06)", border: "0.5px solid rgba(37,99,235,0.25)", borderRadius: "0.625rem" }}>
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.625rem" }}>
                Sistemul a detectat un anunț similar.
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button onClick={() => onConfirmDup(listing.id, listing.duplicate_match_id)} style={{ padding: "0.375rem 0.875rem", backgroundColor: "rgba(37,99,235,0.12)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>
                  ✓ Confirmă duplicat
                </button>
                <button onClick={() => onDismissDup(listing.id)} style={{ padding: "0.375rem 0.875rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "0.5px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>
                  Nu e duplicat
                </button>
              </div>
            </div>
          )}

          {listing.description && (
            <div style={{ marginTop: "1rem" }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Descriere</div>
              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{listing.description}</div>
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "1.25rem" }}>
            <button onClick={onSave} style={actBtn("#60a5fa")}><Bookmark style={{ width: "14px", height: "14px" }} /> Salvează</button>
            <button onClick={onIgnore} style={actBtn("var(--text-secondary)")}><EyeOff style={{ width: "14px", height: "14px" }} /> Ignoră</button>
            {listing.url && <a href={listing.url} target="_blank" rel="noopener noreferrer" style={{ ...actBtn("#4ade80"), textDecoration: "none" }}><ExternalLink style={{ width: "14px", height: "14px" }} /> Deschide</a>}
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
