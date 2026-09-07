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

// FRONT-1 — pragul de la care o reactualizare conteaza (24 h). Sub o zi e zgomot, nu
// semnal: pe OLX `lastRefreshTime == createdTime` cand anuntul n-a fost bumpat niciodata,
// iar pe Storia `pushedUpAt` si `createdAtFirst` pot diferi cu o secunda.
const PRAG_BUMP_MS = 24 * 3600 * 1000;

function msDin(iso) {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : null;
}

// FRONT-1 — regula „anunt reactualizat", intr-un SINGUR loc pe frontend.
//
// Semnalul: un anunt vechi dupa `listed_at`, dar repromovat recent dupa `refreshed_at`,
// inseamna marfa care nu pleaca — deci loc de negociere. Masurat la DATE-2 pe Storia:
// mediana diferentei 31 de zile, maximul 807.
//
// Fara `listed_at` nu stim vechimea, deci NU marcam anuntul ca reactualizat; `refreshed_at`
// singur ramane afisabil (modal, sortare) si primeste `sinceBumpDays`. Orice intrare
// invalida (null, string neparsabil, obiect lipsa) da forma neutra, niciodata exceptie.
//
// Perechea in backend e `este_reactualizat` din app/utils/listing_dates.py — aceeasi
// regula, acelasi prag, testate pe ambele parti.
export function bumpInfo(listing, now = Date.now()) {
  const gol = { bumped: false, ageDays: null, sinceBumpDays: null };
  if (!listing || typeof listing !== "object") return gol;
  const listed = msDin(listing.listed_at);
  const refreshed = msDin(listing.refreshed_at);
  const zile = (ms) => Math.floor((now - ms) / 86400000);
  if (refreshed === null) {
    return { ...gol, ageDays: listed === null ? null : zile(listed) };
  }
  return {
    bumped: listed !== null && refreshed - listed >= PRAG_BUMP_MS,
    ageDays: listed === null ? null : zile(listed),
    sinceBumpDays: zile(refreshed),
  };
}

// FRONT-1 — comparator descrescator pe o cheie de data, cu null-urile MEREU la coada.
// Extras aici fiindca sortarea era scrisa de trei ori, in trei pagini, cu trei tratari
// diferite ale null-ului (radar folosea `-Infinity`, ceea ce da NaN cand ambele lipsesc,
// adica ordine nespecificata). O regula, trei apelanti.
// TZ-3c — `fallbackKey` optional: cand cheia principala lipseste, se foloseste ea.
// Motivul concret: postarile din grupurile Facebook fara `posted_at` au acum `listed_at`
// NULL (rezerva pe `created_at` a fost scoasa — inventa o data pe ceasul gresit). Fara
// rezerva la sortare, toate ar cadea la coada lui „cele mai noi postate", chiar proaspat
// gasite. Cu `found_at` ca rezerva raman aproximativ la locul lor.
//
// De stiut: `listed_at` e pe ceasul PIETEI iar `found_at` pe al SISTEMULUI. Amestecul e
// acceptabil AICI si nicaieri altundeva — o sortare doar reordoneaza vecini apropiati, nu
// trece un prag; eroarea maxima e offsetul dintre ceasuri, si zero pe masina de productie.
export function sortByDateDesc(key, fallbackKey = null) {
  const val = (x) => {
    const t = msDin(x?.[key]);
    return t !== null ? t : (fallbackKey ? msDin(x?.[fallbackKey]) : null);
  };
  return (a, b) => {
    const ta = val(a);
    const tb = val(b);
    if (ta === null && tb === null) return 0;
    if (ta === null) return 1;
    if (tb === null) return -1;
    return tb - ta;
  };
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
