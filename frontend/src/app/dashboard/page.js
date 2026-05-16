"use client";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { dashboardAPI, productsAPI } from "@/lib/api";
import Link from "next/link";
import {
  Package, Eye, Bell, TrendingUp, AlertTriangle, Database,
  Search, Boxes, ArrowRight, CalendarDays, ShoppingCart, Euro, Target
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar,
} from "recharts";

function StatCard({ title, value, icon: Icon, color, bgGlow, subtitle, href, valueColor, valueSize }) {
  const inner = (
    <>
      {/* Subtle glow */}
      <div
        style={{
          position: "absolute",
          top: "-2rem",
          right: "-2rem",
          width: "6rem",
          height: "6rem",
          borderRadius: "50%",
          opacity: 0.15,
          background: bgGlow,
        }}
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
          <div
            style={{
              padding: "0.5rem",
              borderRadius: "0.625rem",
              backgroundColor: color,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon style={{ width: "18px", height: "18px", color: "var(--text-primary)" }} />
          </div>
          <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-secondary)", margin: 0 }}>{title}</p>
        </div>
        <p style={{ fontSize: valueSize || "2.25rem", fontWeight: 700, color: valueColor || "var(--text-primary)", lineHeight: 1, margin: 0 }}>{value}</p>
        {subtitle && (
          <p style={{ fontSize: "0.75rem", marginTop: "0.5rem", color: "var(--text-muted)", margin: "0.5rem 0 0" }}>{subtitle}</p>
        )}
      </div>
    </>
  );

  const baseStyle = {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border-color)",
    borderRadius: "1rem",
    padding: "1.5rem",
    position: "relative",
    overflow: "hidden",
  };

  if (!href) {
    return <div style={baseStyle}>{inner}</div>;
  }

  return (
    <Link
      href={href}
      style={{
        ...baseStyle,
        display: "block",
        textDecoration: "none",
        color: "inherit",
        cursor: "pointer",
        transition: "border-color 0.15s ease, transform 0.15s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color;
        e.currentTarget.style.transform = "translateY(-2px)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border-color)";
        e.currentTarget.style.transform = "translateY(0)";
      }}
    >
      {inner}
    </Link>
  );
}

function QuickAction({ href, icon: Icon, title, description, color }) {
  return (
    <Link
      href={href}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "1rem",
        padding: "0.875rem 1rem",
        borderRadius: "0.75rem",
        border: "1px solid var(--border-color)",
        textDecoration: "none",
        transition: "all 0.15s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)";
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = "transparent";
        e.currentTarget.style.borderColor = "var(--border-color)";
      }}
    >
      <div
        style={{
          padding: "0.625rem",
          borderRadius: "0.625rem",
          backgroundColor: color,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon style={{ width: "18px", height: "18px", color: "var(--text-primary)" }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontWeight: 500, color: "var(--text-primary)", fontSize: "0.875rem" }}>{title}</p>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{description}</p>
      </div>
      <ArrowRight style={{ width: "16px", height: "16px", color: "var(--text-muted)", flexShrink: 0 }} />
    </Link>
  );
}

