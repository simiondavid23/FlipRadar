"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import {
  LayoutDashboard, Search, Eye, Bell, LogOut,
  MessageCircle, Sparkles, FileText, FileBarChart, Shield,
  Heart, BellDot, Globe, FileSpreadsheet, Boxes, Receipt,
  ChevronDown, ChevronRight, Sun, Moon, BarChart2,
  Radar, Target, ShieldOff, Settings, MessageSquare
} from "lucide-react";

// Sidebar-ul ramane mereu dark — pattern UX standard (GitHub, VS Code, Notion).
// Culorile sunt hardcodate pentru ca CSS variables se schimba in light mode
// pe restul aplicatiei, dar sidebar-ul ramane intunecat indiferent de tema.
const SIDEBAR_BG = "#1e293b";
const SIDEBAR_BORDER = "#334155";
const TEXT_PRIMARY = "#f8fafc";
const TEXT_SECONDARY = "#94a3b8";
const TEXT_MUTED = "#64748b";
const HOVER_BG = "rgba(255,255,255,0.05)";
const ACTIVE_BG = "#2563eb";

const categories = [
  {
    id: "catalog",
    label: "Catalog",
    items: [
      { name: "Descopera Oportunitati", href: "/dashboard/products", icon: Search },
      { name: "Scanare Magazine", href: "/dashboard/scraping", icon: Globe, flag: "can_use_scraping" },
      { name: "Oportunitati Salvate", href: "/dashboard/favorites", icon: Heart },
    ],
  },
  {
    id: "business",
    label: "Business",
    items: [
      { name: "Inventar", href: "/dashboard/inventory", icon: Boxes },
      { name: "Registru Vanzari", href: "/dashboard/sales", icon: Receipt },
      { name: "Statistici & Profit", href: "/dashboard/reports", icon: BarChart2 },
    ],
  },
  {
    id: "monitorizare",
    label: "Monitorizare",
    items: [
      { name: "Radar Preturi", href: "/dashboard/watchlist", icon: Eye },
      { name: "Alerte Pret", href: "/dashboard/alerts", icon: Bell, flag: "can_use_alerts" },
      { name: "Centru Notificari", href: "/dashboard/notifications", icon: BellDot },
    ],
  },
  {
    id: "radar",
    label: "Radar Piata",
    items: [
      { name: "Feed Anunturi", href: "/dashboard/radar", icon: Radar },
      { name: "Keyword-uri", href: "/dashboard/radar/keywords", icon: Target },
      { name: "Sabloane Mesaje", href: "/dashboard/radar/templates", icon: MessageSquare },
      { name: "Vanzatori Blocati", href: "/dashboard/radar/blocked", icon: ShieldOff },
      { name: "Setari Radar", href: "/dashboard/radar/settings", icon: Settings },
    ],
  },
  {
    id: "ai",
    label: "AI",
    items: [
      { name: "Asistent AI", href: "/dashboard/support", icon: MessageCircle, flag: "can_use_ai" },
      { name: "Consilier AI", href: "/dashboard/ai-analyze", icon: Sparkles, flag: "can_use_ai" },
      { name: "Creator Anunturi", href: "/dashboard/ai-listing", icon: FileText, flag: "can_use_ai" },
      { name: "Raport Piata", href: "/dashboard/ai-report", icon: FileBarChart, flag: "can_use_ai" },
    ],
  },
  {
    id: "date",
    label: "Date",
    items: [
      { name: "Gestionare Date", href: "/dashboard/import-export", icon: FileSpreadsheet, flag: "can_use_import_export" },
    ],
  },
];

function filterItemsForUser(items, user) {
  if (!user) return items;
  return items.filter((it) => {
    if (!it.flag) return true;
    return user[it.flag] !== false;
  });
}

