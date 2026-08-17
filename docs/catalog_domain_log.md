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
