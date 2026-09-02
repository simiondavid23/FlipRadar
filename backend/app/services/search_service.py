"""SEARCH-1b — cautarea dupa termen, generica peste toate mecanismele.

Pana aici, cautarea exista doar ca cinci scrapere scrise de mana
(`scraper_service._SCRAPERS_BY_SOURCE`), fiecare cu ruta lui in router si cu forma
lui de raspuns. Modulul asta pune un CONTRACT UNIC peste patru mecanisme — cele
cinci scrapere istorice plus trei generice masurate la SEARCH-0 — ca pagina
„Scanare Magazine" sa poata interoga orice magazin din registru fara sa stie cum e
citit.

Mecanismul se alege din registru (`search.kind`), nu din cod: un magazin nou intra
adaugand un descriptor `search`, fara sa se atinga fisierul asta.

Ce NU face, deliberat:
  * nu pagineaza — cautarea pe descriptori citeste doar PRIMA pagina, fiindca
    paginarea cautarii n-a fost masurata la SEARCH-0;
  * nu ghiceste `ean`/`sku`/`category`/`subcategory` pe mecanismele generice si nu
    cheama `infer_category_from_name` — inferenta de categorie e o decizie separata,
    cu sonda ei;
  * nu filtreaza rezultatele dupa relevanta. Motorul magazinului a potrivit deja
    termenul; filtrul din router are alt rol si se aplica doar pe calea `custom`.
"""
import json
import urllib.parse

from app.services.shop_registry import (
    SHOP_REGISTRY,
    browser_domains,
    catalog_api_descriptor,
    search_descriptor,
    search_kind_of,
)
from app.services.scraper_service import (
    _SCRAPERS_BY_SOURCE,
    _emit_catalog,
    _fetch_shop_url_guarded,
)
from app.services.listing_scanner import extrage_carduri, _HEADERS as _HEADERS_HTML
from app.services.api_scanner import _prima_oferta, _HEADERS as _HEADERS_JSON
from app.services.log_manager import log_manager

_TIMEOUT = 25

# Plafonul Shopify e FIX, nu configurabil: masurat la SEARCH-0 pe 3 magazine,
# `resources[limit]=50` intoarce un raspuns BYTE-IDENTIC cu `limit=10`.
_SHOPIFY_PLAFON = 10

# Fereastra VTEX (`_from`/`_to`). f64 raspunde 206 cand fereastra se umple complet.
_VTEX_FEREASTRA = 50

_MOTIV_BLOCAT = "magazinul a blocat cererea sau nu a raspuns"
_MOTIV_BROWSER = "necesita browser — exclus din cautare"
_MOTIV_FARA_SEARCH = "doar prin link"


def _rezultat(*, name, price, original_price, currency, source, source_url,
              image_url, in_stock, sku=None, ean=None):
    """Forma UNICA a unui rezultat, identica cu cea produsa de scraperele istorice.

    Se pastreaza cheie cu cheie (inclusiv cele care raman None pe mecanismele
    generice) fiindca `saveProduct` din frontend si `filter_by_*` din scraper_service
    citesc exact numele astea — un rezultat cu alta forma le-ar rupe tacut.
    """
    return {
        "name": name,
        "price": price,
        "original_price": original_price,
        "is_on_sale": original_price is not None,
        "currency": currency,
        "source": source,
        "source_url": source_url,
        "image_url": image_url,
        "in_stock": in_stock,
        "ean": ean,
        "sku": sku,
        "category": None,
        "subcategory": None,
    }


def _numar(valoare):
    """`float` tolerant: None pe orice nu se converteste.

    Shopify da preturile ca STRING ("134.10", masurat la SEARCH-0), VTEX ca numar,
    iar descriptorii ca float parsat deja de `extrage_carduri` — o singura functie
    le acopera pe toate, fara sa ghiceasca nimic cand valoarea lipseste.
    """
    if valoare is None or isinstance(valoare, bool):
        return None
    try:
        return float(valoare)
    except (TypeError, ValueError):
        return None


