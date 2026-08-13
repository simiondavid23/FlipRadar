# Jurnalul sondelor per domeniu

Acesta e jurnalul ISTORIC al sondelor per-domeniu: de ce a intrat fiecare magazin
in catalog, ce forma de date publica, ce s-a masurat efectiv si ce s-a infirmat pe
parcurs. Textul e mutat aici verbatim din comentariile care insoteau structurile
`VALIDATED_DOMAINS`, `DOMAIN_OVERRIDES` (product_page_extractor.py) si
`_IMPERSONATE_OVERRIDES` (scraper_service.py), la REG-2.

Sursa canonica a starii CURENTE e `backend/app/services/shop_registry.py` — acolo
se citeste ce e validat acum, cu ce metoda si cu ce treapta de impersonate. Aici se
citeste cum s-a ajuns acolo.

Regula ramane neschimbata: un domeniu intra in catalog DOAR dupa o sonda live,
niciodata pe presupunere — o extractie gresita ar scrie preturi false in istoric.
Orice val nou adauga o sectiune aici.

---

## RETAIL-3a

Sonda 2026-07-26. Domeniile pe care extractorul a fost validat pe pagini de produs
REALE. `refresh_source` le reimprospateaza citind direct pagina de produs; celelalte
raman pe re-cautare.

**altex.ro** — 3/3 pagini extrase prin JSON-LD, pret identic cu cel din lista de
cautare.

**emag.ro** — 5/5 pagini extrase prin JSON-LD.

> LIMITARE CUNOSCUTA (sonda RETAIL-5, 2026-07-26) — NU e legata de Genius, cum
> se banuia la RETAIL-3a: pe paginile cu MAI MULTE oferte eMAG afiseaza
> "de la <cel mai mic pret>", in timp ce JSON-LD poarta oferta principala.
> Exemplu masurat (Lenovo IdeaPad Slim 3, 2 oferte): afisat 3.459,99 lei,
> JSON-LD 5689.42. Pe paginile cu o singura oferta relevanta, JSON-LD = afisat.
> Niciun regex pe starea JS incorporata nu acopera ambele cazuri: EM.product
> da oferta principala (gresit pe multi-oferta), iar EM.multiple_min_price si
> datalayer-ul dau minimul altor oferte (gresit pe restul). Ce a mers 5/5 pe
> ambele tipuri de pagina e selectorul pretului afisat, ".product-new-price"
> — REZOLVAT in RETAIL-5b: vezi DOMAIN_OVERRIDES["emag.ro"] mai sus.

### Override de continut: emag.ro (sonda RETAIL-5b)

Jurnalul intrarii `emag.ro` din `DOMAIN_OVERRIDES`:

> eMAG — sonda RETAIL-5b (2026-07-26): 5/5 egalitate cu pretul din lista de
> cautare, inclusiv pe o pagina multi-oferta unde JSON-LD dadea 5689.42 iar
> afisat era "de la 3.459,99" (selectorul a reparat divergenta).
>
> DE CE selector si nu price_regex: cauza divergentei NU e Genius (ipoteza de
> la RETAIL-3a, infirmata), ci paginile cu mai multe oferte — eMAG afiseaza
> "de la <minim>", pe cand JSON-LD si starea JS `EM.product` poarta oferta
> PRINCIPALA. Regexurile pe starea incorporata esueaza fiecare pe cate un tip
> de pagina (masurat in RETAIL-5); doar elementul afisat e corect pe ambele.
> Textul vine spart in span-uri ("3.459 , 99 Lei"), pe care _parse_price_any
> il recompune corect.
>
> NUANTA ACCEPTATA: pe paginile multi-oferta pretul devine cel afisat, dar
> `in_stock` ramane cel din JSON-LD, adica al ofertei PRINCIPALE, nu al
> ofertei minime. Stocul e tri-state si informativ; pretul e cel care intra
> in istoric si in alerte, deci prioritatea e corectitudinea lui.

---

## RETAIL-5c

Al doilea val (sonda RETAIL-5c, 2026-07-26).

> Toate trei extrag prin JSON-LD, FARA override. Regula valului: un link mort
> (fetch esuat / 404) se raporteaza dar nu descalifica domeniul; doar o parsare
> esuata pe o pagina care s-a incarcat corect descalifica. Intrare cu >=2 OK.

