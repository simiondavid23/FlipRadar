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

## LOT2 / LOT2b

Doua sonde, 2026-08-13, pentru lotul tintelor usoare straine. LOT2 si-a DESCOPERIT
singura produsele; LOT2b a completat pe link-uri manuale ce descoperirea n-a scos.
Toate domeniile care au raspuns au facut-o pe treapta implicita de impersonare.

### Verdicte

| domeniu | sonda | confirmate | metoda | moneda | verdict |
|---|---|---|---|---|---|
| computeruniverse.net | LOT2 | 3/3 | jsonld | EUR | validat |
| jb-spielwaren.de | LOT2 | 3/3 | jsonld | EUR | validat |
| caseking.de | LOT2b | 3/3 | jsonld | EUR | validat |
| bergfreunde.eu | LOT2b | 3/3 | jsonld | EUR | validat |
| alternate.de | LOT2b | 3/3 | jsonld | EUR | validat |
| foto-erhardt.com | LOT2b | 3/3 | jsonld | EUR | validat |
| hhv.de | LOT2 | 0/3 | — | — | probed (Grup 4) |

Cele patru domenii completate manual la LOT2b esuasera la LOT2 din cauza
MECANISMULUI de descoperire, nu a magazinelor — paginile lor de produs se extrag
curat din prima.

### Descoperirea — doua defecte reparate in runda de sonda

Prima rulare LOT2 a dat 6/7 esecuri. Sapte magazine sparte simultan fiind
implauzibil, ipoteza a fost defectul propriu — confirmata de doua ori:

1. **Ordinea candidatilor.** Ancorele erau luate in ordinea din document; pe o
   pagina de outlet primele zeci sunt header/nav, iar grila de produse vine mult
   mai jos. Masurat: bergfreunde a dat 1232 de candidati, iar cei 11 incaputi in
   buget erau toti nav. Reparat cu un scor GENERIC de probabil-produs (adancimea
   caii, cifra in ultimul segment, slug lung, text de ancora lung), minus o
   penalizare structurala pentru URL-urile care sunt prefix pentru >=3 alti
   candidati (hub de categorie).
2. **Detectorul de pagina de produs, prea larg.** Regula era "exista cel putin un
   Product in ld+json". Paginile de LISTA emit cate un Product per card: caseking
   /pc-systeme si /neuheiten poarta 40 fiecare si treceau drept produse. Strans la
   EXACT un Product — aceeasi disciplina de ambiguitate ca a extractorului.

Efect: 0 domenii validate -> 2 validate + 1 partial, si bugetul consumat a scazut.

### Lectii pentru loturile viitoare (~40 de domenii ramase)

- **Challenge servit pe 200.** hhv.de raspunde 200 cu ~2KB de JavaScript obfuscat,
  zero ancore, fara titlu. Detectorul clasic (403 / cf-mitigated / fraze cunoscute)
  il rateaza si domeniul apare ca "descoperire esuata" in loc de "blocat". Regula
  adaugata: corp mic + zero ancore + fara titlu = challenge.
- **Fatete in CALE, nu in query.** bergfreunde publica filtrele ca
  `/outlet/properties--2-way-front-zip/` si `/outlet/brands/7mesh/`. Un filtru care
  se uita doar la query string nu le vede. Semnale: `--` intr-un segment, hub-uri
  de tip `/brands/`.
- **Segmente fara structura silabica.** Candidatul de top la alternate era
  `/adc/baacb452-28ae-4b64-bb5a-55d02c9e0c07`, un UUID de tracking premiat gresit
  de euristica "are cifre". De penalizat, nu de premiat.
- **`sku`/`mpn` ca semnal INTARITOR.** Paginile de produs reale de la caseking
  poarta ambele (`HPIT-805`), pe cand categoriile care se declara Product cu pret
  "de la" (cele care au pacalit detectorul) nu le au. De adaugat in detector.

### bergfreunde.eu — variatie BIDIMENSIONALA, si bug-ul pe care il inchide

