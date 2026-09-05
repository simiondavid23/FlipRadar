// Formatare comuna pentru cardurile/modalele de anunturi (Radar + Auto + Imobiliare).
// Copiat EXACT din radar/page.js ca sa pastreze comportament identic dupa extragere.
import { GRADE_COLORS } from "@/lib/uiStyles";

// UI-1 — badge-ul UNIC de scadere de pret, pentru toate modulele.
//
// Inainte existau doua: „↓ de la X" (verde, Radar, din `pret_anterior`) si „↓ N%"
// (portocaliu, Imobiliare, calculat in pagina din `price_history[0]`). Acum unul singur,
// cu ambele informatii, hranit de o singura cheie serializata: `pret_anterior`.
// Verdele castiga fata de portocaliu — o scadere e o veste buna, consecvent cu culoarea
// marjei.
//
// Garda e `anterior > curent > 0`, STRICT, si traieste DOAR aici: componentele care
// randeaza badge-ul sunt partajate cu module ale caror serializari nu trimit (inca)
// cheia — Auto pana la SEEN-3. `Number(undefined)` = NaN pica pe `Number.isFinite`, deci
// badge-ul e inert prin DATE, nu printr-o ramura per modul. Un `>=` l-ar aprinde pe
// valori egale, adica pe „n-a scazut nimic".
export function PretScazutBadge({ listing, size = "10.5px" }) {
  const anterior = Number(listing?.pret_anterior);
  const curent = Number(listing?.price);
  if (!Number.isFinite(anterior) || !Number.isFinite(curent)
      || !(curent > 0) || !(anterior > curent)) return null;
  const pct = Math.round(((anterior - curent) / anterior) * 100);
  return (
    <span
      title={`Preț scăzut cu ${pct}% față de prima vedere`}
      style={{
        fontSize: size, fontWeight: 600, whiteSpace: "nowrap",
        padding: "1px 6px", borderRadius: "999px",
        background: GRADE_COLORS.A.bg,
        border: `1px solid ${GRADE_COLORS.A.border}`,
        color: GRADE_COLORS.A.text,
      }}
    >
      ↓ {pct}% · de la {Math.round(anterior)}
    </span>
  );
}

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
  if (pct === null || pct === undefined) return "var(--text-tertiary)";
  if (pct >= 25) return "#4ade80";
  if (pct >= 10) return "#fde047";
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

// RP-4 — vechimea contului vanzatorului (deocamdata doar OLX: `member_since` = anul
// inregistrarii, extras la enrichment din /api/v1/offers/{id}).
export function memberSinceLabel(listing) {
  if (listing.platform !== "olx" || listing.member_since == null) return "";
  return `membru din ${listing.member_since}`;
}