**cel.ro** — 2/2 JSON-LD. Include prima confirmare LIVE a ramurii negative de
disponibilitate (in_stock=False citit corect din availability).

**vexio.ro** — 3/3 JSON-LD.

**mediagalaxy.ro** — 2/3 JSON-LD; al treilea URL era un resigilat vandut intre timp
(404 = link mort, raportat fara sa descalifice). Platforma comuna cu altex.ro.

---

## FASHION-1b

Valul fashion (sonda FASHION, 2026-07-26).

> Primul val care aduce si magazine cu MARIMI. Doua forme masurate:
> Product simplu (answear, fashiondays) si ProductGroup cu hasVariant
> (eobuwie), citit de FASHION-1b — vezi _candidate_from_group.

**answear.ro** — 2/2 JSON-LD Product. Publica si o lista de marimi (`size` =
['S','M',...]), dar FARA oferta per marime: nu se pot deriva variante, deci ramane
produs simplu.

**fashiondays.ro** — 3/3 JSON-LD Product. EdgeOne trecut de pe IP rezidential (sonda
ruleaza cu impersonate). Include o confirmare LIVE a ramurii negative: un
in_stock=False citit corect din availability.

**epantofi.ro** — 3/3. Pana la FASHION-1b cadea pe OG — suspect pret de LISTA,
fiindca grupul nu expune pret la nivel de produs; dupa ProductGroup pretul vine din
oferta per marime (minimul marimilor in stoc).

**modivo.ro** — 3/3, identic cu epantofi: aceeasi platforma (eobuwie), acelasi
ProductGroup.

---

## FASHION-2

Al treilea val (sonda FASHION-2, 2026-07-26).

**bstn.com** — 4/4 JSON-LD. Forma #2 a variantelor: UN Product cu `offers` = lista de
oferte, fiecare cu `size` propriu (fara ProductGroup) — vezi
_variants_from_offer_list. Storefront-urile sunt path-uri (us_en / eu_en) cu
valute diferite (USD / EUR), acoperite de conversia BNR. ATENTIE la ce s-a
schimbat: pana la FASHION-2 pretul citit era al PRIMEI marimi din lista
(adesea epuizata); acum e minimul marimilor in stoc.

**en.afew-store.com** — 2/2 JSON-LD, pret product-level (offers-lista cu un singur
element, fara size) — deci ramane produs simplu, fara variante. Intrarea e CU
subdomeniu: _domain_of taie doar "www.", iar refresh-ul compara pe egalitate exacta.

---

## FASHION-2b

Completare val 3 (micro-sonda FASHION-2b, 2026-07-26).

> Ambele au atins pragul de 2 URL-uri OK. Zero mecanism nou: formele lor sunt
> deja acoperite de extractor.

**prm.com** — 2/2 JSON-LD product-level pe doua sonde. Forma answear: lista de marimi
FARA oferte per marime -> variants ramane None (nu fabricam variante din
marimi necotate). Localizarea /ro e path, deci cheia exacta ramane curata.

**sneakersnstuff.com** — 2 URL-uri OK (storefront-urile en-int si en-eu); path-ul
vechi /en/product/ da 404 = link mort, care prin regula valului nu descalifica.
offers-lista FARA `size` pe elemente — exact regresia pinuita in FASHION-2: ofertele
neetichetate raman neexploatate, pretul e "primul cu pret", ca inainte.

---

## FASHION-4

Valul FASHION-4 (sonda 2026-07-28).

> Cele doua domenii ratate la FASHION-1/FASHION-2 pentru servire inconsistenta,
> re-auditate: 8 URL-uri x 3 incercari per domeniu, 24/24 OK fiecare. Pe TOATE
> cele 48 de raspunsuri ld+json era prezent (2 blocuri/pagina), iar HTML-ul a
> venit identic la octet intre incercarile aceluiasi URL. Servirea inconsistenta
> din 2026-07-26 NU s-a reprodus, deci regula valului (o parsare esuata pe o
> pagina incarcata corect descalifica) nu mai are ce descalifica.
> In acelasi commit s-a adaugat retry-ul defensiv pe no_product_data din
> extract_product, ca o eventuala recidiva sporadica sa fie absorbita.

**aboutyou.ro** — ProductGroup cu hasVariant (forma stiuta din FASHION-1b), preturi
RON.

