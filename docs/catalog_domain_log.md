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

## LOT5 / LOT5b — jucarii/hobby RO

Sondele: `scripts/diagnostics/dumps/lot5_jucarii/` (descoperire pe 5 domenii) si
`scripts/diagnostics/dumps/lot5b_completare/` (completare pe link-uri manuale).

| domeniu | sonda | metoda | verdict |
|---|---|---|---|
| noriel.ro | LOT5, samanta `/promotii` | jsonld | VALIDAT (3/3 pagini) |
| regatuljocurilor.ro | LOT5, homepage | jsonld | VALIDAT (3/3) |
| jucarii-vorbarete.ro | LOT5, homepage | jsonld | VALIDAT (3/3) |
| nichiduta.ro | LOT5 esuat la ordonare -> LOT5b | jsonld | VALIDAT (3/3, cu treapta laxa) |
| brickdepot.ro | LOT5 respins la confirmare -> LOT5b | jsonld | VALIDAT (1/2 pagini; vezi limita) |

Toate cinci au raspuns pe treapta de baza; nicio escaladare in tot lotul.

### Decizia valului: treapta laxa la parsarea blocurilor ld+json

brickdepot si nichiduta publica ld+json cu **caractere de control BRUTE** (newline
literal in valorile de string, din descrieri multi-linie). `json.loads` strict le
refuza, iar `except: continue` din iterarea blocurilor le arunca TACUT. Docstring-ul
justifica toleranta prin "un bloc corupt nu trebuie sa arunce restul paginii" — dar pe
paginile astea blocul corupt e SINGURUL bloc, deci pagina intreaga ramanea fara date.

Masurat la LOT5b pe extractorul real (shim doar in memorie, inainte de orice
modificare): **0/5 -> 4/5 pagini extrase**, cu preturile 158.99 / 875 / 71 / 749 RON,
toate prin `jsonld`. Fix-ul e GENERAL, nu specific lotului: orice magazin cu descrieri
multi-linie in ld+json e afectat identic.

**Limita treptei laxe, masurata, nu presupusa.** A cincea pagina (brickdepot
`computer-science-ai-kit-68-4-elevi-p-31250.html`) pica si in lax, din alt motiv: o
eroare de SINTAXA in sursa site-ului — ghilimea dublata care inchide descrierea de
doua ori, `"...salvate local"",`. `strict=False` accepta exclusiv caractere de control
in stringuri; sintaxa stricata, ghilimelele dublate si virgulele finale pica in
continuare. Laxul nu e o bagheta, si asta e testat explicit
(`test_jsonld_lax_nu_salveaza_sintaxa_stricata`).

Consecinta operationala acceptata: pagina cu ghilimea dublata ramane neparsabila, iar
refresh-ul ei pastreaza pretul anterior. brickdepot intra FARA override de selector —
cu treapta laxa, pragul de >=2 pagini e atins prin jsonld.

### Corectia de verdict din LOT5b, si de ce a fost posibila

Prima rulare LOT5b a dat `FARA_DATE` pe ambele domenii. Era GRESIT, si din vina
instrumentului: sonda folosea aceeasi parsare stricta ca productia, deci a raportat
"zero purtatori structurati" pe pagini care poarta pretul in ld+json standard.
Traseul real a fost `FARA_DATE` -> `MISMATCH_DE_ANALIZAT` -> validat.

Corectia n-a costat niciun fetch in plus, fiindca dump-urile complete existau deja.
**Regula v2.3 devine PERMANENTA: orice pagina fetch-uita se dumpuieste COMPLET,
indiferent de verdict.** Motivul e povestea brickdepot din LOT5: acolo sonda iesea
inainte de scriere cand pagina nu trecea de confirmare, asa ca exact cele 11 pagini
care cereau analiza au ramas fara dump — si domeniul cel mai relevant pentru arbitraj
din tot lotul a plecat cu verdict de "descoperire esuata" in loc de "limita a
detectorului".

### Omnibus: forma se repeta, si e favorabila

Pe toate domeniile validate, ld+json poarta DOAR pretul PLATIT; referinta taiata sta
in afara datelor structurate. Verificat verbatim: noriel `special-price` / `old-price`
(49,99 vs 99,99 lei), regatuljocurilor `has-discount` + `raw_price` (255,20 din 319),
jucarii-vorbarete Shopify `compare_at_price` in bani (3599 vs 3999), nichiduta
`div.priceNEW` / `div.priceOLD`. Zero declansari ale capcanei pe 9+4 pagini.

Atentie: convergenta raportata de sonda ("toti purtatorii converg") e convergenta unei
SINGURE valori, nu dovada ca produsul n-ar fi redus.

**Nuanta PRP la nichiduta.** Referinta taiata NU e minimul pe 30 de zile, ci pretul
recomandat de producator. Verbatim din tooltip-ul aceluiasi element:
`"Acesta este Pretul Recomandat de Producator. Pretul de vanzare al produsului este
afisat mai jos."` Procentele afisate (-31%, -25%, -38%) sunt fata de PRP, deci marja
reala de arbitraj e mai mica decat sugereaza eticheta. Marjele pe nichiduta se citesc
fata de PRP, nu fata de minim istoric.

### Regula de analiza: element de pret identic pe pagini diferite = componenta partajata

A doua aparitie a capcanei, deci se ridica la regula. La regatuljocurilor,
`<span class="regular-price">319,00 RON</span>` apare identic pe toate cele trei
pagini, inclusiv pe cele nereduse de 59 si 269 RON — e un produs promovat dintr-un
carusel comun. Raportul 255.2/319 = 0.8 exact il facea sa para confirmarea pretului
taiat al paginii; nu era. Semnalul de incredere acolo e `has-discount` + `raw_price`.
La brickdepot, aceeasi capcana in alta forma: `div.swipper-bg > div.product-item >
div.price`.

Marcajul automat prinde capcana doar cand aceeasi valoare apare pe pagini diferite —
la brickdepot NU a prins-o, fiindca cele doua pagini au carusele cu valori diferite.
Cu esantion mic, capcana se cauta manual.

### Avertisment de instrument

Valorile numerice din `dom_pret.json` sunt materie prima, nu preturi. `_numar`
concateneaza cifrele dintr-un text cu mai multe numere: `div.priceOLD` apare cu
**125931** pentru un ATV de 875 lei — sunt `1259` si `31` lipite din
`Pret vechi: 1259 Lei (-31 %)`. La fel `99925` (999 + 25) si `11538` (115 + 38).
Textul VERBATIM e sursa de adevar, nu valoarea derivata.

### Ce NU s-a verificat in lotul asta

**Ipoteza codurilor LEGO ramane netestata efectiv.** Premisa era ca sluguri de tip
`42131` / `75192` sunt cifre STRUCTURATE si anti-UUID-ul nu trebuie sa le penalizeze.
Regula noua (`cifra+silabe`) a lucrat pe 8 din 9 pagini confirmate, dar pe niciun cod
de set real: `2017` era coada unui nume de produs, `2026` anul unei editii, `-p-6906`
un id de magazin. Singurul domeniu cu seturi reale era brickdepot, si acolo codul nici
nu apare in slug — URL-ul poarta id-ul de magazin (`-p-31177`), nu setul.

**Cele doua semnale noi de blocaj n-au fost exercitate.** `202 Accepted` ca blocaj
moale si `<title>` GOL (pe langa `<title>` lipsa) sunt in detector si trec testul
offline, dar niciun domeniu din lot nu le-a declansat. Raman verificate doar sintetic.

### Material de rezerva: specificatia de selector brickdepot (NEIMPLEMENTATA)

Masurata la LOT5b, pastrata aici pentru cazul in care ghilimea dublata se dovedeste
sistemica si un override devine necesar. Blocul de pret, verbatim, pagina REDUSA:

```html
<h2 class="productGeneral" id="productPrices">
 <span class="normalprice 3">264.99Lei</span>
 <span class="productSpecialPrice">158.99Lei</span>
 <span class="discountLabel">40%</span>
```

Pagina NEREDUSA — fara span-uri, pretul e textul PROPRIU al lui `h2`:

```html
<h2 class="productGeneral" id="productPrices"> 3,021.99Lei</h2>
```

Specificatia are deci trei ramuri:
- pret platit pe pagini reduse: `h2#productPrices > span.productSpecialPrice`
- pret pe pagini nereduse: textul propriu al lui `h2#productPrices`
- pret taiat: `h2#productPrices > span.normalprice` — clasa reala e `"normalprice 3"`,
  a doua componenta variaza, deci potrivirea se face pe clasa STABILA `normalprice`
- format ENGLEZESC: `1,599.99Lei` (mii cu `,`, zecimal cu `.`), moneda lipita
- **EXCLUDERE OBLIGATORIE**: `div.swipper-bg > div.product-item > div.price` —
  caruselul de produse conexe (vezi regula componentei partajate, mai sus)

### Nota de limitare frozen (din BR-2)

Sub PyInstaller, instalarea patchright e sarita (PKG-3b), deci exe-ul depinde de
Chrome-ul real al userului pentru domeniile pe `method: browser`. Extensia lui
`--selfcheck` care sa verifice asta explicit ramane parcata pentru o runda PKG
viitoare; nu tine de valul de fata, dar tine de ce vede userul cand un domeniu
browser nu porneste.

---

## SHOP-3 — migrarea jucarii-vorbarete.ro la extractorul Shopify

Sonda: `scripts/diagnostics/dumps/sonda_vorbarete/` (un fetch per endpoint, fara reincercari).

| domeniu | verdict sonda | metoda inainte | metoda dupa | moneda |
|---|---|---|---|---|
| jucarii-vorbarete.ro | SHOPIFY_DESCHIS | jsonld (LOT5) | shopify | RON (/cart.js, incrucisat cu ld+json 3/3) |

Masurat: `/products.json?limit=5` 200 cu `variants` (chei: available, compare_at_price,
price ca STRING zecimal, sku, title...), `/products/<handle>.js` 200 cu `available` bool
si pretul ca INT in bani (3040 == "30.40" pe aceeasi varianta), semnatura powered-by
Shopify, datadome absent. `available` LIPSESTE din `/products/<handle>.json` (SHOP-1a,
0/39) dar e prezent in enumerare si in `.js` — trei formate distincte, nu contradictie.

Limite: FASHION-2 (minimul marimilor disponibile) neexercitata — handle-ul enumerat are
o singura varianta „Default Title"; dimensiunea catalogului nemasurata (limit=5).

Consecinta: domeniul intra automat in scannerul de deal-uri prin `shopify_domains()`.

---

## DEAL-2 — scannerul de listari HTML pe 4 domenii pilot

Sonde: `scripts/diagnostics/dumps_lst1/` (LST-1, 20 de cereri) si `dumps_lst1b/`
(LST-1b, 4 cereri). Toti selectorii din descriptorii de listare sunt MASURATI pe
aceste dump-uri; fixture-urile de test sunt fragmente decupate din ele.

A treia sursa a feed-ului de deal-uri, dupa scannerul Shopify (SHOP-2a) si
scaderile de la refresh (DEAL-1). Magazinele non-Shopify n-au endpoint de
enumerare, deci singura cale de a le scana integral e parcurgerea propriilor
pagini de reduceri. Apartenenta la scanner se decide din prezenta cheii `listing`
in registru, prin `listing_domains()` — cod generic, descriptori declarativi.

