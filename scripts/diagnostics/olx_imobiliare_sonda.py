# -*- coding: utf-8 -*-
"""FlipRadar - SONDA OLX Imobiliare (IM-DIAG-1). Diagnostic READ-ONLY, nu se comite.

Confirma LIVE, inainte de refactorizarea IM-1, trei lucruri despre OLX Imobiliare:
  A. daca path-ul de oras (ex. /.../bucuresti/) exista si filtreaza corect;
  B. cum interactioneaza filtrul de pret search[filter_float_price:to] cu anunturile
     in LEI (comparatie numerica bruta vs per-moneda) si daca exista un param de moneda;
  C. de ce un anunt de 350 EUR dispare cand filtrul e setat la max 400 (reproducem
     URL-ul exact construit de scraperul actual, cu q-Crangasi cu diacritice).

Standalone: doar stdlib + curl_cffi + bs4. NU importa nimic din app.*.
Sincron (curl_cffi.requests.Session), impersonate=chrome131, timeout=20, pauza 2.5s.

RULARE (din radacina repo, cu venv-ul backend):
  python scripts/diagnostics/olx_imobiliare_sonda.py
Nu scrie niciun fisier — output-ul se citeste direct din consola.
"""
import re
import sys
import time
import unicodedata
from urllib.parse import urlencode, urlparse, unquote

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.olx.ro"
IMPERSONATE = "chrome131"

# Headers ceruti de sonda: UA Chrome 131 Windows, Accept-Language redus, Referer olx.ro
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.7",
    "Referer": "https://www.olx.ro/",
}

# Categoria de baza folosita de scraperul actual pentru apartament/garsoniera de inchiriat
CAT = "/imobiliare/apartamente-garsoniere-de-inchiriat/"

REZ = {}  # test -> record, pentru sumar si interpretarea automata


def say(msg=""):
    print(msg, flush=True)


def merge(base, extra):
    # copie a dict-ului de baza + param suplimentar (chei cu [ ] : incluse)
    d = dict(base)
    d.update(extra)
    return d


# -- helper parsare card (reutilizat de toate testele) -------------------------