**trendyol.com** — Product simplu, preturi RON pe /ro/.

---

## ACCESS-2

Valul ACCESS-2 (sondele ACCESS-1/1b, 2026-07-28).

> Primul val intrat pe baza unei matrice de ACCES, nu doar de parsare: ACCESS-1
> a incercat 6 trepte de impersonate (chrome131/136/146/latest, firefox135,
> safari260) x domeniu ca sa gaseasca treapta care deschide fiecare site, iar
> ACCESS-1b a validat apoi extractia pe un set NOU de pagini, cu pretul comparat
> manual cu cel AFISAT in browser: 3/3 match per domeniu. Toate trei extrag prin
> JSON-LD, fara override de continut.

**endclothing.com** — chrome131 (default), JSON-LD, preturi EUR.

**zalando.ro** — chrome131 (default), JSON-LD, preturi RON. Oferta e agregata
(is_aggregate), dar pretul agregat coincide cu cel afisat — deci trece, spre
deosebire de multi-oferta eMAG, unde tocmai divergenta a cerut price_selector.

**43einhalb.com** — firefox135, NU default: pe toate treptele chrome ia 403. Treapta
vine din _IMPERSONATE_OVERRIDES (scraper_service), deci domeniul e citibil doar prin
poarta guarded. JSON-LD, preturi EUR.

> Jurnalul intrarii din `_IMPERSONATE_OVERRIDES`:
>
> ACCESS-1/1b (2026-07-28): 403 challenge pe toate treptele chrome
> (131/136/146/latest); trece curat pe firefox135, 3/3 match de pret.

---

## CONTENT-2

Valul CONTENT-2 (sondele CONTENT-1/1b, 2026-07-28).

> Doua domenii ratate anterior, amandoua reabilitate prin ANALIZA DUMP-ULUI, nu
> prin insistenta: unul avea o concluzie gresita, celalalt o sursa necitita.

**flanco.ro** — firefox135 via _IMPERSONATE_OVERRIDES; extrage prin OG (site-ul nu
publica ld+json deloc, ldjson=0). 8/8 match cumulat pe doua sonde, inclusiv pe produse
cu reducere, unde OG da pretul PLATIT, nu cel taiat.
MISMATCH-ul din ACCESS-1b (extras 5199.00 vs "afisat" 5468.99) a fost EROARE DE
PROTOCOL, nu de extractie: pretul asteptat fusese notat ca cel taiat. Dump-ul
arata pagina consistenta pe 5199.00 in toti cei 5 purtatori de pret (OG,
meta itemprop, price_info, gtmProduct, DOM), iar 5468.99 sta in
`.pretVechiTaiat` — referinta Omnibus pe 30 de zile; diferenta 269.99 e exact
"Economisesti" din pagina.

> Jurnalul intrarii din `_IMPERSONATE_OVERRIDES`:
>
> ACCESS-1/1b (2026-07-28): aceeasi situatie de acces — chrome pica pe paginile
> de produs, firefox135 trece. ACTIV de la CONTENT-2: flanco.ro a intrat in
> VALIDATED_DOMAINS, deci e in allow-list-ul C-14 si chiar se cere prin poarta
> guarded. Fara treapta de aici, domeniul ar fi validat dar necitibil (403).

**evomag.ro** — chrome131; publica pretul EXCLUSIV in microdata — ld+json nu are
niciun Product (doar BreadcrumbList/ElectronicsStore/Organization/WebSite) si nu
exista nici og:title, nici og:price. Un singur `itemprop=price` per pagina, cu
`content` in format masina, plus priceCurrency=RON si availability publicate. 3/3
match prin fallback-ul de microdata adaugat in acest commit.

---

## DISCOVERY-2

Valul DISCOVERY-2 (sondele DISCOVERY-1/1b, 2026-07-28).

**footshop.ro** — chrome131; microdata camelCase (itemProp/itemScope/itemType, SSR
React) in HTML-ul INITIAL — nu e nevoie de browser. Clasificarea "CSR confirmat" din
FASHION-2 a fost ARTEFACT DE MASURARE: cautarea de markere era case-sensitive
pe HTML brut (`itemprop` da 0, `itemProp` da 41), iar fallback-ul de microdata
nici nu exista atunci — a intrat abia la CONTENT-2. Pretul curent poarta
itemProp; cel taiat NU, deci nu poate fi confundat. Stocul vine din
`<link itemProp="availability" href=...>`, RON.

