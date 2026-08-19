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
  headed      — OPTIONAL, DOAR pe method == "browser": True cere fereastra reala
                (headless=False). Nu e preferinta, ci masuratoare: hhv.de raspunde
                headless cu ERR_CONNECTION_RESET si sephora.ro cu 403, iar headed
                trec amandoua (G4/G4b). Costa mai mult — pe server cere xvfb — deci
                se pune doar unde s-a dovedit necesar. Implicit: headless.
  ldjson_availability
              — OPTIONAL, valoarea admisa: "untrusted". Spune ca `availability` din
                ld+json e o CONSTANTA de sablon pe acest domeniu, nu o masuratoare,
                deci extractorul o ignora si lasa `in_stock=None` (necunoscut) in
                loc sa creada sablonul. Aparut pentru ro.vivre.eu (G2F-6), unde
                PDP-urile dau `OutOfStock` pe produse pe care datele proprii de
                listare le marcheaza `"inStock":true`. Absent = availability se
                citeste normal.
  min_fetch_interval_s
              — OPTIONAL, DOAR pe method == "browser": secunde minime intre doua
                vizite ale harness-ului pe domeniu. Sub prag, fetch-ul e refuzat
                FARA a lansa browser, iar refresh-ul pastreaza pretul anterior.
                Aparut pentru sephora.ro, care limiteaza progresiv; pragul real nu
                e masurat (sonda G4b si-a invalidat propria masuratoare), deci
                valoarea e o estimare prudenta care se urca din registru daca apar
                blocaje. Absent = fara limitare.
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
        "status": "validated",
        "notes": "G4: CSR — jsonld apare in DOM-ul randat; headless",
    },
    "powerup.ro": {
        "label": "PowerUp",
        "category": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "custom",
        "status": "validated",
        "notes": "LOT1 + G2A-1/G2A-2; OpenCart cu tema proprie, SSR fara NICIO data "
                 "structurata (zero ld+json, zero microdata, zero OG de pret) — de "
                 "aici extractorul custom `powerup_opencart`. Pretul platit: "
                 ".product-price .discount-price, ancorat OBLIGATORIU in "
                 ".product-price fiindca `.discount-price` apare si in bara de sus "
                 "ca `.nav-price`; `.price-unit` ('/ buc.') se scoate inainte de "
                 "parsare. CAPCANA TRANSATA: `.total-price` NU e pretul paginii — e "
                 "COSUL, masurat identic 0,00 LEI pe doua produse cu preturi "
                 "complet diferite (testul de componente partajate, G2A-1). "
                 "Referinta taiata sta in .product-price .full-price si e prezenta "
                 "DOAR la produsele reduse (masurat pe caruselul SH: 15/15 au "
                 "discount-price, 7/15 n-au full-price) — nu intra in contractul "
                 "extractorului de pagina, doar in descriptorul de listare. "
                 "Zecimalele stau in <sup>, deci textul se ia cu separator GOL. "
                 "Moneda vine din COD (RON): nu e nicaieri in pagina ca data "
                 "structurata. Stocul e None NEMASURAT — nicio pagina de produs "
                 "epuizat nu a fost sondata, iar pe SH produsele sunt bucati unice. "
                 "RISC DE CALITATE: titlurile difera pe TREI surse pentru acelasi "
                 "produs (slug 'ryzen-9-9950x3d...rtx-5090', ancora din listare "
                 "'Ryzen 7 9800X3D...RTX 5080', <title> 'Ryzen 9 9950X...RTX 5080'), "
                 "iar <h1> e GOL — vezi docs/catalog_domain_log.md",
        # DEAL-2 — masurat in G2A-1: „Afişare 1 - 40 din 605 (16 pagini)".
        # DOAR /refurbished-sh: /oferte-speciale (5.668 produse, 142 pagini) asteapta
        # extensia multi-listing per domeniu, la valul D.
        "listing": {
            "url": "https://www.powerup.ro/refurbished-sh",
            "page_url_template": "https://www.powerup.ro/refurbished-sh?page={n}",
            "max_pages": 20,
            "currency": "RON",
            # `products5` e OBLIGATORIU, nu decorativ: fara el selectorul prinde si
            # caruselul de recomandari (55 de noduri in loc de 40 pe dump-ul SH),
            # adica exact capcana caruselului din LOT5.
            "card": "div.item-display-box.products5",
            # Fiecare card poarta DOUA ancore catre acelasi produs: slug-ul si
            # `index.php?route=product/quickview&product_id=<id>`. Excluderea se
            # face pe schema EXISTENTA, printr-un selector CSS negativ — ancora de
            # quickview e singura cu clasa `quickview`. Verificat pe toate cele 40
            # de carduri ale dump-ului: zero cazuri in care selectorul cade pe ea.
            "link": "a:not(.quickview)",
            # Titlul vine din textul aceleiasi ancore (cardul n-are h2/h3 de nume).
            # Vezi riscul de calitate din `notes`: titlul poate descrie alta
            # configuratie decat produsul de la acel URL.
            "title": "a:not(.quickview)",
            # Pe text, nu pe atribut: tema nu expune valoarea numerica nicaieri.
            # `eu_comma` digera forma cu <sup> fara modificari — verificat in G2A-2:
            # el curata orice non-cifra/punct/virgula, deci si spatiul pe care
            # `get_text(" ")` al scannerului il insereaza intre intreg si zecimale.
            "price_text": ".discount-price",
            "compare_text": ".full-price",
            "price_parse": "eu_comma",
            # Omnibus masurat ABSENT: nici pe cele doua listari, nici pe PDP-uri.
            "reference_kind": "nemarcat",
        },
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
        # DEAL-2 — masurat in LST-1: 34 de pagini a 40 de produse (1.338 Results).
        # Oprirea reala e grila GOALA pe 200, nu 404; `max_pages` e doar plasa.
        "listing": {
            "url": "https://www.caseking.de/en/sale",
            "page_url_template": "https://www.caseking.de/en/sale?page={n}",
            "max_pages": 40,
            "currency": "EUR",
            "card": "div.product-tile",
            "link": "a[href]",
            "title_from": "link_aria_label",
            # Atributul `content` poarta zecimala cu PUNCT ("619.90"), deci nu
            # trecem prin textul vizibil ("619,70 €") si prin parserul de virgula.
            "price_attr": ("span.sales .value", "content"),
            "compare_attr": ("span.sales-original .value", "content"),
            "price_parse": "attr_float",
            "stock_attr": ("[data-available]", "data-available", "in-stock"),
            "reference_kind": "nemarcat",
        },
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
        # DEAL-2 — masurat in LST-1/1b: 190 de pagini a 72 de produse (13.638),
        # paginare pe CALE, iar pagina 500 CLAMEAZA la ultima pagina (30 de carduri,
        # zero overlap) — deci oprirea cere regula de linkuri deja vazute.
        "listing": {
            "url": "https://www.bergfreunde.eu/outlet/",
            "page_url_template": "https://www.bergfreunde.eu/outlet/{n}/",
            "max_pages": 200,
            "currency": "EUR",
            "card": "li.product-item",
            "link": "a.product-link",
            # NU `link_aria_label`: pe bergfreunde `aria-label` e o FRAZA de
            # accesibilitate care include si preturile ("Brand: …; Original price:
            # € 79,95; Price: € 47,97; The product is reduced by 40%; …"), deci ar
            # umple feed-ul cu titluri de 250 de caractere. `div.product-title` sta
            # in acelasi dump si da "Women's Flower Boots Tee Merino shirt".
            "title": "div.product-title",
            "price_text": "[data-codecept='currentPrice']",
            # Rezerva documentata: aceeasi valoare sta si pe `span.uvp`, clasa pe
            # care CSS-ul o taie (`.product-price .uvp{text-decoration:line-through}`).
            "compare_text": "[data-codecept='strokePrice']",
            "price_parse": "eu_comma",
            # LST-1b: exista un camp "Lowest price in the last 30 days" DAR e
            # `!hidden`, gol si in spatele unui A/B test oprit. Taiatul e `uvp`,
            # etichetat "Original price" — deci referinta e PRP, nu minim 30 de zile.
            "reference_kind": "prp",
        },
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
    # ── G2B — lotul EU de electronice (sonda 2026-08-18) ──────────────────────
    # Din cele 5 domenii sondate a intrat DOAR cyberport.at. Celelalte patru si
    # motivele lor sunt in docs/catalog_domain_log.md: pccomponentes.com si
    # notebooksbilliger.de sunt Grup 4 (Cloudflare, respectiv Akamai), reichelt.com
    # redirectioneaza spre .de si nu expune produse in listari, iar conrad.com isi
    # randeaza listarile client-side.
    "cyberport.at": {
        "label": "Cyberport",
        "category": "electronice",
        "country": "AT",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # Amprenta implicita a productiei ia challenge Cloudflare pe acest domeniu;
        # profilul de aici trece. Ca la elefant.ro, valoarea concreta NU se comenteaza
        # in text: garda test_niciun_profil_hardcodat_vechi_in_app face grep pe
        # app/**, iar tabelul complet al profilelor sta in docs/catalog_domain_log.md.
        "impersonate": "chrome",
        "notes": "G2B-1/G2B-2; Next.js. ld+json complet pe PDP: Product + Offer cu "
                 "price / priceCurrency EUR / availability, plus sku, gtin13, brand, "
                 "priceValidUntil, priceSpecification, shippingDetails si "
                 "hasMerchantReturnPolicy — ofertele se citesc INTEGRAL, nu doar "
                 "prima. Moneda incrucisata: EUR in date structurate SI € in afisaj. "
                 "Referinta taiata e o ETICHETA TEXTUALA, nu un <del>/<s>: verbatim "
                 "„Store 1.299,00 € UVP 1.279,00 € inkl. MwSt.\", deci Omnibus e de "
                 "tip PRP/UVP, iar ld+json poarta PLATITUL (1.279), nu UVP-ul. "
                 "ATENTIE: aceeasi pagina poate purta si un pret de B-Ware "
                 "(1.151,10 € pe PDP-ul masurat) — e ALTA oferta, a nu se confunda cu "
                 "pretul platit. Outlet-ul /apple-und-zubehoer/outlet-a-b-ware-.html "
                 "e identificat dar NEMASURAT (plafonul sondei s-a dus pe escaladari "
                 "de amprenta) — axa D il ia in valul D, dupa o micro-sonda. "
                 "AMPRENTA: profilul implicit al productiei primeste challenge "
                 "Cloudflare, de aici campul impersonate; profilele concrete sunt in "
                 "tabelul din docs/catalog_domain_log.md (nu aici: garda "
                 "anti-profil-hardcodat face grep pe app/**) — "
                 "vezi docs/catalog_domain_log.md",
    },
    # ── G2C — outlet incaltaminte/sport RO (sonde 2026-08-18) ─────────────────
    # Din patru domenii sondate au intrat DOUA. Celelalte, cu motivele masurate, in
    # docs/catalog_domain_log.md: ccc.ro e domeniu PARCAT (nu magazin), ccc.eu are
    # selector de tara randat client-side, iar hervis.ro redirectioneaza la
    # sportsdirect.ro, care isi randeaza listarile client-side (val de browser).
    "sportvision.ro": {
        "label": "Sport Vision",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2C-1/G2C-2; platforma NBSHOP (server 'Custom Server', cookies "
                 "NBIDSN/NBPHPSESSIONSECURE). IPOTEZA, nu fapt: aceeasi platforma cu "
                 "buzzsneakers.ro, care e tot jsonld — markerul NBSHOP si verdictul "
                 "coincid, dar inrudirea n-a fost dovedita cu fragmente verbatim din "
                 "AMBELE parti, fiindca nu exista dump buzzsneakers. ld+json: Product "
                 "+ Offer cu price / priceCurrency RON / availability, plus sku, "
                 "brand, productID, aggregateRating, hasMerchantReturnPolicy, "
                 "priceValidUntil, shippingDetails. Moneda incrucisata: RON in date "
                 "structurate SI in afisaj. Omnibus ABSENT pe PDP-urile masurate, "
                 "niciun <del>/<s>. Axa D e val ULTERIOR: categoria "
                 "/produse/noua-colectie are 2.312 produse, dar paginarea nu e "
                 "clasica — `a[rel='next']` cu textul 'Arata mai multe', deci "
                 "incarcare client-side, nemasurata — vezi docs/catalog_domain_log.md",
    },
    "sizeer.ro": {
        "label": "Sizeer",
        "category": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2C-1/G2C-1b/G2C-2; Akamai in fata, dar NU blocaj: cookie-urile "
                 "`_abck`/`ak_bmsc`/`bm_sz` sunt infrastructura, puse pe ORICE raspuns "
                 "care trece prin Akamai — exact ca `cf-ray` la Cloudflare. Verdictul "
                 "de blocaj se da pe status, pe interstitiul din corp si pe ABSENTA "
                 "semnalelor pozitive; aici raspunsurile aveau 1,8-2,1 MB si ld+json "
                 "complet. ld+json: Product + Offer cu price / priceCurrency RON / "
                 "availability, plus sku, mpn, brand, color, category, "
                 "aggregateRating, seller, shippingDetails. Moneda incrucisata. "
                 "OMNIBUS `min30` EXPLICIT — primul din catalog: referinta e 'Cel mai "
                 "mic pret din ultimele 30 de zile inainte de reducere', ca ETICHETA "
                 "TEXTUALA, fara <del>/<s> (taiat_in_dom iese gol). Verbatim de pe "
                 "PDP: '239,99 RON cu TVA 259,99 RON -8% (Cel mai mic pret din "
                 "ultimele 30 de zile inainte de reducere)'. TREI componente "
                 "partajate masurate pe ambele PDP-uri — 18 RON (livrare), 219,99 RON "
                 "(promotie din megamenu), 400 RON (prag de livrare gratuita) — pe "
                 "care ld+json le ocoleste, fiindca da exact pretul propriu al "
                 "paginii. Axa D e val ULTERIOR: /outlet n-are produse server-side "
                 "utile (din 92 de carduri candidate, 87 poarta cele doua componente "
                 "partajate) si n-are paginare server-side — "
                 "vezi docs/catalog_domain_log.md",
    },
    # ── G2F — sub-lotul sport/outdoor (sonde 2026-08-18) ──────────────────────
    # Din patru domenii sondate au intrat TREI. decathlon.ro e Grup 4 (Cloudflare
    # „Just a moment" pe toate profilurile, la home) si asteapta valul de browser.
    "intersport.ro": {
        "label": "Intersport",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "custom",
        "status": "validated",
        "notes": "G2F-1/G2F-1b/G2F-2; ZERO date structurate de produs: ld+json are "
                 "doar Organization si BreadcrumbList, iar [itemtype*='Product'] "
                 "lipseste. Exista un itemprop='price' pe nodul de pret, dar e ORFAN "
                 "— fara itemscope de Product in jur — deci fluxul generic de "
                 "microdata nu-l vede si genericul ridica no_product_data (pinuit de "
                 "test). De aici extractorul custom `intersport_custom`. Pretul platit "
                 "vine din ATRIBUTUL data-current-price ('305,99' — virgula zecimala, "
                 "deci parser strict propriu), ancorat OBLIGATORIU in .current-price: "
                 "CAPCANA e span.points-gain, care poarta ACEEASI valoare cu alt "
                 "inteles ('305,99 puncte' de fidelitate, in container .hidden). "
                 "Referinta taiata sta in span.deleted-price (div.deleted-price-"
                 "container) si NU intra in contractul extractorului — e materie de "
                 "val D. Moneda vine din COD (RON): 'LEI' apare doar in textul de "
                 "langa pret. Stocul e None NEMASURAT — semnalele se contrazic pe "
                 "aceeasi pagina (stoc per marime), iar div.out-of-stock e sablon "
                 "ascuns prin CSS extern pe TOATE cardurile listarii, deci interzis ca "
                 "semnal (tiparul elefant). Componente partajate masurate pe ambele "
                 "PDP-uri: 10/17/50/250 lei si 99.99/199.99 LEI (praguri de livrare si "
                 "promotii din header). Axa D e val ULTERIOR: /sale/ are 86 de carduri "
                 "cu article.x-product-box, dar paginarea e nemasurata — "
                 "vezi docs/catalog_domain_log.md",
    },
    "toolnation.nl": {
        "label": "Toolnation",
        "category": "bricolaj",
        "country": "NL",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-1/G2F-2; Magento. ld+json complet pe PDP: Product + Offer cu "
                 "price / priceCurrency EUR / availability, plus itemCondition, seller "
                 "si url. ATENTIE: preturile NU apar deloc in textul vizibil — sunt "
                 "hidratate client-side — deci exista DOAR in datele structurate; o "
                 "garda care cere preturi vizibile declara fals 'fara semnale de "
                 "magazin' (s-a intamplat la sonda). Capcane masurate pe ambele "
                 "PDP-uri: bannerul '€250' (Summer Deals) si NUMARUL DE TELEFON al "
                 "magazinului, '31 85 237 15 00 €', pe care regexul de pret il citeste "
                 "ca suma — ld+json le ocoleste pe amandoua. Omnibus: NEMARCAT (atentie, "
                 "'van' e prepozitie in neerlandeza, nu marcaj de pret; termenul "
                 "relevant ar fi 'adviesprijs'). Axa D: listarea aanbiedingen.html "
                 "poarta 24 de noduri Product COMPLETE in ld+json — primul candidat "
                 "pentru un mod ldjson-listing al scannerului, unde o singura cerere da "
                 "toate produsele gata parsate — vezi docs/catalog_domain_log.md",
    },
    "direct-running.com": {
        "label": "Direct Running",
        "category": "incaltaminte",
        # Sediul NU e dovedit juridic: singurul semnal masurat, prezent identic pe
        # home, PDP si listare, e „Customer service in France". E serviciu de clienti,
        # nu sediu, si sta in tensiune cu moneda USD — de aici mentiunea din notes.
        "country": "FR",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-1/G2F-2; domeniul REAL e FARA www — redirect MASURAT "
                 "www.direct-running.com -> direct-running.com. ld+json: Product + "
                 "Offer cu price / priceCurrency / availability. MONEDA E USD, nu EUR: "
                 "incrucisat intre ld+json si afisaj ($130.00 / $99.05 / $4.95), pe un "
                 ".com cu 'Customer service in France' — conversia BNR acopera USD. "
                 "TARA e o DEDUCTIE slaba, nu o masuratoare: singurul semnal e acel "
                 "'Customer service in France', repetat pe toate paginile; nu exista "
                 "adresa, VAT sau numar de inregistrare in dump-uri, iar moneda "
                 "contrazice. Daca apare o dovada mai buna, campul se corecteaza. "
                 "Axa D: /outlet are 97 de carduri (div.group.theme-elitelab...) — "
                 "val ULTERIOR — vezi docs/catalog_domain_log.md",
    },
    "zooplus.ro": {
        "label": "Zooplus",
        "category": "pet",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-3/G2F-4; Next.js. ld+json e un @graph, iar produsul e un "
                 "ProductGroup cu `hasVariant` (o varianta per gramaj/pachet), NU un "
                 "Product cu offers-lista: fiecare varianta isi poarta propriul Offer "
                 "cu price / priceCurrency RON / availability, deci pretul "
                 "product-level iese din `_aggregate_variants` — minimul variantelor "
                 "in stoc, regula care exista de la FASHION-1. SEMANTICA PRETULUI: "
                 "ld+json publica pretul POST-VOUCHER, nu pretul de lista — masurat pe "
                 "PDP1, unde corpul arata 16,90 LEI si un -20%, iar ld+json da 13,52 "
                 "(= 16,90 x 0,8). E pretul REAL PLATIBIL, deci fapt de exploatare, nu "
                 "defect: un deal calculat pe el e un deal adevarat. De retinut la "
                 "comparatii cu magazine care publica pretul de lista. Vitrina poarta "
                 "componente partajate care NU apartin produsului — praguri de livrare "
                 "(199 / '99 LEI') si un 9,90 recurent —, deci o extractie pe text "
                 "vizibil ar culege cifre straine; datele structurate le ocolesc. "
                 "PDP-ul are forma /shop/<cale-de-categorii>/<ID_numeric> (masurat: "
                 "/shop/pisici/jucarii_pisici/mingiute/364856 si "
                 "/shop/pisici/hrana_uscata_pisici/purizon/pachete_de_testare/1347045) "
                 "— ID-ul numeric final e ancora, calea de categorii variaza. "
                 "Axa D: /shop/oameni_animale/promotii cu 817 produse si selector "
                 "stabil — val ULTERIOR — vezi docs/catalog_domain_log.md",
    },
    "hornbach.ro": {
        "label": "Hornbach",
        "category": "bricolaj",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-5/G2F-6; ld+json are DOAR `Product` — zero microdata, iar OG "
                 "poarta `og:type=og:product` fara `product:price:*`, deci datele "
                 "structurate sunt singura sursa. Moneda incrucisata: ld+json RON "
                 "vs afisaj `2333,00 lei` / `1829,24 lei`. ATENTIE la forma "
                 "ofertelor: un produs poate publica DOUA `Offer` cu ACELASI pret, "
                 "diferite doar prin livrare (`availableAtOrFrom`, "
                 "`deliveryLeadTime`) — regula minimului de la G2F-4 le traverseaza "
                 "inofensiv (min(x, x) = x), si e primul caz romanesc masurat pe "
                 "ramura aceea. Omnibus ABSENT, niciun pret taiat in DOM. "
                 "PDP-ul are forma /p/<slug>/<ID_numeric>/, categoriile "
                 "/c/<slug>/S<ID>/. Home-ul e un shell randat client-side (raport "
                 "text/HTML 0,0037, zero preturi vizibile) DAR poarta 9 PDP-uri "
                 "complete: e sursa buna de URL-uri, spre deosebire de listari. "
                 "CAPCANA de navigare: linkul de reduceri din home e un ARTICOL "
                 "editorial (/noutati/campanie-promotionala-...), nu o listare — "
                 "un tipar pe `promo` il alege gresit. Axa D nemasurata.",
    },
    "bonami.ro": {
        "label": "Bonami",
        "category": "general",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-5/G2F-6; Next.js. PDP-ul are forma /p/<slug> — forma NU exista "
                 "in niciun dump (catalogul e hidratat, zero ancore de produs), a "
                 "fost CONSTRUITA prin simetrie cu ruta de categorie masurata "
                 "/c/<slug> si confirmata pe viu (200, fara redirect). PDP-ul poarta "
                 "ld+json `Product` obisnuit, cu `price` NUMERIC (572.9, nu sir) si "
                 "`shippingDetails`; valoarea se confirma incrucisat cu "
                 "`__NEXT_DATA__` (customerPrice 57290 / 10^2). ATENTIE: LISTAREA nu "
                 "are ld+json deloc — pentru axa D datele stau in "
                 "`initialCataloguePageState.blocks[].products[]` din __NEXT_DATA__ "
                 "(48 produse, pret ca `units`/10^`scale`, `availability.usableStock` "
                 "numeric, `retailPrice` ca pret de referinta) — val ULTERIOR. "
                 "Pretul de referinta NU e in ld+json (oferta are doar `price`), deci "
                 "reducerea nu se poate calcula din PDP. Zgomot de vitrina: pragul "
                 "partajat `40 Lei`. `og:type` e `website`, nu `product`.",
    },
    "action.com": {
        "label": "Action",
        "category": "general",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-5/G2F-6; Next.js + Cloudflare. Intrebarea de existenta (lista "
                 "master: „verifica daca expune preturi online\") e INCHISA AFIRMATIV: "
                 "are magazin online cu preturi reale — `Offer` cu `price` 3.98 si "
                 "11.95 RON, `InStock`, `priceSpecification` si `seller`. "
                 "ANTI-BOT PE RATA, nu pe ruta si nu pe profil: a 4-a cerere intr-un "
                 "minut a dat 403 „Just a moment...\", iar ACELASI URL pe ACELASI "
                 "profil de PRODUCTIE a trecut cu 200 dupa o pauza de 95s (masurat, "
                 "G2F-5 corectie). Domeniul are deci nevoie de un interval minim "
                 "intre cereri — vezi nota din docs: mecanismul `min_fetch_interval_s` "
                 "exista azi DOAR pe method=browser, deci pe calea HTTP nu e inca "
                 "aplicabil. Pretul e SPART in DOM (`11 95`), deci extractia pe text "
                 "vizibil e nesigura si ld+json e sursa; cifrele mici (0,07-8,98 lei) "
                 "sunt preturi PE BUCATA, nu ale produsului. PDP "
                 "/ro-ro/p/<ID_numeric>/<slug>/; /ro-ro/promocie-saptamanii/ da 404 "
                 "MASURAT. Omnibus absent, niciun pret taiat.",
    },
    "ro.vivre.eu": {
        "label": "Vivre",
        "category": "general",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "ldjson_availability": "untrusted",
        "notes": "G2F-5/G2F-6; Next.js. Cheia e pe SUBDOMENIU fiindca acolo duce "
                 "redirectul MASURAT: www.vivre.ro -> ro.vivre.eu (precedent de cheie "
                 "cu subdomeniu: en.afew-store.com). PDP-ul are forma /p-<ID>/<slug>. "
                 "`availability` din ld+json e CONSTANTA DE SABLON, de unde flagul "
                 "`ldjson_availability: untrusted`: PDP-urile emit `OutOfStock` pe "
                 "produse pe care datele proprii de listare ale aceluiasi site le dau "
                 "`\"inStock\":true` — contradictie pe ACELEASI doua produse "
                 "(8831337, 1977409); pe tot lotul `\"inStock\":true` x24, `false` "
                 "x0, iar `schema.org/InStock` nu apare NICIODATA. Fara flag, "
                 "extractorul ar scrie `in_stock=False` pe toate cele 46.536 de "
                 "produse. PDP-ul e randat client-side la extrem (raport text/HTML "
                 "0,0004 — 280 de octeti de text vizibil, doar titlu si footer legal), "
                 "deci ld+json e SINGURA sursa server-side, iar moneda RON NU e "
                 "incrucisabila pe text: acceptata pe ld+json, 2/2 PDP-uri. "
                 "Listarea /products?discount=yes, 46.536 produse — val ULTERIOR.",
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
    "f64.ro": {
        "label": "F64",
        "category": "foto",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "VTX-1/2; VTEX. Pretul si stocul vin din oferta IMBRICATA a "
                 "AggregateOffer, nu din agregat (agregatul n-are availability — a "
                 "cerut coborarea adaugata la VTX-2). Pretul taiat NU e in ld+json: "
                 "sta doar in DOM, cu DOUA etichete, 'Pret anterior' si 'PRP' — "
                 "Omnibus PRP, care din ele e minimul pe 30 de zile e NEMASURAT. "
                 "API-ul de catalog VTEX e deschis (206 + header resources, 52.930 "
                 "produse), rezervat axei D — vezi docs/catalog_domain_log.md",
    },
    "elefant.ro": {
        "label": "Elefant",
        "category": "general",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "validated",
        # Amprenta implicita a productiei (_IMPERSONATE din scraper_service) ia 403
        # de la Cloudflare pe elefant; `chrome` ia 200. Profilul concret NU se scrie
        # aici: garda test_niciun_profil_hardcodat_vechi_in_app face grep pe app/**
        # dupa profilele vechi, iar tabelul complet e in docs/catalog_domain_log.md.
        "impersonate": "chrome",
        "notes": "ELF-1/1b/2; Intershop, ZERO date structurate (fara ld+json, "
                 "microdata sau OG) — de aici extractorul custom. Pretul: "
                 "[data-testing-id='current-price'], cu moneda pe acelasi element "
                 "(data-price-currencymnemonic); rezerva payload-ul GTM "
                 "window.ish.GTMproductDetail, care insa n-are moneda. Stocul NU e "
                 "randat server-side nicaieri: PDP-ul unui produs AvailableFlag-0 e "
                 "identic cu al unuia in stoc pe toate cele 12 semnale verificate, "
                 "deci in_stock e None PRIN DESIGN (ELF-1b). URL de produs "
                 "/<slug>_<uuid>; ruta ViewProduct-Start?SKU=<uuid> functioneaza. "
                 "Outlet 'lichidari-de-stoc', ~9k produse, placi hidratate cu AMBELE "
                 "preturi la 5,7KB — material pentru un val D. AMPRENTA: profilul "
                 "implicit al productiei primeste 403 Cloudflare, `chrome` primeste "
                 "200 — masurat ELF-2, de aici campul impersonate; profilele concrete "
                 "sunt in tabelul din docs/catalog_domain_log.md (nu aici: garda "
                 "anti-profil-hardcodat face grep pe app/**) — "
                 "vezi docs/catalog_domain_log.md",
    },
    # ── G1 — ultimele doua din Grupul 1 (sonda G1-1 + pasa 2, 2026-08-17) ──────
    # Amandoua erau marcate "sonda Shopify la implementare"; masuratoarea le-a
    # infirmat pe amandoua, deci intra pe jsonld. Fara camp `impersonate`: 12/12
    # cereri au raspuns 2xx pe amprenta implicita a productiei, lantul de
    # escaladare nu s-a activat niciodata.
    "sivasdescalzo.com": {
        "label": "Sivasdescalzo",
        "category": "sneakers",
        "country": "ES",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G1-1; Next.js/RSC, NU Shopify (/products.json da 404 cu "
                 "__next_error__). Ruta /en/ serveste USD, nu EUR: ld+json, "
                 "payload-ul RSC (price_range.regular_price.currency) si textul "
                 "vizibil ($190) spun toate acelasi lucru, iar EUR apare in pagina "
                 "DOAR in tabelul de livrari per tara — moneda se citeste din "
                 "pagina, conversia BNR acopera restul. ld+json ABSENT pe unele "
                 "pagini (gift card: zero blocuri application/ld+json), deci "
                 "no_product_data e comportamentul CORECT acolo, nu un bug. "
                 "Marimile stau doar in RSC, nu in ld+json (hasVariant lipseste). "
                 "Axa D cere o runda RSC separata in valul D — pagina de promotii "
                 "e o aterizare, nu o listare — vezi docs/catalog_domain_log.md",
    },
    "tezyo.ro": {
        "label": "Tezyo",
        "category": "incaltaminte",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G1-1/pasa 2; Magento 2, CDN comun cu otter.ro (cdn.otter.ro). "
                 "DOUA forme de ld+json: produsul simplu da Product + Offer cu "
                 "price/availability, iar produsul cu marimi da ProductGroup + "
                 "AggregateOffer — acolo pretul si stocul stau in oferta IMBRICATA "
                 "(AggregateOffer.offers[]) si in hasVariant[].offers, cate una pe "
                 "marime, cu size si sku propriu; agregatul in sine n-are "
                 "availability, exact tiparul f64/VTX-2. Referinta taiata NU e in "
                 "ld+json (lowPrice == highPrice == pretul platit): sta doar in DOM "
                 "(.old-price) si in cardurile de listare — de aici descriptorul de "
                 "mai jos. `.product-info-stock-sku` poarta placeholderul Magento "
                 "NEINLOCUIT ('Numai %1 ramase'), deci textul de stoc din DOM e "
                 "inutilizabil; datele structurate sunt sursa buna",
        # DEAL-2 — masurat in G1-1: 1.655 produse pe 69 de pagini (toolbar-amount
        # "Produsele 1 - 23 din 1655"). ACOPERIRE PARTIALA ASUMATA: doar sectiunea
        # femei e masurata; celelalte sectiuni de reduceri se adauga in valul D,
        # dupa sondare — nu le presupunem aici.
        "listing": {
            "url": "https://www.tezyo.ro/reduceri/pentru/femei",
            "page_url_template": "https://www.tezyo.ro/reduceri/pentru/femei?p={n}",
            "max_pages": 80,
            "currency": "RON",
            "card": "li.product-item",
            "link": "a.product-item-link",
            # Titlul VINE DIN TEXTUL LINKULUI: `title` e un selector CSS pe card, iar
            # aici tinteste chiar ancora, deci _titlu_of ii ia textul. Nu e nevoie de
            # o conventie noua — pe otter.ro acelasi camp tinteste h3.product-item-name.
            "title": "a.product-item-link",
            # Magento expune numericul in atribut, deci nu parsam "244,00 lei".
            # `finalPrice` (nu `.special-price [data-price-amount]`): acelasi nod pe
            # cardurile REDUSE, dar il poarta si cardurile la pret plin, deci un
            # produs nereus nu dispare tacit daca listarea ajunge sa contina unul.
            "price_attr": ("[data-price-type='finalPrice']", "data-price-amount"),
            # Masurat G1-2, PASUL 0.5: ramura taiata ARE data-price-amount ("349",
            # data-price-type="oldPrice"), deci merge tot pe attr_float — nu a fost
            # nevoie de rezerva pe text cu eu_comma.
            "compare_attr": ("[data-price-type='oldPrice']", "data-price-amount"),
            "price_parse": "attr_float",
            # Omnibus MASURAT absent: nici pe listare, nici pe cele doua PDP-uri nu
            # apare vreo formulare de pret de referinta (nici PRP, nici 30 de zile).
            "reference_kind": "nemarcat",
        },
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
        # DEAL-2 — masurat in LST-1: Magento, 197 de pagini a 24 de produse.
        # Pagina 500 da 200 cu grila GOALA.
        "listing": {
            "url": "https://www.otter.ro/reduceri",
            "page_url_template": "https://www.otter.ro/reduceri?p={n}",
            "max_pages": 210,
            "currency": "RON",
            "card": "li.product-item",
            "link": "a.product-item-photo",
            "title": "h3.product-item-name",
            # Magento expune pretul numeric in atribut, deci nu parsam "98,00 lei".
            "price_attr": ("[data-price-type='finalPrice']", "data-price-amount"),
            "compare_attr": ("[data-price-type='oldPrice']", "data-price-amount"),
            "price_parse": "attr_float",
            # Omnibus LST-1, verbatim din dump: "PRP: 379,00 lei" si "Salvezi 82 lei
            # fata de pretul recomandat de producator".
            "reference_kind": "prp",
        },
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
        "status": "validated",
        "headed": True,
        "min_fetch_interval_s": 180,
        "notes": "G4/G4b: limitare progresiva variabila — sesiune-per-pagina, "
                 "interval minim configurabil (productia e masuratoarea; se urca "
                 "din registru daca apar blocaje); microdata pe DOM-ul randat",
    },
    "makeup.ro": {
        "label": "Makeup",
        "category": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "validated",
        "overrides": {"price_selector": '[class*="ProductBuySection__container"] > [itemprop="price"]'},
        "notes": "G4/G4b: interstitiu JS pe 202 trecut de browser; paginile cu "
                 "variante de culoare au N itemprop=price — selectorul tinteste "
                 "containerul principal (clasele au sufixe generate, ancorare pe "
                 "partea stabila); meta content; BR-1b: selector copil-direct — "
                 "unic pe pagina (masurat 3/3 la BR-1), imun la reordonari",
    },
    "hhv.de": {
        "label": "HHV",
        "category": "fashion",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4/G4b: reset de conexiune pe headless; jsonld curat headed; "
                 "marimile absente din date — se urmareste produsul; pquid taiat "
                 "de canonical",
    },
    "noriel.ro": {
        "label": "Noriel",
        "category": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT5; ld+json poarta DOAR pretul platit — referinta taiata sta "
                 "in afara datelor structurate (special-price/old-price in DOM)",
        # DEAL-2 — masurat in LST-1/1b: Magento, 115 pagini a 60 de produse.
        # Pagina 500 CLAMEAZA la pagina 1 (acelasi set de 60 de linkuri), deci
        # fara regula de linkuri deja vazute scannerul ar bucla la infinit.
        "listing": {
            "url": "https://noriel.ro/promotii",
            "page_url_template": "https://noriel.ro/promotii?p={n}",
            "max_pages": 125,
            "currency": "RON",
            # SUBSET de clase: containerul real e `div.product-item.freegifts-<id>`,
            # cu token per-produs. Potrivirea pe lista completa ar da zero carduri.
            "card": "div.product-item",
            # `<a>` fara clasa, DESCENDENT al cardului: inveleste CONTINUTUL
            # (h2 + price-box sunt inauntrul lui), dar containerul `div.product-item`
            # ii ramane parinte. LST-1 descrisese asta ca "inveleste cardul", de unde
            # ipoteza `@parent_a` din briefing — masuratoarea pe dump o infirma.
            "link": "a[href]",
            "title": "h2.product-item-name",
            "price_text": ".special-price .price",
            "compare_text": ".old-price .price",
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
        },
    },
    "regatuljocurilor.ro": {
        "label": "Regatul Jocurilor",
        "category": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT5; aceeasi forma Omnibus: platitul in date, taiatul in DOM "
                 "(has-discount + raw_price); capcana caruselului comun — "
                 "regular-price identic pe pagini diferite e componenta "
                 "partajata, nu pretul paginii",
    },
    "jucarii-vorbarete.ro": {
        "label": "Jucarii Vorbarete",
        "category": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "notes": "SHOP-3; migrat de la jsonld (LOT5) dupa sonda de enumerare: "
                 "SHOPIFY_DESCHIS, /products.json cu variants, .js cu available, "
                 "moneda RON din /cart.js incrucisata cu ld+json 3/3, datadome "
                 "absent; regula FASHION-2 neexercitata la sonda (o singura "
                 "varianta Default Title) — pretul in enumerare e STRING zecimal, "
                 "in .js e INT in bani",
    },
    "nichiduta.ro": {
        "label": "Nichiduta",
        "category": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT5b; pret dublu-sursat (ld+json + div.priceNEW), platitul in "
                 "date; ATENTIE la citirea marjelor: referinta taiata e PRP "
                 "(Pretul Recomandat de Producator, verbatim din tooltip), NU "
                 "minimul pe 30 de zile — procentele de reducere sunt fata de PRP",
    },
    "brickdepot.ro": {
        "label": "BrickDepot",
        "category": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT5b; ld+json cu caractere de control — clientul treptei laxe; "
                 "pagina cu ghilimea dublata in sursa site-ului ramane neparsabila "
                 "(refresh pastreaza pretul); spec de selector de rezerva in jurnal",
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


def listing_domains() -> set[str]:
    """Domeniile cu descriptor de listare (DEAL-2), pentru scannerul de reduceri.

    Apartenenta se decide din PREZENTA cheii `listing`, nu dintr-o lista paralela
    si nici din `method`: un magazin poate fi citit prin `jsonld` la nivel de produs
    si, separat, parcurs pe paginile lui de reduceri — cele doua capabilitati sunt
    independente, exact ca la `shopify_domains`.
    """
    return {domain for domain, meta in SHOP_REGISTRY.items() if "listing" in meta}


def listing_descriptor(domain: str) -> dict | None:
    """Descriptorul de listare al unui domeniu, copiat adanc.

    Copia e obligatorie din acelasi motiv ca la `domain_overrides`: payload-ul e un
    dict mutabil, iar scannerul il plimba prin functii — o referinta ar lasa un bug
    de acolo sa rescrie registrul pentru tot procesul.
    """
    meta = SHOP_REGISTRY.get(domain) or {}
    return copy.deepcopy(meta["listing"]) if "listing" in meta else None


def browser_domains() -> set[str]:
    """Domeniile servite de harness-ul de browser (method == "browser").

    Dubla folosinta, ca la shopify_domains: alege calea de fetch in extractor SI e
    lista de destinatii pe care harness-ul are voie sa navigheze. Un domeniu nu
    poate fi deci deschis in browser fara sa fie declarat aici.
    """
    return {domain for domain, meta in SHOP_REGISTRY.items()
            if meta.get("method") == "browser"}


def browser_profile_of(domain: str) -> dict:
    """Profilul de rulare al harness-ului pentru un domeniu.

    Mereu aceleasi chei, cu implicitele aplicate (headless, fara limitare), ca
    apelantul sa nu duplice absenta campurilor. Dict-ul e construit la fiecare
    apel, deci nu poate fi mutat inapoi in registru.
    """
    meta = SHOP_REGISTRY.get(domain) or {}
    return {
        "headed": bool(meta.get("headed")),
        "min_fetch_interval_s": meta.get("min_fetch_interval_s"),
    }
