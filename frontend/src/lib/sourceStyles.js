/**
 * POLISH-2 — culorile badge-ului de sursa, intr-un singur loc.
 *
 * Obiectul era DUPLICAT identic in scraping/page.js si tracked-products/page.js:
 * orice culoare adaugata intr-unul singur ar fi dezsincronizat cele doua pagini
 * pentru acelasi magazin. Cheile sunt EXACT domeniile stocate pe produs (aceleasi
 * pe care le compara refresh-ul), deci en.afew-store.com sta cu subdomeniu cu tot.
 *
 * Perechile sunt rgba(...,0.2) pe fundal + hex deschis pe text, ca sa ramana
 * lizibile pe tema intunecata.
 */
export const SOURCE_STYLES = {
  // ── electro (RETAIL-3a / 5c) ──
  "altex.ro": { bg: "rgba(59,130,246,0.2)", fg: "#60a5fa" },       // albastru
  "emag.ro": { bg: "rgba(250,204,21,0.2)", fg: "#facc15" },        // galben
  "cel.ro": { bg: "rgba(14,165,233,0.2)", fg: "#38bdf8" },         // cyan
  "vexio.ro": { bg: "rgba(20,184,166,0.2)", fg: "#2dd4bf" },       // turcoaz
  "mediagalaxy.ro": { bg: "rgba(239,68,68,0.2)", fg: "#f87171" },  // rosu

  // ── fashion (FASHION-1b / 2 / 2b) ──
  "answear.ro": { bg: "rgba(217,70,239,0.2)", fg: "#e879f9" },     // magenta
  "fashiondays.ro": { bg: "rgba(244,63,94,0.2)", fg: "#fb7185" },  // roz-rosu
  "epantofi.ro": { bg: "rgba(139,92,246,0.2)", fg: "#a78bfa" },    // violet
  "modivo.ro": { bg: "rgba(99,102,241,0.2)", fg: "#818cf8" },      // indigo
  "bstn.com": { bg: "rgba(249,115,22,0.2)", fg: "#fb923c" },       // portocaliu
  // Cheia EXACTA, cu subdomeniu — asa se stocheaza si asa se compara la refresh.
  "en.afew-store.com": { bg: "rgba(132,204,22,0.2)", fg: "#a3e635" },  // lime
  "prm.com": { bg: "rgba(6,182,212,0.2)", fg: "#22d3ee" },         // cyan inchis
  "sneakersnstuff.com": { bg: "rgba(245,158,11,0.2)", fg: "#fbbf24" },  // chihlimbar

  // ── pastrate din versiunea veche: nevalidate azi, dar produsele salvate
  //    inainte le au inca pe sursa, deci stergerea lor ar fi o regresie vizuala ──
  "sole.ro": { bg: "rgba(236,72,153,0.2)", fg: "#f472b6" },
  "farmaciatei.ro": { bg: "rgba(34,197,94,0.2)", fg: "#4ade80" },
  "pcgarage.ro": { bg: "rgba(168,85,247,0.2)", fg: "#c084fc" },
};

/** Gri neutru pentru orice sursa necunoscuta — comportamentul dinainte. */
const FALLBACK = { bg: "rgba(148,163,184,0.2)", fg: "#cbd5e1" };

export function styleFor(source) {
  return SOURCE_STYLES[source] || FALLBACK;
}