function ActivityItem({ icon: Icon, label, value, color, isLast }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 0",
        borderBottom: isLast ? "none" : "1px solid var(--border-color)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
        <Icon style={{ width: "15px", height: "15px", color: color }} />
        <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{label}</span>
      </div>
      <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [productsStats, setProductsStats] = useState(null);
  const [timeseries, setTimeseries] = useState([]);
  const [topProducts, setTopProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      const [statsRes, tsRes, topRes, productsStatsRes] = await Promise.all([
        dashboardAPI.getStats(),
        dashboardAPI.getSalesTimeseries(30),
        dashboardAPI.getTopProducts(5),
        productsAPI.getStats().catch(() => ({ data: null })),
      ]);
      setStats(statsRes.data);
      setTimeseries((tsRes.data?.data || []).map((d) => ({
        ...d,
        label: new Date(d.day).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }),
      })));
      setTopProducts(topRes.data || []);
      setProductsStats(productsStatsRes.data);
    } catch (error) {
      console.error("Error loading dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  const hasResaleData = productsStats && productsStats.produse_cu_pret_revanzare > 0;
  const roiMediu = productsStats?.roi_mediu ?? 0;
  let roiColor = "#4ade80";
  let roiBgGlow = "radial-gradient(circle, rgba(34,197,94,0.6), transparent)";
  let roiSubtitle = "Portofoliu excelent";
  if (roiMediu < 10) {
    roiColor = "#f87171";
    roiBgGlow = "radial-gradient(circle, rgba(239,68,68,0.6), transparent)";
    roiSubtitle = "Necesita optimizare";
  } else if (roiMediu < 25) {
    roiColor = "#facc15";
    roiBgGlow = "radial-gradient(circle, rgba(250,204,21,0.6), transparent)";
    roiSubtitle = "Portofoliu bun";
  }

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div
          style={{
            width: "2.5rem",
            height: "2.5rem",
            border: "4px solid #2563eb",
            borderTopColor: "transparent",
            borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }}
        />
      </div>
    );
  }

  const today = new Date();
  const dateStr = today.toLocaleDateString("ro-RO", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "2rem" }}>
        <div>
          <h1 style={{ fontSize: "1.625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Bine ai venit, {user?.full_name || user?.username}! 👋
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.375rem", fontSize: "0.875rem" }}>
            Iata o privire de ansamblu asupra activitatii tale.
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 0.875rem",
            borderRadius: "0.625rem",
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
          }}
        >
          <CalendarDays style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
          <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>{dateStr}</span>
        </div>
      </div>

      {/* Main Stats - 3 columns */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <StatCard
          title="Produse monitorizate"
          value={stats?.total_products || 0}
          icon={Package}
          color="#2563eb"
          bgGlow="radial-gradient(circle, rgba(37,99,235,0.5), transparent)"
          subtitle="Total produse in baza de date"
          href="/dashboard/products"
        />
        <StatCard
          title="Produse in Watchlist"
          value={stats?.watchlist_count || 0}
          icon={Eye}
          color="#9333ea"
          bgGlow="radial-gradient(circle, rgba(147,51,234,0.5), transparent)"
          subtitle="Produse urmarite de tine"
          href="/dashboard/watchlist"
        />
        <StatCard
          title="Alerte active"
          value={stats?.active_alerts || 0}
          icon={Bell}
          color="#16a34a"
          bgGlow="radial-gradient(circle, rgba(22,163,74,0.5), transparent)"
          subtitle="Alerte de pret configurate"
          href="/dashboard/alerts"
        />
      </div>

      {/* Purchase Summary Row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <StatCard
          title="Volum total produse"
          value={`${(stats?.inventory_total_eur || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR`}
          icon={ShoppingCart}
          color="#16a34a"
          bgGlow="radial-gradient(circle, rgba(34,197,94,0.6), transparent)"
          subtitle={`${stats?.inventory_items_count || 0} articole in inventar`}
          href="/dashboard/inventory"
          valueColor="#4ade80"
          valueSize="2rem"
        />
        <StatCard
          title="Valoare vanzari"
          value={`${(stats?.sales_total_eur || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR`}
          icon={Euro}
          color="#9333ea"
          bgGlow="radial-gradient(circle, rgba(147,51,234,0.6), transparent)"
          subtitle={`${stats?.sales_count || 0} vanzari inregistrate`}
          href="/dashboard/sales"
          valueColor="#a78bfa"
          valueSize="2rem"
        />
      </div>

      {/* Profitability Summary Row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        {hasResaleData ? (
          <StatCard
            title="Profit estimat total"
            value={`${Number(productsStats.profit_estimat_total || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })}`}
            icon={TrendingUp}
            color="#16a34a"
            bgGlow="radial-gradient(circle, rgba(34,197,94,0.6), transparent)"
            subtitle={`${productsStats.produse_profitabile || 0} produse profitabile`}
            valueColor="#4ade80"
            valueSize="2rem"
          />
        ) : (
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px dashed var(--border-color)",
              borderRadius: "1rem",
              padding: "1.5rem",
              display: "flex", alignItems: "center", gap: "0.75rem",
            }}
          >
            <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#16a34a", display: "flex" }}>
              <TrendingUp style={{ width: "18px", height: "18px", color: "var(--text-primary)" }} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-secondary)", margin: 0 }}>Profit estimat total</p>
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.5rem 0 0", lineHeight: 1.5 }}>
                Adauga preturi de revanzare pentru a vedea profitabilitatea
              </p>
              <Link href="/dashboard/products" style={{
                display: "inline-block", marginTop: "0.5rem",
                fontSize: "0.75rem", color: "var(--blue-light)", textDecoration: "none", fontWeight: 500,
              }}>
                Mergi la produse →
              </Link>
            </div>
          </div>
        )}

        {hasResaleData ? (
          <StatCard
            title="ROI mediu portofoliu"
            value={`${Number(roiMediu).toFixed(2)}%`}
            icon={Target}
            color={roiColor}
            bgGlow={roiBgGlow}
            subtitle={roiSubtitle}
            valueColor={roiColor}
            valueSize="2rem"
          />
        ) : (
          <div
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px dashed var(--border-color)",
              borderRadius: "1rem",
              padding: "1.5rem",
              display: "flex", alignItems: "center", gap: "0.75rem",
            }}
          >
            <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#facc15", display: "flex" }}>
              <Target style={{ width: "18px", height: "18px", color: "var(--text-primary)" }} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-secondary)", margin: 0 }}>ROI mediu portofoliu</p>
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.5rem 0 0", lineHeight: 1.5 }}>
                Adauga preturi de revanzare pentru a vedea profitabilitatea
              </p>
              <Link href="/dashboard/products" style={{
                display: "inline-block", marginTop: "0.5rem",
                fontSize: "0.75rem", color: "var(--blue-light)", textDecoration: "none", fontWeight: 500,
              }}>
                Mergi la produse →
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Sales chart (last 30 days) */}
      <div
        style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "1rem",
          padding: "1.5rem",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Vanzari si profit (ultimele 30 de zile)</h2>
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Valori in EUR</span>
        </div>
        <div style={{ width: "100%", height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={timeseries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563eb" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                labelStyle={{ color: "var(--text-secondary)" }}
                itemStyle={{ color: "var(--text-primary)" }}
                formatter={(v, name) => [`${Number(v).toFixed(2)} EUR`, name === "revenue_eur" ? "Venit" : "Profit"]}
              />
              <Area type="monotone" dataKey="revenue_eur" stroke="#3b82f6" strokeWidth={2} fill="url(#revGrad)" />
              <Area type="monotone" dataKey="profit_eur" stroke="#22c55e" strokeWidth={2} fill="url(#profitGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top products chart */}
      {topProducts.length > 0 && (
        <div
          style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "1rem",
            padding: "1.5rem",
            marginBottom: "1.5rem",
          }}
        >
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>Top produse dupa venit</h2>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topProducts} layout="vertical" margin={{ top: 5, right: 16, left: 16, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false} width={140} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                  labelStyle={{ color: "var(--text-secondary)" }}
                  itemStyle={{ color: "var(--text-primary)" }}
                  formatter={(v) => [`${Number(v).toFixed(2)} EUR`, "Venit"]}
                />
                <Bar dataKey="revenue_eur" fill="#9333ea" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Two columns: Quick Actions + Activity Summary */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1rem",
        }}
      >
        {/* Quick Actions */}
        <div
          style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "1rem",
            padding: "1.5rem",
          }}
        >
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>Actiuni rapide</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <QuickAction
              href="/dashboard/products"
              icon={Search}
              title="Cauta produse"
              description="Gaseste produse profitabile"
              color="#2563eb"
            />
            <QuickAction
              href="/dashboard/inventory"
              icon={Boxes}
              title="Inventar"
              description="Gestioneaza produsele pe stoc"
              color="#16a34a"
            />
            <QuickAction
              href="/dashboard/watchlist"
              icon={Eye}
              title="Watchlist"
              description="Vezi produsele urmarite"
              color="#9333ea"
            />
          </div>
        </div>

        {/* Activity Summary */}
        <div
          style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "1rem",
            padding: "1.5rem",
          }}
        >
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>Rezumat activitate</h2>
          <div>
            <ActivityItem icon={AlertTriangle} label="Alerte declansate" value={stats?.triggered_alerts || 0} color="#facc15" />
            <ActivityItem icon={Database} label="Inregistrari de pret" value={stats?.total_price_records || 0} color="#22d3ee" />
            <ActivityItem icon={Package} label="Produse monitorizate" value={stats?.total_products || 0} color="#60a5fa" />
            <ActivityItem icon={Eye} label="In watchlist" value={stats?.watchlist_count || 0} color="#a78bfa" />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: "0.75rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                <TrendingUp style={{ width: "15px", height: "15px", color: "#34d399" }} />
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Status sistem</span>
              </div>
              <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "#34d399" }}>● Activ</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
