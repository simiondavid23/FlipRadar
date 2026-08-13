"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Percent } from "lucide-react";

import { dealsAPI } from "@/lib/api";
import { selectStyle, tabPillStyle } from "@/lib/uiStyles";
import ListingFeedCard from "@/components/shared/ListingFeedCard";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import StatCardsRow from "@/components/shared/StatCardsRow";
import TopBar from "@/components/shared/TopBar";
import { timeAgo } from "@/components/shared/listingHelpers";

// Praguri de discount, in spiritul GRADE_COLORS din uiStyles: cu cat reducerea e
// mai mare, cu atat insigna e mai "verde".
const DISCOUNT_COLORS = [
  { min: 40, bg: "rgba(74,222,128,.22)", border: "rgba(74,222,128,.5)", text: "#4ade80" },
  { min: 30, bg: "rgba(74,222,128,.13)", border: "rgba(74,222,128,.34)", text: "#86efac" },
  { min: 0, bg: "rgba(250,204,21,.13)", border: "rgba(250,204,21,.34)", text: "#fde047" },
];
const discountCfg = (pct) => DISCOUNT_COLORS.find((c) => (pct || 0) >= c.min) || DISCOUNT_COLORS[2];

const SHOP_CHIP = {
  bg: "rgba(34,211,238,.11)", border: "rgba(34,211,238,.3)", text: "#7ee7f8",
};

// Filtrul de stare. `active` merge ca query param spre backend; `state` la fel.
// „Active" ascunde deliberat deal-urile ignorate — sunt tot active, dar userul
// le-a scos din atentie.
const STATE_TABS = [
  { key: "active", label: "Active" },
  { key: "noi", label: "Noi" },
  { key: "ignorate", label: "Ignorate" },
  { key: "incheiate", label: "Încheiate" },
];

const DISCOUNT_FILTERS = [
  { value: "", label: "Orice discount" },
  { value: "20", label: "≥ 20%" },
  { value: "30", label: "≥ 30%" },
  { value: "40", label: "≥ 40%" },
  { value: "50", label: "≥ 50%" },
];

const SORTS = [
  { value: "discount", label: "Sortare: discount" },
  { value: "recent", label: "Cele mai noi" },
  { value: "price", label: "Preț crescător" },
];

const REASON_LABEL = {
  compare_at: "reducere magazin",
  istoric: "minim istoric",
  ambele: "reducere + minim istoric",
};

const CATEGORY_LABEL = {
  sneakers: "Sneakers",
  incaltaminte: "Încălțăminte",
  tcg: "TCG",
  fashion: "Fashion",
  electronice: "Electronice",
};

const round1 = (n) => (n == null ? null : Math.round(n * 10) / 10);