Masurat: `variesBy: ["https://schema.org/size", "https://schema.org/color"]`, cu
24 de variante (8 marimi x 3 culori), 15 si 52 pe celelalte doua produse. Fiecare
varianta poarta `size`, `color` si `sku` propriu, iar preturile DIFERA pe culoare
la aceeasi marime:

| marime | culoare | pret | in stoc |
|---|---|---|---|
| S | Olive Green | 67.96 | da |
| S | Summer Blue | 67.96 | nu |
| S | Timber Red | **63.96** | nu |

Etichetate doar cu `size` — cum facea extractorul — cele trei "S" erau NEunice, iar
selectia per-varianta din `create_product_from_url` ia PRIMA potrivire. Userul care
alegea "S" primea tacut pretul si stocul altei culori. Bug preexistent, vizibil
abia acum, fiindca toate grupurile de pana acum variau pe o singura dimensiune.

Decizia: **eticheta compusa** din dimensiunile declarate in `variesBy`, in ordinea
lor ("S / Olive Green"). Refoloseste integral masinaria variantă-ca-string
(FASHION-1c: etichete string liber, fara normalizare), e unica SI lizibila, si nu
schimba schema. Compunerea se activeaza DOAR la mai mult de o dimensiune, deci
grupurile masurate anterior (eobuwie, About You) raman byte-identice.

LIMITA CONSTIENTA: pe un grup care produce etichete duplicate FARA sa declare
`variesBy` multi, coliziunea ramane — n-avem din ce compune. Cazul n-a fost
intalnit; daca apare, se rezolva cu `sku`-ul variantei (care E unic), nu prin
ghicirea dimensiunilor.

Testul `?sel=color`: 159.95 cu query, 159.95 fara — IDENTICE. Spre deosebire de
flip.ro, aici query-ul e stare de UI pentru preselectia culorii, nu semantica, deci
bergfreunde NU are nevoie de `url_identity: "exact"`.

### foto-erhardt.com — starea traieste doar in cale

Nici macar bucata Second Hand nu poarta `itemCondition`; toate trei paginile au
`availability: InStock`. Singurul semnal ca produsul e folosit sta in CALE
(`/second-hand/`) si in nume. Daca vrem starea la implementare, se ia din URL, nu
din date. Hostul a ramas `.com` — niciun redirect spre `.de`, contrar ipotezei.
Bucatile fiind unice, un "vandut" ar fi permanent, dar sonda n-a intalnit niciunul,
deci comportamentul in acel caz ramane NEMASURAT (aceeasi limita ca la
usedproducts.ro).

### caseking.de

Storefront-ul `/en/` e localizat LINGVISTIC, moneda ramane EUR (nu GBP). `canonical`
taie query-ul de tracking `_gl`, deci comportamentul implicit (preferinta pentru
canonical) e corect si domeniul nu are nevoie de `url_identity`.

### Nota

badabum.ro a fost deja consemnat ca ELIMINAT la LOT1 (site mort, confirmat manual).

## LOT3 / LOT3b

Doua sonde, 2026-08-13, pentru lotul 2c — fashion/incaltaminte RO. Nucleul
categoriei era deja validat din valurile FASHION; lotul acopera restul.

### Verdicte

| domeniu | sonda | confirmate | metoda | moneda | verdict |
|---|---|---|---|---|---|
| buzzsneakers.ro | LOT3 | 3/3 | jsonld | RON | validat |
| officeshoes.ro | LOT3 | 3/3 | microdata | RON | validat |
| otter.ro | LOT3b | 3/3 | jsonld | RON | validat |
| spartoo.ro | LOT3b | 3/3 | jsonld | RON | validat |
| boozt.com | LOT3b | 2/2 | jsonld | EUR | validat |
| booztlet.com | LOT3b | 3/3 | jsonld | EUR | validat |

### Descoperirea — verdictul de maturitate: NU

LOT3 era testul de maturitate al mecanismului de descoperire: a doua rulare, cu
lectiile LOT2/LOT2b incorporate de la inceput. Rezultat: **2 din 6**, deci NU devine
standardul Fazei 2 in forma actuala; restul lotului a trecut pe link-uri manuale.

