"use client";
import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { scrapingAPI, productsAPI, trackedProductsAPI, currencyAPI } from "@/lib/api";
import { Globe, Search, ShoppingBag } from "lucide-react";
import AddByLinkWizard from "@/components/AddByLinkWizard";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import StorePicker, { incarcaSelectie, salveazaSelectie } from "@/components/scraping/StorePicker";
import SourcePanel from "@/components/scraping/SourcePanel";
import ProductResultCard, { pretInRon } from "@/components/scraping/ProductResultCard";
import { runPool } from "@/lib/searchPool";

const SEARCH_TYPE_PLACEHOLDERS = {
  name: "ex: MacBook Pro 14, crema hidratanta",
  ean: "ex: 5901234567890 (8 sau 13 cifre)",
  sku: "ex: MDE14ROA",
};

const inputStyle = {
  background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
  border: "1px solid transparent",
  fontFamily: "var(--font-sans)",
  outline: "none",
};

const monoMic = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: ".14em",
  textTransform: "uppercase",
  color: "var(--text-mono)",
  margin: 0,
};

// Textul EXACT din backend/app/services/search_service.py (_MOTIV_BROWSER).
// Comparatie intreaga, nu includes(): o reformulare in backend trebuie sa rupa
// vizibil contorul, nu sa-l lase sa numere altceva in tacere.
const MOTIV_BROWSER = "necesita browser — exclus din cautare";