**asos.com** — extractor CUSTOM (vezi CUSTOM_EXTRACTORS): numele din ld+json-ul
paginii (Product fara `offers`), iar pretul/stocul/moneda din API-ul public
stockprice cu codurile RO (ROE/EUR/RO), fara cookie-uri. Preturi EUR.

---

## SHOP-1a

Sondele Grup 1 (2026-08-12) si SHOP-1a (2026-08-13). Primul val intrat pe baza
PLATFORMEI, nu a formei de date din pagina: 13 magazine Shopify cu endpoint de
enumerare deschis, validate apoi pe extractie per-produs.

Rezultatul sondei de validare: **38/39 produse MATCH** (3 handle-uri per domeniu,
candidatul comparat cu pretul afirmat de pagina in ld+json/OpenGraph). Zero domenii
fara referinta — toate cele 13 publica ld+json cu pret. Monede masurate prin
`/cart.js`, incrucisate cu `priceCurrency` din pagini, consistente peste tot:
EUR x7, RON x5, SEK x1 (caliroots).

### Descoperirea care a dictat implementarea: `.js`, nu `.json`

Endpoint-ul per-produs `/products/<handle>.json` **nu poarta deloc campul
`available`** — 0 din 39 de produse, pe toate cele 13 domenii. Variantele lui au
`inventory_management`, dar nimic despre disponibilitate, deci regula FASHION-2
(pretul minim al marimilor DISPONIBILE) e imposibil de aplicat pe el. Endpoint-ul
Ajax `/products/<handle>.js` il poarta 13/13. In schimb formatul pretului difera:

| | `/products/<h>.json` | `/products/<h>.js` |
|---|---|---|
| `available` per varianta | absent (0/39) | prezent (13/13) |
| format pret | string zecimal `'248.61'` | int in unitati minore `24861` |

Conversia ÷100 s-a validat singura: 38/39 potriviri cu pretul afirmat de pagina,
zero anomalii de format pe candidat (321/321 variante cu `price` int).

### nakedcph.com — singurul mismatch, si nu al magazinului

Produsul `nike-nike-shox-tl-se-black-black-black-ir2097-001`, cu 8/8 variante
disponibile: candidatul din Ajax e 182.95, iar ld+json-ul paginii declara
`{"price": "183", "priceCurrency": "EUR"}`. Pagina AFISEAZA 182,95 (22 aparitii in
HTML), deci candidatul e cel corect — tema publica pretul rotunjit la intreg in
ld+json. Celelalte doua produse nakedcph au preturi rotunde (80, 50), unde
rotunjirea e invizibila; de aici 2/3. Verdict: VALIDAT, cu nota in registru ca
ld+json-ul acestui domeniu e nesigur ca sursa de tracking.

### Doua erori de MASURARE ale sondei, gasite si corectate

Amandoua au produs verdicte false inainte de a fi prinse; se noteaza fiindca sunt
capcane care se pot repeta la valurile urmatoare.

1. **Virgula zecimala in referinte.** Parserul de referinta cerea `\d+(\.\d+)?`,
   deci arunca ofertele ld+json scrise `'248,61'`. rocashoes.ro iesea 0/3, cu
   "referinte" de 24861 — aceleasi cifre fara virgula, de pe variantele epuizate.
   Dupa corectie: 3/3 MATCH. Formatul cu virgula apare la 18 din 39 de produse, deci
   nu e o ciudatenie a unui singur magazin.
2. **Endpoint-ul gresit pentru candidat.** Prima rulare deriva candidatul din
   `.json` si raporta 39/39 produse epuizate — implauzibil pentru 13 magazine vii,
   de unde s-a prins lipsa campului `available`.

### Limitare asumata

La niciunul dintre cele 39 de produse `min(disponibile)` n-a diferit de
`min(toate)`: cea mai ieftina marime era mereu in stoc. Regula FASHION-2 e deci
implementata si exercitata (35 de produse aveau date de disponibilitate), dar
ramura in care regula chiar DISCRIMINEAZA n-a aparut live. E acoperita offline, pe
payload sintetic, de `test_pret_minim_al_marimilor_disponibile` din
`test_shopify_extractor.py`.

