"use client";
import { styleFor } from "@/lib/sourceStyles";

/**
 * SEARCH-2 — selectorul de magazine, grupat pe categorie.
 *
 * Magazinele necautabile se ARATA dezactivate, cu motivul in tooltip (D2), nu se
 * ascund: userul trebuie sa vada ca `sephora.ro` exista in platforma si de ce nu se
 * poate cauta pe el, altfel ar crede ca lipseste.
 */

// Etichetele RO ale categoriilor din registru. `categoriaLabel` cade pe id-ul brut
// pentru orice categorie necunoscuta — o categorie noua adaugata in backend NU are
// voie sa rupa pagina, doar sa arate mai putin frumos pana i se scrie eticheta.
const CATEGORII = {
  electronice: "Electronice",
  fashion: "Fashion",
  sneakers: "Sneakers",
  incaltaminte: "Încălțăminte",
  tcg: "TCG",
  outdoor: "Outdoor",
  jucarii: "Jucării",
  foto: "Foto",
  beauty: "Beauty",
  general: "General",
  bricolaj: "Bricolaj",
  pet: "Pet",
  biciclete: "Biciclete",
  "bijuterii-ceasuri": "Bijuterii & ceasuri",
  farmacie: "Farmacie",
};

const categoriaLabel = (id) => CATEGORII[id] || id || "Altele";

const CHEIE_STOCARE = "flipradar.scraping.selected";

/**
 * Selectia salvata, INTERSECTATA cu ce e cautabil acum.
 *
 * Doua reguli, amandoua ca sa nu mintim userul:
 *   * un domeniu scos din registru (sau devenit necautabil) NU ramane selectat;
 *   * un domeniu APARUT intre timp nu se selecteaza automat — userul il vede nou in
 *     picker si il bifeaza el, in loc sa i se strecoare in cautari.
 * Fara nimic salvat, implicit sunt TOATE cele cautabile.
 */
export function incarcaSelectie(sources) {
  const cautabile = new Set(sources.filter((s) => s.searchable).map((s) => s.domain));
  let brut = null;
  try {
    brut = window.localStorage.getItem(CHEIE_STOCARE);
  } catch {
    brut = null; // localStorage poate fi blocat; nu e motiv sa cada pagina
  }
  if (!brut) return cautabile;
  try {
    const salvate = JSON.parse(brut);
    if (!Array.isArray(salvate)) return cautabile;
    return new Set(salvate.filter((d) => cautabile.has(d)));
  } catch {
    return cautabile;
  }
}

export function salveazaSelectie(selected) {
  try {
    window.localStorage.setItem(CHEIE_STOCARE, JSON.stringify([...selected]));
  } catch {
    /* stocare indisponibila — selectia ramane doar pe sesiunea curenta */
  }
}

const btnMic = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: ".1em",
  textTransform: "uppercase",
  padding: "4px 9px",
  borderRadius: "8px",
  border: "1px solid rgba(148,163,184,0.25)",
  background: "transparent",
  color: "var(--text-dim)",
  cursor: "pointer",
};

export default function StorePicker({ sources, selected, onChange }) {
  const cautabile = sources.filter((s) => s.searchable);

  const setSelectie = (domenii) => onChange(new Set(domenii));

  const comuta = (domain) => {
    const next = new Set(selected);
    if (next.has(domain)) next.delete(domain);
    else next.add(domain);
    onChange(next);
  };

  // Grupare pe categorie, pastrand ordinea din API (sortata dupa label).
  const grupuri = [];
  const dupaCategorie = new Map();
  for (const s of sources) {
    if (!dupaCategorie.has(s.category)) {
      dupaCategorie.set(s.category, []);
      grupuri.push(s.category);
    }
    dupaCategorie.get(s.category).push(s);
  }
  grupuri.sort((a, b) => categoriaLabel(a).localeCompare(categoriaLabel(b), "ro"));

  return (
    <div className="glass-panel" style={{ padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", marginBottom: "12px" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--text-mono)", margin: 0 }}>
          {selected.size} din {cautabile.length} magazine selectate
        </p>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <button type="button" style={btnMic} onClick={() => setSelectie(cautabile.map((s) => s.domain))}>Toate</button>
          <button type="button" style={btnMic} onClick={() => setSelectie([])}>Niciunul</button>
          <button
            type="button"
            style={btnMic}
            title="Magazinele care dau preturi in RON (inclusiv cele cu scraper dedicat)"
            onClick={() => setSelectie(cautabile.filter((s) => s.currency === "RON" || s.currency == null).map((s) => s.domain))}
          >
            Doar RON
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {grupuri.map((cat) => {
          const magazine = dupaCategorie.get(cat);
          const cautabileGrup = magazine.filter((s) => s.searchable).map((s) => s.domain);
          return (
            <div key={cat}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "7px" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--text-mono)" }}>
                  {categoriaLabel(cat)}
                </span>
                {cautabileGrup.length > 0 && (
                  <button
                    type="button"
                    style={{ ...btnMic, padding: "2px 7px", fontSize: "8.5px" }}
                    onClick={() => setSelectie([...new Set([...selected, ...cautabileGrup])])}
                  >
                    + toate
                  </button>
                )}
              </div>
              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                {magazine.map((s) => {
                  const style = styleFor(s.domain);
                  const activ = selected.has(s.domain);
                  const dezactivat = !s.searchable;
                  return (
                    <button
                      key={s.domain}
                      type="button"
                      disabled={dezactivat}
                      title={dezactivat ? s.reason || "necautabil" : s.domain}
                      onClick={() => !dezactivat && comuta(s.domain)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "6px 10px",
                        borderRadius: "9px",
                        fontSize: "12px",
                        cursor: dezactivat ? "not-allowed" : "pointer",
                        opacity: dezactivat ? 0.4 : 1,
                        background: activ ? style.bg : "rgba(148,163,184,0.06)",
                        border: `1px solid ${activ ? `${style.fg}66` : "rgba(148,163,184,0.18)"}`,
                        color: activ ? style.fg : "var(--text-secondary)",
                      }}
                    >
                      {s.label}
                      {s.currency && (
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".06em", color: "var(--text-dim)" }}>
                          {s.currency}·{s.country}
                        </span>
                      )}
                      {!s.currency && s.country && (
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".06em", color: "var(--text-dim)" }}>
                          {s.country}
                        </span>
                      )}
                      {s.truncated_at && (
                        <span
                          title={`Shopify intoarce cel mult ${s.truncated_at} rezultate per cautare`}
                          style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".06em", padding: "1px 5px", borderRadius: "6px", background: "rgba(148,163,184,0.14)", color: "var(--text-dim)" }}
                        >
                          max {s.truncated_at}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