def _trunchiat(n_brut, max_results, plafon):
    """„Pot exista rezultate nearatate" — regula UNICA, pentru toate mecanismele.

    `n_brut` e cate elemente a intors magazinul/scraperul INAINTE de orice taiere sau
    sarire, nu cate au supravietuit: un produs sarit pentru pret neparsabil nu spune
    nimic despre existenta altora, iar `carduri[:max_results]` taie tacut.

    Doua motive independente, ambele „mai sunt":
      * `n_brut > max_results` — noi am cerut mai putin decat a dat magazinul;
      * `n_brut == plafon`     — magazinul a dat exact cat ii permite plafonul lui,
                                 deci lista lui e probabil taiata la sursa.
    Plafonul difera per mecanism (10 la shopify, fereastra la vtex, `max_results` la
    descriptor si custom), dar regula nu — de aceea sta intr-un singur loc.
    """
    return n_brut > max_results or n_brut == plafon


def _referinta(referinta, pret):
    """Pretul de referinta e valid DOAR daca e strict peste cel curent.

    Masurat la SEARCH-0: pe Shopify `compare_at_price_min` e "0.00" cand nu exista
    reducere, NU `null`. Fara verificarea asta, orice produs fara reducere ar iesi cu
    `original_price=0.0` si `is_on_sale=True` — o reducere fantoma de 100%.
    """
    referinta = _numar(referinta)
    if referinta is None or pret is None or referinta <= pret:
        return None
    return referinta


# ── mecanismele ──────────────────────────────────────────────────────────────

def _cauta_shopify(domain, meta, query, max_results):
    q = urllib.parse.quote(query)
    url = (f"https://{domain}/search/suggest.json?q={q}"
           f"&resources[type]=product&resources[limit]={_SHOPIFY_PLAFON}")
    raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS_JSON, timeout=_TIMEOUT)
    if raspuns is None:
        return {"status": "blocked", "reason": _MOTIV_BLOCAT}

    date = json.loads(raspuns.text)
    produse = (((date.get("resources") or {}).get("results") or {})
               .get("products"))
    if not isinstance(produse, list):
        return {"status": "empty"}

    rezultate = []
    for produs in produse:
        pret = _numar(produs.get("price"))
        if pret is None or pret <= 0:
            continue                    # fara pret parsabil nu se ghiceste nimic
        cale = produs.get("url") or ""
        rezultate.append(_rezultat(
            name=produs.get("title"),
            price=pret,
            # Perechea masurata: `compare_at_price_min`, nu `compare_at_price` —
            # campul din urma NU EXISTA in payload-ul `suggest.json` (SEARCH-0).
            original_price=_referinta(produs.get("compare_at_price_min"), pret),
            currency=meta.get("currency"),
            source=domain,
            # `url` e relativ si poarta `?_pos=…&_psq=…`. Se PASTREAZA: e tracking
            # intern Shopify, nu schimba produsul tintit.
            source_url=f"https://{domain}{cale}" if cale else None,
            image_url=produs.get("image"),
            in_stock=produs.get("available"),
        ))

    return {
        "status": "ok" if rezultate else "empty",
        "results": rezultate,
        "n_brut": len(produse),
        "plafon": _SHOPIFY_PLAFON,
        "more_url": f"https://{domain}/search?q={q}&type=product",
    }


