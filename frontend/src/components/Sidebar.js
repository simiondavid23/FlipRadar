"use client";
import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { LayoutDashboard, Search, LogOut, Settings } from "lucide-react";
import { DASHBOARD_HREF, visibleModules, findModuleForPath } from "@/lib/navigation";

// Sidebar-ul "Prism Obsidian": panou flotant din sticla, nav plat cu un item per
// MODUL, item activ pill cu punct cyan + index. Paginile modulului se vad in
// ModuleTabs, deasupra continutului. Culorile sunt hardcodate pentru ca panoul
// ramane intunecat indiferent de restul temei.
const ICON = { width: 14, height: 14, strokeWidth: 1.8, flexShrink: 0 };

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

  // Indexul mono din dreapta itemului activ = pozitia modulului in nav (01, 02, …),
  // cu 01 rezervat pentru Tablou de Bord.
  const { modules, indexOf } = useMemo(() => {
    const ms = visibleModules(user);
    const idx = { [DASHBOARD_HREF]: 1 };
    let n = 1;
    for (const m of ms) idx[m.id] = ++n;
    return { modules: ms, indexOf: idx };
  }, [user]);

  const activeModuleId = findModuleForPath(pathname, user)?.module.id ?? null;

  // Cautarea coboara la nivel de PAGINA: doar etichetele de modul n-ar da destul context.
  const q = norm(query);
  const results = q
    ? modules.flatMap((m) =>
        m.pages
          .filter((p) => norm(p.name).includes(q) || norm(m.label).includes(q))
          .map((p) => ({ module: m, page: p }))
      )
    : [];

  const dashboardActive = pathname === DASHBOARD_HREF;
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
          <Link href={DASHBOARD_HREF} className={`pill-nav-item${dashboardActive ? " active" : ""}`}>
            {dashboardActive ? <span className="pill-nav-dot" /> : <LayoutDashboard style={ICON} />}
            <span>Tablou de Bord</span>
            {dashboardActive && <span className="pill-nav-idx">{pad(indexOf[DASHBOARD_HREF])}</span>}
          </Link>
        )}

        <div style={{ marginTop: "12px" }}>
          {q
            ? results.map(({ module, page }) => {
                const Icon = page.icon;
                return (
                  <Link key={`${module.id}:${page.href}`} href={page.href} className="pill-nav-item">
                    <Icon style={ICON} />
                    <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {module.label} › {page.name}
                    </span>
                  </Link>
                );
              })
            : modules.map((module) => {
                const isActive = module.id === activeModuleId;
                const Icon = module.icon;
                return (
                  <Link
                    key={module.id}
                    href={module.pages[0].href}
                    className={`pill-nav-item${isActive ? " active" : ""}`}
                  >
                    {isActive ? <span className="pill-nav-dot" /> : <Icon style={ICON} />}
                    <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{module.label}</span>
                    {module.badge && (
                      <span
                        style={{
                          fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".12em",
                          textTransform: "uppercase", color: "#41547a",
                          border: "1px solid rgba(94,140,255,.18)", borderRadius: "5px",
                          padding: "1px 5px", marginLeft: "auto", flexShrink: 0,
                        }}
                      >
                        {module.badge}
                      </span>
                    )}
                    {isActive && <span className="pill-nav-idx">{pad(indexOf[module.id])}</span>}
                  </Link>
                );
              })}
        </div>
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