### Nota despre afew

Domeniul gol `afew-store.com` redirecteaza spre storefront-ul `de.*`, iar
`en.afew-store.com` (deja in catalog de la FASHION-2) enumereaza identic: acelasi
handle, acelasi pret, aceeasi disponibilitate. Ramane o singura intrare, cea cu
subdomeniu; domeniul gol nu se adauga.

## LOT1

Sonda 2026-08-13, lotul 2a (electronice RO), 8 domenii. Primul val in care sonda
NU si-a reimplementat parsarea: a IMPORTAT `parse_product_html` si a rulat-o pe
HTML-ul capturat (functia e pura), deci intrebarea masurata a fost "extractorul
EXISTENT le citeste corect?", nu "s-ar putea citi?".

Toate cele 8 domenii au raspuns pe treapta implicita `chrome131`. Nicio escaladare
de impersonate, niciun BLOCAT, niciun MORT.

### Verdicte

| domeniu | URL-uri OK | metoda | verdict |
|---|---|---|---|
| itgalaxy.ro | 3/3 | jsonld | validat |
| carrefour.ro | 3/3 | jsonld | validat |
| flip.ro | 3/3 | jsonld | validat, `url_identity: exact` |
| usedproducts.ro | 3/3 | jsonld | validat |
| senetic.ro | 3/3 | jsonld | validat, override `vat_prices` |
| pcgarage.ro | 3/3 | microdata | validat DUPA fixul de scopare |
| orange.ro | 0/3 | — | probed (Grup 4) |
| powerup.ro | 0/3 | — | probed (Grup 3) |

### pcgarage.ro — blocat de o regula de-a noastra, nu de site

Paginile publica microdata completa: un singur scope Product, un singur
`itemprop="price"` cu `content` in format masina, `priceCurrency=RON`,
`availability`, `sku`, `mpn`, `brand`, `name`. Rulat pe dump, `_collect_microdata`
dadea pret/moneda/stoc CORECTE si cadea doar pe nume, iar garda de nume din
`parse_product_html` ridica `no_product_data` inainte sa se uite la pret.

Cauza: in scope-ul Product exista DOUA `itemprop="name"` — `<td>`-ul produsului si
un `<meta itemprop="name" content="Lenovo">` care apartine obiectului NESTED
`itemprop="brand"`. Regula "un singur candidat, sau h1-ul dintre mai multi" vedea
doi si niciun h1.

Fixul: scopare nested standard (un element apartine root-ului daca cel mai apropiat
stramos cu `itemscope` E root-ul), aplicata DOAR la nume.

DE CE doar la nume, si nu uniform pe toate campurile: pretul, moneda si stocul
apartin PRIN DESIGN obiectului nested `offers` — asa e si pe pcgarage, si pe
evomag, exact ca `Product.offers.price` din JSON-LD. Masurat inainte de
implementare: filtrarea uniforma da (1 nume, 0 preturi) pe AMANDOUA, adica ar fi
rupt si evomag, domeniu validat din CONTENT-2. Filtrarea doar pe nume da (1, 1) pe
amandoua. Numai `name` are coliziune reala, fiindca doar `brand` poarta o
proprietate cu acelasi nume.

Preturile extrase dupa fix — 5498.99 / 2249.99 / 1136.92 — coincid exact cu ce
intoarce parserul dedicat `fetch_pcgarage_price_from_url` pe aceleasi URL-uri, deci
refresh-ul a migrat pe calea generica (ordinea din `refresh_source` o face automat:
ramura domeniilor validate precede ramura pcgarage). Ramura dedicata ramane
fallback istoric.

La URL-ul cu ancora de desigilat (`#u38312673`), purtatorii structurati poarta DOAR
produsul nou — oferta resigilata nu e distinsa in microdata.

### flip.ro — `?shape=` e semantic, deci starea e parte din identitate

Aceeasi pagina, acelasi produs:

| URL | pret extras |
|---|---|
| `.../75268382/?shape=Excelent` | 2999.99 |
| `.../75268382/` (fara shape) | 2849.99 |

Datele structurate URMEAZA parametrul. De aici campul `url_identity: "exact"` din
registru: la salvarea sursei se pastreaza URL-ul lipit de user (fara fragment, care
e stare de UI) si se IGNORA canonicalul — altfel am urmari tacut alt pret decat cel
vazut.

