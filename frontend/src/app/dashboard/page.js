"use client";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { dashboardAPI, productsAPI, reportsAPI } from "@/lib/api";
import Link from "next/link";
import {
  Package, Eye, Bell, TrendingUp, AlertTriangle, Database,
  Search, Boxes, ArrowRight, ArrowUpRight, Euro, Target,
  Radar, Car, Building2, ShoppingCart
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar,
} from "recharts";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import KpiCard from "@/components/shared/KpiCard";

const nf = (v, d = 2) => Number(v || 0).toLocaleString("ro-RO", { minimumFractionDigits: d, maximumFractionDigits: d });

// Panoul glass reutilizat de graficele si listele paginii.
function Panel({ title, sub, right, children, style }) {
  return (
    <div className="glass-panel" style={{ padding: "16px 18px", ...style }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", marginBottom: "11px", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)" }}>{title}</div>
          {sub ? (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".13em", color: "var(--text-mono)", marginTop: "3px", textTransform: "uppercase" }}>
              {sub}
            </div>
          ) : null}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

// Legenda punctata a graficelor (VENIT / PROFIT).
function LegendDot({ color, label }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "6px", fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-tertiary)" }}>
      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: color, boxShadow: `0 0 8px ${color}` }} />
      {label}
    </span>
  );
}

// Cardul unui modul de scanare (Radar / Auto / Imobiliare).
function ModuleCard({ icon: Icon, name, value, keywords, href }) {
  return (
    <Link
      href={href}
      className="glass-card-gradient lift-hover"
      style={{
        position: "relative", flex: 1, padding: "15px 17px", display: "flex", flexDirection: "column",
        justifyContent: "center", gap: "8px", color: "inherit", textDecoration: "none", minHeight: "104px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
        <div
          style={{
            width: "28px", height: "28px", borderRadius: "9px", background: "rgba(34,211,238,.09)",
            border: "1px solid rgba(34,211,238,.26)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}
        >
          <Icon style={{ width: "14px", height: "14px", color: "#7ee7f8" }} strokeWidth={1.8} />
        </div>
        <span style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)" }}>{name}</span>
        <ArrowUpRight style={{ width: "13px", height: "13px", color: "var(--text-mono)", marginLeft: "auto" }} strokeWidth={1.8} />
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "7px" }}>
        <span style={{ fontSize: "24px", fontWeight: 700, letterSpacing: "-.5px", lineHeight: 1, color: "#7ee7f8" }}>+{value}</span>
        <span style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>anunțuri noi · 24h</span>
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".12em", color: "var(--text-mono)" }}>
        {keywords} KW ACTIVE
      </div>
    </Link>
  );
}

// Rand de scurtatura din panoul "Acțiuni rapide".
function QuickAction({ href, icon: Icon, title, suffix }) {
  return (
    <Link
      href={href}
      className="glass-chip quick-action"
      style={{
        display: "flex", alignItems: "center", gap: "11px", padding: "8px 11px", borderRadius: "11px",
        color: "inherit", textDecoration: "none",
      }}
    >
      <Icon style={{ width: "14px", height: "14px", color: "#7ee7f8", flexShrink: 0 }} strokeWidth={1.8} />
      <span style={{ fontSize: "12px", fontWeight: 500, flex: 1, color: "var(--text-primary)" }}>{title}</span>
      {suffix ? <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-mono)" }}>{suffix}</span> : null}
      <ArrowRight style={{ width: "13px", height: "13px", color: "var(--text-mono)", flexShrink: 0 }} strokeWidth={1.8} />
    </Link>
  );
}

