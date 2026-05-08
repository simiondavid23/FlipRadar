"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard, Search, Eye, Bell, LogOut,
  MessageCircle, Sparkles, FileText, FileBarChart, Shield,
  Heart, BellDot, Globe, FileSpreadsheet, Boxes, Receipt,
  ChevronDown, ChevronRight
} from "lucide-react";

const categories = [
  {
    id: "catalog",
    label: "Catalog",
    items: [
      { name: "Cauta Produse", href: "/dashboard/products", icon: Search },
      { name: "Web Scraping", href: "/dashboard/scraping", icon: Globe, flag: "can_use_scraping" },
      { name: "Favorite", href: "/dashboard/favorites", icon: Heart },
    ],
  },
  {
    id: "business",
    label: "Business",
    items: [
      { name: "Inventar", href: "/dashboard/inventory", icon: Boxes },
      { name: "Vanzari", href: "/dashboard/sales", icon: Receipt },
    ],
  },
  {
    id: "monitorizare",
    label: "Monitorizare",
    items: [
      { name: "Watchlist", href: "/dashboard/watchlist", icon: Eye },
      { name: "Alerte", href: "/dashboard/alerts", icon: Bell, flag: "can_use_alerts" },
      { name: "Notificari", href: "/dashboard/notifications", icon: BellDot },
    ],
  },
  {
    id: "ai",
    label: "AI",
    items: [
      { name: "AI Support", href: "/dashboard/support", icon: MessageCircle, flag: "can_use_ai" },
      { name: "Analiza AI", href: "/dashboard/ai-analyze", icon: Sparkles, flag: "can_use_ai" },
      { name: "Listing Generator", href: "/dashboard/ai-listing", icon: FileText, flag: "can_use_ai" },
      { name: "Raport AI", href: "/dashboard/ai-report", icon: FileBarChart, flag: "can_use_ai" },
    ],
  },
  {
    id: "date",
    label: "Date",
    items: [
      { name: "Import / Export", href: "/dashboard/import-export", icon: FileSpreadsheet, flag: "can_use_import_export" },
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
  const [openCategory, setOpenCategory] = useState(() => findInitiallyOpenCategory(pathname));

  const toggleCategory = (id) => {
    setOpenCategory((prev) => (prev === id ? null : id));
  };

  const dashboardActive = pathname === "/dashboard";

  return (
    <div
      style={{
        position: "fixed", left: 0, top: 0, bottom: 0, width: "240px",
        backgroundColor: "var(--bg-card)", borderRight: "1px solid var(--border-color)",
        display: "flex", flexDirection: "column", zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border-color)" }}>
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
            backgroundColor: dashboardActive ? "#2563eb" : "transparent",
            color: dashboardActive ? "white" : "#94a3b8",
            marginBottom: "0.5rem",
            transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => { if (!dashboardActive) { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "white"; }}}
          onMouseLeave={(e) => { if (!dashboardActive) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}}
        >
          <LayoutDashboard style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          <span>Dashboard</span>
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
                  color: hasActiveChild ? "white" : "#64748b",
                  backgroundColor: "transparent", border: "none", cursor: "pointer",
                  transition: "color 0.15s ease",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "white"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = hasActiveChild ? "white" : "#64748b"; }}
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
                          backgroundColor: isActive ? "#2563eb" : "transparent",
                          color: isActive ? "white" : "#94a3b8",
                          transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "white"; }}}
                        onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}}
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
            <span>Admin Panel</span>
          </Link>
        </div>
      )}

      <div style={{ padding: "0.75rem", borderTop: "1px solid var(--border-color)" }}>
        {user && (
          <div style={{ padding: "0.375rem 0.875rem", marginBottom: "0.25rem" }}>
            <p style={{ fontSize: "0.8125rem", fontWeight: 500, color: "white", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.full_name || user.username}
            </p>
            <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.email}
            </p>
          </div>
        )}
        <button onClick={logout}
          style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.875rem", borderRadius: "0.625rem",
            fontSize: "0.8125rem", fontWeight: 500, color: "#94a3b8", backgroundColor: "transparent",
            border: "none", cursor: "pointer", width: "100%" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(239,68,68,0.1)"; e.currentTarget.style.color = "#f87171"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
        >
          <LogOut style={{ width: "16px", height: "16px", flexShrink: 0 }} />
          <span>Deconectare</span>
        </button>
      </div>
    </div>
  );
}