### senetic.ro — preturi duale, decizia de a le pastra pe amandoua

Toate trei paginile poarta doua preturi, in raport EXACT 1.21:

| produs | ld+json | microdata | raport |
|---|---|---|---|
| AD1J1ET | 3394.59 | 4107.45 | 1.21 |
| DELL-U4025QW | 8146.23 | 9856.94 | 1.21 |
| UCK-G2-SSD | 1152.62 | 1394.67 | 1.21 |

Adica TVA 21%: ld+json publica NETUL, microdata BRUTUL. Cu precedenta normala am fi
luat sistematic netul — un pret cu 21% sub cel platit, deci fiecare produs senetic
ar fi parut chilipir intr-un comparator.

Decizia: pastram AMANDOUA, prin masinaria de variante din FASHION-1b. Override-ul
`vat_prices` face `price` = brutul (comparabilul de consumator) si expune
`variants` = ["cu TVA", "fara TVA"], deci selectia per-marime din add-by-link
functioneaza din prima. Garda de sens (brut strict mai mare ca netul, ambele
valide) tine flag-ul inofensiv pe o pagina care nu se comporta asa.

### orange.ro vs powerup.ro — doua feluri de "fara date"

Ies amandoua fara purtatori, dar NU sunt acelasi caz:

- **orange.ro** — CSR real. 339 KB de HTML, titlu GENERIC ("Orange Magazin Online",
  fara numele produsului), zero ld+json, zero `itemprop` in ambele scrieri (lower si
  camelCase — verificat dupa lectia footshop), zero clase de pret, zero stare JS
  incorporata. Shell-ul nu poarta nimic despre produs. **Grup 4** (necesita browser).
- **powerup.ro** — SSR fara date structurate. Titlurile SUNT specifice produsului,
  iar pretul E in DOM: `.discount-price` = "3.990 ,00 LEI" (platit), `.full-price` =
  "5.590 ,00 LEI" (taiat). **Grup 3**, candidat de `price_selector`.
  CAPCANA pentru cine implementeaza: exista si `.total-price` = "0 ,00 LEI", totalul
  cosului gol — un selector prea lax ar extrage 0. De aceea intrarea cere o
  micro-sonda pe produse NEreduse inainte de validare.

### usedproducts.ro

Toate trei `https://schema.org/InStock`, extrase corect (299.99 / 350.00 / 599.99).
Fiind bucati unice second-hand, un "vandut" ar fi permanent — dar sonda NU a
intalnit niciun produs vandut, deci comportamentul paginii in acel caz ramane
NEMASURAT.

### badabum.ro — ELIMINAT

Site mort, confirmat manual de David in 2026-08. Scos din lot inainte de sonda,
deci nu apare in masuratori. Reverificare optionala la un val viitor.

---

## Domenii neintrate

> NU sunt validate: sole.ro si farmaciatei.ro (degradate la sonda RETAIL-1 — 502 pe
> pagina de produs, respectiv cautare goala) si pcgarage.ro (n-a avut URL-uri de
> produs la sonda RETAIL-3a; refresh-ul lui ramane pe fetch_pcgarage_price_from_url,
> care trece de Cloudflare cu retry).
>
> Ratate in valul RETAIL-5c: flanco.ro si evomag.ro — amandoua PROMOVATE la valul
> CONTENT-2 (sondele 2026-07-28). Vezi nota valului din VALIDATED_DOMAINS.
>
> Ratate in valurile FASHION-1 si FASHION-2 (sonde 2026-07-26):
>   aboutyou.ro si trendyol.com — PROMOVATE la valul FASHION-4 (sonda 2026-07-28):
>                  servirea inconsistenta care le descalificase nu s-a reprodus.
>                  Vezi nota valului din VALIDATED_DOMAINS.
>   footshop.ro  — PROMOVAT la valul DISCOVERY-2: "CSR confirmat" a fost artefact de
>                  masurare, nu realitate. Vezi nota valului din VALIDATED_DOMAINS.
>   sole.ro      — RECLASIFICAT: nu e magazin de fashion, deci nu apartine acestor
>                  valuri. Ramane in backlogul general (degradat de la RETAIL-1: 502).
