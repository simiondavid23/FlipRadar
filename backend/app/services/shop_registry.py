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
  channel     — OBLIGATORIU (DISC-1/1b), canalul Discord pe care pleaca deal-urile
                domeniului: electronice | sneakers | haine | jucarii | beauty |
                diverse.
                La DISC-1 campul era OPTIONAL si absenta insemna `diverse`. La
                DISC-1b cele 24 de domenii ramase implicite au primit eticheta lor,
                iar regula s-a INVERSAT: `test_fiecare_domeniu_are_channel` cade
                daca un magazin nou intra fara ea. Motivul e ca implicitul se
                purta prea bine — un magazin de electronice uitat ajungea in
                `diverse`, feed-ul mergea, si nimic nu semnala greseala. Acum
                greseala se vede la test, nu pe Discord peste doua luni.
                `deal_channel` PASTREAZA totusi rezerva pe `diverse`, si nu e
                contradictie: ea acopera randuri vechi ale unui magazin scos din
                registru intre timp, unde alternativa ar fi o excepție in mijlocul
                unui scan.
                E DELIBERAT separat de `category`,
                desi cele doua seamana: `category` descrie ce vinde magazinul si
                are 15 valori crescute organic pe masura ce intrau valuri;
                `channel` descrie unde se uita David si are exact sase, fiindca
                atatea canale exista in serverul lui. Legarea lor ar fi insemnat
                ca adaugarea unei categorii noi (`farmacie`, `biciclete`) ruteaza
                tacut intr-un canal inexistent.
                Pe descriptorii cu `entries`, cheia poate aparea SI pe o intrare,
                si atunci INTRAREA are prioritate — vezi eMAG Resigilate, unde
                cele 12 departamente merg de la laptopuri la scutece. Regula
                intreaga (intrare > domeniu > `diverse`) traieste intr-un singur
                loc, `deal_channel()`; niciun consumator n-are voie sa tina lista
                lui de domenii per canal.
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
                documentat la structura din product_page_extractor). Doua chei
                optionale din payload NU tin de parsare, ci de POARTA DE FETCH, si
                se citesc din scraper_service prin `overrides_option_map` (AMZ-1a):
                  * block_markers — tuplu de stringuri LOWERCASE, adaugate la
                    BLOCK_MARKERS-ul generic din base_scraper DOAR pentru domeniul
                    asta. Se pune cand magazinul serveste un interstitiu anti-bot
                    pe care markerii generici nu-l prind. Fiecare marker trebuie
                    masurat pe dump-uri reale: zero aparitii pe pagini NORMALE ale
                    domeniului, altfel poarta declara blocate paginile bune.
                    (Contraexemplu masurat la AMZ-0: „entschuldigung" apare pe 103
                    pagini reale amazon.de — deci NU e marker.)
                  * interstitial_max_bytes — int pozitiv, pragul sub care prezenta
                    markerilor mai e concludenta, cand cel generic (40 000) nu e
                    potrivit. Se pune DOAR daca s-a masurat o pagina de blocare mai
                    mare decat pragul generic; pe amazon.de nu e cazul (cel mai mare
                    interstitiu masurat are 3 817 octeti).
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
  cookie_jar  — OPTIONAL (AMZ-1), nume de jar: magazinul cere o SESIUNE ca sa
                serveasca pagini reale. Cookie-urile se persista la
                `<DATA_DIR>/data/cookies_<nume>.json` — acelasi director cu sesiunea
                Facebook, acoperit de aceeasi regula `.gitignore` (`backend/data/`),
                fiindca sunt date locale sensibile. Absent = fara jar, exact
                comportamentul celorlalte magazine (nu se trimite `cookies=`).
                Masurat pe amazon.de la AMZ-0/0c: sesiunea RECE e blocata 100%
                (interstitiu de 200, DOGS 503, provocare AWS WAF 202), iar cu jar-ul
                incarcat intr-un proces nou pagina de produs vine intreaga.
  bootstrap_url
              — OPTIONAL (AMZ-1), URL care EMITE cookie-urile de sesiune, cerut
                inaintea primei cereri utile (si o singura data dupa un blocaj).
                Are sens doar impreuna cu `cookie_jar`. Pe amazon.de e ruta `glow`
                de alegere a tarii de livrare: raspunde 200 pe sesiune rece — unde
                homepage-ul si pagina de produs sunt blocate — si emite 6 cookie-uri
                cu expirare la 2 ani. NU e login: nu exista cont, iar valorile nu
                intra niciodata in jurnal.
  min_fetch_interval_s
              — OPTIONAL, pe ORICE metoda (int pozitiv): secunde minime intre doua
                cereri catre domeniu. Cele doua cai il consuma DIFERIT, si asta e
                deliberat:
                  * BROWSER (`browser_fetch`): sub prag fetch-ul e REFUZAT fara a
                    lansa browser, iar refresh-ul pastreaza pretul anterior —
                    lansarea unui browser e prea scumpa ca sa astepti cu el pornit;
                  * HTTP (poarta `_fetch_shop_url_guarded`, RATE-1): sub prag
                    cererea ASTEAPTA diferenta si apoi pleaca — o cerere HTTP e
                    ieftina, iar refuzul ar pierde inutil o extractie.
                Aparut pentru sephora.ro (browser, 180s), care limiteaza progresiv
                — acolo pragul real nu e masurat (sonda G4b si-a invalidat propria
                masuratoare), deci valoarea e o estimare prudenta. Extins la calea
                HTTP pentru action.com (90s), unde limitarea pe RATA e masurata
                exact: a 4-a cerere intr-un minut ia 403, iar acelasi URL pe acelasi
                profil trece dupa 95s (G2F-5). Absent = fara limitare, si niciun
                cost — harta se deriva o data la import, iar domeniile care nu-s in
                ea nu ating nici macar lacatul.
  extra_headers
              — OPTIONAL (DEAL-D8), dict nume->valoare: antete pe care poarta HTTP
                le adauga la FIECARE cerere catre domeniu. Sunt antete de
                PREFERINTA — vitrina, moneda, tara, limba — si NICIODATA de
                sesiune sau autentificare: valorile stau intr-un literal Python
                versionat, deci orice ar fi secret aici ar fi secret in git.
                Aparut pentru asos.com, unde comutatorul de vitrina NU e in query
                (`?store=ROE&currency=EUR&country=RO` e ignorat TACIT, pagina vine
                intreaga dar in GBP) ci in `Cookie: browseCountry=RO`, masurat la
                LST-D8/DEAL-D8: cu el, 72/72 de produse in EUR si starea pe
                ROE/EUR/RO; fara el, 72/72 in GBP.
                Se aplica PER HOP si doar pe hop-urile care apartin domeniului,
                cu aceeasi granita pe punct ca jar-ul: un redirect catre alt
                magazin nu are voie sa duca preferintele noastre acolo.
                La coliziune de nume, antetele domeniului SUPRASCRIU antetele
                apelantului — un `Cookie` accidental al apelantului nu are voie sa
                dezactiveze tacit comutatorul de vitrina si sa publice preturi in
                alta moneda.
                GARDA (`_valideaza_extra_headers`): `cookie_jar` + un `Cookie` in
                `extra_headers` pe acelasi domeniu e RESPINS la import, fiindca
                poarta trimite jar-ul prin `cookies=` iar antetul prin `headers=`,
                iar cele doua s-ar ciocni fara ca nimeni sa vada care castiga.
  search      — OPTIONAL, descriptorul de CAUTARE DUPA TERMEN (SEARCH-1). Prezenta
                cheii = domeniul apare in pagina „Scanare Magazine". Absenta = doar
                prin link. `kind` alege mecanismul:
                  * "shopify"    — Ajax Predictive Search `/search/suggest.json`.
                                   Cere method == "shopify" (moneda vine din registru,
                                   payload-ul n-o poarta). Plafon FIX de 10 rezultate,
                                   masurat la SEARCH-0 pe 3 magazine (limit=50 intoarce
                                   raspuns byte-identic cu limit=10) — fara alte chei.
                  * "vtex"       — `?ft=` pe `catalog_api.endpoint`. Cere `catalog_api`.
                  * "descriptor" — pagina HTML de cautare a magazinului, citita cu
                                   `extrage_carduri`. Chei:
                                     url_template — URL cu `{q}` (termenul, url-encodat
                                                    de apelant), luat din <form>-ul real
                                                    al magazinului (inclusiv hidden-urile
                                                    lui — SEARCH-0 §5a);
                                     INTRARILE (EMAG-D) — un descriptor `listing`
                                                    declara ori `url` (+
                                                    `page_url_template` cand
                                                    max_pages > 1), ori o lista
                                                    `entries` de forma
                                                    [{url, page_url_template,
                                                    max_pages?}, ...] — SAU-EXCLUSIV,
                                                    niciodata amandoua. `max_pages` per
                                                    intrare e optional si cade inapoi pe
                                                    cel al descriptorului. Forma cu
                                                    lista e pentru magazinele fara URL
                                                    agregat de reduceri: eMAG Resigilate
                                                    isi imparte catalogul pe 12
                                                    departamente, fiecare paginat in
                                                    CALE. Pinuit de garda descriptorilor.
                                     selectorii de PRET — price_text SAU price_attr,
                                                    optional compare_text/compare_attr,
                                                    price_parse (valorile admise, si in
                                                    `listing`: pe TEXT "eu_comma"
                                                    („1.393,94 lei"), "us_dot"
                                                    („$117.63", DEAL-D1) sau "eu_sup"
                                                    („529 99 lei", DEAL-D2: zecimalele
                                                    stau intr-un <sup> FARA separator,
                                                    iar `get_text(" ")` le lasa un
                                                    spatiu — evomag; parserul deleaga
                                                    la `eu_comma` daca sirul are totusi
                                                    virgula, ca la powerup) — citite acum
                                                    chiar de `_pret_of`, o valoare
                                                    necunoscuta ridica ValueError; pe
                                                    ATRIBUT "attr_float", unde parserul
                                                    strict e impus de calea de cod, nu de
                                                    camp).
                                     compare_parse — OPTIONAL (DEAL-D2), parserul laturii
                                                    de REFERINTA cand ea se citeste altfel
                                                    decat pretul platit. Cerut exact cand
                                                    descriptorul are `price_attr` SI
                                                    `compare_text`: pretul vine din atribut
                                                    (`attr_float`, impus de calea de cod)
                                                    iar referinta din text, deci o singura
                                                    cheie `price_parse` n-ar putea descrie
                                                    amandoua (itgalaxy.ro). Absent = se cade
                                                    inapoi pe `price_parse`.
                                     title_from   — OPTIONAL, de unde se ia TITLUL cand el
                                                    nu e textul unui nod. Valorile admise:
                                                    "link_aria_label" (caseking) si
                                                    "link_title" (DEAL-D4, officeshoes:
                                                    ancora produsului n-are text, doar un
                                                    <img>, iar numele complet e in
                                                    `title=`). Ambele citesc ancora aleasa
                                                    de `link`; `link_title` cade inapoi pe
                                                    selectorul `title` daca atributul
                                                    lipseste. Absent = textul lui `title`.
                                     OBLIGATORIU declarati
                                                    aici chiar daca sunt identici cu cei
                                                    din `listing`: acolo sunt scrisi pentru
                                                    pagini de REDUCERI si pe pagina de
                                                    cautare pot prinde 1 din 60 (noriel,
                                                    SEARCH-0). Restul cardului (card, link,
                                                    title, image, image_attr, currency) se
                                                    MOSTENESTE din `listing`, deci cere
                                                    `listing` prezent.
                  * "custom"     — scraper de cautare scris de mana, in
                                   scraper_service._SCRAPERS_BY_SOURCE (cele 5 istorice).
                Domeniile cu method == "browser" NU pot avea `search` (D2: un browser
                per query e prea scump pentru o pagina interactiva). Pinuit de test.
  notes       — valul/sonda de origine
"""
import copy

SHOP_REGISTRY: dict[str, dict] = {
    # ── AMZ-1 ─────────────────────────────────────────────────────────────────
    "amazon.de": {
        "label": "Amazon.de",
        "category": "general",
        "channel": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "validated",
        "currency": "EUR",
        "min_fetch_interval_s": 10,
        "cookie_jar": "amazon_de",
        "bootstrap_url": ("https://www.amazon.de/portal-migration/hz/glow/"
                          "get-rendered-address-selections?deviceType=desktop"
                          "&pageType=Gateway&storeContext=NoStoreName"
                          "&actionSource=desktop-modal"),
        "overrides": {
            # Masurati la AMZ-0 pe 137 de dump-uri: ZERO aparitii pe pagini reale.
            # `api-services-support@amazon.com` apare SI pe paginile 404 — e sigur
            # doar fiindca `classify()` verifica statusul 404 INAINTEA markerilor.
            "block_markers": ("validatecaptcha", "api-services-support@amazon.com"),
        },
        "notes": "AMZ-0/0c/AMZ-1. Sesiunea RECE e blocata 100%: primele 20 de cereri "
                 "fara cookie-uri au picat pe patru rute si cu trei mecanisme diferite "
                 "— interstitiu de 200 (3.815 octeti, buton „Weiter shoppen”, NU "
                 "captcha vizual), pagina 503 „Tut uns Leid!”, provocare AWS WAF pe "
                 "status 202. Nu tine de amprenta TLS: cele 5 profiluri incercate au "
                 "primit raspuns identic la octet. Deblocarea vine din `bootstrap_url` "
                 "(ruta glow), care raspunde 200 pe sesiune rece si emite 6 cookie-uri "
                 "cu expirare la 2 ani; dupa ele, 90/90 de cereri OK la 5-20 s "
                 "interval, iar sesiunea supravietuieste restartului de proces. "
                 "ZERO ld+json pe 9/9 PDP-uri, deci `method: custom` — genericul "
                 "n-ar avea ce parsa. IDENTITATEA e ASIN-ul din URL: "
                 "`link[rel=canonical]` sare pe parintele de varianta (alt ASIN) pe "
                 "3/9 pagini, deci extractorul intoarce el forma canonica "
                 "`/dp/<ASIN>` si NU citeste canonicalul paginii; `input#ASIN` a fost "
                 "egal cu ASIN-ul cerut pe 9/9 si se verifica la fiecare extractie. "
                 "De aceea NU se pune `url_identity: exact`: acela ar pastra "
                 "`?ref=...` din URL-ul lipit de user si ar sparge dedup-ul pe ASIN. "
                 "CAPCANE de parsare: primul `.a-offscreen` din `.priceToPay` e un "
                 "span GOL (deci prima potrivire NEVIDA, nu prima potrivire), 2/9 "
                 "PDP-uri au literalul „null” ca pret taiat, iar `basisPrice` poate fi "
                 "EGAL cu pretul platit desi `.savingsPercentage` anunta −7% — de "
                 "aceea referinta se accepta doar daca e strict mai mare. Buy box-ul "
                 "poate fi oferta second („Amazon Retourenkauf”), deci extractorul "
                 "intoarce `seller`/`condition`; NU se persista, fiindca modelul "
                 "Product n-are coloanele (decizie amanata la AMZ-2). Preturile vin cu "
                 "TVA RO prin geolocatia IP-ului, iar masuratoarea NU se transfera pe "
                 "o iesire straina (VPS/proxy), unde tara de livrare ar trebui setata "
                 "programatic — mecanism inca nedescoperit. Link-urile scurte "
                 "amzn.eu / amzn.to NU sunt suportate in v1 (nu sunt in allow-list). "
                 "Panoul „toate ofertele” (AOD) ramane NEMASURAT: ambele rute "
                 "incercate dau 404. Axa D e separata: SERP-ul are 33 de carduri pe "
                 "`i=toys` (nu 60), iar pretul taiat de pe carduri amesteca UVP, "
                 "„Statt” si preturi UNITARE (0,05 €/Stück) — vezi docs.",
    },
    # ── RETAIL-3a ─────────────────────────────────────────────────────────────
    "altex.ro": {
        "label": "Altex",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── STATE-2 — axa D pe STARE, nu pe selectori CSS ──────────────────
        #
        # DEAL-D2 citea cardul din DOM si vedea 48 de produse din ~8000, fiindca
        # butonul de paginare vine gol (`<div class="Toolbar-next md:hidden">`),
        # randat client-side. JSON-0 a cautat apelul XHR de listare cu captura de
        # retea si NU l-a gasit — a gasit in schimb ca produsele erau de la
        # inceput in acelasi raspuns, in `__NEXT_DATA__`, impreuna cu URL-urile
        # TUTUROR paginilor. Deci nu era nevoie nici de API, nici de browser:
        # doar de citit alta parte a paginii pe care o descarcam oricum.
        "listing": {
            "url": "https://altex.ro/resigilate/",
            # MASURAT live (STATE-2): `/filtru/p/2/` -> 200 cu alte 48 de produse
            # (46 din 48 noi fata de dump-ul de ieri), iar `/filtru/p/500/` -> tot
            # 200, dar cu grila GOALA (`products: []`, `toolbar.pagination: []`,
            # `<h1>Produse resigilate</h1>` neschimbat). Oprirea e deci „grila
            # goala pe 200", forma pe care `altex_next` o intoarce ca `[]`.
            "page_url_template": "https://altex.ro/resigilate/filtru/p/{n}/",
            # Reala e 168 (`toolbar.pagination` are 168 de intrari, confirmate si
            # pe p2 live). 30 e PLAFON DE BUGET, nu masuratoare: 30 x 48 = 1.440
            # de produse per scan, restul catalogului intra prin rotatia zilelor
            # urmatoare. De ridicat cand scanul isi permite.
            "max_pages": 30,
            "currency": "RON",
            "state_extractor": "altex_next",
            # `nemarcat`: referinta e `price` din stare, adica pretul unitatii NOI
            # a aceluiasi SKU („Nou:" in DOM) — ce marcheaza eMAG cu `label:"NOU"`.
            # Nu e Omnibus si nu e PRP. Semantica inversata a celor doua campuri
            # de pret e explicata pe larg in docstring-ul lui `altex_next`.
            "reference_kind": "nemarcat",
            # Starea produsului („resigilat") NU intra in titlu: `name` e numele
            # curat, iar registrul n-are cheie de prefix. Aceeasi limita ca la
            # eMAG cu GRADUL, si ca la descriptorul CSS pe care il inlocuieste.
        },
        "search": {"kind": "custom"},
        "notes": "RETAIL-3a; DEAL-D2 (CSS, inlocuit); STATE-2 — axa D pe `/resigilate/` "
                 "prin `altex_next`, din `__NEXT_DATA__`: 48 de produse pe pagina si "
                 "168 de pagini anuntate in `toolbar.pagination`, plafonate la 30 pe "
                 "scan (1.440 de produse) din buget. Paginarea `/filtru/p/{n}/` e "
                 "MASURATA live, iar oprirea e grila goala pe 200. Pretul platit e "
                 "`lowest_price` (resigilatul), referinta e `price` (unitatea NOUA, "
                 "„Nou:”) — semantica inversata fata de nume. URL-ul se compune cu "
                 "`sku`, nu cu `id`. Frate de platforma cu mediagalaxy.ro, pe ACELASI "
                 "extractor: gazda se citeste din `runtimeConfig.settings.baseUrl`. "
                 "JSON-0 a exclus pista de API (zero apeluri de listare in 640 de "
                 "raspunsuri); `fenrir.altex.ro` ramane neexplorat.",
    },
    "emag.ro": {
        "label": "eMAG",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # PROD-1 — RATE, si masurat de DOUA ori in acelasi scan de productie
        # (10 septembrie): odata ca `RuntimeError: listare esuata la pagina 1
        # (status: 511)`, care a pierdut tot domeniul, si odata ca WARN pe
        # `pc-periferice-software`, oprita la pagina 9 tot cu 511. 511 („Network
        # Authentication Required") e forma in care eMAG raspunde la rafala, iar
        # rafala era a noastra: 12 categorii x ~11 pagini la 2,5-4 s din
        # `_pauza()`, adica ~130 de cereri intr-un sfert de ora.
        #
        # 6 s e ales SUB pragul care a cedat, nu peste: paginile 1-8 ale unei
        # categorii treceau la 2,5-4 s, deci pragul real e undeva peste asta;
        # 6 s dubleaza distanta si tine domeniul la ~12 min pe scan (vezi
        # `max_pages`). Nu e o masuratoare a pragului — pragul nu s-a cautat
        # prin bisectie, fiindca ar fi insemnat sa provocam blocaje.
        #
        # ATENTIE, efect DINCOLO de scanul de listare: poarta impune intervalul
        # pe ORICE cerere catre domeniu (`_fetch_shop_url_guarded`), deci si
        # add-by-link si `refresh_source` pe un produs eMAG platesc pana la 6 s.
        # Acceptat: 6 s pe o actiune manuala e o intarziere, nu un blocaj, si e
        # pretul ca scanul automat sa nu mai arda domeniul pentru toti.
        "min_fetch_interval_s": 6,
        # ── EMAG-D, din dump-urile EMAG-1 (20-21 august) verificate live ────
        "listing": {
            # Forma cu LISTA, primul consumator al mecanismului. eMAG n-are un URL
            # de reduceri agregat pe care sa merite sa mergem: exista
            # `/resigilate` (7996 de produse, `rel=next` catre `/resigilate/p2`),
            # dar adancimea lui n-a fost NICIODATA ceruta, nici la EMAG-1 nici la
            # EMAG-D — cele 3 cereri ale rundei s-au dus pe forma de CATEGORIE.
            # Deci se merge pe cele 12 departamente, care SUNT masurate, si nu se
            # pariaza pe o paginare de 134 de pagini neverificata.
            #
            # Ordinea e a hub-ului (`category_panel_1_0` .. `_12_0`), slug-urile
            # sunt luate verbatim din ancorele lui. Numarul de pagina sta la
            # MIJLOC, intre categorie si `/d` — citit din `rel=next`:
            # `<link rel="next" href="/resigilate/laptop-tablete-telefoane/p2/d">`.
            #
            # DISC-1 — `channel` PER INTRARE. eMAG Resigilate e singurul domeniu
            # unde un canal la nivel de magazin ar minti: cele 12 departamente
            # acopera catalogul intreg, de la laptopuri la scutece. Domeniul
            # declara `electronice` (patru din primele cinci departamente sunt
            # exact asta), iar intrarile care NU sunt electronice si-l suprascriu.
            # `gaming-carti-birotica` ramane pe implicit deliberat: consolele si
            # perifericele resigilate domina departamentul, iar cartile si
            # birotica n-au canal propriu.
            "entries": [
            # Laptop, Tablete & Telefoane
            {"url": "https://www.emag.ro/resigilate/laptop-tablete-telefoane/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/laptop-tablete-telefoane/p{n}/d"},
            # PC, Periferice & Software
            {"url": "https://www.emag.ro/resigilate/pc-periferice-software/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/pc-periferice-software/p{n}/d"},
            # TV, Audio-Video & Foto
            {"url": "https://www.emag.ro/resigilate/tv-audio-video-foto/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/tv-audio-video-foto/p{n}/d"},
            # Electrocasnice & Climatizare
            {"url": "https://www.emag.ro/resigilate/electrocasnice-climatizare/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/electrocasnice-climatizare/p{n}/d"},
            # Gaming, Carti & Birotica
            {"url": "https://www.emag.ro/resigilate/gaming-carti-birotica/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/gaming-carti-birotica/p{n}/d"},
            # Bacanie
            {"url": "https://www.emag.ro/resigilate/alimente-bauturi/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/alimente-bauturi/p{n}/d",
             "channel": "diverse"},
            # Fashion
            {"url": "https://www.emag.ro/resigilate/fashion/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/fashion/p{n}/d",
             "channel": "haine"},
            # Ingrijire personala & Cosmetice
            {"url": "https://www.emag.ro/resigilate/ingrijire-personala-cosmetice/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/ingrijire-personala-cosmetice/p{n}/d",
             "channel": "beauty"},
            # Casa, Gradina & Bricolaj
            {"url": "https://www.emag.ro/resigilate/casa-bricolaj-petshop/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/casa-bricolaj-petshop/p{n}/d",
             "channel": "diverse"},
            # Sport & Travel
            {"url": "https://www.emag.ro/resigilate/sport-activitati-aer-liber/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/sport-activitati-aer-liber/p{n}/d",
             "channel": "diverse"},
            # Auto, Moto & RCA
            {"url": "https://www.emag.ro/resigilate/auto-moto-rca/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/auto-moto-rca/p{n}/d",
             "channel": "diverse"},
            # Jucarii, Copii & Bebe
            {"url": "https://www.emag.ro/resigilate/jucarii-copii-bebe/d",
             "page_url_template":
                 "https://www.emag.ro/resigilate/jucarii-copii-bebe/p{n}/d",
             "channel": "jucarii"},
            ],
            # UNIC la nivel de descriptor, si nu din comoditate: hub-ul publica UN
            # total (7996 de produse) si NICIUN numar per categorie, iar singura
            # categorie cu dump propriu, `laptop-tablete-telefoane`, anunta 1948 de
            # produse = 33 de pagini la 60/pagina. 40 e aia plus marja, conventia
            # otter. Un plafon per intrare ar fi trebuit INVENTAT pentru celelalte
            # unsprezece.
            #
            # Plafonul e o plasa, nu granita reala: oprirea masurata la EMAG-D pe
            # `/p500/d` e GRILA GOALA PE 200 (180 KB, zero carduri), deci bucla se
            # inchide singura pe prima conditie din `_scaneaza_domeniu` mult
            # inaintea plafonului. Cele 18 aparitii de `card-item` din acel corp
            # sunt placeholder-e de carusel de recomandari
            # (`rec-card-item card-item js-card-item` cu `div.card-v2 card-shimmer`
            # gol) — NU au `js-product-data`, si de aia clasa aia e obligatorie in
            # selector. Capcana caruselului, a treia oara dupa LOT5 si powerup.
            #
            # PROD-1: 40 -> 6, si cifra e un BUGET, nu o masuratoare de adancime.
            # Cheia e la nivel de descriptor, dar `_intrari` o rezolva PER INTRARE
            # (fallback), deci 6 inseamna 6 pagini pentru FIECARE dintre cele 12
            # categorii: 12 x 6 x 60 = 4 320 de produse pe scan, la ~12 min cu
            # intervalul de 6 s. Inainte, aceleasi 12 categorii mergeau pana la
            # ~11 pagini fiecare in rafala si cadeau pe 511 (vezi
            # `min_fetch_interval_s`). Adancimea reala ramane cea din comentariul
            # de mai sus (33 de pagini pe `laptop-tablete-telefoane`); ce se pierde
            # e coada fiecarei categorii, iar resigilatele noi intra pe primele
            # pagini, care sunt sortate implicit dupa relevanta/noutate.
            "max_pages": 6,
            "currency": "RON",
            # Cel mai din AFARA dintre cele patru niveluri imbricate cu 60 de
            # noduri fiecare (`card-v2`, `card-v2-wrapper`, `card-v2-content` au
            # acelasi numar): doar el poarta `data-product-id` / `data-offer-id` /
            # `data-url` SI imaginea. `js-product-data` e obligatoriu in selector.
            "card": "div.card-item.js-product-data",
            # Ancora de titlu, nu `a[href]`: cardul are patru ancore catre acelasi
            # produs (poza, titlu, rating, „Vezi Detalii"). Linkul ei pastreaza
            # fragmentul `#used-products`, DELIBERAT — duce la sectiunea de oferte
            # resigilate a PDP-ului, adica exact oferta din deal. `external_id` si
            # `handle` se calculeaza pe CALE, deci fragmentul nu atinge dedup-ul.
            "link": "a.card-v2-title",
            # Acelasi nod da si titlul, iar el POARTA DEJA starea: `_text_of` intoarce
            # „RESIGILAT: Telefon mobil Apple iPhone Air, 256GB, 5G, Light Gold" pe
            # 60/60 de carduri, pe toate cele trei dump-uri de listare. De aceea NU
            # se pune niciun prefix de titlu — ar produce „Resigilat: RESIGILAT: …".
            "title": "a.card-v2-title",
            "image_attr": ["src"],
            # Pretul e SPART pe noduri, si merita spus ca nu e o problema:
            # `<p class="product-new-price"><span class="fs-12">de la</span>
            #  4.599<sup><small class="mf-decimal">,</small>99</sup> <span>Lei</span></p>`
            # `_text_of` da „de la 4.599 , 99 Lei" (get_text(" ") pune spatii intre
            # noduri), iar `_pret_eu_comma` sterge tot ce nu e cifra/punct/virgula —
            # inclusiv „de la", spatiile si „Lei", niciunul cu cifre. Rezultat masurat:
            # 4599.99, corect, pe 60/60.
            #
            # „de la" e pe 60/60: un resigilat are mai multe oferte (grade diferite),
            # iar cardul arata cea mai ieftina — pretul real platibil, ca „Starting at"
            # la direct-running.
            "price_text": "p.product-new-price",
            # `NOU 4.999,99 Lei` — pretul de vanzare CURENT al unitatii NOI a
            # ACELUIASI produs, pe acelasi magazin. Incrucisat cu PDP-ul, care
            # poarta verbatim `"recommended_retail_price":{"amount":4999.99,
            # "is_visible":true,"label":"NOU"}` si afiseaza 4.999,99 ca pret
            # principal si 4.599,99 ca oferta resigilata.
            #
            # ATENTIE la omonimie: aceeasi cheie JSON apare pe PDP si cu
            # `"label":"PRP:"` si valoarea 6274.56 — ala e Pretul Recomandat de
            # Producator, alt numar si alt lucru. Cardul arata „NOU".
            #
            # Prezent pe 59/60, si pe toate 59 STRICT peste pretul platit — zero
            # referinte inversate sau inutile.
            "compare_text": "p.pricing.rrp",
            "price_parse": "eu_comma",
            # `nemarcat`, si e cinstit de ce nu e nici min30 nici prp: pe listare
            # zero „ultimele 30 de zile", zero „pret recomandat", zero „PRP", zero
            # „Omnibus". („cel mai mic pret" apare doar in textul de ajutor al
            # sortarii, iar „30 de zile" in politica de retur din <meta> — niciuna
            # nu eticheteaza campul; lectia bergfreunde.) Referinta ramane insa cea
            # mai buna posibila pentru un resigilat: acelasi SKU, acelasi magazin,
            # unitate noua. Vocabularul registrului n-are un al patrulea termen.
            "reference_kind": "nemarcat",
            #
            # FARA `stock_attr`: `data-availability-id` exista, dar e `2` pe 60/60,
            # deci nu se poate deosebi de o constanta de sablon — capcana masurata
            # pe toolnation si dovedita pe vivre.
            #
            # GRADUL resigilatului (ca nou / foarte buna / acceptabila) NU e in card:
            # cautat pe toate 60, zero aparitii. Sta pe PDP, in sectiunea catre care
            # duce chiar linkul cardului. Feed-ul spune „RESIGILAT: <produs>" fara
            # grad — onest, dar mai putin decat stie magazinul.
        },
        "overrides": {"price_selector": ".product-new-price"},
        "search": {"kind": "custom"},
        "notes": "RETAIL-3a",
    },
    # ── SEARCH-1 — ultimele doua magazine dinafara registrului ────────────────
    # Pana aici traiau EXCLUSIV in `_SCRAPERS_BY_SOURCE`: aveau scraper de cautare,
    # dar nicio metadata (label, categorie, tara). Intra acum ca sa poata fi randate
    # de selectorul din „Scanare Magazine" ca oricare altul — pagina se construieste
    # din registru, deci un magazin absent din el ar fi disparut din UI.
    "sole.ro": {
        "label": "Sole",
        "category": "beauty",
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "probed",
        "search": {"kind": "custom"},
        "notes": "SEARCH-1. Intra in registru DOAR cu scraperul de cautare istoric "
                 "(_SCRAPERS_BY_SOURCE); NU exista extractor de pagina de produs, deci "
                 "status ramane `probed` — validated ar pune domeniul in VALIDATED_DOMAINS "
                 "si ar promite o extractie PDP care nu exista.",
    },
    "farmaciatei.ro": {
        "label": "Farmacia Tei",
        "category": "farmacie",
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "probed",
        "search": {"kind": "custom"},
        "notes": "SEARCH-1. Ca sole.ro: doar cautare (comenzi.farmaciatei.ro), fara PDP, "
                 "status `probed`.",
    },

    # ── RETAIL-5c ─────────────────────────────────────────────────────────────
    "cel.ro": {
        "label": "CEL.ro",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D2, din dump-urile LST-D2 (7 septembrie) ──────────────────
        "listing": {
            "url": "https://www.cel.ro/resigilate/",
            # Forma `/0i-{n}`, citita verbatim din paginatorul paginii:
            # `<a data-ajaxp="true" data-scrolltop="true"
            #     href="https://www.cel.ro/resigilate/0i-2" >2</a>`
            # Confirmata live la DEAL-D2 (v. `notes`).
            "page_url_template": "https://www.cel.ro/resigilate/0i-{n}",
            # Corpul poarta DOAR `0i-1` si `0i-2`, deci doua pagini si ~120 de
            # produse. 3 e aia plus marja, conventia otter.
            "max_pages": 3,
            "currency": "RON",
            "card": ".product_data",
            "link": "a.product_link",
            "title": "h2.productTitle",
            "image_attr": ["src"],
            "price_text": "div.pret_n",
            "price_parse": "eu_comma",
            # FARA `compare_*`, si nu din lene: pe 60/60 de carduri singurul pret
            # e `div.pret_n`, iar clasa nodului parinte e chiar
            # `div.noDiscount price_part` — magazinul spune el insusi ca nu e
            # reducere. Zero <del>, zero <s>, zero `.pret_v`, zero eticheta
            # PRP/min30 pe toata pagina. Un `compare_text` aici ar FABRICA o
            # reducere pe fiecare card; axa D ramane pe R2 (minim istoric).
            "reference_kind": "nemarcat",
            # Starea E in titlu, ca SUFIX: „… (Negru) Resigilat" — deci nici aici
            # nu se pune vreun prefix.
        },
        "notes": "RETAIL-5c; DEAL-D2 — axa D pe `/resigilate/`, 60 de carduri pe pagina, doua pagini (`0i-1`, `0i-2`). ZERO referinta: pe 60/60 parintele pretului poarta chiar clasa `noDiscount`, deci deal-urile stau exclusiv pe R2 (minim istoric); un `compare_*` ar fabrica o reducere pe fiecare card. Starea e SUFIX in titlu („… (Negru) Resigilat”).",
    },
    "vexio.ro": {
        "label": "Vexio",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # DEAL-D10a — amprenta, si de ce e ea cheia intregului domeniu.
        #
        # Nota de mai jos se incheia cu „se reia doar daca se schimba amprenta".
        # LST-D9 a schimbat-o si domeniul s-a deschis din a doua incercare. Efect
        # COLATERAL deliberat: `_impersonate_for` e per DOMENIU, deci profilul se
        # aplica si pe axa L (PDP-urile `jsonld`). Verificat live la D10a inainte
        # de a fi scris aici — vezi nota.
        "impersonate": "firefox135",
        "notes": "RETAIL-5c; DEAL-D2 — in afara axei D: prima cerere de listare cu profilul implicit a primit challenge Cloudflare (403, `cf-mitigated: challenge`, `<title>Just a moment...`) chiar pe radacina domeniului. Se reia doar daca se schimba amprenta. "
                 "BRW-0d — zidul e TERMINAL si in browser (Turnstile), deci calea "
                 "de browser nu era o alternativa. LST-D9/DEAL-D10a — deschis pe "
                 "`firefox135`: pe implicit poarta da `None` si cererea directa 403 cu "
                 "`cf_chl_opt` x7 si ZERO ancore, pe a doua treapta de Chrome tot "
                 "`None`, iar Firefox a dat 200 cu 324.749 octeti si 1.024 de "
                 "ancore. Home-ul deblocat isi "
                 "declara singur cele doua listari. Profilul e acelasi cu al lui "
                 "43einhalb/flanco/notino, deci nu e o treapta noua.",
        # ── DEAL-D10a — din sonda LST-D9 §4.3 ─────────────────────────────────
        "listing": {
            # Ambele intrari sunt ANCORE ale home-ului deblocat, nu ghicite.
            "entries": [
                {"url": "https://www.vexio.ro/reduceri-finale/",
                 "page_url_template": "https://www.vexio.ro/reduceri-finale/pagina{n}/"},
                {"url": "https://www.vexio.ro/promotii/",
                 "page_url_template": "https://www.vexio.ro/promotii/pagina{n}/"},
            ],
            # Paginarea e in CALE, nu in query, si nu e o presupunere: p1 poarta
            # `<link rel="next" href=".../pagina2/">` si un bloc de paginare cu
            # `title="Pagina 2 din 147"` (respectiv 122 pe `/promotii/`). Plafonul
            # e insa 10, nu 147: 10 x 23 = 230 de produse per intrare si scan, in
            # linie cu conrad (15). Adancimea reala ramane consemnata aici ca sa
            # se vada ca plafonul e o ALEGERE de cost, nu o margine masurata.
            "max_pages": 10,
            "currency": "RON",
            "card": "article.product-box",
            # `a[data-ecproduct]` e ancora de PRODUS. Cardul mai are una,
            # `a.preview` („Vezi detalii"), catre acelasi URL, si un `h2.name > a`.
            "link": "a[data-ecproduct]",
            # `h2.name` poarta si MARCA („Logitech Boxe Z313, 25W RMS"), pe cand
            # atributul `title` al ancorei da doar modelul („Boxe Z313, 25W RMS").
            "title": "h2.name",
            # `div.price` are AMBELE preturi in text („263,99 lei 239,99 lei"),
            # deci selectorul trebuie scopat pe latura platita.
            "price_text": "div.price .discounted strong",
            "compare_text": "del.small",
            "price_parse": "eu_comma",
            # Fara eticheta legala pe card: nici PRP, nici minim de 30 de zile —
            # doar un pret taiat si un badge de procent. 23/23 si 20/20 il au.
            "reference_kind": "nemarcat",
        },
    },
    "mediagalaxy.ro": {
        "label": "Media Galaxy",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── STATE-2 — FRATE DE PLATFORMA cu altex.ro, acum si pe STARE ─────
        # DEAL-D2 masurase frateria pe DOM: Jaccard 1.000 pe clasele cardului
        # (LST-D2 §3.2), acelasi prim produs la acelasi pret. JSON-0 a masurat-o
        # si pe STARE — aceeasi cale de chei, acelasi `id: 844256` la aceleasi
        # preturi — iar STATE-2 a confirmat-o live pe pagina 2. Descriptorul
        # ramane IDENTIC in afara lui `url` si `page_url_template`, si un test o
        # impune (`test_altex_mediagalaxy_frati_de_platforma`), tocmai ca o
        # reparatie facuta la unul singur sa nu-l lase pe celalalt in urma.
        # Motivarea fiecarui camp: v. altex.ro.
        "listing": {
            "url": "https://mediagalaxy.ro/resigilate/",
            "page_url_template": "https://mediagalaxy.ro/resigilate/filtru/p/{n}/",
            # Reala e 157 (`toolbar.pagination`); 30 e acelasi plafon de buget ca
            # la altex, si trebuie sa RAMANA egal — testul de fratie il compara.
            "max_pages": 30,
            "currency": "RON",
            "state_extractor": "altex_next",
            "reference_kind": "nemarcat",
        },
        "notes": "RETAIL-5c; DEAL-D2 (CSS, inlocuit); STATE-2 — axa D pe `/resigilate/` "
                 "prin `altex_next`, ACELASI extractor ca altex.ro: gazda vine din "
                 "`runtimeConfig.settings.baseUrl` (aici `https://mediagalaxy.ro`, "
                 "gateway `cerberus` in loc de `fenrir`), deci un singur cod acopera "
                 "ambii frati. 48 de produse pe pagina, 157 de pagini anuntate, "
                 "plafonate la 30 pe scan. Pagina 2 MASURATA live: 48 de carduri, toate "
                 "pe gazda mediagalaxy.ro.",
    },

    # ── FASHION-1b ────────────────────────────────────────────────────────────
    "answear.ro": {
        "label": "Answear",
        "category": "fashion",
        "channel": "haine",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": ("FASHION-1b"
                 " DEAL-D4 - RAMAS IN AFARA axei D: home-ul are 219 de ancore si un nav de catalog complet, dar NICIUNA nu poarta `reduceri|sale|outlet`. Singura campanie, `/s/back-to-school` („pana la -25%”), ar fi iesit cu cuvantul `procent` in lista sondei - deci „nicio candidata sub lista de cuvinte”, nu „magazinul n-are reduceri”."
                 " LST-D7 - INTRA, dar pe STARE, si asta e chiar lectia: pagina are"
                 " ancore `data-test` STABILE, iar descriptorul CSS scris pe ele e"
                 " gresit in doua feluri tacute: `priceSaleWithMinimalDesktop` poarta"
                 " doar eticheta („Pret actual:”), deci pretul iese None si TOATE cele"
                 " 80 de carduri se sar; iar `priceWithMinimalDesktop` poarta textul"
                 " intreg al Omnibusului („...ultimele 30 de zile...: 309,90 LEI”), din"
                 " care `eu_comma` scoate 30309.9. Din stare, cele trei preturi sunt"
                 " campuri numerice numite."),
        # ── DEAL-D7, din dump-urile LST-D7 (p1/p2/plast) ────────────────────
        "listing": {
            # CAMPANIE CU TERMEN, si e singura candidata pe care home-ul o declara
            # (a doua ancora cu procent duce la `/newsletter`, un formular). Daca
            # expira, descriptorul moare TACUT — de urmarit la prima listare goala.
            # ── DEAL-D11 — de la o campanie la fatetele de sale (LST-D10 §5) ──
            # Verdictul DEAL-D4 de mai sus („home-ul are 219 de ancore si NICIUNA
            # nu poarta `reduceri|sale|outlet`”) era corect despre ancorele
            # RANDATE, si gresit ca verdict despre magazin: taxonomia de sale
            # traieste in STARE. Meniul are 4 noduri `label == "Sale"`
            # (Femei/Barbati/Copii cu `urlType` simbolic, si Home ca
            # `rawUrlItem`) plus 220 de noduri cu `options.isSaleLink == true`.
            #
            # Forma `/sale/<departament>` e DOVEDITA pe DOUA departamente, nu
            # extrapolata de pe unul: starea fiecarei pagini isi declara singura
            # parametrii — `{"category": "home"|"femei", "page": n,
            # "specialPage": {"sale": 1}, "productsPerPage": 80}`. Cele doua
            # listari sunt DISJUNCTE (zero produse comune), deci sunt liste
            # diferite, nu aceeasi pagina cu alt titlu.
            #
            # `barbati` si `copii` NU intra acum: in meniu sunt `urlType`
            # simbolic (`saleMale`/`saleChild`), rezolvat client-side, si niciun
            # URL literal nu exista in stare. Intra dupa ce sunt CERUTE.
            "entries": [
                # Campania originala (DEAL-D7), neschimbata.
                {"url": "https://answear.ro/s/back-to-school",
                 "page_url_template": "https://answear.ro/s/back-to-school?page={n}"},
                # „home” e departamentul de CASA, nu radacina sitului: nav-ul are
                # `/k/home/living-si-dormitor/…` alaturi de `/k/femei/…`. E
                # singurul URL de sale LITERAL din stare (`rawUrlItem`).
                {"url": "https://answear.ro/sale/home",
                 "page_url_template": "https://answear.ro/sale/home?page={n}"},
                {"url": "https://answear.ro/sale/femei",
                 "page_url_template": "https://answear.ro/sale/femei?page={n}"},
            ],
            # Paginarea E masurata: `?page=2` a dat 80 de produse noi, zero comune.
            # Adancimea NU: `data.count` din stare e 162.614, adica tot catalogul,
            # nu campania. 10 e plafon de buget; coada se inchide oricum singura —
            # `?page=500` raspunde 500, iar un 5xx pe o pagina > 1 e sfarsit de
            # intrare in scanner (STATE-1), cu paginile citite pastrate.
            #
            # DEAL-D11 — plafonul urca de la 10 la 20, si diferenta fata de nota
            # de mai sus conteaza: pe fatetele de sale adancimea E declarata de
            # pagina, nu ghicita. `/sale/femei` poarta ancora `?page=125`, adica
            # ~10.000 de produse. 20 ramane tot o ALEGERE de cost (20 x 80 =
            # 1.600 per intrare si scan), nu o margine masurata.
            "max_pages": 20, "currency": "RON",
            "state_extractor": "answear_state",
            # `min30`: referinta e `priceMinimal`, campul etichetat pe card „cel mai
            # mic pret din ultimele 30 de zile inainte de reducere". NU `priceRegular`
            # — cele doua diverg pe 7/80 (p1) si 27/80 (p2).
            "reference_kind": "min30",
        },
    },
    "fashiondays.ro": {
        "label": "Fashion Days",
        "category": "fashion",
        "channel": "haine",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            # NU `/shop/outlet-w/`: acela e un HUB (`<h1>ALEGE-TI MARIMEA</h1>`,
            # `<h1>Prinde ofertele in functie de categorie</h1>`), 240 de aparitii
            # ale sirului `product-card` si ZERO carduri cu pret. Listarea reala e
            # campania, cu 6993 de produse anuntate.
            "url": "https://www.fashiondays.ro/s/sale-sale-sale-w",
            "page_url_template": "https://www.fashiondays.ro/s/sale-sale-sale-w?page={n}",
            # `rel=next` corect, `p1 ∩ p2 = 0` din 90 (paginare reala), iar
            # `?page=500` da 404 — semnatura de oprire curata, pe care scannerul o
            # trateaza ca sfarsit de paginare (VAL D), nu ca eroare.
            "max_pages": 40,
            "currency": "RON",
            "card": ".product-card",
            "link": "a.campaign-item",
            "title": "span.product-card-name",
            # IMG-1a/1a2: `src` e un placeholder (`/images/blank_310x465.png`).
            "image": "img.lazy",
            "image_attr": ["data-original", "src"],
            # Calea de ATRIBUT, si nu din eleganta: textul vizibil vine spart de un
            # `<sup>` („299 99 lei"), deci ar cere `eu_sup` — ancora poarta insa
            # chiar numarul, cu punct zecimal.
            "price_attr": ["a.campaign-item", "data-gtm-price"],
            # `cmmp30` = Cel Mai Mic Pret 30 de zile, adica Omnibus-ul, pe 90/90 de
            # carduri. Coexista cu `data-gtm-price-rrp` (PRP, tot 90/90) — alegerea
            # nu e o ghicire, semantica e scrisa CHIAR IN NUMELE campurilor.
            "compare_attr": ["span[data-cmmp30-price]", "data-cmmp30-price"],
            "price_parse": "attr_float",
            "reference_kind": "min30",
        },
        "notes": ("FASHION-1b"
                 " DEAL-D4 - axa D: campania `/s/sale-sale-sale-w` (90/pagina, 6993 de produse), NU `/shop/outlet-w/`, care e un hub fara preturi. Pretul si Omnibus-ul se citesc din ATRIBUTE (`data-gtm-price`, `data-cmmp30-price`), fiindca textul vizibil are zecimalele intr-un `<sup>`. `?page=500` -> 404, oprire curata."),
    },
    "epantofi.ro": {
        "label": "ePantofi",
        "category": "fashion",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        # Frate de platforma cu modivo.ro (eobuwie), dovedit pe CLASE, nu pe numele
        # platformei: `a.product-card-link`, `.price-container` si `.omnibus` sunt
        # exact cheile descriptorului lui modivo din registru.
        "listing": {
            # ATENTIE: intrarea e o CAMPANIE CU TERMEN — pagina spune verbatim
            # „Reducere la produsele selectate, la cumparaturi de la 379 lei /
            # Valabil pana pe 08.09". Analogia cu modivo (`akcja:new_sale`) a fost
            # CERUTA la DEAL-D4 si a raspuns 404 cu zero carduri, deci nu exista o
            # intrare permanenta echivalenta. Cand campania expira, scanul va da 0
            # carduri: asta NU e un bug de selectori, ci cererea de re-masurare a
            # intrarii.
            "url": "https://epantofi.ro/c/epantofi/akcja:extraseptember_lp",
            "page_url_template": "https://epantofi.ro/c/epantofi/akcja:extraseptember_lp?p={n}",
            # `p1 ∩ p2 = 4` din 76 (cele 4 carduri `sponsored`, care se repeta),
            # iar `?p=500` da 404 — oprire curata.
            "max_pages": 25,
            "currency": "RON",
            "card": ".product-list-item",
            "link": "a.product-card-link",
            "title": ".product-details > div:first-child",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image": "img.image",
            "image_attr": ["src"],
            "price_text": ".price-container",
            # Omnibus etichetat, verbatim: „Prețul actual 174,90 Lei / Prețul
            # inițial 213,00 Lei -17% / Cel mai mic preț 196,00 Lei -10%". Prezent
            # pe 28 din 76 pe p1 si pe 31 din 76 pe p2 — restul cardurilor n-au
            # linia, deci `compare_at` None acolo e CORECT, nu un selector rupt.
            "compare_text": ".omnibus .line:nth-child(2) .value",
            "price_parse": "eu_comma",
            "reference_kind": "min30",
        },
        "notes": ("FASHION-1b"
                 " DEAL-D4 - axa D, frate de platforma cu modivo.ro (eobuwie: aceleasi `a.product-card-link` / `.price-container` / `.omnibus`). Intrarea e o CAMPANIE cu termen („Valabil pana pe 08.09”), fiindca echivalentul permanent al lui modivo (`akcja:new_sale`) a fost CERUT la DEAL-D4 si da 404. Un scan cu 0 carduri inseamna campanie expirata, nu selectori rupti."),
    },
    "modivo.ro": {
        "label": "Modivo",
        "category": "fashion",
        "channel": "haine",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-1b",
        # DEAL-2 — masurat la LST-3b (dump-uri `scripts/diagnostics/dumps_lst3b/`).
        # Platforma eobuwie (Nuxt/Vue), aceeasi cu epantofi.ro — dovedit in dump-ul
        # LST-3: `Go.MODIVO={type:"all"};Go.eobuwie={type:ni};Go.CCC={type:ni};...`
        # si cheia de configurare `"roROEob","epantofi.ro","roROBrandEob"`.
        #
        # URL-ul NU e o conventie ghicita: `/outlet` e link in propriul nav dar da
        # 404, iar fateta reala a fost harvestata verbatim din navigatia paginii de
        # 404, sub ancora „Reduceri recente":
        #   /c/femei/akcja:new_sale/omnibus_discount:~r-5-99?itm_source=ovm&...
        # Parametrii `itm_*` (atributie de campanie) sunt taiati deliberat: intr-un
        # descriptor intra fateta, nu attribution-ul cuiva.
        #
        # Totalul NU e in text vizibil — singura sursa e `offerCount` din ld+json
        # (1490), acelasi nod care e capcana de PRET (vezi mai jos). 1490 / 73 pe
        # pagina => 21 de pagini, iar linkurile din DOM merg pana la `p=21`.
        "listing": {
            "url": "https://modivo.ro/c/femei/akcja:new_sale/omnibus_discount:~r-5-99",
            "page_url_template": "https://modivo.ro/c/femei/akcja:new_sale/"
                                 "omnibus_discount:~r-5-99?p={n}",
            # DERIVAT, nu citat: 21 de pagini masurate plus marja, conventia otter.
            "max_pages": 25,
            # Din COD: langa suma scrie „Lei", nu „RON".
            "currency": "RON",
            "card": ".product-card-small",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src"],
            "link": "a.product-card-link",
            # Cardul n-are un nod unic de nume: `div.title` e MARCA („G-STAR") si
            # `div.description` e descrierea („Blugi · Bleumarin · Relaxed Fit").
            # Parintele lor e un `div` FARA clasa cu exact acesti doi copii, deci se
            # tinteste prin pozitie in `.product-details`, iar `_titlu_of` concateneaza:
            # „G-STAR Blugi · Bleumarin · Relaxed Fit". `img[alt]` e mai bogat (are si
            # codul de model) dar ar fi cerut un camp nou de schema — nu e nevoie.
            "title": ".product-details > div:first-child",
            # Textul include eticheta sr-only „Prețul actual", dar ea n-are NICIO
            # cifra, deci `_pret_eu_comma` o curata odata cu „Lei". Formele masurate:
            # „1.072,90 Lei" (separator de mii cu punct) pe 15 din 73 de carduri.
            "price_text": ".price-container",
            #
            # (1) LINIA A DOUA, deliberat. Blocul `.omnibus` are DOUA linii etichetate
            #     in romana: „Prețul inițial" (pret de lista) si „Cel mai mic preț"
            #     (referinta Omnibus). Ele DIVERG pe 32 din 73 de carduri (p1) — de
            #     exemplu initial 229,90 vs cel-mai-mic 190,90 la un pret curent de
            #     171,90 — deci alegerea schimba marja raportata. Luam a doua, ca marja
            #     sa fie cea onesta: lectia PRP de la nichiduta („marja reala e mai
            #     mica decat sugereaza eticheta"). Verificat ca linia 2 CHIAR poarta
            #     eticheta „Cel mai mic preț" pe 146/146 de carduri, pe ambele pagini —
            #     testul o pinuieste pe TEXT, nu doar pe pozitie.
            #     Ambele referinte sunt strict peste pretul curent pe 146/146, deci
            #     niciuna n-ar produce o reducere <= 0.
            #
            # (2) `:nth-child(2)` e POZITIONAL, fiindca eticheta e un nod-text si nu
            #     se poate selecta CSS. Riscul concret: `.omnibus` incepe cu un
            #     `<!-- -->` (placeholder Vue). Comentariul nu e element, deci acum nu
            #     deplaseaza nimic — dar daca devine element, linia 2 se muta. DACA
            #     `compare_at` incepe sa iasa None in masa, AICI se cauta intai.
            "compare_text": ".omnibus .line:nth-child(2) .value",
            "price_parse": "eu_comma",
            # Eticheta vizibila „Cel mai mic preț" + numele campurilor din stare
            # (`omnibus_price`, `show_omnibus_price`) + fateta `omnibus_discount` din
            # URL. ATENTIE: „30 de zile" apare O SINGURA DATA in toata sursa si e
            # „30 de zile pentru retur" — politica de retur, NU fereastra de pret.
            # Fereastra nu e scrisa vizibil nicaieri; verdictul se sprijina pe
            # eticheta campului plus afisarea Omnibus-conforma cu doua linii.
            "reference_kind": "min30",
            #
            # (3) ACOPERIRE PARTIALA, asumata (tiparul tezyo): fateta e per SECTIUNE,
            #     iar aici intra doar `femei`. Nav-ul arata si
            #     `/c/barbati/akcja:new_sale/omnibus_discount:~r-5-99` si
            #     `/c/copii/...` — nemasurate. Se adauga cand domeniul capata mai
            #     multe listari, extensia care asteapta si la powerup si la nichiduta.
            #
            # (4) `price-wrapper discount` NU e semnal de reducere. Pe fateta asta e pe
            #     73/73 (toate chiar reduse), dar pe categoria masurata gresit la LST-3
            #     era pe 70 din 72 de carduri cu ZERO preturi taiate — clasa e pusa de
            #     componenta, nu de starea produsului. „E redus?" se citeste din
            #     prezenta blocului `.omnibus`, nu din ea.
            #
            # CAPCANA de pret, pentru cine ar fi tentat de datele structurate: singurul
            # `Product` din ld+json e la nivel de CATEGORIE — `name: "Femei"`, cu
            # `AggregateOffer` `lowPrice: 55` / `highPrice: 2911` / `offerCount: 1490`.
            # Citit ca pret de produs ar da 55 lei pe orice card. E buna doar la numarat.
            # In plus `CollectionPage.mainEntity.ItemList` poarta numele in POLONEZA
            # netradusa („Jeansy … Granatowy" acolo unde DOM-ul scrie „Blugi …
            # Bleumarin"), deci nici el nu e sursa de titlu.
        },
    },

    # ── FASHION-2 ─────────────────────────────────────────────────────────────
    "bstn.com": {
        "label": "BSTN",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "FASHION-2. JSON-0 — ZID: home-ul a raspuns 403 cu o pagina de "
                 "asteptare de marca (2641 de octeti, `<title>BSTN Store</title>`, "
                 "ZERO ancore, doar logoul SVG), deci n-a existat niciun link de "
                 "listare de descoperit. De notat ca `_detecteaza_blocare` NU l-a "
                 "prins: regula de shell cere si titlu gol, iar titlul e nevid "
                 "(v. GUARD-1 in docs/catalog_domain_log.md). "
                 "LST-D9/DEAL-D10b — zidul a cazut la SCHIMBAREA AMPRENTEI, din "
                 "prima incercare alternativa. Ce merita retinut: la JSON-0 "
                 "domeniul daduse 403 si in BROWSER REAL, deci calea de browser nu "
                 "era o alternativa — iar HTTP-ul cu alta amprenta trece pe unde "
                 "browserul nu trecuse. Home-ul deblocat (386.844 octeti, 573 de "
                 "ancore) isi declara singur 12 ancore de sale, pe trei genuri x "
                 "patru rafturi.",
        # DEAL-D10b — profilul se aplica per DOMENIU, deci si pe axa L (`jsonld`).
        # Verificat LIVE la D10b (PASUL 4) inainte de a fi scris aici.
        "impersonate": "chrome131",
        # ── DEAL-D10b — din sonda LST-D9 §4.4 ─────────────────────────────────
        "listing": {
            # O SINGURA intrare, si asta e o alegere, nu o omisiune. Home-ul
            # declara 12 ancore de sale, dar doar `/eu_en/men/sale` a fost CERUTA
            # si masurata (96 de hituri, nbHits 8.463). Regula nichiduta spune ca
            # fatetele nemasurate pot intra cu `max_pages: 1` cand markup-ul e
            # dovedit identic — aici insa nu e dovedit pe nimic: `women/sale` si
            # `kids/sale` n-au fost atinse deloc. Intra la prima runda care le cere.
            "url": "https://www.bstn.com/eu_en/men/sale",
            # PAGINA UNICA, si nu din prudenta: pagina NU-si declara paginarea in
            # niciun fel. Zero `?page=`, zero `rel="next"`, zero `/page/N`; ruta
            # Next e `/[gender]/[level2]` cu `query: {gender, level2}`, fara
            # parametru de pagina. Starea Algolia stie ca sunt 89 de pagini
            # (`nbPages`, din 8.463 de hituri la 96 pe pagina), dar asta e o cifra
            # a RASPUNSULUI, nu un URL: raftul urmator se cere din browser prin
            # API, nu printr-o adresa pe care s-o putem construi.
            #
            # Un `?page={n}` scris aici ar fi un URL INVENTAT — exact ce runda
            # asta n-are voie sa faca. Deci 96 de produse pe scan, iar restul de
            # 8.367 raman pentru o runda care chiar masoara forma de paginare.
            "max_pages": 1,
            "currency": "EUR",
            "state_extractor": "bstn_next",
            # `default_original_formated` e pretul dinainte al ACELUIASI produs, nu
            # o eticheta legala: nici Omnibus, nici PRP.
            "reference_kind": "nemarcat",
        },
    },
    # Cheia e CU subdomeniu: _domain_of taie doar "www.", iar refresh-ul compara
    # pe egalitate exacta. Domeniul GOL (afew-store.com) nu se adauga: redirecteaza
    # spre storefront-ul de.*, iar catalogul e acelasi (acelasi handle, acelasi pret
    # masurate pe ambele la SHOP-1a) — o a doua intrare ar fi acelasi magazin de
    # doua ori.
    "en.afew-store.com": {
        "label": "Afew Store",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "FASHION-2, SHOP-1a",
    },

    # ── FASHION-2b ────────────────────────────────────────────────────────────
    "prm.com": {
        "label": "PRM",
        "category": "fashion",
        "channel": "sneakers",
        # Tara exacta NU e confirmata de sonda; se corecteaza la un val viitor,
        # nu se ghiceste.
        "country": "EU",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            # Vitrina `/ro/`, cea validata pe axa L: radacina globala `prm.com/`
            # are 11 KB si e o poarta de localizare, nu magazinul.
            #
            # PROD-1 — intrarea a fost SCHIMBATA fiindca a expirat. `/ro/s/final-sale`
            # a dat 404 pe pagina 1 la scanul din 10.09: `/ro/s/<slug>` sunt
            # PSEUDOCATEGORII, adica campanii editoriale, iar campaniile se sting.
            # Aceeasi capcana ca la carrefour, cu alt final: acolo campania s-a
            # micsorat, aici a disparut.
            #
            # Inlocuitorul e PERMANENT prin constructie: nu o alta campanie, ci
            # FILTRUL de reduceri al magazinului, aplicat pe cele doua categorii de
            # nivel 1. Filtrul e citit verbatim din payload-ul de lista al
            # dump-ului LST-D4: `{"name":"discount","label":"Doar promoţii",
            # "param":"reducere","type":"CHECKBOX","items":{"value":1,...}}` — de
            # unde `?reducere=1`. Slugurile `femei` / `barbati` sunt intrarile
            # „Vezi toate" de nivel 1 din acelasi meniu.
            #
            # CAPCANA, consemnata fiindca era gata sa treaca drept semnal: meniul
            # marcheaza `"isSaleLink":true`, dar pe 94 din 94 de intrari de
            # categorie — constanta de sablon, nu marcaj de reducere. A treia oara
            # dupa `data-availability-id=2` pe eMAG si `data-*`-ul de la toolnation.
            #
            # Masurat prin poarta (PROD-1, 3 cereri): femei 200 / 80 de carduri,
            # barbati 200 / 80, si — spre deosebire de `final-sale`, unde 46 din 80
            # de carduri n-aveau pret taiat — 80/80 cu pret SI referinta pe ambele,
            # ceea ce e chiar sensul filtrului. Listele anunta 7 672 (femei) si
            # 9 374 (barbati) de produse reduse, adica ~96 si ~117 pagini a 80.
            "entries": [
                {"url": "https://prm.com/ro/k/femei?reducere=1",
                 "page_url_template": "https://prm.com/ro/k/femei?reducere=1&page={n}"},
                {"url": "https://prm.com/ro/k/barbati?reducere=1",
                 "page_url_template": "https://prm.com/ro/k/barbati?reducere=1&page={n}"},
            ],
            # `p1 ∩ p2 = 0` din 80 — paginare reala, re-confirmata la PROD-1 pe
            # noua intrare (`femei`, `&page=2`: 80 de carduri, zero comune cu p1).
            # Templateul e masurat pe `femei`; pe `barbati` e aceeasi ruta si
            # acelasi mecanism — paginarea sta in query string, nu in slug.
            #
            # Coada: pe vechea intrare `?page=500` raspundea HTTP **500**. Nota de
            # atunci spunea ca un 5xx pierde tot scanul domeniului — nu mai e
            # adevarat, tocmai fiindca acea masuratoare a produs STATE-1: orice
            # raspuns nereusit pe o pagina > 1 a unei intrari care a citit deja o
            # pagina e SFARSIT DE INTRARE cu WARN, iar paginile citite raman comise.
            #
            # `max_pages` ramane 25 si NU se atinge la PROD-1. Cu doua intrari
            # inseamna 25 de pagini pentru fiecare, adica 50 x 80 = 4 000 de produse
            # in ~4 min la ~4,5 s pagina (1,2 s fetch masurat + `_pauza()`) — de la
            # 25 de pagini pe o singura lista. Plafonul e acum DEPARTE de coada
            # (~96 si ~117 pagini disponibile), deci nu mai e o plasa pe sfarsitul
            # listei, ci pur si simplu bugetul de timp al domeniului.
            "max_pages": 25,
            "currency": "RON",
            # Clase de modul CSS cu hash de build (`__cAcr_`, `__eYDbk`): se prind
            # pe PORTIUNEA STABILA a numelui, nu pe hash.
            "card": "[class*='Products__productsFullWide']",
            "link": "a",
            "title": "[class*='productCardName']",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image": "img",
            "image_attr": ["src", "srcset"],
            # DOI selectori, si asta e o masuratoare: cardurile NEREDUSE (46 din
            # 80) n-au `priceSaleMinimal`, ci `priceRegular__`. Cu unul singur,
            # descriptorul citea 34 din 80 si arata a succes. `priceRegular__` nu
            # se confunda cu `priceRegularMinimalLabel__`: acolo dupa
            # `priceRegular` vine `M`, nu `_`.
            "price_text": "[class*='priceSaleMinimal'], [class*='priceRegular__']",
            # Primul nod cu clasa asta e „Preț normal: 94,90 LEI". Al doilea e
            # „Cel mai mic preț DE LA LANSARE" — alta semantica decat Omnibus-ul
            # („in ultimele 30 de zile"), de aia `reference_kind` NU e `min30`.
            "compare_text": "[class*='priceRegularMinimalLabel']",
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
        },
        "notes": ("FASHION-2b"
                 " DEAL-D4 - axa D pe vitrina `/ro/`: `/s/final-sale`, 80 de carduri. Referinta e „Preț normal”, NU Omnibus: fraza „Cel mai mic preț DE LA LANSARE” de pe acelasi card e alta semantica. Cardurile nereduse au alt nod de pret, deci `price_text` are doi selectori. ATENTIE: `?page=500` da HTTP 500, iar scannerul trateaza ca final de paginare doar 404 - un 5xx ridica si pierde scanul domeniului."
                 " PROD-1 - intrarea `/s/final-sale` a EXPIRAT (404 pe pagina 1 la scanul din 10.09): `/ro/s/<slug>` sunt campanii editoriale. Inlocuita cu doua intrari PERMANENTE, filtrul propriu de reduceri pe categoriile de nivel 1: `/ro/k/femei?reducere=1` si `/ro/k/barbati?reducere=1` (`param: reducere`, CHECKBOX, valoare 1, citit din payload-ul LST-D4). Masurat: 80 de carduri pe fiecare, 80/80 cu pret SI referinta, p2 fara niciun link comun cu p1. `isSaleLink: true` din meniu NU e semnal - e pe 94/94 de categorii."),
    },
    "sneakersnstuff.com": {
        "label": "Sneakersnstuff",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "SE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D3, din dump-urile LST-D3 (7 septembrie) ──────────────────
        "listing": {
            "url": "https://www.sneakersnstuff.com/collections/sale",
            # `<link rel="next" href="…/collections/sale?page=2">`
            "page_url_template": ("https://www.sneakersnstuff.com/collections/sale"
                                  "?page={n}"),
            # Oprirea e MASURATA, nu presupusa: p1 si p2 n-au niciun handle comun,
            # iar `?page=500` intoarce grila GOALA (0 carduri). 40 e conventia otter.
            "max_pages": 40,
            "currency": "EUR",
            "card": ".card--product",
            "link": "a[href]",
            "title": ".card__title",
            # `src` e PROTOCOL-RELATIV (`//www.sneakersnstuff.com/cdn/shop/files/…`);
            # normalizatorul ii pune schema.
            "image_attr": ["src"],
            # `<span class="price__current">€147</span>` — preturi INTREGI, fara
            # zecimale, simbolul INAINTE si lipit de suma.
            "price_text": "span.price__current",
            "compare_text": "s.price__original",
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
            #
            # Shopify, pe `/collections/`. Enumerarea `/products.json` N-A FOST
            # masurata la LST-D3. Daca e deschisa, `method: shopify` ar bate acest
            # descriptor (acelasi caz ca sneakerindustry la SNK-1) — se verifica
            # intr-o sonda, nu se presupune aici.
        },
        "notes": "FASHION-2b; DEAL-D3 - axa D pe `/collections/sale` (Shopify), 24 "
                 "de carduri pe pagina, preturi INTREGI in EUR. Oprirea e MASURATA: "
                 "p1 si p2 n-au niciun handle comun, iar `?page=500` intoarce grila "
                 "GOALA. Enumerarea `/products.json` N-A fost masurata - daca e "
                 "deschisa, `method: shopify` ar bate descriptorul (acelasi caz ca "
                 "sneakerindustry la SNK-1); de verificat intr-o sonda.",
    },

    # ── FASHION-4 ─────────────────────────────────────────────────────────────
    "aboutyou.ro": {
        "label": "About You",
        "category": "fashion",
        "channel": "haine",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.aboutyou.ro/c/femei/sale-32543",
            # Nicio paginare in HTML-ul brut, deci `p2` n-a fost nici macar cerut
            # la sonda. 30 de carduri pe pagina; restul catalogului de sale cere
            # alt mecanism (v. `notes`).
            "max_pages": 1,
            "currency": "RON",
            # TOATE clasele magazinului sunt hash-uri de build (`.she0wnd`,
            # `.w13wcbtj`) si se schimba la fiecare deploy — `data-testid`-urile
            # sunt SINGURUL motiv pentru care domeniul e propozabil.
            "card": "li[data-testid^='productTileTracker-']",
            "link": "a[data-testid^='productTile-']",
            "title": "[data-testid='productName']",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src", "srcset"],
            # `<span data-testid="finalPrice"><span …>242,90 lei</span></span>`
            "price_text": "[data-testid='finalPrice']",
            # Omnibus-ul, cu eticheta vizibila „Ultimul preț minim:" si valoarea
            # intr-un nod propriu (`div[data-value="true"]` = `218,61 lei`).
            # Coexista cu `[data-testid='originalPrice']` = „Preț original:
            # 489,00 lei", care e PRP-ul: cardul poarta DOUA referinte cu
            # semantici diferite, iar descriptorul o alege explicit pe cea legala.
            #
            # `> span:first-child` NU e decor. Pe cardurile unde pretul curent e
            # SUB minim, `div[data-value="true"]` are DOI copii:
            # `<span><s>70,32 lei</s></span><span> -2%</span>`. Fara restrictia la
            # primul, `_text_of` da „70,32 lei -2%" si `_pret_eu_comma` lipeste
            # cifra procentului: 70.322 in loc de 70.32. Prins de fixture-ul
            # DEAL-D4 pe al DOILEA card — controlul LST-D4 se uitase doar la primul.
            "compare_text": ("[data-testid='lowestProductPrice30D'] "
                             "[data-value='true'] > span:first-child"),
            "price_parse": "eu_comma",
            "reference_kind": "min30",
            # ATENTIE la citirea marjelor: pe 6 din 30 de carduri pretul e
            # precedat de „De la" („De la 199,00 lei"), langa „Mărimi disponibile",
            # deci acolo e pretul VARIANTEI CELEI MAI IEFTINE, nu al produsului.
            # Linkul duce la PDP-ul grupului, nu al marimii.
        },
        "notes": ("FASHION-4"
                 " DEAL-D4 - axa D: `/c/femei/sale-32543`, 30 de carduri, o singura pagina (zero paginare in HTML-ul brut). Omnibus pe card sub numele „Ultimul preț minim” (`data-testid=lowestProductPrice30D`), langa un „Preț original” care e PRP. Descriptorul sta pe `data-testid`: clasele magazinului sunt hash-uri de build."),
    },
    "trendyol.com": {
        "label": "Trendyol",
        "category": "fashion",
        "channel": "haine",
        "country": "TR",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": ("FASHION-4"
                 " DEAL-D4 - RAMAS IN AFARA axei D: JS_ONLY. Candidata din home a fost un BANNER (`a.banner-link`), nu o ancora de navigatie; pagina de campanie are 0 jetoane de pret, 0 carduri si 0 colectii de produse in blobul de stare. O CATEGORIE (nu o campanie) ramane nemasurata. "
                 "LST-D5 — MASURATA, si verdictul se nuanteaza: campania din "
                 "banner ramane JS_ONLY, dar o CATEGORIE din nav poarta `ld+json` "
                 "`ItemList` cu 36 de produse complete server-side, 36/36 cu "
                 "`offers.price` si `priceCurrency: RON` — forma identica pe doua "
                 "categorii (`/ro/rochii-x-c56`, `/ro/bluze-x-c1019`), deci nu e "
                 "accident. Deci CERE_MECANISM („listare din ItemList”), nu "
                 "JS_ONLY: grila CSS da 0 carduri, iar `numberOfItems` anunta "
                 "156 754 desi lista poarta 36 (prima pagina). `offers` n-are "
                 "pret de referinta -> doar R2. Categoriile sunt catalog intreg, "
                 "Categoriile sunt catalog intreg, nu listari de reduceri; fateta de reducere ramane nemasurata. "
                 "LST-D7 - masurata acum, si verdictul e NEPOTRIVIT: fateta de "
                 "reducere NU EXISTA in niciun URL pe care pagina il declara. "
                 "Cautarea in dump a gasit `?fl=<slug>` (slug-uri de campanie), "
                 "`&sst=BEST_SELLER|MOST_FAVOURITE` (sortare, nu dupa reducere) si "
                 "`&wc=`/`&attr=` (categorie si atribut) — niciun `indirim=`, "
                 "`discount=` sau `sale=`. Nu s-a ghicit niciun parametru. Ce se "
                 "putea cere, fiindca era citit verbatim din rutarea paginii: "
                 "`/ro/flas-indirimler` -> 404 (ruta exista in router, nu si pe "
                 "vitrina RO), `/ro/campaign/list/barbati/2` -> 200 dar e un WIDGET "
                 "de 16 produse fara paginare, iar `/ro/campaign/list/"
                 "back-to-school-sale/101627` -> 200 cu ZERO produse. Deci nici "
                 "macar „16 produse per hub” nu e o forma stabila."),
    },

    # ── ACCESS-2 ──────────────────────────────────────────────────────────────
    "endclothing.com": {
        "label": "END.",
        "category": "sneakers",
        "channel": "haine",
        "country": "GB",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": ("ACCESS-2; DEAL-D3 - JS_ONLY pe axa D: `/eu/sale` raspunde 200 cu "
                 "1,5 MB si ZERO carduri, iar `__NEXT_DATA__`-ul de 1,37 MB n-are "
                 "produse - cele 105 chei `price` din el sunt praguri de livrare "
                 "(`config/shipping/methods`), iar singurele array-uri mari sunt "
                 "arbori de categorii. Zero rezultate de cautare in corp, iar "
                 "`algolia` apare de 14 ori: produsele vin client-side."
                 " DEAL-D4 - corectie de MONEDA la nota de mai sus: dump-ul aceleiasi pagini, recitit cu un jeton de pret care cunoaste toate monedele, arata `RON972` / `RON294` - pagina servea RON, nu GBP. Verdictul JS_ONLY nu se schimba (DOM-ul e gol), doar moneda din nota."
                 "LST-D7 - DOM-ul ramane gol, dar pagina NU e JS_ONLY: raspunsul "
                 "Algolia e INLINAT in `__NEXT_DATA__` "
                 "(`initialAlgoliaState.results.hits`, 120 de hit-uri, cu nbHits/"
                 "nbPages/hitsPerPage si `params`-ul cererii, filtrul de sale "
                 "verbatim). Deci INTRA pe STARE. API-ul ramane deschis ca mecanism "
                 "VIITOR, pentru adancime: componentele sunt toate in pagina "
                 "(app id, cheia PUBLICA de cautare, indexul, parametrii), iar "
                 "gazdele `search{1,2,3}web.endclothing.com` sunt subdomenii ale "
                 "domeniului validat, deci allow-list-ul NU e obstacolul — poarta e "
                 "GET-only, iar forma de interogare Algolia cere POST. Masuratoarea "
                 "pe fir a ramas NEFACUTA (LST-D7 §3.4)."
                 " IMG-2 - imaginile INTRA: CDN-ul serveste pozele prin URL-uri cu"
                 " virgule in calea de transformare"
                 " (`f_auto,q_auto:eco,w_400,h_400`), pe care `normalizeaza_imagine`"
                 " le taia la prima virgula; regula ei s-a stramtat la srcset-urile"
                 " REALE (cele cu descriptori), deci URL-ul trece intreg."),
        # ── DEAL-D7, din dump-urile LST-D7 (p1 = all-sale, p1alt = sneakers) ─
        "listing": {
            "entries": [
                # DOAR cele doua categorii MASURATE. Hub-ul `/eu/sale` declara 28,
                # dar celelalte 26 n-au fost cerute niciodata: un URL nemasurat n-are
                # ce cauta intr-un descriptor (regula nichiduta).
                {"url": "https://www.endclothing.com/eu/sale/all-sale",
                 "max_pages": 1},
                {"url": "https://www.endclothing.com/eu/sale/sneakers",
                 "max_pages": 1},
            ],
            # `max_pages: 1` e MASURATOARE, nu comoditate: forma de URL a paginii 2
            # nu apare NICAIERI in pagina — nici `?page=`, nici `/page/`, niciun
            # `rel=next`. Paginarea se face client-side, prin Algolia. 120 de produse
            # per categorie per scan, din 5.762 (all-sale) si 859 (sneakers).
            "max_pages": 1,
            # EUR, desi magazinul AFISEAZA RON. `final_price_3` (website_id 3, citit
            # din `config.country`) e in moneda de BAZA: pagina arata `RON 552` pentru
            # `full_price_3 = 105`, adica 105 x 5.252101, unde 5.252101 e
            # `config.country.rate` — CURSUL MAGAZINULUI. Declarand EUR, conversia
            # ramane la BNR; altfel am importa in scorare cursul comercial al
            # magazinului, care nu e cursul pietei.
            "currency": "EUR",
            "state_extractor": "endclothing_state",
            # `full_price_<id>` = pretul dinainte de reducere al aceluiasi produs,
            # fara nicio eticheta legala pe pagina.
            "reference_kind": "nemarcat",
        },
    },
    "zalando.ro": {
        "label": "Zalando",
        "category": "fashion",
        "channel": "haine",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.zalando.ro/sale/?sale=true",
            # `max_pages: 1` e o MASURATOARE, nu prudenta, si e cea mai tare din
            # lot: sablonul `/sale/{n}/?sale=true` CHIAR apare in DOM
            # (`<a href="/sale/274/?sale=true">`), dar `…/sale/2/` SI `…/sale/500/`
            # redirecteaza amandoua catre `…/sale/?sale=true` — pagina 1. Dovedit
            # pe identitatile cardurilor, nu pe numar: p1 ∩ plast = 24 din 24
            # (identice), p1 ∩ p2 = 19 din 24. Deci paginarea nu exista
            # server-side, iar raftul nici macar nu e stabil intre doua cereri.
            # Fara `page_url_template`: garda il cere abia peste plafonul 1, si
            # n-avem ce URL real sa punem.
            "max_pages": 1,
            "currency": "RON",
            # ZERO carlige stabile pe acest magazin: niciun `data-testid`, doar
            # hash-uri de build (`.Km7l2y`, `.Yb63TQ`, `.JT3_zV`). Singura ancora e
            # STRUCTURA — `<article>` cu `<header><h3>` si un `<section>` cu trei
            # `<p>`: platit, „Inițial:", „Cel mai mic preț recent:". E fragil prin
            # constructie: orice redesign il rupe. Daca da 0 carduri pe un scan
            # viitor, se RE-MASOARA, nu se ghiceste alt selector.
            "card": "article:has(header h3)",
            "link": "a",
            "title": "header h3",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src", "srcset"],
            # `<span class="…Km7l2y">127,00 lei</span>`, primul `<p>` al sectiunii.
            "price_text": "section > p:first-child > span",
            # Al TREILEA `<p>`: „Cel mai mic preț recent:" + `134,00 lei` + `-5%`.
            # Exista doar pe cardurile CU Omnibus — 3 din 24 masurate — deci
            # `compare_at` e None pe restul, si asta e corect, nu o pierdere.
            "compare_text": "section > p:nth-child(3) > span:nth-child(2)",
            "price_parse": "eu_comma",
            # Eticheta e VIZIBILA pe card, verbatim „Cel mai mic preț recent:",
            # langa un „Inițial:" NEMARCAT (nici <del>, nici clasa de taiere) pe
            # toate 24. Se citeste Omnibus-ul, nu „Inițial".
            "reference_kind": "min30",
        },
        "notes": ("ACCESS-2"
                 " DEAL-D4 - axa D: `/sale/?sale=true` (24 de carduri, 308.498 de produse anuntate), Omnibus vizibil pe card („Cel mai mic preț recent”) dar doar pe 3 din 24. Selectori STRUCTURALI: magazinul n-are niciun `data-testid`, doar hash-uri de build. `max_pages: 1` MASURAT - `/sale/2/` si `/sale/500/` redirecteaza amandoua la pagina 1 (p1 identic cu plast pe 24 din 24), iar raftul difera intre doua cereri (19 din 24 comune)."),
    },
    "43einhalb.com": {
        "label": "43einhalb",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "impersonate": "firefox135",
        "notes": "ACCESS-2; DEAL-D3 - CITIBIL dar fara card identificabil: `/sale` "
                 "are pretul platit si un pret taiat etichetat VERBATIM `UVP` pe camp "
                 "(deci PRP), plus paginare reala `/sale/page/{n}` din `rel=next`. "
                 "DAR grila randeaza acelasi produs de mai multe ori, in variante de "
                 "layout responsive: 69 de `div.item-wrapper` pentru 16 URL-uri "
                 "distincte, iar 36 din 69 n-au niciun `<a href>`. Un descriptor pe "
                 "ele scotea 6 carduri cu 3 URL-uri - masuratoare falsa care arata a "
                 "succes. In plus `page/500` a dat 403 si `classify` -> BLOCKED. Nu "
                 "intra pana la o sonda care separa duplicatele. LST-D6 - "
                 "duplicatele NU erau responsive: niciun stramos n-are clasa de "
                 "breakpoint. Cele 66 de `.pInfo` se impart in 36 in `div#prodList` "
                 "(grila) si 30 in `header#header` (previzualizari de MEGAMENIU); "
                 "scopat la `#prodList`, ies 36 de carduri cu 36 de URL-uri "
                 "distincte, ZERO duplicate. Deci INTRA, pe CSS. Duplicatele de "
                 "megameniu aveau oricum pret identic cu al grilei (0 URL-uri "
                 "divergente), deci si fara scopare dedup-ul SCAN-1 le-ar fi "
                 "absorbit - dar cu ele grila goala de la coada n-ar mai fi fost "
                 "goala, si oprirea paginarii s-ar fi pierdut.",
        # ── DEAL-D6, din dump-urile LST-D6 (p1, p2, page/48) ────────────────
        "listing": {
            "url": "https://www.43einhalb.com/sale",
            "page_url_template": "https://www.43einhalb.com/sale/page/{n}",
            # Adancimea reala e ~47 (1.663 de produse la 36/pagina, DERIVATA, nu
            # numarata - totalul drifteaza: 1.664 pe 7 septembrie, 1.663 pe 8).
            # 30 e PLAFON DE BUGET, conventia altex/mediagalaxy.
            #
            # Oprirea masurata: `/sale/page/48` -> 200 cu GRILA GOALA (`url_final`,
            # `canonical` si `<title>` spun toate „Seite 48", deci nu e clamp).
            # DOUA capcane in jurul ei:
            #   * pagina goala INCA anunta `<link rel="next" href="/sale/page/49">`,
            #     deci `rel=next` nu e semnal de final aici - grila goala e;
            #   * `page/500` da 403 (`classify` -> BLOCKED). Coada e ZID, deci
            #     plafonul nu se ridica prin bisectie pe pagini mari.
            "max_pages": 30,
            "currency": "EUR",
            # SCOPAT la grila. Fara `#prodList`, selectorul mai prinde 30 de
            # carduri de megameniu (6 dintre ele cu forma completa de pret, deci
            # 6 carduri in plus la extractie) - iar pe pagina de coada, unde grila
            # e goala, ele ar face pagina sa para plina si ar rupe oprirea.
            "card": "#prodList div.item-wrapper",
            "link": "a.product-title",
            "title": "a.product-title",
            # 32 din 36 de carduri sunt LENESE: `src="/images/noimage.png"` (un
            # placeholder, respins corect de `normalizeaza_imagine`) si poza reala
            # in `data-srcset`. Cu `["src"]` singur, controlul da 4/36; cu
            # rezerva, 36/36. Acelasi tipar ca intersport la IMG-1a.
            "image_attr": ["data-srcset", "src"],
            "price_text": ".product-price--new",
            "compare_text": ".product-price--old",
            "price_parse": "eu_comma",
            # `prp`, si nu din deductie: nota de subsol a paginii eticheteaza
            # CAMPUL - „UVP = unverbindliche Preisempfehlung des Herstellers".
            # `„€ 119,95 UVP ²"` -> 119.95, fiindca `²` (U+00B2) nu e cifra.
            "reference_kind": "prp",
        },
    },

    # ── CONTENT-2 ─────────────────────────────────────────────────────────────
    "flanco.ro": {
        "label": "Flanco",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "og",
        "status": "validated",
        "impersonate": "firefox135",
        "notes": "CONTENT-2; DEAL-D2 — NEMASURAT, si NU blocat: poarta a intors `None` "
                 "pe `https://flanco.ro/`, dar cererea directa cu ACELASI profil "
                 "(firefox135) a dat 200 si 881 KB de pagina reala, iar `classify()` "
                 "rulat pe chiar acel corp intoarce `Outcome.OK`. Redirectul e catre "
                 "`https://www.flanco.ro:443/` (port explicit). Cauza e deci in lantul "
                 "de hopuri al portii, nu in sit — de investigat separat, fiindca "
                 "atinge si axa L. GATE-1/GATE-2 — masurat hop cu hop: situl "
                 "raspunde 308 cu `Location: https://www.flanco.ro:443` (cale GOALA "
                 "si port implicit scris explicit), iar exact acea forma primeste 403 "
                 "`cf-mitigated: challenge`. Poarta normalizeaza acum URL-ul de hop "
                 "(RFC 3986), deci intrarea trece prin `https://www.flanco.ro/` si "
                 "raspunde 200. `classify` n-a gresit niciodata: cele doua sonde "
                 "comparau doua CORPURI diferite. "
                 "DEAL-D5 — FARA_LISTARE pe axa D, cu poarta GATE-2 "
                 "functionand: home prin `www.` a dat 200 si 1074 de ancore, "
                 "dar cele patru cuvinte au produs O SINGURA candidata, "
                 "`/regulamente-promotii`, editoriala (regula hornbach: se "
                 "penalizeaza, nu se ascunde — fiind singura, a fost ceruta). "
                 "Rezerva `/multi-deals-extra-discount` a dat 200 cu 548 KB si "
                 "ZERO jetoane de pret (client-side). Semnificativ pentru un "
                 "magazin de electronice: ZERO aparitii de „resigilat” pe "
                 "home, desi resigilatele sunt tocmai axa D aici."
                 "BRW-0d — in BROWSER interstitiul Turnstile INGHEATA la 2,6–2,9 s "
                 "cu `cf-turnstile-response` GOL, iar 41 din 41 de poll-uri pana "
                 "la 60 s au intors corpuri identice la octet. Fraza „Verificarea "
                 "a reusit” exista in pagina, dar sub `display: none` — de aceea "
                 "rundele dinainte au crezut ca provocarea trecuse. "
                 "DEAL-D11 — verdictul „NEMASURAT, si NU blocat” se INCHIDE, dar "
                 "pe alt motiv decat accesul: flanco iese definitiv de pe axa D "
                 "fiindca n-are PRETURI server-side. Masurat pe trei forme: "
                 "home-ul are 61 de cutii `price-box` si `data-product` dar UN "
                 "SINGUR jeton de pret; `/multi-deals-extra-discount` n-are grila "
                 "deloc (617 ancore, ZERO de produs, zero `price-box`) — e o "
                 "pagina de campanie, nu o grila client-side; iar o CATEGORIE "
                 "reala (`/telefoane-tablete.html`, 200 cu 560.579 de octeti) n-are "
                 "nici macar containerul: zero jetoane de pret, zero `price-box`, "
                 "zero ld+json, zero `itemprop`. Ramura de browser (BRW-1) nu e o "
                 "iesire: acolo e chiar Turnstile-ul de mai sus. Deci prostul "
                 "candidat nu era accesul, era randarea.",
    },
    "evomag.ro": {
        "label": "evoMAG",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        # ── DEAL-D2, din dump-urile LST-D2 (7 septembrie) ──────────────────
        # Domeniul care a CERUT treapta `eu_sup`: vezi `price_text` mai jos.
        "listing": {
            "url": "https://www.evomag.ro/resigilate-produse-resigilate/",
            # `<a rel="next" href="/resigilate-produse-resigilate/filtru/pagina:2">2</a>`
            # Separatorul e DOUA PUNCTE, nu cratima. Confirmat live la DEAL-D2.
            "page_url_template": ("https://www.evomag.ro/"
                                  "resigilate-produse-resigilate/filtru/pagina:{n}"),
            # Corpul paginii 1 poarta numere de pagina pana la 11; 14 e aia plus
            # marja.
            "max_pages": 14,
            "currency": "RON",
            "card": ".nice_product_container",
            # Ancora din titlu, nu cea din poza: aceeasi tinta, dar `h2.m-0 a`
            # da si titlul, deci cele doua chei citesc acelasi nod.
            "link": "h2.m-0 a",
            # Titlul poarta DEJA starea, ca prefix, pe 64/64:
            # `<span style="color:green">Resigilat!</span> Aspirator robot …`.
            # De aceea NU se pune niciun prefix — ar produce
            # „Resigilat: Resigilat! …" (lectia eMAG).
            "title": "h2.m-0",
            "image_attr": ["src"],
            # `<span class="real_price">529<sup class="price_sup">99</sup> lei</span>`
            # `_text_of` (get_text(" ")) da „529 99 lei". AMBELE parsere de
            # dinainte de DEAL-D2 intorc 52999.0 — de 100 de ori prea mult, pe
            # 64/64 de carduri, masurat de controlul LST-D2 §4. De aici treapta
            # `eu_sup`. Contrast cu powerup.ro, unde <sup>-ul CONTINE virgula si
            # `eu_comma` merge nemodificat.
            "price_text": "span.real_price",
            # `<span style="color:#7e7e7e">NOU: <span style="color:#494949">1.474
            #  <sup class="price_sup">99</sup> lei</span>` — 64/64.
            "compare_text": ".price_block_list span[style]",
            "price_parse": "eu_sup",
            # `nemarcat`: eticheta e „NOU:", intarita de propriul tooltip
            # `data-tippy-content="Acesta este pretul produsului nou."` — pretul
            # unitatii NOI a aceluiasi SKU la acelasi magazin, ca la eMAG si
            # altex. Nu e nici min30, nici PRP.
            "reference_kind": "nemarcat",
            # FARA `stock_attr`: stocul e text („In stoc magazin", in
            # `span.stock_instocmagazin`), fara atribut de comparat.
        },
        "notes": "CONTENT-2; DEAL-D2 — axa D pe `/resigilate-produse-resigilate/`, 64 "
                 "de carduri pe pagina, paginare `filtru/pagina:{n}` (separatorul e "
                 "DOUA PUNCTE). Domeniul care a CERUT treapta `eu_sup`: zecimalele stau "
                 "intr-un `<sup class=price_sup>` FARA separator, iar cele doua parsere "
                 "de dinainte citeau „529 99 lei” ca 52999.0 — de 100 de ori prea mult, "
                 "pe 64/64. Referinta `NOU:` (cu tooltip propriu „Acesta este pretul "
                 "produsului nou.”) e unitatea noua a aceluiasi SKU, nu Omnibus. Titlul "
                 "poarta deja `Resigilat!` ca prefix, deci nu se adauga niciunul.",
    },

    # ── DISCOVERY-2 ───────────────────────────────────────────────────────────
    "footshop.ro": {
        "label": "Footshop",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        # ── DEAL-D3, din dump-urile LST-D3 (7 septembrie) ──────────────────
        "listing": {
            # Listarea GLOBALA; celelalte ancore de `reduceri` din dump sunt fatete
            # per categorie (`/ro/4-pantofi/reduceri-toate_vanzarile`).
            "url": "https://www.footshop.ro/ro/872-reduceri",
            "page_url_template": "https://www.footshop.ro/ro/872-reduceri/page-{n}",
            # p1 si p2 n-au niciun handle comun, DAR `page-500` intoarce 24 de
            # produse REALE, tot fara intersectie cu p1: oprirea NU s-a atins, deci
            # plafonul e pur BUGET, nu granita masurata. (Contrast cu
            # sneakersnstuff, unde `?page=500` da grila goala.)
            "max_pages": 40,
            "currency": "RON",
            "card": ".Product_wrapper_2egST",
            "link": "a[href]",
            "title": ".Product_name_1Go7D",
            "image_attr": ["src"],
            # `strong`, si NU div-ul de pret — asta e masuratoarea care conteaza:
            #   <div class="ProductPrice_price_J4pAM ProductPrice_sale_2nd5i">
            #     <strong>477 RON</strong>
            #     <span class="ProductPrice_oldPrice_1NHjx">529 RON</span>
            #   </div>
            # Referinta e IMBRICATA in nodul de pret, deci textul div-ului le contine
            # pe amandoua („477 RON 529 RON") si `_pret_eu_comma` ar da 477529.0.
            # `strong` e pe 24/24 si poarta exact pretul platit.
            "price_text": "strong",
            "compare_text": "span.ProductPrice_oldPrice_1NHjx",
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
            #
            # FRAGILITATE: `_2egST`, `_1Go7D`, `_1NHjx` sunt hash-uri de build si se
            # schimba la fiecare deploy. Pentru pretul platit exista alternativa
            # (`strong`) si se foloseste; pentru card, titlu si referinta NU exista
            # alta in dump. Daca un scan da 0 carduri, se re-masoara.
        },
        "notes": "DISCOVERY-2; DEAL-D3 - axa D pe listarea GLOBALA "
                 "`/ro/872-reduceri`, 24 de carduri pe pagina. Pretul platit se ia de "
                 "pe `strong`, NU de pe div-ul de pret: referinta e IMBRICATA in el, "
                 "deci textul div-ului contine ambele sume (477 RON 529 RON -> "
                 "477529.0). Clasele sunt hash-uri de build (`_2egST`, `_1Go7D`, "
                 "`_1NHjx`) si se schimba la deploy. `page-500` intoarce 24 de produse "
                 "REALE, deci oprirea NU s-a atins si `max_pages` e pur buget - "
                 "contrast cu sneakersnstuff, unde `?page=500` da grila goala.",
    },
    "asos.com": {
        "label": "ASOS",
        "category": "fashion",
        "channel": "haine",
        "country": "GB",
        "delivery": "ro_confirmed",
        "method": "custom",
        "status": "validated",
        "notes": ("DISCOVERY-2"
                 " DEAL-D4 - RAMAS IN AFARA axei D, desi grila e curata: `li.productTile_U0clN`, 72 de placi, paginare `?page={n}` reala (p1 si p2 disjuncte). Listarea serveste insa GBP pe 72 din 72, iar locala validata pe axa L e `store=ROE&currency=EUR&country=RO` prin API-ul public `stockprice`. Lipseste doar comutatorul de magazin; pana atunci ar fi alt magazin."
                 " LST-D8/DEAL-D8 - comutatorul GASIT, si NU e in query: `?store=ROE&currency=EUR&country=RO` intoarce 200 si pagina intreaga, dar in GBP pe 72/72 (ignorat TACIT). Comuta antetul `Cookie`, iar `browseCountry=RO` e si necesar, si SUFICIENT singur: cu el, starea da ROE/EUR/RO si 72/72 in EUR; cu tripleta din DISCOVERY-2 dar FARA el, inapoi pe GBP. De aici `extra_headers` si intrarea pe axa D."),
        # DEAL-D8 — antetele de PREFERINTA ale domeniului, aplicate de poarta HTTP
        # pe fiecare hop care apartine lui asos.com (vezi `_antete_pentru`).
        # Un singur cookie, fiindca al doilea n-ar schimba nimic: PASUL 3 al rundei
        # a masurat ca `browseCountry=RO` SINGUR da 72/72 in EUR si starea pe
        # ROE/EUR/RO. Nu e cookie de sesiune si nu vine de la un login — e o
        # preferinta de vitrina, exact ce are voie sa stea intr-un literal versionat.
        "extra_headers": {"Cookie": "browseCountry=RO"},
        # DEAL-D8 — listare pe STARE, nu pe CSS. Grila EXISTA si e curata, dar ii
        # lipsesc doua lucruri pe care doar starea le are (masurat la LST-D8 §4.1):
        # referinta e numai in `aria-label` (72/72 acolo, 0/72 in DOM, iar
        # `_pret_strict` refuza corect sirul) si imaginile lipsesc pe 68 din 72 de
        # placi. Vezi `asos_plp`.
        "listing": {
            "url": "https://www.asos.com/women/sale/cat/?cid=7046",
            "page_url_template": "https://www.asos.com/women/sale/cat/?page={n}&cid=7046",
            # 20 pe conventia otter: paginarea e reala (p1 ∩ p2 = 0, masurat), iar
            # 20 x 72 = 1 440 de produse e un plafon prudent pentru o categorie de
            # sale care se schimba zilnic.
            "max_pages": 20,
            # EUR, si asta e o AFIRMATIE VERIFICATA la fiecare pagina, nu o
            # declaratie: `asos_plp` compara `config.country.defaultCurrency` din
            # stare cu valoarea de aici si RIDICA daca difera. Fara garda, un antet
            # cazut ar publica preturi GBP etichetate EUR — pagina parseaza la fel
            # de curat in ambele cazuri.
            "currency": "EUR",
            "state_extractor": "asos_plp",
            # `price` e pretul INTREG al aceluiasi produs, fara nicio eticheta
            # legala pe pagina (nici Omnibus, nici PRP) — deci NEMARCAT, ca la
            # endclothing.
            "reference_kind": "nemarcat",
        },
    },

    # ── SHOP-1a ───────────────────────────────────────────────────────────────
    # Primul val de magazine Shopify: extractia nu mai trece prin HTML, ci prin
    # endpoint-ul Ajax /products/<handle>.js (singurul per-produs care poarta
    # `available`). Moneda vine de aici, din registru — payload-ul nu o contine.
    "asphaltgold.com": {
        "label": "Asphaltgold",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "footdistrict.com": {
        "label": "Footdistrict",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "ES",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "overkillshop.com": {
        "label": "Overkill",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a; livrare de reverificat periodic (nota lista master)",
    },
    "nakedcph.com": {
        "label": "NAKED Copenhagen",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DK",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a; ld+json rotunjeste pretul la intreg, nesigur ca sursa",
    },
    "patta.nl": {
        "label": "Patta",
        "category": "sneakers",
        "channel": "haine",
        "country": "NL",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "slamjam.com": {
        "label": "Slam Jam",
        "category": "sneakers",
        "channel": "haine",
        "country": "IT",
        "delivery": "ro_confirmed",
        "method": "shopify",
        "status": "validated",
        "currency": "EUR",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "redgoblin.ro": {
        "label": "Red Goblin",
        "category": "tcg",
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "ada-shoes.ro": {
        "label": "Ada Shoes",
        "category": "incaltaminte",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "rocashoes.ro": {
        "label": "Roca Shoes",
        "category": "incaltaminte",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "shopium.ro": {
        "label": "Shopium",
        "category": "incaltaminte",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },
    "sosukicks.ro": {
        "label": "Sosu Kicks",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
        "notes": "SHOP-1a",
    },

    # ── LOT1 — electronice RO (sonda 2026-08-13) ──────────────────────────────
    # Primul val in care extractorul EXISTENT a fost rulat pe HTML-ul capturat
    # (parse_product_html e pura), nu reimplementat in sonda. Toate 8 domeniile au
    # raspuns pe treapta IMPLICITA de impersonare — niciun `impersonate` de adaugat.
    "itgalaxy.ro": {
        "label": "IT Galaxy",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D2, din dump-urile LST-D2 (7 septembrie) ──────────────────
        "listing": {
            "url": "https://www.itgalaxy.ro/promotii/",
            # `<link rel="next" href="https://www.itgalaxy.ro/promotii/pagina2/" />`
            "page_url_template": "https://www.itgalaxy.ro/promotii/pagina{n}/",
            # Plafonul e BUGET, nu granita: paginatorul anunta verbatim
            # `title="Pagina 2 din 770"`, iar `pagina500` a fost CERUTA si a
            # raspuns 200 cu 36 de carduri ale caror URL-uri nu se intersecteaza
            # deloc cu ale paginii 1. Adancimea reala e deci ~27.700 de produse.
            # 40 e conventia otter.
            "max_pages": 40,
            "currency": "RON",
            "card": ".product-box",
            "link": "a.pbimg",
            "title": "h2.name",
            "image": "img.img-fluid",
            "image_attr": ["src"],
            # Pretul platit vine din ATRIBUT, pe 36/36:
            # `<button class="addtocart-ajax …" data-pprice="2815.99">`.
            # Zecimal cu punct, deci trece prin parserul strict si nu atinge
            # deloc logica de virgula — preferinta DEAL-D1 pentru atribute
            # numerice. Textul vizibil („2.815,99 lei") ar fi mers si el, dar
            # atributul e cu un pas mai putin de ghicit.
            "price_attr": ["[data-pprice]", "data-pprice"],
            # Referinta ramane pe TEXT — nu exista in niciun atribut.
            # `<div class="price-placeholder">
            #    <span class="old-price d-block">PRP: 525,00 lei</span></div>`
            # Prezenta pe 9/36 (p1), 18/36 (p2), 0/36 (pagina 500).
            "compare_text": ".old-price",
            "price_parse": "attr_float",
            # `compare_parse` (DEAL-D2) — itgalaxy e PRIMUL descriptor care
            # amesteca caile: pretul din atribut (parser strict, `attr_float`),
            # referinta din text („PRP: 525,00 lei", virgula zecimala). O singura
            # cheie `price_parse` nu poate descrie amandoua, deci latura de
            # referinta si-o declara pe a ei. Absenta cheii = comportamentul
            # vechi (se cade inapoi pe `price_parse`), deci cele 19 descriptoare
            # de dinainte raman neatinse.
            "compare_parse": "eu_comma",
            # `prp`, si e singurul domeniu din lot cu eticheta CHIAR PE CAMP.
            # Nuanta onesta: din cele 9 referinte de pe p1, 4 poarta prefixul
            # `PRP:` si 5 sunt sume goale (`3.188,00 lei`); pe p2, 9 din 18.
            # Acelasi camp, aceeasi clasa, eticheta inconsistenta — dar prezenta
            # verbatim, ceea ce niciun alt domeniu din lot n-a oferit.
            "reference_kind": "prp",
            # FARA `stock_attr`: disponibilitatea e TEXT („in stoc limitat" /
            # „in stoc suficient", in `aria-label`), nu un atribut cu valoare
            # comparabila. `_in_stoc` cere (selector, atribut, asteptat).
            #
            # AVERTISMENT de semantica: `/promotii/` pare sa fie practic tot
            # catalogul „in promotie" (770 de pagini), exact situatia DEAL-2b
            # unde intreg outletul e permanent „redus" fata de referinta si
            # primul scan otter a produs 15.832 de deal-uri. Pragul R1 propriu
            # caii de listare e ce tine feed-ul in frau; acoperirea referintei
            # (9-18 din 36) e oricum sub jumatate.
        },
        "notes": "LOT1; DEAL-D2 — axa D pe `/promotii/`, care e practic tot catalogul "
                 "„in promotie”: paginatorul anunta `Pagina 2 din 770`, iar `pagina500` "
                 "a fost CERUTA si a raspuns 36 de carduri fara nicio intersectie cu "
                 "pagina 1. Referinta `.old-price` e pe 9/36 (p1) si 18/36 (p2), iar "
                 "eticheta `PRP:` sta CHIAR PE CAMP (4 din 9, respectiv 9 din 18) — "
                 "singurul domeniu al lotului cu eticheta verbatim. Pragul R1 al "
                 "listarilor e ce tine feed-ul in frau (precedentul otter, DEAL-2b). "
                 "Primul descriptor care citeste pretul din atribut si referinta din "
                 "text, de unde cheia `compare_parse`.",
    },
    "carrefour.ro": {
        "label": "Carrefour",
        "category": "electronice",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D3, din dump-urile LST-D3 (7 septembrie) ──────────────────
        "listing": {
            # `/campanii/` e chiar prefixul LISTARILOR pe carrefour, nu un marcaj
            # editorial — greseala care a ars 5 din 6 cereri la LST-D2.
            "url": "https://carrefour.ro/campanii/oferte-saptamanale",
            # 384 de carduri pe o pagina si ZERO linkuri de paginare in HTML-ul
            # brut: campania saptamanala intreaga, dintr-o bucata.
            "max_pages": 1,
            "currency": "RON",
            "card": ".product_container",
            "link": "a.product_card",
            "title": ".product_title",
            # `image_attr: ["src"]` si nimic mai mult, si merita spus de ce ajunge:
            # PRIMUL `<img>` al fiecarui card e un placeholder lazy
            # `src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAA…"`,
            # pe 384/384. `normalizeaza_imagine` respinge orice `data:` (garda
            # exista din IMG-1a, nu e adaugata acum), iar `_imagine_of` trece la
            # `<img>`-ul urmator. Masurat pe toate cele 384: 368 primesc poza reala
            # `https://cdn-media.carrefour.ro/media/catalog/product/cache/…`, iar
            # 16 primesc un banner de campanie `https://carrefour.ro/media//
            # carrefour_campai…` — imprecizie cunoscuta, nu URL rupt. Nu exista
            # niciun atribut lazy de rezerva: singurul `data-*` de pe `<img>` e
            # `data-nimg` (marcaj Next.js), care nu poarta URL.
            "image_attr": ["src"],
            # `<div class="Price_priceWrapperRed__BWFkK …">8 79 LEI</div>` — intregul
            # si zecimalele sunt noduri separate, FARA separator, iar `_text_of`
            # (get_text(" ")) le lipeste cu un spatiu.
            "price_text": "div.Price_priceWrapperRed__BWFkK",
            # `<div class="Price_priceWrapperStrikeThrough__EvRr7 …">10 99 LEI</div>`,
            # prezent pe 181/384.
            "compare_text": "div.Price_priceWrapperStrikeThrough__EvRr7",
            # AL DOILEA consumator al treptei `eu_sup` (dupa evomag, DEAL-D2):
            # „8 79 LEI" -> 8.79. `eu_comma` ar da 879.0, adica de 100 de ori prea
            # mult pe 384 de carduri — un feed intreg de chilipiruri false.
            #
            # Nota de masuratoare: agregatul sondei a raportat initial 70 de
            # referinte „inversate sau egale" din 181. Numarul era un ARTEFACT —
            # comparatorul intern al analizei nu cunostea `eu_sup`. Recalculat cu
            # parserul corect: 181 de perechi, ZERO inversate.
            "price_parse": "eu_sup",
            # `nemarcat`: pretul taiat n-are nicio eticheta pe camp — zero „PRP",
            # zero „ultimele 30 de zile", zero „Omnibus" pe pagina.
            "reference_kind": "nemarcat",
            #
            # FRAGILITATE: `__BWFkK` si `__EvRr7` sunt hash-uri de build (CSS
            # Modules) si se schimba la fiecare deploy. N-au alternativa in dump.
            # Daca un scan da 0 carduri sau 0 preturi, selectorii se RE-MASOARA pe
            # un dump nou; nu se ghicesc.
            #
            # PROD-1 — prima verificare a acelei reguli, si a iesit NEGATIV, adica
            # bine. Scanul din 10.09 a dat 33 de produse fata de 384 masurate la
            # LST-D3, ceea ce arata exact ca un hash schimbat. Sonda a deosebit
            # cele doua ipoteze pe pagina, numarand selectorul EXACT si varianta
            # lui „pe portiunea stabila" (`div[class*='Price_priceWrapperRed']`):
            # 35 = 35 la pret si 20 = 20 la referinta, deci hash-urile sunt intacte.
            # `.product_container` da 33 in HTML-ul brut si descriptorul extrage
            # 33 din 33. Campania SAPTAMANALA s-a micsorat, atat: 384 (7.09) -> 33
            # (10.09), si de aia `max_pages: 1` ramane corect.
        },
        "notes": "LOT1; DEAL-D2 — NEMASURAT: sonda a ales gresit intrarea din home "
                 "(pagina de REGULAMENTE de tombola, care avea destule blocuri "
                 "link+suma cat sa treaca de pragul de carduri), deci nicio masuratoare "
                 "valida despre listare. Pistele reale, din navigatia deja salvata: "
                 "`/campanii/oferte-saptamanale` si `/campanii/reduceri-de-gama` — pe "
                 "carrefour `/campanii/` e chiar prefixul listarilor. DEAL-D3 — "
                 "axa D pe campania saptamanala `/campanii/oferte-saptamanale`: 384 "
                 "de carduri pe o singura pagina, fara paginare in HTML brut. "
                 "Zecimalele stau pe noduri SEPARATE fara separator (`8 79 LEI`), "
                 "deci `eu_sup` — al doilea consumator al treptei dupa evomag; "
                 "`eu_comma` ar da 879.0. Primul `<img>` al fiecarui card e un "
                 "placeholder `data:` (384/384), respins de normalizator, iar poza "
                 "reala vine de pe al doilea `<img>` (368 poze de produs, 16 bannere "
                 "de campanie). Referinta e pe 181/384, fara nicio eticheta legala. "
                 "PROD-1 — campania VARIAZA saptamanal: 384 de carduri (7.09) -> 33 "
                 "(10.09). Nu e un descriptor stricat: hash-urile de build sunt "
                 "intacte (selectorul exact si cel „pe portiune stabila” dau acelasi "
                 "numar, 35 si 20), iar din 33 de `.product_container` se extrag 33. "
                 "Un numar mic de carduri pe acest domeniu e o stire despre campanie, "
                 "nu despre cod.",
    },
    "flip.ro": {
        "label": "Flip",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "url_identity": "exact",
        # ── STATE-1 — axa D prin extractor de STARE, nu prin selectori CSS.
        # Grila e hidratata client-side; datele vin din cache-ul react-query al
        # lui `__NEXT_DATA__` (v. `flip_next`, unde stau cheile verbatim).
        "listing": {
            "url": "https://flip.ro/magazin/",
            # MASURAT live (STATE-1 B3): `?page=2` intoarce 32 de carduri, 30 NOI
            # fata de pagina 1, iar `queryKey`-ul din starea raspunsului devine
            # `limit=32|offset=32` — deci parametrul E onorat si se traduce in
            # offset. `?page=500` intoarce 200 cu grila GOALA (0 carduri prin
            # extractor), adica oprire curata: conditia compozita din scanner o
            # prinde fara sa aiba nevoie de un plafon exact.
            "page_url_template": "https://flip.ro/magazin/?page={n}",
            # `total` din stare: 604 la LST-D3, 577 la masuratoarea live — stocul
            # de refurbished se misca zilnic. 604/32 -> 19 pagini, deci 19 e
            # plafonul, cu oprirea REALA data de grila goala.
            "max_pages": 19,
            "currency": "RON",
            "state_extractor": "flip_next",
            # `retailPrice` = pretul unitatii NOI a aceluiasi model, aceeasi
            # semantica cu „NOU" la eMAG si „Nou:" la altex. NU e Omnibus.
            "reference_kind": "nemarcat",
        },
        "notes": "LOT1; ?shape= semantic — starea e parte din identitatea sursei; "
                 "DEAL-D2 — NEMASURAT: home-ul are ZERO ancore `<a href>` in 377 KB "
                 "(shell Next.js pur), deci intrarea nu se poate descoperi din "
                 "navigatie. Piste din `__NEXT_DATA__`: catalogul general e `/magazin/`, "
                 "iar fatetele contin `promo=GENIUS-DEAL`. DEAL-D3 — `/magazin/` e "
                 "STATE, si cel mai curat din familie: `__NEXT_DATA__` -> "
                 "`props.pageProps.dehydratedState.queries[0].state.data.data."
                 "productsPage`, array PLAT de 32 de produse cu chei directe "
                 "(`price`, `previousPrice`, `retailPrice`, `pdpUrl`, `imagePath`, "
                 "`currency: RON`). Gradul sta in `naming.title` ca SUFIX pe 32/32 "
                 "(`..., 128 GB, Excelent`; 16 Excelent / 11 Ca nou / 5 Foarte bun) si "
                 "in `pdpUrl` ca `?shape=`, ceea ce confirma `url_identity: exact`. "
                 "CAPCANA: `lowestPriceOfTheYear` e `false` pe 32/32 — constanta de "
                 "sablon, nu masuratoare (lectia vivre). Candidat `state_extractor`. "
                 "STATE-1 — INTRAT pe axa D prin `flip_next`. Paginare MASURATA "
                 "live: `?page={n}` e onorat (se traduce in `offset` in queryKey, "
                 "30 de produse noi pe pagina 2), iar `?page=500` da grila GOALA "
                 "— oprire curata, fara plafon ghicit. Catalogul e INTEGRAL "
                 "refurbished, deci `retailPrice` (referinta) e pretul unitatii "
                 "NOI a aceluiasi model, nu un pret taiat al aceluiasi articol. "
                 "Fateta `?promo=genius-deal` exista (citita din stare la DEAL-D2) "
                 "dar NU e masurata ca listare separata.",
    },
    "usedproducts.ro": {
        "label": "Used Products",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT1; bucati unice second-hand, comportamentul la vandut nemasurat; "
                 "DEAL-D2 — JS_ONLY: `/reduceri` raspunde 200 dar e o cochilie RSC "
                 "(Next.js) de 43 KB al carei text vizibil e exact titlul paginii, iar "
                 "blobul `self.__next_f` are 32 KB si ZERO chei de pret. Datele vin "
                 "dintr-o cerere client-side, deci nu se pot citi fara browser.",
    },
    "senetic.ro": {
        "label": "Senetic",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "overrides": {"vat_prices": True},
        # ── DEAL-D5 — axa D. Sonda LST-D5 §3.2 a re-masurat GRILA, nu caruselul:
        # 24 de carduri `div.product-block`, control 24/24 cu pret, titlu, imagine
        # si URL-uri unice.
        "listing": {
            "url": "https://www.senetic.ro/category/outlet-8898/",
            # FARA `page_url_template`: niciun sablon de paginare in HTML-ul brut
            # care sa pastreze calea intrarii. `rel=next` exista pe pagina, dar
            # trimite la HOME — artefact de sit, respins de garda de cale a sondei.
            "max_pages": 1,
            "currency": "RON",
            "card": "div.product-block",
            "link": "a[data-action='title']",
            "title": "h3.name",
            # Scopat la `a.obrazek`, nu `img` gol: PRIMUL `<img>` din card e
            # indicatorul de incarcare al widgetului de comparatie
            # (`ajax-loader-new.gif`). Azi el cade oricum, fiindca
            # `normalizeaza_imagine` respinge `.gif` — dar asta e noroc, nu regula,
            # si s-ar sparge tacut la primul spinner in `.png`. Regula casei e
            # dezambiguizarea prin SELECTOR (v. docstringul lui
            # `normalizeaza_imagine`, cazul otter/tezyo cu insignele).
            "image": "a.obrazek img",
            "image_attr": ["src"],
            # BRUTUL, adica pretul PLATIT de client: „1 115,00 RON cu TVA".
            # `div.price-net` de pe acelasi card arata „921,49 RON fara TVA" —
            # citirea lui ar raporta preturi cu ~19% mai mici si ar face magazinul
            # sa para plin de chilipiruri. Capcana B2B, masurata pe 24/24.
            # Separatorul de mii e SPATIU („1 115,00"); `eu_comma` il inghite.
            "price_text": "div.price-gross",
            "price_parse": "eu_comma",
            # FARA `compare_*`: zero preturi taiate pe 24/24, deci nu exista
            # referinta din care sa iasa un deal -> axa D ramane doar pe R2.
            "reference_kind": "nemarcat",
        },
        "notes": "LOT1; ld+json = pret net (fara TVA), microdata = brut; "
                 "raport 1.21 masurat 3/3; DEAL-D2 — NEPOTRIVIT pe axa D: pagina de "
                 "outlet randeaza server-side DOAR un carusel `glide` de 25 de produse "
                 "(25/25 au un stramos `glide__slide`), nicio grila, si ZERO referinta "
                 "pe 25/25. Cardul arata AMBELE preturi, etichetate explicit: "
                 "`div.price_our_net` „5 613,99 RON fara TVA” si `div.price_our_gross` "
                 "„6 792,93 RON cu TVA” — raportul 1,21 confirmat si pe listare. "
                 "CORECTIE DEAL-D3: verdictul NEPOTRIVIT de mai sus s-a dat pe "
                 "CARUSEL. Exista si o grila SSR in afara lui — `div.product-block`, "
                 "24 de produse, sub `div.category-filters-products__container` — pe "
                 "care sonda LST-D2 a ratat-o fiindca ordona dupa numar si caruselul "
                 "avea un exemplar in plus (25). Referinta tot lipseste, deci axa D "
                 "ramane doar pe R2; verdictul se RE-MASOARA, nu se rescrie de aici. "
                 "DEAL-D5 — RE-MASURAT: verdictul NEPOTRIVIT de la DEAL-D2 e "
                 "INLOCUIT, fiindca fusese dat pe carusel. Grila SSR e reala si "
                 "descriptorul e mai jos. Numele claselor difera intre cele doua "
                 "zone si asta explica divergenta din notele vechi: caruselul "
                 "foloseste `price_our_net`/`price_our_gross`, cardurile din grila "
                 "`price-net`/`price-gross` — in cele 24 de `div.product-block` "
                 "exista 24 din fiecare si ZERO `price_our_*`. Referinta lipseste si "
                 "pe grila (0/24 taiate). Sonda a gasit si 6 SUB-categorii de outlet "
                 "cu numere anuntate — `outlet-computer-equipment-9315` (39), "
                 "`outlet-accesorii-9317` (34), `outlet-reelistic-9313` (24), "
                 "`outlet-electrocasnice-24919` (10), "
                 "`outlet-servers-and-storage-9314` (3), `outlet-power-solutions-9318` "
                 "(2) — materia pentru o forma `entries` daca paginarea ramane "
                 "negasibila; NEMASURATE, niciuna n-a fost ceruta.",
    },
    "pcgarage.ro": {
        "label": "PC Garage",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        "search": {"kind": "custom"},
        "notes": "LOT1; deblocat de scoparea nested; refresh migrat de pe calea "
                 "dedicata pe cea generica; DEAL-D2 — in afara axei D: prima cerere "
                 "de listare cu profilul implicit a primit challenge Cloudflare (403, "
                 "`cf-mitigated: challenge`, titlu „Just a moment...”). Daca se "
                 "deblocheaza, e candidat pentru forma `entries`: PDP-ul listeaza TREI "
                 "sectiuni de desigilate si CINCI de extra-reduceri, fara niciun URL "
                 "agregat."
                 "BRW-0d masurase in BROWSER: interstitiul Turnstile INGHEATA la "
                 "2,6–2,9 s cu `cf-turnstile-response` GOL, iar 41 din 41 de "
                 "poll-uri pana la 60 s au intors corpuri identice la octet. "
                 "Fraza „Verificarea a reusit” exista in pagina, dar sub "
                 "`display: none`. Concluzia de atunci — „zidul e TERMINAL” — e "
                 "INFIRMATA de DEAL-D11, si merita spus exact de ce: BRW-0d "
                 "masurase RABDAREA, nu amprenta, iar propria lui fraza spunea "
                 "„ar cere alta cale de acces, nu alt timeout”. O alta amprenta "
                 "TLS chiar ESTE alta cale de acces. Pe HTTP cu `firefox135` "
                 "listarea raspunde 200 din PRIMA incercare (LST-D10 §3.1), deci "
                 "terminal era timeout-ul din browser, nu domeniul.",
        # ── DEAL-D11 — amprenta care deschide domeniul (sonda LST-D10 §3.1) ───
        # `chrome` (implicitul, comun sondelor si productiei) primeste challenge;
        # `firefox135` a dat 200 cu 268.387 de octeti si 582 de ancore pe PRIMA
        # treapta a baleiajului. Al doilea caz dupa vexio, tot pe acest profil.
        "impersonate": "firefox135",
        "listing": {
            # Cele DOUA intrari sunt exact sectiunile masurate, nu deduse: nota
            # DEAL-D2 de mai sus spunea ca magazinul are TREI sectiuni de
            # desigilate si CINCI de extra-reduceri „fara niciun URL agregat”.
            # Aici intra doar cele doua care au fost CERUTE si numarate (35 si
            # 19 carduri). Celelalte intra la runda care le cere.
            "entries": [
                {"url": "https://www.pcgarage.ro/promotie-componente-desigilate/"},
                {"url": "https://www.pcgarage.ro/promotie-reduceri-laptop-desigilate/"},
            ],
            # PAGINA UNICA, si nu din lipsa de curiozitate: `/p2/` (forma
            # incercata) a dat 404, iar pagina nu-si declara paginarea in NICIUN
            # fel — zero `rel="next"`, zero ancore de pagina, zero `?pag=`. Un
            # sablon scris aici ar fi un URL inventat (regula bstn, BRW-0d).
            "max_pages": 1,
            "currency": "RON",
            "card": "div.product_box",
            # Ancora de imagine e singura care poarta si URL-ul, si numele curat.
            # `title_from` e OBLIGATORIU: ancora n-are text (doar `<img>`), deci
            # fara ea titlul iese gol pe 35/35 — masurat, nu presupus.
            "link": "a.bf_pimage_link",
            "title": "a.bf_pimage_link",
            "title_from": "link_title",
            # Zecimalele stau in `<sup>`, dar VIRGULA e inauntrul lui:
            # `2.399<sup>,99 RON</sup>` -> `_text_of` da „2.399 ,99 RON”.
            # Masurat prin parserele reale: `eu_comma` da 2399.99, iar `eu_sup`
            # da ACELASI lucru fiindca delegheaza cand vede o virgula. Deci forma
            # NU e cea evomag (unde separatorul e chiar spatiul), si `eu_comma` e
            # alegerea corecta — nu doar una care merge.
            "price_text": "p.bfp_new",
            "compare_text": "p.bfp_old",
            "price_parse": "eu_comma",
            # `nemarcat`, si asta e o masuratoare, nu o prudenta: `bfp_old` nu e
            # etichetata NICICUM in pagina — zero „Pret vechi”, zero „NOU” langa
            # pret, zero „economisesti”. Reducerea mediana e 18,8% (2,1–40,0),
            # deci linia e reala, dar CE anume reprezinta pagina nu spune.
            #
            # DATE IN PLUS, cu limita lor: la PASUL 3 al rundei, PDP-ul produsului
            # `procesoare/amd/ryzen-5-5600-35ghz-box` a intors LIVE 674,99 RON,
            # exact cat are `bfp_old` pe cardul aceluiasi produs (unde `bfp_new` e
            # 627,49). Coincidenta e sugestiva, dar e UN SINGUR card verificat
            # incrucisat — nu ajunge ca sa numim referinta, si `reference_kind`
            # ramane `nemarcat`. O runda care vrea s-o numeasca are de masurat
            # PDP-ul pentru un esantion, nu pentru unul.
            "reference_kind": "nemarcat",
            # Starea sta in `div.bf_descr` („Ambalaj original deschis, produsul
            # prezinta usoare urme de utilizare”), NU in titlu: titlul e numele
            # curat al produsului, fara prefix de stare, ca la altex.
            #
            # 35 de carduri dau 29 de `external_id`, si asta e CORECT: magazinul
            # listeaza UNITATI FIZICE separate — sase ventilatoare identice la
            # 24,45 RON, diferite doar prin fragmentul `#u38379989`, `#u38380009`…
            # `_external_id` ignora fragmentul si le colapseaza, fiindca sase
            # unitati la acelasi pret sunt aceeasi oferta. Randamentul real e 29.
        },
    },
    "orange.ro": {
        "label": "Orange",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "validated",
        "notes": "G4: CSR — jsonld apare in DOM-ul randat; headless",
    },
    "powerup.ro": {
        "label": "PowerUp",
        "category": "electronice",
        "channel": "electronice",
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
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src"],
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
        "channel": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2; aterizare pe storefront /de, EUR. "
                 "LST-D5 — POARTA, adica un defect la NOI, nu un blocaj al "
                 "magazinului: `_fetch_shop_url_guarded` a intors None pe "
                 "`/de`, iar cererea directa pe ACELASI hop "
                 "(`allow_redirects=False`, lectia GATE-1) a dat 200 cu 1,1 MB si "
                 "titlu real, iar `classify()` pe corp da OK. Corpul n-are "
                 "niciunul dintre cei doi markeri WAF, domeniul n-are "
                 "`block_markers`, n-a existat redirect, iar profilul "
                 "`impersonate` a fost identic pe amandoua. Cauza NU e stabilita: "
                 "cere o sonda hop-cu-hop pe poarta (GATE-3). "
                 "GATE-3 — NU REPRODUCE: exact acelasi `/de`, prin ACEEASI poarta, a "
                 "dat 200 din primul hop (1.101.369 de octeti, 1,23 s), iar apexul "
                 "urca in trei hopuri `computeruniverse.net/` -> 301 -> `www.` -> 307 "
                 "-> `/en` -> 200. Deci storefront-ul de aterizare e `/en`, nu `/de`. "
                 "Esecul de la LST-D5 ramane NEEXPLICAT si neremis; RATE si "
                 "Esecul de la LST-D5 ramane NEEXPLICAT si neremis; RATE si interstitiul au fost excluse cu cifre. "
                 "LST-D7 - poarta E deschisa (200 pe `/de/o/outlet`; pe "
                 "`/de/page/deals` un `None` tranzitoriu, apoi 200 direct), dar "
                 "domeniul NU intra pe axa D: JS_ONLY, dovedit pe TREI pagini — "
                 "hub-ul `/de/o/outlet` (792.576 octeti, 0 carduri, 18 jetoane de "
                 "pret), pagina CMS `/de/page/deals` (662.901, 0 carduri) si o "
                 "SUBCATEGORIE reala, `/de/o/outlet/hardware-komponenten-outlet` "
                 "(893.191 octeti, 0 carduri, 6 jetoane de pret). Singurul lucru cu "
                 "preturi din `__NEXT_DATA__` e un slider de recomandari Dynamic "
                 "Yield (`template: DYReco`), nu grila. A treia pagina e cea care "
                 "inchide discutia: nu e „am nimerit paginile gresite”. Reintrarea "
                 "cere captura API-ului de listare, pe HTTP. "
                 "LST-D9/DEAL-D10b — verdictul de mai sus era masurat pe HUB si e "
                 "corect PENTRU HUB: `/de/o/outlet` chiar n-are raft, iar sliderul "
                 "cu preturi din `__NEXT_DATA__` chiar e Dynamic Yield. Ce lipsea "
                 "era un nivel mai jos: FRUNZELE lui (cele zece din "
                 "`catalog.SubCategories`) poarta `algoliaServerState` cu raspunsul "
                 "intreg — `hardware-komponenten-outlet` are nbHits 2.211 pe 50 de "
                 "pagini, cu 20 de hituri server-side. Deci NU cere captura de API: "
                 "raspunsul e deja in pagina. A sasea capcana de carusel a "
                 "proiectului (dupa senetic, noriel, powerup, LOT5, conrad), si a "
                 "doua oara cand un verdict „client-side\" era de fapt „am masurat "
                 "hub-ul\".",
        # ── DEAL-D10b — din sonda LST-D9 §4.1 ─────────────────────────────────
        "listing": {
            # Cele ZECE frunze, verbatim din `catalog.SubCategories` al hub-ului
            # `/de/o/outlet` (dump-ul LST-D7). Hub-ul insusi NU e intrare: n-are
            # `algoliaServerState`, deci ar da grila goala la fiecare scan.
            "entries": [
                # Games & Spielzeug Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/games-filme-spielzeug-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/games-filme-spielzeug-outlet?page={n}"},
                # TV / HiFi / Video Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/tv-hifi-video-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/tv-hifi-video-outlet?page={n}"},
                # Foto / Video Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/foto-video-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/foto-video-outlet?page={n}"},
                # Haushalt Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/haushalt-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/haushalt-outlet?page={n}"},
                # Notebooks, Tablets & PCs Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/notebooks-tablets-pcs-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/notebooks-tablets-pcs-outlet?page={n}"},
                # Baumarkt & Garten Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/baumarkt-garten-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/baumarkt-garten-outlet?page={n}"},
                # Hardware & Komponenten Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/hardware-komponenten-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/hardware-komponenten-outlet?page={n}"},
                # Software Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/software-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/software-outlet?page={n}"},
                # Handy & Smart Devices Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/smartphones-funk-gps-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/smartphones-funk-gps-outlet?page={n}"},
                # Computer- & Buerobedarf Outlet
                {"url": "https://www.computeruniverse.net/de/o/outlet/computer-burobedarf-outlet",
                 "page_url_template": "https://www.computeruniverse.net/de/o/outlet/computer-burobedarf-outlet?page={n}"},
            ],
            # 20 de hituri pe pagina; `hardware-komponenten` singura are 50 de
            # pagini. Plafonul de 3 e de COST: 10 frunze x 3 pagini x 20 = 600 de
            # produse pe scan. Paginarea e prin query si e MASURATA (`?page=2` ->
            # `results[0].page == 1`), nu presupusa.
            "max_pages": 3,
            "currency": "EUR",
            "state_extractor": "cu_algolia",
            # FARA REFERINTA: hitul n-are niciun camp de pret anterior. Domeniul
            # califica deci doar pe R2 (minim istoric), ca notebooksbilliger.
            "reference_kind": "nemarcat",
        },
    },
    "jb-spielwaren.de": {
        "label": "JB Spielwaren",
        "category": "jucarii",
        "channel": "jucarii",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": ("LOT2; plentyShop; LEGO retired + SALE; DEAL-D3 — nota aia despre "
                 "SALE descrie o sectiune EDITORIALA: `/spezielle-lego-angebote-und-"
                 "gwp/` are titlul `Spezielle LEGO Angebote und GWPs` si "
                 "`<h1>Alle Unsere Aktuellen LEGO ® Aktionen, Angebote & GWPs</h1>`, "
                 "dar 2 jetoane de pret pe 236 KB, zero carduri si zero produse in "
                 "blobul de stare. Re-sonda cu alta intrare."
                 " DEAL-D4 - FARA_LISTARE confirmat a doua oara, cu cuvinte EXTINSE (`restposten|auslaufartikel|%|sale|angebote`) pe un home proaspat de 428 de ancore: o singura candidata, chiar cea editoriala de mai sus. plentyShop marcheaza produsele cu `storeSpecial: Sonderangebot` in DATE, dar magazinul nu expune o categorie de oferte in navigatia server-side. LST-D9/DEAL-D10b - verdictul de mai sus e despre NAVIGATIE si ramane adevarat: magazinul chiar n-are o categorie de oferte in nav. Intrarea a venit de la David, nu din pagina (`/en/all-lego-sets/` NU apare in home). Si acolo nu e nevoie de o categorie de reduceri, fiindca REFERINTA e pe PRODUS: fiecare card poarta `prices.rrp` (UVP), iar 170/200 pe pagina 1 si 186/200 pe pagina 2 il au STRICT peste pretul platit. Catalogul integral e deci si listarea de reduceri. `storeSpecial: Sonderangebot` din nota de mai sus e in aceleasi date, dar nu se citeste: `rrp` e o cifra, nu o eticheta de campanie."),
        # ── DEAL-D10b — din sonda LST-D9 §3.2 ─────────────────────────────────
        "listing": {
            # URL dat de David, nu citit din nav. Vitrina engleza si cea germana
            # (`/alle-lego-sets/`) dau ACELASI catalog, masurat: 200 de produse
            # fiecare, cu aceleasi 170 de referinte.
            "url": "https://www.jb-spielwaren.de/en/all-lego-sets/",
            "page_url_template": "https://www.jb-spielwaren.de/en/all-lego-sets/?page={n}",
            # 200 de produse pe pagina, dar pagina cantareste 4,5 MB — plafonul e
            # de BANDA, nu de adancime: 5 x 200 = 1.000 de produse pentru ~22 MB.
            # Oprirea reala o da grila goala: `?page=500` intoarce 0 `category-item`
            # (masurat), adica exact conditia de final a scannerului.
            "max_pages": 5,
            "currency": "EUR",
            "state_extractor": "jb_plenty",
            # `rrp` E pretul recomandat de producator (UVP), deci PRP — spre
            # deosebire de celelalte doua domenii ale rundei, care n-au eticheta.
            "reference_kind": "prp",
        },
    },
    "caseking.de": {
        "label": "Caseking",
        "category": "electronice",
        "channel": "electronice",
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
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src"],
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
        "channel": "haine",
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
            # PROD-1: 200 -> 60, plafon de TIMP, nu de adancime. Masurat in scanul
            # de productie din 10 septembrie: 12 173 de produse in 14 minute, adica
            # ~169 de pagini a 72 la ~5,0 s bucata (`_pauza()` 2,5-4 s + fetch).
            # Domeniul asta si otter au fost cele doua varfuri ale unui scan de 51
            # de minute pe 28 de domenii — 28 de minute din 51, in doua magazine.
            # 60 x 72 = 4 320 de produse in ~5 min.
            # Ce se pierde e coada outlet-ului, si e acceptabil tocmai fiindca
            # outlet-ul e PERMANENT: produsele lui nu expira intr-o zi, iar ce nu
            # intra azi in primele 60 de pagini intra la o rotatie viitoare a
            # listei. Un plafon nu schimba niciuna dintre cele trei conditii de
            # oprire — clamp-ul pe ultima pagina, masurat la LST-1b, ramane.
            "max_pages": 60,
            "currency": "EUR",
            "card": "li.product-item",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src"],
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
        # SEARCH-1 — masurat la SEARCH-0: 72 de carduri la `salomon`, si TOATE 72
        # cu pret (acoperire completa), iar termenul inexistent da 0 noduri-card pe
        # 200. Selectorii de pret sunt aceiasi cu cei din `listing`, dar se declara
        # explicit: `search_descriptor` nu mosteneste pretul (D6), tocmai ca sa nu
        # devina o coincidenta tacuta daca unul din ei se schimba.
        "search": {
            "kind": "descriptor",
            "url_template": "https://www.bergfreunde.eu/index.php?lang=10&cl=search&searchparam={q}",
            "price_text": "[data-codecept='currentPrice']",
            "compare_text": "[data-codecept='strokePrice']",
            "price_parse": "eu_comma",
        },
    },
    "alternate.de": {
        "label": "Alternate",
        "category": "electronice",
        "channel": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b. LST-D5 — FARA_LISTARE pe axa D la ambele intrari din nav: "
                 "`/Angebote` e hub EDITORIAL (0 jetoane de pret, h1 "
                 "„Promotion-Aktionen”), iar `/Outlet` arata doar un CARUSEL de "
                 "15 produse (`div.product-carousel-card`), nu o grila. Nicio "
                 "paginare in HTML-ul brut. Grila outlet reala, daca exista, sta "
                 "sub linkurile de categorie din `/Outlet` — NEMASURATA. "
                 "LST-D7 - MASURATA si INTRA: `/Outlet/<categorie>` chiar are grila "
                 "server-side, 24 de carduri pe pagina, cu pret, referinta, titlu si "
                 "imagine. Motivul pentru care sonda o ratase e un punct orb al ei, "
                 "nu al magazinului: cardul ESTE ancora, iar `identifica_carduri` "
                 "cerea un `<a>` DESCENDENT (v. LST-D7 §6).",
        # ── DEAL-D7, din dump-urile LST-D7 (p1/p2/plast pe Hardware, p1 pe Notebook)
        "listing": {
            "entries": [
                # Hardware: singura careia i s-a masurat paginarea (p1 si p2 dau
                # 24 de carduri fiecare, `p1 ∩ p2 = 0`).
                {"url": "https://www.alternate.de/Outlet/Hardware",
                 "page_url_template":
                     "https://www.alternate.de/Outlet/Hardware?page={n}",
                 "max_pages": 5},
                # Notebook: masurata DOAR pe pagina 1 (acelasi selector, 24 de
                # carduri). Fara adancime masurata nu primeste nici template, nici
                # plafon > 1 — regula nichiduta: se pagineaza doar fatetele carora
                # li s-a MASURAT adancimea.
                {"url": "https://www.alternate.de/Outlet/Notebook", "max_pages": 1},
                # Celelalte 15 subcategorii `/Outlet/*` exista in nav si NU intra:
                # n-au fost cerute, iar un URL nemasurat e o presupunere, nu un
                # descriptor.
            ],
            # Plafon de buget, nu adancime: `?page=500` intoarce 200 cu EXACT
            # aceleasi 24 de URL-uri ca pagina 1 (`p1 ∩ plast = 24`), adica CLAMP,
            # a doua oara dupa action.com. Bucla se inchide pe conditia compozita
            # din scanner (pagina e submultime a celor deja vazute), nu pe plafon.
            "max_pages": 5,
            "currency": "EUR",
            # Cardul e ANCORA (`<a class="card ... productBox ...">`), deci se
            # descrie copilul lui unic si linkul se ia urcand: `@parent_a`, forma
            # noriel de la LST-1, al doilea consumator al ei.
            "card": "div.grid-container.listing a.productBox div.container",
            "link": "@parent_a",
            "title": "div.product-name",
            "price_text": "span.price",
            # `nemarcat`, si nu din deductie: langa pretul taiat magazinul pune un
            # popover cu textul „Preis der Neuware" — pretul unitatii NOI, aceeasi
            # semantica cu „Nou:" la altex si „NOU" la eMAG. Nu e Omnibus, nu e PRP.
            "compare_text": "span.line-through",
            "price_parse": "eu_comma", "reference_kind": "nemarcat",
        },
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
        "channel": "electronice",
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
                 "era identificat dar NEMASURAT (plafonul sondei se dusese pe "
                 "escaladari de amprenta). DEAL-D11 l-a MASURAT, si verdictul e "
                 "NEGATIV: axa D se INCHIDE pe HTTP. Doua cereri pe `chrome` "
                 "(profilul care merge deja) au dat 200 cu 1,66 si 1,69 MB, dar "
                 "catalogul e CLIENT-SIDE — in 1,66 MB exista DOUA valori `\"price\"` "
                 "si 13 aparitii de €, pentru o pagina cu 279 de aparitii ale "
                 "cuvantului „B-Ware”. In plus `?page=2` e IGNORAT: multimea "
                 "ancorelor lui p1 si p2 e IDENTICA, deci nici forma de paginare nu e "
                 "cea presupusa. PDP-ul ramane neatins si valid. "
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
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── STATE-2 — axa D, masurata pe dump-ul HTTP (nu pe randarea de browser)
        #
        # Distinctia conteaza: JSON-0 masurase pagina in browser, dar scannerul
        # citeste HTTP. Cererile 4 si 5 ale rundei au aratat ca HTTP-ul da ACELEASI
        # 24 de carduri (876 KB), deci nu era nevoie de browser.
        "listing": {
            "url": "https://www.sportvision.ro/produse/noua-colectie",
            # `a[rel='next']` din pagina, VERBATIM:
            #   <a rel="next" class="btn btn-default next-load-btn"
            #      href="https://www.sportvision.ro/produse/noua-colectie/page-2">
            #      Arata mai multe</a>
            # Nota de registru de dinainte spunea „incarcare client-side,
            # nemasurata" — adevarat despre CLICK (JSON-0: clickul avanseaza
            # contorul si nu aduce nimic), dar URL-ul exista si e servit
            # server-side. Cererea 5 l-a cerut: 200, alte 24 de carduri, ZERO
            # comune cu pagina 1.
            "page_url_template": ("https://www.sportvision.ro/produse/"
                                  "noua-colectie/page-{n}"),
            # Categoria anunta 2.312 produse (~97 de pagini a 24). 30 e plafon de
            # buget, ca la altex: 720 de produse pe scan.
            "max_pages": 30,
            "currency": "RON",
            "card": "div.product-item",
            "link": "a[href]",
            # `div.title` — nu `[class*='title']`: acela prinde si
            # `span.current-price-title`, care contine textul „Pret".
            "title": "div.title",
            # Poza reala sta in `data-original-img`, RELATIVA la radacina, iar
            # `src` lipseste (lazy-load `lozad`). Acelasi tipar ca buzzsneakers —
            # tot NBSHOP — pe care `normalizeaza_imagine` il stie deja.
            "image_attr": ["data-original-img"],
            # `.current-price` da „Pret 249,99 RON"; „Pret" si „RON" n-au cifre,
            # deci `eu_comma` le sterge. Atributul `data-productprice="249,99"`
            # ar fi parut mai curat, dar calea `price_attr` merge prin parserul
            # STRICT (punct zecimal) si intoarce None pe virgula — verificat.
            "price_text": ".current-price",
            "price_parse": "eu_comma",
            # FARA referinta, si e o MASURATOARE, nu o omisiune:
            # `data-productprevprice` e EGAL cu `data-productprice` pe 24/24, iar
            # `data-productdiscount` e „0" pe 24/24 — exact capcana constantei de
            # la vivre si `previousPrice` de la flip. Citita ca referinta, ar
            # produce reduceri de 0% pe tot catalogul. Deci axa D doar pe R2.
            "reference_kind": "nemarcat",
        },
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
        "channel": "sneakers",
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
                 "vezi docs/catalog_domain_log.md. "
                 "JSON-0 — ZID pe calea de BROWSER: `/outlet` a raspuns 403 (289 de "
                 "octeti, `<title>Access Denied</title>`, `errors.edgesuite.net`), de "
                 "doua ori. NU contrazice masuratoarea G2C-1b (1,8-2,1 MB pe HTTP cu "
                 "`impersonate`): verdictul „nu e blocaj” era legat de CALEA pe care a "
                 "fost dat. De RE-MASURAT pe HTTP inainte de orice concluzie. "
                 "LST-D6 - RE-MASURAT, si axa D se INCHIDE: pe HTTP poarta e "
                 "deschisa (`/outlet` a raspuns 200 cu 1,71 MB, deci verdictul "
                 "G2C-1b ramane valid pentru calea HTTP), dar GRILA NU E SERVITA "
                 "DELOC - 4 carduri cu pret propriu (un raft de recomandari), 0 "
                 "carduri pe `/promotii-actuale`, si ZERO bloburi de stare: nici "
                 "`__NUXT__`, nici `__NEXT_DATA__`, nici `<script "
                 "type=application/json>`, nici `window.__*`. Deci JS_ONLY, nu "
                 "zgomot: nota veche („87 din 92 de carduri poarta componentele "
                 "partajate\") era corecta dar din motivul gresit. Verificarea "
                 "blobului e pasul care lipsea, si el schimba „n-am gasit produse\" "
                 "in „nu exista produse de gasit\". Reintrarea cere captura "
                 "API-ului din spatele grilei - pe HTTP, unde poarta e deschisa, "
                 "nu in browser, unde e 403 Akamai."
                 "LST-D9 — captura NU mai e pasul urmator, fiindca s-a facut si "
                 "raspunsul inchide domeniul: blobul inline al paginii isi declara "
                 "singur configuratia, iar API-ul e pe `api-sizeer.adafir.eu` — "
                 "domeniul `adafir.eu`, care NU e subdomeniu al lui `sizeer.ro`. "
                 "Allow-list-ul portii il refuza pe drept, si asta e un STOP, nu un "
                 "obstacol de ocolit. In plus cere `clientId` si `clientCode` "
                 "(valorile NU se transcriu nicaieri), iar 3 din cele 4 `<script "
                 "src>` ale paginii sunt Akamai. NOTA de masuratoare: o cautare "
                 "automata de cai `/api/` da patru potriviri FALSE — "
                 "`/barbati/pantofi/slapi` contine literele „api” in „slapi”; "
                 "numarul real de cai `/api/…` e ZERO. "
                 "DEAL-D11 — API-ul NU e necesar, si de aceea STOP-ul de allow-list "
                 "RAMANE NEATINS: nu s-a ridicat, s-a dovedit inutil. Verdictele "
                 "vechi („grila nu e servita deloc”, „reintrarea cere captura "
                 "API-ului”) erau corecte DESPRE PAGINILE MASURATE — `/outlet` are o "
                 "singura oferta reala, iar `/promotii-actuale` zero — dar amandoua "
                 "sunt pagini gresite: `/outlet` e aproape gol, iar "
                 "`/promotii-actuale` e o pagina de aterizare cu linkuri de campanie. "
                 "Pe o CATEGORIE (`/barbati`) grila e INTREAGA in DOM: 60 de carduri "
                 "`[data-product-id]`, adica exact `defaultItemPerPage` din "
                 "configuratie. Capcana de numarat, daca cineva se intoarce la "
                 "bloburi: acolo blocurile sunt `variant_product_offer` — VARIANTE de "
                 "marime — si doar PRIMA varianta poarta `name`/`id`/`price` reale, "
                 "restul au `id: 0` si `price_gross: 0`; pe `/outlet` ies 40 de "
                 "variante din 4 parinti pentru O SINGURA oferta.",
        # ── DEAL-D11 — axa D pe CSS, din DOM (sonda LST-D10 §4) ───────────────
        "listing": {
            # Intrarea e o CATEGORIE, nu pagina de outlet: `/outlet` are 1 oferta,
            # `/promotii-actuale` are 0. `/femei` si `/copii` intra dupa ce sunt
            # CERUTE — exista in nav, dar n-au fost masurate.
            "url": "https://sizeer.ro/barbati",
            # Sablonul e citit VERBATIM din pagina: `<link rel="next"
            # href="/barbati?page=2">`. Si e DOVEDIT, nu doar declarat: p2 da alte
            # 60 de produse, cu ZERO in comun cu p1.
            "page_url_template": "https://sizeer.ro/barbati?page={n}",
            "max_pages": 10,
            "currency": "RON",
            # Cardul poarta si `data-price="249.99"`, care ar fi fost mai curat
            # decat textul. NU e folosit, si motivul e de cod, nu de gust:
            # `price_attr` face `card.select_one(<selector>)`, care cauta printre
            # DESCENDENTI, iar `data-price` e chiar pe cardul insusi — deci
            # selectorul intoarce None si extractorul sare TOATE cardurile.
            # Masurat: `price_attr` da 0 carduri, `price_text` da 60/60.
            "card": "div[data-product-id]",
            "link": "a.title",
            "title": "a.title",
            "price_text": "span.main-price",
            # REFERINTA E `min30`, SI NU E O PREFERINTA. Cardul are DOUA linii
            # taiate: una directa (pretul de lista) si una in `.omnibus-price`,
            # etichetata „- cel mai mic pret”. Ele DIVERG pe 13 din 26:
            #
            #   produs                    platit   min30   taiat
            #   Reebok Club C 85 Vintage  289,99  309,99  449,99   6,5% vs 35,6%
            #   Vans rucsac Old Skool     159,99  169,99  229,99   5,9% vs 30,4%
            #   Nike rucsac Y NK JDI Mini 109,99  129,99  139,99  15,4% vs 21,4%
            #
            # Un descriptor pe linia taiata ar raporta reduceri mai mari decat
            # cele legale. A treia oara in proiect dupa modivo (LST-3b) si
            # answear (LST-D7), unde doua linii ETICHETATE divergeau la fel.
            "compare_text": "span.omnibus-price span.old-price",
            "price_parse": "eu_comma",
            "compare_parse": "eu_comma",
            "reference_kind": "min30",
            # FARA IMAGINE, si e masurat: `<img>` poarta un placeholder base64 in
            # `src` si un `data-original` GOL — URL-ul real vine din JS. 0/60.
            # (Bloburile de stare au `gallery`, dar un descriptor CSS nu le poate
            # atinge, si nu se amesteca cele doua cai pentru un camp optional.)
        },
    },
    # ── G2F — sub-lotul sport/outdoor (sonde 2026-08-18) ──────────────────────
    # Din patru domenii sondate au intrat TREI. decathlon.ro e Grup 4 (Cloudflare
    # „Just a moment" pe toate profilurile, la home) si asteapta valul de browser.
    "intersport.ro": {
        "label": "Intersport",
        "category": "incaltaminte",
        "channel": "haine",
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
        # DEAL-2 — masurat la LST-2 (dump-uri `scripts/diagnostics/dumps_lst2/`):
        # `data-total-pages="305"`, 30 de carduri pe pagina, 9148 de produse — dar
        # astea sunt cifrele pe care le ANUNTA site-ul, nu cele pe care le SERVESTE;
        # vezi nota despre clamp de la `max_pages`.
        # CORECTIE la nota de mai sus: G2F-2 consemnase „86 de carduri"; masurat
        # acum sunt 30, cifra care se si inchide cu totalul (305 x 30 = 9150 ~ 9148).
        # Paginarea, nemasurata la G2F-2, e acum masurata pe ambele capete:
        # `<link rel="next" href="https://www.intersport.ro/sale/p2/" />` pe p1 si
        # `rel="prev"` -> /sale/ pe p2. Dincolo de final NU e 404: `/sale/p9999/` da
        # 200 cu grila GOALA (zero `article.x-product-box`, „0 produse"), adica
        # tiparul otter/caseking — il prinde conditia compusa existenta, deci valul
        # asta n-a avut nevoie de cod nou in scanner. ATENTIE: pe pagina goala
        # `rel=next` inca arata spre /sale/p10000/, deci rel=next NU e semnal de
        # oprire; scannerul se opreste pe grila goala, si bine face.
        "listing": {
            "url": "https://www.intersport.ro/sale/",
            # Numarul de pagina e in CALE, sub forma /pN/ — citit din `rel=next`.
            "page_url_template": "https://www.intersport.ro/sale/p{n}/",
            # DERIVAT, nu citat: 305 pagini ANUNTATE (`data-total-pages`) plus marja,
            # dupa conventia otter (197 reale / 210).
            #
            # In practica plasa asta NU se atinge, si merita stiut de ce. Scanul live
            # de la RUNDA 2 s-a oprit la pagina 126 pe clauza „pagina repetata"
            # (CLAMP), dupa 125 de pagini si 3477 de produse UNICE — adica 38% din
            # catalogul anuntat. 125 x 30 = 3750, exact offset-ul de la care pagina
            # 126 ar trebui sa inceapa: site-ul pare sa clameze la ultima pagina
            # servita cand ceri dincolo de setul real, tiparul bergfreunde. Deci
            # „9148 produse / 305 pagini" e o numaratoare de catalog (probabil pe
            # variante), nu adancimea navigabila a grilei.
            #
            # Listarea se si RE-SORTEAZA intre cereri: 273 din cele 3750 de carduri
            # servite erau deja vazute (7,3%), iar sonda masurase acelasi lucru intre
            # p1 si p2 (2 URL-uri comune din 60, Jaccard 0.034). Garda SCAN-1
            # (`vazute`) le absoarbe, deci nu se dubleaza nimic in baza.
            "max_pages": 320,
            # Din COD, ca la axa L: langa pret scrie „LEI", nu „RON".
            "currency": "RON",
            "card": "article.x-product-box",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["data-src"],
            # Doua ancore per card duc la acelasi PDP; `js-select-product` e cea
            # unica (a doua poarta doar `js-click-product`).
            "link": "a.js-select-product",
            # `h2.heading` poarta numele CU brand („adidas PANTOFI GALAXY 8");
            # `.title` din acelasi card il da fara brand („PANTOFI GALAXY 8").
            "title": "h2.heading",
            # Pe TEXT, nu pe atribut: `data-current-price="189,99"` e cu VIRGULA, iar
            # calea de atribut trece prin parserul strict cu punct si ar da tacut
            # None. Nodul `.current-price` poarta „189,99 LEI" si merge prin
            # `_pret_eu_comma`. Capcana `span.points-gain` din G2F-2 (aceeasi cifra,
            # alt inteles) e fenomen de PDP: pe listare apare de 0 ori.
            "price_text": ".current-price",
            "compare_text": "span.deleted-price",
            "price_parse": "eu_comma",
            # Niciun label legal pe listare: „Omnibus" x0, „30 de zile" x0,
            # „cel mai mic" x0, „PRP" x0 — deci referinta e NEMARCATA.
            "reference_kind": "nemarcat",
            # FARA `stock_attr`, INTERZIS EXPLICIT: `out-of-stock` apare pe 30/30 de
            # carduri ca sablon ascuns prin CSS extern (tiparul elefant, deja
            # consemnat in nota axei L). Un sablon ascuns nu e stare, deci ar marca
            # tot catalogul drept indisponibil.
        },
    },
    "toolnation.nl": {
        "label": "Toolnation",
        "category": "bricolaj",
        "channel": "diverse",
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
        # DEAL-2 / VAL D runda 4a — PRIMUL descriptor de listare pe STARE, nu pe
        # selectori CSS. Datele listarii nu sunt in DOM: pretul nu apare deloc in
        # textul vizibil (vezi `notes`), deci `card`/`link`/`price_text` n-au ce
        # descrie. De aici cheia `state_extractor`, care deleaga parsarea unui
        # extractor inregistrat in `listing_state_extractors.py`.
        #
        # Masurat pe DOUA pagini — p1 la G2F-1/G2F-2 (`dumps_g2f/`) si p2 la LST-4
        # (`dumps_lst4/`): 24 de `Product` pe fiecare, cu ACELEASI noua chei pe
        # 24/24 si o singura `Offer` cu opt chei pe 24/24, iar `p1 ∩ p2 = 0` —
        # starea chiar traieste pe paginare, nu re-randeaza prima pagina.
        # Paginarea: `<link rel="next" href=".../aanbiedingen.html?p=2" />` pe p1 si
        # `?p=3` pe p2; totalul, verbatim din toolbar: „1 - 24 van 819" pe p1 si
        # „25 - 48 van 818" pe p2 (a driftat cu unul in cinci zile).
        "listing": {
            "url": "https://www.toolnation.nl/aanbiedingen.html",
            "page_url_template": "https://www.toolnation.nl/aanbiedingen.html?p={n}",
            # DERIVAT, nu citat: `class="page last"` arata `?p=35`, iar 35 x 24 = 840
            # acopera cele 818-819 produse anuntate. 45 e aia plus marja, conventia
            # otter.
            "max_pages": 45,
            # Din STARE, incrucisat: `priceCurrency: "EUR"` pe 24/24 pe ambele pagini.
            "currency": "EUR",
            "state_extractor": "toolnation_ldjson",
            # NEMARCAT, si mai tare decat de obicei: in ld+json nu exista NICIO cheie
            # de referinta (`highPrice`/`listPrice`/`was`), masurat pe ambele pagini.
            # Consecinta e de regim, nu cosmetica: `compare_at` iese None pe tot, deci
            # R1 nu poate porni NICIODATA aici si dealurile vin exclusiv din minimul
            # istoric (R2) — acelasi caz ca buzzsneakers.
            "reference_kind": "nemarcat",
            #
            # Doua campuri din stare ramin DELIBERAT necitite:
            #  * stocul — `availability` e `InStock` pe 24/24 pe AMBELE pagini, ceea ce
            #    nu se poate deosebi de o constanta de sablon. Capcana e dovedita pe
            #    vivre (`ldjson_availability: "untrusted"`), unde PDP-urile emiteau
            #    `OutOfStock` pe produse pe care listarea proprie le dadea in stoc.
            #    Cat timp e nedecis, nu se declara stoc deloc.
            #  * `description` — IDENTIC pe toate cele 24 („Sale % bij Toolnation.
            #    Ontdek alle producten binnen deze categorie."), deci text de
            #    categorie, componenta partajata. Titlul vine din `name`, distinct
            #    24/24.
        },
    },
    "direct-running.com": {
        "label": "Direct Running",
        "category": "incaltaminte",
        "channel": "sneakers",
        # Sediul NU e dovedit juridic: singurul semnal masurat, prezent identic pe
        # home, PDP si listare, e „Customer service in France". E serviciu de clienti,
        # nu sediu, si sta in tensiune cu moneda USD — de aici mentiunea din notes.
        "country": "FR",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # DEAL-D1: moneda lipsea de la nivelul intrarii. Nu e o presupunere —
        # ld+json declara USD pe PDP (G2F-1) si cardurile de listare poarta „$" pe
        # 24/24 (LST-D1 §2.1), doua surse independente pe acelasi domeniu.
        "currency": "USD",
        # ── DEAL-D1, din sonda LST-D1 §2.1 ──────────────────────────────────
        "listing": {
            "url": "https://direct-running.com/outlet",
            # PAGINA-UNICA, masurat: zero `rel=next`, zero `?page=`/`?p=`, zero
            # token `pagination` in HTML-ul brut; incarcarea e pe buton („Show
            # more"), deci NU exista `page_url_template`. Cu `max_pages: 1` bucla
            # face o tura si `_pagina_url` intoarce `url`, fara sa atinga vreodata
            # template-ul. Acoperire: 24 de carduri SSR din cele „1406 products"
            # anuntate — tiparul bonami, unde infinite-scroll-ul e NON-SCOP.
            "max_pages": 1,
            # Din CARD, incrucisat pe 24/24: simbolul e „$", nu „€" — vezi `notes`.
            "currency": "USD",
            "card": "div.group.relative.w-full",
            # `a[title]`, nu `a[href]`: cardul poarta 4 ancore, dintre care una
            # catre /brands/<marca>. Ancora de titlu e singura cu atributul
            # `title`.
            "link": "a[title]",
            "title": "a[title]",
            "image_attr": ["src"],
            "price_text": ".special-price .price",
            "compare_text": ".old-price .price",
            # MOTIVUL pentru care treapta `us_dot` exista (DEAL-D1): pe „$117.63"
            # parserul european da 11763.0, fiindca sterge punctul ca separator de
            # mii — masurat de LST-D1 §2.8, rulind acest descriptor prin
            # `extrage_carduri` insusi. `attr_float` n-avea ce citi: cardul n-are
            # niciun atribut numeric (0 `content=`, 0 `data-price*`). Domeniul e
            # primul si singurul consumator al treptei.
            "price_parse": "us_dot",
            # `Starting at` pe 24/24 — pret „de la", nu eticheta legala. Singurul
            # „30 days" din pagina e politica de retur („30 days to change your
            # mind"), deci nu eticheteaza campul (lectia bergfreunde).
            "reference_kind": "nemarcat",
        },
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
                 "val ULTERIOR — vezi docs/catalog_domain_log.md. DEAL-D1, din sonda "
                 "LST-D1: axa D intrata, cu DOUA corecturi la randul de mai sus. (1) "
                 "Numarul: /outlet serveste 24 de carduri server-rendered, nu 97 — "
                 "pagina anunta „1406 products\" si restul se incarca pe buton „Show "
                 "more\", deci NU exista paginare server-side si acoperirea e cele 24 "
                 "(tiparul bonami). Situl e SvelteKit. (2) Selectorul: clasele sunt "
                 "utilitare Tailwind, iar `w-full` e OBLIGATORIU — "
                 "`div.group.relative` singur prinde 48 de noduri, adica dublu. "
                 "Fragilitate declarata: un refactor de layout poate schimba clasele "
                 "fara sa schimbe produsul. Domeniul e primul consumator al treptei de "
                 "parsare `us_dot`, adaugata tot la DEAL-D1: pretul din card e "
                 "„$117.63\", pe care parserul european il citea 11763.0.",
    },
    "zooplus.ro": {
        "label": "Zooplus",
        "category": "pet",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D1, din sonda LST-D1 §2.2 ──────────────────────────────────
        "listing": {
            "url": "https://www.zooplus.ro/shop/oameni_animale/promotii",
            "page_url_template": "https://www.zooplus.ro/shop/oameni_animale/"
                                 "promotii?p={n}",
            # DERIVAT: „1 - 48 din 801 rezultate" -> 17 pagini reale, plus marja
            # (conventia otter). Oprirea reala vine oricum din CLAMP: `?p=500`
            # raspunde 200 cu EXACT cardurile paginii 1.
            "max_pages": 22,
            "currency": "RON",
            # `data-zta`, NU clasa: `ProductCard_productCard__HRbGU` selecteaza
            # acelasi set, dar `__HRbGU` e hash de build CSS-modules si moare la
            # redeploy.
            "card": "[data-zta='product-card']",
            "link": "a[title]",
            "title": "h2",
            "image": "img[data-zta='product-slider-image']",
            "image_attr": ["src"],
            # Atribut numeric cu punct zecimal, exact una pe card (48/48) — se
            # prefera textului „20,90 lei" si parserului de virgula.
            "price_attr": ("meta[itemprop='price']", "content"),
            "price_parse": "attr_float",
            # DELIBERAT FARA `compare_*`. Singura referinta din card e etichetata
            # `Individual` (12/48 pe p1, 19/48 pe p2, ZERO altfel), cu tooltipul
            # „Pretul total al acelorasi produse daca sunt cumparate separat" — e
            # o comparatie pachet-vs-bucata, nu un pret anterior. Citita ca
            # `compare_at`, ar fabrica un deal pe fiecare multipack. Fraza
            # Omnibus exista in subsol si in i18n, dar NU eticheteaza niciun camp
            # de card (lectia bergfreunde). Consecinta: R1 nu porneste niciodata
            # aici, dealurile vin din R2 — acelasi regim ca toolnation si
            # buzzsneakers.
            "reference_kind": "nemarcat",
        },
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
                 "stabil — val ULTERIOR — vezi docs/catalog_domain_log.md. "
                 "DEAL-D1, din sonda LST-D1: axa D INTRATA, dar cu o CORECTIE la "
                 "„selector stabil\" de mai sus — cardul se selecteaza pe "
                 "`data-zta=\"product-card\"`, NU pe clasa. Clasa "
                 "`ProductCard_productCard__HRbGU` selecteaza acelasi set de 48, dar "
                 "sufixul `__HRbGU` e un hash de build CSS-modules si se schimba la "
                 "orice redeploy; `data-zta` e atributul de test al magazinului. "
                 "Numaratoarea anuntata azi e „1 - 48 din 801 rezultate\" (817 la "
                 "G2F-4). Vezi descriptorul `listing` pentru de ce NU se citeste "
                 "niciun pret taiat.",
    },
    "hornbach.ro": {
        "label": "Hornbach",
        "category": "bricolaj",
        "channel": "diverse",
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
                 "un tipar pe `promo` il alege gresit. "
                 "DEAL-D5 — axa D MASURATA acum: FARA_LISTARE. Home-ul are 171 "
                 "de ancore si ZERO candidate pentru "
                 "reduceri/promotii/oferte/procent — navigatia de reduceri e "
                 "client-side. De data asta n-a existat nici macar linkul "
                 "editorial care a dat numele regulii; o singura cerere "
                 "cheltuita.",
    },
    "bonami.ro": {
        "label": "Bonami",
        "category": "general",
        "channel": "diverse",
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
        # DEAL-2 / VAL D runda 4b — listare pe STARE, din `__NEXT_DATA__`.
        # Produsele stau in `initialCataloguePageState.blocks[*].products[]`, si
        # accentul e pe STEA: `blocks` are sapte elemente, iar `products` apare pe
        # TREI (indicii 4, 5, 6, cate 16 = 48). Celelalte patru sunt breadcrumbs,
        # banner si carusel. Un extractor care ar lua primul bloc cu produse ar
        # raporta 16 din 48, tacut.
        #
        # Am verificat si o pista care parea mai buna si a picat: acelasi state are
        # un `productList` cu `totalProductsCount` / `nextPageToken` / `pageIndex`.
        # E GOL server-side (`products: []`, `totalProductsCount: 0`) — e magazinul
        # client-side de infinite-scroll, hidratat ulterior. `blocks[].products[]`
        # ramane singura sursa randata.
        "listing": {
            "url": "https://www.bonami.ro/c/oferte-speciale-si-reduceri",
            # PAGINA-UNICA, masurat: `nextPagePath` e None, zero `rel=next`, zero
            # href cu `?page=`, iar `productList` e gol. Deci NU exista
            # `page_url_template` — si nici nu e nevoie: cu `max_pages: 1` bucla
            # ruleaza o singura tura, iar `_pagina_url` intoarce `url` pentru pagina
            # 1 fara sa atinga vreodata template-ul. Cele 48 de produse sunt o
            # selectie editoriala, nu catalogul de reduceri; infinite-scroll-ul
            # client-side e NON-SCOP.
            "max_pages": 1,
            "currency": "RON",
            "state_extractor": "bonami_next",
            # `retailPrice` e pret de referinta comercial, fara eticheta legala pe
            # pagina — nici „30 de zile", nici „PRP".
            "reference_kind": "nemarcat",
            # Linkul se CONSTRUIESTE `/p/<slug>`: DOM-ul listarii n-are NICIO ancora
            # de produs (masurat: zero `a[href^="/p/"]`), grila fiind hidratata.
            # Forma vine de pe axa L, unde a fost confirmata pe viu (200, fara
            # redirect) — vezi `notes`.
        },
    },
    "action.com": {
        "label": "Action",
        "category": "general",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # RATE-1: 90s intre cereri, pe poarta HTTP. Vezi masuratoarea din notes —
        # 95s a fost pauza care a trecut, 90 e pragul ales sub ea, nu peste.
        "min_fetch_interval_s": 90,
        # ── DEAL-D5 — axa D. Sonda LST-D5 §3.1, control pe p1+p2+plast, 23/23
        # carduri cu pret, referinta, imagine, titlu si URL-uri unice pe fiecare.
        "listing": {
            "url": "https://www.action.com/ro-ro/oferta-saptamanala/",
            "page_url_template": "https://www.action.com/ro-ro/oferta-saptamanala/?page={n}",
            # MASURAT prin bisectie (DEAL-D5, 3 cereri la 90s): pagina 6 are
            # continut nou (18 carduri, pagina activa 6), paginile 7 si 12
            # PLAFONEAZA la pagina 1 (`url_final` cade pe URL-ul fara query,
            # pagina activa 1, acelasi set de 23 de URL-uri, corp byte-identic).
            # Ultima pagina cu continut nou = 6, deci 6 + 1: plusul e chiar
            # pagina care confirma clamp-ul, platita o data per scan de garda
            # `linkuri_pagina <= linkuri_vazute` din `_scaneaza_domeniu`.
            # Verificare independenta: 5 pagini pline x 23 + 18 pe ultima = 133,
            # exact totalul anuntat pe p1 („133 rezultate").
            # Plafonul e MIC si din cost: la `min_fetch_interval_s: 90`, un scan
            # plateste `max_pages` x 90 s, adica ~10 minute pe acest domeniu.
            "max_pages": 7,
            "currency": "RON",
            "card": "[data-testid='product-card']",
            "link": "a[data-testid='product-card-link']",
            "title": "[data-testid='product-card-title']",
            "image": "[data-testid='product-card-image']",
            "image_attr": ["src", "srcset"],
            # Pretul PLATIT e spart in doua noduri (`…price-whole` = 12,
            # `…price-fractional` = 99), iar containerul lor da textul „12 99" —
            # de aici `eu_sup`. `eu_comma` pe acelasi text da 1299.0, adica exact
            # bugul LST-D1, cu doua ordine de marime peste pretul real.
            "price_text": "span:has(> [data-testid='product-card-price-whole'])",
            # NU se citeste `product-card-price-description`: acolo sta pretul pe
            # UNITATE („16,04 lei/kg", „19,98 lei/l", „3,66 lei/m"), care difera
            # de cel platit pe 7 din 12 carduri verificate. E capcana douglas
            # (`price-base-unit`, DEAL-D4), a doua oara in lot.
            "compare_text": "[data-testid='product-card-price-original-amount']",
            "price_parse": "eu_sup",
            # Referinta e taiata (`line-through`) pe 23/23, dar NEETICHETATA.
            # Cele 6 aparitii de „cel mai mic pret" din pagina sunt SLOGAN de
            # marca („Intotdeauna cel mai mic pret", in antet si in teaserul de
            # aplicatie), toate in afara cardurilor — detectorul le-a tinut afara
            # tocmai fiindca lucreaza pe CARD, nu pe pagina.
            "reference_kind": "nemarcat",
        },
        "notes": "G2F-5/G2F-6; Next.js + Cloudflare. Intrebarea de existenta (lista "
                 "master: „verifica daca expune preturi online\") e INCHISA AFIRMATIV: "
                 "are magazin online cu preturi reale — `Offer` cu `price` 3.98 si "
                 "11.95 RON, `InStock`, `priceSpecification` si `seller`. "
                 "ANTI-BOT PE RATA, nu pe ruta si nu pe profil: a 4-a cerere intr-un "
                 "minut a dat 403 „Just a moment...\", iar ACELASI URL pe ACELASI "
                 "profil de PRODUCTIE a trecut cu 200 dupa o pauza de 95s (masurat, "
                 "G2F-5 corectie). De aici `min_fetch_interval_s: 90` — REZOLVAT la "
                 "RATE-1, care a extins mecanismul de pe calea browser pe poarta HTTP "
                 "(`_fetch_shop_url_guarded`), unde sub prag cererea asteapta "
                 "diferenta in loc sa fie refuzata. 90 e ales SUB pauza de 95s care a "
                 "trecut masurat, nu peste ea. Pretul e SPART in DOM (`11 95`), deci extractia pe text "
                 "vizibil e nesigura si ld+json e sursa; cifrele mici (0,07-8,98 lei) "
                 "sunt preturi PE BUCATA, nu ale produsului. PDP "
                 "/ro-ro/p/<ID_numeric>/<slug>/; /ro-ro/promocie-saptamanii/ da 404 "
                 "MASURAT. Omnibus absent, niciun pret taiat pe PDP. "
                 "DEAL-D5 — pe LISTARE exista insa pret taiat pe 23/23 "
                 "(`product-card-price-original-amount`), deci absenta de mai sus e "
                 "a PDP-ului, nu a magazinului. Oferta e SAPTAMANALA: identitatea "
                 "produselor se schimba in fiecare saptamana, deci R2 (minim istoric) "
                 "are memorie scurta aici si R1 (referinta de pe card) e ruta utila.",
    },
    "ro.vivre.eu": {
        "label": "Vivre",
        "category": "general",
        "channel": "diverse",
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
        # DEAL-2 / VAL D runda 4b — listare pe STARE, din payload-ul RSC.
        # URL-ul e forma CANONICA `?qf=discount`, cea pe care o genereaza chiar
        # paginarea lor; sonda LST-4 a masurat ca `?discount=yes` (forma veche, din
        # `notes`) si `?qf=discount` sunt ECHIVALENTE — acelasi total si aceleasi
        # 24 de produse, intersectie 24/24 in aceeasi zi. Paginarea `&page={n}` e
        # dovedita live: `meta.page` chiar devine 2, cu intersectie 0 fata de p1.
        "listing": {
            "url": "https://ro.vivre.eu/products?qf=discount",
            "page_url_template": "https://ro.vivre.eu/products?qf=discount&page={n}",
            # PLAFON DELIBERAT, nu plasa — singurul din registru asa, si merita spus
            # de ce. `meta.total_pages` era 1.939 pe 18 august, 5.118 pe 21 si 5.201
            # pe 23: catalogul a crescut cu ~78.000 de produse in cinci zile. O plasa
            # „peste maxim" n-are ce sa acopere aici. Primele 50 de pagini (1.200 de
            # produse, sortarea implicita a magazinului) sunt segmentul pe care
            # feedul il urmareste zilnic; enumerarea completa a celor 124.819 e
            # NON-SCOP, nu o limitare tehnica.
            "max_pages": 50,
            "currency": "RON",
            "state_extractor": "vivre_rsc",
            # Singurul domeniu din familie cu fereastra Omnibus scrisa EXPLICIT:
            # i18n-ul din payload spune verbatim „Cel mai mic pret in ultimele 30 de
            # zile", iar textul legal vorbeste de „perioada de 30 de zile anterioara
            # aplicarii reducerii de pret". La modivo eticheta era doar „Cel mai mic
            # pret", fara fereastra. Referinta citita e `lowestPrice` — vezi
            # extractorul pentru de ce NU `originalPrice`.
            "reference_kind": "min30",
        },
    },
    "biciclop.eu": {
        "label": "Biciclop",
        "category": "biciclete",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "G2F-7/G2F-8; WordPress + LiteSpeed. Cheia e FARA `www` — redirect "
                 "MASURAT www.biciclop.eu -> biciclop.eu. ld+json `Product` cu "
                 "`price` / `priceCurrency: RON`, incrucisat cu afisajul "
                 "(`199,99 lei` / `189,99 lei`). ATENTIE, `Offer` n-are "
                 "`availability` — cheile masurate sunt doar [@type, url, price, "
                 "priceCurrency] — deci `in_stock` iese None, si e ONEST: magazinul "
                 "chiar nu publica stoc, pagina spune „Contacteaza-ne pentru "
                 "confirmare stoc\". Referinta taiata (`<del>257 lei</del>`) exista "
                 "DOAR in DOM si e etichetata „Pret recomandat\" — adica RRP, NU "
                 "Omnibus (minimul pe 30 de zile); a nu se confunda intr-un calcul "
                 "de reducere. Ce vinde ONLINE sunt PIESE si accesorii: paginile "
                 "`/biciclete*` sunt editoriale (`/biciclete/` e „catalog istoric\", "
                 "`/biciclete-mtb/` e „informatii utile\"), iar categoria "
                 "`/biciclete-mtb/` masurata are 1 card si zero produse. "
                 "Componente partajate de footer, de ignorat: `200.200,00 RON` "
                 "(capital social) si `400 lei` (pragul de livrare gratuita). "
                 "PDP `/prod/<slug>/`. "
                 "DEAL-D5 — FARA_LISTARE pe axa D: 235 de ancore pe home si "
                 "ZERO candidate pentru reduceri/promotii/oferte/lichidare. "
                 "Nuanta care conteaza: home-ul POARTA produse reduse — 20 de "
                 "ancore de produs cu badge `-51%`, `-55%`, `-50%` — dar niciun "
                 "link de NAVIGATIE catre un raft de reduceri. Magazinul face "
                 "reduceri; nu le aduna intr-un raft adresabil. WordPress DA "
                 "(98 x `wp-content`), WooCommerce NU (0), deci formele "
                 "`?on_sale` / `/product-category/` nu se pot presupune.",
    },
    "cellini.ro": {
        "label": "Cellini",
        "category": "bijuterii-ceasuri",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "custom",
        "status": "validated",
        "notes": "G2F-7/G2F-8; PHP propriu (cookie `csCurrencyId`). Datele de produs "
                 "exista EXCLUSIV in starea paginii — ld+json are doar "
                 "`Organization`/`WebSite`/`BreadcrumbList`, microdata lipseste, iar "
                 "genericul ridica `no_product_data` (pinuit de test). Extractor "
                 "dedicat `cellini_datalayer`: obiectul de produs AL PAGINII se "
                 "identifica pe cheia `url` (numele de fisier al PDP-ului) si se "
                 "incruciseaza cu `code`. Identificarea NU e optionala: pagina are "
                 "48 de obiecte cu `price` (carusele), iar DOM-ul e si mai rau — "
                 "~70 de preturi vizibile, dintre care 8 IDENTICE intre doua PDP-uri "
                 "diferite, deci o extractie pe text ar da sistematic pretul altui "
                 "produs. Pretul: `price` e INTREGUL de lei, banii stau in "
                 "`decimalprice` — se combina, ca sa nu se piarda tacut. Moneda se "
                 "CITESTE din `currencyname` (\"Lei\"), cu `currencyid: \"1\"` si "
                 "`ronvalue: \"1.0000\"` ca semnale suplimentare. Stocul: `stock` e "
                 "sir romanesc, masurat „in stoc\" pe ambele PDP-uri; forma NEGATIVA "
                 "e NEMASURATA, deci se afirma doar pozitivul, restul None. "
                 "`oldprice` + `save_percent` exista in stare dar NU intra in "
                 "contract — referinta ramane pentru axa D. PDP "
                 "`/bijuterii/filtre/<slug>-<COD>.html` (200, fara redirect). "
                 "Segment de lux: preturi masurate pana la 27.990 lei. Listarea "
                 "promo are 539 de produse si 179 de carduri pe pagina, cu "
                 "price+oldprice per card in stare — val ULTERIOR.",
        # DEAL-2 / VAL D runda 4b — listare pe STARE, din `var products`.
        # CORECTIE la `notes` de mai sus: „179 de carduri pe pagina" e GRESIT.
        # Masurat la extractia R4 si reconfirmat la LST-4 pe un dump proaspat: sunt
        # 48, consistent pe fiecare clasa de card din DOM si pe 48 de URL-uri
        # distincte. Totalul 539 se confirma verbatim („Promotii (539)"), deci
        # 539 / 48 = 12 pagini — si exact 12 e si pagina maxima linkata.
        "listing": {
            "url": "https://www.cellini.ro/bijuterii/filtre/promo-promotii",
            # `/pag-{n}` in CALE, citit din `rel=next` verbatim. ATENTIE la forma:
            # nu `/page-`, nu `?page=` — tiparul romanesc `pag` n-a fost prins de
            # detectorul de paginare al sondei, l-a salvat `rel=next`.
            "page_url_template": "https://www.cellini.ro/bijuterii/filtre/"
                                 "promo-promotii/pag-{n}",
            # 12 masurate + marja.
            "max_pages": 16,
            "currency": "RON",
            "state_extractor": "cellini_js",
            # Zero eticheta legala pe listare; `save_percent` din stare e doar
            # procentul fata de `oldprice`, nu o referinta Omnibus.
            "reference_kind": "nemarcat",
            #
            # DOUA consecinte de stiut, ambele masurate la LST-4:
            #
            # (1) `external_id` iese pe calea-RADACINA. `url` din stare e un nume de
            #     fisier gol, ancorat de `<base href="https://www.cellini.ro/">`.
            #     Sonda C6 a masurat ca forma-radacina raspunde 200 fara redirect si
            #     e SELF-CANONICAL (og:url + ld+json `Product.url` la fel), in timp
            #     ce `/bijuterii/filtre/<fisier>.html` canonicalizeaza spre
            #     `/bijuterii` — categoria. Radacina e deci calea corecta.
            #     Fiindca `external_id` e sha1 pe CALE, randurile vechi intrate prin
            #     `refresh_diff` pe `/bijuterii/filtre/` vor avea ALT id. Divergenta
            #     e ASUMATA si nu se migreaza: sunt cateva randuri de link manual,
            #     iar o migrare ar rescrie identitati pe baza unei presupuneri
            #     despre ce a vrut userul sa urmareasca.
            #
            # (2) Titlul vine din SLUG, nu din stare: `name` e `null` pe 48/48, iar
            #     `metatitle`/`subtitle` sunt goale. Alternativa era `code` (SKU),
            #     stabil dar ilizibil in feed. DOM-ul ar fi avut `.product-name`, dar
            #     l-ar fi legat de o a doua sursa — se reconsidera cand schema va sti
            #     sa combine stare + DOM.
            #
            # DOM-ul de pret e oricum nefolosibil: `.price-product` da
            # „17.340 , 00 Lei (-15%) 14.739 , 00 Lei" — ambele preturi intr-un nod,
            # cu spatii in jurul virgulei, deci un parser de text le-ar concatena.
        },
    },
    "foto-erhardt.com": {
        "label": "Foto Erhardt",
        "category": "foto",
        "channel": "electronice",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT2b; starea second-hand traieste doar in calea URL "
                 "(itemCondition absent); bucati unice, comportament la vandut nemasurat. "
                 "LST-D5 — NEPOTRIVIT pe axa D, masurat: `/second-hand.html` are "
                 "listare reala (36/pagina) dar ZERO preturi taiate pe 155 de "
                 "carduri, pe 4 pagini — bucati unice, deci nicio referinta din "
                 "care sa iasa un deal, iar un istoric pe o bucata unica nu spune "
                 "nimic. Doua forme de retinut: cardul E ancora "
                 "(`a.product.product--used`), punct orb al sondelor, care cer o "
                 "ancora DESCENDENTA; si `/second-hand.html/500` plafoneaza la "
                 "ULTIMA pagina (activa 10, canonical si h1 neschimbate), nu la "
                 "prima ca action — deci `max_pages` = 10 se citeste direct din "
                 "paginator. Unele carduri poarta un INTERVAL de pret "
                 "(„999,00 - 1.199,00 €”), care nu e un pret de citit. "
                 "LST-D9/DEAL-D10a — verdictul NEPOTRIVIT de mai sus era despre "
                 "SECOND-HAND, si ramane corect acolo. Produsele NOI reduse traiesc "
                 "in alta parte: `/dealzone.html`, ancora „%Dealzone\" a home-ului, "
                 "necurata vreodata pana la LST-D9. Magazinul NU-si arata reducerea "
                 "ca pret taiat pe NICIUNA din cele patru pagini masurate ale lui "
                 "(second-hand, hama-sale, dealzone, offers): zero `<del>`, zero "
                 "`<s>`, zero `line-through`, zero `UVP`, zero `statt`, zero `-N%`. "
                 "O arata ca ECONOMIE, si acolo e pe 48/48. `/offers.html` (36 de "
                 "carduri, alt sablon) are 0/36 economie, deci NU intra: ar fi o "
                 "intrare fara referinta, pe alt selector de card decat dealzone.",
        # ── DEAL-D10a — din sonda LST-D9 §3.1 ─────────────────────────────────
        "listing": {
            "url": "https://www.foto-erhardt.com/dealzone.html",
            # Paginarea e RELATIVA in pagina (`href="?page=2"`), iar sonda a
            # respins-o gresit: `_absolut` rezolva orice href fata de RADACINA
            # (regula corecta pentru linkurile de CARD, gresita pentru paginare) si
            # ajungea la `foto-erhardt.com/?page=2`, fara cale. Verificat direct:
            # `dealzone.html?page=2` da 200 cu 48 de carduri si intersectie 1.
            "page_url_template": "https://www.foto-erhardt.com/dealzone.html?page={n}",
            # Pagina declara 6 pagini; plafonul e 8 ca sa incapa o campanie ceva
            # mai mare fara sa se re-scrie registrul. Oprirea reala o da grila
            # goala sau clamp-ul.
            "max_pages": 8,
            "currency": "EUR",
            # Cardul E chiar ancora: 48 de `a.products__product`, copii DIRECTI ai
            # containerului, cu ZERO ancore interioare. De aici `link: "@self"`.
            "card": "div.products a.products__product",
            "link": "@self",
            "title": ".products__name",
            "image": "img",
            "price_text": "span.products__price--standard",
            # DEAL-D10a — referinta e o RECONSTRUCTIE: pret + economie.
            # „699,00 €" + „50,00 € saved" = 749,00. `eu_comma` curata singur si
            # cuvantul „saved", si simbolul, si spatiul neintrerupt.
            "compare_saving_text": "small.products__price--saved",
            "price_parse": "eu_comma",
            # Ramane `nemarcat` DELIBERAT: 749,00 nu e un pret pe care magazinul
            # l-a declarat vreodata, ci unul calculat de noi din doua pe care le-a
            # declarat. Corect aritmetic, dar nu o referinta legala — deci acelasi
            # grad de incredere ca un pret taiat fara eticheta.
            "reference_kind": "nemarcat",
        },
        # Pretul e BRUT („VAT incl." pe card).
        #
        # Dealzone e o campanie CU TERMEN: fiecare card poarta `data-ending`
        # (epoca) si un `products__countdown`. Consecinta operationala: un scan
        # care intoarce ZERO carduri nu inseamna neaparat descriptor stricat, ci
        # poate insemna „campania s-a incheiat" — se re-masoara inainte de a se
        # umbla la selectori.
    },
    "f64.ro": {
        "label": "F64",
        "category": "foto",
        "channel": "electronice",
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
        # AXA D — `api_enum`, primul domeniu pe sursa asta. Mecanismele sunt
        # masurate la VTX-1/1b/1c/2 si VTX-3; ce e aici sunt DATE despre magazin,
        # nu algoritm (fereastra, plafoanele si descenderea stau in api_scanner).
        "catalog_api": {
            # RUNDA 3b — baza CU `www`, masurata: runda 3 a plecat de la cheia de
            # registru (`https://f64.ro/...`) si a incasat un redirect pe 335 din
            # 335 de cereri, catre `https://www.f64.ro:443/...`. Hopul se plateste
            # o data la fiecare cerere, deci se evita din start.
            "base": "https://www.f64.ro",
            "endpoint": "/api/catalog_system/pub/products/search",
            "tree": "/api/catalog_system/pub/category/tree/2",
            # Moneda NU vine din raspuns: `commertialOffer` n-are niciun camp de
            # moneda (masurat: „RON" x0, „currency" x0 in tot corpul), deci se ia
            # de aici. RON e masurat pe ld+json-ul aceluiasi domeniu (VTX-2).
            "currency": "RON",
            # `ListPrice` e PRP, nu minim pe 30 de zile: de aceea R1 merge pe
            # `listing_r1_threshold`, nu pe pragul global.
            "reference_kind": "prp",
            # Categorii ne-catalog. SASE, nu sapte: „EOL" a fost SCOASA la runda
            # 3e, pe masuratoarea VTX-3d, si merita spus de ce — documentele o
            # dadeau drept zgomot, iar cifrele o contrazic:
            #
            #   EOL (1000013)                          20.779 produse
            #   Insurance / frontend / Card Cadou F64        6 / 1 / 1
            #   Advanced Payment / SH-uri de postat / NoDepartment   0 / 0 / 0
            #
            # Cele 20.779 erau 99,96% din gaura de acoperire masurata la 3c
            # (52.540 in catalog fata de 31.752 intalnite). ATENTIE insa la
            # compozitia lor, masurata complet prin recensaminte de banda la
            # rundele 3g/3h: doar 13 produse au pret real (resigilatele, ex.
            # Fujifilm X-T2 la -20%), iar 20.766 (99,94%) au pretul indexat 0 —
            # non-oferte, tratate prin D9 (banda P:[0 TO 0] se recenseaza dar
            # NU se enumereaza). Esantionul E8 de la 3d (10 produse "toate cu
            # pret") era capul unei liste sortate, deci partinitor. EOL ramane
            # inclusa pentru cele 13 reale; `categoriesIds: ["/1000013/"]`
            # arata ca stau exclusiv acolo.
            # Celelalte sase raman: masurate goale sau neglijabile (8 produse cap).
            "exclude_categories": [
                "Advanced Payment Products",
                "SH-uri de postat",
                "frontend",
                "NoDepartment",
                "Insurance",
                "Card Cadou F64",
            ],
        },
        # SEARCH-1 — cautarea refoloseste `catalog_api.endpoint` cu `?ft=`, masurat
        # la SEARCH-0: 206 pe fereastra plina (50/50 la `sony alpha`), 200 cu `[]`
        # pe termenul inexistent.
        "search": {"kind": "vtex"},
    },
    "elefant.ro": {
        "label": "Elefant",
        "category": "general",
        "channel": "diverse",
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
                 "vezi docs/catalog_domain_log.md; DEAL-D2 — JS_ONLY pe axa D. "
                 "Scheletul lichidarilor e cartografiat complet: URL-ul real e "
                 "`/list/promotii-speciale/lichidari-de-stoc/filters/"
                 "warehouse_stock-true` (home-ul NU-l linkuieste), paginarea "
                 "`?pag={n}`, 8.260 de produse anuntate, iar `?pag=500` intoarce "
                 "grila GOALA (semnatura de oprire). Lipsesc doar datele: cele 60 "
                 "de placi sunt literalmente goale, fiindca Intershop le randeaza "
                 "prin `ViewProduct-RenderProductComponents` per SKU, adica o A "
                 "DOUA cerere. Ruta scurta `/lichidari-de-stoc` da 503 persistent "
                 "(aceeasi pagina de mentenanta din august).",
    },
    # ── G1 — ultimele doua din Grupul 1 (sonda G1-1 + pasa 2, 2026-08-17) ──────
    # Amandoua erau marcate "sonda Shopify la implementare"; masuratoarea le-a
    # infirmat pe amandoua, deci intra pe jsonld. Fara camp `impersonate`: 12/12
    # cereri au raspuns 2xx pe amprenta implicita a productiei, lantul de
    # escaladare nu s-a activat niciodata.
    "sivasdescalzo.com": {
        "label": "Sivasdescalzo",
        "category": "sneakers",
        "channel": "sneakers",
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
                 "e o aterizare, nu o listare — vezi docs/catalog_domain_log.md. "
                 "IMP-2: pica pe profilul centralizat (2026-08-22, BLOCKED), deci "
                 "ramane pinuit pe profilul anterior — vezi cheia `impersonate`. "
                 "Masurat INTERMITENT, nu determinist: pe profilul centralizat 2 din "
                 "4 cereri au iesit BLOCKED, pe cel anterior 0 din 4. Singurul "
                 "domeniu din 73 cu regresie, si singurul motiv pentru care exista "
                 "override-ul de mai jos. "
                 "JSON-0 — ZID pe browser: 307 apoi 403, cu lantul de challenge "
                 "Cloudflare Turnstile (`/cdn-cgi/challenge-platform/…`, "
                 "`challenges.cloudflare.com/turnstile/v0/…`). Nici aici "
                 "`_detecteaza_blocare` n-a prins: markerul „Just a moment” e DOAR in "
                 "`<title>`, iar corpul zice „Performing security verification” — "
                 "v. GUARD-1 in docs/catalog_domain_log.md. "
                 "LST-D7 - INTRA pe axa D, iar nota veche („pagina de promotii e o "
                 "ATERIZARE, nu o listare”) era GRESITA: `/en` declara in nav CINCI "
                 "listari de sale — `/en/deals/men`, `/en/deals/women` si trei "
                 "praguri de procent. `/en/deals/men` are 48 de carduri, 48 de "
                 "URL-uri, referinta si imagine 48/48, `p1 ∩ p2 = 0`. Poarta daduse "
                 "`None` pe `/en/` fiindca acolo e un 301 catre `/en` (fara slash) "
                 "pe care nu l-a dus la capat; pe forma canonica a mers din prima.",
        # ── DEAL-D7, din dump-urile LST-D7 (p1/p2) + o cerere de verificare ──
        "listing": {
            "url": "https://www.sivasdescalzo.com/en/deals/men",
            # `?p={n}`, citit din `<link rel=next>` din `<head>` — nu dintr-un
            # `<a rel=next>` din corp, care pe alte magazine s-a dovedit sageata de
            # carusel (corectia C2 a sondei, LST-D7 §0).
            "page_url_template": "https://www.sivasdescalzo.com/en/deals/men?p={n}",
            # Plafon de buget. Adancimea reala n-a fost masurata, dar coada DA:
            # `?p=500` raspunde 200 cu GRILA GOALA (0 carduri, 463.957 octeti) —
            # oprire curata, aceeasi semnatura ca la altex/flip/lego. Deci plafonul
            # e plasa, iar bucla se inchide singura.
            "max_pages": 20,
            # Vitrina `/en` serveste USD — masurat la G1-1 pe trei surse
            # independente si reconfirmat la LST-D7 din RSC-ul listarii
            # (`"currency":"USD"`). Conversia o face BNR, ca la direct-running.
            "currency": "USD",
            "card": "#products-grid li.overflow-hidden",
            "link": "a[href*=\"/en/p/\"]",
            "title": "h3",
            # In card, pretul platit si cel taiat sunt doua `<p>` frati; al doilea
            # poarta `line-through`. `us_dot`: „$96.25" are punct zecimal.
            "price_text": ".Product_Information_Container p.text-black",
            "compare_text": ".Product_Information_Container p.line-through",
            "price_parse": "us_dot", "reference_kind": "nemarcat",
            # `/en/deals/women` exista in nav si NU intra: n-a fost masurata.
        },
        # IMP-2: vezi nota. Pinuit pe profilul anterior fiindca acolo masuratoarea e
        # curata (4/4 OK), nu fiindca profilul nou ar fi gresit in general — pe
        # celelalte 72 de domenii e egal sau mai bun (3 deblocari). De re-masurat
        # la urmatorul bump de profil; daca devine stabil, override-ul iese.
        "impersonate": "chrome131",
    },
    "tezyo.ro": {
        "label": "Tezyo",
        "category": "incaltaminte",
        "channel": "sneakers",
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
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image": "img.product-image-photo", "image_attr": ["src"],
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
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3. SNK-1 a adaugat proba de PLATFORMA care lipsea la G2C-2: e "
                 "NBSHOP, aceeasi cu sportvision.ro — cookies NBIDSN + "
                 "NBPHPSESSIONSECURE, marker `NBSHOP` in corp, cai de imagine "
                 "`slike-proizvoda` si resturi sarbesti netraduse in carduri "
                 "(`Uporedi`, `Brzi Pregled`). Nota lui sportvision spunea ca "
                 "inrudirea „n-a fost dovedita cu fragmente din AMBELE parti, "
                 "fiindca nu exista dump buzzsneakers\" — exista, din LOT3, iar acum "
                 "exista si dump de LISTARE.",
        # DEAL-2 — masurat la SNK-1/SNK-2: NBSHOP, `data-total-pages="39"`, 24 de
        # carduri pe pagina, 918 produse la scanul live. Intrarea a asteptat valul
        # D fiindca paginarea se termina in 404 (pagina 40), iar `_scaneaza_domeniu`
        # ridica RuntimeError la orice status != 200 — inainte de `db.commit()`,
        # deci se pierdea tot scanul. Valul D a invatat scannerul ca 404 pe o
        # pagina > 1, dupa una reusita, e OPRIRE; `max_pages` redevine o margine.
        "listing": {
            "url": "https://www.buzzsneakers.ro/produse/outlet",
            # Numarul de pagina e in CALE, cu CRATIMA — nu in query, ca la Magento.
            "page_url_template": "https://www.buzzsneakers.ro/produse/outlet/page-{n}",
            # 39 de pagini MASURATE; plasa e peste, ca la otter (197 reale / 210).
            # Supra-dimensionarea e gratuita de la valul D incoace: pagina de peste
            # final da 404 si opreste curat. Sub-dimensionarea ar tacea si ar taia,
            # iar `/produse/outlet` e un OUTLET — numarul de pagini scade des.
            "max_pages": 60,
            "currency": "RON",
            # Cardul-PARINTE, cel care poarta atributele; 24 pe pagina.
            "card": ".product-item",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["data-original-img"],
            "link": "a.product-link",
            # `.title`, nu textul ancorei: ancora produsului scrie „Detalii" pe
            # TOATE cardurile, deci ar da acelasi titlu peste tot.
            "title": ".title",
            # Pe text, nu pe atribut: `data-productprice` exista pe card, dar e cu
            # VIRGULA („455,99"), iar calea de atribut trece prin parserul strict cu
            # punct si ar da tacut None. `div.current-price span.value` poarta
            # aceeasi valoare si merge prin `_pret_eu_comma`.
            "price_text": "div.current-price span.value",
            "price_parse": "eu_comma",
            # FARA cheie de pret taiat, DELIBERAT. Pretul vechi exista doar ca
            # `data-productprevprice="759,99"` — tot cu virgula, deci necitibil pe
            # calea de atribut — iar vizibil nu se randeaza niciun pret taiat (zero
            # <del>/<s>, `data-productdiscount` constant "0"). Domeniul califica deci
            # pe R2 (minim istoric), nu pe R1.
            "reference_kind": "nemarcat",
        },
    },
    "officeshoes.ro": {
        "label": "Office Shoes",
        "category": "incaltaminte",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "microdata",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.officeshoes.ro/sale",
            # Infinite scroll: cardurile poarta `class="infinite_article"`, iar
            # optiunile de pagina (24/48/96) sunt un `<select>`, nu linkuri.
            "max_pages": 1,
            "currency": "RON",
            "card": ".product-article",
            # PRIMA ancora a cardului e SIGLA MARCII
            # (`<a class="logo" href=".../branduri/calvin-klein">`), nu produsul.
            # Un `link: "a"` ar scoate 48 de carduri cu 10 URL-uri distincte — o
            # masuratoare falsa care arata a duplicate responsive. Ancora
            # produsului e a doua.
            "link": "a.send-search",
            # Ancora n-are TEXT (doar un `<img>`), iar numele complet sta in
            # atributul ei `title`. `h2.product_list_title` exista si e fallback-ul,
            # dar da doar modelul („Kobe M 1C"), fara marca.
            "title_from": "link_title",
            "title": "h2.product_list_title",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image": "img.product-prv",
            "image_attr": ["data-img-article-main", "src"],
            # Ambele numere stau pe ACELASI nod, cu punct zecimal:
            # `<span class="old-price" data-new="359.00" data-old="599.00">`.
            # Textul vizibil e „359,00Lei", fara spatiu inaintea monedei.
            "price_attr": ["span.old-price", "data-new"],
            "compare_attr": ["span.old-price", "data-old"],
            "price_parse": "attr_float",
            # Pret taiat pe 48 din 48, fara nicio eticheta legala langa camp.
            "reference_kind": "nemarcat",
        },
        "notes": ("LOT3"
                 " DEAL-D4 - axa D: `/sale`, 48 de carduri, infinite scroll (deci o pagina). Pretul si referinta vin din atribute pe acelasi nod (`data-new`/`data-old`). PRIMA ancora a cardului e sigla MARCII, nu produsul - de aia `link` e `a.send-search`; titlul e in `title=` pe ea, deci `title_from: link_title` (cheia noua a rundei)."),
    },
    "otter.ro": {
        "label": "Otter",
        "category": "incaltaminte",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT3b; ProductGroup cu hasVariant si variesBy=[size] — "
                 "marimile ies deja ca variante. SEARCH-0: pagina de cautare e "
                 "schelet Nosto hidratat client-side, HTML independent de query "
                 "(24 noduri si pe termen inexistent) — cautare exclusa peste HTTP.",
        # DEAL-2 — masurat in LST-1: Magento, 197 de pagini a 24 de produse.
        # Pagina 500 da 200 cu grila GOALA.
        "listing": {
            "url": "https://www.otter.ro/reduceri",
            "page_url_template": "https://www.otter.ro/reduceri?p={n}",
            # PROD-1: 210 -> 35, acelasi plafon de TIMP ca la bergfreunde, dar cu
            # ALTA cifra, si diferenta e chiar masuratoarea. Productia (10.09):
            # 2 546 de produse in 14 minute. Paginile de aici au 24 de produse
            # (LST-1: 197 de pagini a 24), deci 2 546 / 24 ~ 106 pagini in 840 s =
            # ~7,9 s pe pagina — de 1,6 ori mai scump per pagina decat bergfreunde
            # SI de 3 ori mai sarac in produse. 60 de pagini ar fi insemnat tot
            # ~8 minute; 35 x 7,9 s ~ 4,6 min, sub pragul de 5 minute pe domeniu.
            # Randamentul e insa mic (35 x 24 = 840 de produse), si asta e cifra
            # care ar justifica o intrare mai buna pe otter intr-o runda viitoare,
            # nu un plafon mai mare.
            "max_pages": 35,
            "currency": "RON",
            "card": "li.product-item",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image": "img.product-image-photo", "image_attr": ["src"],
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
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.spartoo.ro/pantofi-ieftina.php",
            # Nicio paginare in HTML-ul brut al paginii — `p2` n-a fost cerut.
            # 144 de carduri pe pagina, cel mai mare raft al lotului.
            "max_pages": 1,
            "currency": "RON",
            "card": ".dis_zoomInfo",
            # Linkul cardului e RELATIV FARA slash initial
            # (`Helly-Hansen-GARIBALDI-V4-x15480018.php`), iar `_link_of` rezolva
            # fata de `https://{domeniu}/` — exact unde stau PDP-urile spartoo.
            "link": "a",
            "title": "span.productlist_name",
            # IMG-1a/1a2: `src` e `lazyLoader.gif`.
            "image": "img.lazyZoom",
            "image_attr": ["data-original", "src"],
            # `span.productlist_prix` contine AMBELE preturi („841,00 Lei 630,75
            # Lei"), deci nu poate fi citit ca atare — `_text_of` ar da 841630.75.
            # `s` e referinta, `span`-ul dinauntru e pretul platit.
            "price_text": "span.productlist_prix > span",
            "compare_text": "span.productlist_prix s",
            "price_parse": "eu_comma",
            # Taiat semantic (`<s>`) pe 144 din 144, dar fara nicio eticheta de
            # „30 de zile" sau „PRP" langa camp.
            "reference_kind": "nemarcat",
        },
        "notes": ("LOT3b; og:type propriu (non-standard); site-ul tolereaza dublu "
                 "slash in cale — normalizat la salvare (C3)"
                 " DEAL-D4 - axa D: `/pantofi-ieftina.php`, 144 de carduri (cel mai mare raft al lotului), pret taiat semantic (`<s>`) pe 144 din 144, fara eticheta legala. `span.productlist_prix` contine AMBELE preturi, deci se citesc nodurile dinauntru. Zero paginare in HTML-ul brut."),
    },
    "boozt.com": {
        "label": "Boozt",
        "category": "fashion",
        "channel": "haine",
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
        "channel": "haine",
        "country": "DK",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # ── STATE-2 — axa D, masurata pe dump-ul HTTP (cererea 6) ──────────
        #
        # JSON-0 gasise pagina bogata in browser (86 de produse randate
        # server-side, zero apeluri XHR de listare). Cererea 6 a verificat ca
        # HTTP-ul da EXACT aceleasi 86 de carduri (2,0 MB) — deci booztlet nu
        # cere browser si intra pe calea obisnuita.
        "listing": {
            # `/eu/en/women` e o ATERIZARE de departament (1,24 MB, ZERO carduri);
            # frunza de listare e `view-all`, luata verbatim din nav-ul paginii.
            "url": "https://www.booztlet.com/eu/en/women/view-all",
            # `max_pages: 1` e MASURATOARE: HTML-ul brut n-are `rel=next`, n-are
            # nicio ancora cu `page=`, iar in browser scroll-ul pana la capatul
            # grilei (dovedit de 65 de imagini lenese incarcate) n-a declansat
            # nicio cerere de produse. Fara `page_url_template`: garda il
            # interzice la plafon 1, tocmai ca sa nu inventam un URL nemasurat.
            "max_pages": 1,
            "currency": "EUR",
            "card": "[data-product-id]",
            "link": "a[href]",
            # Titlul complet („Part Two NadyaPW OTW - Light Jackets") sta intr-un
            # singur nod; `data-product-name` ar da doar „NadyaPW OTW", fara marca.
            "title": ".palette-product-card-description__content__brand-product-name",
            "image_attr": ["src"],
            # PRETUL: `span.palette-product-card-price__price-tag`, 86/86.
            #
            # Brief-ul cerea atributul numeric `data-cnstrc-item-price="78.000"`,
            # care trece prin parserul strict — dar el e prezent doar pe 80/86.
            # Cele SASE care-i lipsesc sunt produse REALE (Enkel Studio by PWT, cu
            # href si pret), deci calea aia ar fi pierdut tacut sase carduri.
            # `data-actual-price="78 €"` e pe 86/86, dar are „€", iar `price_attr`
            # merge prin parserul strict si ar da None. Ramane textul.
            #
            # `<s>` are ACEEASI clasa ca pretul platit, deci selectorul trebuie sa
            # numeasca si eticheta: `span...` = platit, `s...` = referinta.
            "price_text": "span.palette-product-card-price__price-tag",
            "compare_text": "s.palette-product-card-price__price-tag",
            # `us_dot`, NU `eu_comma`: preturile sunt cu PUNCT zecimal
            # („69.50 €" = 69,50 EUR). `eu_comma` ar citi 6950.0 — de 100 de ori
            # mai mult. Sigur pe tot dump-ul: valorile merg de la 9.0 la 433.3 si
            # niciuna n-are separator de mii, deci ambiguitatea „1.299" nu apare.
            "price_parse": "us_dot",
            # `nemarcat`: `<s>130 €</s>` e un pret taiat FARA nicio eticheta.
            # Cele trei potriviri de „lowest price" din pagina sunt numele unei
            # rubrici de meniu („Lowest prices", `/campaigns/women/lowest-prices`),
            # nu o eticheta de camp — lectia bergfreunde. Prezent pe 79/86; cele
            # 7 fara `<s>` sunt exact cele 7 fara reducere.
            "reference_kind": "nemarcat",
        },
        "notes": "LOT3b; outlet integral, sora boozt; aceleasi variante doar pe "
                 "colorway; EUR. STATE-2 — axa D pe `/eu/en/women/view-all`: 86 de "
                 "carduri, identic pe HTTP si in browser, deci NU cere browser. "
                 "`/eu/en/women` e aterizare, nu listare. Pret cu PUNCT zecimal "
                 "(`us_dot`), referinta din `<s>` nemarcat (79/86). `max_pages: 1` e "
                 "masuratoare: zero paginare in brut, iar scroll-ul pana la capat n-a "
                 "cerut nimic (JSON-0). Adancimea cere API-ul Constructor.io, sugerat "
                 "de atributele `data-cnstrc-*` — pista neexplorata.",
    },
    # ── LOT4 / LOT4b — beauty/parfumuri (sonde 2026-08-13) ────────────────────
    "marionnaud.ro": {
        "label": "Marionnaud",
        "category": "beauty",
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── STATE-1 — axa D prin extractor de STARE (SAP Commerce/Spartacus).
        # Raftul e in blobul `application/json`, nu in DOM (v. `marionnaud_json`).
        "listing": {
            "url": "https://www.marionnaud.ro/promotii/c/F",
            # `max_pages: 1` si FARA template, MASURAT live (STATE-1 B3): starea
            # anunta `totalPages: 42`, dar parametrul `?page=` e IGNORAT
            # server-side — si `?page=1`, si `?page=500` intorc `currentPage: 0`
            # si exact acelasi set de 20 de produse. Restul celor 42 de pagini se
            # aduc client-side, dupa hidratare, prin API-ul Spartacus. Un template
            # `?page={n}` ar cere deci 41 de pagini identice cu prima si le-ar
            # taia abia garda de clamp, dupa ce le-a descarcat pe toate.
            "max_pages": 1,
            "currency": "RON",
            "state_extractor": "marionnaud_json",
            # FARA referinta, masurat pe 20/20: `otherPrices`, `otherPricesMap` si
            # `priceRange` sunt goale, iar `savePrice` e sirul vid. `promotions`
            # da un PROCENT, nu un pret anterior -> axa D doar pe R2.
            "reference_kind": "nemarcat",
        },
        "notes": ("LOT4"
                 " DEAL-D4 - RAMAS IN AFARA axei D: STATE. In DOM exista doar 15 elemente cu link si pret, si alea sunt bara de NAVIGATIE; raftul e in blobul de stare (`searchModel.products`, 20 pe pagina, 834 in total). Candidat pentru un `state_extractor`, nu pentru selectori CSS."
                 " STATE-1 - INTRAT pe axa D prin `marionnaud_json`. Pretul se ia"
                 " din `price.value` (NUMERIC), nu din `price.formattedValue`"
                 " (sir cu virgula), iar `url` e RELATIV si se rezolva la radacina."
                 " Paginarea din stare e ZERO-INDEXATA (`currentPage: 0`,"
                 " `totalPages: 42`), dar parametrul `?page=` e IGNORAT"
                 " server-side: masurat, `?page=1` si `?page=500` dau amandoua"
                 " `currentPage: 0` si acelasi set de 20 -> `max_pages: 1`, fara"
                 " template."),
    },
    "notino.ro": {
        "label": "Notino",
        "category": "beauty",
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "impersonate": "firefox135",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            # Campanie, 28 de produse. Treapta de impersonate vine din `impersonate`
            # de mai sus (firefox135), aplicata de poarta.
            "url": "https://www.notino.ro/shopping-days/",
            # Nicio paginare in HTML-ul brut.
            "max_pages": 1,
            "currency": "RON",
            "card": "[data-testid='product-container']",
            "link": "a",
            "title": "[data-testid='product-card-name']",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src", "srcset"],
            # `<span data-testid="price-component">2.953</span>` +
            # `<span data-testid="currency-component">RON</span>`.
            "price_text": "[data-testid='product-price']",
            # FARA `compare_*`, DELIBERAT. Al doilea pret de pe card e
            # `2.362 RON folosind codul shoppingdays` — un CUPON intr-un nod
            # separat, nu o referinta taiata. Citit ca referinta, ar produce
            # „reduceri" care nu exista fara cod. Raftul asta e deci R2-only.
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
        },
        "notes": ("LOT4; deschis pe treapta din campul impersonate"
                 " DEAL-D4 - axa D: `/shopping-days/`, 28 de carduri, o pagina. FARA referinta, deliberat: al doilea pret de pe card („2.362 RON folosind codul shoppingdays”) e un CUPON intr-un nod separat, nu un pret taiat - raftul e R2-only."),
    },
    "parfumdreams.de": {
        "label": "Parfumdreams",
        "category": "beauty",
        "channel": "beauty",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.parfumdreams.de/Angebote",
            "page_url_template": "https://www.parfumdreams.de/Angebote?p={n}",
            # `p1 ∩ p2 = 0` din 30 (paginare reala), iar `?p=500` raspunde 200 cu
            # GRILA GOALA — oprirea pe care scannerul o cunoaste din LST-1b.
            # 449 de produse anuntate.
            "max_pages": 15,
            "currency": "EUR",
            # Tailwind pur: nicio clasa nu numeste lucrul, toate descriu aspectul.
            # Singura ancora stabila de card e atributul.
            "card": "div[data-product-id]",
            "link": "a.group",
            "title": "p.font-bold.break-words",
            # IMG-1a/1a2: cardul are si `/images/Tip.svg` si `/images/ratingstars.svg`
            # ca `<img>`, deci selectorul TREBUIE sa fie cel al pozei produsului.
            "image": "img.card-hover",
            "image_attr": ["src", "srcset"],
            # Pretul PUBLIC. Nodul vecin, `span.hidden` cu variante Tailwind
            # `premium:`, poarta pretul de MEMBRU (69,26 € fata de 76,95 €) — un
            # vizitator obisnuit nu-l plateste, deci citit ca pret ar inventa o
            # reducere.
            "price_text": "span.inline",
            # UVP. `:not(.article-description)` NU e cosmetic: fara el,
            # `select_one` ia `p.article-description.text-xs.text-darkgraystrong`
            # („Eau de Parfum Spray nachfüllbar"), care il PRECEDE in document.
            "compare_text": "p.text-darkgraystrong.text-xs:not(.article-description)",
            "price_parse": "eu_comma",
            # UVP pe 30 din 30. Omnibus-ul EXISTA, dar doar in `data-props` JSON al
            # ancorei (`LowestPriceLast30DaysTC_f`), iar `price_attr` cere un
            # atribut strict numeric — necitibil pe calea actuala.
            "reference_kind": "prp",
            # NU se citeste Grundpreis-ul („100 ml (769,50 € / 1 l)"), nod separat.
        },
        "notes": ("LOT4; pret in priceSpecification — clientul fix-ului de moneda; "
                 "Grundpreis inchis manual: pretul e al flaconului"
                 " DEAL-D4 - axa D: `/Angebote`, 30 de carduri, 449 de produse, oprire pe grila goala. Referinta e UVP (PRP) pe 30 din 30; Omnibus-ul exista dar doar in `data-props` JSON, necitibil pe calea actuala. Nodul vecin al pretului e pretul de MEMBRU (`premium:`), care nu trebuie citit."),
    },
    "douglas.ro": {
        "label": "Douglas",
        "category": "beauty",
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        "listing": {
            "url": "https://www.douglas.ro/ro/c/reduceri/05",
            "page_url_template": "https://www.douglas.ro/ro/c/reduceri/05?page={n}",
            # PLAFON DUR, nu buget. `p1 ∩ p2 = 0` din 48 (paginare reala), dar
            # `?page=500` intoarce PAGINA 1 — `p1 ∩ plast = 48 din 48`. Nu exista
            # nicio semnatura de oprire: nici 404, nici grila goala. Clamp-ul
            # scannerului (`linkuri_pagina <= linkuri_vazute`) o prinde abia dupa
            # ce a re-citit o pagina intreaga, deci plafonul e singura oprire
            # care se poate declara aici.
            "max_pages": 20,
            "currency": "RON",
            # `data-testid` stabile peste hash-urile de build.
            "card": "[data-testid='product-tile']",
            "link": "a[data-testid='main-link']",
            "title": "span[id^='product-tile-image-title']",
            # IMG-1a/1a2: placile de sub pliu sunt LENESE (Swiper) — `src` gol,
            # poza in `data-lazy-src`. Fara el, 15 din 35 de carduri ieseau fara
            # imagine.
            "image": "img.image",
            "image_attr": ["src", "data-lazy-src", "srcset", "data-lazy-srcset"],
            # DOI `data-testid` pe fiecare latura: 13 din 48 de carduri folosesc
            # varianta `-color` a campului, iar Omnibus-ul lor e taiat
            # (`-strikethrough`). Cu unul singur, descriptorul citea 35 din 48.
            "price_text": ("[data-testid='price-type-discount'], "
                           "[data-testid='price-type-discount-color']"),
            # Omnibus ETICHETAT, verbatim „Cel mai mic preț din ultimele 30 de
            # zile 429,00 RON", pe 47 din 48. Coexista cu „PRP 798,00 RON"
            # (`price-type-original`), tot pe 47.
            "compare_text": ("[data-testid='price-type-lowest'], "
                             "[data-testid='price-type-lowest-strikethrough']"),
            "price_parse": "eu_comma",
            "reference_kind": "min30",
            # NU se citeste `[data-testid='price-base-unit']`: acela e pretul pe
            # UNITATE („80 ml (5,66 RON / 1 ml)"), nu al produsului — aceeasi
            # capcana ca `Grundpreis` la parfumdreams, dar aici pe listare.
        },
        "notes": ("LOT4b; o pagina per volum, fara variante — fiecare volum e sursa "
                 "proprie; incadrarea Grup 3 din descoperire corectata: esec de "
                 "ordonare, nu de site"
                 " DEAL-D4 - axa D: `/ro/c/reduceri/05`, 48 de carduri, Omnibus etichetat pe 47 din 48 („Cel mai mic preț din ultimele 30 de zile”), langa PRP. `max_pages` e PLAFON DUR: `?page=500` intoarce pagina 1, deci nu exista nicio semnatura de oprire. 13 din 48 de carduri folosesc varianta `-color` a campurilor, iar placile de sub pliu au poza in `data-lazy-src`."),
    },
    "sephora.ro": {
        "label": "Sephora",
        "category": "beauty",
        "channel": "beauty",
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
        "channel": "beauty",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "validated",
        "overrides": {"price_selector": '[class*="ProductBuySection__container"] > [itemprop="price"]'},
        "notes": "G4/G4b: interstitiu JS pe 202 trecut de browser; paginile cu "
                 "variante de culoare au N itemprop=price — selectorul tinteste "
                 "containerul principal (clasele au sufixe generate, ancorare pe "
                 "partea stabila); meta content; BR-1b: selector copil-direct — "
                 "unic pe pagina (masurat 3/3 la BR-1), imun la reordonari. "
                 "BRW-0b/BRW-1 - intra pe axa D prin BROWSER (`via: \"browser\"`), "
                 "dar PAGINA-UNICA: home-ul randat declara EXACT o candidata de "
                 "reduceri (`/categorys/723566/`), iar ea n-are NICIO forma de "
                 "paginare - zero `rel=next`, zero `?page=`, zero `/page/`, zero "
                 "`?p=`; singurul jeton e un „load more\", si scannerul nu simuleaza "
                 "click. Deci `max_pages: 1` si 50 de produse pe scan. Referinta e "
                 "`.Price__priceOld`, fara eticheta legala -> `nemarcat` (28/50). "
                 "CAPCANA de parser: zecimala e PUNCT (`94.93 lei`), deci `us_dot` - "
                 "pe `eu_comma` ar fi iesit 9493,0. Regula sufixelor generate de la "
                 "BR-1b se aplica identic la selectorii de listare. HTTP nu e "
                 "alternativa: poarta a intors `None`.",
        # ── BRW-1 — din sonda BRW-0b §3.2 ──────────────────────────────────────
        "listing": {
            "via": "browser",
            "url": "https://makeup.ro/categorys/723566/",
            # `max_pages: 1` fara `page_url_template`: garda de descriptor cere
            # sablonul EXACT cand bucla chiar l-ar citi (de la pagina 2 in sus).
            # Domeniul n-are nicio paginare masurata, deci un sablon aici ar fi un
            # URL INVENTAT pus doar ca sa treaca o garda.
            "max_pages": 1,
            "currency": "RON",
            # Clasele poarta sufixe generate (`shop_808tam_ouxm47`), care se
            # schimba la fiecare build al vitrinei — ancorarea e pe partea stabila,
            # aceeasi regula ca la `overrides.price_selector` de mai sus.
            "card": ".ProductCard__card",
            "link": "a[href^='/product/']",
            "title": ".ProductCard__title",
            "price_text": ".Price__priceCurrent",
            "compare_text": ".Price__priceOld",
            # PUNCT zecimal (`94.93 lei`), nu virgula: al treilea consumator al
            # treptei dupa direct-running si brickdepot. Pe `eu_comma` ar fi iesit
            # 9493,0 — eroarea de 100x care arata perfect plauzibil intr-un feed.
            "price_parse": "us_dot",
            "reference_kind": "nemarcat",
        },
    },
    "hhv.de": {
        "label": "HHV",
        "category": "fashion",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "ro_confirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4/G4b: reset de conexiune pe headless; jsonld curat headed; "
                 "marimile absente din date — se urmareste produsul; pquid taiat "
                 "de canonical. LST-D8: pe HTTP, nav-ul VINE (fragmentele "
                 "`turbo-frame` de la /header/level raspund 200 cu antetul "
                 "`Turbo-Frame`), dar listarea de sale intoarce o provocare JS "
                 "proprie de 1 934 de octeti — vezi `block_markers`. Ramane pe "
                 "browser; axa D nu e posibila pe HTTP.",
        # LST-D8 §5 — provocarea de mai sus trecea de `classify` ca `OK`: corpul
        # e de 1 934 de octeti (sub pragul generic de 40 000) dar nu poarta NICIUN
        # marker generic, deci ajungea la extractor ca HTML valid si iesea
        # `no_product_data` -> 422 („n-am putut extrage datele", care acuza
        # parserul nostru) in loc de 502 („magazinul a blocat cererea").
        #
        # `hhv-js-ch` e verbatim din tabloul de siruri al provocarii, alaturi de
        # `cookie`, `location`, `reload` si `; path=/;` — numele propriu al
        # mecanismului, deci nu se poate ciocni cu proza unei pagini bune, spre
        # deosebire de contraexemplul „entschuldigung" de la AMZ-0. Lowercase
        # DELIBERAT: `classify` compara markerii cu `body.lower()`.
        "overrides": {"block_markers": ("hhv-js-ch",)},
    },
    "noriel.ro": {
        "label": "Noriel",
        "category": "jucarii",
        "channel": "jucarii",
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
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["src"],
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
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "LOT5; aceeasi forma Omnibus: platitul in date, taiatul in DOM "
                 "(has-discount + raw_price); capcana caruselului comun — "
                 "regular-price identic pe pagini diferite e componenta "
                 "partajata, nu pretul paginii",
        # DEAL-2 — masurat la LST-3 (dump-uri `scripts/diagnostics/dumps_lst3/`).
        # PrestaShop: pagina de reduceri e controllerul standard `prices-drop`, iar
        # `/outlet` — conventia incercata prima — da 404 prin `controller=404`.
        # URL-ul canonic s-a obtinut din navigatia PROPRIE a paginii de 404, nu prin
        # ghicit: `index.php?controller=prices-drop` redirectioneaza la
        # `/ro/reduceri-de-pret` (200), iar `<body>` poarta clasa `page-prices-drop`.
        # Total anuntat verbatim: „Sunt 269 produse", 20 pe pagina => 14 pagini reale.
        # Paginarea e masurata pe ambele capete: `rel=next` pe p1 arata verbatim
        # `https://regatuljocurilor.ro/ro/reduceri-de-pret?page=2`, iar p1 si p2 sunt
        # DISJUNCTE (20 + 20, intersectie 0 pe `data-id-product`) — deci paginarea
        # chiar serveste produse noi, nu re-randeaza aceeasi grila.
        "listing": {
            "url": "https://regatuljocurilor.ro/ro/reduceri-de-pret",
            "page_url_template": "https://regatuljocurilor.ro/ro/reduceri-de-pret?page={n}",
            # DERIVAT, nu citat: 14 pagini masurate plus marja, conventia otter.
            "max_pages": 20,
            # Din COD: langa suma scrie „RON", dar moneda nu se citeste din text.
            "currency": "RON",
            # Scoparea pe `#js-product-list` NU e decorativa: in afara grilei stau 9
            # `.product-item` (carusel de recomandari), fiecare cu `.price` propriu.
            # A doua plasa e chiar numele clasei — grila foloseste
            # `.js-product-miniature`, caruselul `.product-item`, deci selectorul
            # scopat da 20 si prinde ZERO carduri de carusel (verificat pe dump).
            # Asta e a doua aparitie a capcanei pe domeniu, dupa cea din `notes`.
            "card": "#js-product-list .js-product-miniature",
            # IMG-1a/1a2: unde sta poza pe acest domeniu.
            "image_attr": ["data-src"],
            # Ancora de titlu e si ancora de produs; `a.product-thumbnail` din acelasi
            # card duce la acelasi PDP, deci alegerea e indiferenta — o pastram pe cea
            # care da si textul, ca `title` sa nu tinteasca alt nod decat `link`.
            "link": "h3.product-title a",
            "title": "h3.product-title a",
            # Pe TEXT, nu pe atribut: cardul n-are nici `content=`, nici `data-*price*`
            # (verificat pe toata grila). Forma e „291,60\xa0RON", cu NBSP intre suma
            # si moneda — `_pret_eu_comma` il digera deja, e chiar cazul noriel pinuit
            # in docstringul lui.
            "price_text": ".price",
            "compare_text": ".regular-price",
            "price_parse": "eu_comma",
            # Niciun label legal pe listare: „Omnibus", „30 de zile", „PRP" si „pret
            # recomandat" apar de 0 ori in textul vizibil al ambelor pagini.
            "reference_kind": "nemarcat",
            # DOUA ramuri deliberat NEDECLARATE, ca sa nu para omisiuni:
            #
            # (1) Fara `stock_attr`. Listarea CHIAR contine produse epuizate — `.stock`
            #     poarta „Nu este momentan in stoc" / „Ultimele produse in stoc" — dar
            #     semnalul e TEXT, iar schema n-are decat varianta pe atribut. Fara
            #     camp, `_in_stoc` intoarce True pe tot, deci epuizatele se ingereaza.
            #     Sunt inerte cat timp pretul e valid: intra in memoria de preturi ca
            #     orice card, si pot genera o alerta pentru ceva necumparabil. Se
            #     rezolva cand schema capata `stock_text`, nu prin cod aici.
            #
            # (2) Fara ancorare pe `.discount-percentage`. Insigna e prezenta pe
            #     majoritatea cardurilor dar LIPSESTE pe unele care AU totusi
            #     `.regular-price` (masurat pe cardul 4 al dump-ului p1), deci „e
            #     redus?" nu se poate citi de pe ea.
            #
            # RAMURA NEMASURATA, asumata: pe ambele pagini masurate toate cele 20+20
            # de carduri au SI `.price` SI `.regular-price` — pagina de prices-drop
            # nu serveste, prin definitie, carduri la pret plin. Daca vreodata apare
            # unul, `_pret_of` intoarce None pe compare (nod absent -> `.get`-ul de la
            # `select_one`, fara exceptie) si cardul ramane valid cu pretul lui.
        },
        # SEARCH-1 — masurat la SEARCH-0: 20 de carduri la `catan`, toate cu pret,
        # iar termenul inexistent da 0 noduri-card pe 200. Hidden-urile din URL
        # (`controller`, `orderby`, `orderway`) sunt cele din <form>-ul real al
        # magazinului, nu conventii PrestaShop presupuse.
        #
        # `compare_text` ramane declarat desi pe pagina de cautare a dat 0 noduri:
        # acolo produsele sunt majoritar la pret intreg, deci absenta lui e normala
        # si `compare_at` iese None. Cand exista o reducere, selectorul e cel corect
        # — e acelasi nod pe care listarea il citeste de 20 din 20 de ori.
        "search": {
            "kind": "descriptor",
            "url_template": "https://regatuljocurilor.ro/ro/cautare?controller=search&orderby=position&orderway=desc&search_query={q}",
            "price_text": ".price",
            "compare_text": ".regular-price",
            "price_parse": "eu_comma",
        },
    },
    "jucarii-vorbarete.ro": {
        "label": "Jucarii Vorbarete",
        "category": "jucarii",
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "shopify",
        "status": "validated",
        "currency": "RON",
        "search": {"kind": "shopify"},
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
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D4, din dump-urile LST-D4 (8 septembrie) ──────────────────
        # Al DOILEA descriptor pe forma `entries`, dupa eMAG. Magazinul n-are URL
        # agregat de reduceri: `/oferte-speciale` e un HUB (titlu si `h1` de oferte,
        # zero produse, zero blob de stare) care isi expune insa cele 17 FATETE
        # `/<categorie>/produse-cu:reducere`. URL-urile de mai jos sunt verbatim din
        # ancorele hub-ului.
        #
        # Ca forma, `entries` a fost DOVEDITA, nu presupusa: doua fatete au fost
        # cerute la LST-D4, iar selectorul primei aduce 60 de carduri si pe a doua,
        # cu zero URL-uri comune intre ele — un singur set de selectori acopera tot.
        "listing": {
            # PAGINAREA E INFIXATA — numarul sta la MIJLOC, nu la coada:
            # `<a class="pagenext circle shadow"
            #     href="/carucioare-copii/carucioare-2-in-1/p2/produse-cu:reducere">`.
            # Confirmata live la DEAL-D4: `p2` da 60 de carduri, ZERO comune cu `p1`.
            #
            # De ce plafonul descriptorului e 1 si doar DOUA intrari pagineaza:
            # o pagina PESTE adancimea reala a fatetei nu da 404 si nici grila
            # goala — magazinul ARUNCA fateta si serveste categoria intreaga.
            # Masurat pe `p500`: raspuns 200, 60 de carduri,
            # `canonical` devine `/carucioare-copii/carucioare-2-in-1/` (fara
            # `produse-cu:reducere`), `h1` pierde „Cu Reducere", iar numarul de
            # produse sare de la 201 la 520. Cardurile alea sunt produse
            # NEREDUSE, iar scannerul nu le poate deosebi: clamp-ul lui cere ca
            # pagina sa fie SUBMULTIME a celor vazute, si aici 20 din 60 sunt noi.
            # Deci pagineaza doar fatetele carora li s-a MASURAT adancimea.
            "max_pages": 1,
            "entries": [
                {"url": "https://www.nichiduta.ro/carucioare-copii/carucioare-3-in-1/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/carucioare-copii/carucioare-2-in-1/produse-cu:reducere",
                 "page_url_template": "https://www.nichiduta.ro/carucioare-copii/carucioare-2-in-1/p{n}/produse-cu:reducere",
                 "max_pages": 4},
                {"url": "https://www.nichiduta.ro/carucioare-copii/carucioare-standard/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/carucioare-copii/carucioare-sport/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/scaune-auto-copii/scaune-cu-isofix/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/camera-copilului/tarcuri-copii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/camera-copilului/sisteme-de-siguranta-copii/produse-cu:reducere/tip-produs-19:bariere-protectie-pat-nic_140,porti-de-siguranta-nic_138,protectii"},
                {"url": "https://www.nichiduta.ro/la-plimbare/triciclete-copii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/la-plimbare/trotinete-copii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/jucarii-de-exterior/tobogane-copii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/jucarii-de-exterior/casute-pentru-copii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/jucarii-de-exterior/gonflabile-si-bazine/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/jucarii-de-exterior/accesorii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/alimentatie/suzete-si-accesorii/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/articole-pentru-gravide/pompe-de-san/produse-cu:reducere"},
                {"url": "https://www.nichiduta.ro/articole-pentru-gravide/perne-de-alaptat/produse-cu:reducere",
                 "page_url_template": "https://www.nichiduta.ro/articole-pentru-gravide/perne-de-alaptat/p{n}/produse-cu:reducere",
                 "max_pages": 3},
                {"url": "https://www.nichiduta.ro/articole-pentru-gravide/recipiente-pentru-lapte/produse-cu:reducere"},
            ],
            "currency": "RON",
            "card": ".listing_product_item",
            # Ancorele cardului sunt RELATIVE FARA slash initial
            # (`href="carucior-…-427420"`), iar pagina poarta
            # `<base href="https://www.nichiduta.ro/" />`; canonicul unui produs e
            # la RADACINA. `_link_of` rezolva fata de `https://{domeniu}/`, adica
            # exact ce prescrie `<base>` — o rezolvare fata de URL-ul PAGINII ar da
            # 404 (masurat la LST-D4, doua cereri arse asa).
            "link": "a.h-prod-name",
            "title": "span.prod_name",
            # IMG-1a/1a2: `src` e `img/new/pix.gif`.
            "image": "img.load_image",
            "image_attr": ["data-src", "src"],
            # `<div class="prices">899<sup>lei</sup><br/><span>503 <sup>lei</sup>
            # </span></div>` — `.prices` intreg ar da „899 lei 503 lei" (899503.0).
            "price_text": ".prices span",
            # FARA `compare_text`, si nu din uitare: pretul taiat (PRP, per LOT5b)
            # e TEXT DIRECT al lui `div.prices`, fara niciun nod propriu, deci nu
            # exista selector CSS care sa-l izoleze. Reducerea e afisata ca badge
            # (`<li class="discount circle shadow">-44 %</li>`), nu ca pret.
            # Raftul asta e deci R2-only.
            "price_parse": "eu_comma",
            "reference_kind": "nemarcat",
        },
        "notes": ("LOT5b; pret dublu-sursat (ld+json + div.priceNEW), platitul in "
                 "date; ATENTIE la citirea marjelor: referinta taiata e PRP "
                 "(Pretul Recomandat de Producator, verbatim din tooltip), NU "
                 "minimul pe 30 de zile — procentele de reducere sunt fata de PRP DEAL-D3 - `/oferte-speciale` e un HUB: are titlu si `h1` de "
                 "oferte, dar textul vizibil e meniul de categorii, zero produse, "
                 "zero stare. Isi expune insa fatetele: 17 ancore "
                 "`/<categorie>/produse-cu:reducere`, deci candidat pentru forma "
                 "`entries` (al doilea caz dupa eMAG). Niciuna dintre cele 17 n-a "
                 "fost ceruta inca."
                 " DEAL-D4 - cele 17 fatete au intrat ca `entries` (al doilea caz dupa eMAG), dovedite: selectorul unei fatete aduce 60 de carduri si pe alta, cu zero URL-uri comune. Paginarea e INFIXATA (`/<cat>/p2/produse-cu:reducere`) si confirmata live, dar pagineaza doar cele DOUA fatete carora li s-a masurat adancimea: o pagina peste adancimea reala nu da 404, ci ARUNCA fateta si serveste categoria intreaga (masurat pe p500: canonical fara `produse-cu:reducere`, 520 de produse in loc de 201). Fara `compare_text`: pretul taiat e text direct al lui `div.prices`, fara nod propriu."),
    },
    "brickdepot.ro": {
        "label": "BrickDepot",
        "category": "jucarii",
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D3, din dump-urile LST-D3 (7 septembrie) ──────────────────
        "listing": {
            # Intrarea prezumata `/promotii/` s-a dovedit un HUB (200, zero
            # carduri); listarea reala e landing page-ul de campanie gasit in
            # navigatia home-ului, cu textul „Explorează".
            #
            # ATENTIE, e o CAMPANIE: „Până la 40% reducere la o selecție de…".
            # Poate expira. Daca un scan da 0 carduri, intrarea se RE-MASOARA din
            # navigatia home-ului; nu se ghiceste un id nou.
            "url": ("https://brickdepot.ro/index.php?main_page=landing_page&id=250"
                    "&page=P%C3%A2n%C4%83-la-40%25-reducere-la-o-selec%C8%9Bie-d"),
            # Pagina anunta verbatim „91 produse" si afiseaza 91: o singura pagina.
            "max_pages": 1,
            "currency": "RON",
            "card": ".attribute-item",
            # `<a class="name" href="https://brickdepot.ro/lego-super-mario-c-120/
            #  mario-kart-luigi-și-mach-8-p-30375.html"> Mario Kart™ – Luigi și Mach 8</a>`
            # Acelasi nod da si linkul si titlul. Href-ul are un spatiu NESEPARATOR
            # (U+00A0) dupa slash — codificat `%20` de garda DEAL-D3 din
            # `listing_scanner._fara_spatii`.
            "link": "a.name",
            "title": "a.name",
            # LIMITA DECLARATA: imaginile ies GOALE, 0/91. `src` e o cale relativa
            # FARA slash initial (`bmz_cache/f/fd86af86….image.280x280.jpg`), iar
            # `normalizeaza_imagine` refuza deliberat asa ceva: fara o baza masurata
            # n-are cum s-o rezolve, iar a ghici ar produce 404-uri tacute. Nu e o
            # alegere proasta de selector — e o limita a normalizatorului, si
            # descriptorul intra ASA, cu deal-uri fara poza.
            "image_attr": ["src"],
            # Perechea zen-cart: `<span class="productSpecialPrice">569.99Lei</span>`
            # (platit) si `<span class="normalprice">949.99Lei</span>` (de baza).
            "price_text": "span.productSpecialPrice",
            "compare_text": "span.normalprice",
            # `us_dot` pe un magazin ROMANESC, si tocmai de aia se declara: „569.99Lei"
            # are punct zecimal si niciun separator de mii. `_pret_eu_comma` ar da
            # 56999.0. Din sir cele doua forme nu se pot deosebi — doar magazinul stie.
            "price_parse": "us_dot",
            # `nemarcat`: `normalprice` e pretul de baza al magazinului, nu o
            # referinta legala. Zero „PRP", zero „30 de zile" pe pagina.
            "reference_kind": "nemarcat",
        },
        "notes": "LOT5b; ld+json cu caractere de control — clientul treptei laxe; "
                 "pagina cu ghilimea dublata in sursa site-ului ramane neparsabila "
                 "(refresh pastreaza pretul); spec de selector de rezerva in jurnal; "
                 "DEAL-D3 — axa D pe un LANDING PAGE de campanie (`main_page="
                 "landing_page&id=250`, `Pana la 40% reducere...`), 91 de produse "
                 "anuntate si 91 afisate; `/promotii/` s-a dovedit un hub gol. "
                 "Pretul e zecimal cu PUNCT pe un magazin romanesc (`569.99Lei`), "
                 "deci `us_dot` — `eu_comma` ar da 56999.0. Imaginile NU se pot "
                 "extrage (0/91): `src` e cale relativa fara slash initial "
                 "(`bmz_cache/…`), pe care normalizatorul o refuza deliberat. "
                 "Ancora cardului are un spatiu NESEPARATOR (U+00A0) in href, "
                 "codificat `%20` de garda DEAL-D3.",
    },

    # ── G4-V0b — valul zero de browser ────────────────────────────────────────
    # Sonda G4-V0 a masurat opt tinte de Grup 4 prin patchright + Chrome real.
    # Rezultatul central: ZERO challenge INTERACTIV pe toate opt — 403-urile pe care
    # le vedea poarta HTTP nu erau ziduri anti-bot care cer verificare umana, ci doar
    # „lipseste un browser real". Intra aici doar cele pe care sonda le-a dovedit
    # VIABILE, iar `method: "browser"` doar unde HTTP-ul chiar NU raspunde: harness-ul
    # costa un Chromium per pagina si nu se pune pe domenii care merg pe curl.
    "bb-shop.ro": {
        "label": "B&B SHOP",
        "category": "bijuterii-ceasuri",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4-V0b; INLOCUIESTE bbcollection.ro (parcat la G2F-8) — acelasi "
                 "comerciant, dovedit pe TREI ancore: codul `35000513`, id-ul intern "
                 "`175484` (canonical bbcollection `...-35000513-pb175484.html` -> "
                 "bb-shop `...-175484.html`) si aceeasi pereche de preturi 295,00 -> "
                 "206,50 (-30%). Pe HTTP PDP-ul da 403 cu `cf-mitigated: challenge` "
                 "(corp 6.204 octeti, pe profilul de productie); in Chrome real trece TACIT, "
                 "fara nicio interactiune, in 2,62s. DOM-ul randat (254.605 octeti) "
                 "poarta ld+json `Product` curat: Offer [price \"206.5\", "
                 "priceCurrency RON, availability `OnlineOnly` — NU InStock, dar "
                 "genericul il citeste ca in_stock=True, itemCondition NewCondition]. "
                 "Genericul extrage FARA override (method jsonld pe HTML-ul randat). "
                 "Pentru axa D: pretul VECHI e fragmentat in markup (`295 , 00 lei`) "
                 "si NU e taiat semantic (zero <del>/<s>/<strike>), Omnibus NEMARCAT "
                 "(tiparul elefant.ro) — dar exista DOUA surse masinabile, selectorul "
                 "`.old .a-price-whole` + `.a-price-fraction` si starea "
                 "`var date_js = {\"arti\":175484,\"art\":\"35000513\","
                 "\"pret_inmag\":\"295.00\",...}`. CAPCANA la verificare: `295` da "
                 "fals pozitiv in datele de path SVG ale paginii. PDP "
                 "`/bijuterie-<slug>-<id>.html`. headless NEMASURAT (sonda a rulat "
                 "tot headed) — optimizare ieftina pentru un val ulterior.",
    },
    "conrad.com": {
        "label": "Conrad",
        "category": "electronice",
        "channel": "electronice",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4-V0b; Grup 4 la G2B-1b (403 `cf-mitigated: challenge` si pe home, "
                 "si pe listare, pe profilul de productie — zero date server-side). In Chrome "
                 "real: 200 in 4,48s, DOM randat de 1.156.723 octeti cu ld+json "
                 "`Product`. ATENTIE, pretul NU e in `offers.price` — acela e `null`; "
                 "sta in `offers.priceSpecification.price` = 36.97 / EUR, iar genericul "
                 "il citeste corect (method jsonld, FARA override). CAPCANA MAJORA: "
                 "`\"valueAddedTaxIncluded\": false` — pretul e NET, fara TVA. O "
                 "comparatie directa cu preturi brute romanesti subestimeaza "
                 "sistematic; orice calcul de marja trebuie sa adauge TVA intai. Offer "
                 "are cheile [@type, availability, priceSpecification, seller, "
                 "shippingDetails, url]; `hasVariant` EXISTA dar e GOL (n=0), deci nu e "
                 "sursa de variante. Produsul poarta sku/gtin13/mpn (1934286 / "
                 "5099206080263 / 910-005470) — utile la incrucisare. Listarea "
                 "`/en/promotions/sale.html` se randeaza (828.541 octeti, preturi EUR "
                 "vizibile) dar are ZERO ld+json — materie pentru axa D, val ULTERIOR. "
                 "PDP `/en/p/<slug>-<id>.html`. LIVRAREA IN RO nu s-a masurat: "
                 "`unconfirmed` pana la verdictul de checkout al lui David (ar fi prima "
                 "intrare care nu e ro_confirmed/ro_storefront). headless NEMASURAT. "
                 "BRW-0c/DEAL-D9 - listarea de sale (`/en/promotions/sale.html`) e "
                 "intr-adevar numai caruseluri (12 blocuri `productplacement`, 1.648 "
                 "aparitii `cmsReco`), deci verdictul FARA_LISTARE de la BRW-0 era "
                 "corect PENTRU PAGINA ACEEA si gresit pentru domeniu: CTA-urile "
                 "caruselurilor („More X offers\") duc la pagini cu filtru de reducere, "
                 "si exista EXACT UN flag in tot documentul - "
                 "`tfo_flags=priceReducedProduct`, 38 de aparitii. Pe forma "
                 "`search.html?categoryId=<t>&tfo_flags=priceReducedProduct` ies 90 de "
                 "carduri, IDENTIC pe browser si pe HTTP (3,3 MB randat vs 2,6 MB HTTP, "
                 "90 = 90) - regula G4-V4b inca o data: viabil prin browser NU inseamna "
                 "are nevoie de browser. De aici asimetria de mai jos.",
        # ── DEAL-D9 — PRIMUL domeniu cu axele DEZLIPITE ────────────────────────
        # Axa L ramane pe BROWSER (`method: "browser"`, `headed: True`): PDP-ul da
        # 403 `cf-mitigated: challenge` pe poarta HTTP, masurat la G2B-1b.
        # Axa D merge pe HTTP fiindca DESCRIPTORUL n-o cere altfel — si asta e o
        # alegere, nu o consecinta structurala. Formularea de dinainte („scannerul
        # foloseste DOAR `_fetch_shop_url_guarded`") a fost adevarata pana la
        # BRW-1, care i-a adaugat o a doua cale de fetch; ce ramane valabil, si e
        # partea care conteaza, e ca ramura NU se alege dupa `method`, ci dupa
        # cheia `via` a descriptorului de listare. conrad e chiar contraexemplul
        # care tine granita: `method: "browser"` pentru PDP, HTTP pentru listare,
        # fiindca listarea lui a raspuns 200 pe HTTP acolo unde PDP-ul da 403.
        # Vezi `test_brw1_in_registru`, care apara granita prin comportament.
        "listing": {
            # Forma `search.html` cu filtrul de reducere. NU `/en/o/<categorie>` cu
            # acelasi `tfo_flags`: sonda a cerut-o ca a doua intrare
            # (`/en/o/multimeters-1101010.html?tfo_flags=...`) si a primit o pagina
            # reala (200, titlu real, 1,28 MB) cu UN SINGUR card. Filtrul tine pe
            # cautare, nu pe categorie.
            "url": ("https://www.conrad.com/en/search.html?categoryId=t07"
                    "&tfo_flags=priceReducedProduct"),
            # Gazda e cea PUBLICA, si asta e o corectie, nu o transcriere:
            # href-urile de paginare din pagina scurg un host intern
            # (`com-storefront-intern-https.prod.tds-p.com`, 111 aparitii), pe care
            # allow-list-ul de destinatie il respinge pe drept. Sablonul se
            # re-ancoreaza pe `www.conrad.com` (masuratoarea 24 din BRW-0c).
            "page_url_template": ("https://www.conrad.com/en/search.html?categoryId=t07"
                                  "&tfo_flags=priceReducedProduct&page={n}"),
            # 23 de pagini reale, plafonate la 15: 15 x 90 = 1.350 de produse pe scan,
            # destul pentru o categorie de reduceri si mai ieftin decat 2.070.
            # Paginarea e DOVEDITA, nu declarata: pagina 2 ceruta prin HTTP a dat 90
            # de carduri cu intersectie ZERO fata de pagina 1 (Jaccard 0,000 pe
            # URL-urile de produs).
            "max_pages": 15,
            "currency": "EUR",
            # Escape-ul e cel cu care controlul a dat 90/90 pe TREI corpuri (randat
            # p1, HTTP p1, HTTP p2): `group/productcard` e un nume de grup Tailwind,
            # deci slash-ul trebuie escapat in CSS.
            "card": r".group\/productcard",
            "link": r"a.after\:absolute.after\:inset-0",
            # Ancora poarta numele si in `title`, si in text. `link_title` il ia din
            # atribut; `title` de mai jos e plasa, ca un deploy care scoate atributul
            # sa nu piarda produsul (aceeasi logica ca la officeshoes, DEAL-D4).
            "title_from": "link_title",
            "title": r"a.after\:absolute.after\:inset-0",
            "image": "img[srcset]",
            # IMG-2: primul candidat din `srcset`. MASURAT: primul e `?x=100`, iar
            # `src` poarta `?x=600`. Daca miniaturile de 100 px se dovedesc prea mici
            # in interfata, inversarea listei e o singura linie.
            "image_attr": ["srcset", "src"],
            # Se citesc CELE DOUA span-uri, nu div-ul-invelis: trei div-uri parinte
            # contin AMBELE preturi ("€ 165.00 € 91.99"), iar un parser pus pe ele ar
            # lipi sumele.
            "price_text": "span.discounted-price",
            # 90/90 pe toate cele trei corpuri masurate.
            "compare_text": "span.line-through",
            # OBLIGATORIU `us_dot`: conrad scrie EUR in format US. Rulat pe parserele
            # de productie, `_pret_eu_comma("€ 91.99")` da 9199.0 si
            # `_pret_eu_comma("€ 1,079.00")` da 1.079; `_pret_us_dot` da 91.99 si
            # 1079.0. Parserul gresit ar strica preturile cu doua ordine de marime,
            # in AMBELE directii.
            "price_parse": "us_dot",
            # Pret taiat FARA eticheta legala: zero Omnibus, zero PRP, zero „de la
            # lansare" pe card.
            "reference_kind": "nemarcat",
        },
    },
    "forit.ro": {
        "label": "Forit",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D1, din sonda LST-D1 §2.6 ──────────────────────────────────
        "listing": {
            # `forit.ro` redirecteaza la `www.forit.ro`: se pune direct destinatia.
            "url": "https://www.forit.ro/resigilate/",
            # Forma e `/pN/c` — cu `/c` final, NU `/page-N` si NU `?page=N`. Nu
            # exista `rel=next`; href-urile brute (p2, p6, p7) sunt singura sursa,
            # tiparul cellini.
            "page_url_template": "https://www.forit.ro/resigilate/p{n}/c",
            # DERIVAT: „(1–60 din 413 rezultate)" / 60 pe pagina = 7 pagini, plus
            # marja. Oprirea reala e CLAMP: /p500/c redirecteaza la pagina 1.
            "max_pages": 10,
            "currency": "RON",
            "card": ".p-card",
            # `a.p-img` n-are text, dar e prima ancora si e stabila; titlul vine
            # separat, din `div.p-title`.
            "link": "a.p-img",
            "title": "div.p-title",
            "image": "img.p-img-real",
            "image_attr": ["src"],
            # Pretul e SPART intre noduri: `4.435,30` in div si „ lei" intr-un
            # `span.cur` copil. `_text_of` concateneaza, deci selectorul de div e
            # corect; o citire pe textul propriu al nodului l-ar rata.
            "price_text": "div.p-price",
            # Prezent pe 4 din 60 de carduri pe p1 — restul n-au reducere activa.
            "compare_text": "div.p-price-old",
            "price_parse": "eu_comma",
            # Zero „30 de zile", zero „pret recomandat", zero PRP pe listare.
            # Singurul „cel mai mic pret" din lot e in <title>-ul unui PDP, ca
            # marketing — deci NU eticheteaza campul (lectia bergfreunde).
            "reference_kind": "nemarcat",
            #
            # FARA `stock_attr`: `.p-stock` exista pe 60/60, dar valorile masurate
            # sunt `p-stock-ok` si `p-stock-limited` — niciuna nu inseamna
            # „epuizat".
            #
            # RESIGILATE: starea NU e in date structurate (`itemCondition` e
            # `NewCondition` si pe desigilate), ci in NUME: 57/60 de carduri au
            # „desigilat"/„resigilat" in `data-name`/`div.p-title` si in slug, deci
            # titlul o duce singur in feed.
        },
        "notes": "G4-V0b, sondat la WL-1. NU e intrare de browser, desi a intrat in "
                 "valul de browser: dump-urile HTTP ale lui WL-1 (pe profilul de "
                 "productie) dau 200 pe AMBELE PDP-uri, iar genericul extrage din ele "
                 "507,30 RON si 644,99 RON, method jsonld, fara override. Harness-ul "
                 "de browser costa un Chromium per pagina si se pune doar unde nu "
                 "exista alta cale — aici exista. (Prin browser s-a masurat oricum: "
                 "1,78s, cea mai rapida incarcare din val, aceeasi valoare.) ld+json "
                 "`Product` singur pe pagina, Offer [price \"507.30\", priceCurrency "
                 "RON, availability InStock]. Valoarea declarata e sectiunea de "
                 "RESIGILATE (`/resigilate/`, masurata la WL-1). ATENTIE la semantica "
                 "starii: `itemCondition` e `NewCondition` CHIAR SI pe produsele "
                 "desigilate — starea reala apare doar in titlu si in sku "
                 "(`AT-150-RSO- desigilata`). Pe axa L se ignora (decizia resigilate), "
                 "pe axa D se consemneaza. Componente partajate de ignorat in orice "
                 "citire pe text: `21.99 Lei` (Curier Romania) si `300 lei` (pragul de "
                 "livrare gratuita) — ld+json le ocoleste. PDP `/<slug>-bp<id>`. "
                 "DEAL-D1, din sonda LST-D1: axa D intrata pe `/resigilate/`, si aici "
                 "starea CHIAR ajunge in feed fara munca in plus — 57 din cele 60 de "
                 "carduri de pe pagina 1 au „desigilat\"/„resigilat\" chiar in titlu "
                 "(`data-name` / `div.p-title`) si in slug, deci deal-ul nu poate "
                 "parea produs nou. Cele doua componente partajate de mai sus s-au "
                 "CONFIRMAT pe dump-uri: `300 lei` e in bara de sus („Livrare gratuita "
                 "la comenzi peste 300 lei\") si apare si pe PDP-uri, `21.99 Lei` doar "
                 "pe PDP-uri — selectorii din `listing` le ocolesc pe amandoua.",
    },

    # ── WL-3 — watchlist-ul conditionat, dupa sonda corectiva WL-4 ────────────
    # Din cele trei domenii de watchlist a intrat UNUL. quickmobile.ro raspunde
    # 503 pe home si la WL-1, si la re-masuratoarea WL-4 (nu era tranzitoriu), iar
    # skinmobile.ro nu se rezolva in DNS (`Non-existent domain`, verificat pe apex
    # si pe www) — niciunul nu poate fi validat.
    "istyle.ro": {
        "label": "iSTYLE",
        "category": "electronice",
        "channel": "electronice",
        "country": "RO",
        "delivery": "ro_storefront",
        # DEAL-D1: `jsonld` -> `shopify`. Nota WL-4 spunea „Shopify, dar NU pe
        # fluxul `shopify`: enumerarea nu s-a masurat" — LST-D1 a masurat-o si e
        # deschisa, deci conditia acelei fraze s-a implinit.
        "method": "shopify",
        "status": "validated",
        # Din `/cart.js` (LST-D1 §3). Pe calea `shopify` moneda NU vine din
        # payload, o citeste extractorul din registru — camp obligatoriu.
        "currency": "RON",
        # Vine ODATA cu `method: shopify` — vezi acelasi comentariu la
        # sneakerindustry.ro. Pinuit de `test_search_shopify_pe_toate_shopify`.
        "search": {"kind": "shopify"},
        "notes": "WL-3, masurat la WL-4. ATENTIE la istoric: sonda WL-1 daduse "
                 "verdictul „custom pe stare structurata\", si era GRESIT — masurase "
                 "trei pagini `/pages/*` („Back to School\", „Modele Mac\", „Modele "
                 "Apple Watch\"), care pe Shopify sunt pagini CMS si n-au ld+json de "
                 "produs. PDP-urile reale sunt `/products/<handle>` si poarta "
                 "`Product` + `ProductGroup`; genericul extrage FARA override, "
                 "masurat 2/2 (resigilat 4.699,99 RON, normal 4.999,99 RON). "
                 "MIGRAT la DEAL-D1 pe fluxul `shopify`: randul de mai jos spunea "
                 "„enumerarea nu s-a masurat, deci ramane pe ld+json\", iar LST-D1 §3 "
                 "a masurat-o — SHOPIFY_DESCHIS, 3 cereri, 3 raspunsuri 200, "
                 "`powered-by: Shopify`, fara cookie `datadome`. Valorile: "
                 "`/products.json?limit=5` intoarce 5 produse ale caror variante au "
                 "`available` SI `compare_at_price` (5/5) — abatere de la tiparul "
                 "SHOP-1, unde `.json` nu poarta `available` si de aceea se cerea "
                 "`.js` per produs; aici enumerarea e suficienta. Pretul se "
                 "incruciseaza exact pe ACEEASI varianta (id 58085408932104, sku "
                 "`O_MVXR3HC/A_CV55VXR6LL`): `\"5349.99\"` string in enumerare, "
                 "`534999` int in bani in `/products/<handle>.js`. `/cart.js` da "
                 "`currency: RON`. Consecinta pentru `in_stock`: pe calea `shopify` "
                 "vine din `available` al variantei, deci NU mai iese None ca pe "
                 "ld+json (unde `Offer` n-are `availability` — vezi mai jos). "
                 "RESIGILATE pe axa D: starea se citeste din handle si din nume, care "
                 "au fost concordante pe 5/5 (`resigilat-<slug>` / „Resigilat: \"), in "
                 "timp ce `product_type` NU e de incredere — doua din cele cinci "
                 "produse resigilate aveau `product_type: Husa de protectie`, fara "
                 "niciun cuvant despre stare. "
                 "ISTORIC pe calea ld+json, valabil daca se revine la ea: `Offer` NU "
                 "are `availability` — cheile "
                 "masurate sunt [@type, itemCondition, price, priceCurrency, "
                 "priceValidUntil, shippingDetails, url] — deci `in_stock` iese None, "
                 "si e ONEST (ca la biciclop.eu). Valoarea declarata e sectiunea de "
                 "RESIGILATE: produsele resigilate NU sunt linkuri in home, stau in "
                 "STAREA Shopify ca handle-uri `resigilat-<slug>`, unele purtand "
                 "starea in handle (`stare-bun-63-23feb`, `stare-perfect-66-23feb`) — "
                 "de aceea WL-1 a raportat „niciun link in home\". Numele PDP-ului "
                 "prefixeaza „Resigilat: \". SEMANTICA STARII: `itemCondition` e "
                 "`NewCondition` CHIAR SI pe resigilate — nefolosibil ca semnal; pe "
                 "axa L se ignora (decizia resigilate), pe axa D se citeste din "
                 "handle/nume. Fara Omnibus si fara taiat semantic (zero "
                 "<del>/<s>/<strike>). CAPCANA la orice citire pe text: pretul "
                 "vizibil apare si concatenat cu gtin-ul (`195950609745 4 699,99 "
                 "lei`), iar `500 lei` / `200 lei` sunt praguri de livrare — ld+json "
                 "le ocoleste pe toate.",
    },

    # ── G4-V2b — reziduul Valului 2 ───────────────────────────────────────────
    # Sonda G4-V2 a masurat sase tinte cu anti-bot cunoscut sau prezumat. Intra
    # TREI. watchshop.ro ramane BLOCAT (challenge Cloudflare nerezolvat nici in
    # browser) si footlocker.ro NEDETERMINAT (randare pe client, PDP nemasurat) —
    # amandoua documentate in docs pentru Valul 3.
    #
    # solebox.com si snipes.com sunt ACELASI MAGAZIN TEHNIC: pagina solebox isi
    # incarca asset-urile de pe `api.snipes.com` / `asset.snipes.com`, ambele
    # domenii impart prefixul distinctiv de clase `hydra-` si acelasi tipar de PDP
    # `/<locale>/p/<slug>`. Dar identitatea de platforma NU implica identitate de
    # acces: snipes trece pe HTTP din prima, solebox da 403 pe toate cele trei
    # profiluri ale lantului si cere browser. Anti-botul e configurat per domeniu.
    "snipes.com": {
        "label": "SNIPES",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D3, din dump-urile LST-D3 (7 septembrie) ──────────────────
        "listing": {
            # Locala `/de-de/` e cea VALIDATA pe axa L (v. `notes`): radacina
            # globala ar fi masurat alt catalog in alta moneda.
            "url": "https://www.snipes.com/de-de/c/sale-660",
            # 24 de carduri, zero paginare in HTML-ul brut.
            "max_pages": 1,
            "currency": "EUR",
            "card": ".card",
            # `<a class="image-container desktop-image"
            #     href="/de-de/p/adidas-originals-samba-og-beige-92395">`
            "link": "a.image-container",
            "title": "h2",
            "image_attr": ["src"],
            # `<span class="price sale">Preis 95,99 €</span>` — cuvantul german se
            # sterge odata cu simbolul, `_pret_eu_comma` da 95.99.
            "price_text": "span.price.sale",
            # `<del class="strikeout">Originalpreis 119,99 €</del>`, pe 24/24.
            "compare_text": "del.strikeout",
            "price_parse": "eu_comma",
            # DECIZIE, nu omisiune: pagina publica SEPARAT un camp Omnibus real,
            # verbatim `<… class="lowest-prior-price">30-Tage-Bestpreis: 95,99 €</…>`.
            # Nu el intra ca `compare_at`, fiindca pe cardul masurat valoarea lui e
            # EGALA cu pretul de vanzare — ca referinta n-ar califica NICIODATA R1
            # (pragul cere referinta strict mai mare). Se citeste deci
            # `Originalpreis`, care da o marja reala, iar `reference_kind` ramane
            # `nemarcat` tocmai fiindca `Originalpreis` NU e campul legal.
            "reference_kind": "nemarcat",
        },
        "notes": "G4-V2b; cea mai ieftina tinta din val — 200 din PRIMA cerere pe "
                 "profilul de productie, fara escaladare. PDP `/<locale>/p/<slug>` cu "
                 "ld+json [WebSite, Organization, Product]; genericul extrage fara "
                 "override (masurat 74,99 EUR). Acelasi magazin tehnic ca "
                 "solebox.com — vezi nota de acolo — dar aici anti-botul nu cere "
                 "browser, deci NU se pune pe harness: ar fi un Chromium per pagina "
                 "degeaba. Locala masurata `/de-de/`, moneda EUR. LIVRAREA IN RO nu "
                 "s-a masurat (zero semnale in corp): `unconfirmed` pana la verdictul "
                 "de checkout al lui David. DEAL-D3 - axa D pe `/de-de/c/sale-660` (locala validata pe axa "
                 "L), 24 de carduri fara paginare SSR. Referinta citita e "
                 "`Originalpreis`; pagina publica SEPARAT un camp Omnibus real, "
                 "`30-Tage-Bestpreis`, dar pe cardul masurat valoarea lui era "
                 "EGALA cu pretul de vanzare, deci ca `compare_at` n-ar califica "
                 "niciodata R1. Selectorii sunt IPOTEZA pentru solebox.com "
                 "(acelasi magazin tehnic, pe browser): `.card`, "
                 "`span.price.sale`, `del.strikeout`, `a.image-container` - de "
                 "VERIFICAT acolo, nu de presupus.",
    },
    "solebox.com": {
        "label": "solebox",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4-V2b; ruleaza pe INFRASTRUCTURA SNIPES — pagina isi incarca "
                 "asset-urile de pe `api.snipes.com` si `asset.snipes.com`, prefixul "
                 "de clase `hydra-` e comun, iar tiparul de PDP e identic "
                 "`/<locale>/p/<slug>`. Cu toate astea intra pe BROWSER, nu pe "
                 "jsonld ca snipes: pe HTTP da 403 cu „just a moment\" pe TOATE cele "
                 "trei profiluri ale lantului, in timp ce snipes trece din prima. "
                 "Lectia: identitatea de platforma nu se transfera la stratul de "
                 "acces. In Chrome real challenge-ul se rezolva TACIT — home 1,07MB "
                 "in 5,19s, cu 108 carduri cu pret. PDP-ul randat poarta ld+json "
                 "[WebSite, Organization, Product, BreadcrumbList] si genericul "
                 "extrage fara override (masurat 118,99 EUR). Locala masurata "
                 "`/en-eu/`, moneda EUR. LIVRAREA IN RO nu s-a masurat: "
                 "`unconfirmed`. headless NEMASURAT. Daca vreodata anti-botul lui "
                 "solebox se relaxeaza la nivelul lui snipes, domeniul poate cobori "
                 "ieftin pe `jsonld` — structura de date e deja aceeasi. "
                 "BRW-0b/BRW-1 - intra pe axa D prin BROWSER (`via: \"browser\"`), "
                 "singurul domeniu al valului cu referinta LEGALA. Doua corecturi "
                 "fata de ipoteza LST-D3, amandoua masurate pe home-ul randat de la "
                 "G4-V2b: locala e `en-eu` (297 de aparitii, fata de UNA singura "
                 "pentru `de-de`), iar cardul de listare NU e `.card` — acela e "
                 "cardul de pe HOME. Listarea foloseste `sni-lib-product-tile`, "
                 "elementul custom al platformei snipes. 24 de carduri pe pagina, "
                 "`p1 ∩ p2 = 0`, titlu si imagine 24/24. Coada e ZID, nu grila "
                 "goala: `?page=500` raspunde 403 cu un shell de 531 KB - de aceea "
                 "`max_pages` e plafon, nu bisectie.",
        # ── BRW-1 — din sonda BRW-0b §3.1 ──────────────────────────────────────
        "listing": {
            # `via` alege calea de FETCH a scannerului de listari, si e
            # independenta de `method`: `method` spune cum se citeste un PDP,
            # `via` cum se aduce o pagina de listare. Contraexemplul viu e
            # conrad.com — tot `method: "browser"`, dar listarea lui merge pe HTTP
            # (DEAL-D9), fiindca acolo raspunde 200. Aici HTTP-ul da `None`.
            "via": "browser",
            "url": "https://www.solebox.com/en-eu/c/sale-2775",
            "page_url_template": "https://www.solebox.com/en-eu/c/sale-2775?page={n}",
            # Plafonul iese din COST, nu din adancime: o pagina care se valideaza
            # costa 6,2–6,3 s aici, una care nu se valideaza costa plafonul intreg
            # de poll (22 s). Coada e oricum zid (403 la `?page=500`).
            "max_pages": 5,
            "currency": "EUR",
            # Elementul custom al platformei snipes. NU `.card`: acela e cardul de
            # pe home, si pe el fusese masurata ipoteza LST-D3.
            "card": "sni-lib-product-tile",
            "link": "a[href*='/en-eu/p/']",
            "title": "a[href*='/en-eu/p/']",
            "title_from": "link_aria_label",
            # Cardul poarta TREI preturi: `span.price.sale` (platit),
            # `del.strikeout` (pretul de lista, marketing) si `.lowest-prior-price`
            # (minimul de 30 de zile). A treia oara dupa modivo si answear cand
            # doua linii etichetate divergesc, si a treia oara cea legala castiga.
            "price_text": "span.price.sale",
            # AL DOILEA span, nu containerul: primul copil e eticheta „30-day-best
            # price", iar `eu_comma` ii lipeste „30" de valoare -> 30159,99. E
            # aceeasi capcana ca la answear, si doar controlul o arata.
            "compare_text": ".lowest-prior-price span:nth-of-type(2)",
            "price_parse": "eu_comma",
            "reference_kind": "min30",
        },
    },
    "lego.com": {
        "label": "LEGO",
        "category": "jucarii",
        "channel": "jucarii",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "G4-V2b; vitrina romaneasca `/ro-ro`, preturi in RON. PDP "
                 "`/ro-ro/product/<slug>-<cod>` cu ld+json [Organization, WebPage, "
                 "Product, BreadcrumbList]; genericul extrage fara override (masurat "
                 "899,99 RON). ATENTIE la istoricul deciziei: sonda G4-V2 l-a masurat "
                 "prin BROWSER si iesise viabil acolo, dar numai fiindca plafonul HTTP "
                 "se epuizase pe escaladarile irosite la solebox si watchshop. "
                 "Re-masurat explicit pe HTTP inainte de intrare: 200 pe profilul de "
                 "productie, fara challenge — deci `jsonld`, nu `browser` (aceeasi "
                 "lectie ca la forit.ro: „viabil prin browser\" nu inseamna „are "
                 "nevoie de browser\"). CAPCANA la orice citire pe text: pagina "
                 "poarta pragurile de livrare `100 lei` / `300 lei` / `500 lei` / "
                 "`1000 lei` alaturi de pretul real — ld+json le ocoleste. DEAL-D3 - NU intra pe axa D: navigatia `/ro-ro/` n-are nicio "
                 "categorie de sale, doar pagina CMS "
                 "`/ro-ro/page/lego-offers-promotions`, iar aceea e un CARUSEL de "
                 "20 (20/20 sub `ol.Carousel_items__...`) peste un "
                 "`__NEXT_DATA__` cu cache Apollo NORMALIZAT, in care valorile "
                 "stau in intrari separate legate prin referinte. Deci STATE, dar "
                 "cere un resolver de referinte. DEAL-D6 - INTRA, cu resolverul "
                 "scris: `lego_apollo`. Sonda a gasit si listarea reala, "
                 "`/ro-ro/categories/sales-and-deals` (18 produse pe p1, 4 pe p2, "
                 "0 comune), care la DEAL-D3 fusese declarata inexistenta - URL-ul "
                 "n-a fost ghicit, ci citit din cache: `SKUCarousel:<id>.cta.link` "
                 "e SINGURUL sir `/ro-ro/` din tot cache-ul campaniei.",
        # ── DEAL-D6, din dump-urile LST-D6 (categoria) + LST-D3 (campania) ──
        #
        # A DOUA forma `entries` pe un singur MAGAZIN (dupa eMAG si nichiduta,
        # care listau categorii): aici cele doua intrari sunt sectiuni diferite
        # ale aceleiasi vitrine, iar suprapunerea lor e reala (calendarul din
        # campanie e si in categorie). Nu deranjeaza: `vazute` dedupliceaza pe
        # `external_id`, si ambele au fost MASURATE, deci niciuna nu e ghicita.
        "listing": {
            "entries": [
                # 22 de produse azi (18 + 4). `?page=500` -> 200 cu grila goala
                # si cache fara nicio cheie `SingleVariantProduct:*`: oprire
                # curata, aceeasi semnatura ca altex/flip, deci plafonul e plasa.
                {"url": "https://www.lego.com/ro-ro/categories/sales-and-deals",
                 "page_url_template":
                     "https://www.lego.com/ro-ro/categories/sales-and-deals?page={n}",
                 "max_pages": 5},
                # Campania: pagina CMS masurata inca de la LST-D3, 20 de produse
                # intr-un carusel, fara paginare - de aici `max_pages: 1` si
                # niciun template (garda de paginare l-ar respinge oricum, si pe
                # buna dreptate: n-ar fi citit niciodata).
                {"url": "https://www.lego.com/ro-ro/page/lego-offers-promotions",
                 "max_pages": 1},
            ],
            # Plafonul descriptorului e doar rezerva ceruta de contract: ambele
            # intrari si-l declara pe al lor. 5 x 18 = 90, cu marja peste cele 22
            # de azi - numarul e al unei campanii si poate creste.
            "max_pages": 5,
            "currency": "RON",
            "state_extractor": "lego_apollo",
            # Varianta CSS exista si a fost masurata (18/18, 4/4, referinta
            # 22/22), dar NU se foloseste: da imagine pe 0/22 (`img[data-test=
            # 'product-leaf-image-1']` n-are nici `src`, nici `srcset` in brut),
            # si mai ales fiindca atributele de test sunt INVERSATE - `data-test=
            # "product-leaf-price"` e pretul TAIAT, iar cel platit sta in
            # `product-leaf-discounted-price`. Aceeasi capcana ca la altex.
            # Detaliile, in docstring-ul lui `lego_apollo`.
            #
            # `nemarcat`: `listPrice` e pretul de lista LEGO (PRP-ul lor), fara
            # nicio eticheta legala pe pagina - nici Omnibus, nici „UVP".
            "reference_kind": "nemarcat",
        },
    },
    "cardmarket.com": {
        "label": "Cardmarket",
        "category": "tcg",
        "channel": "diverse",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4-V2b; MARKETPLACE, nu magazin — extractor dedicat "
                 "`cardmarket_oferte`. Pretul e MINIMUL ofertelor publice, decizia lui "
                 "David: a patra aplicare a conventiei minimului din catalog (dupa "
                 "lowPrice, variantele G2F-4 si listele de oferte FASHION-1). PDP-ul "
                 "randat are 50 de randuri `.article-row` (`id=\"articleRow<N>\"`), "
                 "fiecare cu pretul in `.price-container`, format `2,98 €` — masurat "
                 "2,98..4,50 € pe un singur produs. Se ia `min()`, NU primul rand: "
                 "pagina masurata era deja sortata crescator, dar minimul nu trebuie "
                 "sa depinda de o sortare pe care magazinul o poate schimba. ZERO date "
                 "structurate — nici ld+json, nici microdata, nici itemprop=price — "
                 "deci genericul ridica `no_product_data` (pinuit de test), si nu "
                 "exista rezerva pe el. `method: \"browser\"` NU alege calea aici "
                 "(extractorul custom are prioritate in `extract_product`), dar E "
                 "lista de destinatii pe care harness-ul are voie sa navigheze — fara "
                 "el `_verifica_destinatia` ar refuza URL-ul. ACCESUL: challenge pe "
                 "RUTA, nu pe profil — `/en/Magic` trece pe un profil al lantului "
                 "(masurat la G3-1), dar `/Products/*` da 403 pe TOATE profilurile, "
                 "inclusiv pe acela; in Chrome real ruta de produs trece si da 284KB "
                 "de continut real. DE CONSEMNAT pentru axa D: livrarea e PER "
                 "VANZATOR (fiecare rand e alt vanzator, cu costul lui), deci „pretul "
                 "final\" nu e derivabil din pagina de produs. LIVRARE IN RO "
                 "nemasurata: `unconfirmed`. headless NEMASURAT.",
    },

    # ── G4-V3b — inchiderea axei L ────────────────────────────────────────────
    # Ultimele doua intrari ale axei. Celelalte doua tinte ale sondei G4-V3 —
    # pccomponentes.com si watchshop.ro — sunt BLOCATE FINAL pe Cloudflare
    # Turnstile (verificare interactiva): inaccesibile fara instrumente la care
    # s-a renuntat (proxy platit, Scrapling, rotatie de modem). Vezi docs.
    "notebooksbilliger.de": {
        "label": "notebooksbilliger",
        "category": "electronice",
        "channel": "electronice",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "browser",
        "status": "validated",
        "headed": True,
        "notes": "G4-V3b; ATENTIE la istoricul verdictului — banca G2B il avea drept "
                 "„Akamai, blocat\", si era o MASURATOARE GRESITA: daduse 404, pe UN "
                 "singur profil, fara escaladare (`escaladare_indice: 0`), fiindca "
                 "regula `expected` trateaza 404 ca terminal, nu ca challenge de "
                 "escaladat; corpul era o pagina de eroare Akamai reala („uups... Die "
                 "Seite wurde nicht gefunden\"). In Chrome real trece imediat: 295KB "
                 "cu 60 de carduri in 4,27s, PDP cu ld+json `Product` in 3,30s. "
                 "Genericul extrage fara override (masurat 69,90 EUR). BROWSERUL E "
                 "OBLIGATORIU, re-verificat explicit pe HTTP inainte de intrare: "
                 "profilul de productie ia marker de challenge `sec-if-cpt-container` "
                 "(Akamai bot manager), al doilea profil ia 404, iar al treilea da "
                 "200 dar FARA nicio structura de produs — deci HTTP-ul nu e o "
                 "alternativa, spre deosebire de footlocker. NU e `b2b_only`, masurat: "
                 "`inkl. MwSt` x2 (pret BRUT, cu TVA — spre deosebire de conrad.com, "
                 "care e net), `Geschaeftskunden` apare o singura data ca link de "
                 "navigatie, zero cerinta de `USt-IdNr`. Decizia lui David: intra ca "
                 "magazin obisnuit, livrarea in RO ramane `unconfirmed`. CAPCANA "
                 "pentru axa D: referinta taiata e `UVP` (pret recomandat de "
                 "producator), NU Omnibus — acelasi tipar ca nichiduta si biciclop; "
                 "masurat „-39 % UVP: 115,00 € -> 69,90 €\". headless NEMASURAT. "
                 "BRW-0/BRW-1 - intra pe axa D prin BROWSER (`via: \"browser\"`), pe "
                 "`/outlet`. Intrarea din plan, `/angebote`, e GRESITA si asta s-a "
                 "masurat: se randeaza (325.871 octeti) dar e afisul „Deal des "
                 "Tages\", cu ZERO jetoane de pret in text - a costat plafonul "
                 "intreg de poll, 37,62 s, pentru zero carduri. HTTP nu e "
                 "alternativa nici pe listare: poarta a intors `None` pe AMBELE "
                 "intrari. Capcana UVP de mai sus e a PDP-ului, nu a outletului: pe "
                 "`/outlet` e marfa folosita („Gebrauchtware\") cu un SINGUR pret - "
                 "zero noduri taiate, zero aparitii de `UVP` sau `statt` in toata "
                 "pagina - deci descriptorul n-are `compare_*` si domeniul califica "
                 "doar pe R2.",
        # ── BRW-1 — din sonda BRW-0 §3.1 ───────────────────────────────────────
        "listing": {
            "via": "browser",
            # `/outlet`, NU `/angebote`: a doua e afisul „Deal des Tages", masurat
            # cu ZERO preturi in text si zero carduri, pe 37,62 s de poll.
            "url": "https://www.notebooksbilliger.de/outlet",
            "page_url_template": "https://www.notebooksbilliger.de/outlet?page={n}",
            # Plafon din COST (v. solebox). Adancimea reala nu s-a masurat; se stie
            # doar ca pagina 2 exista (20 de carduri, `p1 ∩ p2 = 1`) si ca
            # `?page=500` e CLAMP — serveste iar pagina 1, plus alte 18, deci
            # conditia compozita a scannerului o prinde ca submultime.
            "max_pages": 5,
            "currency": "EUR",
            "card": ".product-listing__row",
            # PDP-urile au forma `/marca+model+<id>`, cu plus-uri.
            "link": "a[href*='+']",
            "title": ".product-card__product-heading-title",
            "price_text": ".product-price__price",
            "price_parse": "eu_comma",
            # FARA `compare_*`, si asta e o masuratoare, nu o omisiune: outletul e
            # de marfa folosita, cu un singur pret. Domeniul califica doar pe R2.
            "reference_kind": "nemarcat",
        },
    },
    "footlocker.ro": {
        "label": "Foot Locker",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        # ── DEAL-D1, din sonda LST-D1 §2.4 ──────────────────────────────────
        "listing": {
            "url": "https://www.footlocker.ro/ro/special-prices/",
            # Numarul de pagina e in CALE, sub forma /pN/ — citit din ancora
            # `title="next-page"`, care poarta si `data-page="2"`.
            "page_url_template": "https://www.footlocker.ro/ro/special-prices/"
                                 "p{n}/",
            # CITAT, nu derivat: pagina declara `data-total-pages="38"`
            # (`data-page-size="20"`), plus marja dupa conventia otter. Oprirea
            # reala e CLAMP: /p500/ redirecteaza la pagina 1.
            "max_pages": 45,
            "currency": "RON",
            # `.x-box` selecteaza acelasi set, dar e un nume prea generic ca sa
            # reziste la un refactor de sablon.
            "card": "article.x-product-box",
            "link": "a.js-product-link",
            "title": "h2.js-product-link",
            "image_attr": ["src"],
            "price_text": ".current-price",
            "compare_text": ".recommended-price .price span[data-exchange-price]",
            "price_parse": "eu_comma",
            # Etichetat EXPLICIT si vizibil: „Pret de vanzare recomandat:", cu
            # explicatia magazinului („pretul de vanzare initial pe care l-a avut
            # produsul"). Alternativa masurata, tot etichetata, e
            # `.lowest-price .price` („Cel mai mic pret pe 30 de zile:") — ar cere
            # `reference_kind: "min30"`.
            #
            # DE STIUT: pe cele 60 de carduri masurate (p1+p2+plast),
            # `current-price` e IDENTIC cu `recommended-price` — categoria n-avea
            # nicio reducere activa in ziua sondei, deci `compare_at <= price` si
            # R1 nu califica nimic.
            "reference_kind": "prp",
        },
        "notes": "G4-V3b; a intrat prin valul de browser dar NU e intrare de browser — "
                 "a treia oara cand se aplica regula, dupa forit.ro si lego.com. "
                 "Sonda G4-V3 l-a masurat randat (PDP cu ld+json `Product` + "
                 "`BreadcrumbList`, 549,99 RON), iar verificarea de HTTP dinainte de "
                 "intrare a dat 200 pe profilul de productie, fara challenge, cu "
                 "ACEEASI valoare — deci `jsonld`, si nu se plateste un Chromium per "
                 "pagina. CAPCANA de recoltare, masurata: HOME-ul nu poarta NICIUN "
                 "link de produs, nici macar dupa hidratare (241 de ancore, zero "
                 "produse) — produsele apar pe CATEGORII, de ex. `/ro/barbati/pantofi/` "
                 "(28 de carduri). Cine cauta PDP-uri pornind de la home nu gaseste "
                 "nimic si trage concluzia gresita ca situl e gol. PDP "
                 "`/ro/<sectiune>/<categorie>/<subcategorie>/<slug>`. Stocul se "
                 "citeste din ld+json si POATE fi False pe produse afisate normal "
                 "(masurat `in_stock: False` pe PDP-ul de proba, cu pagina servita "
                 "fara eroare). DEAL-D1, din sonda LST-D1: axa D intrata pe "
                 "`/ro/special-prices/`. DE STIUT la primul scan: pe cele 60 de "
                 "carduri masurate (p1+p2+plast) `current-price` == "
                 "`recommended-price` == `lowest-price` — categoria n-avea NICIO "
                 "reducere activa in ziua sondei, deci `compare_at <= price` si R1 nu "
                 "califica nimic la baseline; dealurile vor veni din R2. Pagina isi "
                 "declara singura adancimea (`data-total-pages=\"38\"`, "
                 "`data-page-size=\"20\"`), iar /p500/ redirecteaza la pagina 1.",
    },

    # ── G4-V4b — epilogul axei L ──────────────────────────────────────────────
    # Din cele patru tinte ale sondei corective G4-V4 intra UNA (reichelt);
    # decathlon vine separat, deblocat de aplatizarea ofertelor imbricate.
    # sportsdirect.ro cere extractor pe stare (pretul e in `productPrice`, ancorat
    # pe `productId`) — runda proprie. ccc.eu e blocat de un zid de CONSIMTAMANT
    # fara buton de refuz, iar fressnapf.ro isi incarca produsele printr-un XHR
    # ulterior. Toate trei in docs.
    "decathlon.ro": {
        "label": "Decathlon",
        "category": "outdoor",
        "channel": "diverse",
        "country": "RO",
        "delivery": "ro_storefront",
        # ── DEAL-D11 — MIGRAT de pe browser pe HTTP (sonda LST-D10 §3.2) ──────
        # `method` era `browser` si `headed: True`; amandoua au fost sterse dupa
        # ce trei PDP-uri REALE au trecut prin `extract_product` de productie cu
        # `safari2601` (v. PASUL 3 al rundei). Costul recurent pe care BRW-0b il
        # asumase explicit — „~1 minut de Chromium pe noapte" — dispare aici.
        "method": "jsonld",
        "status": "validated",
        "notes": "G4-V4b; deblocat de aplatizarea listelor imbricate din `offers` "
                 "(`_aplatizeaza_oferte`). Forma masurata: ld+json `Product` cu "
                 "`offers` = lista de DOUA liste a cate 9 `Offer` — 18 in total, toate "
                 "cotate `159,99 RON` / `InStock`. Inainte de fix, consumatorii sareau "
                 "orice element nedict si le pierdeau pe toate 18, deci pagina cadea cu "
                 "`no_product_data` desi publica preturi perfect valide: nu era pagina "
                 "fara date, era forma nerecunoscuta. Preturile fiind egale, minimul "
                 "G2F-4 e chiar el. CAPCANA la citirea pe text: pagina poarta si "
                 "`0 00 RON` (cosul gol) langa pretul real — ld+json il ocoleste. "
                 "AFIRMATIA VECHE „BROWSERUL E OBLIGATORIU… 403 pe TOATE cele trei "
                 "profiluri ale lantului” e INFIRMATA de DEAL-D11, si nuanta conteaza: "
                 "era adevarata despre profilurile INCERCATE, nu despre toate. G2F-1 "
                 "spunea „Cloudflare pe toate profilurile”, G4-V4b „403 pe toate cele "
                 "trei profiluri ale lantului”, BRW-0b „403 si in Chrome real” — dar "
                 "cele trei nu sunt numite nicaieri, si niciuna dintre runde n-a atins "
                 "un Safari. Pe `safari2601` home-ul da 200 cu 574.356 de octeti, "
                 "listarea de reduceri da 40 de carduri, iar PDP-ul da ld+json "
                 "complet. Lectia generala: „blocat pe toate profilurile” e valabil "
                 "doar pentru profilurile NUMITE.",
        # ── DEAL-D11 — amprenta care deschide AMANDOUA axele (LST-D10 §3.2) ───
        "impersonate": "safari2601",
        "listing": {
            # Singura cale de reduceri din home-ul deblocat, citita verbatim din
            # ancorele lui — nu construita. Cardurile sunt de MARKETPLACE
            # (`/p/mp/<marca>/…`), ceea ce se vede si in nume.
            "url": "https://www.decathlon.ro/deals/reduceri-parteneri-marketplace",
            # PAGINA UNICA: zero `rel="next"`, zero ancore de pagina. Ca la
            # pcgarage, un sablon aici ar fi inventat.
            "max_pages": 1,
            "currency": "RON",
            "card": "article.product-card",
            "link": "h2 a",
            "title": "h2 a",
            # CAPCANA, si e chiar tiparul answear (LST-D7): AMBELE spanuri de
            # pret poarta o eticheta `sr-only` INAUNTRU — „Pretul actual” si
            # „Pretul anterior” — deci textul lor incepe cu cuvinte, nu cu cifre.
            # `p.price-size-container` e nodul CURAT, fara eticheta. Masurat:
            # `span.vp-price-amount--sale` (cu eticheta) da acelasi numar pe
            # 40/40, fiindca `eu_comma` sterge non-cifrele — deci sabotajul „ia
            # spanul cu eticheta” e INERT aici. Descriptorul ia oricum nodul
            # curat: a te baza pe toleranta parserului nu e acelasi lucru cu a
            # citi nodul potrivit.
            "price_text": "p.price-size-container",
            "compare_text": "span.vp-price-barred-amount",
            "price_parse": "eu_comma",
            "compare_parse": "eu_comma",
            # Eticheta e „Pretul anterior”, adica pretul de dinainte — nu un
            # minim de 30 de zile si nici un PRP. Reducerea mediana e 16,7%
            # (3,1–67,7). 40/40 au pret, referinta, titlu SI imagine.
            "reference_kind": "nemarcat",
        },
    },
    "reichelt.de": {
        "label": "reichelt elektronik",
        "category": "electronice",
        "channel": "electronice",
        "country": "DE",
        "delivery": "unconfirmed",
        "method": "microdata",
        "status": "validated",
        "notes": "G4-V4b; ATENTIE la istoric — domeniul a stat mult drept „poarta de "
                 "sesiune neclarificata\", si era o RECOLTARE gresita, nu un blocaj: "
                 "sondele incarcasera `/magazin/`, care e REVISTA, nu catalogul. "
                 "Traseul real, masurat: home -> 72 de cai de catalog -> `/de/de` "
                 "(57 de carduri) -> PDP `/de/de/shop/produkt/<slug>`. Metoda e "
                 "MICRODATA, nu jsonld (ld+json-ul are doar Organization/WebSite/ "
                 "BreadcrumbList/WebPage): genericul extrage fara override, masurat pe "
                 "DOUA PDP-uri cu preturi mult diferite — 89,99 EUR si 1.188,50 EUR. "
                 "NU e intrare de browser, desi acolo a fost masurat prima oara: "
                 "re-verificat pe HTTP inainte de intrare, da 200 pe profilul de "
                 "productie, fara challenge, cu ACEEASI valoare. CAPCANA la nume: "
                 "`name` din microdata include sufixul de titlu al paginii („... | "
                 "LED-Panels günstig kaufen | reichelt elektronik\") — se curata la "
                 "afisare. LIVRARE IN RO nemasurata: `unconfirmed` (exista o locala "
                 "`/ro/de/`, dar asta e tintire, nu confirmare de checkout). "
                 "DEAL-D5 — JS_ONLY pe axa D: intrarea „Sale” din nav "
                 "(`/de/de/shop/landingpage/-2568`) raspunde 200 cu 214 KB si e "
                 "GOALA de continut — 2 jetoane de pret, ZERO ancore catre "
                 "`/de/de/…`, zero linkuri de produs, niciun h1, zero colectii "
                 "de produse in starea serializata. `/magazin/` a fost exclus "
                 "explicit din candidate (e REVISTA, nu catalog, G4-V4b) si nu "
                 "s-a cerut. "
                 "LST-D9/DEAL-D10a — verdictul DEAL-D5 „JS_ONLY / pagina goala\" era "
                 "corect PENTRU PAGINA AIA si gresit pentru domeniu: "
                 "`landingpage/-2568` se numeste chiar „Sale\" si e un HUB de zece "
                 "categorii, nu un raft. Fiecare categorie apare in el de DOUA ori, "
                 "iar a doua forma poarta filtrul de reduceri, verbatim: "
                 "`?VIEWALL=1&specialprice=1`. Home-ul n-avea de unde sa-l dea — "
                 "nav-ul lui de categorii e client-side (117 ancore, ZERO cai "
                 "`/shop/kategorie`). A doua corectie de acelasi fel: pretul taiat "
                 "EXISTA, dar clasa lui e `p.highprice` (32/32 pe doua categorii), "
                 "nu `line-through` (3/16) — cautarea markerului gresit era gata sa "
                 "declare domeniul fara referinta.",
        # ── DEAL-D10a — din sonda LST-D9 §3.3 ─────────────────────────────────
        "listing": {
            # Cele ZECE categorii, verbatim din hub-ul `landingpage/-2568`
            # (`dumps_lstd5/reichelt.de_p1.html`). `specialprice=1` NU e ghicit:
            # e chiar filtrul pe care pagina il pune pe a doua forma a fiecarei
            # categorii. `/magazin/` ramane exclus (e revista, nu catalog).
            "entries": [
                # Bauelemente
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/bauelemente-2875?VIEWALL=1&specialprice=1"},
                # Raspberry Pi / Arduino
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/entwicklerboards-8241?VIEWALL=1&specialprice=1"},
                # Stromversorgung
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/stromversorgung-1012?VIEWALL=1&specialprice=1"},
                # Messtechnik
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/messtechnik-5868?VIEWALL=1&specialprice=1"},
                # Werkstatt und Loettechnik
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/messtechnik_und_werkstattbedarf-536?VIEWALL=1&specialprice=1"},
                # Haustechnik / Sicherheit
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/haus-_und_sicherheitstechnik-2712?VIEWALL=1&specialprice=1"},
                # Netzwerktechnik
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/netzwerktechnik-5820?VIEWALL=1&specialprice=1"},
                # PC-Technik
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/pc-technik-639?VIEWALL=1&specialprice=1"},
                # Sat & TV / Audio / Video
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/sat-tv_audio_video-2876?VIEWALL=1&specialprice=1"},
                # Kommunikation & Buero
                {"url": "https://www.reichelt.de/de/de/shop/kategorie/buero_kommunikation-845?VIEWALL=1&specialprice=1"},
            ],
            # O singura pagina per categorie: `VIEWALL=1` NU extinde peste 16, si
            # asta s-a masurat pe amandoua categoriile sondate. 16 x 10 = ~160 de
            # produse pe scan.
            "max_pages": 1,
            "currency": "EUR",
            "card": "#productResult div.al_gallery_article",
            # PRIMA ancora a cardului e logo-ul PRODUCATORULUI
            # (`/shop/hersteller/FREI`) — sonda a ars doua cereri pe ea. Ancora de
            # produs se scopeaza explicit.
            "link": "a[href*='/shop/produkt/']",
            # `[itemprop=name]` e un `<meta>`, deci n-are TEXT: titlul iesea gol pe
            # 16/16. Numele complet sta in atributul `title` al ancorei de produs —
            # exact modul scris la DEAL-D4 pentru officeshoes, al doilea consumator.
            "title": "[itemprop='name']",
            "title_from": "link_title",
            # A DOUA fata a capcanei logo-ului: prima `<img>` a cardului e tot
            # logo-ul producatorului (`web/logo/FREI.png?type=Manufacturer`).
            # Imaginea produsului se scopeaza sub ACEEASI ancora ca linkul.
            "image": "a[href*='/shop/produkt/'] img",
            # Pretul se citeste din ATRIBUT, si nu din comoditate: in text
            # zecimalele stau intr-un `<sup>` („0, 08 €"), adica treapta `eu_sup`.
            # Calea de atribut ocoleste capcana cu totul.
            "price_attr": ["meta[itemprop='price']", "content"],
            "price_parse": "attr_float",
            # Referinta e in TEXT, deci isi declara parserul ei (DEAL-D2).
            # Badge-ul „SPARE" NU se citeste: are doua forme pe aceleasi carduri —
            # 25 procentuale („SPARE 89%") si 7 in suma („SPARE 150,00 €").
            "compare_text": "p.highprice",
            "compare_parse": "eu_comma",
            # Fara eticheta legala: nici UVP, nici Omnibus, doar un pret mai mare.
            "reference_kind": "nemarcat",
        },
        # Pretul e BRUT — `inkl. 19% gesetzl. MwSt` pe card, pe `CCTYPE=private`,
        # care e si implicitul portii. NU e capcana conrad (acolo pretul era NET).
        # Comutatorul `CCTYPE=private|business|nonprofit` exista si e vizibil in
        # pagina; daca implicitul s-ar schimba vreodata pe `business`, preturile
        # ar deveni nete si comparatia cu magazinele romanesti ar subestima
        # sistematic. De re-masurat daca apare un cookie de sesiune pe poarta.
    },

    # ── SNK-2 — lotul de sneakers (sonda SNK-1) ───────────────────────────────
    "sneakerindustry.ro": {
        "label": "Sneaker Industry",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        # DEAL-D1: `og` -> `shopify`. Enumerarea e DESCHISA, masurat — vezi `notes`.
        "method": "shopify",
        "status": "validated",
        # Din `/cart.js`, masurat la DEAL-D1. Pe calea `shopify` moneda NU vine din
        # payload, o citeste extractorul de aici — deci campul e obligatoriu, nu
        # decorativ.
        "currency": "RON",
        # Vine ODATA cu `method: shopify`, nu ca decizie separata: mecanismul e API
        # de PLATFORMA (`/search/suggest.json`), disponibil pe orice magazin
        # Shopify prin constructie, iar absenta lui ar fi o omisiune care ar face
        # magazinul sa lipseasca TACIT din pagina „Scanare Magazine". Pinuit de
        # `test_search_shopify_pe_toate_shopify`.
        "search": {"kind": "shopify"},
        # `og:title` e numele SITULUI („Sneaker Industry - SNKR IND."), nu al
        # produsului. `h1` e unic pe PDP si poarta numele real, verificat pe DOUA
        # pagini: „On Cloud 6 Geo WP" si „On Cloudzone". INERT de la DEAL-D1:
        # calea `shopify` citeste numele din payload si intoarce
        # `override_applied: False`. Se pastreaza fiindca descrie calea `og`, la
        # care s-ar reveni daca enumerarea s-ar inchide din nou.
        "overrides": {"name_selector": "h1"},
        "notes": "SNK-2, RASTURNAT la LST-D1/DEAL-D1 — a DOUA corectie de platforma "
                 "pe acelasi domeniu, in sens INVERS fata de prima. Istoric, ca sa nu "
                 "se re-descopere: domeniul a stat luni intregi drept „Shopify cu "
                 "enumerarea inchisa\" (403 pe `products.json`), apoi SNK-1 a masurat "
                 "`powered-by: PrestaShop` + `PHPSESSID` + `PrestaShop-<hash>` si a "
                 "scris ca „nu se poate deschide ceva ce nu exista\". Intre timp "
                 "magazinul a MIGRAT INAPOI pe Shopify, iar asta invalideaza exact "
                 "acea concluzie. Masurat la LST-D1 (2026-09-07), patru semnale "
                 "independente: antet `powered-by: Shopify`; cookie-uri `_shopify_y` / "
                 "`_shopify_s` (zero `PHPSESSID`); `/ro/reduceri-de-pret` "
                 "REDIRECTEAZA la `/collections/reduceri`; cardul de listare e "
                 "`product-card` (zero aparitii `product-miniature` in dump). "
                 "ENUMERAREA E DESCHISA, masurat la DEAL-D1 cu 3 cereri: "
                 "`/products.json?limit=5` -> 200 cu 5 produse, variantele purtand "
                 "`available` + `price` + `compare_at_price` (5/5); `/cart.js` -> 200 "
                 "cu `currency: RON`; `/products/60915795.js` -> 200, unde varianta "
                 "54713477759322 are `price: 16900` = `\"169.00\"` x 100 din "
                 "enumerare, `available: true`. Fara cookie `datadome`. De aceea "
                 "`method: shopify` si NU un descriptor `listing`: enumerarea acopera "
                 "tot catalogul, nu doar grila de reduceri, iar `compare_at_price` e "
                 "referinta comerciantului (R1 pe pragul global), nu una de listare "
                 "(R1 la 40%). Pe esantionul de 5, `compare_at_price` e null peste "
                 "tot. Descriptorul CSS masurat de LST-D1 §2.3 ramane in raport ca "
                 "REZERVA, daca enumerarea se inchide iar: card `.product-card` (48 pe "
                 "pagina), `sale-price` / `compare-at-price`, `?page={n}`, oprire pe "
                 "grila goala la `?page=500`, 819 produse. "
                 "ISTORIC pe calea `og`, valabil doar daca se revine la ea: "
                 "PDP-urile n-au NICIUN ld+json. "
                 "Metoda masurata e `og` (`product:price:amount`), pe doua PDP-uri cu "
                 "preturi diferite — 899,10 RON si 692,10 RON, moneda RON incrucisata "
                 "in og SI in afisaj. CAPCANE: (1) exista microdata cu un singur "
                 "`itemtype=schema.org/Product`, dar DOUASPREZECE noduri "
                 "`itemprop=price` — cel propriu e sub `p.product-price[itemprop="
                 "offers]`, restul sunt carduri de recomandare "
                 "(`.product-price-and-shipping`); de aceea genericul cade pe og si "
                 "microdata NU e o alternativa sigura fara selector. (2) Widget de "
                 "rate Mokka, `.mokka-price-amount` = „74,93 RON/luna\". (3) Pretul "
                 "vechi exista, in `span.regular-price` (999,00 RON), dar FARA "
                 "<del>/<s> si fara nicio formulare de 30 de zile: Omnibus NEMARCAT. "
                 "Randul vechi „axa D e nesondata: 48 de carduri "
                 "`article.product-miniature.home-product`, PDP "
                 "`/ro/<categorie>/<id>-<id>-<slug>.html`\" e MORT odata cu migrarea: "
                 "acele selectoare si acea forma de URL nu mai exista pe sit. Forma "
                 "actuala de PDP e `/products/<handle>`.",
    },
    "nike.com": {
        "label": "Nike",
        "category": "sneakers",
        "channel": "sneakers",
        "country": "RO",
        "delivery": "ro_storefront",
        "method": "jsonld",
        "status": "validated",
        "notes": "SNK-2; intrat CONTRA asteptarilor si a cincea aplicare a regulii "
                 "G4-V4b („viabil prin browser\" != „are nevoie de browser\"), dupa "
                 "forit, lego, footlocker si reichelt. Sonda pornise cu asteptari "
                 "mici — varf de clasa de protectie — si a masurat altceva: "
                 "`https://www.nike.com/ro/` da 200 pe profilul de PRODUCTIE al "
                 "scraperului, 684 KB, titlu real, ZERO challenge, fara escaladare de "
                 "profil; singurul cookie e `ak_bmsc`, infrastructura Akamai, "
                 "nevinovat prin el insusi. Escaladarea la browser s-a facut pentru "
                 "ca home-ul si categoriile n-au pret server-side (`__NEXT_DATA__` "
                 "fara chei de pret, zero linkuri `/t/`) — deci NEMASURABIL pe "
                 "treapta 1, nu blocat. Odata ce URL-ul de PDP a fost recoltat din "
                 "listarea RANDATA, ACELASI PDP pe HTTP a dat `ProductGroup` cu 19 "
                 "oferte, toate cu `price`/`RON`. Lectia, generala pentru SPA-uri: "
                 "absenta datelor pe home NU prezice absenta lor pe PDP — browserul "
                 "poate fi necesar ca sa RECOLTEZI URL-ul, fara sa fie necesar ca sa "
                 "CITESTI pagina. Forma masurata: PDP `/ro/t/<slug>/<cod-stil>`, "
                 "listari `/ro/w/<slug>`. `in_stock` iese None: ofertele n-au "
                 "`availability` — negasit, nu ignorat. Pret verificat: 1.499,99 RON, "
                 "identic in ld+json si in afisaj. DEAL-D3 - POARTA: `/ro/w/promotional-styles-3vvvm` a primit "
                 "`None` din poarta, dar cererea directa cu ACELASI profil a dat "
                 "200 (875 KB, titlu real) si `classify()` rulat pe chiar acel "
                 "corp intoarce OK. Deci situl serveste pagina si poarta e cea "
                 "care refuza - al doilea caz dupa flanco. Afirmatia SNK-2 (fara "
                 "pret server-side pe listari) ramane NETESTATA: poarta n-a "
                 "livrat corpul. "
                 "LST-D7 - TESTATA acum, pe dump-urile care EXISTAU deja la 200 "
                 "(GATE-1 si LST-D3, acelasi URL, 875.547 vs 875.548 octeti): "
                 "afirmatia e GRESITA pentru pagina asta. Listarea "
                 "`/ro/w/promotional-styles-3vvvm` are 24 de carduri in DOM sub "
                 "`#skip-to-products`, cu pret vizibil, plus 66 de `currentPrice` cu "
                 "`currency: RON` in `__NEXT_DATA__`. Zero cereri cheltuite ca sa se "
                 "afle: raspunsul era pe disc.",
        # ── DEAL-D7, din `dumps_lstd3/nike.com_p1_direct.html` ───────────────
        "listing": {
            "url": "https://www.nike.com/ro/w/promotional-styles-3vvvm",
            # In HTML-ul brut nu exista nicio paginare care sa pastreze calea
            # intrarii: pagina incarca prin scroll infinit. 24 de carduri per scan.
            "max_pages": 1, "currency": "RON",
            "card": "#skip-to-products div.product-card",
            "link": "[data-testid=\"product-card__link-overlay\"]",
            "title": "[data-testid=\"product-card__link-overlay\"]",
            # CAPCANA, a treia oara dupa altex si lego: `data-testid` inverseaza
            # intuitia — `product-price` e pretul TAIAT pe cardurile reduse, iar cel
            # platit sta in `product-price-reduced`. Descriptorul NU se sprijina insa
            # pe ele, ci pe CLASELE de stare, care spun acelasi lucru fara ambiguitate
            # si, mai ales, acopera si cardurile NEREDUSE:
            #   `is--current-price` — pretul platit, prezent pe 24/24;
            #   `is--striked-out`   — pretul taiat, prezent doar pe cele 3 reduse.
            # Pe `data-testid` ar fi intrat doar cele 3 carduri reduse (cardurile
            # nereduse n-au nodul `product-price-reduced`, deci ar fi fost sarite);
            # asa intra toate 24, iar cele 21 nereduse au `compare_at` None si
            # califica pe R2 (minim istoric), ca buzzsneakers si toolnation.
            "price_text": ".product-price.is--current-price",
            "compare_text": ".product-price.is--striked-out",
            "price_parse": "eu_comma", "reference_kind": "nemarcat",
        },
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


def _valideaza_extra_headers(registru: dict) -> None:
    """DEAL-D8. `cookie_jar` + un `Cookie` in `extra_headers` = RESPINS la import.

    Poarta trimite jar-ul ca argument separat (`cookies=jar` catre curl_cffi) si
    `extra_headers` prin `headers=`. Cele doua ar ajunge amandoua la acelasi antet
    `Cookie` al cererii, iar cine castiga e o proprietate a clientului HTTP, nu o
    decizie a noastra — adica exact felul de ambiguitate care se descopera abia
    cand un magazin incepe sa serveasca alta moneda.

    Ridica la IMPORT, nu la prima cerere: registrul e un literal Python, deci o
    combinatie gresita e o greseala de scriere care trebuie sa cada imediat, nu
    dupa ce a rulat un scan intreg. Ia registrul ca ARGUMENT ca sa poata fi
    verificata si pe un registru sintetic, in teste.

    Numele de antet se compara case-insensitive: HTTP-ul nu deosebeste `Cookie`
    de `cookie`, deci nici garda n-are voie s-o faca.
    """
    for domain, meta in (registru or {}).items():
        antete = meta.get("extra_headers")
        if not antete:
            continue
        if not isinstance(antete, dict):
            raise ValueError(
                f"{domain}: `extra_headers` trebuie sa fie dict, nu "
                f"{type(antete).__name__}")
        if not meta.get("cookie_jar"):
            continue
        for nume in antete:
            if str(nume).strip().lower() == "cookie":
                raise ValueError(
                    f"{domain}: `cookie_jar` si `extra_headers[\"{nume}\"]` nu pot "
                    f"coexista — jar-ul pleaca prin `cookies=`, antetul prin "
                    f"`headers=`, iar cine castiga nu e decizia noastra")


_valideaza_extra_headers(SHOP_REGISTRY)


# DISC-1 — canalele Discord pe care se imparte axa D. Multimea e INCHISA si mica:
# sunt exact canalele care exista in serverul lui David, iar un al saptelea ar
# cere intai un canal acolo si abia apoi o valoare aici.
#
# `toate` NU e in lista, deliberat: el nu e un canal AL UNUI MAGAZIN, ci o
# destinatie care primeste orice deal indiferent de canal. Un domeniu cu
# `channel: "toate"` ar fi o confuzie intre cele doua, deci garda il respinge.
CANALE_DEAL = ("electronice", "sneakers", "haine", "jucarii", "beauty", "diverse")

# Canalul pe care cade un domeniu care nu-si declara niciunul.
CANAL_IMPLICIT = "diverse"


def _valideaza_channel(registru: dict) -> None:
    """DISC-1. O valoare de `channel` din afara setului = RESPINS la import.

    Ridica la IMPORT din acelasi motiv ca `_valideaza_extra_headers`: registrul e
    un literal Python, deci `"electronic"` in loc de `"electronice"` e o greseala
    de SCRIERE, si trebuie sa cada imediat. Fallback-ul tacut ar fi aici mai rau
    decat de obicei — `deal_channel` intoarce `diverse` pentru orice necunoscut,
    deci o typo ar trimite un magazin intreg pe canalul de fund fara ca nimeni sa
    observe, iar simptomul (deal-uri „lipsa" dintr-un canal) nu arata catre cauza.

    Verifica AMBELE nivele, fiindca amandoua sunt scrise de mana: cheia de pe
    domeniu si cheia de pe fiecare intrare din `listing.entries`.

    Ia registrul ca ARGUMENT ca sa poata fi verificata si pe unul sintetic, in
    teste — o garda care se poate rula doar pe registrul real n-are cum sa
    dovedeasca ce respinge.
    """
    def _verifica(valoare, unde: str) -> None:
        if valoare is None:
            return
        if valoare not in CANALE_DEAL:
            raise ValueError(
                f"{unde}: `channel` necunoscut {valoare!r} — valorile permise "
                f"sunt {', '.join(CANALE_DEAL)} (absenta = {CANAL_IMPLICIT})")

    for domain, meta in (registru or {}).items():
        _verifica(meta.get("channel"), domain)
        intrari = (meta.get("listing") or {}).get("entries") or []
        for indice, intrare in enumerate(intrari):
            if isinstance(intrare, dict):
                _verifica(intrare.get("channel"), f"{domain}: intrarea {indice}")


_valideaza_channel(SHOP_REGISTRY)


def deal_channel(domain: str, entry: dict | None = None) -> str:
    """DISC-1 — canalul Discord al unui deal: intrare > domeniu > `diverse`.

    SINGURUL loc unde regula de rutare traieste. Notificatorul primeste de aici un
    string si atat: daca ar tine el o lista de domenii per canal, ea ar diverge de
    registru la primul magazin nou — exact bug-ul tacut pentru care exista REG-1.

    `entry` e intrarea de listare din care a iesit deal-ul, cand domeniul are mai
    multe (eMAG). Pe domeniile cu o singura listare se cheama fara ea. Un `entry`
    fara `channel` nu suprascrie nimic: cade pe cel al domeniului.

    Toleranta la necunoscut e ASIMETRICA fata de garzi, si deliberat, pe doua
    nivele: o valoare gresita SCRISA in registru cade la import
    (`_valideaza_channel`), un domeniu din registru fara eticheta cade la test
    (DISC-1b), dar un domeniu care nu mai e DELOC in registru intoarce `diverse`
    in loc sa ridice. Ultimul caz nu e o scapare de configurare, ci un rand vechi
    al unui magazin scos intre timp — iar acolo un deal fara canal trebuie sa
    ajunga undeva, nu sa rupa scanul.
    """
    canal = None
    if isinstance(entry, dict):
        canal = entry.get("channel")
    if not canal:
        canal = (SHOP_REGISTRY.get(domain) or {}).get("channel")
    return canal if canal in CANALE_DEAL else CANAL_IMPLICIT


def label_of(domain: str) -> str:
    """Numele lizibil al magazinului, cu domeniul ca rezerva.

    Acelasi tipar `meta.get("label") or domain` pe care il scriau deja de mana
    `search_service` si `routers/deals`; DISC-1 i-ar fi adaugat a treia copie, in
    embed-ul de Discord. Lookup direct, fara copie, ca la `url_identity_of`:
    valoarea e un scalar imutabil.
    """
    return (SHOP_REGISTRY.get(domain) or {}).get("label") or domain


def option_map(key: str) -> dict:
    """Domeniu -> valoarea cheii OPTIONALE `key` de la NIVELUL DE SUS al intrarii.

    AMZ-1. Perechea lui `overrides_option_map`, dar pentru chei care NU stau in
    payload-ul `overrides`: acolo traiesc lucruri de PARSARE, aici lucruri de
    TRANSPORT (`cookie_jar`, `bootstrap_url`), langa `min_fetch_interval_s` si
    `impersonate`, care sunt deja de nivel de sus din acelasi motiv.

    Aceeasi disciplina ca la celelalte derivari: doar domeniile care CHIAR au cheia,
    ca apelantul sa poata construi harta o data la import, si copie adanca fiindca
    valoarea poate fi mutabila.
    """
    return {domain: copy.deepcopy(meta[key])
            for domain, meta in SHOP_REGISTRY.items() if key in meta}


def overrides_option_map(key: str) -> dict:
    """Domeniu -> valoarea cheii OPTIONALE `key` din payload-ul `overrides`.

    AMZ-1a. Pana acum nu exista niciun accesor generic peste cheile optionale din
    `overrides`: fiecare consumator facea manual
    `DOMAIN_OVERRIDES.get(match_shop_domain(...)) or {}` si apoi `.get(cheie)`
    (vezi product_page_extractor, la `vat_prices`). Poarta de fetch retail are
    nevoie de doua astfel de chei, iar a treia copie a tiparului ar fi fost locul
    in care apar divergentele.

    Intoarce doar domeniile care CHIAR au cheia, exact ca `impersonate_overrides`
    si `domain_overrides`, ca apelantul sa poata deriva o harta o singura data la
    import si sa nu plateasca nimic pe domeniile fara cheie.

    Copie adanca din acelasi motiv ca la `domain_overrides`: valoarea poate fi un
    tuplu (imutabil) dar si o lista (mutabila), iar o referinta ar lasa un bug din
    consumator sa rescrie registrul pentru tot procesul.
    """
    return {domain: copy.deepcopy(meta["overrides"][key])
            for domain, meta in SHOP_REGISTRY.items()
            if isinstance(meta.get("overrides"), dict) and key in meta["overrides"]}


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


def catalog_api_domains() -> set[str]:
    """Domeniile cu descriptor de API de catalog (VAL D / `api_enum`).

    Apartenenta se decide din PREZENTA cheii `catalog_api`, exact ca la
    `listing_domains`: un magazin poate fi citit prin `jsonld` la nivel de produs
    SI, separat, enumerat prin API-ul lui de catalog — capabilitati independente.
    """
    return {domain for domain, meta in SHOP_REGISTRY.items()
            if "catalog_api" in meta}


def catalog_api_descriptor(domain: str) -> dict | None:
    """Descriptorul de API al unui domeniu, copiat adanc — acelasi motiv ca la
    `listing_descriptor`: scannerul il plimba prin functii, iar o referinta ar lasa
    un bug de acolo sa rescrie registrul pentru tot procesul."""
    meta = SHOP_REGISTRY.get(domain) or {}
    return copy.deepcopy(meta["catalog_api"]) if "catalog_api" in meta else None


def search_domains() -> set[str]:
    """Domeniile care se pot cauta dupa termen (SEARCH-1).

    Apartenenta se decide din PREZENTA cheii `search`, ca la `listing_domains` si
    `catalog_api_domains`: cautarea e o capabilitate independenta de metoda de
    citire a paginii de produs. Un magazin poate fi `jsonld` la nivel de PDP si,
    separat, cautabil prin API-ul lui de platforma — sau invers, citibil doar prin
    link, fara cautare.
    """
    return {domain for domain, meta in SHOP_REGISTRY.items() if "search" in meta}


def search_kind_of(domain: str) -> str | None:
    """Mecanismul de cautare al unui domeniu, sau None daca n-are `search`.

    Lookup direct, fara copie — acelasi motiv ca la `url_identity_of`: valoarea e
    un scalar imutabil, deci n-are cum sa fie mutata de apelant.
    """
    return ((SHOP_REGISTRY.get(domain) or {}).get("search") or {}).get("kind")


# Cheile din `listing` care NU au voie sa ajunga in descriptorul de cautare.
#
# Primele patru sunt strict de LISTARE: descriu plimbarea prin paginile de reduceri
# (`url` de intrare, sablonul de paginare, plafonul de pagini) si semantica referintei
# de pret pe acele pagini. Pe o cautare n-au niciun sens — `url_template` ii ia locul
# lui `url`, iar paginarea cautarii nici nu e masurata inca.
_LISTING_DOAR_LISTARE = ("url", "page_url_template", "max_pages", "reference_kind")

# Cheile de PRET se scot pe toate, chiar daca descriptorul de cautare declara doar
# una. Motivul e D6 si e masurat la SEARCH-0: descriptorii de listare sunt scrisi
# pentru pagini de REDUCERI, unde fiecare produs poarta un pret taiat. Pe o pagina de
# CAUTARE majoritatea produselor sunt la pret intreg, iar selectorul de reduceri
# prinde 1 din 60 (noriel) sau 0 din 24 (otter) — cardurile cad in tacere, fiindca
# `extrage_carduri` arunca orice card fara pret valid.
#
# Se scot TOATE, nu doar cele redeclarate: altfel un `search` care declara `price_text`
# ar mosteni `compare_attr` din listare si ar citi referinta cu selectorul paginii de
# reduceri peste pretul citit cu al paginii de cautare — o pereche care n-a fost
# masurata impreuna niciodata. Pretul se declara, nu se mosteneste.
_LISTING_PRET = ("price_text", "price_attr", "compare_text", "compare_attr",
                 "price_parse")


def search_descriptor(domain: str) -> dict | None:
    """Descriptorul EFECTIV de cautare, gata de folosit, copiat adanc.

    Pe `kind != "descriptor"` e pur si simplu copia lui `search`. Pe "descriptor"
    e `listing` (fara cheile de mai sus) suprascris de `search`: forma cardului
    (card, link, title, image, image_attr, currency) se mosteneste, pentru ca acolo
    e aceeasi grila de produse, dar pretul vine exclusiv din `search`.

    Copia e obligatorie din acelasi motiv ca la `listing_descriptor`: consumatorul
    il plimba prin functii, iar o referinta ar lasa un bug de acolo sa rescrie
    registrul pentru tot procesul.
    """
    meta = SHOP_REGISTRY.get(domain) or {}
    if "search" not in meta:
        return None
    descriptor = copy.deepcopy(meta["search"])
    if descriptor.get("kind") != "descriptor":
        return descriptor
    baza = copy.deepcopy(meta.get("listing") or {})
    for cheie in _LISTING_DOAR_LISTARE + _LISTING_PRET:
        baza.pop(cheie, None)
    baza.update(descriptor)
    return baza


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