// Rand din "Rezumat activitate": punct colorat + eticheta + valoare mono.
function ActivityItem({ color, label, detail, value, isLast }) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: "10px", padding: "8px 0",
        borderBottom: isLast ? "none" : "1px solid rgba(94,140,255,.08)",
      }}
    >
      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}`, flexShrink: 0 }} />
      <span style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 500, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: "11.5px", color: "var(--text-tertiary)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {detail}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-primary)", fontWeight: 700, flexShrink: 0 }}>{value}</span>
    </div>
  );
}

// Tooltip glass pentru graficele recharts.
const tooltipStyle = {
  background: "rgba(4,9,18,.9)",
  backdropFilter: "blur(14px)",
  border: "1px solid rgba(34,211,238,.3)",
  borderRadius: "12px",
  fontSize: "11px",
  fontFamily: "var(--font-sans)",
  boxShadow: "0 12px 30px rgba(0,0,0,.5)",
};
const axisTick = { fill: "#2b3a5c", fontSize: 8, fontFamily: "var(--font-mono)" };

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [productsStats, setProductsStats] = useState(null);
  const [timeseries, setTimeseries] = useState([]);
  const [topProducts, setTopProducts] = useState([]);
  const [bestCategory, setBestCategory] = useState(null); // FlipRadar — C.2
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      // Interval ultimele 30 de zile pentru rezumatul de rapoarte (cea mai profitabila categorie)
      const to = new Date();
      const from = new Date();
      from.setDate(to.getDate() - 29);
      const isoDate = (d) => d.toISOString().slice(0, 10);

      const [statsRes, tsRes, topRes, productsStatsRes, reportsRes, schedRes] =
        await Promise.all([
          dashboardAPI.getStats().catch(() => ({ data: null })),
          dashboardAPI.getSalesTimeseries(30).catch(() => ({ data: null })),
          dashboardAPI.getTopProducts(5).catch(() => ({ data: null })),
          productsAPI.getStats().catch(() => ({ data: null })),
          reportsAPI.getSummary({ date_from: isoDate(from), date_to: isoDate(to) }).catch(() => ({ data: null })),
          dashboardAPI.getSchedulerStatus().catch(() => ({ data: null })),
        ]);
      setStats(statsRes.data);
      setTimeseries((tsRes.data?.data || []).map((d) => ({
        ...d,
        label: new Date(d.day).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }),
      })));
      setTopProducts(topRes.data || []);
      setProductsStats(productsStatsRes.data);
      setSchedulerStatus(schedRes.data);

      // DASH-1: backend-ul calculeaza acum categoria cu cel mai mare ROI pe
      // TOATE categoriile cu cost declarat (null daca nu exista sau ROI <= 0).
      setBestCategory(reportsRes.data?.best_roi_categorie || null);
    } catch (error) {
      console.error("Error loading dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  const hasResaleData = productsStats && productsStats.produse_cu_pret_revanzare > 0;
  const roiMediu = productsStats?.roi_mediu ?? 0;
  let roiTone = "good";
  let roiSubtitle = "portofoliu excelent";
  if (roiMediu < 10) {
    roiTone = "bad";
    roiSubtitle = "necesită optimizare";
  } else if (roiMediu < 25) {
    roiTone = "warn";
    roiSubtitle = "portofoliu bun";
  }

  // DASH-1: status real din scheduler (era hardcodat pe verde).
  const schedRunning = schedulerStatus?.scheduler_running;
  const schedColor = schedRunning === true ? "#4ade80" : schedRunning === false ? "#f87171" : "var(--text-muted)";
  const schedLabel = schedRunning === true ? "SISTEM ACTIV" : schedRunning === false ? "SISTEM OPRIT" : "STATUS NECUNOSCUT";

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div
          style={{
            width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)",
            borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite",
          }}
        />
      </div>
    );
  }

  if (!stats) {
    return (
      <div style={{ maxWidth: "960px", margin: "0 auto" }}>
        <div className="glass-panel" style={{ padding: "1.5rem", textAlign: "center" }}>
          <p style={{ color: "var(--red-light)", fontSize: "12.5px", margin: "0 0 0.75rem" }}>
            Nu am putut încărca datele tabloului de bord. Verifică dacă serverul răspunde.
          </p>
          <button onClick={() => { setLoading(true); loadAll(); }} className="btn-cyan">
            Reîncearcă
          </button>
        </div>
      </div>
    );
  }

  const mods = stats?.modules || {};
  const new24h = (mods.radar?.new_24h ?? 0) + (mods.auto?.new_24h ?? 0) + (mods.imobiliare?.new_24h ?? 0);

  return (
    <div>
      <TopBar path={["TABLOU DE BORD"]} />

      <PageHeading
        title={`Bine ai venit, ${user?.full_name || user?.username || ""}`}
        subtitle={<>Piața arată bine azi — <Hl>{new24h} anunțuri noi</Hl> în ultimele 24h pe modulele tale.</>}
        meta={schedLabel}
      />

      {/* KPI-uri financiare */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(225px,1fr))", gap: "14px", marginTop: "16px" }}>
        <KpiCard
          idx="01"
          icon={Euro}
          label="Valoare vânzări"
          value={nf(stats?.sales_total_eur)}
          unit="EUR"
          chip={`${stats?.sales_count || 0} vânzări`}
          chipTone="cyan"
          note="înregistrate"
          href="/dashboard/sales"
        />
        <KpiCard
          idx="02"
          icon={TrendingUp}
          label="Profit estimat"
          value={hasResaleData ? nf(productsStats.profit_estimat_total) : "—"}
          unit={hasResaleData ? "EUR" : ""}
          chip={hasResaleData ? `${productsStats.produse_profitabile || 0} produse` : "fără date"}
          chipTone={hasResaleData ? "good" : "neutral"}
          note={hasResaleData ? "profitabile" : "adaugă prețuri de revânzare"}
          href="/dashboard/products"
        />
        <KpiCard
          idx="03"
          icon={ShoppingCart}
          label="Valoare inventar"
          value={nf(stats?.inventory_total_eur)}
          unit="EUR"
          chip={`${stats?.inventory_items_count || 0} articole`}
          note="cost achiziție"
          href="/dashboard/inventory"
        />
        <KpiCard
          idx="04"
          icon={Target}
          label="ROI mediu portofoliu"
          value={hasResaleData ? nf(roiMediu) : "—"}
          unit={hasResaleData ? "%" : ""}
          chip={hasResaleData ? roiSubtitle : "fără date"}
          chipTone={hasResaleData ? roiTone : "neutral"}
          note={hasResaleData ? "vs. pragul tău" : "adaugă prețuri de revânzare"}
          href="/dashboard/products"
        />
        {/* C.2 — afisat doar daca exista date din rapoarte */}
        {bestCategory && (
          <KpiCard
            idx="05"
            icon={Target}
            label="Cea mai profitabilă categorie"
            value={bestCategory.categorie}
            chip={`ROI ${Number(bestCategory.roi).toFixed(0)}%`}
            chipTone="good"
            note="ultimele 30 de zile"
            href="/dashboard/reports"
          />
        )}
      </div>

      {/* Grafic vânzări + coloana modulelor */}
      <div className="dash-split" style={{ marginTop: "14px" }}>
        <Panel
          title="Vânzări și profit"
          sub="Ultimele 30 zile · EUR"
          right={
            <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
              <LegendDot color="#22d3ee" label="VENIT" />
              <LegendDot color="#2563eb" label="PROFIT" />
            </div>
          }
        >
          <div style={{ width: "100%", height: 268 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries} margin={{ top: 10, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2563eb" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(94,140,255,.07)" strokeDasharray="4 6" vertical={false} />
                <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={false} />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#41547a", fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".1em", textTransform: "uppercase" }}
                  itemStyle={{ color: "var(--text-primary)" }}
                  cursor={{ stroke: "rgba(34,211,238,.45)", strokeDasharray: "3 3" }}
                  formatter={(v, name) => [`${Number(v).toFixed(2)} EUR`, name === "revenue_eur" ? "Venit" : "Profit"]}
                  labelFormatter={(label, payload) => {
                    const units = payload?.[0]?.payload?.units ?? 0;
                    return `${label} — ${units} buc. vândute`;
                  }}
                />
                <Area type="monotone" dataKey="revenue_eur" stroke="#22d3ee" strokeWidth={2} fill="url(#revGrad)" />
                <Area type="monotone" dataKey="profit_eur" stroke="#2563eb" strokeWidth={2} fill="url(#profitGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        {/* DASH-2: rândul modulelor de scanare — anunțuri noi în 24h per modul */}
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <ModuleCard
            icon={Radar}
            name="Radar Piață"
            value={mods.radar?.new_24h ?? 0}
            keywords={mods.radar?.active_keywords ?? 0}
            href="/dashboard/radar"
          />
          <ModuleCard
            icon={Car}
            name="Auto Anunțuri"
            value={mods.auto?.new_24h ?? 0}
            keywords={mods.auto?.active_keywords ?? 0}
            href="/dashboard/auto-listings/feed"
          />
          <ModuleCard
            icon={Building2}
            name="Imobiliare"
            value={mods.imobiliare?.new_24h ?? 0}
            keywords={mods.imobiliare?.active_keywords ?? 0}
            href="/dashboard/real-estate-monitor/feed"
          />
        </div>
      </div>

      {/* Catalog: produse, urmărite, alerte */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(225px,1fr))", gap: "14px", marginTop: "14px" }}>
        <KpiCard
          idx="06"
          icon={Package}
          label="Produse monitorizate"
          value={stats?.total_products || 0}
          note="în catalogul tău"
          href="/dashboard/products"
        />
        <KpiCard
          idx="07"
          icon={Eye}
          label="Produse urmărite"
          value={stats?.monitored_count || 0}
          note="urmărite de tine"
          href="/dashboard/tracked-products"
        />
        <KpiCard
          idx="08"
          icon={Bell}
          label="Alerte active"
          value={stats?.active_alerts || 0}
          note="alerte de preț configurate"
          href="/dashboard/alerts"
        />
      </div>

      {/* Top produse după venit */}
      {topProducts.length > 0 && (
        <Panel title="Top produse după venit" sub="Ultimele 30 zile · EUR" style={{ marginTop: "14px" }}>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topProducts} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="rgba(94,140,255,.07)" strokeDasharray="4 6" horizontal={false} />
                <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fill: "#7d90b5", fontSize: 10, fontFamily: "var(--font-sans)" }}
                  tickLine={false}
                  axisLine={false}
                  width={140}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#41547a", fontSize: "10px" }}
                  itemStyle={{ color: "var(--text-primary)" }}
                  cursor={{ fill: "rgba(34,211,238,.05)" }}
                  formatter={(v) => [`${Number(v).toFixed(2)} EUR`, "Venit"]}
                />
                {/* maxBarSize: cu putine produse bara ar umple toata banda si ar arata ca un bloc */}
                <Bar dataKey="revenue_eur" fill="#22d3ee" fillOpacity={0.75} radius={[0, 4, 4, 0]} maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      {/* Acțiuni rapide + Rezumat activitate */}
      <div className="dash-duo" style={{ marginTop: "14px" }}>
        <Panel
          title="Acțiuni rapide"
          right={<span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".14em", color: "var(--text-mono)" }}>SHORTCUTS</span>}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
            <QuickAction href="/dashboard/products" icon={Search} title="Caută produse" suffix="CATALOG" />
            <QuickAction href="/dashboard/inventory" icon={Boxes} title="Gestionează inventarul" suffix={`${stats?.inventory_items_count || 0} ART.`} />
            <QuickAction href="/dashboard/tracked-products" icon={Eye} title="Vezi produsele urmărite" suffix={`${stats?.monitored_count || 0} URM.`} />
            <QuickAction href="/dashboard/radar" icon={Radar} title="Anunțuri noi în feed" suffix={`${new24h} NOI`} />
          </div>
        </Panel>

        <Panel
          title="Rezumat activitate"
          right={
            <span style={{ display: "flex", alignItems: "center", gap: "6px", fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".1em", color: schedColor }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: schedColor, boxShadow: `0 0 7px ${schedColor}` }} />
              {schedLabel}
            </span>
          }
        >
          <div>
            <ActivityItem color="#fde047" label="Alerte declanșate" detail="alerte de preț atinse" value={stats?.triggered_alerts || 0} />
            <ActivityItem color="#22d3ee" label="Înregistrări de preț" detail="puncte de preț colectate" value={stats?.total_price_records || 0} />
            <ActivityItem color="#60a5fa" label="Produse monitorizate" detail="în catalogul tău" value={stats?.total_products || 0} />
            <ActivityItem color="#4ade80" label="Urmărite" detail="produse urmărite de tine" value={stats?.monitored_count || 0} isLast />
          </div>
        </Panel>
      </div>

      <style>{`
        .dash-split {
          display: grid;
          grid-template-columns: 1fr 316px;
          gap: 14px;
        }
        .dash-duo {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
        }
        @media (max-width: 1100px) {
          .dash-split, .dash-duo { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