Ce a lucrat: fatetele in cale au filtrat masiv (126 pe officeshoes, 202 pe otter);
detectorul strans a respins corect listele intalnite. Ce a lipsit: pe fashion,
taxonomiile de categorie sunt adanci si cu sluguri lungi — exact ce premia scorul
de forma a URL-ului, deci categoriile urcau in top. Semnal adaugat in runda:
**cardul de produs are miniatura**, link-ul de navigatie rareori (masurat pe otter:
103 ancore cu `<img>` vs 453 fara). Efect: officeshoes 0 -> 3/3.

Oprire deliberata dupa a doua iteratie: a treia ar fi insemnat reglaj pe cele sase
magazine din lot, adica supra-potrivire, nu mecanism.

### RETRAGEREA discriminatorului `url`/`@id`

Raportul LOT3 propunea, pentru descoperirea v3, ca produsul principal sa fie
identificat prin `url`/`@id` egal cu URL-ul paginii. Masurat la LOT3b: **zero**
dintre Product-urile otter poarta `url` sau `@id`. Discriminatorul nu poate
functiona; propunerea se retrage.

### CORECTIA raportului LOT3b — nu exista "a treia forma"

Raportul LOT3b a descris otter ca "ProductGroup + Product-uri FRATI cu sku comun,
o a treia forma structurala". **Ambele afirmatii erau artefacte ale sondei:**

1. Walker-ul recursiv al sondei coboara in `hasVariant`, deci numara variantele
   NESTED ca obiecte de nivel inalt — de aici "8 Product-uri cu oferta".
   `_iter_jsonld_objects` (ce vede extractorul) intoarce UN singur obiect: grupul.
2. Print-ul de diagnostic trunchia sku-ul la 14 caractere, deci sku-uri distincte
   pareau identice. Masurat intreg: 8 sku-uri DIFERITE din 8
   (`KZNZ40111BK2206139` pentru grup, `...923`, `...921`, `...919` pentru marimi).

otter e **FASHION-1b curat**: ProductGroup cu `hasVariant` nested si
`variesBy: [size]`. Extractorul il gestiona deja corect INAINTE de acest val —
verificat pe dump: `variants=7`, etichete `45, 44, 43, 42 ½, 42, 41, 40`, pret 409
RON (minimul marimilor in stoc), nume curat de la grup.

Consecinta: capabilitatea "variante din frati cu sku comun", planificata pentru
acest val, a fost ABANDONATA. Conditia ei de activare (sku partajat) n-ar fi pornit
niciodata pe datele reale, deci ar fi ramas cod fara acoperire. In locul ei, un
test PINUIESTE forma reala, ca eroarea sa nu se repete si sa nu mai justifice cod.

### variesBy la o singura dimensiune (C2)

Garda din LOT2 cerea mai mult de o dimensiune. Extinsa: compunerea porneste oricand
`variesBy` e declarat si parsabil. Pe `[size]` rezultatul e identic cu cel de
dinainte (partea `size` singura E `_variant_label`-ul pe size). Castigul e pe
dimensiunile NON-size: boozt/booztlet declara `variesBy: [color]`, iar fara
compunere eticheta cadea pe plasa de nume. Masurat pe dump, inainte -> dupa:

| inainte | dupa |
|---|---|
| `Adrian Cherry Red Arcadia - CHERRY RED` | `CHERRY RED` |
| `VINTAGE BUTTERFLY S/S TEE - WHITE` | `WHITE` |
| `501 LOOSE IN MY BRONCO - LIGHT INDIGO - WORN IN` | `LIGHT INDIGO - WORN IN` |

### Normalizarea caii (C3)

spartoo.ro serveste IDENTIC `/Nike-x.php` si `//Nike-x.php`: fara redirect, fara
canonical care sa normalizeze (masurat — URL-ul final pastreaza dublul slash). Doua
forme ale aceluiasi URL ar trece amandoua de dedup si ar deveni doua surse pentru
acelasi produs. La salvare, secventele de `/` se colapseaza in CALE; schema, query
si fragmentul raman neatinse.