/** `Number` care refuza NaN/Infinity. `??` NU prinde NaN, deci nu e suficient. */
function pretNumeric(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

export default function ScrapingPage() {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState("name");
  const [sortOrder, setSortOrder] = useState("default");
  const [view, setView] = useState("panels");     // panels | unified
  // RETAIL-4 — link lipit in campul de cautare: deschide asistentul de adaugare.
  const [linkUrl, setLinkUrl] = useState(null);

  const [sources, setSources] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [pickerDeschis, setPickerDeschis] = useState(true);
  const [eurRon, setEurRon] = useState(null);

  // `perDomain: {domain -> {state, result}}`. `null` = nicio cautare inca.
  const [perDomain, setPerDomain] = useState(null);
  const [rulare, setRulare] = useState(false);
  // Contorul de rulari: orice rezultat sosit cu alt `runId` decat cel curent e al
  // unei cautari abandonate si se arunca. Ref, nu state, ca `isStale` sa citeasca
  // mereu valoarea la zi din interiorul pool-ului.
  const runIdRef = useRef(0);

  useEffect(() => {
    scrapingAPI.getSources()
      .then((res) => {
        const lista = res.data?.sources || [];
        setSources(lista);
        setSelected(incarcaSelectie(lista));
      })
      .catch((e) => console.error("nu s-au putut incarca magazinele", e));

    // Cursul nu blocheaza cautarea: pe eroare ramane null si bara de rezultate o spune.
    currencyAPI.getRates()
      .then((res) => setEurRon(res.data?.EUR_RON ?? null))
      .catch(() => setEurRon(null));
  }, []);

  const cautabile = useMemo(() => sources.filter((s) => s.searchable), [sources]);
  // Cele doua motive de necautabilitate se numara SEPARAT: 10 magazine cer browser
  // (D2), iar 68 n-au descriptor `search` si se pot doar urmari prin link. Un singur
  // contor le-ar eticheta pe toate 78 drept „browser", ceea ce e fals.
  const browser = useMemo(
    () => sources.filter((s) => !s.searchable && s.reason === MOTIV_BROWSER).length,
    [sources],
  );
  const doarLink = useMemo(
    () => sources.filter((s) => !s.searchable && s.reason !== MOTIV_BROWSER).length,
    [sources],
  );

  // ORDINEA panourilor e cea din picker (API-ul sorteaza dupa label), nu ordinea in
  // care raspund magazinele — altfel lista ar sari la fiecare rezultat sosit.
  const ordineaSelectiei = useMemo(
    () => cautabile.filter((s) => selected.has(s.domain)),
    [cautabile, selected],
  );

  const schimbaSelectia = useCallback((next) => {
    setSelected(next);
    salveazaSelectie(next);
  }, []);

  const eanHint = (() => {
    if (searchType !== "ean" || !query.trim()) return "";
    const v = query.trim();
    if (!/^\d+$/.test(v)) return "EAN-ul contine doar cifre.";
    if (v.length !== 8 && v.length !== 13) return "EAN standard are 8 sau 13 cifre.";
    return "";
  })();

  const handleSearch = async (e) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    // RETAIL-4 — un URL nu e un termen de cautare: deschide asistentul in loc sa
    // trimita link-ul catre scraperele de cautare (ar returna 0 rezultate).
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      setLinkUrl(trimmed);
      return;
    }
    if (ordineaSelectiei.length === 0) return;

    const myRunId = runIdRef.current + 1;
    runIdRef.current = myRunId;
    setRulare(true);
    setPickerDeschis(false);
    setSortOrder("default");
    setPerDomain(Object.fromEntries(
      ordineaSelectiei.map((s) => [s.domain, { state: "pending", result: null }]),
    ));

    const invechit = () => runIdRef.current !== myRunId;

    await runPool(
      ordineaSelectiei.map((s) => s.domain),
      async (domain) => {
        setPerDomain((prev) => (prev && prev[domain]
          ? { ...prev, [domain]: { state: "loading", result: null } }
          : prev));
        const res = await scrapingAPI.searchOne(domain, trimmed, undefined, searchType);
        return res.data;
      },
      {
        concurrency: 6,
        isStale: invechit,
        onResult: (domain, outcome) => {
          setPerDomain((prev) => {
            // Un rezultat pentru un domeniu care nu mai e in tabel (deselectat de un
            // race) se ignora tacut — nu se reintroduce coloana.
            if (!prev || !prev[domain]) return prev;
            const result = outcome.ok
              ? outcome.data
              : {
                  status: "error",
                  reason: outcome.error?.response?.data?.detail || outcome.error?.message || "eroare de retea",
                  results: [],
                  count: 0,
                };
            return { ...prev, [domain]: { state: "done", result } };
          });
        },
      },
    );

    if (!invechit()) setRulare(false);
  };

  const opreste = () => {
    runIdRef.current += 1;             // rezultatele care mai vin devin invechite
    setRulare(false);
    setPerDomain((prev) => {
      if (!prev) return prev;
      const next = {};
      for (const [domain, v] of Object.entries(prev)) {
        next[domain] = (v.state === "pending" || v.state === "loading")
          ? { state: "anulat", result: null }
          : v;
      }
      return next;
    });
  };

  const buildSaveMessage = (data, productName) => {
    if (data.is_new) {
      return `Produs nou adaugat in baza de date:\n"${productName}"\n\nPret: ${data.current_price} ${data.currency}`;
    }
    // Produsul exista deja
    if (data.price_changed && data.previous_price != null) {
      const oldP = Number(data.previous_price).toFixed(2);
      const newP = Number(data.current_price).toFixed(2);
      const diff = Number(data.current_price) - Number(data.previous_price);
      const direction = diff < 0 ? "a SCAZUT" : "a CRESCUT";
      return `Produsul exista deja in baza de date.\n"${productName}"\n\nPretul ${direction}:\n${oldP} ${data.currency}  ->  ${newP} ${data.currency}\n(diferenta: ${diff > 0 ? "+" : ""}${diff.toFixed(2)} ${data.currency})`;
    }
    return `Produsul exista deja in baza de date.\n"${productName}"\n\nPretul a ramas neschimbat: ${data.current_price} ${data.currency}`;
  };

  const saveProduct = async (product) => {
    try {
      const res = await productsAPI.createProduct({
        name: product.name,
        current_price: product.price,
        currency: product.currency || "RON",
        source: product.source,
        source_url: product.source_url,
        image_url: product.image_url,
        ean: product.ean || null,
        sku: product.sku || null,
        category: product.category || null,
        subcategory: product.subcategory || null,
      });
      alert(buildSaveMessage(res.data, product.name));
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare");
    }
  };

  const saveAndTrack = async (product) => {
    try {
      const saved = await productsAPI.createProduct({
        name: product.name, current_price: product.price, currency: product.currency || "RON",
        source: product.source, source_url: product.source_url, image_url: product.image_url,
        ean: product.ean || null, sku: product.sku || null,
        category: product.category || null, subcategory: product.subcategory || null,
      });
      await trackedProductsAPI.toggleMonitoring(saved.data.id, true, null);
      const status = saved.data.is_new
        ? "Produs nou salvat si adaugat in Produse Urmarite!"
        : (saved.data.price_changed
            ? `Produsul exista deja — pretul a fost actualizat (${Number(saved.data.previous_price).toFixed(2)} -> ${Number(saved.data.current_price).toFixed(2)} ${saved.data.currency}) si adaugat in Produse Urmarite.`
            : "Produsul exista deja in baza de date si a fost adaugat in Produse Urmarite.");
      alert(status);
    } catch (e) { alert(e.response?.data?.detail || "Eroare"); }
  };

  // ── agregari peste `perDomain` ──────────────────────────────────────────────
  const rezumat = useMemo(() => {
    if (!perDomain) return null;
    let produse = 0, cuRezultate = 0, goale = 0, blocate = 0, erori = 0, terminate = 0;
    let inCurs = 0;
    for (const v of Object.values(perDomain)) {
      if (v.state === "pending" || v.state === "loading") { inCurs += 1; continue; }
      // Cererile ANULATE cu „Opreste" nu intra in niciun contor: n-au raspuns, dar
      // nici nu mai sunt asteptate.
      if (v.state !== "done") continue;
      terminate += 1;
      const s = v.result?.status;
      if (s === "ok") { cuRezultate += 1; produse += v.result.count || 0; }
      else if (s === "empty") goale += 1;
      else if (s === "blocked") blocate += 1;
      else erori += 1;
    }
    return {
      produse, cuRezultate, goale, blocate, erori, terminate, inCurs,
      total: Object.keys(perDomain).length,
      // „Gata" inseamna ca nu mai asteptam pe nimeni — NU `terminate === total`,
      // care dupa „Opreste" n-ar mai fi niciodata adevarat (anulatele nu sunt done).
      terminat: inCurs === 0,
    };
  }, [perDomain]);

  // Sortarea traieste INTR-UN SINGUR LOC si se coboara ca prop in `SourcePanel`:
  // altfel lista unica si panourile ar avea fiecare copia ei, iar o corectura ar
  // trebui facuta de doua ori (exact cum era inainte de SEARCH-2b).
  const sorteaza = useCallback((produse) => {
    if (sortOrder === "default" || produse.length < 2) return produse;
    // Fara curs, EUR cade pe valoarea NOMINALA — imperfect, dar mai bun decat sa
    // dispara din clasament; bara de rezultate spune ca lipseste cursul.
    const cheie = (p) => pretInRon(p, eurRon) ?? pretNumeric(p?.price);
    const copie = [...produse];
    copie.sort((a, b) => {
      const x = cheie(a), y = cheie(b);
      // Produsele fara pret comparabil stau la COADA in AMBELE directii. Nu prin
      // ±Infinity: acela le-ar muta in cap la sortarea descrescatoare.
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return sortOrder === "price_asc" ? x - y : y - x;
    });
    return copie;
  }, [sortOrder, eurRon]);

  const toateProdusele = useMemo(() => {
    if (!perDomain) return [];
    const out = [];
    for (const s of ordineaSelectiei) {
      const v = perDomain[s.domain];
      if (v?.state === "done" && v.result?.status === "ok") out.push(...(v.result.results || []));
    }
    return out;
  }, [perDomain, ordineaSelectiei]);

  const listaUnica = useMemo(() => sorteaza(toateProdusele), [toateProdusele, sorteaza]);

  // Fragmentele cu valoarea 0 se OMIT: „0 blocate" e zgomot, iar cu toate zero
  // ramane doar numaratoarea de rezultate.
  const fragmenteRezumat = rezumat
    ? [
        [rezumat.goale, "fără rezultate"],
        [rezumat.blocate, "blocate"],
        [rezumat.erori, "erori"],
      ].filter(([n]) => n > 0).map(([n, text]) => `${n} ${text}`)
    : [];

  let subtitlu;
  if (!rezumat) {
    subtitlu = `Caută pe ${cautabile.length} magazine (${browser} necesită browser, ${doarLink} doar prin link)`;
  } else if (!rezumat.terminat) {
    subtitlu = `Se caută pe ${rezumat.total} magazine…`;
  } else {
    subtitlu = (
      <>
        <Hl>{rezumat.produse} rezultate</Hl> din {rezumat.cuRezultate} magazine
        {fragmenteRezumat.length > 0 && <> — {fragmenteRezumat.join(", ")}</>}
      </>
    );
  }

  return (
    <div>
      <TopBar path={["CATALOG", "SCANARE MAGAZINE"]} />

      <PageHeading icon={Globe} title="Scanare Magazine" subtitle={subtitlu} />

      {/* Search */}
      <form onSubmit={handleSearch} style={{ marginTop: "16px" }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "stretch" }}>
          <select value={searchType} onChange={(e) => setSearchType(e.target.value)}
            title="Tipul codului dupa care cautam"
            style={{ ...inputStyle, padding: "10px 13px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12.5px", minWidth: "150px", cursor: "pointer" }}>
            <option value="name">Cauta dupa: Nume</option>
            <option value="ean">Cauta dupa: EAN</option>
            <option value="sku">Cauta dupa: SKU</option>
          </select>
          <div style={{ flex: 1, minWidth: "200px", position: "relative" }}>
            <Search style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", width: "15px", height: "15px", color: "var(--text-muted)" }} strokeWidth={1.8} />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={SEARCH_TYPE_PLACEHOLDERS[searchType]}
              inputMode={searchType === "ean" ? "numeric" : "text"}
              style={{ ...inputStyle, width: "100%", padding: "10px 13px 10px 34px", borderRadius: "10px", color: "var(--text-primary)", fontSize: "12.5px" }} />
          </div>
          {rulare ? (
            <button type="button" onClick={opreste} className="btn-cyan">Opreste</button>
          ) : (
            <button type="submit" disabled={ordineaSelectiei.length === 0} className="btn-cyan">Cauta</button>
          )}
        </div>
        {eanHint && (
          <p style={{ marginTop: "8px", fontSize: "11.5px", color: "#fde047" }}>{eanHint}</p>
        )}
        {searchType !== "name" && !eanHint && (
          <p style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--text-dim)" }}>
            Doar magazinele cu scraper dedicat (Altex, eMAG, PCGarage, Sole, Farmacia Tei) filtreaza dupa cod; celelalte trimit codul ca termen de cautare.
          </p>
        )}
        <p style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--text-muted)" }}>
          Poti lipi direct link-ul unei pagini de produs — se deschide asistentul de adaugare.
        </p>
      </form>

      {linkUrl && <AddByLinkWizard url={linkUrl} onClose={() => setLinkUrl(null)} />}

      {/* Selectorul de magazine */}
      <div style={{ marginTop: "14px" }}>
        {pickerDeschis ? (
          <>
            <StorePicker sources={sources} selected={selected} onChange={schimbaSelectia} />
            {perDomain && (
              <button type="button" onClick={() => setPickerDeschis(false)}
                style={{ ...monoMic, marginTop: "8px", background: "transparent", border: "none", cursor: "pointer", color: "var(--text-dim)" }}>
                ascunde selectorul
              </button>
            )}
          </>
        ) : (
          <button type="button" onClick={() => setPickerDeschis(true)}
            style={{ ...monoMic, background: "transparent", border: "none", cursor: "pointer", color: "var(--text-dim)" }}>
            {selected.size} magazine selectate · modifica
          </button>
        )}
      </div>

      {/* Bara de rezultate */}
      {perDomain && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", margin: "16px 0 12px", flexWrap: "wrap" }}>
          <div>
            <p style={monoMic}>
              {rezumat.produse} produse · {rezumat.terminate}/{rezumat.total} magazine
            </p>
            {eurRon == null && (
              <p style={{ margin: "4px 0 0", fontSize: "10.5px", color: "var(--text-dim)" }}>
                curs BNR indisponibil — preturile EUR nu sunt convertite
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <select value={view} onChange={(e) => setView(e.target.value)}
              style={{ ...inputStyle, padding: "7px 11px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12px", cursor: "pointer" }}>
              <option value="panels">Pe magazine</option>
              <option value="unified">Lista unica</option>
            </select>
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}
              title="Sortarea foloseste pretul in RON (EUR convertit la cursul BNR)"
              style={{ ...inputStyle, padding: "7px 11px", borderRadius: "10px", color: "var(--text-secondary)", fontSize: "12px", cursor: "pointer" }}>
              <option value="default">Sorteaza: Implicit</option>
              <option value="price_asc">Pret: crescator</option>
              <option value="price_desc">Pret: descrescator</option>
            </select>
          </div>
        </div>
      )}

      {/* Rezultatele */}
      {perDomain && view === "panels" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {ordineaSelectiei.map((s) => {
            const v = perDomain[s.domain];
            if (!v) return null;
            return (
              <SourcePanel
                key={s.domain}
                source={s}
                state={v.state}
                result={v.result}
                eurRon={eurRon}
                sorteaza={sorteaza}
                onSave={saveProduct}
                onSaveAndTrack={saveAndTrack}
              />
            );
          })}
        </div>
      )}

      {perDomain && view === "unified" && (
        <>
          {listaUnica.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {listaUnica.map((product, i) => (
                <ProductResultCard
                  key={`${product.source}-${product.source_url || product.name}-${i}`}
                  product={product}
                  eurRon={eurRon}
                  onSave={saveProduct}
                  onSaveAndTrack={saveAndTrack}
                />
              ))}
            </div>
          )}
          {/* Cat timp mai raspund magazine, lista unica NU are voie sa spuna „nu s-au
              gasit produse" — ar fi o concluzie trasa inainte de final. Vederea pe
              magazine arata progresul singura, prin pastilele de stare. */}
          {!rezumat.terminat && (
            <p style={{ ...monoMic, marginTop: listaUnica.length > 0 ? "12px" : 0, color: "var(--text-dim)" }}>
              se caută… ({rezumat.terminate} din {rezumat.total} magazine au răspuns)
            </p>
          )}
          {rezumat.terminat && listaUnica.length === 0 && (
            <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
              <ShoppingBag style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
              <p style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>Nu s-au gasit produse</p>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Incearca alt termen de cautare sau alte magazine.</p>
            </div>
          )}
        </>
      )}

      {!perDomain && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Globe style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
          <p style={{ color: "var(--text-primary)", fontSize: "1.125rem", marginBottom: "0.5rem" }}>Cauta produse pe magazinele online</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            Alege magazinele de mai sus si introdu un termen de cautare.
          </p>
        </div>
      )}
    </div>
  );
}