| domeniu | listare | paginare | produse/pag | pagini masurate | pret platit | pret taiat | referinta |
|---|---|---|---|---|---|---|---|
| otter.ro | /reduceri | `?p={n}` | 24 | 197 | `data-price-amount` (finalPrice) | `data-price-amount` (oldPrice) | PRP |
| caseking.de | /en/sale | `?page={n}` | 40 | 34 (1.338 produse) | `content` in `span.sales .value` | `content` in `span.sales-original .value` | nemarcat |
| noriel.ro | /promotii | `?p={n}` | 60 | 115 | `.special-price .price` | `.old-price .price` | nemarcat |
| bergfreunde.eu | /outlet/ | `/outlet/{n}/` | 72 | 190 (13.638 produse) | `[data-codecept='currentPrice']` | `[data-codecept='strokePrice']` | PRP |

**Conditia de oprire NU e statusul HTTP.** Toate cele patru raspund 200 dincolo de
ultima pagina, dar diferit: otter si caseking servesc grila GOALA, noriel CLAMEAZA
la pagina 1 (acelasi set de 60 de linkuri), bergfreunde CLAMEAZA la ultima pagina
(30 de carduri). Un scanner care s-ar opri doar la „zero carduri" ar bucla la
infinit pe doua din patru. De aceea oprirea e compusa: grila goala SAU toate
linkurile paginii deja vazute SAU `max_pages` (plasa de siguranta).

