"use client";
import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard, Search, Bell, LogOut,
  Heart, Globe, Boxes, Receipt,
  BarChart2, Radar, Target, Bookmark, Settings,
  Calculator, Rss, Tag, Activity, Percent
} from "lucide-react";

// Sidebar-ul "Prism Obsidian": panou flotant din sticla, nav plat cu etichete de
// grup mono, item activ pill cu punct cyan + index. Culorile sunt hardcodate
// pentru ca panoul ramane intunecat indiferent de restul temei.
const ICON = { width: 14, height: 14, strokeWidth: 1.8, flexShrink: 0 };

const categories = [
  {
    id: "catalog",
    label: "Catalog",
    items: [
      { name: "Descoperă Oportunități", href: "/dashboard/products", icon: Search },
      { name: "Deal-uri", href: "/dashboard/deals", icon: Percent },
      { name: "Scanare Magazine", href: "/dashboard/scraping", icon: Globe, flag: "can_use_scraping" },
      { name: "Produse Urmărite", href: "/dashboard/tracked-products", icon: Heart },
    ],
  },
  {
    id: "radar",
    label: "Radar Piața",
    items: [
      { name: "Feed Anunțuri", href: "/dashboard/radar", icon: Radar },
      { name: "Keyword-uri", href: "/dashboard/radar/keywords", icon: Target },
      { name: "Salvate & Ignorate", href: "/dashboard/radar/saved", icon: Bookmark },
    ],
  },
  {
    id: "auto_lots",
    label: "Loturi Automobile — În lucru",
    items: [
      { name: "Feed Loturi", href: "/dashboard/auto/lots/feed", icon: Rss },
      { name: "Keyword-uri", href: "/dashboard/auto/lots/keywords", icon: Tag },
      { name: "Cauta Loturi", href: "/dashboard/auto/lots/search", icon: Search },
      { name: "Loturi Salvate", href: "/dashboard/auto/lots/saved", icon: Heart },
      { name: "Calculator Import", href: "/dashboard/auto/lots/calculator", icon: Calculator },
    ],
  },
  {
    id: "auto_listings",
    label: "Auto Anunțuri",
    items: [
      { name: "Feed Anunțuri", href: "/dashboard/auto-listings/feed", icon: Rss },
      { name: "Keyword-uri", href: "/dashboard/auto-listings/keywords", icon: Tag },
      { name: "Salvate & Ignorate", href: "/dashboard/auto-listings/saved", icon: Bookmark },
    ],
  },
  {
    id: "real_estate",
    label: "Imobiliare",
    items: [
      { name: "Feed Anunțuri", href: "/dashboard/real-estate-monitor/feed", icon: Rss },
      { name: "Keyword-uri", href: "/dashboard/real-estate-monitor/keywords", icon: Tag },
      { name: "Salvate & Ignorate", href: "/dashboard/real-estate-monitor/saved", icon: Bookmark },
    ],
  },
  {
    id: "gestiune",
    label: "Gestiune",
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
      { name: "Jurnale Live", href: "/dashboard/logs", icon: Activity },
      { name: "Alerte Pret", href: "/dashboard/alerts", icon: Bell, flag: "can_use_alerts" },
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

// Diacriticele nu trebuie sa strice cautarea in nav ("anunturi" gaseste "Anunțuri").
// NFD desparte si virgula de sub ț/ș (U+0326), deci intervalul acopera ambele familii.
const norm = (s) =>
  String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

function initialsOf(user) {
  const src = user?.full_name || user?.username || user?.email || "";
  const parts = src.trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "FR";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [query, setQuery] = useState("");

  // Indexul mono din dreapta itemului activ = pozitia paginii in nav (01, 02, …).
  const { groups, indexOf } = useMemo(() => {
    const idx = { "/dashboard": 1 };
    let n = 1;
    const gs = categories
      .map((cat) => ({ ...cat, items: filterItemsForUser(cat.items, user) }))
      .filter((cat) => cat.items.length > 0);
    for (const cat of gs) {
      for (const it of cat.items) idx[it.href] = ++n;
    }
    return { groups: gs, indexOf: idx };
  }, [user]);

  const q = norm(query);
  const visibleGroups = q
    ? groups
        .map((cat) => ({ ...cat, items: cat.items.filter((it) => norm(it.name).includes(q) || norm(cat.label).includes(q)) }))
        .filter((cat) => cat.items.length > 0)
    : groups;

  const dashboardActive = pathname === "/dashboard";
  const showDashboardLink = !q || norm("Tablou de Bord").includes(q);
  const pad = (n) => String(n).padStart(2, "0");

  return (
    <aside className="app-sidebar">
      {/* Logo + wordmark */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "18px 18px 14px" }}>
        <Image
          src="/flipradar-icon.svg"
          alt="FlipRadar"
          width={30}
          height={30}
          priority
          style={{ borderRadius: "8px", boxShadow: "0 4px 14px rgba(34,211,238,.3)" }}
        />
        <div>
          <div style={{ fontSize: "14.5px", fontWeight: 700, letterSpacing: "-.2px", color: "#e6edf9" }}>
            Flip<span style={{ color: "#7ee7f8" }}>Radar</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "7.5px", letterSpacing: ".22em", color: "#38bdf8", marginTop: "1px" }}>
            PRODUCT RESEARCH
          </div>
        </div>
      </div>

      {/* Cautare in nav */}
      <label
        style={{
          margin: "0 12px 4px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 12px",
          borderRadius: "99px",
          background:
            "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.1) 50%, transparent) border-box",
          border: "1px solid transparent",
          cursor: "text",
        }}
      >
        <Search style={{ width: "13px", height: "13px", color: "#54648a", flexShrink: 0 }} strokeWidth={1.8} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Caută…"
          aria-label="Caută în meniu"
          style={{
            flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none",
            color: "#e6edf9", fontSize: "11.5px", fontFamily: "var(--font-sans)", padding: 0,
          }}
        />
        <span
          style={{
            fontFamily: "var(--font-mono)", fontSize: "8px", color: "#41547a",
            border: "1px solid rgba(94,140,255,.18)", borderRadius: "5px", padding: "1px 5px", flexShrink: 0,
          }}
        >
          ⌘K
        </span>
      </label>

      <nav style={{ flex: 1, padding: "8px 10px 0", overflowY: "auto" }}>
        {showDashboardLink && (
          <Link href="/dashboard" className={`pill-nav-item${dashboardActive ? " active" : ""}`}>
            {dashboardActive ? <span className="pill-nav-dot" /> : <LayoutDashboard style={ICON} />}
            <span>Tablou de Bord</span>
            {dashboardActive && <span className="pill-nav-idx">{pad(indexOf["/dashboard"])}</span>}
          </Link>
        )}

        {visibleGroups.map((cat) => (
          <div key={cat.id} style={{ marginTop: "12px" }}>
            <div
              style={{
                fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".18em",
                textTransform: "uppercase", color: "#41547a", padding: "0 13px 5px",
              }}
            >
              {cat.label}
            </div>
            {cat.items.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} className={`pill-nav-item${isActive ? " active" : ""}`}>
                  {isActive ? <span className="pill-nav-dot" /> : <Icon style={ICON} />}
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.name}</span>
                  {isActive && <span className="pill-nav-idx">{pad(indexOf[item.href])}</span>}
                </Link>
              );
            })}
          </div>
        ))}
        <div style={{ height: "10px" }} />
      </nav>

      {/* Footer — cont + setari + logout */}
      <div style={{ padding: "12px", borderTop: "1px solid rgba(94,140,255,.1)", display: "flex", alignItems: "center", gap: "10px" }}>
        <div
          style={{
            width: "32px", height: "32px", borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#2563eb)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", fontWeight: 700,
            color: "#04070e", flexShrink: 0,
          }}
        >
          {initialsOf(user)}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "#e6edf9", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.full_name || user?.username || "Utilizator"}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".08em", color: "#41547a" }}>
            CONT PRO
          </div>
        </div>
        <Link href="/dashboard/settings" aria-label="Setari" title="Setari" className="sidebar-foot-btn">
          <Settings style={{ width: "15px", height: "15px" }} strokeWidth={1.8} />
        </Link>
        <button onClick={logout} aria-label="Deconectare" title="Deconectare" className="sidebar-foot-btn danger">
          <LogOut style={{ width: "15px", height: "15px" }} strokeWidth={1.8} />
        </button>
      </div>

      <style>{`
        .app-sidebar {
          position: fixed;
          top: 18px;
          left: 18px;
          bottom: 18px;
          z-index: 50;
          width: 238px;
          border-radius: 20px;
          background: rgba(10,17,32,.6);
          backdrop-filter: blur(24px);
          border: 1px solid rgba(34,211,238,.13);
          box-shadow: inset 0 1px 0 rgba(255,255,255,.06), 0 20px 50px rgba(0,0,0,.45);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .sidebar-foot-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          background: none;
          border: none;
          padding: 0;
          color: #5b6b8c;
          cursor: pointer;
          transition: color 0.15s ease;
        }
        .sidebar-foot-btn:hover { color: #7ee7f8; }
        .sidebar-foot-btn.danger:hover { color: #f87171; }
      `}</style>
    </aside>
  );
}
