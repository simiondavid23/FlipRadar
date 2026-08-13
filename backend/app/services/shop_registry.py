"""REG-1 — registrul declarativ de magazine: sursa UNICA de metadata per domeniu.

Pana aici, metadatele unui magazin erau imprastiate in trei structuri din doua
fisiere: VALIDATED_DOMAINS si DOMAIN_OVERRIDES (product_page_extractor) plus
_IMPERSONATE_OVERRIDES (scraper_service). Cu ~80 de magazine in plan, fiecare val
nou ar fi trebuit sa scrie in mai multe locuri, iar divergentele dintre ele ar fi
devenit bug-uri TACUTE (un domeniu validat dar fara treapta de impersonate e
validat si necitibil — vezi flanco.ro la CONTENT-2). De aici incolo structura
canonica e SHOP_REGISTRY, iar cele trei structuri istorice se DERIVA din ea.

Modulul e FRUNZA prin constructie: nu importa nimic din `app.*`, doar stdlib.
Asta tine directia importurilor sigura — `product_page_extractor -> shop_registry`
nu poate inchide ciclul documentat in antetul lui scraper_service.

Registrul poarta DATE, nu cod. CUSTOM_EXTRACTORS (care mapeaza domenii la functii)
ramane in product_page_extractor; aici traieste doar metadata `method: "custom"`.
Scraperele de cautare (_SCRAPERS_BY_SOURCE) nu sunt inca reprezentate.

Jurnalul sondelor per domeniu — de ce a intrat fiecare magazin, ce forma de date
publica, ce s-a masurat — sta in `docs/catalog_domain_log.md`. Aici e STAREA
CURENTA; acolo e ISTORICUL. Un val nou adauga intrari aici si o sectiune acolo.

Campurile unei intrari:
  label       — numele magazinului, pentru UI
  category    — electronice | fashion | sneakers | incaltaminte | tcg | outdoor
                | jucarii | foto | beauty
  country     — cod de tara ISO, sau "EU" cand tara exacta nu e confirmata
  delivery    — ro_confirmed   (livreaza in RO, confirmat la sonda)
                ro_storefront  (magazin cu vitrina .ro)
                b2b_only | unconfirmed
  method      — jsonld | og | microdata | custom | shopify | browser
  status      — validated (sonda live trecuta) | probed | planned | watchlist
  currency    — moneda magazinului, masurata la sonda (/cart.js incrucisat cu
                priceCurrency din pagina). OBLIGATORIE cand method == "shopify":
                payload-ul Ajax al Shopify NU poarta moneda, deci registrul e
                singura ei sursa. Optionala altfel (celelalte metode o citesc din
                pagina). Pinuita de test_shopify_cere_moneda.
  url_identity— OPTIONAL, singura valoare permisa: "exact". Marcheaza magazinele
                unde QUERY STRING-ul face parte din identitatea sursei, deci URL-ul
                lipit de user se salveaza ca atare (fara fragment), iar canonicalul
                se ignora. Cerut de flip.ro, unde `?shape=` alege starea produsului
                si odata cu ea pretul (2999.99 cu `?shape=Excelent` vs 2849.99 fara,
                masurat la LOT1). Absent = comportamentul implicit (canonical
                preferat). Consultat in routers/products.py prin url_identity_of().
  impersonate — OPTIONAL, treapta TLS/HTTP2 cand default-ul nu deschide site-ul
  overrides   — OPTIONAL, payload-ul DOMAIN_OVERRIDES (contractul campurilor e
                documentat la structura din product_page_extractor)
  notes       — valul/sonda de origine
"""
import copy

