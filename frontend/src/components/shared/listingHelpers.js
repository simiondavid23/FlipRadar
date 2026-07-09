// Formatare comuna pentru cardurile/modalele de anunturi (Radar + Auto).
// Copiat EXACT din radar/page.js ca sa pastreze comportament identic dupa extragere.

export function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "acum câteva secunde";
  if (diff < 3600) return `acum ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `acum ${Math.floor(diff / 3600)} h`;
  return `acum ${Math.floor(diff / 86400)} zile`;
}

export function formatListedDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  const sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  const yest = new Date(now.getTime() - 86400000);
  const isYesterday = d.getFullYear() === yest.getFullYear() && d.getMonth() === yest.getMonth() && d.getDate() === yest.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `azi ${hh}:${mm}`;
  if (isYesterday) return `ieri ${hh}:${mm}`;
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mo}.${d.getFullYear()} ${hh}:${mm}`;
}

export function marginColor(pct) {
  if (pct === null || pct === undefined) return "var(--text-secondary)";
  if (pct >= 25) return "#4ade80";
  if (pct >= 10) return "#facc15";
  return "#fb923c";
}

// RP-1 — eticheta de rating a vanzatorului, formatata per platforma:
//   okazii: "{pct}% pozitive ({n})"  (pct = rating×20)
//   vinted (si generic, scara 0-5): "★{rating} ({n} evaluări)"
export function sellerRatingLabel(listing) {
  if (listing.seller_reviews === 0) return "fără evaluări";
  const n = listing.seller_reviews;
  const r = listing.seller_rating;
  if (r === null || r === undefined) {
    return n !== null && n !== undefined ? `(${n} evaluări)` : "";
  }
  if (listing.platform === "okazii") {
    const pct = Math.round(r * 20);
    return n !== null && n !== undefined ? `${pct}% pozitive (${n})` : `${pct}% pozitive`;
  }
  return n !== null && n !== undefined ? `★${r.toFixed(1)} (${n} evaluări)` : `★${r.toFixed(1)}`;
}