### Alte observatii

- **spartoo publica `og:type` propriu**: `spartoo_com:article`, nu `product`. Ramura
  OG a oricarui detector nu se poate baza pe conformitate cu vocabularul standard.
  Paginile sunt insa perfect extractibile prin ld+json (293.60 / 811.76 / 225.56 RON).
- **boozt a raspuns cu 429** la ritmul standard de 1.5s intre cereri. La LOT3b, cu
  3s pe grupul boozt, niciun 429. Grupul cere politete mai mare.
- **boozt/booztlet publica variante DOAR pe colorway**; marimile lipsesc cu totul
  din datele structurate, desi lotul e fashion. UI-ul nu trebuie sa promita selectie
  pe marime pe aceste domenii.
- **hhv.de** ramane `probed` (challenge servit pe 200, consemnat la LOT2).

## LOT4 / LOT4b

Doua sonde, 2026-08-13, pentru lotul 2d — beauty/parfumuri. Specificul categoriei:
variatia tipica e pe VOLUM (30/50/100 ml), echivalentul marimilor din fashion.

### Verdicte

| domeniu | sonda | confirmate | metoda | moneda | verdict |
|---|---|---|---|---|---|
| marionnaud.ro | LOT4 | 3/3 | jsonld | RON | validat |
| notino.ro | LOT4 | 3/3 | jsonld | RON | validat, pe alta treapta |
| parfumdreams.de | LOT4 | 3/3 | jsonld | EUR | validat DUPA fixul de moneda |
| douglas.ro | LOT4b | 3/3 | jsonld | RON | validat |
| sephora.ro | LOT4 | 0 | — | — | probed (Grup 4) |
| makeup.ro | LOT4b | 0 | — | — | probed (Grup 4) |
| bipa.ro | LOT4 | 0 | — | — | NU e magazin — inchis |

### parfumdreams.de — pretul si moneda in `priceSpecification`

FRAGMENT VERBATIM (`index_145673.aspx`, prima varianta din `hasVariant`):

```json
{
  "@type": "Product",
  "sku": "1284803",
  "name": "Issey Miyake L'Eau d'Issey Eau Essentielle Eau de Parfum Spray 50 ml",
  "size": "50 ml",
  "offers": {
    "@type": "Offer",
    "size": "50 ml",
    "availability": "https://schema.org/InStock",
    "priceSpecification": {
      "@type": "UnitPriceSpecification",
      "price": 59.9,
      "priceCurrency": "EUR",
      "referenceQuantity": {
        "@type": "QuantitativeValue",
        "value": 50, "unitCode": "MLT",
        "valueReference": {"@type": "QuantitativeValue", "value": 100, "unitCode": "MLT"}
      }
    }
  },
  "gtin13": "3423222134761"
}
```

Oferta n-are nici `price`, nici `priceCurrency` la nivelul ei. Extractorul citea deja
PRETUL de acolo (ramura din `_price_from_offers`), dar MONEDA o cauta doar in
`offer.priceCurrency` si mai sus — deci cadea pe implicitul romanesc din
`parse_product_html`. Masurat: toate cele 11 pagini ieseau **RON**, desi datele spun
**EUR**; 59.90 EUR salvat ca 59.90 RON face produsul sa para de ~5 ori mai ieftin.

E un bug GENERAL de extractor — orice magazin cu forma asta il lovea — nu o
ciudatenie parfumdreams. Reparat cu `_offer_currency`, care prefera nivelul ofertei
si cade pe spec doar cand acolo nu exista nimic. Dupa fix, toate cele 11 pagini ies
EUR.

Nuanta `Grundpreis`: `UnitPriceSpecification` cu `referenceQuantity` (50 ml) si
`valueReference` (100 ml) lasa deschis daca 59.90 e pretul flaconului sau pretul pe
100 ml. INCHIS MANUAL de David: e pretul FLACONULUI, deci ramura e sanatoasa dincolo
de moneda.