def _cauta_vtex(domain, meta, query, max_results):
    descriptor = catalog_api_descriptor(domain) or {}
    baza = descriptor.get("base") or ""
    endpoint = descriptor.get("endpoint") or ""
    q = urllib.parse.quote(query)
    pana_la = max(min(max_results, _VTEX_FEREASTRA), 1) - 1
    url = f"{baza}{endpoint}?ft={q}&_from=0&_to={pana_la}"

    raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS_JSON, timeout=_TIMEOUT)
    if raspuns is None:
        return {"status": "blocked", "reason": _MOTIV_BLOCAT}
    # 206 e normal, nu o eroare: VTEX raspunde „partial content" cand fereastra
    # ceruta se umple complet (masurat la SEARCH-0, 50/50 pe `sony alpha`).
    status = getattr(raspuns, "status_code", None)
    if status not in (200, 206):
        return {"status": "error", "reason": f"raspuns neasteptat: HTTP {status}"}

    produse = json.loads(raspuns.text)
    if not isinstance(produse, list):
        return {"status": "empty"}

    rezultate = []
    for produs in produse:
        # NU `_extrage_produse`: acela sare produsele indisponibile, fiindca e scris
        # pentru feed-ul de deal-uri. La o CAUTARE un produs epuizat e informatie —
        # userul vrea sa stie ca magazinul il are in catalog dar nu pe stoc.
        oferta = _prima_oferta(produs) or {}
        pret = _numar(oferta.get("Price"))
        if pret is None or pret <= 0:
            continue
        articole = produs.get("items") or []
        imagini = (articole[0].get("images") or []) if articole else []
        rezultate.append(_rezultat(
            name=produs.get("productName"),
            price=pret,
            original_price=_referinta(oferta.get("ListPrice"), pret),
            currency=descriptor.get("currency"),
            source=domain,
            source_url=produs.get("link"),
            image_url=(imagini[0].get("imageUrl") if imagini else None),
            in_stock=oferta.get("IsAvailable"),
        ))

    return {
        "status": "ok" if rezultate else "empty",
        "results": rezultate,
        "n_brut": len(produse),
        # Fereastra CERUTA, nu constanta: `_to` e inclusiv, deci plafonul real al
        # raspunsului e `pana_la + 1`.
        "plafon": pana_la + 1,
        # Pagina de cautare a magazinului. Confirmata 200 la verificarea SEARCH-1 §5.
        "more_url": f"{baza}/{q}?_q={q}&map=ft",
    }


def _cauta_descriptor(domain, meta, query, max_results):
    descriptor = search_descriptor(domain) or {}
    url = descriptor["url_template"].format(q=urllib.parse.quote(query))
    raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS_HTML, timeout=_TIMEOUT)
    if raspuns is None:
        return {"status": "blocked", "reason": _MOTIV_BLOCAT}

    # Doar PRIMA pagina — paginarea cautarii nu e masurata (vezi docstringul).
    carduri = extrage_carduri(raspuns.text, descriptor, domain)
    rezultate = [
        _rezultat(
            name=card.get("title"),
            price=card.get("price"),
            original_price=card.get("compare_at"),
            currency=descriptor.get("currency"),
            source=domain,
            source_url=card.get("url"),
            image_url=card.get("image_url"),
            # Descriptorul de listare nu poarta stocul pe niciunul din cele doua
            # domenii masurate, deci None („necunoscut"), nu True.
            in_stock=None,
        )
        for card in carduri[:max_results]
    ]
    return {
        "status": "ok" if rezultate else "empty",
        "results": rezultate,
        # Numarate INAINTE de `[:max_results]`: taierea e a noastra, si exact ea e
        # ce trebuie semnalat. Masurat la SEARCH-0: bergfreunde da 72 de carduri la
        # `salomon`, din care implicit aratam 50.
        "n_brut": len(carduri),
        "plafon": max_results,
        "more_url": url,
    }


def _cauta_custom(domain, meta, query, max_results):
    # Termenul se taie la 80 de caractere ca in router-ul istoric.
    brute = _SCRAPERS_BY_SOURCE[domain](query[:80], max_results) or []
    # `n_brut` e cat a intors SCRAPERUL, sentinelele incluse: ele sunt tot ce a
    # intors, iar un raspuns care e doar sentinela are oricum 1 element, mult sub
    # plafon, deci nu poate declara fals „mai sunt".
    return {**_curata_sentinele(brute),
            "n_brut": len(brute), "plafon": max_results}