export default function DealsPage() {
  const [deals, setDeals] = useState([]);
  const [stats, setStats] = useState(null);
  const [shops, setShops] = useState([]);
  const [loading, setLoading] = useState(true);
  const [feedError, setFeedError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [promoting, setPromoting] = useState(null);

  const [tab, setTab] = useState("active");
  const [shopFilter, setShopFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [minDiscount, setMinDiscount] = useState("");
  const [sortBy, setSortBy] = useState("discount");

  // Starea si discountul se filtreaza SERVER-side; categoria ramane client-side,
  // fiindca maparea magazin -> categorie e deja in datele de la /shops.
  const loadDeals = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (tab === "incheiate") params.active = false;
      else params.active = true;
      if (tab === "noi") params.state = "nou";
      if (tab === "ignorate") params.state = "ignorat";
      if (shopFilter) params.shop_domain = shopFilter;
      if (minDiscount) params.min_discount = Number(minDiscount);

      const { data } = await dealsAPI.list(params);
      // Tab-ul „Active" arata tot ce e viu MAI PUTIN ce a fost ignorat explicit.
      setDeals(tab === "active" ? data.filter((d) => d.state !== "ignorat") : data);
      setFeedError("");
    } catch (err) {
      setFeedError(err.response?.data?.detail || "Nu am putut încărca deal-urile.");
    } finally {
      setLoading(false);
    }
  }, [tab, shopFilter, minDiscount]);

  const loadSide = useCallback(async () => {
    try {
      const [s, sh] = await Promise.all([dealsAPI.stats(), dealsAPI.shops()]);
      setStats(s.data);
      setShops(sh.data || []);
    } catch {
      // Statisticile si lista de magazine sunt accesorii: o eroare aici nu trebuie
      // sa ascunda feed-ul, care are propriul banner.
    }
  }, []);

  useEffect(() => { loadDeals(); }, [loadDeals]);
  useEffect(() => { loadSide(); }, [loadSide]);

  const shopByDomain = useMemo(
    () => Object.fromEntries(shops.map((s) => [s.domain, s])), [shops]);

  const categories = useMemo(() => {
    const set = new Set(shops.map((s) => s.category).filter(Boolean));
    return [...set].sort((a, b) => a.localeCompare(b, "ro"));
  }, [shops]);

  const problemShops = useMemo(
    () => shops.filter((s) => s.last_status && s.last_status !== "ok"), [shops]);

  const visibleDeals = useMemo(() => {
    let rows = deals;
    if (categoryFilter) {
      rows = rows.filter((d) => shopByDomain[d.shop_domain]?.category === categoryFilter);
    }
    const sorted = [...rows];
    if (sortBy === "recent") {
      sorted.sort((a, b) => new Date(b.first_seen_at) - new Date(a.first_seen_at));
    } else if (sortBy === "price") {
      // Comparatia se face pe RON, ca preturile in EUR/SEK sa fie comparabile.
      sorted.sort((a, b) => (a.price_ron ?? a.price) - (b.price_ron ?? b.price));
    } else {
      sorted.sort((a, b) => b.discount_pct - a.discount_pct);
    }
    return sorted;
  }, [deals, categoryFilter, shopByDomain, sortBy]);

  const statCards = [
    { label: "Deal-uri active", value: stats?.active ?? 0, color: "#22d3ee" },
    { label: "Noi", value: stats?.noi ?? 0, color: "#4ade80" },
    {
      label: "Discount mediu",
      value: stats?.avg_discount_active != null ? `${round1(stats.avg_discount_active)}%` : "—",
      color: "#fde047",
    },
    { label: "Ultimul scan", value: stats?.last_scan_at ? timeAgo(stats.last_scan_at) : "—", color: "#a5b4fc" },
  ];

  const patch = (id, changes) =>
    setDeals((prev) => prev.map((d) => (d.id === id ? { ...d, ...changes } : d)));

  const handleOpen = (deal) => {
    if (deal.state === "nou") {
      patch(deal.id, { state: "vazut" });
      dealsAPI.setState(deal.id, "vazut").catch(() => {});
    }
  };

  const handleIgnore = async (deal) => {
    const anterior = deals;
    // Scoatere optimista din feed-ul curent (in „Ignorate" ramane vizibil).
    setDeals((prev) => prev.filter((d) => d.id !== deal.id));
    try {
      await dealsAPI.setState(deal.id, "ignorat");
      loadSide();
    } catch (err) {
      setDeals(anterior);
      setActionMessage(err.response?.data?.detail || "Nu am putut ignora deal-ul.");
    }
  };

  const handlePromote = async (deal) => {
    setPromoting(deal.id);
    setActionMessage("");
    try {
      await dealsAPI.promote(deal.id);
      patch(deal.id, { state: "promovat" });
      setActionMessage(`„${deal.title}” a fost adăugat la produsele urmărite.`);
      loadSide();
    } catch (err) {
      // Promovarea face extracție live: produsul poate fi dispărut între timp.
      setActionMessage(err.response?.data?.detail || "Promovarea a eșuat.");
    } finally {
      setPromoting(null);
    }
  };

  return (
    <div>
      <TopBar path={["CATALOG", "DEAL-URI"]} />

      <PageHeading
        icon={Percent}
        title="Deal-uri"
        subtitle={<>Chilipiruri găsite automat în magazinele Shopify — <Hl>{visibleDeals.length}</Hl> în vizualizare.</>}
        meta={stats?.last_scan_at ? `ULTIMUL SCAN · ${timeAgo(stats.last_scan_at)}` : null}
      />

      <StatCardsRow cards={statCards} />

      {/* Filtre */}
      <div style={{
        display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginTop: "16px",
      }}>
        {STATE_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{ ...tabPillStyle(tab === t.key), display: "inline-flex", alignItems: "center", gap: "8px" }}
          >
            {tab === t.key && <span className="pill-nav-dot" />}
            {t.label}
          </button>
        ))}

        <select value={shopFilter} onChange={(e) => setShopFilter(e.target.value)} style={selectStyle}>
          <option value="">Toate magazinele</option>
          {shops.map((s) => (
            <option key={s.domain} value={s.domain}>{s.label}</option>
          ))}
        </select>

        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} style={selectStyle}>
          <option value="">Toate categoriile</option>
          {categories.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABEL[c] || c}</option>
          ))}
        </select>

        <select value={minDiscount} onChange={(e) => setMinDiscount(e.target.value)} style={selectStyle}>
          {DISCOUNT_FILTERS.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={selectStyle}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Banda de sănătate — apare DOAR când un magazin nu a scanat curat. */}
      {problemShops.length > 0 && (
        <div style={{ display: "flex", gap: "7px", flexWrap: "wrap", marginTop: "12px" }}>
          {problemShops.map((s) => (
            <span
              key={s.domain}
              title={s.error_message || ""}
              style={{
                padding: "3px 9px", borderRadius: "8px", fontSize: "10.5px", fontWeight: 600,
                background: s.last_status === "error" ? "rgba(248,113,113,.1)" : "rgba(250,204,21,.1)",
                color: s.last_status === "error" ? "#f87171" : "#fde047",
                border: `1px solid ${s.last_status === "error" ? "rgba(248,113,113,.3)" : "rgba(250,204,21,.3)"}`,
              }}
            >
              {s.label}: {s.last_status === "error" ? "eroare la ultimul scan" : "scan parțial"}
            </span>
          ))}
        </div>
      )}

      {actionMessage && (
        <div style={{
          marginTop: "12px", padding: "9px 13px", borderRadius: "10px",
          background: "rgba(34,211,238,.07)", border: "1px solid rgba(34,211,238,.25)",
          color: "var(--text-secondary)", fontSize: "12px",
        }}>
          {actionMessage}
        </div>
      )}

      <FeedErrorBanner message={feedError} onRetry={loadDeals} />

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem", color: "var(--text-dim)", fontSize: "12.5px" }}>
          Se încarcă deal-urile…
        </div>
      ) : visibleDeals.length === 0 ? (
        <div className="glass-panel" style={{
          textAlign: "center", padding: "3rem", marginTop: "14px",
          color: "var(--text-dim)", fontSize: "12.5px",
        }}>
          Niciun deal aici. Scanarea rulează la fiecare 6 ore — verifică în Setări
          pragul de discount și magazinele active.
        </div>
      ) : (
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(305px, 1fr))",
          gap: "14px", marginTop: "14px",
        }}>
          {visibleDeals.map((deal) => {
            const shop = shopByDomain[deal.shop_domain];
            const incheiat = Boolean(deal.ended_at);
            const marimi = deal.sizes_available || [];
            return (
              <ListingFeedCard
                key={deal.id}
                listing={{
                  id: deal.id,
                  title: deal.title,
                  url: deal.url,
                  price: deal.price,
                  currency: deal.currency,
                  found_at: deal.first_seen_at,
                  status: deal.state === "promovat" ? "saved"
                    : deal.state === "ignorat" ? "ignored" : null,
                }}
                image={deal.image_url}
                showMarginLine={false}
                scoreBadge={`−${Math.round(deal.discount_pct)}%`}
                scoreCfg={discountCfg(deal.discount_pct)}
                platformBadge={shop?.label || deal.shop_domain}
                platformCfg={SHOP_CHIP}
                imageOverlaySlot={
                  <>
                    {/* Favicon-ul magazinului: zero mentenanță per domeniu, se ascunde singur dacă lipsește. */}
                    <img
                      src={`https://www.google.com/s2/favicons?domain=${deal.shop_domain}&sz=32`}
                      alt=""
                      onError={(e) => { e.currentTarget.style.display = "none"; }}
                      style={{
                        position: "absolute", bottom: "9px", left: "9px",
                        width: "18px", height: "18px", borderRadius: "5px",
                        background: "rgba(8,14,27,.7)", padding: "2px",
                      }}
                    />
                    {incheiat && (
                      <div style={{
                        position: "absolute", inset: 0,
                        background: "rgba(4,7,14,.62)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        <span style={{
                          padding: "4px 11px", borderRadius: "8px",
                          background: "rgba(148,163,184,.18)", color: "var(--text-dim)",
                          border: "1px solid rgba(148,163,184,.3)",
                          fontFamily: "var(--font-mono)", fontSize: "9.5px",
                          letterSpacing: ".14em", textTransform: "uppercase",
                        }}>
                          Încheiat
                        </span>
                      </div>
                    )}
                  </>
                }
                priceNode={
                  <>
                    <span style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-.4px", color: "#ffffff" }}>
                      {Math.round(deal.price)}
                    </span>
                    <span style={{ fontSize: "11.5px", fontWeight: 500, color: "var(--text-tertiary)" }}>
                      {deal.currency}
                    </span>
                    {deal.compare_at_price ? (
                      <span style={{ fontSize: "12px", color: "var(--text-muted)", textDecoration: "line-through" }}>
                        {Math.round(deal.compare_at_price)}
                      </span>
                    ) : null}
                    {deal.currency !== "RON" && deal.price_ron != null ? (
                      <span style={{ width: "100%", fontSize: "11px", color: "var(--text-mono)" }}>
                        ≈ {Math.round(deal.price_ron)} RON
                      </span>
                    ) : null}
                  </>
                }
                specsNode={
                  <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                    {marimi.length > 0 && (
                      <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                        {marimi.slice(0, 8).map((m, i) => (
                          <span key={`${m}-${i}`} style={{
                            padding: "1px 6px", borderRadius: "5px", fontSize: "10px",
                            background: "rgba(148,163,184,.09)", color: "var(--text-tertiary)",
                            border: "1px solid rgba(148,163,184,.16)",
                          }}>
                            {m}
                          </span>
                        ))}
                        {marimi.length > 8 && (
                          <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>
                            +{marimi.length - 8}
                          </span>
                        )}
                      </div>
                    )}
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".1em",
                      textTransform: "uppercase", color: "var(--text-mono)",
                    }}>
                      {REASON_LABEL[deal.reason] || deal.reason}
                      {deal.state === "promovat" ? " · promovat" : ""}
                    </span>
                  </div>
                }
                openLabel={promoting === deal.id ? "Se promovează…" : "Deschide în magazin"}
                hideActions={incheiat}
                onOpen={() => handleOpen(deal)}
                onOpenExternal={() => handleOpen(deal)}
                onSave={() => handlePromote(deal)}
                onIgnore={() => handleIgnore(deal)}
                isSelected={false}
                onToggleSelect={() => {}}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
