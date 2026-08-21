"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { findModuleForPath } from "@/lib/navigation";

// NAV-2 — linia de tab-uri a modulului curent, randata de layout deasupra paginii.
// Nu stie nimic despre paginile in sine: totul vine din @/lib/navigation.
export default function ModuleTabs() {
  const pathname = usePathname();
  const { user } = useAuth();

  const match = findModuleForPath(pathname, user);
  if (!match) return null;

  const { module, page: activePage } = match;
  // Un singur tab nu comunica nimic — pagina isi tine singura titlul.
  if (module.pages.length < 2) return null;

  return (
    <div className="module-tabs">
      {module.pages.map((page) => {
        const isActive = page.href === activePage.href;
        const Icon = page.icon;
        return (
          <Link
            key={page.href}
            href={page.href}
            className={`module-tab${isActive ? " active" : ""}`}
            aria-current={isActive ? "page" : undefined}
          >
            <Icon style={{ width: "14px", height: "14px", strokeWidth: 1.8, flexShrink: 0 }} />
            <span>{page.name}</span>
          </Link>
        );
      })}

      <style>{`
        .module-tabs {
          display: flex;
          gap: 4px;
          border-bottom: 1px solid rgba(94,140,255,.14);
          margin-bottom: 1.25rem;
          overflow-x: auto;
        }
        .module-tab {
          display: flex;
          align-items: center;
          gap: 7px;
          padding: 8px 14px;
          font-size: 13px;
          color: #94a3b8;
          text-decoration: none;
          white-space: nowrap;
          border-bottom: 2px solid transparent;
          transition: color 0.15s ease, border-bottom-color 0.15s ease;
        }
        .module-tab:hover {
          color: var(--text-primary);
        }
        .module-tab.active {
          color: var(--text-primary);
          border-bottom-color: #22d3ee;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