SHOP_REGISTRY: dict[str, dict] = {
    # ── RETAIL-3a ─────────────────────────────────────────────────────────────
    "altex.ro": {
        "label": "Altex",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "RETAIL-3a",
    },
    "emag.ro": {
        "label": "eMAG",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "overrides": {"price_selector": ".product-new-price"},
        "notes": "RETAIL-3a",
    },

    # ── RETAIL-5c ─────────────────────────────────────────────────────────────
    "cel.ro": {
        "label": "CEL.ro",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "RETAIL-5c",
    },
    "vexio.ro": {
        "label": "Vexio",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "RETAIL-5c",
    },
    "mediagalaxy.ro": {
        "label": "Media Galaxy",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "RETAIL-5c",
    },

    # ── FASHION-1b ────────────────────────────────────────────────────────────
    "answear.ro": {
        "label": "Answear",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-1b",
    },
    "fashiondays.ro": {
        "label": "Fashion Days",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-1b",
    },
    "epantofi.ro": {
        "label": "ePantofi",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-1b",
    },
    "modivo.ro": {
        "label": "Modivo",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-1b",
    },

    # ── FASHION-2 ─────────────────────────────────────────────────────────────
    "bstn.com": {
        "label": "BSTN",
        "category": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-2",
    },
    # Cheia e CU subdomeniu: _domain_of taie doar "www.", iar refresh-ul compara
    # pe egalitate exacta. Domeniul GOL (afew-store.com) nu se adauga: redirecteaza
    # spre storefront-ul de.*, iar catalogul e acelasi (acelasi handle, acelasi pret
    # masurate pe ambele la SHOP-1a) — o a doua intrare ar fi acelasi magazin de
    # doua ori.
    "en.afew-store.com": {
        "label": "Afew Store",
        "category": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "FASHION-2, SHOP-1a",
    },

    # ── FASHION-2b ────────────────────────────────────────────────────────────
    "prm.com": {
        "label": "PRM",
        "category": "fashion",
        # Tara exacta NU e confirmata de sonda; se corecteaza la un val viitor,
        # nu se ghiceste.
        "country": "EU",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-2b",
    },
    "sneakersnstuff.com": {
        "label": "Sneakersnstuff",
        "category": "sneakers",
        "country": "SE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-2b",
    },

    # ── FASHION-4 ─────────────────────────────────────────────────────────────
    "aboutyou.ro": {
        "label": "About You",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-4",
    },
    "trendyol.com": {
        "label": "Trendyol",
        "category": "fashion",
        "country": "TR",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-4",
    },

    # ── ACCESS-2 ──────────────────────────────────────────────────────────────
    "endclothing.com": {
        "label": "END.",
        "category": "sneakers",
        "country": "GB",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "ACCESS-2",
    },
    "zalando.ro": {
        "label": "Zalando",
        "category": "fashion",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "ACCESS-2",
    },
    "43einhalb.com": {
        "label": "43einhalb",
        "category": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "impersonate": "firefox135",
        "notes": "ACCESS-2",
    },

    # ── CONTENT-2 ─────────────────────────────────────────────────────────────
    "flanco.ro": {
        "label": "Flanco",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "og",
        "status": "validated",
        "impersonate": "firefox135",
        "notes": "CONTENT-2",
    },
    "evomag.ro": {
        "label": "evoMAG",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        "notes": "CONTENT-2",
    },

    # ── DISCOVERY-2 ───────────────────────────────────────────────────────────
    "footshop.ro": {
        "label": "Footshop",
        "category": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        "notes": "DISCOVERY-2",
    },
    "asos.com": {
        "label": "ASOS",
        "category": "fashion",
        "country": "GB",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "validated",
        "notes": "DISCOVERY-2",
    },

    # ── SHOP-1a ───────────────────────────────────────────────────────────────
    # Primul val de magazine Shopify: extractia nu mai trece prin HTML, ci prin
    # endpoint-ul Ajax /products/<handle>.js (singurul per-produs care poarta
    # `available`). Moneda vine de aici, din registru — payload-ul nu o contine.
    "asphaltgold.com": {
        "label": "Asphaltgold",
        "category": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a",
    },
    "footdistrict.com": {
        "label": "Footdistrict",
        "category": "sneakers",
        "country": "ES",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a",
    },
    "overkillshop.com": {
        "label": "Overkill",
        "category": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a; livrare de reverificat periodic (nota lista master)",
    },
    "nakedcph.com": {
        "label": "NAKED Copenhagen",
        "category": "sneakers",
        "country": "DK",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a; ld+json rotunjeste pretul la intreg, nesigur ca sursa",
    },
    "caliroots.com": {
        "label": "Caliroots",
        "category": "sneakers",
        "country": "SE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "SEK",
        "notes": "SHOP-1a",
    },
    "patta.nl": {
        "label": "Patta",
        "category": "sneakers",
        "country": "NL",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a",
    },
    "slamjam.com": {
        "label": "Slam Jam",
        "category": "sneakers",
        "country": "IT",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "notes": "SHOP-1a",
    },
    "redgoblin.ro": {
        "label": "Red Goblin",
        "category": "tcg",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-1a",
    },
    "ada-shoes.ro": {
        "label": "Ada Shoes",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-1a",
    },
    "rocashoes.ro": {
        "label": "Roca Shoes",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-1a",
    },
    "shopium.ro": {
        "label": "Shopium",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-1a",
    },
    "sosukicks.ro": {
        "label": "Sosu Kicks",
        "category": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-1a",
    },

    # ── LOT1 — electronice RO (sonda 2026-08-13) ──────────────────────────────
    # Primul val in care extractorul EXISTENT a fost rulat pe HTML-ul capturat
    # (parse_product_html e pura), nu reimplementat in sonda. Toate 8 domeniile au
    # raspuns pe treapta IMPLICITA de impersonare — niciun `impersonate` de adaugat.
    "itgalaxy.ro": {
        "label": "IT Galaxy",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT1",
    },
    "carrefour.ro": {
        "label": "Carrefour",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT1",
    },
    "flip.ro": {
        "label": "Flip",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "url_identity": "exact",
        "notes": "LOT1; ?shape= semantic — starea e parte din identitatea sursei",
    },
    "usedproducts.ro": {
        "label": "Used Products",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT1; bucati unice second-hand, comportamentul la vandut nemasurat",
    },
    "senetic.ro": {
        "label": "Senetic",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "overrides": {"vat_prices": True},
        "notes": "LOT1; ld+json = pret net (fara TVA), microdata = brut; "
                 "raport 1.21 masurat 3/3",
    },
    "pcgarage.ro": {
        "label": "PC Garage",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        "notes": "LOT1; deblocat de scoparea nested; refresh migrat de pe calea "
                 "dedicata pe cea generica",
    },
    "orange.ro": {
        "label": "Orange",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "probed",
        "notes": "LOT1: CSR real — 339KB, titlu generic, zero purtatori de pret in "
                 "HTML-ul initial; Grup 4",
    },
    "powerup.ro": {
        "label": "PowerUp",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "custom",
        "status": "probed",
        "notes": "LOT1: SSR fara date structurate; .discount-price candidat de "
                 "selector (capcana: .total-price=0,00 al cosului); micro-sonda pe "
                 "produse NEreduse inainte de validare",
    },

    # ── LOT2 / LOT2b — tinte usoare straine (sonde 2026-08-13) ────────────────
    # Doua sonde: LOT2 si-a DESCOPERIT singura produsele (samanta outlet/sale ->
    # ancore filtrate -> confirmare), LOT2b a completat pe link-uri manuale ce
    # descoperirea n-a scos. Toate au raspuns pe treapta implicita de impersonare.
    "computeruniverse.net": {
        "label": "computeruniverse",
        "category": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2; aterizare pe storefront /de, EUR",
    },
    "jb-spielwaren.de": {
        "label": "JB Spielwaren",
        "category": "jucarii",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2; plentyShop; LEGO retired + SALE",
    },
    "caseking.de": {
        "label": "Caseking",
        "category": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b; /en localizat lingvistic, moneda EUR; sku/mpn prezente pe "
                 "pagina de produs",
    },
    "bergfreunde.eu": {
        "label": "Bergfreunde",
        "category": "outdoor",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b; OXID; ProductGroup cu variesBy size+color — primul client "
                 "al etichetei compuse",
    },
    "alternate.de": {
        "label": "Alternate",
        "category": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b",
    },
    "foto-erhardt.com": {
        "label": "Foto Erhardt",
        "category": "foto",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b; starea second-hand traieste doar in calea URL "
                 "(itemCondition absent); bucati unice, comportament la vandut nemasurat",
    },
    # ── LOT3 / LOT3b — fashion RO (sonde 2026-08-13) ──────────────────────────
    "buzzsneakers.ro": {
        "label": "Buzz Sneakers",
        "category": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3",
    },
    "officeshoes.ro": {
        "label": "Office Shoes",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        "notes": "LOT3",
    },
    "otter.ro": {
        "label": "Otter",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3b; ProductGroup cu hasVariant si variesBy=[size] — "
                 "marimile ies deja ca variante",
    },
    "spartoo.ro": {
        "label": "Spartoo",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3b; og:type propriu (non-standard); site-ul tolereaza dublu "
                 "slash in cale — normalizat la salvare (C3)",
    },
    "boozt.com": {
        "label": "Boozt",
        "category": "fashion",
        "country": "DK",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3b; storefront /eu/en, EUR; variante DOAR pe colorway "
                 "(variesBy=color), marimile absente din date — UI sa nu promita "
                 "selectie pe marime",
    },
    "booztlet.com": {
        "label": "Booztlet",
        "category": "fashion",
        "country": "DK",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3b; outlet integral, sora boozt; aceleasi variante doar pe "
                 "colorway; EUR",
    },
    # ── LOT4 / LOT4b — beauty/parfumuri (sonde 2026-08-13) ────────────────────
    "marionnaud.ro": {
        "label": "Marionnaud",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT4",
    },
    "notino.ro": {
        "label": "Notino",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "impersonate": "firefox135",
        "notes": "LOT4; deschis pe treapta din campul impersonate",
    },
    "parfumdreams.de": {
        "label": "Parfumdreams",
        "category": "beauty",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT4; pret in priceSpecification — clientul fix-ului de moneda; "
                 "Grundpreis inchis manual: pretul e al flaconului",
    },
    "douglas.ro": {
        "label": "Douglas",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT4b; o pagina per volum, fara variante — fiecare volum e sursa "
                 "proprie; incadrarea Grup 3 din descoperire corectata: esec de "
                 "ordonare, nu de site",
    },
    "sephora.ro": {
        "label": "Sephora",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "probed",
        "notes": "LOT4: 403 cu corp 519B pe toate treptele; candidat Grup 4",
    },
    "makeup.ro": {
        "label": "Makeup",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "probed",
        "notes": "LOT4b: interstitiu JS servit cu 202, corp identic la octet pe "
                 "toate treptele — nu e amprenta TLS; candidat Grup 4",
    },
    "hhv.de": {
        "label": "HHV",
        "category": "fashion",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "browser",
        "status": "probed",
        "notes": "LOT2: challenge servit pe 200 — corp ~2KB JS obfuscat, zero "
                 "ancore, fara titlu; candidat Grup 4 (browser)",
    },
}