def _curata_sentinele(brute):
    """Scoate sentinelele istorice si le traduce in `status`.

    Scraperele scrise de mana semnaleaza „nimic gasit" si „a picat" prin elemente
    speciale in aceeasi lista cu produsele (`{"message": …}` / `{"error": …}`). Erau
    randate de frontend ca atare; aici NU au voie sa iasa, fiindca ar aparea in UI ca
    produse fara pret. Informatia lor trece in `status`/`reason`.
    """
    reale, mesaje, erori = [], [], []
    for element in brute:
        if not isinstance(element, dict):
            continue
        if element.get("error"):
            erori.append(str(element["error"]))
        elif element.get("message"):
            mesaje.append(str(element["message"]))
        else:
            reale.append(element)

    if reale:
        return {"status": "ok", "results": reale}
    # Eroarea are prioritate peste „gol": daca scraperul a picat, „0 rezultate" ar fi
    # un raspuns fals linistitor.
    if erori:
        return {"status": "error", "reason": erori[0][:120]}
    return {"status": "empty"}


_MECANISME = {
    "shopify": _cauta_shopify,
    "vtex": _cauta_vtex,
    "descriptor": _cauta_descriptor,
    "custom": _cauta_custom,
}


# ── contractul public ────────────────────────────────────────────────────────

def search(domain: str, query: str, max_results: int = 50) -> dict:
    """Cauta `query` pe `domain`, prin mecanismul declarat in registru.

    SINCRONA: toate fetch-urile de dedesubt sunt sincrone (`curl_cffi`), iar
    router-ul o ruleaza in `asyncio.to_thread`, exact ca wrapper-ele `scrape_*`.

    `status`:
      ok          — cel putin un rezultat real;
      empty       — zero rezultate, dar magazinul A RASPUNS;
      blocked     — poarta a intors None. ATENTIE: poarta NU distinge intre blocaj
                    anti-bot, timeout si eroare de retea — toate trei ies la fel
                    (vezi `_fetch_shop_url_guarded`), deci nici `reason` nu poate fi
                    mai precis de atat;
      error       — exceptie in parsare sau in scraper; `reason` e mesajul taiat la
                    120 de caractere, niciodata un traceback (ajunge in UI);
      unsupported — domeniul nu are `search`, sau cere browser.

    `truncated` inseamna „POT EXISTA rezultate nearatate" — fie magazinul a dat mai
    mult decat am cerut, fie a dat exact cat ii permite plafonul lui. Se calculeaza
    la fel pe toate mecanismele (vezi `_trunchiat`); nu e specific Shopify.

    Un domeniu care nu e DELOC in registru ridica `ValueError` — e o greseala de
    apelant, nu o stare a magazinului, iar router-ul o traduce in 404.
    """
    meta = SHOP_REGISTRY.get(domain)
    if meta is None:
        raise ValueError(f"Magazin necunoscut: {domain}")

    label = meta.get("label") or domain
    kind = search_kind_of(domain)

    # Browser-ul se verifica INAINTEA lui `kind`: e motivul cel mai specific, iar
    # registrul oricum interzice combinatia (pinuit de test).
    if domain in browser_domains():
        return _raspuns(domain, label, kind, status="unsupported",
                        reason=_MOTIV_BROWSER)
    if kind not in _MECANISME:
        return _raspuns(domain, label, kind, status="unsupported",
                        reason=_MOTIV_FARA_SEARCH)

    try:
        brut = _MECANISME[kind](domain, meta, query, max_results)
    except Exception as exc:                                     # noqa: BLE001
        brut = {"status": "error", "reason": str(exc)[:120]}

    raspuns = _raspuns(domain, label, kind, max_results=max_results, **brut)

    # Jurnalul spune ce s-a intamplat CU ADEVARAT, si de aceea nu e o singura linie
    # pentru toate starile:
    #
    #   ok / empty  — linia SCAN normala. `empty` e o interogare reusita cu 0
    #                 rezultate, deci merita exact aceeasi linie ca `ok`.
    #   error       — WARN, nu SCAN. O linie SCAN aici ar AFIRMA o interogare normala
    #                 cu 0 rezultate, ascunzand exceptia — jurnalul ar arata identic
    #                 cu „magazinul n-are produsul", ceea ce e fals.
    #   blocked     — NIMIC. Poarta a scris deja WARN-ul ei la clasificare
    #                 (`_clasifica_raspuns`), iar o a doua linie ar fi duplicat.
    #   unsupported — nu ajunge aici (iese mai sus): n-a plecat nicio cerere.
    if raspuns["status"] in ("ok", "empty"):
        _emit_catalog(label, query, raspuns["results"])
    elif raspuns["status"] == "error":
        log_manager.emit(
            "catalog", "WARN",
            f"{label}: cautare esuata pentru '{query}' — {raspuns['reason']}")
    return raspuns