function findInitiallyOpenCategory(pathname) {
  for (const cat of categories) {
    if (cat.items.some((it) => it.href === pathname)) return cat.id;
  }
  return null;
}

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [openCategory, setOpenCategory] = useState(() => findInitiallyOpenCategory(pathname));

  const toggleCategory = (id) => {
    setOpenCategory((prev) => (prev === id ? null : id));
  };

  const dashboardActive = pathname === "/dashboard";
  const isLight = theme === "light";

  return (
    <div
      style={{
        position: "fixed", left: 0, top: 0, bottom: 0, width: "240px",
        backgroundColor: SIDEBAR_BG, borderRight: `1px solid ${SIDEBAR_BORDER}`,
        display: "flex", flexDirection: "column", zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", padding: "1.25rem 1.5rem", borderBottom: `1px solid ${SIDEBAR_BORDER}` }}>
        <Image
          src="/flipradar-logo.svg"
          alt="FlipRadar"
          width={180}
          height={39}
          priority
          style={{ height: "auto" }}
        />
      </div>

      <nav style={{ flex: 1, padding: "0.75rem", overflowY: "auto" }}>
        <Link href="/dashboard"
          style={{
            display: "flex", alignItems: "center", gap: "0.75rem",
            padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
            fontSize: "0.8125rem", fontWeight: 500, textDecoration: "none",
            backgroundColor: dashboardActive ? ACTIVE_BG : "transparent",
            color: dashboardActive ? "white" : TEXT_SECONDARY,
            marginBottom: "0.5rem",
            transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => { if (!dashboardActive) { e.currentTarget.style.backgroundColor = HOVER_BG; e.currentTarget.style.color = TEXT_PRIMARY; }}}
          onMouseLeave={(e) => { if (!dashboardActive) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = TEXT_SECONDARY; }}}
        >
          <LayoutDashboard style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          <span>Tablou de Bord</span>
        </Link>

        {categories.map((cat) => {
          const visibleItems = filterItemsForUser(cat.items, user);
          if (visibleItems.length === 0) return null;
          const isOpen = openCategory === cat.id;
          const hasActiveChild = visibleItems.some((it) => it.href === pathname);
          return (
            <div key={cat.id} style={{ marginBottom: "0.25rem" }}>
              <button
                onClick={() => toggleCategory(cat.id)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                  gap: "0.5rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
                  fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: hasActiveChild ? TEXT_PRIMARY : TEXT_MUTED,
                  backgroundColor: "transparent", border: "none", cursor: "pointer",
                  transition: "color 0.15s ease",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = TEXT_PRIMARY; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = hasActiveChild ? TEXT_PRIMARY : TEXT_MUTED; }}
              >
                <span>{cat.label}</span>
                {isOpen ? (
                  <ChevronDown style={{ width: "14px", height: "14px" }} />
                ) : (
                  <ChevronRight style={{ width: "14px", height: "14px" }} />
                )}
              </button>

              {isOpen && (
                <div style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "2px" }}>
                  {visibleItems.map((item) => {
                    const isActive = pathname === item.href;
                    const Icon = item.icon;
                    return (
                      <Link key={item.href} href={item.href}
                        style={{
                          display: "flex", alignItems: "center", gap: "0.75rem",
                          padding: "0.5rem 0.875rem 0.5rem 1.75rem", borderRadius: "0.625rem",
                          fontSize: "0.8125rem", fontWeight: 500, textDecoration: "none",
                          backgroundColor: isActive ? ACTIVE_BG : "transparent",
                          color: isActive ? "white" : TEXT_SECONDARY,
                          transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.backgroundColor = HOVER_BG; e.currentTarget.style.color = TEXT_PRIMARY; }}}
                        onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = TEXT_SECONDARY; }}}
                      >
                        <Icon style={{ width: "16px", height: "16px", flexShrink: 0 }} />
                        <span>{item.name}</span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {user?.is_admin && (
        <div style={{ padding: "0 0.75rem 0.5rem" }}>
          <Link href="/admin"
            style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
              fontSize: "0.8125rem", fontWeight: 500, textDecoration: "none",
              backgroundColor: "rgba(220,38,38,0.1)", color: "#f87171", border: "1px solid rgba(220,38,38,0.2)" }}>
            <Shield style={{ width: "16px", height: "16px", flexShrink: 0 }} />
            <span>Panou Administrare</span>
          </Link>
        </div>
      )}

      <div style={{ padding: "0.75rem", borderTop: `1px solid ${SIDEBAR_BORDER}` }}>
        {user && (
          <div style={{ padding: "0.375rem 0.875rem", marginBottom: "0.25rem" }}>
            <p style={{ fontSize: "0.8125rem", fontWeight: 500, color: TEXT_PRIMARY, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.full_name || user.username}
            </p>
            <p style={{ fontSize: "0.6875rem", color: TEXT_SECONDARY, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.email}
            </p>
          </div>
        )}
        {/* FlipRadar — ITEM 16: link catre pagina de setari (alerte Flash Deal) */}
        <Link href="/dashboard/settings"
          style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
            fontSize: "0.8125rem", fontWeight: 500, textDecoration: "none",
            backgroundColor: pathname === "/dashboard/settings" ? ACTIVE_BG : "transparent",
            color: pathname === "/dashboard/settings" ? "white" : TEXT_SECONDARY,
            width: "100%", marginBottom: "0.25rem", transition: "all 0.15s ease" }}
          onMouseEnter={(e) => { if (pathname !== "/dashboard/settings") { e.currentTarget.style.backgroundColor = HOVER_BG; e.currentTarget.style.color = TEXT_PRIMARY; } }}
          onMouseLeave={(e) => { if (pathname !== "/dashboard/settings") { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = TEXT_SECONDARY; } }}
        >
          <Settings style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          <span>Setari</span>
        </Link>
        <button onClick={toggleTheme}
          title={isLight ? "Comuta la tema intunecata" : "Comuta la tema luminoasa"}
          style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
            fontSize: "0.8125rem", fontWeight: 500, color: TEXT_SECONDARY, backgroundColor: "transparent",
            border: "none", cursor: "pointer", width: "100%", marginBottom: "0.25rem", transition: "all 0.15s ease" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = HOVER_BG; e.currentTarget.style.color = TEXT_PRIMARY; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = TEXT_SECONDARY; }}
        >
          {isLight ? (
            <Moon style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          ) : (
            <Sun style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          )}
          <span>{isLight ? "Tema intunecata" : "Tema luminoasa"}</span>
        </button>
        <button onClick={logout}
          style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
            fontSize: "0.8125rem", fontWeight: 500, color: TEXT_SECONDARY, backgroundColor: "transparent",
            border: "none", cursor: "pointer", width: "100%" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(239,68,68,0.1)"; e.currentTarget.style.color = "#f87171"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = TEXT_SECONDARY; }}
        >
          <LogOut style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          <span>Deconectare</span>
        </button>
      </div>
    </div>
  );
}