# Derivarile intorc de fiecare data un OBIECT PROASPAT, niciodata o referinta in
# registru. Consumatorii isi tin copia proprie la nivel de modul, iar suita
# existenta o monkeypatcheaza (ex. adaugarea unui domeniu de test in
# VALIDATED_DOMAINS); fara copie, mutatia s-ar propaga in registru si de acolo in
# toti ceilalti consumatori, intre teste.

def validated_domains() -> set[str]:
    """Domeniile cu status == "validated"."""
    return {domain for domain, meta in SHOP_REGISTRY.items()
            if meta.get("status") == "validated"}


def domain_overrides() -> dict[str, dict]:
    """Domeniu -> payload overrides, doar intrarile care au cheia.

    Copia e adanca: payload-ul e el insusi un dict mutabil, deci o copie doar a
    dict-ului exterior ar lasa consumatorii sa scrie inapoi in registru.
    """
    return {domain: copy.deepcopy(meta["overrides"])
            for domain, meta in SHOP_REGISTRY.items() if "overrides" in meta}


def impersonate_overrides() -> dict[str, str]:
    """Domeniu -> treapta impersonate, doar intrarile care au cheia."""
    return {domain: meta["impersonate"]
            for domain, meta in SHOP_REGISTRY.items() if "impersonate" in meta}


def url_identity_of(domain: str) -> str | None:
    """Politica de identitate a URL-ului pentru un domeniu, sau None (implicit).

    Lookup direct, fara copie: valoarea e un scalar imutabil, deci n-are cum sa fie
    mutata de apelant — spre deosebire de set-urile si dict-urile de mai sus.
    """
    return (SHOP_REGISTRY.get(domain) or {}).get("url_identity")


def shopify_domains() -> set[str]:
    """Domeniile servite de extractorul generic Shopify (method == "shopify").

    Apartenenta se decide din `method`, nu dintr-o lista paralela: un magazin nu
    poate fi marcat shopify aici si uitat dincolo.
    """
    return {domain for domain, meta in SHOP_REGISTRY.items()
            if meta.get("method") == "shopify"}