def parse_price(raw):
    """Valoare numerica a pretului. Logica copiata din scraper (_common.parse_price):
    strip non-cifre (pastreaza . si ,), '.' de mii eliminat, ',' -> '.', apoi float.
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(raw)).replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def detecteaza_moneda(raw):
    """RON daca textul contine lei/ron, EUR daca contine simbol euro/eur, altfel '?'."""
    t = (raw or "").lower()
    if "lei" in t or "ron" in t:
        return "RON"
    if "€" in t or "eur" in t:  # € = simbolul euro
        return "EUR"
    return "?"


def ascii_lower(s):
    """NFKD -> ascii -> lowercase, pentru comparatii fara diacritice."""
    n = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return n.strip().lower()


def extrage_carduri(soup):
    """Lista de dict-uri {titlu, pret_raw, pret_val, moneda, locatie} pentru fiecare l-card."""
    cards = soup.select('div[data-cy="l-card"]') or soup.select('[data-testid="l-card"]')
    out = []
    for card in cards:
        # titlu: h4 / h6 / primul <a>, maxim 60 caractere
        el = card.find("h4") or card.find("h6") or card.find("a")
        titlu = el.get_text(strip=True)[:60] if el else ""
        # pret raw: element [data-testid="ad-price"], get_text cu separator spatiu
        pel = card.find(attrs={"data-testid": "ad-price"})
        pret_raw = pel.get_text(" ", strip=True) if pel else ""
        # locatie raw: element [data-testid="location-date"]
        lel = card.find(attrs={"data-testid": "location-date"})
        locatie = lel.get_text(" ", strip=True) if lel else ""
        out.append({
            "titlu": titlu,
            "pret_raw": pret_raw,
            "pret_val": parse_price(pret_raw),
            "moneda": detecteaza_moneda(pret_raw),
            "locatie": locatie,
        })
    return out


def min_max(cards, moneda):
    vals = [c["pret_val"] for c in cards if c["moneda"] == moneda and c["pret_val"] is not None]
    return (min(vals), max(vals)) if vals else (None, None)


def fmt(v):
    if v is None:
        return "-"
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def ruleaza_test(session, n, descriere, url, params, oras_asteptat):
    """Executa un test, printeaza raportul si intoarce record-ul pentru sumar."""
    requested = url + ("?" + urlencode(params) if params else "")
    say(f"\n[T{n}] {descriere}")
    say(f"  URL final: {requested}")

    try:
        r = session.get(url, params=params, headers=HEADERS, impersonate=IMPERSONATE, timeout=20)
        status = r.status_code
        url_final = str(r.url)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        say(f"  EROARE request: {exc}")
        rec = {"n": n, "status": "ERR", "cards": 0, "eur": 0, "ron": 0, "unk": 0,
               "pct": None, "eur_min": None, "eur_max": None, "ron_min": None,
               "ron_max": None, "parsed": []}
        REZ[f"T{n}"] = rec
        return rec

    # semnalam redirect real (path decodat schimbat) — relevant pt path-ul de oras
    p_req = unquote(urlparse(requested).path).rstrip("/").lower()
    p_fin = unquote(urlparse(url_final).path).rstrip("/").lower()
    if p_fin != p_req:
        say(f"  -> redirect server catre: {url_final}")

    parsed = extrage_carduri(soup)
    n_cards = len(parsed)
    eur = sum(1 for c in parsed if c["moneda"] == "EUR")
    ron = sum(1 for c in parsed if c["moneda"] == "RON")
    unk = sum(1 for c in parsed if c["moneda"] == "?")
    eur_min, eur_max = min_max(parsed, "EUR")
    ron_min, ron_max = min_max(parsed, "RON")

    say(f"  HTTP {status} | {n_cards} carduri SSR")
    say(f"  Distributie moneda: EUR={eur}  RON={ron}  ?={unk}")
    say(f"  Pret EUR: min={fmt(eur_min)} max={fmt(eur_max)}   |   "
        f"Pret RON: min={fmt(ron_min)} max={fmt(ron_max)}")

    say("  Primele 5 carduri:")
    for c in parsed[:5]:
        say(f"    - {c['titlu']} | {c['pret_raw']} | {c['locatie']}")
    if not parsed:
        say("    (niciun card SSR)")

    pct = None
    if oras_asteptat:
        cu_loc = [c for c in parsed if c["locatie"]]
        oras_n = ascii_lower(oras_asteptat)
        match = [c for c in cu_loc if oras_n in ascii_lower(c["locatie"])]
        pct = (100.0 * len(match) / len(cu_loc)) if cu_loc else None
        pct_txt = f"{pct:.0f}%" if pct is not None else "n/a"
        say(f"  Locatie: {len(match)}/{len(cu_loc)} carduri cu locatie contin "
            f"'{oras_asteptat}' ({pct_txt})")

    rec = {"n": n, "status": status, "cards": n_cards, "eur": eur, "ron": ron, "unk": unk,
           "pct": pct, "eur_min": eur_min, "eur_max": eur_max, "ron_min": ron_min,
           "ron_max": ron_max, "parsed": parsed}
    REZ[f"T{n}"] = rec
    return rec


def main():
    say("=" * 78)
    say("SONDA OLX IMOBILIARE (IM-DIAG-1) — path oras + filtru pret + moneda + q-")
    say(f"impersonate={IMPERSONATE}  timeout=20  pauza 2.5s intre requesturi")
    say("=" * 78)

    session = curl_requests.Session()

    order_only = {"search[order]": "created_at:desc"}
    price_to = {"search[order]": "created_at:desc", "search[filter_float_price:to]": 400}

    # (n, sectiune-header-sau-None, descriere, url, params, oras_asteptat)
    teste = [
        (1, "SECTIUNEA 1 — reproducerea starii actuale (scraperul de azi)",
         "Repro scraper actual: q-Crangasi cu diacritice, fara oras, fara filtru pret",
         BASE + CAT + "q-Crângași/", dict(order_only), None),
        (2, None,
         "Repro scenariu raportat: acelasi URL ca T1 + filtru pret max 400",
         BASE + CAT + "q-Crângași/", dict(price_to), None),

        (3, "SECTIUNEA 2 — path de oras (neconfirmat pana acum)",
         "Path oras Bucuresti (fara params)",
         BASE + CAT + "bucuresti/", {}, "bucuresti"),
        (4, None,
         "Path oras Cluj-Napoca (slug cu cratima, fara params)",
         BASE + CAT + "cluj-napoca/", {}, "cluj-napoca"),
        (5, None,
         "Path oras Bucuresti + filtru pret max 400 (oras + pret impreuna)",
         BASE + CAT + "bucuresti/", dict(price_to), "bucuresti"),

        (6, "SECTIUNEA 3 — moneda la filtrare (explorator, e OK sa esueze)",
         "T5 + param suplimentar currency=EUR",
         BASE + CAT + "bucuresti/", merge(price_to, {"currency": "EUR"}), "bucuresti"),
        (7, None,
         "T5 + param suplimentar search[currency]=EUR",
         BASE + CAT + "bucuresti/", merge(price_to, {"search[currency]": "EUR"}), "bucuresti"),

        (8, "SECTIUNEA 4 — q- combinat cu oras (informativ pt viitor)",
         "Path oras Bucuresti + q-crangasi (fara diacritice) impreuna",
         BASE + CAT + "bucuresti/q-crangasi/", dict(order_only), "bucuresti"),
    ]

    first = True
    for n, sectiune, descriere, url, params, oras in teste:
        if sectiune:
            say("\n" + "-" * 78)
            say(sectiune)
            say("-" * 78)
        if not first:
            time.sleep(2.5)  # pauza intre requesturi
        first = False
        ruleaza_test(session, n, descriere, url, params, oras)

    # -- SUMAR ------------------------------------------------------------------
    say("\n" + "=" * 78)
    say("SUMAR FINAL")
    say("=" * 78)
    say(f"{'test':<5}| {'status':<7}| {'carduri':<8}| {'EUR':<4}| {'RON':<4}| %locatie-ok")
    for k in sorted(REZ, key=lambda x: int(x[1:])):
        r = REZ[k]
        pct_txt = "-" if r["pct"] is None else f"{r['pct']:.0f}%"
        say(f"{k:<5}| {str(r['status']):<7}| {r['cards']:<8}| "
            f"{r['eur']:<4}| {r['ron']:<4}| {pct_txt}")

    # -- interpretare automata prudenta (exact 3 linii) -------------------------
    say("\nINTERPRETARE AUTOMATA (prudenta):")

    def ok_oras(t):
        r = REZ.get(t)
        return bool(r and r["status"] == 200 and r["cards"] >= 10
                    and r["pct"] is not None and r["pct"] >= 80)

    ok3, ok4 = ok_oras("T3"), ok_oras("T4")
    v1 = "DA" if (ok3 and ok4) else ("PROBABIL" if (ok3 or ok4) else "NU")
    say(f"  1. Path oras functional: {v1}  "
        f"(T3 ok={ok3}, T4 ok={ok4}; criteriu: 200 + >=10 carduri + >=80% locatie)")

    t5 = REZ.get("T5")
    filtru = bool(t5 and t5["status"] == 200 and t5["cards"] >= 1
                  and t5["eur_max"] is not None and t5["eur_max"] <= 400)
    if t5 and t5["eur_max"] is None:
        detaliu2 = "fara carduri EUR in T5 — neconcludent"
    else:
        detaliu2 = f"max pret EUR in T5 = {fmt(t5['eur_max']) if t5 else '-'}"
    say(f"  2. Filtru pret pe path oras: {'DA' if filtru else 'NU'}  ({detaliu2})")

    t3 = REZ.get("T3")
    ron_t5 = [c for c in (t5["parsed"] if t5 else []) if c["moneda"] == "RON"]
    ron_t5_over = [c for c in ron_t5 if c["pret_val"] is not None and c["pret_val"] > 400]
    ron_t3 = [c for c in (t3["parsed"] if t3 else []) if c["moneda"] == "RON"]
    if ron_t5_over:
        v3 = "DA"
        nota = (f"{len(ron_t5_over)} anunturi RON cu pret numeric > 400 supravietuiesc "
                f"filtrului :to=400 => comparatie numerica bruta, NU per-moneda")
    elif ron_t5:
        v3 = "DA"
        nota = f"{len(ron_t5)} anunturi RON sub filtru, toate cu valoare numerica <= 400"
    elif ron_t3:
        v3 = "NU"
        nota = (f"0 anunturi RON sub filtru desi T3 avea {len(ron_t3)} "
                f"=> filtrul le taie numeric (valoarea in lei > 400)")
    else:
        v3 = "NU"
        nota = "0 anunturi RON in T5 si T3 — neconcludent"
    say(f"  3. Anunturi RON prezente sub filtru pret: {v3}  ({nota})")

    say("\nGata. Sonda READ-ONLY, niciun fisier scris, nimic comis.")


if __name__ == "__main__":
    main()