### douglas.ro — corectie fata de incadrarea din descoperire

La LOT4, descoperirea a nimerit doar pagini de BRAND (`/ro/b/dior/b0690`), iar
homepage-ul de 2 MB cu `window.__INITIAL_STATE__` a dus la incadrarea provizorie
Grup 3. Pe paginile de PRODUS (LOT4b, link-uri manuale) realitatea e alta: **un
bloc ld+json cu un Product, `priceCurrency` RON**, extractie curata (135.00 /
305.25 / 273.00 RON), zero microdata, `og:type` absent.

Starea `window.__INITIAL_STATE__` chiar exista si se parseaza, dar cautarea de chei
de pret (`price`, `value`, `formattedValue`, `amount`, `priceValue`, pana la
adancimea 14) a intors ZERO rezultate — deci nu ea poarta pretul. Rezerva: cautarea
a mers pe o lista FIXA de chei.

Deci esecul de la LOT4 a fost al ORDONARII candidatilor, nu al site-ului.

**Forma variantelor: o pagina per volum.** Cele trei pagini publica un singur Product
fara `hasVariant`, desi doua sunt parfumuri. Douglas foloseste cate un cod de produs
si o pagina per volum — pentru implementare, cazul cel mai simplu: fiecare volum e o
sursa proprie, fara selectie de varianta.

### makeup.ro — interstitiu servit cu 202

`202 Accepted` pe toate cele patru trepte, pe ambele URL-uri, cu corp IDENTIC LA
OCTET (2020 octeti):

```html
<!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title></title> <style> body { font-family: "Arial"; } </style> <script type...
```

Zero ancore, zero ld+json, titlu GOL. Raspunsul fiind identic pe toate treptele,
blocajul NU e pe amprenta TLS/HTTP2 — escaladarea n-are ce rezolva.

LECTIE DE COMPLEMENTARITATE: regula veche de shell gol (corp <10KB + zero ancore +
FARA titlu) NU l-ar fi prins, fiindca pagina ARE un `<title>`, doar ca gol. Regula
noua "202 = provocare" l-a prins. Cele doua sunt complementare, nu redundante; ambele
intra in detectorul v2.2.

Nota: makeup serveste 202 SELECTIV — homepage-ul raspunde 200, doar paginile de
produs sunt blocate. De aceea sonda de descoperire l-a vazut ca domeniu accesibil.

### sephora.ro

`/promotii` da 404 real; homepage-ul da **403 cu corp de 519 octeti** pe toate
treptele, si pe `www`, si pe apex. Blocaj autentic.

### bipa.ro — NU e magazin, inchis

Dintr-un homepage de 408 987 octeti au iesit **4 candidati**, toti non-produs:
`/pliant`, `/campanie`, `/magazinul-meu`, `/compliance`. Filtrele au taiat putin
(46 cuvinte-neprodus, 40 alt host, 8 duplicate), deci lista nu e goala din cauza lor
— pur si simplu nu exista link-uri de produs in HTML. Combinatia (pliant, campanie,
localizator de magazine) descrie un catalog de prezentare. Rezerva: fiind SPA Nuxt,
un magazin ar putea fi randat client-side, dar nimic din HTML-ul initial nu-l
sugereaza. NU intra in registru; se inchide aici.

### notino.ro — NU e Grup 4

Lista master il anticipa ca dificil (Cloudflare + F5). Treapta implicita a fost
provocata, a doua a dat 403, iar a treia a deschis curat (200, 768 018 octeti).
3/3 pagini validate, JSON-LD, RON. Treapta traieste in campul `impersonate` din
registru, nu in proza — locul sanctionat, precedentul 43einhalb.

### Maturitatea descoperirii v2.1

Din 7 domenii, clasificand onest cauzele, mecanismul a esuat propriu-zis pe UNUL
SINGUR (douglas — ordonare), fata de 4 la LOT3:

| esec | cauza reala |
|---|---|
| makeup.ro | acces (202 selectiv) — ordonarea functionase, top-ul era produs real |
| sephora.ro | acces (403 pe toate treptele) |
| bipa.ro | site-ul nu e magazin |
| douglas.ro | ordonare — singurul esec real al mecanismului |

marionnaud a atins 3 confirmari in 4 fetch-uri. Bonusul miniaturii si departajarea
pe sku au lucrat, fara nicio respingere gresita observata.

### Bilantul Grupului 4 dupa val

hhv.de, orange.ro, sephora.ro, makeup.ro — **patru candidati**. Pragul de la care un
harness de browser incepe sa se justifice e atins.

---

## G4 / G4b / BR-1 — Grupul 4 si harness-ul de browser

Doua sonde in browser (patchright, 2026-08-13) plus runda de implementare BR-1, care
a facut din browser A TREIA cale de fetch, alaturi de curl si de endpoint-ul Shopify.
Grupul 4 nu e o categorie de magazine, ci o categorie de ACCES: patru domenii unde
datele exista in pagina, dar nu in raspunsul pe care-l primeste un client fara motor
de randare.

### Verdicte

| domeniu | mod | metoda pe DOM randat | moneda | verdict |
|---|---|---|---|---|
| orange.ro | headless | jsonld | RON | validat (2/2 la G4) |
| hhv.de | **headed** | jsonld | EUR | validat (3/3 la G4b) |
| sephora.ro | **headed** | microdata | RON | validat (reverificare G4b) |
| makeup.ro | headless | microdata + override | RON | validat cu `price_selector` |

### makeup: 202-ul e interstitiu JS, nu refuz

LOT4b incadrase `202 Accepted` drept "blocaj moale". In browser, aceleasi pagini se
randeaza complet: `og:type=product`, 119–183 markeri `itemprop`, titlu real. Deci 202
nu era un refuz, ci un interstitiu care asteapta executie de JS — ceea ce explica
RETROACTIV observatia care nu se lega la LOT4b: corpul era identic la octet pe toate
treptele de impersonare. Nu era amprenta TLS fiindca nu era nicio decizie despre
client; era acelasi document de asteptare servit tuturor.

Ce blocheaza extractia e altceva: pagina poarta **3 / 11 / 3** elemente
`itemprop="price"` intr-un singur scope Product, iar regula de siguranta din
`_collect_microdata` refuza corect ambiguitatea. Structura, verbatim din
`makeup.ro/product/181283/`:

```html
<div class="ProductBuySection__container shop_1hy48pa_l3p3ge"
     itemprop="offers" itemscope itemtype="https://schema.org/Offer">
  <meta itemprop="price" content="49.29">
  <meta itemprop="priceCurrency" content="RON">
```

```html
<div class="ProductBuySection__title shop_1v5nkdl_l3p3ge">02 - Natural</div>
<meta itemprop="name" content="Fond de ten - Paese Long Cover Fluid  02 - Natural">
<meta itemprop="price" content="55.29">
```

Un pret principal in container, plus cate unul per varianta de culoare. Doua capcane
masurate la implementare, ambele pe dump:

1. **variantele sunt NESTED in container**, deci selectorul de descendenti se
   potriveste cu 11 elemente, nu cu unul; `select_one` ia primul, care e chiar meta-ul
   propriu al ofertei — masurat 159 / 49.29 / 44.45 pe cele trei pagini, adica pretul
   principal de fiecare data.
2. **clasele poarta sufixe generate la build** (`shop_1hy48pa_l3p3ge`), deci selectorul
   se ancoreaza pe partea stabila a numelui, nu pe clasa intreaga.

Purtatorul fiind un `<meta>`, n-are text — de aici extensia din `_apply_override`:
cand `price_selector` gaseste un element din al carui text nu iese pret, se citeste
atributul `content`. Textul ramane prioritar, deci niciun override existent nu-si
schimba sursa.

### sephora: masuratoarea sondei a fost invalidata de sonda insasi