def _raspuns(domain, label, kind, *, status, reason=None, results=None,
             n_brut=0, plafon=None, max_results=0, more_url=None):
    """Ambaleaza contractul, cu invariantele lui aplicate intr-un singur loc:
    `results` e goala pe orice status != ok, `count` o urmeaza mereu, iar `truncated`
    se CALCULEAZA aici — mecanismele raporteaza doar `n_brut` si `plafon`, ca regula
    sa existe intr-o singura copie.

    `plafon is None` inseamna „n-a rulat niciun mecanism" (unsupported): acolo nu
    exista nimic nearatat, deci `truncated` e fals prin constructie.
    """
    rezultate = list(results or []) if status == "ok" else []
    trunchiat = (status == "ok" and plafon is not None
                 and _trunchiat(n_brut, max_results, plafon))
    return {
        "source": domain,
        "label": label,
        "kind": kind,
        "status": status,
        "reason": reason,
        "results": rezultate,
        "count": len(rezultate),
        "truncated": trunchiat,
        "more_url": more_url,
    }


def sources() -> list[dict]:
    """Toate magazinele din registru, pentru selectorul din „Scanare Magazine".

    Se intorc TOATE, nu doar cele cautabile: pagina le arata si pe cele dezactivate,
    cu motivul in tooltip (D2). Un magazin filtrat de aici ar disparea din UI fara
    explicatie, iar userul ar crede ca nu exista.
    """
    browsere = browser_domains()
    iesire = []
    for domain, meta in SHOP_REGISTRY.items():
        kind = search_kind_of(domain)
        cautabil = kind in _MECANISME and domain not in browsere

        motiv = None
        if not cautabil:
            motiv = _MOTIV_BROWSER if domain in browsere else _MOTIV_FARA_SEARCH

        # Moneda: din registru unde e declarata (obligatoriu pe shopify), altfel din
        # descriptorul mecanismului. Ramane None pe `jsonld`/`custom`, unde se
        # citeste din PAGINA la extractie — nu se inventeaza aici.
        moneda = meta.get("currency")
        if moneda is None and kind == "vtex":
            moneda = (catalog_api_descriptor(domain) or {}).get("currency")
        elif moneda is None and kind == "descriptor":
            moneda = (search_descriptor(domain) or {}).get("currency")

        iesire.append({
            "domain": domain,
            "label": meta.get("label") or domain,
            "category": meta.get("category"),
            "country": meta.get("country"),
            "currency": moneda,
            "kind": kind,
            "searchable": cautabil,
            "reason": motiv,
            "truncated_at": _SHOPIFY_PLAFON if kind == "shopify" else None,
        })

    iesire.sort(key=lambda s: (s["label"] or "").lower())
    return iesire