**Pretul taiat nu e minim pe 30 de zile.** La otter e PRP explicit („PRP: 379,00 lei",
„Salvezi 82 lei fata de pretul recomandat de producator"); la bergfreunde e `uvp`,
etichetat „Original price" — exista si un camp „Lowest price in the last 30 days",
dar e `!hidden`, gol si in spatele unui A/B test oprit. La caseking si noriel nu
exista nicio eticheta legala. `reference_kind` din descriptor consemneaza asta, iar
codul nu pretinde nicaieri „minim 30 de zile".

**Capcane de potrivire, masurate:** cardul se potriveste pe SUBSET de clase — noriel
eticheteaza fiecare container cu id-ul produsului (`div.product-item.freegifts-223986`),
deci potrivirea pe lista completa da zero carduri. Tot la noriel, `<a>`-ul fara clasa
inveleste CONTINUTUL cardului (h2 + price-box inauntru), dar containerul ii ramane
parinte — linkul e deci descendent, nu stramos.

**Anti-avalansa Discord:** la primul scan reusit al unui domeniu nu se trimite nicio
notificare. R1 e gratuit pe calea asta (orice card cu pret taiat califica instant),
deci primul scan al lui otter singur ar declansa sute de alerte pentru produse aflate
la reducere de saptamani. De la al doilea scan alerteaza doar deal-urile NOI, plafonat
la 10 per domeniu per scan; restul intra tacut in feed.

**Retrogradat:** booztlet.com — listarea reala (`/eu/en/women/view-all`, 80 de carduri
server-renderate, 57.129 produse) nu expune NICIO paginare in HTML brut (infinite
scroll). Revine pe un val cu API, nu pe calea asta.

**Sortare (masurata, NEfolosita inca):** doar noriel expune sortare dupa reducere
(`product_list_order=discount.percent`). otter are acelasi toolbar Magento fara
optiunea de reducere, caseking are `?srule=` cu 6 valori fara reducere (dar si
`start`/`sz`, deci dimensiunea paginii ar putea creste peste 40), bergfreunde n-are
marcaj de sortare. Materie prima pentru o runda de tuning, nu pentru scanul curent.

---

## DEAL-2b — zgomotul PRP: prag separat pentru R1 pe listari

Primul scan DEAL-2 a produs **15.832 de deal-uri**, dominate de „reduceri" fata de
pretul recomandat: la otter.ro, **87%** din tot ce apare pe /reduceri califica la
pragul global de 20%. R1 nu mai purta informatie pe calea asta si ingropa R2 —
scaderea sub minimul istoric, adica semnalul curat.

**Prag separat pentru R1 pe listari.** `_evalueaza` primeste `prag_r1` optional
(`None` = acelasi prag ca R2, deci apelurile existente se comporta IDENTIC — o
singura implementare, fara copie divergenta). `listing_scanner` il alimenteaza din
`RadarSettings.listing_r1_threshold`, implicit `DEFAULT_LISTING_R1_THRESHOLD = 40.0`.
La `reason="ambele"`, fiecare regula se compara cu pragul EI.

R2 ramane pe `deal_discount_threshold`, neatins. Scannerul Shopify ramane integral
pe pragul global: acolo `compare_at_price` chiar e referinta unui comerciant activ,
deci semantica SHOP-2 nu se schimba.

**Inchiderea deal-urilor care nu mai califica — defect in AMBELE scannere.** Pana
acum criteriul era `external_id not in vazute`, deci se inchideau doar produsele
DISPARUTE. Un produs inca prezent dar care nu mai trece pragul (pretul a urcat, sau
pragul a fost marit din UI) trecea prin `continue` la evaluare si ramanea „activ" cu
date vechi pentru totdeauna. Ambele module tin acum si `calificate` (id-urile care
au primit deal in scanul curent), iar inchiderea se face pe el.

Efect **retroactiv prin design**: primul scan de dupa o schimbare de prag isi face
singur curatenia — zero SQL manual, zero migratie de date. Fara fixul asta, pragul
de mai sus n-ar fi avut niciun efect asupra celor 15.832 de randuri existente.

Filtrul pe `deal_source` e acum EXPLICIT in ambele scannere (`shopify_enum`,
respectiv `listing_scan`). Randurile `refresh_diff` pot sta pe acelasi domeniu (un
produs urmarit prin link) si niciun scanner nu spune nimic despre ele; pana acum
scapau doar fiindca `external_id`-ul lor (`src:<id>`) nu se ciocnea accidental.
D7 ramane: starea userului nu se atinge, randul nu se sterge.

**Filtru de sursa in feed.** `_serialize` intoarce `deal_source`; `list_deals`
primeste `source`, validat contra `_SURSE` (422 explicit pe valoare invalida).
Filtrarea e pe SERVER — feed-ul are zeci de mii de randuri, spre deosebire de
filtrul de categorie, care lucreaza client-side pe lista deja incarcata.

---

## VTX-1/1b/1c/2 — f64.ro (VTEX) si elefant.ro (Intershop)

Sonde: `scripts/diagnostics/dumps_vtx1/`, `dumps_vtx1b/`, `dumps_vtx1c/`
(6 + 4 + 5 = 15 cereri, read-only). Prezumtia initiala era o "pereche VTEX";
**doar f64.ro e VTEX**. elefant.ro ruleaza pe **Intershop** — dovada verbatim din
`elefant.ro_home.html`: `media.elefant.ro/INTERSHOP/static/WFS/elefant-Site/...`.

### Axa L — f64.ro intra pe `method: jsonld` (VTX-2, FACUT)

ld+json `Product` cu `AggregateOffer`, iar oferta REALA sta intr-o lista imbricata:

```json
{"@type":"AggregateOffer","lowPrice":475.9,"priceCurrency":"RON","offerCount":1,
 "offers":[{"@type":"Offer","price":475.9,"priceCurrency":"RON",
            "availability":"http://schema.org/InStock","sku":"00381218"}]}
```

Agregatul **nu are `availability`**, deci extractorul (care citea doar nivelul
agregatului) intorcea `in_stock=None` desi stocul era publicat corect. VTX-2 a
adaugat coborarea in ofertele imbricate — a treia forma de `offers`, dupa
ProductGroup/hasVariant (FASHION-1) si lista de oferte cu `size` (FASHION-2).
Agregare optimista: cumparabil daca MACAR o oferta imbricata e in stoc; toate
epuizate -> False; niciuna declarata -> None (nu se inventeaza True).
`availability` pe agregat, cand exista, are precedenta.

Pretul taiat **NU e in ld+json** — sta doar in DOM, cu doua etichete distincte
(`Pret anterior` si `PRP`, cu aceeasi valoare pe produsul masurat). Omnibus **PRP**;
care din cele doua e minimul pe 30 de zile ramane NEMASURAT (doua pagini nu ajung).

### Axa D — API-ul de catalog VTEX (DOCUMENTAT, nu implementat)

Endpoint: `/api/catalog_system/pub/products/search`. **2xx include 206** — VTEX
raspunde `206 Partial Content`, iar o verificare pe `status == 200` clasifica API-ul
drept inchis (exact greseala primei treceri). Header-ul `resources` poarta
`interval/total`, deci prima pagina a oricarui segment da totalul GRATIS.

Plafoane MASURATE, verbatim din raspunsurile de eroare:

```
_from=0&_to=99      -> 400  "Parameter _to can't be greater than 50."
_from=2540&_to=2549 -> 400  "Parameter _from can't be greater than 2500."
```

Deci enumerarea liniara acoperă ~2.550 din **52.930** de produse (4,8%):
**segmentarea e obligatorie.**

**Designul aprobat — descendere adaptiva in arbore.** `/api/catalog_system/pub/category/tree/2`
da **41 categorii de nivel 1 si 179 noduri de nivel 2**. Prima pagina a unui segment
(`fq=C:<id>`) intoarce totalul in `resources`; sub ~2.500 se enumera liniar, peste
se coboara pe copiii de nivel 2. Contraexemplul masurat, care a decis designul:

| categorie | id | `resources` | total | enumerabila liniar? |
|---|---|---|---|---|
| Aparate foto | 1000003 | `0-9/1164` | 1.164 | da |
| Obiective foto | 1000017 | `0-9/2855` | 2.855 | **nu** (are 5 subcategorii) |

Filtrul restrange real: doar 2 din 10 produse ale paginii nefiltrate cad in
"Aparate foto". Frunza care depaseste ea insasi plafonul: sub-segmentare pe
intervale de preț (`fq=P:[a TO b]`), tipar VTEX clasic dar **NEMASURAT la f64** —
de verificat cu o cerere la implementare, nu de presupus.

Excludere din arbore (categorii ne-catalog, citite din `tree`): `Advanced Payment
Products`, `EOL`, `SH-uri de postat`, `frontend`, `NoDepartment`, `Insurance`,
`Card Cadou F64`. Fara ele, segmentarea cheltuie cereri pe zgomot.

R1 = `ListPrice` vs `Price` din `commertialOffer`. Semantica e de **PRP**, deci
pragul relevant e `listing_r1_threshold` (DEAL-2b), nu cel global. Moneda **NU e in
`commertialOffer`** — se ia din registru/pagina (RON masurat). **1 seller per produs**
la toate cele 10 masurate: f64 nu e marketplace.

Aritmetica: ~1.100–1.300 de cereri per scan complet (52.930/50 = 1.059 minim, plus
paginile partiale de segment), ~35–40 min la pauza de politete de 1,5s + jitter
0–0,6s (cadenta JSON din `deal_scanner`, nu cea de 2,5s a paginilor HTML).

Nemasurat inca: cate din cele 41 de categorii depasesc 2.550 (2 testate, 1 a picat)
si daca vreo subcategorie de nivel 2 depaseste ea insasi plafonul.

### elefant.ro — amanat la VTX (Intershop) — INCHIS de ELF-1/1b/2, mai jos

> Sectiunea de mai jos ramane cum a fost scrisa la VTX-1c, ca istoric. Doua
> afirmatii din ea s-au dovedit GRESITE si sunt corectate in sectiunea ELF:
> „secțiune de Outlet (`data-testing-id="Outlet-link"`)" — acel testing-id NU
> poarta un URL de outlet; si ipoteza despre `StickyAddProduct` la epuizat —
> masurata si INFIRMATA la ELF-1b.

Axa L cere **extractor custom**: pagina de produs are ZERO `application/ld+json`,
zero `itemtype`/`itemscope` (cele 3 `itemprop` sunt `reviewRating`), fara
`og:price`. Doua ancore curate exista totusi:

```html
<div class="current-price" data-testing-id="current-price"
     data-price-currencymnemonic="RON">89,99 lei </div>
```
```javascript
window.ish.GTMproductDetail.push({"id":"7fcfa5a6-...","price":"89.99","brand":"D-Toys"});
```

Payload-ul GTM are zecimala cu PUNCT si acelasi UUID ca `data-sku` (tiparul noriel).
**Stocul nu s-a putut masura**: zero `availability`/`in-stock` pe pagina; butonul
`StickyAddProduct` exista lang preț, dar absenta lui la epuizat e ipoteza, nu
masuratoare (un singur produs, in stoc).

Axa D: listarea de categorie e un **schelet** — 60 de placi `div.lazy.inventory-item`
GOALE, fiecare cu `data-action` catre `ViewProductTileAsync-Start?...ProductID=...`.
Placa hidratata (6K, `text/html`) livreaza pretul si linkul canonic, de forma
`/<slug>_<data-sku>`. Deci `listing_scan` clasic nu merge: ori o cerere per produs
(1.603 doar pentru o categorie), ori harness de browser. Bonus masurat: elefant are
secțiune de Outlet (`data-testing-id="Outlet-link"`), punctul firesc de intrare
pentru un val de reduceri.

---

## ELF-1/1b/2 — elefant.ro: extractor custom Intershop, cu stoc onest necunoscut

Trei sonde (5 cereri) si o implementare. Sondele au inchis pe rand: pretul curent
si moneda (VTX-1c), pretul taiat + Omnibus (ELF-1), ramura negativa a stocului
(ELF-1b). Dump-urile stau in `scripts/diagnostics/dumps_elf1/` si `dumps_elf1b/`
(gitignorate), iar fragmentele folosite de teste in `backend/tests/fixtures/elefant/`.

### Axa L — `method: custom`, `elefant_intershop` (FACUT)

Fluxul generic chiar n-are ce citi: verificat pe dump-ul real, `parse_product_html`
ridica `no_product_data` (zero ld+json, zero microdata, zero OG pe domeniu). Testul
`test_elefant_fluxul_generic_chiar_nu_poate_citi_pagina` pinuieste asta — daca
elefant capata candva date structurate, testul cade si intrebarea „mai avem nevoie
de cod bespoke?" se pune singura.

Pretul, in ordinea de incredere masurata pe TREI PDP-uri (redus, neredus, epuizat):

1. `[data-testing-id="current-price"]` — exact **1 aparitie per pagina** pe toate
   trei, cu moneda pe ACELASI element (`data-price-currencymnemonic="RON"`).
2. Rezerva: `window.ish.GTMproductDetail`, unde `price` are zecimala cu PUNCT.
   Moneda nu e in payload, deci pe ramura asta ramane `None` — deliberat: pagina
   din care a disparut ancora primara e o pagina schimbata, iar un „RON" presupus
   ar ascunde exact schimbarea.

Pretul TAIAT exista, dar NU face parte din contractul extractorului de pagina —
e material de val D (mai jos). Forma lui, pe doua suprafete:

```html
<!-- blocul principal, table.pdp-table — FARA testing-id -->
<span class="old-price">39,99&nbsp;lei</span><span class="current-price">19,31&nbsp;lei</span>
<!-- bara sticky, div.price-container — CU testing-id -->
<div class="was-price old-price" data-testing-id="old-price">39,99 lei</div>
<div class="current-price sale-price" data-testing-id="current-price"
     data-price-currencymnemonic="RON">19,31 lei </div>
```

Comentariul de template `<!-- Determines if the SalePrice is equal to the Comparable
Price Type -->` apare doar pe produsul NEREDUS: e marker de ramura, nu de pret.

**Omnibus: NEMARCAT.** Zero „30 de zile", „cel mai mic", „recomandat", PRP/RRP/PVR
pe pagina redusa; textul vizibil din jurul perechii e gol (`39,99 lei 19,31 lei`).
Procentul e decorativ si are clase diferite per suprafata (`product-img-discount`
pe PDP, `product-label product-label-discount` pe placa). Consecinta pentru un
eventual R1 pe elefant: referinta exista, dar **fara eticheta legala** — de decis
separat daca asta califica pentru prag.

### Amprenta: `impersonate: chrome` e OBLIGATORIU (ELF-2)

Prima verificare live prin `extract_product` a picat pe toate cele trei URL-uri cu
`reason=challenge`, desi sonda validase domeniul de cinci ori in aceeasi zi.
Cauza nu era extractorul, ci amprenta — masurat pe acelasi URL, la minute distanta:

| amprenta | de unde vine | raspuns |
|---|---|---|
| `chrome131` | `_IMPERSONATE`, implicitul productiei (`scraper_service`) | **403**, `server: cloudflare` |
| `chrome` | `DEFAULT_IMPERSONATE`, ce folosesc SONDELE (`app/utils/http_profile`) | **200**, 142.696 octeti |

De aici campul `impersonate: "chrome"` in intrarea din registru. Lectia trece
dincolo de elefant: **sondele si productia merg pe doua amprente diferite**, deci o
sonda verde NU dovedeste ca domeniul merge in productie — doar verificarea live
prin calea de productie o dovedeste.

### Stocul — `in_stock=None` PRIN DESIGN (ELF-1b)

elefant.ro **nu randeaza stocul server-side nicaieri**. PDP-ul unui produs pe care
catalogul il claseaza `AvailableFlag-0` („Indisponibil") e identic cu al unuia in
stoc: din 12 semnale verificate, ZERO separa ramurile; singura diferenta de
testing-id intre paginile comparate a fost `old-price`, adica ramura de PRET.
PDP-ul n-are nici macar mecanism de inventar (`GetInventoryStatus`,
`inventory-status`, `js-product-sold-out` = 0 aparitii), iar ETA-ul livrarii e un
`<span class="js-eta" id="ArrivalTime"></span>` GOL pe toate paginile.

Trei semnale par sa spuna stocul si toate sunt FALSE — enumerate si in comentariul
extractorului, ca sa nu le „repare" nimeni din reflex:

| semnal | de ce nu merge |
|---|---|
| `[data-testing-id="addToCartButton"]` | prezent identic pe produsul indisponibil, fara `disabled` — ar da `True` mereu |
| bara sticky | `StickyAddProduct` SI `StickyNotAvailable` („Indisponibil") exista amandoua in DOM pe ORICE produs, ambele cu `display: none` |
| `data-sold-out-text="Stoc epuizat!"` | sablon pe fiecare placa din ORICE listare (61 aparitii si in cea de indisponibile, si in cea in stoc), ascuns in `div.hidden.js-product-sold-out-text` |

Stocul real traieste doar in `GetProductData-GetInventoryStatusForProducts`,
declarat de LISTARE prin `data-inventory-status-url` si apelat de JS — NEMASURAT
(probabil POST + `SynchronizerToken`). Avalul e tri-state (`StockBadge` -> „Stoc
necunoscut", garda `is not None` in `products.py`), deci `None` e informatie
corecta, nu lipsa de informatie.

> RAMANE NEEXCLUS ca produsele din `AvailableFlag-0` sa fie totusi cumparabile,
> iar flagul sa insemne altceva decat „epuizat". Cele 2 cereri ale ELF-1b nu
> departajeaza; ar departaja doar endpoint-ul de inventar.

### Navigare si material pentru axa D (DOCUMENTAT, nu implementat)

* URL de produs: `/<slug>_<uuid>`, unde `<uuid>` e `data-sku`-ul din listare.
  Ruta `ViewProduct-Start?SKU=<uuid>` (prefix
  `/INTERSHOP/web/WFS/elefant-elefantRO-Site/ro_RO/-/RON/`) intoarce PDP-ul
  complet, 200, fara redirect — utila cand ai doar `data-sku`. Atentie: pagina
  venita pe ruta asta **nu poarta `link rel=canonical`**.
* Outlet: `https://www.elefant.ro/list/promotii-speciale/lichidari-de-stoc/filters/warehouse_stock-true`
  — ~9.060 produse, 151 pagini x 60, `?pag=N`. **NU** se ajunge la el prin
  `data-testing-id="Outlet-link"`: acela e un testing-id reciclat pe slotul de link
  promotional din bara de utilitati (Marketplace / Targul de cadouri / Esentiale,
  toate CMS, doua dintre ele intr-un comentariu HTML).
* Listarile implicite arata doar produse in stoc (`AvailableFlag=1` in
  `SearchParameter`); filtrul de indisponibile e ascuns utilizatorului printr-o
  regula CSS din pagina: `li:has(a[href*="AvailableFlag-0"]) { display: none !important; }`.
* Scheletul de listare **poarta link canonic**, pe `a.product-list-item__sold-out-wrapper`,
  frate al lui `div.lazy.inventory-item` in `div.product-list-item`. Deci un val D
  ajunge la PDP-uri FARA hidratare.
* Hidratarea placii (`data-action` -> `ViewProductTileAsync-Start`) ramane utila
  pentru PRETURI: placa poarta AMBELE preturi si eticheta de discount, la **5,7 KB
  fata de 133 KB pagina** — de ~23x mai ieftin, la aceeasi 1 cerere/produs.

---

## G1-1/G1-2 — sivasdescalzo.com (Next.js/RSC) si tezyo.ro (Magento 2)

Ultimele doua domenii ale Grupului 1. Amandoua erau marcate in lista master
„sonda Shopify la implementare; daca nu e Shopify -> jsonld", iar miza era ca un
domeniu Shopify confirmat ar fi intrat pe AMBELE axe dintr-un foc (L prin metoda
`shopify`, D gratis prin `shopify_domains()`). **Masuratoarea le-a infirmat pe
amandoua**, deci Grupul 1 se inchide fara acel castig. Sonda: 12 cereri in total
(10 in G1-1 + 2 in pasa 2), dump-urile in `scripts/diagnostics/dumps_g1/` si
`dumps_g1_pasa2/` (gitignorate), fragmentul de listare in
`backend/tests/fixtures/listing/tezyo.ro_cards.html`.

### Amprenta — de ce niciunul n-are camp `impersonate`

Doctrina ELF-2 aplicata din start: sonda a masurat cu profilul de PRODUCTIE al caii
retail, nu cu cel de sonda, iar la challenge ar fi escaladat pe profilul alternativ
si apoi pe `firefox135`, consemnand care a raspuns. **Toate cele 12 cereri au primit
2xx pe prima incercare**, deci lantul de escaladare nu s-a activat niciodata si
registrul nu are ce suprascrie. Spre deosebire de elefant.ro, aici sonda verde chiar
dovedeste ca merge in productie.

### sivasdescalzo.com — `method: jsonld`

Nu e Shopify: `/products.json` da **404** cu `<html id="__next_error__">`, iar home-ul
poarta `x-powered-by: Next.js` si 69 de referinte `/_next/static`. Zero markeri
Shopify in corp, headere sau cookies.

* **Moneda e USD, nu EUR**, desi magazinul e spaniol. Nu e artefact de masurare:
  ld+json (`priceCurrency: "USD"`), payload-ul RSC
  (`price_range.regular_price.currency`) si textul vizibil (`$190`) spun toate acelasi
  lucru. `EUR` apare de 39 de ori in pagina, dar **exclusiv** in tabelul de metode de
  livrare per tara (`"country_code":"AT" … "currency":"EUR"`). Home-ul expune un
  singur prefix de limba (`/en/`). Moneda se citeste din pagina, conversia BNR acopera.
* **ld+json lipseste pe unele pagini**: pe `/en/p/svd-gift-card` sunt **zero** blocuri
  `application/ld+json` si zero aparitii de `"price"`. Verificat cu extractorul real pe
  dump: `parse_product_html` ridica `no_product_data`. Acesta e comportamentul CORECT
  acolo, nu un bug de raportat.
* Marimile stau doar in RSC (`self.__next_f`), nu in ld+json — `hasVariant` lipseste,
  exista un singur `"sku"`. Cine are nevoie de ele deschide o runda de tip Vinted.
* **Axa D e scumpa**: `/en/l/active-promotions` e o pagina de ATERIZARE, nu o listare —
  3.549 de caractere de text vizibil, doua linkuri `/p/`, zero `<del>`. Listarea e
  hidratata client-side prin RSC, deci axa D cere o runda separata in valul D.

### tezyo.ro — `method: jsonld` + descriptor de listare

Magento 2, confirmat de cookie-urile de server `X-Magento-Vary` si `PHPSESSID`, de 67
de aparitii `Magento_` si de `requirejs/mixins`. Foloseste acelasi CDN ca otter.ro
(`cdn.otter.ro`). `/products.json` da 404.

**Doua forme de ld+json, masurate pe doua PDP-uri alese deliberat** (unul cu reducere
si marimi, unul la pret plin fara variante):

| forma | tip | pret | stoc |
|---|---|---|---|
| produs simplu | `Product` + `Offer` | `price: "27.00"` | `availability: InStock` |
| produs cu marimi | `ProductGroup` + `AggregateOffer` | `lowPrice`/`highPrice` | in oferta IMBRICATA |

Pe forma agregata, pretul si stocul stau in `AggregateOffer.offers[]` si in
`hasVariant[].offers` — cate o oferta pe marime, fiecare cu `size`, `sku` si
`availability` proprii. Agregatul in sine n-are `availability`: exact tiparul f64/VTEX
care a cerut coborarea adaugata la VTX-2, iar extractorul o face deja — verificat pe
dump, iese `is_aggregate: true` cu 5 variante (35–39), fiecare in stoc.

* **Referinta taiata NU e in ld+json**: `lowPrice == highPrice == pretul platit`
  (244.00), iar 349,00 lei apare doar in DOM (`.old-price`) si in cardurile de listare.
* `.product-info-stock-sku` poarta placeholderul Magento **neinlocuit** — literal
  `"Numai %1 ramase SKU 3WMS13114DT5519999"` — deci textul de stoc din DOM e
  inutilizabil. Datele structurate sunt sursa buna.
* Omnibus: **absent**, masurat atat pe listare cat si pe ambele PDP-uri — de aici
  `reference_kind: "nemarcat"`.

### Axa D — listarea de reduceri, in scannerul DEAL-2 (FACUT)

`/reduceri/pentru/femei`: **1.655 de produse pe 69 de pagini**, citit verbatim din
`#toolbar-amount` („Produsele 1 - 23 din 1655"). `max_pages: 80` e plasa, nu tinta.

Descriptorul e aproape geamanul lui otter.ro — aceeasi tema Magento — cu doua note:

* **titlul vine din TEXTUL ancorei**: cardul n-are un `h2`/`h3` de nume, deci `title`
  tinteste chiar `a.product-item-link`. Nu a cerut conventie noua (`_titlu_of` ia
  textul oricarui selector), dar e primul descriptor de forma asta, deci e pinuit de
  `test_tezyo_titlul_vine_din_textul_ancorei`.
* **ambele ramuri de pret sunt in atribut**: verificat offline inainte de implementare,
  ramura taiata ARE `data-price-amount="349"` (`data-price-type="oldPrice"`), la fel ca
  cea platita — deci tot descriptorul merge pe `attr_float` si nu a fost nevoie de
  rezerva pe text cu `eu_comma`.
* Pretul platit se ia de pe `[data-price-type='finalPrice']`, nu de pe
  `.special-price [data-price-amount]`: pe cardurile reduse sunt acelasi nod, dar
  `finalPrice` il poarta si cardurile la pret plin, deci un produs nereus nu dispare
  tacit daca listarea ajunge sa contina unul.

**ACOPERIRE PARTIALA, asumata**: doar sectiunea femei e masurata. Celelalte sectiuni
de reduceri (barbati, copii) se adauga in valul D, dupa sondare — nu se presupun aici.

---

## G2A-1/G2A-2 — powerup.ro (OpenCart) pe ambele axe; badabum.ro nu exista

Restantele electronice RO. O sonda de 7 cereri (din 16 permise) si o implementare.
Dump-urile stau in `scripts/diagnostics/dumps_g2a/` (gitignorate), fragmentele
folosite de teste in `backend/tests/fixtures/powerup/` si
`backend/tests/fixtures/listing/powerup.ro_cards.html`.

### badabum.ro — NU intra, si nu din cauza vreunui anti-bot

Lista master il marca „anti-bot probabil redus". Masuratoarea a infirmat premisa
insasi: domeniul **nu are inregistrare A si nici AAAA**, deci nu exista server web
la care sa te conectezi. Zona e delegata la Cloudflare
(`amir.ns.cloudflare.com` / `miki.ns.cloudflare.com`) si are MX activ catre
Microsoft 365 (`badabum-ro.mail.protection.outlook.com`) — domeniul e detinut si
folosit pentru email, dar nu serveste niciun magazin. Verificat si prin resolver
public (8.8.8.8), cu `powerup.ro` drept control (a raspuns cu adresa). Nu s-a
cheltuit decat 1 cerere, esuata la DNS; celelalte 7 au ramas nefolosite.

### powerup.ro — `method: custom`, `powerup_opencart` (FACUT)

OpenCart cu tema proprie: `index.php?route=`, `catalog/view/theme` in corp,
`x-powered-by: PHP/7.3.33`, `server: LiteSpeed`. Toate cele 6 cereri au raspuns 2xx
pe amprenta de PRODUCTIE, deci fara camp `impersonate`.

Fluxul generic chiar n-are ce citi — verificat pe dump-urile reale,
`parse_product_html` ridica `no_product_data`: zero ld+json, zero microdata, zero OG
de pret. Testul `test_powerup_fluxul_generic_chiar_nu_poate_citi_pagina` pinuieste
asta, ca la elefant.

Blocul de pret, VERBATIM din `powerup.ro_prod_red1.html`:

    <div class="product-price clearfix">
      <span class="full-price">26.900<sup>,00</sup> LEI</span><br/>
      <span class="discount-price"><i>19.990<sup>,00</sup> LEI</i>
        <span class="price-unit">/ buc.</span></span>
    </div>

**Capcana din LOT1, transata definitiv.** Nota veche marca `.discount-price` drept
„candidat" si semnala `.total-price=0,00` ca posibila capcana, dar micro-sonda se
facuse pe produse NEREDUSE, unde nimic nu discrimineaza. G2A-1 a masurat testul de
componente partajate pe doua produse cu preturi complet distincte (pid 179352:
26.900 -> 19.990; pid 227146: 955,34 -> 637,78):

| selector | pagina A | pagina B | verdict |
|---|---|---|---|
| `.discount-price` | 19.990,00 | 637,78 | pretul PLATIT |
| `.full-price` | 26.900,00 | 955,34 | referinta taiata |
| `.total-price` | 0,00 LEI | 0,00 LEI | **COSUL** — componenta partajata |
| `.price-new` / `.price-old` / `.price` / `.special-price` / `.old-price` | — | — | absente (nu e tema standard) |

Trei finete masurate, toate in cod:

* **Ancorarea in `.product-price` e obligatorie**: `.discount-price` apare de doua
  ori pe pagina, a doua oara ca `.discount-price.nav-price` in bara de sus. Fixture-ul
  de test pastreaza dublura, iar testul ii da o valoare diferita ca sa poata
  discrimina un selector neancorat.
* **Zecimalele stau in `<sup>`**, deci textul se ia cu separator GOL (`get_text("")`
  da „19.990,00LEI"; cu spatiu ar iesi „19.990 ,00 LEI").
* **`.price-unit` („/ buc.") se scoate inainte de parsare**: apare doar la unele
  produse, iar parserul strict ar respinge textul cu sufix — s-ar pierde pretul
  exact pe produsele vandute la bucata.

Moneda e `"RON"` **din cod**, si e singura intrare unde se intampla asta: pagina n-o
poarta nicaieri ca data structurata. Singurul indiciu e sufixul „LEI" din textul
vizibil, pe care parserul strict deja il cere ca sa accepte valoarea. Tiparul NU se
generalizeaza la domeniile unde moneda e masurabila.

Stocul e `None` **nemasurat** — spre deosebire de elefant, unde None e o decizie
sprijinita pe 12 semnale verificate, aici pur si simplu nicio pagina de produs
epuizat n-a fost sondata. Pe `/refurbished-sh` produsele sunt bucati unice, deci
stocul chiar conteaza (tiparul foto-erhardt); o micro-sonda viitoare poate ridica
asta la True/False.

**RISC DE CALITATE A DATELOR, consemnat:** titlurile difera pe TREI surse pentru
acelasi produs — slug-ul URL zice `ryzen-9-9950x3d ... rtx-5090`, textul ancorei din
listare zice „AMD Ryzen 7 9800X3D ... RTX 5080", iar `<title>`-ul PDP-ului zice
„AMD Ryzen 9 9950X ... RTX 5080". `<h1>` e GOL, deci numele vine din `<title>`.
Verificat pe HTML-ul verbatim al aceleiasi ancore: e inconsistenta site-ului, nu a
masuratorii. Pentru axa D inseamna ca titlul din card poate descrie alta configuratie
decat produsul de la acel URL.

### Axa D — `/refurbished-sh` in scannerul DEAL-2 (FACUT)

„Afişare 1 - 40 din **605** (16 pagini)", paginare `?page={n}`, `max_pages: 20` ca
plasa. Doua capcane, amandoua in descriptor:

* **`products5` e obligatoriu in selectorul de card.** Pe dump-ul SH exista 55 de
  noduri `div.item-display-box`: 40 in grila (`.products5`) si 15 intr-un carusel de
  recomandari. Fara token, scannerul ar scana caruselul — capcana din LOT5.
* **Quickview-urile se exclud prin `a:not(.quickview)`.** Fiecare card poarta doua
  ancore catre acelasi produs, iar sonda a cazut exact aici: `prod_red2` a nimerit
  `route=product/quickview&product_id=179352`, adica al doilea „produs" era acelasi
  cu primul, ceea ce a invalidat testul de componente partajate pana la pasa de
  corectie. Verificat pe toate cele 40 de carduri: zero cazuri in care selectorul
  cade pe quickview.

Pretul se ia pe TEXT, nu pe atribut — tema nu expune valoarea numerica nicaieri.
Parserul `eu_comma` EXISTENT digera forma cu `<sup>` fara nicio modificare: el curata
orice non-cifra/punct/virgula, deci si spatiul pe care `get_text(" ")` al scannerului
il insereaza intre intreg si zecimale. Omnibus: absent si pe listari, si pe PDP-uri.

**ACOPERIRE PARTIALA, asumata**: doar `/refurbished-sh`. `/oferte-speciale`
(5.668 produse, 142 pagini) asteapta extensia multi-listing per domeniu, la valul D.

---

## G2B-1/G2B-2 — lotul EU de electronice: 5 sondate, 1 intrat

Cel mai mare lot de sonda de pana acum: pccomponentes.com, reichelt.com, conrad.com,
cyberport.at, notebooksbilliger.de. 23 de cereri din 30 (18 in pasa 1, 5 in pasa de
corectie). Dump-urile stau in `scripts/diagnostics/dumps_g2b/` si `dumps_g2b_pasa2/`
(gitignorate).

| domeniu | verdict | profil care a raspuns | moneda |
|---|---|---|---|
| pccomponentes.com | **Grup 4** — Cloudflare | niciunul (403 pe toate trei) | — |
| reichelt.com | nemasurat pe PDP; redirect spre `.de` | implicit al productiei | € vizibil |
| conrad.com | listari client-side | `firefox135` | — |
| **cyberport.at** | **`jsonld` — INTRAT** | `chrome` | **EUR** |
| notebooksbilliger.de | **Grup 4** — Akamai | niciunul | — |

**Trei domenii au cerut profiluri diferite de cel implicit al productiei**, iar doua
dintre ele ar fi fost clasate FALS drept Grup 4 fara lantul de escaladare ELF-2:
cyberport raspunde pe al doilea profil din lant, conrad abia pe al treilea. Tabelul
concret al profilelor per domeniu ramane cel din sectiunea ELF-2.

### cyberport.at — `method: jsonld` (FACUT)

Next.js. PDP-ul poarta ld+json complet, verificat cu extractorul REAL pe dump-ul
sondei (`cyberport.at_prod1_p2.html`): pret **1279.0**, moneda **EUR**, in stoc,
`method: jsonld`. Structura, verbatim:

    {"@type":"Product","name":"Apple iPhone 17 Pro 256GB Cosmic Orange MG8H4ZD/A",
     "sku":"A415-20G","gtin13":"0195950627442","brand":"Apple",
     "offers":[{"@type":"Offer","price":1279,"priceCurrency":"EUR",
       "availability":"https://schema.org/InStock", …}]}

Oferta mai poarta `priceValidUntil`, `priceSpecification`, `shippingDetails`,
`hasMerchantReturnPolicy` si `seller`. Moneda e INCRUCISATA, nu presupusa: `EUR` in
datele structurate si `€` in afisaj (lectia sivasdescalzo, unde un magazin spaniol
servea USD).

* **Referinta e o ETICHETA TEXTUALA, nu un `<del>`/`<s>`**: `taiat_in_dom` iese GOL,
  iar textul vizibil spune „Store 1.299,00 € UVP 1.279,00 € inkl. MwSt." Deci
  Omnibus e de tip **PRP/UVP**, iar ld+json poarta PLATITUL (1.279), nu UVP-ul.
* **Capcana B-Ware**: aceeasi pagina poarta si un al treilea pret — 1.151,10 € „Als
  B-Ware schon ab" — care e ALTA oferta, nu pretul produsului nou. Un extractor care
  ar lua „cel mai mic pret vizibil" ar raporta gresit.
* **Outlet identificat, NEMASURAT**: `/apple-und-zubehoer/outlet-a-b-ware-.html`,
  gasit in home pe tiparul `outlet`. Plafonul per domeniu (6 cereri) s-a consumat pe
  escaladari de amprenta, deci axa D cere intai o micro-sonda de 2-3 cereri.

### Celelalte patru — de ce n-au intrat

* **pccomponentes.com — Grup 4.** 403 cu interstitiul „just a moment" pe TOATE cele
  trei profiluri din lant. Asteptarea listei master („override probabil de
  impersonate") s-a infirmat: nu e o chestiune de amprenta.
* **notebooksbilliger.de — Grup 4, Akamai.** Homepage-ul da **404** pe primele doua
  profiluri, cu o pagina de eroare PERSONALIZATA a magazinului („uups... Die Seite
  wurde nicht gefunden" + id de urmarire) — deci un 404 poate fi blocaj mascat, nu
  pagina lipsa. Pe al treilea profil raspunde **200, dar cu corp de challenge**:
  cookie `_abck`, `sec-if-cpt-container`, `behavioral-content`, 2.875 de octeti,
  ZERO text vizibil. Un 200 se verifica pe CONTINUT, nu pe status. Ipoteza „doar PJ
  pentru RO" din lista master a ramas NETESTATA — blocajul e anterior oricarui
  semnal de continut.
* **reichelt.com — nemasurat, si pe alt domeniu decat se credea.** Home-ul e un
  selector de tara/limba, nu un magazin; forma reala e `reichelt.com/<tara>/<limba>/`
  (`ro` chiar exista). Dar nici `/ro/de/` nu expune produse: 6 candidati, toti pagini
  editoriale. In plus `.com` REDIRECTIONEAZA spre `.de` —
  `url_final = https://www.reichelt.de/magazin/?lang=de&country=ro`. Urmatorul pas e
  o sonda pe **reichelt.de**, pornind dintr-o pagina de CATEGORIE.
* **conrad.com — listari client-side.** Home (204 KB) si `/en/promotions/sale.html`
  (197 KB) sunt SSR dar au ZERO carduri cu pret si zero simboluri de moneda, iar
  ld+json-ul lor e doar `Corporation`. Singurele linkuri cu cifre sunt de categorie
  (`/en/o/weather-stations-0514060.html`, `/en/c/scanners-17157.html`). Cookie-ul
  `pdpSSR=true` sugereaza ca PDP-urile SUNT server-side, deci urmatorul pas e un URL
  de produs obtinut din **sitemap**, nu din listari.

Nota de metoda: `cf-ray` NU e semn de blocaj. Conrad l-a servit pe un raspuns 200
perfect valid (`cf-cache-status: HIT`) — Cloudflare il pune pe orice raspuns care
trece prin reteaua lui.

---

## G2C-1/1b/2 — outlet incaltaminte/sport RO: 4 sondate, 2 intrate

Intrarea #42 din lista master, patru domenii intr-o singura pozitie. Doua sonde
(16 + 6 cereri) si o implementare. Dump-urile in `scripts/diagnostics/dumps_g2c/` si
`dumps_g2c_sizeer/` (gitignorate).

| domeniu | verdict | profil | moneda |
|---|---|---|---|
| **sportvision.ro** | **`jsonld` — INTRAT** | implicit al productiei | **RON** |
| **sizeer.ro** | **`jsonld` — INTRAT** | implicit al productiei | **RON** |
| ccc.ro | domeniu PARCAT — nu e magazin | implicit | — |
| hervis.ro | redirect -> sportsdirect.ro, listari client-side | implicit | — |

Ambele ipoteze de grup din briefing au fost INFIRMATE: `ccc.ro` nu apartine grupului
CCC (nu e nici magazin), iar sizeer si sportvision nu au nimic comun — sizeer e in
spatele Akamai fara markeri de platforma, sportvision e NBSHOP.

### sportvision.ro — `method: jsonld` (FACUT)

`Product` + `Offer` cu `price` / `priceCurrency: RON` / `availability`, plus `sku`,
`brand`, `productID`, `aggregateRating`, `hasMerchantReturnPolicy`, `priceValidUntil`,
`shippingDetails`. Moneda incrucisata: RON in date structurate SI in afisaj. Omnibus
ABSENT pe PDP-urile masurate; niciun `<del>`/`<s>`.

Platforma e **NBSHOP** (`server: Custom Server`, cookies `NBIDSN` /
`NBPHPSESSIONSECURE`) — aceeasi cu `buzzsneakers.ro` (LOT3), care e tot `jsonld`.
Consemnat ca IPOTEZA, nu ca fapt: markerul si verdictul coincid, dar inrudirea n-a
fost dovedita cu fragmente verbatim din ambele parti, fiindca nu exista dump
buzzsneakers.

Axa D e val ULTERIOR: `/produse/noua-colectie` are **2.312 produse**, dar paginarea
nu e clasica — `a[rel='next']` cu textul „Arata mai multe", deci incarcare
client-side, nemasurata.

### sizeer.ro — `method: jsonld`, FARA override de amprenta (FACUT)

`Product` + `Offer` cu `price` / `priceCurrency: RON` / `availability`, plus `sku`,
`mpn`, `brand`, `color`, `category`, `aggregateRating`, `seller`, `shippingDetails`.

**OMNIBUS `min30` EXPLICIT — primul din tot catalogul.** Celelalte domenii au dat
„prp" (bergfreunde, cyberport, f64) sau „nemarcat". Aici referinta e chiar minimul
legal pe 30 de zile, ca ETICHETA TEXTUALA, fara `<del>`/`<s>` — `taiat_in_dom` iese
gol. Verbatim de pe PDP-ul Nike:

    239,99 RON cu TVA 259,99 RON -8%
    (Cel mai mic pret din ultimele 30 de zile inainte de reducere)

**Trei componente partajate**, masurate pe ambele PDP-uri: `18 RON` (livrare),
`219,99 RON` (promotie din megamenu, „2 tricouri la 219,99 RON") si `400 RON` (prag
de livrare gratuita). ld+json le ocoleste — da exact pretul propriu al paginii
(239.99, respectiv 349.99). Un extractor pe text vizibil ar fi luat 219,99 pe orice
produs.

**Misterul amprentei, inchis.** Sonda G2C-1 raportase „challenge pe profilul de
productie", ceea ce ar fi cerut un `impersonate`. Verdictul era ARTEFACT: detectorul
sondei trata cookie-ul `_abck` drept blocaj, iar Akamai il pune pe ORICE raspuns care
trece prin el — exact ca `cf-ray` la Cloudflare. Raspunsurile asa-zis blocate aveau
1,8-2,1 MB, ld+json complet si preturi reale. Controlul de la G2C-2 a extras live pe
profilul IMPLICIT al productiei, cu succes (239.99 RON, `jsonld`), deci intrarea NU
are camp `impersonate` si harta pinuita ramane pe 5 domenii.

Regula generalizata pentru sonde: un cookie de infrastructura anti-bot (`_abck`,
`ak_bmsc`, `bm_sz`, `cf-ray`) arata ca traficul TRECE prin acel furnizor, nu ca a
fost blocat. Verdictul de blocaj se da pe status, pe interstitiul din corp si pe
ABSENTA semnalelor pozitive.

Axa D e val ULTERIOR: `/outlet` n-are produse server-side utile — din 92 de carduri
candidate, 87 poarta cele doua componente partajate si doar 5 au pret propriu — si
n-are paginare server-side.

### Celelalte doua — de ce n-au intrat

* **ccc.ro — domeniu PARCAT, nu magazin.** `server: Caddy`, `<title>ccc.ro</title>`,
  `robots: noindex`, descriere „Find the best information and most relevant links on
  all topics related to", **6 caractere** de text vizibil, zero linkuri interne.
* **ccc.eu — poarta de tara CLIENT-SIDE.** `https://ccc.eu/` redirectioneaza masurat
  la `/start/`: **853 de octeti**, 23 de caractere vizibile, „SELECT YOUR COUNTRY",
  iar `<div class="countries-list">` e GOL. In corpul brut nu exista niciun `/ro/`,
  `ccc.ro` sau `hreflang="ro"` — deci calea RO nu se poate obtine fara JS, iar a o
  construi ar fi fost ghicit. Al doilea domeniu cu poarta de tara, dupa reichelt.
* **hervis.ro — redirectioneaza la `sportsdirect.ro`** (Frasers Group, vizibil in
  `frasers.group` printre gazdele de asset). Next.js + Akamai. Listarea `/sale` da
  200 dar are 39 de linkuri, toate de CONT, si zero preturi: client-side complet.
  Candidat pentru valul de BROWSER, alaturi de conrad.com.

---

## G2F-1/1b/2 — sub-lotul sport/outdoor: 4 sondate, 3 intrate

Doua sonde (17 + 2 cereri) si o implementare. Dump-urile in
`scripts/diagnostics/dumps_g2f/` si `dumps_g2f_intersport/` (gitignorate),
fragmentele folosite de teste in `backend/tests/fixtures/intersport/`.

| domeniu | verdict | profil | moneda |
|---|---|---|---|
| **intersport.ro** | **`custom` — INTRAT** | implicit | **RON** (din cod) |
| **toolnation.nl** | **`jsonld` — INTRAT** | implicit | **EUR** |
| **direct-running.com** | **`jsonld` — INTRAT** | implicit | **USD** |
| decathlon.ro | Grup 4 — Cloudflare la home, pe toate profilurile | niciunul | — |

### intersport.ro — `method: custom`, `intersport_custom` (FACUT)

Fluxul generic chiar n-are ce citi: ld+json are doar `Organization` si
`BreadcrumbList`, iar `[itemtype*="Product"]` lipseste. Exista un `itemprop="price"`
pe nodul de pret, dar e **ORFAN** — fara `itemscope` de `Product` in jur.

Finete masurata, care conteaza pentru testul-garda: pagina reala are **DOUA** noduri
`itemprop="price"`, cu aceeasi valoare, in containere diferite
(`div.current-price-container` si `div.prices-container`). Pe pagina intreaga
genericul ridica `no_product_data`; pe un fragment care pastreaza doar UNUL dintre
ele, genericul reuseste sa citeasca `microdata`. Fixture-ul de test le poarta pe
amandoua — altfel testul-garda ar fi trecut degeaba.

Contractul extractorului:

* pret platit din **atributul** `data-current-price` (`"305,99"` — virgula zecimala,
  deci parser strict propriu, tiparul powerup), citit de pe nodul ancorat in
  `.current-price`;
* **CAPCANA**: `span.points-gain` poarta ACEEASI valoare cu alt inteles —
  „305,99 puncte" de fidelitate, in `div.points-gain-container.hidden`. O selectie
  libera pe cifra ar citi punctele. Fixture-ul o contine, iar un test o pinuieste;
* referinta taiata (`span.deleted-price` in `div.deleted-price-container`) NU intra in
  contract — e materie de val D;
* moneda `"RON"` din COD: „LEI" apare doar in textul de langa pret;
* `in_stock: None` NEMASURAT — semnalele se contrazic pe aceeasi pagina („Adauga in
  cos" x2, „stoc" x10, „Indisponibil" x3), plauzibil fiindca stocul e per marime.
  `div.out-of-stock` e INTERZIS ca semnal: apare pe TOATE cele 30 de carduri ale
  listarii, fara `display:none` inline — sablon ascuns prin CSS extern, exact tiparul
  `data-sold-out-text` de la elefant.

Componente partajate, masurate pe ambele PDP-uri: `10 lei`, `17 lei`, `50 lei`,
`99.99 lei`, `199.99 LEI`, `250 lei` (praguri de livrare si promotii din header);
propriile sunt 305,99/611,99 si 169,99/299,99 — exact perechile din cardurile
listarii. Axa D e val ULTERIOR: `/sale/` are 86 de carduri cu
`article.x-product-box`, dar paginarea e nemasurata.

### toolnation.nl — `method: jsonld`, categoria noua `bricolaj` (FACUT)

Magento. `Product` + `Offer` cu `price` / `priceCurrency: EUR` / `availability`, plus
`itemCondition`, `seller`, `url`.

**Preturile NU apar deloc in textul vizibil** — sunt hidratate client-side si exista
DOAR in datele structurate. O garda care cere preturi vizibile declara fals „fara
semnale de magazin"; s-a intamplat la sonda si a impiedicat fotografia listarii.

Capcane masurate pe ambele PDP-uri: bannerul `€250` („Summer Deals") si **numarul de
telefon** al magazinului, `31 85 237 15 00 €`, pe care regexul de pret il citeste ca
suma. ld+json le ocoleste pe amandoua.

Omnibus: **NEMARCAT**. Atentie la limba: `van` e prepozitie in neerlandeza, nu marcaj
de pret — un tipar Omnibus care o include raporteaza fals (24 de aparitii pe un PDP).
Termenul relevant ar fi `adviesprijs`.

**Axa D — cel mai promitator caz de pana acum:** listarea `aanbiedingen.html` poarta
**24 de noduri `Product` COMPLETE** in ld+json, fiecare cu pret, moneda, stoc si url.
O singura cerere da toate produsele gata parsate, fara descriptor de carduri — primul
candidat pentru un mod `ldjson-listing` al scannerului.

Categoria `bricolaj` e introdusa aici (unelte/atelier); hornbach si action urmeaza.

### direct-running.com — `method: jsonld` (FACUT)

Domeniul REAL e **fara `www`**: redirect masurat `www.direct-running.com` ->
`direct-running.com`. `Product` + `Offer` cu `price` / `priceCurrency` /
`availability`.

**Moneda e USD, nu EUR** — incrucisat intre ld+json si afisaj (`$130.00`, `$99.05`,
`$4.95`). Conversia BNR acopera USD.

**Tara e o DEDUCTIE SLABA, nu o masuratoare.** Singurul semnal gasit in dump-uri e
„Customer service in France", repetat identic pe home, PDP si listare. E serviciu de
clienti, nu sediu juridic: nu exista adresa, VAT sau numar de inregistrare, iar
moneda USD sta in tensiune cu el. Campul `country: "FR"` se corecteaza daca apare o
dovada mai buna. Axa D: `/outlet` are 97 de carduri — val ULTERIOR.

### decathlon.ro — Grup 4

Cloudflare „Just a moment" pe TOATE cele trei profiluri, chiar la home. Intra in valul
de browser, alaturi de cardmarket.com, conrad.com si sportsdirect.ro.

---

## G2F-3/G2F-4 — sub-lotul pet: 2 sondate, 1 intrat

| domeniu | verdict | PDP-uri masurate | moneda |
|---|---|---|---|
| zooplus.ro | **jsonld, validat** | 2/2 | RON |
| fressnapf.ro | catalog client-side pe toate cele 4 niveluri | 0 | — |

### zooplus.ro — `method: jsonld`, categoria noua `pet` (FACUT)

Next.js. ld+json-ul e un **`@graph`**, iar produsul din el e un **`ProductGroup` cu
`hasVariant`** — o varianta per gramaj/pachet, fiecare cu propriul `Offer` (`price`,
`priceCurrency: RON`, `availability`). NU e un `Product` cu `offers`-lista; distinctia
conteaza, fiindca pretul product-level iese din `_aggregate_variants` (minimul
variantelor in stoc, regula existenta de la FASHION-1), nu din calea de lista.

Masurat: PDP1 `/shop/pisici/jucarii_pisici/mingiute/364856` — o varianta, 13,52 RON;
PDP2 `/shop/pisici/hrana_uscata_pisici/purizon/pachete_de_testare/1347045` — zece
variante intre 4,90 si 50,26, dintre care una epuizata, deci produsul iese la **4,90**.

**Pretul din ld+json e cel POST-VOUCHER, nu cel de lista.** Pe PDP1 corpul arata
`16,90 LEI` si un `-20%`, iar ld+json publica `13,52` (= 16,90 x 0,8). E **pretul real
platibil**, deci un fapt de exploatare, nu un defect: un deal calculat pe el e un deal
adevarat. De retinut doar la comparatii cu magazine care publica pretul de lista —
acolo zooplus va parea sistematic mai ieftin, si chiar este.

Vitrina poarta componente **partajate** care nu apartin produsului: pragurile de
livrare (`199`, `99 LEI`) si un `9,90` recurent. O extractie pe text vizibil ar culege
cifrele astea drept pret; datele structurate le ocolesc. Fixture-urile din
`tests/fixtures/zooplus/` pastreaza deliberat zgomotul, ca garda sa cada daca extractia
aluneca vreodata pe text.

Forma PDP-ului: `/shop/<cale-de-categorii>/<ID_numeric>`. **ID-ul numeric final e
ancora**; calea de categorii de dinaintea lui variaza si nu e stabila.

**Axa D:** listarea `/shop/oameni_animale/promotii` are **817 produse** si selector
stabil — val ULTERIOR.

### fressnapf.ro — valul de browser

Catalogul e client-side pe toate cele patru niveluri sondate: nimic despre produs in
HTML-ul servit. Intra in **valul de browser**, care ajunge astfel la **7 membri**:
decathlon.ro, conrad.com, sportsdirect.ro, cardmarket.com, fressnapf.ro,
pccomponentes.com si notebooksbilliger.de.

### Regula de semantica a pretului pe liste de oferte (G2F-4)

Runda a aliniat ultima forma de variante care scapase conventiei comune.

Extractorul intalneste **trei** forme in care un produs isi publica variantele, si de
la G2F-4 toate trei raspund la aceeasi intrebare — *cat costa cea mai ieftina varianta
disponibila*:

| forma | unde apare | de unde iese pretul |
|---|---|---|
| `AggregateOffer` cu `lowPrice` | tezyo, f64 | minimul e publicat de magazin, il citim |
| `ProductGroup.hasVariant` / `offers`-lista cu `size` | eobuwie, BSTN, **zooplus** | `_aggregate_variants` — minimul marimilor in stoc |
| `offers`-lista **fara** `size` | sneakersnstuff, direct-running | **G2F-4: minimul ofertelor valide** |

Pana la G2F-4, ultima linie lua **primul element cotat**. Ordinea unei liste de
`Offer` in JSON-LD e insa **arbitrara** — niciun magazin n-o declara semnificativa —
deci pretul produsului atarna de un accident de serializare: la o reordonare tacuta a
feed-ului, acelasi produs isi schimba pretul fara ca magazinul sa fi schimbat ceva.

Detaliu care nu e cosmetic: oferta **intoarsa** e acum cea care a castigat pretul, nu
prima din lista. Moneda si `availability` se citesc din ea, deci altfel pretul ar fi al
unei variante si moneda al alteia. La egalitate castiga prima intalnita, ca rezultatul
sa ramana stabil.

**Raza de actiune, masurata inainte de schimbare** pe toate cele 150 de dump-uri de
sonda: doar **3 noduri** au lista cu >=2 preturi valide (tezyo pdp1, otter prod1,
direct-running pdp2) si la toate primul era deja minimul. Tabelul de regresie a iesit
**integral identic** dupa schimbare. Regula e asadar o **plasa pentru ordinea
viitoare**, nu o corectie de valori de azi — singurul loc unde muta ceva e forma
pinuita sneakersnstuff din teste (149,99 epuizat -> 99,99 in stoc), si acolo muta in
bine. Fiindca niciun dump real nu deosebeste „minim" de „primul", dovada regulii sta
intr-un fixture **explicit sintetic**
(`tests/fixtures/zooplus/pdp2_offers_lista_SINTETIC.html`): preturile reale zooplus
turnate in forma de lista, ordonate descrescator, cu minimul spre coada.

---

## G2F-5/G2F-6 — sub-lotul home&deco: 4 sondate, 4 intrate

| domeniu | metoda | moneda incrucisata | anti-bot | particularitate |
|---|---|---|---|---|
| hornbach.ro | jsonld | ✓ pe text vizibil | niciunul | doua `Offer` cu pret identic |
| bonami.ro | jsonld | slaba (prag partajat) | niciunul | forma PDP CONSTRUITA; listarea n-are ld+json |
| action.com | jsonld | ✓ (`11.95` ↔ `11,95 lei`) | **Cloudflare pe RATA** | pret spart in DOM |
| ro.vivre.eu | jsonld | ✗ neincrucisabila | niciunul | **`availability` = constanta de sablon** |

Primul lot din 2f in care intra TOATE domeniile sondate. Ordinea sondei a fost
hornbach → vivre → bonami → action, iar doua dintre ele au cerut o pasa de corectie
(5 cereri autorizate, 4 folosite).

### hornbach.ro — `method: jsonld`, pe categoria `bricolaj` (FACUT)

ld+json are **doar** `Product`: zero microdata, iar OG poarta `og:type=og:product`
fara `product:price:*`. Datele structurate sunt asadar singura sursa — dar una
completa. Moneda se incruciseaza curat: ld+json `RON` vs afisaj `2333,00 lei` si
`1829,24 lei`. Omnibus **absent**, niciun pret taiat in DOM.

**Forma ofertelor merita atentie:** generatorul publica **doua `Offer` cu ACELASI
pret** (2333.00), care difera doar prin cheile de livrare (`availableAtOrFrom`,
`deliveryLeadTime`, `potentialAction`). E prima ramura lista-de-oferte intalnita pe
un domeniu romanesc dupa G2F-4, iar regula minimului o traverseaza inofensiv:
`min(2333.00, 2333.00) = 2333.00`. Daca maine cele doua livrari ar avea preturi
diferite, regula ar alege-o pe cea mai ieftina — semantica dorita.

PDP-ul are forma `/p/<slug>/<ID_numeric>/`, categoriile `/c/<slug>/S<ID>/`.

**Doua lectii de navigare, ambele costisitoare la sonda:**
1. Home-ul e un shell randat client-side (raport text/HTML **0,0037**, zero preturi
   vizibile) — dar poarta **9 PDP-uri complete**. Home-ul poate fi o sursa de URL-uri
   mai buna decat o listare, contrar ordinii „home → listare → produse".
2. Singurul link din home care se potriveste tiparelor de reduceri e un **articol
   editorial** — `/noutati/campanie-promotionala-curatenie-tip-top-premii-dirt-devil/`,
   prins pe `promo` din „campanie-promotionala". Un tipar de reduceri fara filtru
   negativ pe `/noutati/` si `/stiri/` alege gresit. Aceeasi clasa de defect ca
   `/info/about/shippingcosts` la zooplus (G2F-3).

### bonami.ro — `method: jsonld`, forma PDP CONSTRUITA si confirmata (FACUT)

Next.js. Forma URL-ului de produs **nu exista in niciun dump**: catalogul e hidratat,
listarea are zero ancore de produs, iar rutele din home sunt doar `c`, `cos`,
`inspiratii`, `lista-mea-de-comparare`. URL-ul a fost deci **construit** din primul
`slug` din `__NEXT_DATA__`, prin simetrie cu ruta de categorie masurata `/c/<slug>` —
constructie admisa pe precedentul elefant (ViewProduct-Start), fiindca era singura
cale si fiindca **forma insasi era masuratoarea**. A raspuns: `/p/<slug>`, 200, fara
redirect.

Pe PDP exista ld+json `Product` obisnuit, cu `price` **NUMERIC** (572.9, nu sir) si
`shippingDetails`. Valoarea se confirma incrucisat cu `__NEXT_DATA__`:
`customerPrice.amount.units` 57290 / 10^`scale` 2 = 572,90. Doua surse independente
ale aceleiasi pagini, de acord.

**Listarea, in schimb, n-are ld+json deloc** — si de aici o lectie: un verdict de
domeniu dat pe listare ar fi clasat bonami drept „val de browser", fals. Pentru axa D
datele stau in `initialCataloguePageState.blocks[].products[]` din `__NEXT_DATA__`:
48 de produse, pret ca `units`/10^`scale`, `availability.usableStock` **numeric**
(stoc cu cantitate!), `retailPrice` ca pret de referinta. Val ULTERIOR.

Pretul de referinta **nu** e in ld+json (oferta are doar `price`), deci reducerea nu
se poate calcula din PDP. Zgomot de vitrina: pragul partajat `40 Lei`. `og:type` e
`website`, nu `product`.

### action.com — `method: jsonld`; intrebarea de existenta, INCHISA AFIRMATIV (FACUT)

Domeniul purta in lista master marcajul „verifica daca expune preturi online", deci
s-a tratat ca bipa (G2D-1): prima cerere decide ramura. **Are magazin online**, cu
probe tari — `Offer` cu `price` 3.98 si 11.95 RON, `InStock`, plus `priceSpecification`
si `seller`. Ramura „vitrina" nu s-a declansat.

**Anti-bot pe RATA, nu pe ruta si nu pe profil.** A 4-a cerere intr-un minut a primit
403 cu interstitiul Cloudflare „Just a moment...". Pasa de corectie a separat cele trei
ipoteze in doua trepte (tiparul sephora): **acelasi URL, acelasi profil `chrome131`,
dupa o pauza de 95s → 200**. Escaladarea de profil n-a mai fost necesara.

> **Deschis pentru implementare:** domeniul are nevoie de un interval minim intre
> cereri. Campul `min_fetch_interval_s` EXISTA in registru, dar contractul lui il
> limiteaza explicit la `method: "browser"` (e consumat doar de
> `browser_fetch.fetch_browser_html`, iar suita de registru il si respinge pe alte
> metode). Pe calea HTTP — cea pe care merge action, ca domeniu `jsonld` — nu exista
> azi niciun mecanism echivalent. Intrarea a fost facuta FARA camp, ca sa nu existe
> o protectie doar aparenta; masuratoarea e consemnata aici si in `notes`.

Pretul e **spart in DOM** (`11 95`), deci extractia pe text vizibil e nesigura si
ld+json e sursa. Cifrele mici din pagina (`0,07`–`8,98 lei`) sunt preturi **pe bucata**,
nu ale produsului. PDP `/ro-ro/p/<ID_numeric>/<slug>/`. Ruta `/ro-ro/promocie-saptamanii/`,
linkata din home, da **404 masurat**. Omnibus absent, niciun pret taiat.

### ro.vivre.eu — `method: jsonld` + `ldjson_availability: "untrusted"` (FACUT)

Cheia e pe **subdomeniu**, fiindca acolo duce redirectul MASURAT
`www.vivre.ro` → `ro.vivre.eu` (precedent de cheie cu subdomeniu: `en.afew-store.com`).
PDP-ul are forma `/p-<ID>/<slug>`.

**`availability` din ld+json e o constanta de sablon — dovada:**

| sursa | ce spune despre 8831337 si 1977409 |
|---|---|
| ld+json de pe PDP-ul fiecaruia | `https://schema.org/OutOfStock`, amandoua |
| datele de listare ale ACELUIASI site | `"inStock":true`, amandoua |
| pe tot lotul masurat | `"inStock":true` x24, `"inStock":false` x0 |
| sirul `schema.org/InStock` | **nu apare NICIODATA**, in niciunul din cele 3 dump-uri |

Contradictie pe ACELEASI doua produse, intre doua surse ale aceleiasi pagini de
magazin. Fara flag, extractorul ar fi scris `in_stock=False` pe toate cele **46.536**
de produse: nu o necunoastere, ci o afirmatie falsa si activa, care ar fi ascuns din
feed exact marfa cumparabila. Cu flagul, campul devine `None` — necunoscut, care e
adevarul.

> **Atentie la o capcana de masurare din care era sa iasa concluzia inversa:** o
> numaratoare case-INSENSITIVE dadea „`InStock` x25" pe listare si parea sa infirme
> ipoteza. Case-sensitive, `InStock` apare de **zero** ori; cele 25 erau `"inStock"`
> (camelCase), campul din datele de flux — alt vocabular, alta sursa. „Masurarea
> gresita e prima ipoteza" a functionat exact aici.

PDP-ul e randat client-side la extrem: raport text/HTML **0,0004**, adica ~280 de
octeti de text vizibil (titlu + footer legal). Pretul si stocul nu apar deloc in text.
ld+json e deci SINGURA sursa server-side, iar moneda `RON` **nu e incrucisabila** pe
text — acceptata pe ld+json, 2/2 PDP-uri. Listarea `/products?discount=yes` are
**46.536** de produse — val ULTERIOR.

### Flagul `ldjson_availability: "untrusted"` (G2F-6)

Camp OPTIONAL de registru, o singura valoare admisa. Cand e prezent, extractorul
ignora `availability` din ld+json si lasa `in_stock=None`, in loc sa creada sablonul.

Neutralizarea sta imediat dupa override si **inaintea** microdata, deliberat: flagul
spune ca `availability` DIN LD+JSON nu e de incredere, nu ca domeniul n-are stoc, deci
o sursa independenta (microdata) ramane libera sa completeze campul. Pe vivre cele
doua citiri coincid — pagina n-are microdata — dar distinctia pastreaza flagul cinstit
daca ajunge candva pe un domeniu cu doua surse. Variantele se neutralizeaza odata cu
produsul: stocul lor vine din exact aceeasi `availability`. Pretul si restul extractiei
raman NEATINSE — masurat pe 166 de dump-uri, singura diferenta din tot tabelul de
regresie e stocul celor doua PDP-uri vivre, `False` → `None`.

---

## G2F-7/G2F-8 — biciclete si ceasuri: inchiderea lotului 2f

| domeniu | verdict | metoda |
|---|---|---|
| biciclop.eu | **intrat** | jsonld |
| cellini.ro | **intrat** | custom, `cellini_datalayer` |
| bbcollection.ro | **PARCAT** (masurat integral) | ar fi custom pe DOM |
| veloteca.ro | **inaccesibil de pe IP-ul curent** | — |

Categoriile noi introduse aici: `biciclete` („Biciclete & piese") si
`bijuterii-ceasuri` („Bijuterii & ceasuri").

### biciclop.eu — `method: jsonld`, categoria `biciclete` (FACUT)

WordPress + LiteSpeed. Cheia e **fara `www`**: redirect masurat
`www.biciclop.eu` -> `biciclop.eu`. ld+json `Product` cu `price` / `priceCurrency:
RON`, incrucisat cu afisajul (`199,99 lei` / `189,99 lei`).

**`Offer` n-are `availability`** — cheile masurate sunt exact
`[@type, url, price, priceCurrency]` — deci `in_stock` iese `None`. E o lipsa
ONESTA, nu o scapare: magazinul chiar nu publica stoc, pagina scrie
*„Contacteaza-ne pentru confirmare stoc. Verifica disponibilitatea"*.

Referinta taiata (`<del>257 lei</del>`) exista **doar in DOM** si e etichetata
explicit *„Pret recomandat: 257 lei -22% 199,99 lei"* — adica **RRP, nu Omnibus**.
Diferenta e materiala: Omnibus cere minimul din ultimele 30 de zile, RRP e pretul
recomandat de producator. A le confunda intr-un calcul de reducere umfla artificial
„chilipirul".

**Ce vinde ONLINE sunt piese si accesorii**, nu biciclete. Paginile `/biciclete*`
sunt editoriale: `/biciclete/` se intituleaza „catalog **istoric**", iar
`/biciclete-mtb/` „**informatii utile**" — categoria masurata are 1 card si zero
produse, iar navigatia laterala listeaza doar componente (Angrenaj, Antifurt,
Butuc pedalier, Frane, Ghidon, Pedale, Pinioane). De aici si numele categoriei:
`biciclete` acopera „biciclete **& piese**", cu accentul azi pe piese.

Componente partajate de footer, de ignorat la orice extractie pe text:
`200.200,00 RON` (capitalul social din datele firmei) si `400 lei` (pragul de
livrare gratuita). Ambele au fost prinse de triajul de preturi partajate.

### cellini.ro — `method: custom` (`cellini_datalayer`), categoria `bijuterii-ceasuri` (FACUT)

PHP propriu (cookie `csCurrencyId`). **Datele de produs exista EXCLUSIV in starea
paginii.** ld+json are doar `Organization` / `WebSite` / `BreadcrumbList`, microdata
lipseste, iar extractorul generic ridica `no_product_data` — pinuit de test, ca sa
aflam daca magazinul adauga vreodata `Product` si codul bespoke devine inutil.

**Identificarea obiectului propriu e miezul extractorului, si e neambigua.** Pagina
poarta **48 de obiecte cu `price`** (carusele de recomandari). Obiectul paginii se
recunoaste dupa cheia `url`, care contine EXACT numele de fisier al PDP-ului, si se
incruciseaza cu `code`:

| PDP | `url` din obiect | `code` | `price` |
|---|---|---|---|
| `...-au-yk18ce26286.html` | `cercei-yoko-london-…-au-yk18ce26286.html` | `AU_YK18CE26286` | 6930 |
| `...-ad-yk18co26296.html` | `colier-yoko-london-…-ad-yk18co26296.html` | `AD_YK18CO26296` | 27990 |

Pe ambele pagini **exact UNUL** din cele 48 de obiecte poarta codul paginii.

**DOM-ul e interzis ca sursa, si nu din preferinta:** textul vizibil are ~**70 de
preturi distincte**, dintre care **8 sunt IDENTICE** intre doua pagini de produse
diferite (carusele partajate). O extractie pe text ar da sistematic pretul altui
produs. Garda din teste foloseste chiar aceasta patologie: fixture-ul contine si
produsul celeilalte pagini, deci acelasi HTML da doua rezultate diferite dupa URL.

Alte masuratori intrate in contract:
* **Pretul**: `price` e INTREGUL de lei (6930, 27990 — `int`), iar banii stau separat
  in `decimalprice` (`"00"` pe ambele), cu `beautifulprice` = `"6.930,00"` ca forma
  afisata. Extractorul le COMBINA: luat singur, `price` ar raporta 6930 pentru un
  produs de 6930,50 — o pierdere tacuta de bani, invizibila pentru orice test scris
  pe preturi rotunde. Tipul e verificat strict: un `price` pe sir e refuzat, nu
  parsat din text.
* **Moneda se CITESTE**, nu se pune din cod: `currencyname` = `"Lei"`, cu
  `currencyid: "1"` si `ronvalue: "1.0000"` ca semnale suplimentare. `RON` ramane
  doar plasa de siguranta.
* **Stocul**: `stock` e sir romanesc, masurat `"in stoc"` pe ambele PDP-uri. Forma
  NEGATIVA e nemasurata (niciun produs epuizat in sonda), deci se afirma doar
  pozitivul — orice altceva ramane `None`, niciodata `False`. Un vocabular de
  epuizare inventat ar ascunde produse cumparabile.
* `oldprice` (`"9240.00"` / `"37320.00"`) si `save_percent` EXISTA in stare dar **nu
  intra in contract** — referinta ramane pentru axa D.

PDP `/bijuterii/filtre/<slug>-<COD>.html` (200, fara redirect). Segment de lux:
preturi masurate pana la 27.990 lei. Listarea promo are **539 de produse** si 179 de
carduri pe pagina, cu `price` + `oldprice` per card in stare — val ULTERIOR.

### bbcollection.ro — PARCAT, cu masuratorile complete

Nu se implementeaza, dar masuratorile se pastreaza, ca sa nu fie refacute.

* **Zero date structurate, pe 2 din 2 produse**: 0 blocuri ld+json, 0 microdata,
  0 `itemprop=price`, `og:type: "website"` cu titlul global al site-ului, iar
  `dataLayer` (x7) fara nicio cheie de pret. Singura sursa ar fi DOM-ul vizibil.
* Conventia proprie de afisare: *„Pret vechi\* 295 , 00 lei / Pret de vanzare\*
  206 , 50 lei"*, cu `Cod: 35000513` si marimile alaturi.
* **Lichidarile sunt uniforme, nu variabile**: 25 din 27 de carduri la exact
  **-30%** (206,50 = 295 x 0,7; 311,50 = 445 x 0,7).
* **Domeniul-sora `bb-shop.ro`**: listarea trimite catre el de **28 de ori** (home
  x7, PDP x5), cu `utm_medium=referral`, iar maparea e sistematica pe **25 de
  perechi** de produse: codul `pb<ID>` din URL-ul bbcollection devine ID-ul de pe
  bb-shop. Exemplu masurat:
  `bbcollection.ro/bijuterie-inel-…-35000513-pb175484.html`
  -> `bb-shop.ro/bijuterie-…-175484.html`.

De ce PARCAT si nu implementat: un extractor pe DOM ar fi cel mai fragil din tot
catalogul, iar `bb-shop.ro` — daca se dovedeste magazinul real al aceluiasi
comerciant — l-ar face inutil din start.

### bb-shop.ro — pe lista valului de browser

Sondat cu 2 cereri (G2F-7): **home-ul raspunde 200** („B&B SHOP - Magazin Online de
Bijuterii, Ceasuri si Accesorii"), dar **ruta de produs da 403 cu challenge
Cloudflare** (`cf-mitigated: challenge`, corp „Just a moment…"). Ordinea cererilor a
fost controlata deliberat: PDP-ul a fost PRIMA atingere a domeniului si a fost
provocat, iar home-ul a doua, pe acelasi profil, la cateva secunde, si a trecut —
deci nu e rata si nu e profil, e **ruta**.

Prima verificare la valul de browser, in ordinea asta:
1. e acelasi comerciant (acelasi produs pe perechea `pb175484`)?
2. acelasi pret ca pe bbcollection (295,00 -> 206,50 lei)?
3. poarta ld+json `Product`?

Daca DA la toate trei, domeniul de exploatare devine bb-shop.ro (clasa vivre) si
extractorul-pe-DOM al lui bbcollection nu se mai scrie niciodata.

### veloteca.ro — inaccesibil de pe IP-ul curent

403 pe **toate cele trei profiluri**, la home. Corpul e un **403 nginx simplu**
(535 / 535 / 139 octeti), fara niciun marker de challenge, servit prin Cloudflare
(`server: cloudflare`, `cf-ray` prezent). Cloudflare doar transporta; originea
refuza. Un browser NU ajuta la un refuz de origine — deci **nu e Grup 4**.
Re-testarea are sens doar **de pe alt IP**, si se leaga de discutia de proxy.

### Taxonomia 403-urilor din lot (referinta)

Lotul asta a produs, intamplator, cate un exemplar din fiecare fel de 403. Merita
tinute separat, fiindca fiecare cere alt raspuns:

| fel | cum se recunoaste | exemplar | ce rezolva |
|---|---|---|---|
| **la ORIGINE** | 403 al serverului de aplicatie (nginx), corp mic, ZERO markeri de challenge, identic pe toate profilurile | veloteca.ro | alt IP / proxy — **nu** browser, **nu** alt profil |
| **pe RUTA** | home 2xx, ruta de produs 403; prima atingere a domeniului e deja provocata | bb-shop.ro (`cf-mitigated: challenge`) | browser (valul de browser) |
| **pe RATA** | acelasi URL, acelasi profil, trece dupa pauza; apare dupa cateva cereri rapide | action.com (403 la a 4-a cerere/minut, 200 dupa 95s) | interval minim intre cereri |
| **pe PROFIL** | un profil e refuzat, altul trece pe aceeasi ruta | (niciunul in acest lot; vezi ELF-2) | escaladarea amprentei |

Regula practica desprinsa: **ordinea cererilor e un instrument de masura**. Punand
ruta suspecta PRIMA si home-ul dupa, „rata" se exclude din constructie; punand
acelasi URL de doua ori la distanta, se exclude „ruta".

---

## Domenii neintrate

> bipa.ro — VITRINA, nu magazin (masurat in G2D-1): ZERO semnale de cos/checkout in
> tot corpul (niciun `add_to_cart`, `/cart`, `/checkout`, „adauga in cos"), 0 din 54
> de ancore poarta pret — produsele nu sunt linkabile — si toate cele 12 linkuri
> interne sunt institutionale (`/despre-bipa`, `/pliant`, `/sortiment`, `/cariere`,
> `/magazinul-meu` care e STORE LOCATOR, nu „contul meu"). Ofertele stau intr-un
> pliant PDF (`Pliantul%20BIPA_kw32-33.pdf`). Cele 6 preturi afisate sunt blocul
> „BIPA FAVES", identic pe home si `/pliant`, deci componenta partajata. Nuxt,
> `server: istio-envoy`, zero date structurate.
>
> ccc.ro — DOMENIU PARCAT (masurat in G2C-1): `server: Caddy`, `robots: noindex`,
> 6 caractere de text vizibil. Magazinul CCC nu e acolo. ccc.eu, domeniul real, are
> selector de tara randat client-side, deci calea RO nu e obtenabila fara JS.
>
> hervis.ro — redirectioneaza la sportsdirect.ro (Frasers Group), care isi randeaza
> listarile client-side. Candidat pentru valul de browser, nu pentru fluxul HTTP.
>
> badabum.ro — NU exista site: domeniul n-are inregistrare A sau AAAA (masurat in
> G2A-1, si prin resolver public, cu powerup.ro drept control). Zona e la Cloudflare
> si MX-ul e activ pe Microsoft 365, deci domeniul e detinut si folosit pentru email,
> dar nu serveste niciun magazin. De re-verificat DOAR daca cineva confirma ca
> site-ul a fost lansat — nu e o chestiune de anti-bot.
>
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
