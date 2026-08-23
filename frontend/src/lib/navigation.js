// NAV-2 — sursa unica de adevar pentru navigatie.
// Sidebar-ul randeaza MODULELE, ModuleTabs randeaza PAGINILE modulului curent.
// Ordinea modulelor de aici da si indexul mono din sidebar (02..08).
import {
  Search, Percent, Globe, Heart,
  Radar, Target, Bookmark,
  Calculator, Rss, Tag,
  Car, Home,
  Boxes, Receipt, BarChart2,
  Activity, Bell,
} from "lucide-react";

export const DASHBOARD_HREF = "/dashboard";

export const MODULES = [
  {
    id: "catalog",
    label: "Magazine",
    icon: Globe,
    pages: [
      { name: "Descoperă Oportunități", href: "/dashboard/products", icon: Search },
      { name: "Deal-uri", href: "/dashboard/deals", icon: Percent },
      { name: "Scanare Magazine", href: "/dashboard/scraping", icon: Globe, flag: "can_use_scraping" },
      { name: "Produse Urmărite", href: "/dashboard/tracked-products", icon: Heart },
    ],
  },
  {
    id: "radar",
    label: "Radar Piața",
    icon: Radar,
    pages: [
      { name: "Feed Anunțuri", href: "/dashboard/radar", icon: Radar },
      { name: "Keyword-uri", href: "/dashboard/radar/keywords", icon: Target },
      { name: "Salvate & Ignorate", href: "/dashboard/radar/saved", icon: Bookmark },
    ],
  },
  {
    id: "auto_lots",
    label: "Loturi Auto",
    icon: Calculator,
    badge: "în lucru",
    pages: [
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
    icon: Car,
    pages: [
      { name: "Feed Anunțuri", href: "/dashboard/auto-listings/feed", icon: Rss },
      { name: "Keyword-uri", href: "/dashboard/auto-listings/keywords", icon: Tag },
      { name: "Salvate & Ignorate", href: "/dashboard/auto-listings/saved", icon: Bookmark },
    ],
  },
  {
    id: "real_estate",
    label: "Imobiliare",
    icon: Home,
    pages: [
      { name: "Feed Anunțuri", href: "/dashboard/real-estate-monitor/feed", icon: Rss },
      { name: "Keyword-uri", href: "/dashboard/real-estate-monitor/keywords", icon: Tag },
      { name: "Salvate & Ignorate", href: "/dashboard/real-estate-monitor/saved", icon: Bookmark },
    ],
  },
  {
    id: "gestiune",
    label: "Gestiune",
    icon: Boxes,
    pages: [
      { name: "Inventar", href: "/dashboard/inventory", icon: Boxes },
      { name: "Registru Vanzari", href: "/dashboard/sales", icon: Receipt },
      { name: "Statistici & Profit", href: "/dashboard/reports", icon: BarChart2 },
    ],
  },
  {
    id: "monitorizare",
    label: "Monitorizare",
    icon: Activity,
    pages: [
      { name: "Jurnale Live", href: "/dashboard/logs", icon: Activity },
      { name: "Alerte Pret", href: "/dashboard/alerts", icon: Bell, flag: "can_use_alerts" },
    ],
  },
];

// Un flag lipsa inseamna pagina publica; flagul se respecta doar cand e explicit false.
export function filterPagesForUser(pages, user) {
  if (!user) return pages;
  return pages.filter((p) => {
    if (!p.flag) return true;
    return user[p.flag] !== false;
  });
}

// Modulele cu paginile deja filtrate; modulele ramase goale dispar complet.
export function visibleModules(user) {
  return MODULES
    .map((m) => ({ ...m, pages: filterPagesForUser(m.pages, user) }))
    .filter((m) => m.pages.length > 0);
}

// Cel mai lung href care e prefix al caii castiga, ca /dashboard/radar/keywords
// sa nu fie revendicat de /dashboard/radar. Prefix inseamna egalitate sau href + "/",
// altfel /dashboard/auto ar prinde /dashboard/auto-listings.
// DASHBOARD_HREF e sarit explicit: fiind prefixul tuturor, ar prinde orice.
export function findModuleForPath(pathname, user) {
  if (!pathname) return null;
  let best = null;
  for (const modul of visibleModules(user)) {
    for (const page of modul.pages) {
      if (page.href === DASHBOARD_HREF) continue;
      const hit = pathname === page.href || pathname.startsWith(page.href + "/");
      if (!hit) continue;
      if (!best || page.href.length > best.page.href.length) best = { module: modul, page };
    }
  }
  return best;
}