Faza automata a raportat 0/3 si "prag nedeterminat" dupa 27,4 minute. Verdictul e
GRESIT, si vina e a sondei. Criteriul de succes era `parse_ok AND not blocata`, deci
o pagina servita normal dar din care parserul nu scotea nimic era numarata drept
blocaj. Cronologia arata limpede ce s-a intamplat:

| ts | spatiere | status | blocata | tratat ca |
|---|---|---|---|---|
| 16:23:49 | 0 min | 200 | **False** | BLOCAT |
| 16:27:29 | 3 min | 200 | **False** | BLOCAT |
| 16:35:10 | 7 min | 200 | **False** | BLOCAT |
| 16:50:50 | 15 min | 200 | True (`access denied`) | BLOCAT |

Primele trei nu erau blocate deloc. Escaladarea a insistat pe acelasi URL, iar
`Access Denied`-ul de la +15 min e cel mai probabil CONSECINTA insistentei, nu cauza
initiala. O singura vizita de reverificare, sesiune scurta:

```
status: 200   blocata: False   lungime: 820782
titlu:  Centella Cleansing Balm - Balsam demachiant | Erborian ≡ SEPHORA
parse:  OK -> 173.0 RON prin microdata, poll 0.39s la PRIMA incercare
```

**Pragul de spatiere ramane NEMASURAT** — premisa n-a fost niciodata exercitata
corect, deci cifrele din cronologie nu se folosesc la nimic. De aceea
`min_fetch_interval_s: 180` e o estimare prudenta, nu o masuratoare: productia e
masuratoarea, iar valoarea se urca din registru daca apar blocaje.

### hhv: headed obligatoriu, `pquid` taiat de canonical, marimi absente

Headless raspunde `ERR_CONNECTION_RESET` la navigare (deci nici macar un challenge —
conexiunea moare), iar headed trece curat: 3/3, jsonld, EUR, un singur purtator de
pret per pagina (17.95 / 149.95 / 219.95). Pe server asta inseamna xvfb, ca la
mobile.de.

Parametrul `pquid` din link-urile de campanie **nu supravietuieste**: pe ambele URL-uri
care-l purtau, `<link rel=canonical>` il taie. Comportamentul implicit (canonical
preferat) e deci corect si hhv NU are nevoie de `url_identity: "exact"`.

Marimile lipsesc din datele structurate pe toate trei paginile, desi sunt articole de
imbracaminte — ca la boozt: se urmareste produsul, nu marimea.

### Parse-poll in loc de asteptare fixa

Prototipul mobile.de asteapta FIX 6s dupa navigare. G4b a masurat timpul real pana la
continut:

| pagina | secunde | incercari |
|---|---|---|
| hhv 1 | 2,53 | 2 |
| hhv 2 | 0,47 | 1 |
| hhv 3 | 0,57 | 1 |
| sephora (reverificare) | 0,39 | 1 |

In 3 din 4 cazuri continutul e gata la PRIMA incercare. Harness-ul incearca deci sa
parseze imediat si apoi la ~1,5s, cu plafon 20s — plafonul n-a fost atins niciodata pe
o pagina care se extrage.

### D12 inchis pe masuratoare: fara storage_state

Reutilizarea starii de sesiune intre pagini nu aduce castig: pe orange.ro, prima
vizita a durat **7,16s** si a doua, cu `storage_state` incarcat, **7,22s**. Sesiune-per-
pagina e deci si mai simpla, si mai politicoasa. Se redeschide doar daca apare un
challenge scump DOVEDIT, unde costul rezolvarii se amortizeaza pe mai multe pagini.

### Doua reguli permanente de protocol, din defectele sondei G4b

**Escaladarea se face DOAR pe `blocata == True`.** "Neparsata" si "blocata" sunt stari
diferite; confundarea lor a produs 27 de minute de asteptari inutile, un verdict fals
si, foarte probabil, chiar blocajul pe care pretindea ca-l masoara.

**Fiecare incercare isi scrie dump-ul cu eticheta UNICA.** Reincercarile pe sephora au
scris toate in acelasi loc, deci artefactele incercarilor 1–3 s-au pierdut si diagnoza
a trebuit facuta din log, nu din pagini.

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
