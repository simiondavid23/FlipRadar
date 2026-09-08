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

> **2026-09-02 (REG-1):** caliroots.com eliminat din registru (nu livreaza in
> Romania). Nu mai exista domenii in SEK.

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

## RATE-1 — interval minim per domeniu, si pe poarta HTTP

Inchide datoria lasata la G2F-6, unde action.com a intrat in registru FARA campul
de interval fiindca mecanismul nu exista pe calea lui.

### Masuratoarea-sursa

Pe action.com (G2F-5, pasa de corectie): a **patra** cerere intr-un minut a primit
403 cu interstitiul Cloudflare „Just a moment...", iar **acelasi URL pe acelasi
profil a trecut cu 200 dupa o pauza de 95s**. Ordinea cererilor a fost aleasa
deliberat ca sa excluda celelalte doua explicatii — nu era ruta (aceeasi ruta
trecuse deja) si nu era profilul (acelasi profil a trecut imediat dupa). Deci
limitarea e pe **RATA**, iar raspunsul corect nu e alta amprenta, ci mai putine
cereri pe minut. Pragul ales, **90s**, sta SUB pauza care a trecut masurat (95s),
nu peste ea.

### Unde sta mecanismul, si de ce acolo

In `_fetch_shop_url_guarded` din `scraper_service` — **poarta unica** prin care
trece tot traficul HTTP catre magazine. La momentul rundei avea sase puncte de
apel, in cinci module: `deal_scanner`, `listing_scanner`, ambele cai din
`product_page_extractor` (fluxul generic si `_fetch_text_guarded` al extractoarelor
custom) si doua apeluri din `scraper_service` insusi. Pus in poarta, mecanismul
acopera si scannerele viitoare fara ca cineva sa-si aminteasca sa-l cableze.

Detaliile care conteaza:
* **Ceas monoton**, nu wall-clock: o ajustare a ceasului de sistem ar putea altfel
  sa para ca au trecut ore, sau sa blocheze o ora.
* **Asteptarea sta SUB lacat.** Daca doua fire ar verifica in paralel, amandoua ar
  vedea „a trecut destul" si ar pleca spate-in-spate catre exact magazinul pe care
  incercam sa-l menajam. Sub lacat se serializeaza. Costul — un al doilea fir catre
  ACELASI domeniu sta blocat — **este** protectia, nu un efect secundar.
* **Stampila la plecare**, nu la intoarcere: masuratoarea numara cereri pe minut,
  iar durata raspunsului nu e sub controlul nostru; altfel ar trebui tinut lacatul
  peste apelul de retea, adica serializate toate fetch-urile.
* **O data pe fetch logic, nu pe hop**: un lant de redirecturi e o singura vizita,
  iar o pauza de 90s intre hop-uri ar rupe fetch-ul in loc sa-l menajeze.
* **Cost zero pe restul catalogului**: harta se deriva o data la import (ca
  `_IMPERSONATE_OVERRIDES`), iar domeniile care nu-s in ea ies inainte de lacat.
* Potrivire **suffix-safe**, identica cu `_impersonate_for` si cu allow-list-ul
  C-14: `shop.action.com` mosteneste intervalul, `evil-action.com.attacker.net` nu.

### Contractul campului, actualizat

`min_fetch_interval_s` nu mai e „doar pe method=browser". E valabil pe ORICE
metoda, dar cele doua cai il consuma DIFERIT, si asta e deliberat:

| cale | sub prag | de ce |
|---|---|---|
| BROWSER (`browser_fetch`) | fetch-ul e **REFUZAT**, refresh-ul pastreaza pretul anterior | lansarea unui browser e prea scumpa ca sa astepti cu el pornit |
| HTTP (poarta, RATE-1) | cererea **ASTEAPTA** diferenta, apoi pleaca | o cerere HTTP e ieftina; refuzul ar pierde inutil o extractie |

### Garda din suita, rescrisa in ACELASI commit

La BR-1 campul fusese inchis pe `method == "browser"` fiindca acolo era singurul
consumator, iar pe alte metode ar fi fost un **camp mort** — prezenta lui ar fi
sugerat fals o protectie inexistenta. Argumentul acela era despre CONSUM, nu despre
semantica: „secunde minime intre cereri" are inteles pe orice cale. La RATE-1
consumatorul HTTP exista, deci restrictia si-a pierdut temeiul si a cazut — dar
**odata cu** aparitia mecanismului, niciodata inaintea lui. `headed` ramane
browser-only: el chiar n-are inteles fara browser.

Regula care se desprinde, si merita tinuta: *o garda care interzice un camp mort se
ridica in acelasi commit cu codul care il face viu — nu mai devreme, ca sa nu apara
campuri decorative, si nu mai tarziu, ca sa nu fie nevoie de un commit care „repara"
suita.*

### Verificarea live, si ce a scos la iveala

Doua extractii consecutive pe action.com, prin calea de productie, fara ca scriptul
sa doarma explicit:

```
[t+  0.0s] action.com /p/2574593/  -> 3.98 RON, jsonld     (extractia a durat 0.3s)
[t+  0.3s] action.com /p/2567526/  -> 11.95 RON, jsonld    (extractia a durat 180.0s)
[t+180.3s] control pe domeniu FARA interval -> pleaca imediat (0.4s, status 200)
```

Mecanismul functioneaza — a doua cerere n-a plecat inainte de prag, iar domeniile
fara camp nu asteapta deloc. Dar cifra de **180s**, nu 90, spune ceva in plus:
`extract_product` are bucla de retry, si **fiecare incercare trece prin poarta**,
deci a consumat DOUA intervale. Adica prima incercare (la t≈90s) n-a dat o pagina
parsabila, iar a doua (la t≈180s) a dat. Bucla nu jurnalizeaza statusul per
incercare, deci cauza exacta n-a fost capturata: ori un challenge la 90s, ori o
eroare tranzitorie.

Doua consecinte practice:
1. **Un retry costa un interval intreg.** E corect ca protectie (retry-ul e tot o
   cerere catre acelasi magazin), dar inseamna ca o extractie nereusita din prima
   poate dura 3 x interval inainte sa renunte.
2. **90s ar putea fi sub pragul real.** Singura recuperare masurata (G2F-5) a fost
   la **95s**, iar valoarea a fost aleasa deliberat SUB ea. Directia e discutabila:
   un interval de protectie ar trebui sa fie la sau peste timpul de recuperare
   observat, nu sub. Verificarea live e compatibila cu ipoteza „90 nu ajunge".
   Valoarea se urca din registru, fara cod — o linie.

### Efectul la deploy

Verificat pe registrul de dinaintea rundei: singurul domeniu cu camp era
`sephora.ro` (browser, 180s), deci **niciun domeniu HTTP nu-l avea**. Comportamentul
intregului catalog ramane identic; singura schimbare e action.com, care de acum
asteapta cel putin 90s intre doua cereri.

---

## G4-V0/G4-V0b — valul zero de browser: 8 sondate, 3 intrate

Prima sonda care a masurat prin BROWSER (patchright + Chrome real pe configuratia de
productie BR-1), nu prin curl_cffi. Pariul: mai multe „tinte grele" ale Grupului 4
sunt de fapt intrari banale, ca sephora.ro si hhv.de.

**Rezultatul central: ZERO challenge INTERACTIV pe toate cele opt.** 403-urile pe
care le vedea poarta HTTP nu erau ziduri anti-bot care cer verificare umana — erau
doar „lipseste un browser real". Cloudflare managed challenge
(`cf-mitigated: challenge`) trece TACIT in Chrome real headed, fara nicio
interactiune. Nicio captura de blocaj n-a trebuit facuta.

| domeniu | verdict | metoda |
|---|---|---|
| bb-shop.ro | **intrat** | browser (HTTP da 403) |
| conrad.com | **intrat** | browser (HTTP da 403) |
| forit.ro | **intrat** | **jsonld** — browserul s-a dovedit INUTIL |
| decathlon.ro | viabil, dar amanat | cere aplatizarea `offers` imbricate |
| ccc.eu, reichelt.de, sportsdirect.ro, fressnapf.ro | nedeterminate | val 2 |

### Duratele masurate — calibrarea asteptarilor de productie

Bimodale, si diferenta conteaza la planificare:

* **succes: 1,78–6,71s** (mediana 3,9s) — continutul e gata practic imediat
* **esec: 27,2–39,9s** — dominat de plafonul de poll (20s) PLUS cautarea de selectori
  de refuz cookie-uri (7 selectori x 2s timeout fiecare)
* `goto` e uniform rapid, 1,35–4,56s, indiferent de verdict

Adica: pe un domeniu care merge, harness-ul costa secunde; pe unul care nu merge,
costa jumatate de minut. Daca un val viitor loveste multe tinte moarte, scurtarea
plafonului sau a listei de selectori taie ~2/3 din timp.

### bb-shop.ro — `method: browser`, categoria `bijuterii-ceasuri` (FACUT)

Raspunde la cele trei intrebari puse la G2F-8, in ordine, cu **DA la toate trei**:

1. **acelasi comerciant?** DA — codul `35000513` (29 ocurente in PDP-ul randat) si
   id-ul intern `175484` (34 ocurente) apar pe ambele; canonical-ul bbcollection
   `...-35000513-pb175484.html` corespunde lui bb-shop `...-175484.html`.
2. **acelasi pret?** DA — `295,00` -> `206,50` lei, aceeasi pereche, acelasi -30%.
3. **ld+json `Product`?** DA — Offer [price `"206.5"`, priceCurrency RON,
   availability `OnlineOnly`, itemCondition NewCondition]. Genericul extrage FARA
   override: `206.5 RON`, `in_stock=True`, `method: jsonld`.

`OnlineOnly` NU e `InStock`; genericul il citeste totusi ca disponibil, si e corect —
inseamna „doar online", nu „indisponibil".

Pentru axa D, pretul vechi are **doua** surse masinabile, desi afisajul e ostil
(fragmentat in markup ca `295 , 00 lei`, NEtaiat semantic — zero `<del>/<s>/<strike>`
— si cu Omnibus NEMARCAT, tiparul elefant.ro):

* selectorul `.old .a-price-whole` + `.a-price-fraction` (nume de clase in stil Amazon)
* starea `var date_js = {"arti":175484,"art":"35000513","pret_inmag":"295.00",...}`

CAPCANA la verificare: `295` da fals pozitiv in datele de path SVG ale paginii. Si
atentie, `295,00`/`206,50` NU apar literal in dump-urile bbcollection — un grep simplu
ar concluziona gresit „pereche gresita".

### bbcollection.ro — PENSIONAT OFICIAL

Criteriul scris chiar aici la G2F-8 („Daca DA la toate trei, domeniul de exploatare
devine bb-shop.ro si extractorul-pe-DOM al lui bbcollection nu se mai scrie
niciodata") e **indeplinit**. bbcollection ramane PARCAT, iar **extractorul-pe-DOM nu
se mai implementeaza niciodata** — bb-shop livreaza acelasi inventar, la acelasi pret,
prin ld+json curat.

Motivul masurat ramane ca referinta, ca sa nu fie re-derivat: bbcollection are zero
date structurate pe 2 din 2 produse, iar pretul exista doar in DOM, spart in noduri
separate. Ar fi fost cel mai fragil extractor din tot catalogul.

### conrad.com — `method: browser`, categoria `electronice` (FACUT)

Grup 4 la G2B-1b: 403 `cf-mitigated: challenge` si pe home, si pe listare, pe profilul
de productie. In Chrome real: **200 in 4,48s**, DOM randat de 1.156.723 octeti cu
ld+json `Product`.

**Doua capcane, amandoua importante:**

1. Pretul NU e in `offers.price` — acela e `null`. Sta in
   `offers.priceSpecification.price` = `36.97` / EUR. Genericul il citeste corect
   (`method: jsonld`, fara override), dar o analiza care se uita doar la `offers.price`
   ar conchide gresit „fara pret public".
2. **`"valueAddedTaxIncluded": false`** — pretul e **NET, fara TVA**. O comparatie
   directa cu preturi brute romanesti subestimeaza sistematic. Orice calcul de marja
   pe conrad trebuie sa adauge TVA intai.

`hasVariant` exista dar e GOL (n=0), deci nu e sursa de variante. Produsul poarta
sku/gtin13/mpn (`1934286` / `5099206080263` / `910-005470`), utile la incrucisare.

Listarea `/en/promotions/sale.html` se randeaza (828.541 octeti, preturi EUR vizibile)
dar are **ZERO ld+json** — materie pentru axa D, val ULTERIOR.

**LIVRAREA IN RO nu s-a masurat.** Intrarea e `delivery: "unconfirmed"` — prima din
catalog care nu e `ro_confirmed`/`ro_storefront`. Verdictul de checkout e al lui David
si poate urca campul cu o linie.

### forit.ro — `method: jsonld`, categoria `electronice` (FACUT)

**A intrat in valul de browser, dar NU e intrare de browser.** Sonda G4-V0 l-a masurat
prin browser (1,78s, cea mai rapida incarcare din val) si a iesit viabil — dar
dump-urile HTTP ale lui WL-1, pe profilul de productie `chrome131`, dau **200 pe
AMBELE PDP-uri**, iar genericul extrage din ele `507,30 RON` si `644,99 RON`,
`method: jsonld`, fara override.

Harness-ul de browser costa un Chromium per pagina si, prin regula lui proprie, se
pune doar unde sonda a dovedit ca **nu exista alta cale**. Aici exista. Un
`method: "browser"` pe forit ar fi fost risipa pura, mai ales pe tinta Raspberry Pi.

Lectia generala: „viabil prin browser" NU inseamna „are nevoie de browser". Verdictul
de metoda se da pe cea mai IEFTINA cale care functioneaza, nu pe calea pe care s-a
nimerit sa fie masurat domeniul.

Valoarea declarata a domeniului e sectiunea de **RESIGILATE** (`/resigilate/`,
masurata la WL-1). ATENTIE la semantica starii: `itemCondition` e `NewCondition`
**chiar si pe produsele desigilate** — starea reala apare doar in titlu si in sku
(`AT-150-RSO- desigilata`). Pe axa L se ignora (decizia resigilate), pe axa D se
consemneaza.

Componente partajate de ignorat in orice citire pe text: `21.99 Lei` (Curier Romania)
si `300 lei` (pragul de livrare gratuita) — ld+json le ocoleste.

### decathlon.ro — viabil, dar AMANAT (o reparatie mica il aduce)

PDP-ul randat poarta ld+json `Product` cu **18 oferte, toate cu pret**
(`159.99` / RON / `InStock`). Genericul pica totusi cu „Pret lipsa sau invalid (None)",
si motivul e precis: **`offers` e o lista de DOUA liste** a cate 9 Offer-uri, iar
`_collect_jsonld` nu aplatizeaza liste imbricate.

Nu cere extractor custom, cere aplatizare — si e o reparatie GENERALA, nu specifica
Decathlon. A fost lasata in afara valului fiindca atinge `product_page_extractor.py`,
adica extractia partajata de tot catalogul; merita rundă proprie, cu regresia ei.

Home-ul da 403 pe HTTP si 200 in 2,53s prin browser, deci accesul nu e problema.

### GOTCHA metodologic — helperul de sonda si extractorul se contrazic in AMBELE sensuri

La decathlon, helperul de analiza `_oferte_integral` raporteaza 18 oferte cu pret iar
extractorul da `None`. La conrad, invers: helperul raporteaza **0** oferte cu pret
(nu vede `priceSpecification`) iar extractorul extrage corect `36.97`.

Concluzia de metoda: **autoritatea e `parse_product_html`, nu semnalele sondei.** De
aceea sonda il ruleaza explicit ca verdict, in loc sa se bazeze pe numaratori.

### Cele patru nedeterminate — val 2, si de ce

Toate randeaza `200`. N-au fost ratate de site, ci de harness: euristica de recoltare
de PDP („cardul cu path-ul cel mai adanc") a ales categorii, iar la sportsdirect chiar
butonul de checkout, care a navigat spre pagina de login.

* **ccc.eu** — poarta de tara FUNCTIONEAZA: `https://ccc.eu/` -> `https://ccc.eu/ro/ro/`
  printr-un singur click, cu preturi RON vizibile (`118,99 lei`, `169,99 lei`). Doar
  PDP-ul lipseste.
* **reichelt.de** — poarta de sesiune trece NATURAL in browser: 200, ld+json
  `[Organization, WebSite, BreadcrumbList, WebPage]`. Dar `/magazin/` e **revista**, nu
  catalogul. (Nota: `lei` detectat in text e fals pozitiv — apare in cuvinte germane.)
* **sportsdirect.ro** — home randeaza 436.781 octeti, dar ld+json e doar `WebSite` si
  singurul pret vizibil e `0,00 €`, adica **cosul gol**.
* **fressnapf.ro** — hidratarea ADAUGA `ItemList` (sonda HTTP vedea doar schelet), dar
  `itemListElement` sunt **categorii**, nu produse:
  `{"@type":"ListItem","url":"https://www.fressnapf.ro/Caine","name":"Câini"}`. `/sct/0/`
  e indexul de categorii.

Ce le trebuie tuturor patru: URL-uri de PDP REALE, plus o recoltare care exclude
explicit `login`/`checkout`/`cart`. ~8 incarcari, val 2.

### Post-scriptum la post-mortem-ul WL-2

FAZA 0 a rundei G4-V0b (diagnosticul WL-2r) s-a inchis pe ramura **(c) — nimic
nicaieri**, dar cu diagnosticul CORECTAT: nu e o a doua pierdere si nu e un defect de
flux. **WL-2r n-a fost niciodata implementat** — runda s-a incheiat cu STOP pe clauza
de coerenta, fiindca dump-urile `dumps_wl/` o contraziceau: istyle.ro are verdictul
`"custom pe stare structurata"` (zero `Product` ld+json pe 4 din 4 pagini),
quickmobile.ro a dat 503 pe toate profilele si skinmobile.ro nu se rezolva in DNS
(`Non-existent domain`, re-verificat).

Ipoteza „ceva sterge modificarile intre sesiuni" a fost testata si INFIRMATA: in
aceeasi sesiune, artefactele sondei G4-V0 (40 de fisiere, 7,4MB) au supravietuit
intacte, un push a tinut, iar modificarile FB din arbore au devenit commit normal.

Poarta „WL-2r pe remote" a fost ridicata EXPLICIT de David, ca sa nu blocheze o
lucrare independenta. Regula ramane valabila, dar cu o completare: daca schita unei
runde e sursa de adevar pentru runda urmatoare, ea trebuie sa ajunga intr-un artefact
COMIS (`docs/`), nu doar in raportul din chat — altfel „re-implementarea identica" n-are
pe ce se sprijini.

---

## WL-1/WL-4/WL-3 — watchlist-ul conditionat: 6 sondate, 1 intrat

Watchlist-ul a fost sondat la WL-1 (2026-08-20) si implementat abia la WL-3
(2026-08-21), dupa o sonda CORECTIVA (WL-4) care a rasturnat unul dintre verdictele
initiale. Traseul merita consemnat, fiindca lectia e despre metoda.

| domeniu | verdict | metoda |
|---|---|---|
| istyle.ro | **intrat** | jsonld |
| forit.ro | **intrat** (la G4-V0b) | jsonld |
| quickmobile.ro | **NEINTRAT** — 503 persistent | — |
| skinmobile.ro | **NEINTRAT** — domeniul nu exista | — |
| sneakerindustry.ro | **INCHIS** la 2026-08-20 | — |
| toychamp.nl | **ELIMINAT** | — |

### Lectia WL-4: un verdict de sonda descrie PAGINILE masurate, nu magazinul

WL-1 a dat lui istyle.ro verdictul „custom pe stare structurata". Pe baza lui, trei
runde succesive (WL-2, WL-2r, WL-3 in forma initiala) au incercat sa scrie
`method: "jsonld"` si au fost oprite de clauza de coerenta — corect, fiindca
dump-urile chiar contraziceau promptul.

Verdictul era insa GRESIT, si abia sonda corectiva l-a aratat: **WL-1 nu masurase
niciodata un PDP istyle**. Euristica ei de carduri alesese trei pagini `/pages/*` —
„Back to School 2026", „Modele Mac", „Modele Apple Watch" — care pe Shopify sunt
pagini CMS si n-au ld+json de produs. In dump-urile ei existau, netinse, **52 de
linkuri `/products/` distincte**.

Doua reguli de retinut:

* **„Masurarea gresita e prima ipoteza" se aplica si verdictelor VECHI**, nu doar
  masuratorii curente. Un verdict din banca nu e mai adevarat fiindca e scris.
* Clauza de coerenta si-a facut treaba de trei ori: a oprit scrierea unei afirmatii
  pe care dovada n-o sustinea. Solutia n-a fost sa fie slabita, ci sa fie masurata
  cauza. Cand promptul si dump-urile se bat cap in cap, uneori promptul are dreptate
  — dar asta se DEMONSTREAZA cu o masuratoare noua, nu se presupune.

### istyle.ro — `method: jsonld`, categoria `electronice` (FACUT)

PDP-urile reale sunt `/products/<handle>` si poarta `Product` + `ProductGroup`;
genericul extrage **fara override**, masurat 2/2: resigilat 4.699,99 RON, normal
4.999,99 RON, ambele `priceCurrency: RON`.

Magazin Shopify, dar intrat pe **ld+json, NU pe fluxul `shopify`**: enumerarea
(`/products.json`, `/cart.js`) nu s-a masurat, deci nu se afirma.

`Offer` NU are `availability` — cheile masurate sunt `[@type, itemCondition, price,
priceCurrency, priceValidUntil, shippingDetails, url]` — deci `in_stock` iese `None`,
si e ONEST (acelasi tipar ca biciclop.eu).

**Sectiunea de RESIGILATE, si de ce WL-1 n-a gasit-o.** Nota ei spunea „RESIGILATE:
niciun link in home — cad pe reduceri". Corect ca observatie despre `<a href>`,
gresit ca verdict: produsele resigilate stau in **STAREA Shopify** a home-ului, ca
handle-uri `resigilat-<slug>`, unele purtand chiar starea in handle
(`stare-bun-63-23feb`, `stare-perfect-66-23feb`). PDP-ul de resigilat e deci adresabil
ca `/products/resigilat-...`, iar numele lui prefixeaza „Resigilat: ".

**Semantica starii:** `itemCondition` e `NewCondition` CHIAR SI pe resigilate — al
treilea magazin din catalog cu acest tipar, dupa forit.ro si eMAG. Concluzia se
generalizeaza: **`itemCondition` nu e un semnal utilizabil pentru resigilate in
magazinele romanesti.** Starea reala se citeste din nume/handle. Pe axa L se ignora
(decizia resigilate), pe axa D se consemneaza.

Fara Omnibus si fara taiat semantic (zero `<del>/<s>/<strike>`). Capcane la orice
citire pe text: pretul apare si concatenat cu gtin-ul (`195950609745 4 699,99 lei`),
iar `500 lei` / `200 lei` sunt praguri de livrare — ld+json le ocoleste pe toate.

### quickmobile.ro — NEINTRAT, 503 persistent

Home-ul da **503 pe toate profilele** la WL-1 si **503 din nou** la re-masuratoarea
WL-4, o zi mai tarziu. Nu e tranzitoriu si nu e challenge (`challenge=None`, deci nu
e nici anti-bot). Domeniul rezolva in DNS (`138.201.252.227`), deci exista — dar
serverul nu serveste. De re-verificat DOAR daca cineva confirma ca magazinul a
revenit.

### skinmobile.ro — NEINTRAT, domeniul nu exista

`Non-existent domain`, verificat de doua ori (apex si `www`), la o zi distanta.
Nu e o chestiune de anti-bot si nu e re-verificabil util. **De scos din watchlist.**

### sneakerindustry.ro — INCHIS la 2026-08-20

`products.json` da 403 pe toate cele trei profiluri ale lantului. Enumerarea Shopify
ramane **inchisa**; domeniul nu intra pe fluxul Grupului 1. Se re-verifica doar la o
runda de watchlist viitoare, nu ad-hoc.

### toychamp.nl — ELIMINAT

403 pe toate profilele, cu marker `enable javascript and cookies`. Tehnicul ar fi
masurabil printr-un val de browser, dar **intrarea era oricum conditionata de
verdictul de livrare RO la checkout, care e al lui David** — si nu s-a dat. Iese din
watchlist; se re-deschide doar daca David confirma livrarea.

### Post-scriptum la post-mortem-ul WL-2

Lucrarea watchlist-ului a fost implementata efectiv abia in **WL-3** (2026-08-21),
dupa doua runde raportate dar necomise (WL-2) si o runda oprita pe dovezi (WL-2r).
Cauza reala n-a fost pierderea de fisiere — verificat si infirmat la G4-V0b — ci
faptul ca **lucrarea nu putea fi facuta corect pe masuratoarea existenta**. Trei
opriri succesive au fost simptomul, nu boala; boala a fost un PDP nemasurat, si s-a
vindecat cu trei cereri.

---

## G4-V2/G4-V2b — reziduul Valului 2: 6 sondate, 4 intrate

Ultima runda mare de registru a axei L. Sase tinte cu anti-bot cunoscut sau prezumat,
masurate in doua trepte (HTTP intai, browser doar pe goluri — designul EMAG-1).

| domeniu | verdict | metoda |
|---|---|---|
| snipes.com | **intrat** | jsonld (HTTP, 200 din prima) |
| lego.com | **intrat** | jsonld (HTTP) |
| solebox.com | **intrat** | browser |
| cardmarket.com | **intrat** | custom, `cardmarket_oferte` (peste browser) |
| watchshop.ro | **NEINTRAT** — challenge nerezolvat nici in browser | Val 3 |
| footlocker.ro | **NEINTRAT** — randare pe client, PDP nemasurat | Val 3 |

### Perechea solebox/snipes — acelasi magazin tehnic, anti-bot DIFERIT

Identitatea de platforma e dovedita direct, nu dedusa din asemanare:

* pagina **solebox isi incarca asset-urile de pe `api.snipes.com` si
  `asset.snipes.com`** — infrastructura e literalmente a lui snipes
* prefixul distinctiv de clase **`hydra-`** apare pe amandoua (plus `img-`,
  `product-`, `icon-`, `sr-`, `no-`)
* tiparul de PDP e identic: `/<locale>/p/<slug>`
* amandoua servesc prin `static.cloudflareinsights.com`

**Si totusi intra pe metode diferite**, si asta e lectia: `snipes.com` raspunde 200
la PRIMA cerere pe profilul de productie, in timp ce `solebox.com` da 403 cu „just a
moment" pe TOATE cele trei profiluri ale lantului si cere browser (unde challenge-ul
se rezolva tacit in 5,19s, 1,07MB, 108 carduri cu pret).

**Identitatea de platforma NU se transfera la stratul de acces.** Anti-botul e
configurat per domeniu. Consecinta practica: acelasi magazin costa o cerere curl pe un
domeniu si un Chromium pe celalalt. Daca solebox se relaxeaza vreodata la nivelul lui
snipes, poate cobori ieftin pe `jsonld` — structura de date e deja aceeasi.

### lego.com — prins la limita: „viabil prin browser" nu inseamna „are nevoie de browser"

Sonda G4-V2 l-a masurat prin browser si iesise viabil acolo. Motivul era insa
accidental: plafonul HTTP se epuizase pe escaladarile irosite la solebox si watchshop
(cate 3 cereri fiecare, toate 403), asa ca PDP-ul lego n-a mai apucat o cerere curl.

Re-masurat explicit inainte de intrare: **200 pe profilul de productie, fara
challenge**, ld+json `Product`, `899,99 RON`, fara override. Deci `jsonld`.

E a doua oara cand tiparul asta apare, dupa forit.ro (G4-V0b). Regula, acum
generalizata: **verdictul de metoda se da pe cea mai IEFTINA cale care functioneaza,
nu pe calea pe care s-a nimerit sa fie masurat domeniul.** Cand o tinta iese viabila
prin browser, se verifica INTOTDEAUNA si HTTP-ul inainte de a o pune pe harness.

### cardmarket.com — marketplace, si o decizie de semantica

Nu e magazin: o carte n-are „un pret", are un tabel de oferte de la vanzatori
diferiti. Masurat pe un PDP: **50 de randuri `.article-row`** (`id="articleRow<N>"`),
fiecare cu pretul in `.price-container` in format `2,98 €`, intre **2,98 € si 4,50 €**.

**Decizia lui David: cel mai mic pret public.** E a patra aplicare a conventiei
minimului din catalog — dupa `lowPrice`, variantele G2F-4 si listele de oferte
FASHION-1 — si singura care face „reducere" sa insemne ceva, fiindca e analogul
pretului de raft.

Implementarea ia `min()`, **nu primul rand**, desi pagina masurata venea deja sortata
crescator: minimul nu trebuie sa depinda de o sortare pe care magazinul o poate
schimba oricand. Garda de test inverseaza randurile fixture-ului si cere acelasi
rezultat.

**Zero date structurate** — nici ld+json, nici microdata, nici `itemprop=price` — deci
genericul ridica `no_product_data` (pinuit de test) si nu exista rezerva pe el.

**ACCESUL: challenge pe RUTA, nu pe profil.** `/en/Magic` trece pe un profil al
lantului (masurat la G3-1), dar `/Products/*` da 403 pe TOATE profilurile, inclusiv pe
acela. In Chrome real, ruta de produs trece si serveste 284KB de continut real.
Intrarea de registru e `method: "browser"` desi extractorul custom are prioritate in
`extract_product`: campul nu alege calea aici, dar E lista de destinatii pe care
harness-ul are voie sa navigheze, si fara el `_verifica_destinatia` refuza URL-ul.

**De consemnat pentru axa D:** livrarea e **per vanzator** (fiecare rand e alt
vanzator, cu costul lui), deci „pretul final" nu e derivabil din pagina de produs.
Orice comparatie serioasa pe cardmarket trebuie sa trateze asta.

### watchshop.ro — Val 3, si un bug de productie gasit pe drum

Challenge Cloudflare **nerezolvat nici in browser**: dupa 36,5s de poll, pagina ramane
27.584 octeti, **2 ancore**, 351 de caractere de text vizibil, cu titlul **„Doar un
moment..."**. Lichidarile 60-75% (valoarea declarata a domeniului) raman NEMASURATE —
n-am ajuns niciodata la continut.

Pe drum s-a gasit insa un bug real in productie: **`browser_fetch._MARKERE_BLOCARE`
e integral EN/DE** (`"just a moment"`, `"checking your browser"`, `"attention
required"`, `"access denied"`, `"zugriff verweigert"`, `"captcha"`, `"verifying you
are human"`). Challenge-ul ROMANESC „Doar un moment" NU e prins, deci
`_detecteaza_blocare` nu-l vede: harness-ul raporteaza `RANDAT_NEVALIDAT` in loc de
`BrowserFetchBlocked`, dupa ce a ars plafonul intreg de poll. Pe orice magazin RO cu
challenge, productia clasifica gresit motivul si pierde 20s. Fixul e o linie, dar e in
afara whitelist-ului acestei runde — runda proprie.

### footlocker.ro — Val 3, randare pe client

Home-ul raspunde **200 pe HTTP** dar poarta **ZERO linkuri de produs**; randat, da
167.549 octeti cu 8 carduri, `ld=[]` si un singur pret vizibil (`199.99 LEI`). Nu e
blocat — pur si simplu nu serveste produse server-side. PDP-ul n-a fost masurat, deci
domeniul ramane NEDETERMINAT, nu „neviabil": ~2 incarcari ar inchide intrebarea.

### Durate de browser masurate (calibrare)

Aceeasi bimodalitate ca la G4-V0, confirmata pe alt lot: **succes 1,79-5,19s**
(cardmarket listare 1,79s; lego PDP 4,93s; solebox home 5,19s), **esec 35,8-37,2s**
(cardmarket PDP pe validator de produs 35,82s; watchshop 36,54s; footlocker 37,16s).
Esecul e dominat de plafonul de poll (20s) plus cautarea de selectori de refuz
cookie-uri (7 selectori x 2s).

---

## G4-V3/G4-V3b — ULTIMA rundă a axei L, și capitolul de închidere

### Cele patru ținte finale

| domeniu | verdict | metoda |
|---|---|---|
| notebooksbilliger.de | **intrat** | browser |
| footlocker.ro | **intrat** | **jsonld** — browserul s-a dovedit inutil |
| pccomponentes.com | **BLOCAT FINAL** | Cloudflare Turnstile |
| watchshop.ro | **BLOCAT FINAL** | Cloudflare Turnstile |

**Doua verdicte vechi s-au dovedit masuratori gresite**, si amandoua au deblocat cate
o intrare:

* **notebooksbilliger.de** era in banca drept „Akamai, blocat". De fapt daduse **404**,
  pe **UN singur profil**, fara escaladare (`escaladare_indice: 0`): regula `expected`
  trateaza 404 ca terminal, nu ca challenge de escaladat. Corpul era o pagina de eroare
  Akamai reala. In Chrome real trece imediat.
* **footlocker.ro** parea gol: home-ul n-are **niciun** link de produs, nici macar dupa
  hidratare (241 de ancore, zero produse). Produsele sunt pe CATEGORII
  (`/ro/barbati/pantofi/`, 28 de carduri). „Home-ul nu poarta produse" NU inseamna
  „situl nu poarta produse".

Si **a treia aplicare a regulii de metoda**, dupa forit.ro si lego.com: footlocker a
intrat prin valul de browser dar a fost verificat pe HTTP inainte de scriere — 200 pe
profilul de productie, aceeasi valoare — deci `jsonld`. notebooksbilliger a fost
verificat la fel si a ramas pe browser: HTTP-ul da marker de challenge
`sec-if-cpt-container`, apoi 404, apoi 200 dar **fara nicio structura de produs**.
Regula se verifica in ambele sensuri, si de-aia merita rulata de fiecare data.

### Zidul final: Cloudflare Turnstile

pccomponentes.com (`Just a moment...`, „Performing security verification") si
watchshop.ro (`Doar un moment...`, „Efectuarea verificării de securitate") servesc
amandoua acelasi shell: ~27KB, **2 ancore**, semnaturile `turnstile` + `cf-chl` +
`challenge-platform`, dupa ~36,5s de asteptare. E **verificare interactiva**.

watchshop a primit doua masuratori, la zile diferite, cu rezultat identic la ~150 de
octeti — un verdict final pe n=1 ar fi fost slab.

Formula de inchidere, pentru amandoua: **inaccesibile fara instrumente la care s-a
renuntat** (proxy platit, Scrapling, rotatie de modem — decise definitiv). Nu e esec,
e o granita cunoscuta.

---

# CAPITOLUL DE INCHIDERE A AXEI L

## 1. Bilantul numeric

**De la 65 de domenii (handover-ul de start) la 93.** Toate cu `status: "validated"` —
registrul nu poarta intrari nevalidate.

Valurile, cu datele din istoricul git al registrului:

| val | data | ce a adus |
|---|---|---|
| LOT2 / LOT3 / LOT4 / BR-1 / BR-1b | 2026-08-13 | 6 straine, 6 fashion, 4 beauty, **harness-ul de browser** + 4 domenii Grup 4 |
| LOT5 | 2026-08-14 | treapta laxa la ld+json, 5 domenii jucarii |
| SHOP-3 | 2026-08-15 | migrare pe `shopify` cu moneda masurata |
| DEAL-2 | 2026-08-16 | scanner de listari pe 4 domenii pilot (samburele axei D) |
| VTX-2 / ELF-2 / G1-2 | 2026-08-17 | f64 (+ design API VTEX), extractor Intershop, sivasdescalzo + tezyo |
| G2A-2 / G2B-2 / G2C-2 / G2F-2 / G2F-4 | 2026-08-18 | powerup, cyberport, sportvision+sizeer, intersport+2, zooplus |
| G2F-6 | 2026-08-19 | hornbach, bonami, action, vivre |
| G2F-8 / RATE-1 | 2026-08-20 | biciclop + cellini; interval minim per domeniu |
| G4-V0b / WL-3 / G4-V2b / **G4-V3b** | 2026-08-21 | valul de browser, istyle, valul 2, **inchiderea** |

## 2. Inventarul metodelor

| metoda | n | ce inseamna |
|---|---|---|
| `jsonld` | 60 | fluxul generic, ld+json — coloana vertebrala |
| `shopify` | 14 | endpoint-ul Ajax, moneda din registru |
| `browser` | 9 | Grupul 4: accesul cere Chrome real |
| `custom` | 5 | cod bespoke per magazin |
| `microdata` | 4 | fara ld+json, dar cu microdata |
| `og` | 1 | ultima rezerva |

Doar **3 override-uri** de selector si **2 domenii** cu interval minim
(`action.com` 90s, `sephora.ro` 180s) — semn ca fluxul generic acopera aproape tot.

Domeniile de browser: bb-shop.ro, cardmarket.com, conrad.com, hhv.de, makeup.ro,
notebooksbilliger.de, orange.ro, sephora.ro, solebox.com.

**Cele SASE extractoare custom si motivul MASURAT al fiecaruia** (sase, nu cinci:
cardmarket e `method: "browser"` cu extractor dedicat, deci nu apare in numaratoarea
de mai sus):

| extractor | motivul masurat |
|---|---|
| `asos.com` | pagina nu poarta datele; extractor bespoke de la DISCOVERY-2 |
| `elefant.ro` | Intershop; stoc onest necunoscut |
| `powerup.ro` | OpenCart cu tema proprie, SSR fara NICIO data structurata |
| `intersport.ro` | zero ld+json Product, `itemprop=price` orfan, pret in `data-current-price` |
| `cellini.ro` | datele exista EXCLUSIV in starea paginii; 48 de obiecte cu `price`, identificarea pe cheia `url` |
| `cardmarket.com` | marketplace: 50 de oferte per pagina, zero date structurate, pretul = minimul public |

## 3. Registrul absentelor — fiecare o decizie, nu o uitare

**Eliminate de David** (livrare sau inexistenta): backmarket, alza, otrium,
**toychamp.nl** (403 pe toate profilurile, dar intrarea era oricum conditionata de
verdictul de livrare RO la checkout, care nu s-a dat), **hervis.ro** (redirectioneaza
la sportsdirect.ro — nu e domeniu propriu), **badabum.ro** (domeniul n-are inregistrare
A/AAAA: zona la Cloudflare si MX activ, deci detinut pentru email, dar nu serveste
niciun magazin), **ccc.ro** (domeniu PARCAT, nu magazin).

**Vitrine fara shop:** **bipa.ro** — zero semnale de cos in tot corpul, 0 din 54 de
ancore poarta pret, ofertele intr-un pliant PDF. Intrebarea simetrica s-a inchis
INVERS la **action.com**, care parea la fel dar s-a dovedit magazin real si a intrat.

**Neintrabile masurate:** **quickmobile.ro** — 503 pe toate profilurile la WL-1 si 503
din nou la re-masuratoarea WL-4, o zi mai tarziu; nu e tranzitoriu si nu e challenge
(`challenge=None`). **skinmobile.ro** — `Non-existent domain`, verificat de doua ori
(apex si `www`), la o zi distanta.

**Parcate conditionat:**
* **chrono24** — decizia lui David.
* **qogita.com** — CONT_OBLIGATORIU: „Sign up to unlock all offers", `Offer` fara `price`.
* **bbcollection.ro** — **PENSIONAT** in favoarea bb-shop.ro, care poarta acelasi
  inventar la acelasi pret prin ld+json curat. Extractorul-pe-DOM nu se mai scrie
  niciodata; motivul masurat ramane ca referinta.
* **reichelt.de** — ATENTIE, nu e „poarta de sesiune neclarificata": la G4-V0 browserul
  A TRECUT (200, 144.307 octeti, ld+json `[Organization, WebSite, BreadcrumbList,
  WebPage]`). Domeniul e **NEMASURAT pe o pagina de produs**, fiindca sonda a incarcat
  `/magazin/`, care e **revista**, nu catalogul. Vina harness-ului, nu a sitului.
* **ccc.eu** — la fel: poarta de tara **FUNCTIONEAZA** (`https://ccc.eu/` ->
  `https://ccc.eu/ro/ro/` printr-un singur click, 1.112.840 octeti, preturi RON
  vizibile: `118,99 lei`, `169,99 lei`). Ce s-a incarcat ca „PDP" era o categorie
  (`/c/promo/bestsellers`) — euristica de recoltare a gresit. Si el e NEMASURAT pe PDP.
* **sportsdirect.ro**, **fressnapf.ro** — idem, nemasurate pe PDP din aceeasi cauza
  (recoltarea a ales home/index de categorii). Toate patru cer URL-uri de PDP reale si
  o recoltare care exclude `login`/`checkout`/`cart`.
* **decathlon.ro** — VIABIL, amanat tehnic: ld+json `Product` cu 18 oferte cotate, dar
  `offers` e **lista de DOUA liste**, iar `_collect_jsonld` nu aplatizeaza liste
  imbricate. Reparatie generala, nu specifica Decathlon.

**In repaus:** **veloteca.ro** — 403 inclusiv in browserul propriu al lui David, de pe
IP-ul lui (2026-08-21). Nu e anti-bot fata de noi, e sit picat. De redeschis doar daca
David confirma ca a revenit.

**Blocate final** — *inaccesibile fara instrumente la care s-a renuntat*:
**pccomponentes.com** si **watchshop.ro** (Cloudflare Turnstile, verificare
interactiva); **cardmarket** a fost salvat de browser, dar ruta lui de produs ramane
403 pe HTTP pe toate profilurile.

**Verificare periodica:** **sneakerindustry.ro** — `products.json` da 403 pe toate cele
trei profiluri (ultima verificare 2026-08-20). Enumerarea Shopify ramane inchisa; se
re-verifica la o runda de watchlist viitoare, nu ad-hoc.

**Degradate la sonda, nereluate:** sole.ro (502, si reclasificat — nu e magazin de
fashion), farmaciatei.ro (cautare goala).

## 4. Candidatii de val D adunati pe drum

Fiecare cu stadiul temei lui, ca valul D sa nu porneasca de la zero:

| candidat | stadiu |
|---|---|
| f64.ro | **design API VTEX copt**, documentat la VTX-2 |
| eMAG Resigilate | **masurat integral la EMAG-1**: 25 de categorii, 1948 de produse doar pe Laptop/Tablete/Telefoane, cardul poarta AMBELE preturi, paginare pe `/pN/`. Axa L cere insa ajustare (vezi EMAG-1) |
| cellini.ro | listarea promo: 539 de produse, 179 de carduri/pagina, `price`+`oldprice` per card in stare |
| cardmarket.com | listarea `/en/Magic` randata; livrarea e PER VANZATOR — pretul final nu e derivabil din pagina |
| bonami.ro | `__NEXT_DATA__` |
| ro.vivre.eu | `?discount=yes`, 46.536 de produse |
| intersport.ro | `/sale/` |
| toolnation.nl | listarea poarta 24 de `Product` in ld+json |
| elefant.ro | placa hidratata cu ambele preturi (5,7KB vs 133KB) |
| powerup.ro | listarea refurbished-sh |
| tezyo.ro | listarea de reduceri (deja in scannerul DEAL-2) |
| booztlet.com, bstn.com | API-uri de listare |
| footlocker.ro | `/ro/special-prices/` |
| forit.ro, istyle.ro | sectiunile de resigilate |
| conrad.com | `/en/promotions/sale.html` — se randeaza, dar ZERO ld+json |
| DEAL-2c, DEAL-3 | sortarile, respectiv `lastmod` din sitemap |

## 4b. EPILOG (G4-V4/G4-V4b) — patru „blocate" reexaminate, doua recuperate

Capitolul de mai sus consemna patru domenii ca **NEMASURATE pe PDP, din vina
recoltarii**. Sonda corectiva G4-V4 le-a dat fiecaruia verdictul pe o pagina de produs
adevarata. Doua au intrat; celelalte doua au primit cauza exacta — si niciuna nu era
ce credeam.

**Diagnosticul care le tinea „blocate".** Sondele foloseau euristica „cardul cu
path-ul cel mai adanc", care alesese: `/magazin/` (REVISTA reichelt) in loc de catalog,
`/c/promo/bestsellers` (o CATEGORIE) in loc de PDP la ccc, indexul `/sct/0/` la
fressnapf, si — la G4-V2 — chiar butonul de checkout la sportsdirect, respectiv
`/service/email-us/` la lego. Fixul e acum **IN COD**, trei filtre in ordine:
(1) candidatul vine dintr-un CARD CU PRET de pe o listare randata, niciodata din home;
(2) filtre negative pe rute de actiune si editoriale (login/checkout/cart/`/magazin`/
blog/…); (3) validare LA INCARCARE — `@type: Product|ProductGroup`, sau microdata, sau
bloc unic de pret — altfel candidatul se ARUNCA, maximum doi per tinta. O regula scrisa
in harness nu se uita la a treia rulare; una tinuta minte, da.

Fixul s-a validat in AMBELE sensuri in aceeasi rulare: a aruncat doi candidati falsi la
sportsdirect (in loc sa produca un verdict fals) si a gasit catalogul corect la
reichelt, ocolind revista.

### Recuperate

* **reichelt.de** — INTRAT, `method: "microdata"`. Nu jsonld: ld+json-ul are doar
  `Organization`/`WebSite`/`BreadcrumbList`/`WebPage`. Traseul real: home -> 72 de cai
  de catalog -> `/de/de` (57 de carduri) -> PDP `/de/de/shop/produkt/<slug>`. Masurat pe
  DOUA PDP-uri cu preturi mult diferite: **89,99 EUR** si **1.188,50 EUR**, genericul
  fara override. **NU e intrare de browser**, desi acolo a fost masurat prima oara:
  verificat pe HTTP inainte de intrare, da 200 pe profilul de productie, fara challenge,
  cu aceeasi valoare. A patra aplicare a regulii „viabil prin browser ≠ are nevoie de
  browser", dupa forit.ro, lego.com si footlocker.ro.
* **decathlon.ro** — INTRAT, `method: "browser"`, deblocat de un fix GENERAL de
  extractor (vezi mai jos). Aici regula a functionat invers: verificat pe HTTP, da
  **403 pe toate cele trei profiluri** — deci browserul chiar e necesar.

### Fixul general: aplatizarea listelor imbricate in `offers`

decathlon publica `offers` ca **lista de DOUA liste** a cate 9 `Offer` — 18 in total,
toate cotate `159,99 RON` / `InStock`. Consumatorii (`_price_from_offers`,
`_variants_from_offer_list`) sar orice element care nu e dict, deci le pierdeau pe toate
18: pagina cadea cu `no_product_data` **desi publica preturi perfect valide**. Nu era o
pagina fara date, era o forma nerecunoscuta.

`_aplatizeaza_oferte` normalizeaza o SINGURA data, in `_collect_jsonld`, la sursa —
amandoi consumatorii citesc acelasi `obj.get("offers")`, deci contractele lor raman
neatinse. Recursiva, cu limita de adancime; elementele nedict se pastreaza verbatim, ca
o forma noua sa se vada in dump in loc sa dispara tacut.

**Tabel de regresie, disciplina G2F-4:** extractorul rulat pe **450 de dump-uri** din
toate bancile, inainte si dupa. Predictia scrisa in avans — „identic peste tot +
decathlon devine extractibil" — s-a confirmat exact: **o singura diferenta**, decathlon
din `no_product_data` in `159,99 RON`. Celelalte 449, identice.

### Reclasificate (cauza reala, alta decat recoltarea)

* **ccc.eu** — **BLOCAT DE CONSIMTAMANT**, o clasa NOUA, distincta de anti-bot.
  Categoria randeaza 898.187 octeti cu 672 de ancore, dar textul vizibil e bannerul de
  cookie-uri si sunt **zero preturi**. Singurul buton masurat e „Acceptă toate
  cookie-urile" — **niciun buton de refuz**; selectorii de refuz ai productiei
  potrivesc 0 noduri. Harness-ul apasa DOAR refuz, deliberat: a accepta cookie-uri in
  numele lui David e o decizie care ii apartine lui, nu sondei. Zero markere de
  challenge, fara turnstile — deci nu e blocaj tehnic, e unul de politica. Se deblocheaza
  daca (si numai daca) David decide ca harness-ul are voie sa accepte pe anumite domenii.
* **fressnapf.ro** — **NEMASURABIL pe calea de browser**. Categoria CORECTA randeaza
  (`Câini - Fressnapf Romania`, 304.242 octeti), dar produsele nu apar nici in DOM, nici
  in stare: ld+json are doar `BreadcrumbList`/`ItemList` de navigatie, zero chei de pret
  sau de produs, doar `dataLayer`. Singurul pret vizibil (`199 lei`) e pragul de livrare
  gratuita. Produsele vin dintr-un XHR ulterior — cere sonda de API, alta runda.
* **sportsdirect.ro** — **CERE EXTRACTOR CUSTOM**, deci nu intra in runda asta.
  Listarea e perfecta (61 de carduri in 3,54s), dar PDP-ul n-are date structurate:
  ld+json doar `BreadCrumbList` (cu majuscula neconforma). Pretul EXISTA in stare:
  `"productId":"113526","productPrice":144.00,"productPriceInBaseUnit":120.0` —
  ancorabil pe `productId`, tiparul cellini. CAPCANA: selectorii `[class*=price]` sunt
  toti `product-line-card__price*`, adica etichete de COS („Preț:", „Total:"), nu pretul
  produsului. `144/120 = 1,2`, deci `productPrice` e BRUT si `productPriceInBaseUnit` e
  NET. Moneda e **EUR pe domeniu `.ro`**.

### Corectura la nota sneakerindustry

Faptul masurat e **doar ca ENUMERAREA e inchisa** (`products.json` -> 403 pe toate
profilurile). Situl functioneaza normal; nu e blocat si nu e picat. Deci nu apartine
clasei „verificare periodica pentru revenire", ci fluxului obisnuit: o runda SI-1 pe
calea jsonld il poate valida oricand, fara sa astepte redeschiderea enumerarii.

### Cifra actualizata

**93 -> 95 de domenii validate.**

## 5. Gardul

**Axa L se considera INCHISA.** Orice domeniu nou de-acum intra prin fluxul standard —
sonda intai, implementare dupa — nu prin redeschiderea acestei liste. Absentele de mai
sus nu sunt un backlog; sunt verdicte. Se redeschid punctual, cu motiv, nu ca lot.

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

---

# SNK-2 — lotul de sneakers (sonda SNK-1, 2026-08-21)

Trei tinte, trei naturi, un singur verdict pe fiecare. Doua intra in registru, una
asteapta o reparatie de scanner. Capitolul se deschide dupa gardul axei L fiindca
exact asta prevedea gardul: domeniile noi intra prin fluxul standard — sonda intai,
implementare dupa — nu prin redeschiderea listei inchise.

## 1. sneakerindustry.ro — INTRAT pe `og`, si o corectie de PLATFORMA

Cea mai lunga poveste din watchlist se inchide, dar nu cum era scrisa.

**Ce spunea banca.** „Shopify cu enumerarea inchisa": `products.json` da 403 pe toate
cele trei profiluri (ultima verificare 2026-08-20), deci domeniul sta pe „verificare
periodica pentru revenire". Corectura din epilogul G4-V4 nuantase deja verdictul —
faptul masurat e DOAR ca enumerarea e inchisa, situl functioneaza pentru oameni — dar
pastrase premisa.

**Ce e masurat.** Premisa era gresita. Situl **nu e Shopify**:

```
powered-by: PrestaShop
set-cookie: PHPSESSID=...; PrestaShop-77a7fdbc0e11141a4675f53b63935921=...
server: cloudflare
```

Deci `products.json` nu e „o enumerare inchisa": e o ruta care **nu exista pe aceasta
platforma**, iar 403-ul e Cloudflare pe o cale straina. Consemnarea „se re-verifica la
o runda de watchlist viitoare" ramane **fara obiect** — nu se poate deschide ceva ce nu
exista. Domeniul iese din clasa „verificare periodica" definitiv, nu temporar.

Regula de metoda, a treia oara in acest jurnal (dupa WL-4 si dupa epilogul G4-V4):
**verdictul vechi se citeste ca o masuratoare, cu premisele ei — nu ca un fapt.**

**Axa L: VIABILA, dar NU pe `jsonld`.** PDP-urile n-au **niciun** ld+json. Metoda
masurata e `og`, pe doua PDP-uri cu preturi diferite: **899,10 RON** si **692,10 RON**,
moneda RON incrucisata in `og` SI in afisaj. Fragmentul propriu, verbatim:

```html
<p class="product-price has-discount" itemprop="offers" itemscope itemtype="https://schema.org/Offer">
  <link itemprop="availability" href="https://schema.org/InStock"/>
  <span itemprop="price" content="899.1">899,10 RON</span>
  <meta itemprop="priceCurrency" content="RON">
</p>
<p class="product-discount"> <span class="regular-price">999,00 RON</span> </p>
```

Trei capcane, toate necesare la implementare:

| capcana | masuratoare |
|---|---|
| `og:title` e numele SITULUI | „Sneaker Industry - SNKR IND." pe ORICE produs. Numele real e in `h1`: „On Cloud 6 Geo WP", „On Cloudzone". De aici override-ul `name_selector: "h1"`. |
| microdata e AMBIGUA | un singur `itemtype=schema.org/Product`, dar **12** noduri `itemprop=price`: cel propriu plus 10 carduri de recomandare (`.product-price-and-shipping`) si un duplicat `.physicalStoresProductPrice`. De aceea genericul cade pe `og`; microdata NU e o alternativa sigura fara selector. |
| widget de rate | `.mokka-price-amount` = „74,93 RON/luna". |

Omnibus: **NEMARCAT**. Pretul vechi exista (`span.regular-price`) dar fara `<del>`/`<s>`
si fara nicio formulare de 30 de zile.

**Axa D: nesondata, nu blocata.** Listarea `/ro/reduceri-de-pret` are 48 de carduri
`article.product-miniature.home-product`, cu forma de PDP
`/ro/<categorie>/<id>-<id>-<slug>.html`. Descriptorul se scrie la un val ulterior, cu
masuratori proprii — nu se ghiceste acum.

## 2. buzzsneakers.ro — descriptor COMPLET, intrare AMANATA (motiv: scannerul)

Axa L era deja in registru (LOT3, `jsonld`, `validated`). SNK-1 a masurat exclusiv
listarea, si a adus in plus proba de platforma care lipsea.

**Inrudirea NBSHOP, dovedita din AMBELE parti.** Nota `sportvision.ro` cerea exact
asta: „inrudirea n-a fost dovedita cu fragmente verbatim din AMBELE parti, fiindca nu
exista dump buzzsneakers". Exista — din LOT3 — iar acum exista si dump de listare.
Semnalele coincid: cookies `NBIDSN` + `NBPHPSESSIONSECURE`, marker `NBSHOP` in corp,
cai de imagine `slike-proizvoda`, si resturi sarbesti netraduse chiar in carduri
(`Uporedi`, `Brzi Pregled`, `Sacuvano u omiljne`).

**Descriptorul masurat**, gata de transcris:

| cheie | valoare masurata |
|---|---|
| `url` | `https://www.buzzsneakers.ro/produse/outlet` |
| `page_url_template` | `https://www.buzzsneakers.ro/produse/outlet/page-{n}` — numarul e in CALE, cu CRATIMA |
| pagini | `data-total-pages="39"`, 24 de carduri pe pagina, **918 produse** citite la scanul live |
| `currency` | `RON` |
| `card` | `.product-item` (24/pagina; cardul-parinte, cel care poarta atributele) |
| `link` | `a.product-link` |
| `title` | `.title` — ancora produsului are textul „Detalii" pe TOATE cardurile |
| `price_text` | `div.current-price span.value` -> `455,99` |
| `price_parse` | `eu_comma` |
| `reference_kind` | `nemarcat` |

**Paginarea NBSHOP e masurata acum.** Nota lui sportvision o lasase drept
„`a[rel='next']` cu textul «Arata mai multe», deci incarcare client-side, nemasurata".
Verbatim din dump:

```html
<a rel="next" href="https://www.buzzsneakers.ro/produse/outlet/page-2"
   class="btn btn-default next-load-btn" data-total-pages="39"
   onclick="autoLoadProductForPage(2, 39, false, event)">
```

AJAX-ul e o **imbunatatire peste un URL de server real**: p2 raspunde 200 cu 24 de
produse **disjuncte** de p1 (suprapunere 0, Jaccard 0.000). Pe sportvision ramane de
re-masurat pe el insusi — inrudirea de platforma nu tine loc de masuratoare.

**Doua motive pentru care cheia `listing` NU s-a scris inca.**

*(a) `compare_at` nu se poate citi.* Pretul vechi exista pe cardul-parinte, dar numai
ca `data-productprevprice="759,99"` — cu VIRGULA. Calea de atribut a scannerului
(`price_attr`/`compare_attr`) trece prin parserul strict cu punct, deci ar da tacut
None. Vizibil nu se randeaza niciun pret taiat (zero `<del>`/`<s>`), iar
`data-productdiscount` e constant `"0"` pe toate cardurile. Domeniul ar califica deci
pe R2 (minim istoric), nu pe R1.

*(b) — decisiv — 404 e semnalul de sfarsit de paginare.* Masurat live: scanul a mers
pe cele 39 de pagini, iar pagina 40 a dat **404**. `_scaneaza_domeniu` ridica
`RuntimeError` la orice status diferit de 200; opririle lui sunt doar „grila goala pe
200" (otter, caseking) si „pagina repetata" (noriel, bergfreunde). Consecinta e mai
grava decat pare: exceptia cade **inainte de `db.commit()`**, deci se pierde TOT
scanul, inclusiv cele 39 de pagini deja citite. Cu numarul exact de pagini scanul merge
perfect — **39 pagini, 918 produse, 0 alerte, 918 randuri de memorie de pret, 160 s** —
dar `/produse/outlet` e un OUTLET: numarul de pagini scade des, si la prima scadere
sub pragul scris s-ar pierde iar totul.

**Decizia (David, in sesiune): la valul D, cu scannerul reparat.** Valul invata
scannerul ca un 404 pe o pagina > 1 e OPRIRE, nu esec — dupa care buzzsneakers intra
cu descriptorul de mai sus, iar `max_pages` redevine o margine inofensiva. Atunci se
poate adauga si citirea atributului cu virgula, si R1 porneste odata cu R2.

Fixture-ul de teste nu s-a comis (whitelist-ul rundei il conditiona de decizia
„acum"). Se regenereaza dintr-un dump SNK-1 cu:

```
python -c "from bs4 import BeautifulSoup as B; h=open('scripts/diagnostics/dumps_snk1/buzzsneakers.ro_listare_p1.html',encoding='utf-8',errors='replace').read(); cs=B(h,'html.parser').select('.product-item')[:3]; open('backend/tests/fixtures/listing/buzzsneakers.ro_cards.html','w',encoding='utf-8').write('<html><body><div id=\"grid\">\n'+'\n'.join(map(str,cs))+'\n</div></body></html>\n')"
```

Valorile asteptate ale primului card, verbatim din dump: pret **455,99**, titlu
**„NIKE Pantofi Sport React Revision"**, URL
`/pantofi-sport/234081-nike-pantofi-sport-react-revision`, `compare_at` **None**.

## 3. nike.com — INTRAT pe `jsonld`, contra asteptarilor

Sonda pornise cu asteptari explicit mici: varf de clasa de protectie, iar
`BLOCAT_FINAL` era un deznodamant asumat ca legitim la prima atingere. Masuratoarea a
dat altceva, pe ambele trepte.

**Treapta 1 (HTTP).** `https://www.nike.com/ro/` da **200** pe profilul de PRODUCTIE
(`chrome131`), 684 KB, `<title>Nike. Just Do It. Nike RO`, **zero challenge**, fara
escaladare de profil. Singurul cookie e `ak_bmsc` — infrastructura Akamai, nevinovat
prin el insusi, exact ca `_abck` la G2C-1b si `cf-ray` la G2C-2.

**De ce s-a escaladat totusi la browser.** Home-ul si categoriile n-au pret
server-side: `__NEXT_DATA__` fara chei de pret, zero linkuri `/t/`. Deci treapta 1 nu
putea RASPUNDE axei L — `NEMASURABIL`, nu blocat. Distinctia e consemnata anume, ca sa
nu devina „nike e blocat" in banca.

**Treapta 2 (browser).** Listarea randata `/ro/w/back-to-school-shoes-840ikzy7ok` a dat
24 de candidati `/t/`; PDP-ul a iesit `VALIDAT` in **2,23 s**, cu `ProductGroup` si 19
oferte, toate cu pret.

**Si apoi regula G4-V4b, a cincea oara.** Acelasi PDP, cerut pe HTTP:

```
200, chrome131, 758.126 octeti, ld+json: ['ProductGroup'], 19 oferte, toate cu price
{'name': 'Nike Mercurial Superfly 11 Elite Firm-Ground Low-Top Football Boots',
 'price': 1499.99, 'currency': 'RON', 'in_stock': None, 'method': 'jsonld'}
```

**Nike NU are nevoie de browser.** Dupa forit.ro, lego.com, footlocker.ro si
reichelt.de, asta e a cincea aplicare a regulii — dar cu o forma NOUA, care merita
scrisa separat fiindca generalizeaza la orice SPA:

> Absenta datelor pe HOME nu prezice absenta lor pe PDP. Browserul poate fi necesar ca
> sa **recoltezi** URL-ul de produs, fara sa fie necesar ca sa **citesti** pagina.

Forma masurata: PDP `/ro/t/<slug>/<cod-stil>`, listari `/ro/w/<slug>`. `in_stock` iese
`None` — ofertele n-au `availability`; e negasit, nu ignorat. Axa D pe nike nu s-a
sondat: intai verdictul de L.

## 4. Corectii ramase din SNK-1

* Nota `sportvision.ro` spune „nu exista dump buzzsneakers". Exista, din LOT3, la
  `scripts/diagnostics/dumps/lot3_fashion_ro/buzzsneakers.ro/`; inrudirea NBSHOP e
  dovedita mai sus. Nota se corecteaza cand se atinge intrarea, la valul D.
* Recoltarea de PDP-uri a gresit din nou, altfel decat la G4-V4: sortarea pe adancimea
  caii a urcat URL-uri de FACETA (`?q=Marime+-37+1//3` — `1//3` aduce doua slash-uri in
  plus) peste PDP-urile reale, arzand 4 cereri pe 403-uri care erau refuzul modulului
  de faceta, nu al sitului (corpul lor era listarea intreaga, 440 KB). Filtrul negativ
  pe facete e acum in harness-ul de sonda.

## 5. Cifra actualizata

**95 -> 97 de domenii validate** (sneakerindustry.ro, nike.com).

---

# DEAL-D1 — Bucket A al axei D (sonda LST-D1, 2026-09-07)

Sonda LST-D1 a masurat opt domenii deja validate pe axa L, pentru care listarea de
reduceri era IDENTIFICATA in notele registrului dar NEMASURATA. Runda de fata scrie
in registru exclusiv ce a iesit din raportul ei
(`backend/scripts/diagnostics/dumps_lstd1/raport.md`), plus verificarea de enumerare
pe care sonda o lasase deschisa.

## 1. Bilantul

| domeniu | listare | paginare | produse | referinta | verdict |
|---|---|---|---|---|---|
| zooplus.ro | `/shop/oameni_animale/promotii` | `?p={n}`, clamp la p1 | 801 (48/pag) | `nemarcat` — NU se citeste | **CSS_GRID, intrat** |
| footlocker.ro | `/ro/special-prices/` | `/p{n}/`, clamp la p1 | 760 (`data-total-pages="38"` x 20) | `prp` („Pret de vanzare recomandat:") | **CSS_GRID, intrat** |
| forit.ro | `/resigilate/` | `/p{n}/c`, clamp la p1 | 413 (60/pag) | `nemarcat` | **CSS_GRID, intrat** |
| direct-running.com | `/outlet` | NICIUNA (buton „Show more") | 24 SSR din 1406 | `nemarcat` („Starting at") | **CSS_GRID, intrat** (`max_pages: 1`, tiparul bonami) |
| sneakerindustry.ro | — | — | — | — | **SHOPIFY_DESCHIS -> `method: shopify`** |
| istyle.ro | — | — | — | — | **SHOPIFY_DESCHIS -> `method: shopify`** |
| cyberport.at | `/apple-und-zubehoer/outlet-a-b-ware-.html` | — | — | — | **BLOCAT, ramane in afara** |
| elefant.ro | necunoscuta | — | — | — | **NEMASURAT, ramane in afara** |

`listing_domains()`: 14 -> **18**. `shopify_domains()`: 13 -> **15**.

## 2. Cele doua corectii de registru

**sneakerindustry.ro — a DOUA corectie de platforma pe acelasi domeniu, in sens
INVERS fata de prima.** Domeniul statuse „Shopify cu enumerarea inchisa" (403 pe
`products.json`), apoi SNK-1 masurase `powered-by: PrestaShop` + `PHPSESSID` si
scrisese ca „nu se poate deschide ceva ce nu exista". Intre timp magazinul a migrat
INAPOI pe Shopify, ceea ce invalideaza exact acea concluzie. Patru semnale
independente la LST-D1: antet `powered-by: Shopify`; cookie-uri `_shopify_y` /
`_shopify_s`; `/ro/reduceri-de-pret` redirecteaza la `/collections/reduceri`; cardul
e `product-card` (zero `product-miniature` in dump).

Lectia nu e „registrul se mai invecheste" — asta se stia de la WL-4. E mai ingusta:
**o nota care spune „nu se poate re-verifica, fiindca obiectul nu exista" isi pierde
temeiul in tacere daca platforma se schimba.** SNK-1 anulase consemnarea „se
re-verifica daca se deschide enumerarea"; corect atunci, gresit sase luni mai tarziu,
si nimic din cod n-ar fi semnalat-o. Verificarea a costat 3 cereri.

**zooplus.ro — „selector stabil" era o masuratoare pe jumatate.** Nota G2F-4 spunea
ca listarea are „817 produse si selector stabil". Clasa `ProductCard_productCard__HRbGU`
chiar selecteaza exact cele 48 de carduri — dar sufixul `__HRbGU` e un hash de build
CSS-modules si moare la primul redeploy. Ancora corecta e atributul de test al
magazinului, `data-zta="product-card"`. Un selector care merge azi nu e acelasi lucru
cu unul stabil, iar diferenta se vede doar daca te uiti la CE anume e clasa.

## 3. Decizia `compare_at` pe zooplus: campul exista si NU se citeste

Singura referinta din cardul zooplus e etichetata `Individual`, cu tooltipul verbatim
„Pretul total al acelorasi produse daca sunt cumparate separat" — adica suma acelorasi
produse cumparate bucata cu bucata, o comparatie pachet-vs-bucata, **nu un pret
anterior**. Distributia masurata pe toate cardurile:

| pagina | carduri | cu referinta | eticheta `Individual` | eticheta „Pret normal" |
|---|---:|---:|---:|---:|
| p1 | 48 | 12 | 12 | **0** |
| p2 | 48 | 19 | 19 | **0** |

Pagina CONTINE fraza Omnibus („Pret normal = Cel mai mic pret la care a fost vandut
produsul in ultimele 30 de zile"), dar in subsolul legal si in dictionarul i18n, nu pe
un camp de card — lectia bergfreunde, a doua oara. Citita ca `compare_at`, referinta ar
fabrica un deal pe fiecare multipack din catalog. Deci descriptorul zooplus n-are
`compare_*`: R1 nu poate porni niciodata acolo, iar dealurile vin exclusiv din minimul
istoric (R2), acelasi regim ca toolnation si buzzsneakers.

Aceeasi forma, alt motiv, la **footlocker**: referinta exista si e etichetata explicit
(„Pret de vanzare recomandat:", plus o a doua linie „Cel mai mic pret pe 30 de zile:"),
dar pe cele 60 de carduri masurate `current == recommended == lowest`. Se citeste,
fiindca poate diverge; doar ca la baseline nu califica nimic.

## 4. Treapta de parsare `us_dot`

Pana la DEAL-D1, `price_parse` era documentatie: orice descriptor pe `price_text` mergea
prin `_pret_eu_comma`, care sterge punctul ca separator de mii. Corect pentru
„1.393,94 lei"; fatal pentru „$117.63", care iesea **11763.0**. Nu e o deductie —
LST-D1 §2.8 a trecut descriptorul propus prin `extrage_carduri` insusi si a citit
valoarea.

Calea de atribut nu era o alternativa: cardul direct-running n-are niciun atribut
numeric (0 `content=`, 0 `data-price*`). Deci `_pret_us_dot`, oglinda stricta a
parserului european (virgula = separator de mii si se sterge, punctul = zecimal si
ramane), iar `_pret_of` chiar citeste acum `price_parse`. Valorile admise: pe text
`eu_comma` (implicit, pentru cei zece descriptori anteriori) si `us_dot`; pe atribut
`attr_float`. **O valoare necunoscuta ridica `ValueError`, nu cade pe un implicit** —
un fallback tacit ar transforma o greseala de tastare in registru intr-un feed intreg
de preturi de 100x care arata perfect plauzibil.

De ce nu se ghiceste din sir: „1.299,00" si „1,299.00" inseamna acelasi lucru cu
separatorii inversati, iar „117.63" inseamna 117.63 pentru un parser si 11763.0 pentru
celalalt. Numai magazinul stie, deci numai registrul poate spune.

## 5. Ramase in afara

**cyberport.at — BLOCAT.** Poarta a intors `None` pe listare **cu profilul `chrome` din
registru**, acelasi care merge pe PDP-uri de la G2B-2. Cererea directa de clasificare:
403, `cf-mitigated: challenge`, `<title>Just a moment...`, markeri `cf_chl` x10, zero
`turnstile`, zero captcha. Deci amprenta e suficienta pentru PDP si insuficienta pentru
outlet — material pentru mecanismul de browser, nu pentru un descriptor CSS.

**elefant.ro — NEMASURAT.** Home-ul raspunde 200 si e o pagina reala, dar nu poarta
NICIUN link catre `lichidari-de-stoc` (zero href cu „lichidari", „outlet" sau
„reducer"; singurele „promo" sunt categorii de carte). Ruta incercata a raspuns **503**
cu o pagina de mentenanta servita de Cloudflare Workers (`<title>Maintenance Banner</title>`),
deci indisponibilitate, NU blocaj anti-bot. Se reia cu `--only elefant.ro`, pornind de
la URL-ul de lichidari incercat direct, nu cautat in home.

## 6. Verificarea live a celor doua migrari

O cerere per domeniu, prin exact functia de extractie pe care o foloseste add-by-link:

| domeniu | `price` | `currency` | `in_stock` | `method` |
|---|---|---|---|---|
| istyle.ro (`resigilat-apple-13-inch-ipad-pro-m4-…`) | `5349.99` | RON | True | shopify |
| sneakerindustry.ro (`60915795`) | `169.0` | RON | True | shopify |

Ambele coincid cu valorile sondei. De notat pentru istyle: pe ld+json `in_stock` iesea
`None` (`Offer` n-are `availability`); pe calea shopify vine din `available` al
variantei, deci migrarea a castigat si un camp, nu doar acoperire.

## 6b. `search` vine odata cu `method: shopify`, nu ca decizie separata

Briefing-ul rundei ceruse sa NU se adauge `search` pe cele doua migrari („decizie
separata"). Registrul nu permite asta: `test_search_shopify_pe_toate_shopify` cere
`search.kind == "shopify"` pe FIECARE domeniu din `shopify_domains()`, iar cele 13
intrari shopify anterioare il au toate. Argumentul gardei, verbatim din docstring-ul
ei: mecanismul e API de PLATFORMA (`/search/suggest.json`), „disponibil pe orice
magazin Shopify prin constructie — o intrare fara `search` ar fi o omisiune, nu o
decizie", si fara garda magazinul „ar lipsi TACIT din pagina de cautare".

Deci `search: {"kind": "shopify"}` s-a adaugat pe amandoua, cu doua consecinte de
consemnat onest:

* **Efect vizibil:** istyle.ro si sneakerindustry.ro apar de acum in pagina „Scanare
  Magazine". Asta e schimbarea pe care briefing-ul voia s-o amane.
* **Nemasurat:** `/search/suggest.json` NU s-a cerut pe niciunul din cele doua domenii
  in runda asta (bugetul sondei a fost cheltuit pe enumerare). Disponibilitatea lui e
  preluata din premisa gardei, nu dintr-o masuratoare pe aceste doua magazine.

## 7. Cifra actualizata

**97 de domenii validate, neschimbat** — DEAL-D1 n-a adaugat domenii, ci capabilitati
pe domenii deja validate: 4 descriptori de listare, 2 migrari pe `shopify`.

---

## EMAG-D — eMAG Resigilate pe axa D + mecanismul `entries`

Prima runda de axa D care a cerut o schimbare de MECANISM, nu doar un descriptor.
Materia prima: dump-urile EMAG-1 din 20-21 august, analizate offline la Partea A
(`scripts/diagnostics/dumps_emag_rs/raport_emag_d.md`), plus trei cereri vii la B3.

### 1. De ce `entries`

eMAG isi imparte cele ~8000 de produse resigilate pe **12 departamente**, fiecare cu
paginare proprie in CALE. Pana acum un descriptor putea declara O singura listare, deci
eMAG ar fi intrat cu o categorie si ar fi pierdut unsprezece.

`entries` e o lista de `{url, page_url_template, max_pages?}`, SAU-EXCLUSIV cu `url`.
Cei 18 descriptori anteriori nu s-au atins si nu s-au convertit — forma cu `url` da o
lista cu un element si merge pe acelasi drum.

Miezul e ce e per INTRARE si ce e per SCAN, si fiecare jumatate a fost aleasa impotriva
unui esec concret:

| stare | domeniu | de ce |
|---|---|---|
| `linkuri_vazute` | **per intrare** | „Clamp" inseamna *lista asta mi-a servit iar pagina precedenta*. Doua categorii care impart legitim un produs NU sunt un clamp; partajat, a doua categorie ar fi taiata dupa prima ei pagina. |
| contorul de pagini | **per intrare** | Un 404 pe pagina 1 a categoriei a doua trebuie sa ramana EROARE (hub-ul s-a schimbat). Cu contorul global ar fi fost inghitit ca „final de paginare". |
| `vazute` | **per scan** | Un produs poate fi listat si la „Laptop" si la „PC". Resetat per intrare, ar fi numarat de doua ori si reevaluat fata de un minim pe care chiar acest scan l-a coborat — „inventarea unei reduceri", exact ce interzice SCAN-1. |
| `calificate` | **per scan** | Inchiderea dealurilor necalificate se face dupa TOATE intrarile; altfel prima categorie ar inchide dealurile celei de-a doua. |

### 2. Cele 12 intrari

Ordinea e a hub-ului (`category_panel_1_0` .. `_12_0`), slug-urile verbatim din ancorele
lui. Numarul de pagina sta la **MIJLOC** — `…/resigilate/<cat>/p{n}/d` — citit din
`<link rel="next" href="/resigilate/laptop-tablete-telefoane/p2/d">`.

| # | departament | slug |
|---|---|---|
| 1 | Laptop, Tablete & Telefoane | `laptop-tablete-telefoane` |
| 2 | PC, Periferice & Software | `pc-periferice-software` |
| 3 | TV, Audio-Video & Foto | `tv-audio-video-foto` |
| 4 | Electrocasnice & Climatizare | `electrocasnice-climatizare` |
| 5 | Gaming, Carti & Birotica | `gaming-carti-birotica` |
| 6 | Bacanie | `alimente-bauturi` |
| 7 | Fashion | `fashion` |
| 8 | Ingrijire personala & Cosmetice | `ingrijire-personala-cosmetice` |
| 9 | Casa, Gradina & Bricolaj | `casa-bricolaj-petshop` |
| 10 | Sport & Travel | `sport-activitati-aer-liber` |
| 11 | Auto, Moto & RCA | `auto-moto-rca` |
| 12 | Jucarii, Copii & Bebe | `jucarii-copii-bebe` |

**`max_pages: 40`, unic la nivel de descriptor.** Hub-ul publica UN total (7996 de
produse) si niciun numar per categorie; singura categorie cu dump propriu,
`laptop-tablete-telefoane`, anunta 1948 = 33 de pagini la 60/pagina. 40 e aia plus marja
(conventia otter). Un plafon per intrare ar fi trebuit INVENTAT pentru celelalte
unsprezece — vezi limitele.

**Corectie la EMAG-1**, care numarase 25 de categorii: sunt **12**. Cele 67 de href-uri
`/resigilate/*` din hub se impart in 12 categorii, 10 branduri, 5 benzi de discount, 11
benzi de pret, 10 filtre, 4 sortari si 2 pagini. „25" se obtine numarand si brandurile —
care nu partitioneaza catalogul.

**URL-ul agregat exista si NU se foloseste.** `/resigilate` e el insusi o grila paginata
(`rel=next` catre `/resigilate/p2`, 7996 de produse = 134 de pagini), deci o singura
intrare ar fi acoperit tot. Dar adancimea lui n-a fost ceruta NICIODATA, nici la EMAG-1
nici la EMAG-D — cele trei cereri ale rundei s-au dus pe forma de categorie, care e
masurata. Nu se pariaza pe 134 de pagini neverificate.

### 3. Referinta: pretul de NOU, si de ce e `nemarcat`

Cardul poarta doua preturi:

```html
<p class="pricing rrp">NOU 4.999<sup><small class="mf-decimal">,</small>99</sup> <span>Lei</span></p>
<p class="product-new-price"><span class="fs-12">de la</span> 4.599<sup>…</sup> <span>Lei</span></p>
```

Incrucisat cu PDP-ul aceluiasi produs, care poarta verbatim
`"recommended_retail_price":{"amount":4999.99,"is_visible":true,"label":"NOU"}` si afiseaza
4.999,99 ca pret principal, 4.599,99 ca oferta resigilata: **referinta e pretul de vanzare
CURENT al unitatii NOI a aceluiasi produs, la acelasi comerciant.**

*Capcana de omonimie:* aceeasi cheie JSON apare pe PDP si cu `"label":"PRP:"` si valoarea
**6274.56** — ala e Pretul Recomandat de Producator, alt numar si alt lucru. Cardul arata
„NOU", nu „PRP".

Pe listare: zero „ultimele 30 de zile", zero „pret recomandat", zero „PRP", zero
„Omnibus". („cel mai mic pret" apare doar in textul de ajutor al sortarii, „30 de zile"
doar in politica de retur din `<meta>` — niciuna nu eticheteaza campul; lectia
bergfreunde, a treia oara.)

**Verdict `nemarcat`, dar campul SE CITESTE.** Nu e Omnibus si nu e PRP, insa e cea mai
buna referinta posibila pentru un resigilat: acelasi SKU, acelasi magazin, unitate noua —
„nou 4.999,99, resigilat 4.599,99" e o economie reala si verificabila. Pe 59/59 de carduri
cu referinta ea e STRICT peste pretul platit, zero inversate. Vocabularul registrului
n-are un al patrulea termen; **daca David vrea ca axa D sa poarte doar referinte legal
etichetate, `compare_text` se scoate si eMAG trece pe R2, ca zooplus.**

### 4. Capcanele de pret

**Pretul e spart pe noduri** — zecimalele intr-un `<sup>`, virgula intr-un
`<small class="mf-decimal">` separat. Nu e o problema, si merita stiut de ce: `_text_of`
foloseste `get_text(" ")`, deci pune spatii intre noduri, iar `_pret_eu_comma` sterge tot
ce nu e cifra/punct/virgula — inclusiv „de la", „NOU", „Lei" si spatiile, niciunul cu
cifre. Masurat prin functiile de productie:

| selector | `_text_of` | `_pret_eu_comma` |
|---|---|---|
| `p.product-new-price` | `'de la 4.599 , 99 Lei'` | **4599.99** |
| `p.pricing.rrp` | `'NOU 4.999 , 99 Lei'` | **4999.99** |

**„de la" e pe 60/60**: un resigilat are mai multe oferte (grade diferite), iar cardul
arata cea mai ieftina — pretul real platibil, ca „Starting at" la direct-running.

**Componente partajate: NICIUNA.** Intersectia `listare ∩ prod1 ∩ prod2` peste jetoanele
de pret e goala; pragurile de livrare si Genius nu apar ca sume in textul listarii.

**Capcana caruselului, a treia oara** (dupa LOT5 si powerup): corpul lui `plast` contine
18 aparitii de `card-item`, toate placeholder-e de carusel de recomandari
(`rec-card-item card-item js-card-item` cu `div.card-v2 card-shimmer` gol). Niciunul n-are
`js-product-data` — de aia clasa aia e obligatorie in selector, si de aia `plast` iese cu
zero carduri in loc de 18.

### 5. Cele 3 cereri de la B3

Dump-urile EMAG-1 aveau **17-18 zile**, iar conditia de oprire lipsea cu totul din ele
(EMAG-1 n-a cerut niciodata o pagina > 1). Trei cereri prin poarta, cu descriptorul deja
scris:

| eticheta | URL | status | octeti | carduri | cu compare | cu imagine |
|---|---|---:|---:|---:|---:|---:|
| `p2` | `…/resigilate/laptop-tablete-telefoane/p2/d` | **200** | 750 106 | **60** | 60 | 60 |
| `plast` | `…/resigilate/laptop-tablete-telefoane/p500/d` | **200** | 180 260 | **0** | 0 | 0 |
| `cat2_p1` | `…/resigilate/pc-periferice-software/d` | **200** | 816 220 | **60** | 60 | 60 |

**Conditia de oprire masurata: GRILA GOALA PE 200** — prima conditie din
`_scaneaza_domeniu`, aceeasi ca otter si caseking. Nu 404, nu clamp: pagina 500 raspunde
200 cu un corp de 180 KB fara niciun card de produs.

Ce a confirmat B3 fata de dump-uri: selectorii tin dupa 18 zile (produse complet noi —
`Nothing Phone (3)` la 3149.99 cu referinta 3677.48 pe `p2`), si descriptorul
generalizeaza peste intrari (`cat2_p1`, alta categorie: `Monitor Samsung Odyssey OLED G6`
la 1899.99 cu referinta 2866.80). Pe paginile vii referinta e prezenta pe **60/60**, fata
de 59/60 pe dump-ul din august.

### 6. `title_prefix`: NU s-a adaugat

Briefingul prevedea o cheie noua daca titlul cardului n-ar purta starea. **O poarta.**
Verbatim din card:

```html
<a class="card-v2-title …" href="…/pd/DDF9FV3BM/#used-products"><span class="text-success fw-semibold">RESIGILAT: </span>Telefon mobil Apple iPhone Air, 256GB, 5G, Light Gold</a>
```

`_text_of` intoarce `'RESIGILAT: Telefon mobil Apple iPhone Air, 256GB, 5G, Light Gold'`
pe **60/60 de carduri, pe toate cele trei dump-uri de listare**. O cheie de prefix ar fi
produs „Resigilat: RESIGILAT: …". Confuzia pe care decizia de resigilate o interzice nu se
poate produce aici — magazinul o previne singur.

**Ce NU ajunge in feed:** gradul (ca nou / foarte buna / acceptabila). Cautat pe toate 60
de carduri: zero aparitii. Sta pe PDP, in sectiunea catre care duce chiar linkul cardului
(fragmentul `#used-products` e pastrat deliberat in `url`; `external_id` si `handle` se
calculeaza pe CALE, deci nu atinge dedup-ul).

### 7. Ce NU s-a declarat, si de ce

* **`stock_attr`** — `data-availability-id` exista dar e `2` pe 60/60, deci nu se poate
  deosebi de o constanta de sablon. Capcana masurata pe toolnation, dovedita pe vivre.
* **`image`** — primul `<img>` din card E poza produsului (60/60, absoluta pe
  `s13emagst.akamaized.net`), deci `image_attr: ["src"]` ajunge. Placeholder-ul lazy e un
  `data:` pe atributul `style` al containerului, pe care `normalizeaza_imagine` il
  respinge oricum.
* **`price_attr`** — butonul de favorite poarta un JSON cu `"price":4599.99`, dar
  `_pret_strict` de pe calea `*_attr` asteapta un numar, nu un JSON. Ramane doar
  incrucisare, nu cale.

### 8. Limitele oneste

1. **Un singur total per categorie.** Doar `laptop-tablete-telefoane` are dump (1948).
   Pentru celelalte 11 nu exista numar, iar hub-ul nu-l afiseaza — de aici `max_pages`
   unic. O categorie cu peste 2400 de produse ar fi trunchiata tacut; nimic din masuratori
   nu spune ca exista una, dar nimic nu spune nici ca nu exista.
2. **Agregatul ramane neverificat** (vezi §2).
3. **Al doilea dump „de listare" din AB-1 e de fapt hub-ul** (`url_final` =
   `/resigilate?ref=hdr_resigilate`) — eticheta din numele fisierului induce in eroare.
   Ramane util ca al doilea punct in TIMP, nu ca a doua categorie.
4. **Oprirea e masurata pe O categorie.** `plast` s-a cerut doar pe
   `laptop-tablete-telefoane`; se presupune ca celelalte 11 se comporta la fel, fiindca
   sunt acelasi sablon.

---

## DEAL-D2 — lotul electronice RO pe axa D (sonda LST-D2, 2026-09-07)

Sonda LST-D2 a triajat 13 domenii de electronice RO cu 44 de cereri, iar controlul ei
(`dumps_lstd2/raport.md` §4) a trecut descriptorii propuși prin `extrage_carduri()` real
pe dump-uri. Runda asta scrie în registru cei cinci care au trecut, adaugă treapta de
parsare pe care unul dintre ei a cerut-o, și consemnează în `notes` motivul fiecărei
ieșiri. Verdictele nu se redeschid aici: materia primă e raportul, nu o măsurătoare nouă.

### 1. Cele 13 verdicte

| domeniu | verdict | în registru |
|---|---|---|
| altex.ro | CSS_GRID | **descriptor** |
| mediagalaxy.ro | CSS_GRID | **descriptor** (frate de platformă cu altex) |
| cel.ro | CSS_GRID | **descriptor** |
| itgalaxy.ro | CSS_GRID | **descriptor** |
| evomag.ro | CSS_GRID | **descriptor** (a cerut `eu_sup`) |
| vexio.ro | BLOCAT | doar `notes` |
| pcgarage.ro | BLOCAT | doar `notes` |
| senetic.ro | NEPOTRIVIT | doar `notes` |
| usedproducts.ro | JS_ONLY | doar `notes` |
| elefant.ro | JS_ONLY | doar `notes` |
| flanco.ro | NEMĂSURAT (nu blocat) | doar `notes` |
| flip.ro | NEMĂSURAT | doar `notes` |
| carrefour.ro | NEMĂSURAT | doar `notes` |

`listing_domains()`: 19 → **24**.

### 2. Cei cinci intrați

| domeniu | intrare | volum măsurat | paginare | referință |
|---|---|---|---|---|
| altex.ro | `/resigilate/` | 48 din 8052 anunțate | **niciuna în HTML brut** → `max_pages: 1` | `Nou:` pe 48/48 → `nemarcat` |
| mediagalaxy.ro | `/resigilate/` | 48 din 7516 anunțate | idem | idem |
| cel.ro | `/resigilate/` | 60/pagină, 2 pagini | `/resigilate/0i-{n}` | **niciuna** (`noDiscount` pe 60/60) |
| itgalaxy.ro | `/promotii/` | 36/pagină × 770 pagini | `/promotii/pagina{n}/` | `.old-price`, 9/36 și 18/36 → `prp` |
| evomag.ro | `/resigilate-produse-resigilate/` | 64/pagină, ≥11 pagini | `filtru/pagina:{n}` | `NOU:` pe 64/64 → `nemarcat` |

Trei lucruri merită scoase în față, fiindcă sunt decizii, nu descrieri:

* **`max_pages: 1` la altex/mediagalaxy e o măsurătoare, nu prudență.** Pagina anunță
  „8052 produse" și nu poartă niciun link de pagină; butonul vine gol
  (`<div class="Toolbar-next md:hidden"></div>`). Descriptorul vede deci 48 din ~8000,
  și asta e tot ce se poate citi fără alt mecanism. Pista de adâncime e API-ul intern
  `fenrir.altex.ro`, pe care producția îl folosește DEJA pentru căutare — rundă separată.
* **cel.ro intră FĂRĂ `compare_*`.** Pe 60/60 de carduri singurul preț e `div.pret_n`,
  iar clasa nodului părinte e chiar `noDiscount`. Un `compare_text` acolo ar fabrica o
  reducere pe fiecare card; deal-urile rămân exclusiv pe R2 (minim istoric).
* **`/promotii/` la itgalaxy e practic tot catalogul** (770 de pagini ≈ 27.700 de
  produse). E situația din DEAL-2b, unde întreg outletul otter era permanent „redus" și
  primul scan a produs 15.832 de deal-uri. Pragul R1 propriu căii de listare e ce ține
  feed-ul în frâu; acoperirea referinței (9-18 din 36) e oricum sub jumătate.

### 3. Treapta de parsare `eu_sup`

evomag randează `<span class="real_price">529<sup class="price_sup">99</sup> lei</span>`.
`_text_of` e `get_text(" ")`-based, deci șirul care ajunge la parser e `529 99 lei`, iar
ambele trepte de dinainte îl citeau **52999.0** — de 100 de ori prea mult, pe 64/64 de
carduri (controlul LST-D2 §4). E eșecul direct-running din DEAL-D1 cu altă cauză, deci
răspunsul e din nou un parser NUMIT pe care registrul îl alege, nu o euristică: odată
spațiul șters, „529 99" și „52999" sunt indistinctibile.

`_pret_eu_sup` păstrează spațiul ca separator și acceptă exact două forme —
`<întreg>` sau `<întreg> <două cifre>`:

| intrare | ieșire |
|---|---|
| `529 99 lei` | 529.99 |
| `NOU: 1.474 99 lei` | 1474.99 |
| `529 lei` | 529.0 |
| `1.474,99 lei` | 1474.99 (delegat la `eu_comma`) |
| `529 9 lei` | **None** (o singură zecimală) |
| `52 99 99` | **None** (două grupuri, ambiguu) |

Delegarea pe virgulă nu e o comoditate: `powerup.ro` are tot zecimale în `<sup>`, dar
al lui CONȚINE virgula, iar `eu_comma` îl digeră nemodificat (G2A-2). Aceeași delegare
face ca evomag să nu se strice în ziua în care ar începe și el să pună separatorul.

Valorile admise pe text sunt acum `eu_comma` | `us_dot` | `eu_sup`; pe atribut rămâne
`attr_float`, impus de calea de cod.

### 4. Cheia `compare_parse` — o coliziune de contract, găsită la scriere

itgalaxy e **primul** descriptor care citește prețul plătit din ATRIBUT
(`data-pprice="2815.99"`, 36/36) și referința din TEXT (`PRP: 525,00 lei`). Cele trei
descriptoare cu `price_attr` de dinainte (caseking, otter, tezyo) își iau și referința
din atribut, iar zooplus n-are referință deloc — deci faptul că `price_parse` e o cheie
UNICĂ pe descriptor n-a fost niciodată pus la încercare.

Pus la încercare, cade: garda cere `price_parse: "attr_float"` când există `price_attr`,
iar `_pret_of` consultă aceeași cheie și pe latura de text, deci `attr_float` ajungea în
`_PARSERE_TEXT` și ridica `ValueError` la primul card.

Reparația e cheia opțională `compare_parse`, citită DOAR pe latura de referință și doar
când există. Absentă, se cade înapoi pe `price_parse` — adică exact linia dinainte, deci
cele 19 descriptoare vechi rămân neatinse. Garda descriptorilor o cere acum exact când
`price_attr` și `compare_text` coexistă.

### 5. Cele 4 cereri live

Sonda LST-D2 citise ambele scheme de paginare din HTML-ul brut, dar nu ceruse nicio
pagină 2 — detectorul ei nu cunoștea separatorii (`0i-` la cel, `:` la evomag), așa că
șabloanele intraseră în raport marcate NEVERIFICATE. Confirmate acum
(`sonda_deal_d2.py`, dump-uri în `dumps_deal_d2/`):

| domeniu | etichetă | URL | status | octeți | carduri | rezultat |
|---|---|---|---|---|---|---|
| cel.ro | `p2` | `https://www.cel.ro/resigilate/0i-2` | 200 | 314 565 | 52 | **template confirmat** — 30 de căi noi față de p1, 22 comune |
| cel.ro | `plast` | `…/resigilate/0i-500` | 200 | 66 473 | **0** | oprirea e **GRILĂ GOALĂ** |
| evomag.ro | `p2` | `…/filtru/pagina:2` | 200 | 550 540 | 64 | **template confirmat** — 64 de căi noi, 0 comune |
| evomag.ro | `plast` | `…/filtru/pagina:500` | 200 | 308 449 | **17** | oprirea e **CLAMP pe ultima pagină** |

Ambele semnături de oprire sunt deja acoperite de `_scaneaza_domeniu`, fără nicio linie
nouă: `if not linkuri_pagina: break` prinde grila goală (cel), iar
`if linkuri_pagina <= linkuri_vazute: break` prinde clamp-ul (evomag) — a doua condiție
din triada măsurată la LST-1b.

Cele 22 de căi comune între p1 și p2 la cel.ro nu sunt un semn că template-ul e greșit:
dump-ul p1 e din seara precedentă, iar listarea se re-sortează între cereri. Garda
SCAN-1 (`vazute`, pe `external_id`) tratează deja exact cazul ăsta.

Prima verificare a lui `eu_sup` pe pagini PROASPETE, nu pe fixture: evomag p2 a dat
149.99 / 199.0 pe primul card și plast 1699.99 / 2599.99 — forme corecte, nu de 100 de
ori mai mari.

### 6. Capcanele nou documentate

Patru, toate din LST-D2, toate arătând ca o măsurătoare reușită și nu ca o eroare:

1. **Caruselul, a patra oară** (după LOT5, powerup, eMAG). Pagina de outlet a lui
   senetic randează server-side DOAR un `outlet-glide` de 25 de produse — 25/25 au un
   strămoș `glide__slide`, și nu există nicio grilă. Un carusel are exact forma unei
   grile; singura deosebire e strămoșul.
2. **`rel=next` de SIT, nu de pagină.** Pe senetic, pagina de outlet poartă
   `<link rel="next" href="https://www.senetic.ro/?page=2/">` — trimite la HOME cu un
   parametru inutil. `rel=next` e autoritar doar dacă URL-ul lui PĂSTREAZĂ calea intrării.
3. **`/campanii/` e prefixul listărilor la carrefour**, nu un marcaj de editorial.
   Penalizarea generică a împins singura candidată needitorială în frunte — pagina de
   REGULAMENTE de tombolă — care avea 13 blocuri link+sumă, destule cât să treacă pragul
   de „carduri". 5 din 6 cereri irosite.
4. **`None` din poartă ≠ blocat.** Pe flanco, poarta a întors `None`, dar cererea directă
   cu ACELAȘI profil (firefox135) a dat 200 și 881 KB de pagină reală, iar `classify()`
   rulat pe chiar acel corp întoarce `Outcome.OK`. Redirectul e către
   `https://www.flanco.ro:443/` (port explicit), deci cauza e în lanțul de hopuri al
   porții, nu în sit. Atinge și axa L — de investigat separat.

### 7. Rămase în afară

| domeniu | motiv |
|---|---|
| vexio.ro | Challenge Cloudflare (403, `cf-mitigated: challenge`, titlu „Just a moment...") chiar pe rădăcina domeniului, cu profilul implicit. |
| pcgarage.ro | Același challenge, la prima cerere de listare. Dacă se deblochează, e candidat pentru forma `entries`: PDP-ul listează TREI secțiuni de desigilate și CINCI de extra-reduceri, fără niciun URL agregat. |
| senetic.ro | NEPOTRIVIT: outletul SSR e un carusel de 25, zero referință pe 25/25. Axa D n-are pe ce se sprijini — nici R1 (fără preț tăiat), nici R2 credibil (nu se știe dacă cele 25 sunt tot outletul sau o rotație). Cardul arată totuși ambele prețuri, etichetate explicit: `div.price_our_net` „5 613,99 RON fara TVA" și `div.price_our_gross` „6 792,93 RON cu TVA", raportul 1,21 confirmat și pe listare. |
| usedproducts.ro | JS_ONLY: `/reduceri` răspunde 200 dar e o cochilie RSC de 43 KB al cărei text vizibil e exact titlul paginii, iar blobul `self.__next_f` are 32 KB și ZERO chei de preț. |
| elefant.ro | JS_ONLY. Scheletul e cartografiat complet — URL-ul real, paginarea `?pag={n}`, 8.260 de produse, grila goală la `?pag=500` — dar cele 60 de plăci sunt goale: Intershop le randează prin `ViewProduct-RenderProductComponents` per SKU, adică o A DOUA cerere. Ruta scurtă `/lichidari-de-stoc` dă 503 persistent. |
| flanco.ro | NEMĂSURAT, și NU blocat (v. §6.4). |
| flip.ro | NEMĂSURAT: home-ul are ZERO ancore `<a href>` în 377 KB (shell Next.js pur), deci intrarea nu se poate descoperi din navigație. Piste din `__NEXT_DATA__`: catalogul general e `/magazin/`, fațetele conțin `promo=GENIUS-DEAL`. |
| carrefour.ro | NEMĂSURAT (v. §6.3). Pistele reale: `/campanii/oferte-saptamanale` și `/campanii/reduceri-de-gama`. |

### 8. Limitele oneste

1. **Adâncimea la altex/mediagalaxy rămâne 48 din ~8000.** Nu e o limitare a
   descriptorului, ci a HTML-ului: paginarea nu există în corp.
2. **`max_pages` la cel.ro e 3 pe două pagini văzute.** Paginatorul poartă doar `0i-1` și
   `0i-2`; dacă listarea crește, plafonul taie tăcut — dar oprirea măsurată (grilă goală)
   se declanșează oricum înaintea lui pe volumul de azi.
3. **`max_pages` la evomag e 14 pe 11 pagini văzute în corp.** Oprirea reală e clamp-ul,
   prins de a doua condiție a scanerului; plafonul e doar plasă.
4. **Referința la itgalaxy e sub jumătate** (9/36 pe p1, 18/36 pe p2, 0/36 pe pagina 500)
   și eticheta `PRP:` e inconsistentă chiar în cadrul aceluiași câmp (4 din 9, 9 din 18).
   Câmpul e același; doar eticheta lipsește uneori.
5. **Adâncimea reală a lui itgalaxy (770 de pagini) nu se scanează**, `max_pages: 40` e
   buget, nu graniță — convenția otter.

---

## DEAL-D3 — lotul jucării + sneakers pe axa D (sonda LST-D3, 2026-09-07)

Sonda LST-D3 a triajat 12 domenii cu 44 de cereri. Runda asta scrie în registru cei cinci
care au trecut controlul, adaugă un gard în extracție și consemnează în `notes` motivul
fiecărei ieșiri. Zero cereri de rețea: tot ce intră, inclusiv paginarea, e măsurat pe
dump-urile sondei.

### 1. Cele 12 verdicte

| domeniu | verdict | în registru |
|---|---|---|
| carrefour.ro | CSS_GRID | **descriptor** |
| brickdepot.ro | CSS_GRID | **descriptor** |
| snipes.com | CSS_GRID | **descriptor** |
| sneakersnstuff.com | CSS_GRID | **descriptor** |
| footshop.ro | CSS_GRID | **descriptor** |
| lego.com | STATE (Apollo normalizat) | doar `notes` |
| flip.ro | STATE (array plat) | doar `notes` |
| nichiduta.ro | `entries` (17 fațete) | doar `notes` |
| jb-spielwaren.de | FĂRĂ_LISTARE pe intrarea găsită | doar `notes` |
| 43einhalb.com | CERE_MECANISM + 403 pe plast | doar `notes` |
| endclothing.com | JS_ONLY (Algolia) | doar `notes` |
| nike.com | POARTĂ | doar `notes` |

`listing_domains()`: 24 → **29**.

### 2. Cei cinci intrați

| domeniu | intrare | volum | paginare | referință | monedă |
|---|---|---|---|---|---|
| carrefour.ro | `/campanii/oferte-saptamanale` | 384/pagină | **niciuna** → `max_pages: 1` | 181/384, neetichetată | RON |
| brickdepot.ro | landing page de campanie | 91 (= „91 produse" anunțate) | niciuna | `normalprice`, 91/91 | RON |
| snipes.com | `/de-de/c/sale-660` | 24 | niciuna SSR | `Originalpreis`, 24/24 | EUR |
| sneakersnstuff.com | `/collections/sale` | 24/pagină | `?page={n}` | `s.price__original`, 24/24 | EUR |
| footshop.ro | `/ro/872-reduceri` | 24/pagină | `/page-{n}` | `oldPrice`, 24/24 | RON |

Trei lucruri care sunt decizii, nu descrieri:

* **carrefour e al doilea consumator al treptei `eu_sup`** (după evomag, DEAL-D2). Întregul
  și zecimalele stau pe noduri separate, fără separator, iar `_text_of` dă `8 79 LEI`.
  `eu_comma` ar citi 879.0 — pe 384 de carduri, un feed întreg de chilipiruri false.
  **Corecție la măsurătoarea LST-D3:** agregatul sondei raportase 70 de referințe „inversate
  sau egale" din 181; numărul era un artefact al comparatorului analizei, care nu cunoștea
  `eu_sup`. Recalculat corect: **181 de perechi, 0 inversate.**
* **brickdepot cere `us_dot` pe un magazin românesc.** `569.99Lei` are punct zecimal și
  niciun separator de mii; `eu_comma` ar da 56999.0. Exact ambiguitatea pe care DEAL-D1 a
  decis-o prin cheie declarată: din șir nu se poate deosebi.
* **footshop citește prețul de pe `strong`, nu de pe div-ul de preț.** Referința e imbricată
  în nodul de preț, deci textul div-ului conține ambele sume (`477 RON 529 RON` → 477529.0).

### 3. Cele două garduri — și ce s-a dovedit că nu era nevoie

**`href` cu spații: gard NOU, chiar necesar.** brickdepot randează ancora cardului cu un
spațiu literal după slash. Fără gard, URL-ul ieșea cu spațiul în el și ajungea așa în
`deals.url` și în orice fetch de refresh de pe axa L. `_link_of` codifică acum orice spațiu
interior ca `%20`, înainte de `urljoin`.

Nuanță măsurată, care contează: **caracterul din dump nu e `U+0020`, ci `U+00A0`** (spațiu
neseparator). O gardă scrisă doar pentru ` `, `\t`, `\n` ar fi lăsat neatins exact cazul care
a cerut-o. Clasa îl conține explicit. Toate variantele devin `%20` — strict vorbind, forma
UTF-8 a lui U+00A0 ar fi `%C2%A0`; alegerea lui `%20` e deliberată (un spațiu neseparator
într-un slug e o greșeală de redactare), dar **rămâne neverificată live**: runda n-a făcut
nicio cerere. Dacă un refresh pe brickdepot dă 404, acolo se uită.

**Imagini `data:`: gardul EXISTA deja, iar premisa era greșită.** Ipoteza de lucru era că
controlul LST-D3 numărase placeholderul lazy al lui carrefour ca imagine validă (384/384).
Verificat: `normalizeaza_imagine` respinge `data:` din IMG-1a (`v.lower().startswith("data:")`),
iar `_imagine_of` trece la `<img>`-ul următor. Controlul raportase deci URL-uri CDN reale, nu
placeholdere — nu era o slăbiciune. Măsurat pe toate cele 384 de carduri: 0 data-URI, 368 poze
de produs `cdn-media.carrefour.ro`, 16 bannere de campanie.

Mai mult: **gardul e redundant**. Un `data:image/gif;base64,…` e tăiat la prima virgulă
(logica de `srcset`), rămâne `data:image/gif;base64`, iar acela cade oricum pe ramura finală
„nici absolut, nici ancorat la rădăcină → None". Sabotajul care scoate gardul nu rupe niciun
test, și e corect că nu-l rupe. Testul `test_normalizeaza_imagine_respinge_data_uri` pinuiește
deci **comportamentul observabil**, nu linia de cod — ceea ce e oricum ce contează pentru
carrefour.

### 4. Decizia snipes: `Originalpreis`, nu `30-Tage-Bestpreis`

Pagina publică două referințe. `del.strikeout` poartă `Originalpreis 119,99 €` — prețul
original al magazinului. Separat, `<… class="lowest-prior-price">30-Tage-Bestpreis: 95,99 €</…>`
e un câmp Omnibus **real**, cu semantică `min30`.

Intră `Originalpreis`, din două motive: pe cardul măsurat valoarea lui `30-Tage-Bestpreis` era
**egală cu prețul de vânzare**, deci ca `compare_at` n-ar califica niciodată R1 (pragul cere
referință strict mai mare); iar `reference_kind` rămâne `nemarcat` tocmai fiindcă
`Originalpreis` **nu** e câmpul legal. Dacă David preferă semantica Omnibus, cheia e acolo și
se schimbă cu o linie — dar atunci axa D pe snipes ar trăi doar din R2.

### 5. Corecția senetic (din LST-D2)

Verdictul NEPOTRIVIT dat lui senetic.ro la LST-D2 s-a dat **pe carusel**. Validarea corecției
de carusel din LST-D3 a arătat că există și o grilă SSR în afara lui: `div.product-block`,
24 de produse, sub `div.category-filters-products__container`. Sonda LST-D2 o ratase fiindcă
ordona după număr, iar caruselul avea un exemplar în plus (25 vs 24).

Referința tot lipsește, deci axa D ar sta oricum doar pe R2. Verdictul se **re-măsoară**
într-o sondă; nu se rescrie de aici. Nota din registru spune asta.

### 6. Defectul `_PRET_TOKEN` al sondei — lecție pentru LST-D4

Detectorul grosier de preț al sondelor (moștenit din LST-D1 prin LST-D2 în LST-D3) are trei
găuri, toate lovind magazinele străine:

```
_PRET_TOKEN = r"\d[\d .,]*\s*(?:lei|ron|eur|€|\$|usd)\b|\b(?:lei|ron)\b\s*\d"
```

1. **simbolul înaintea sumei nu e prevăzut deloc** — `€ 159,95` (43einhalb) nu potrivește;
2. **`€\b` cere caracter de cuvânt DUPĂ simbol** — `95,99 €` la capăt de text (snipes) nu
   potrivește, fiindcă `€` nu e caracter de cuvânt;
3. **`£` nu e în listă** (endclothing).

Efectul măsurat: trei domenii au raportat „0 jetoane de preț" pe pagini pline de prețuri, au
cerut un `p1b` inutil fiecare și au sărit `prod1`/`prod2`. Analiza (cu `_PRET_RE`, care are
ambele ordini) a recuperat grilele din dump-urile salvate, deci s-au pierdut cereri, nu
măsurători.

Aceeași familie de greșeli: `\bLei\b` nu prinde `569.99Lei` (brickdepot), fiindcă între `9` și
`L` nu există graniță de cuvânt — reparat în analiza LST-D3 prin **adiacență de litere**
(`(?<![A-Za-z])lei(?![A-Za-z])`), lecția FBS-12.

Înainte de LST-D4: `_PRET_TOKEN` se înlocuiește cu forma din `analiza_*.py`.

### 7. Rămase în afară

| domeniu | motiv |
|---|---|
| lego.com | Navigația `/ro-ro/` n-are categorie de sale — doar pagina CMS `/ro-ro/page/lego-offers-promotions`, iar aceea e un carusel de 20 (20/20 sub `ol.Carousel_items__…`) peste un `__NEXT_DATA__` cu cache **Apollo normalizat**: valorile stau în intrări separate legate prin referințe. STATE, dar cere un resolver — mai mult decât o rundă de descriptori. |
| flip.ro | STATE, și cel mai curat din familie: `props.pageProps.dehydratedState.queries[0].state.data.data.productsPage`, array plat de 32 cu chei directe (`price`, `previousPrice`, `retailPrice`, `pdpUrl`, `imagePath`, `currency: "RON"`). Gradul e în `naming.title` ca sufix pe 32/32 și în `pdpUrl` ca `?shape=`. Capcană: `lowestPriceOfTheYear` e `false` pe 32/32 — constantă de șablon (lecția vivre). Candidat `state_extractor`. |
| nichiduta.ro | `/oferte-speciale` e hub: h1 de oferte, dar textul vizibil e meniul de categorii. Își expune însă 17 fațete `/<categorie>/produse-cu:reducere` — candidat pentru forma `entries`, al doilea caz după eMAG. Niciuna cerută încă. |
| jb-spielwaren.de | `/spezielle-lego-angebote-und-gwp/` e pagină de campanii: 2 jetoane de preț pe 236 KB, zero carduri, zero produse în stare. Nota LOT2 („LEGO retired + SALE") descrie o secțiune editorială. |
| 43einhalb.com | Citibil (preț plătit + tăiat cu etichetă `UVP` verbatim, paginare `/sale/page/{n}`), dar grila randează același produs de mai multe ori în variante responsive: **69 de `div.item-wrapper` pentru 16 URL-uri distincte**, 36 fără niciun `<a href>`. Un descriptor pe ele scotea 6 carduri cu 3 URL-uri — măsurătoare falsă care arăta a succes. În plus `page/500` → 403, `classify` → `BLOCKED`. |
| endclothing.com | JS_ONLY: `/eu/sale` răspunde 200 cu 1,5 MB și zero carduri; `__NEXT_DATA__`-ul de 1,37 MB n-are produse — cele 105 chei `price` sunt praguri de livrare din `config/shipping/methods`, iar singurele array-uri mari sunt arbori de categorii. `algolia` de 14 ori: produsele vin client-side. |
| nike.com | POARTĂ: `None` din poartă pe `/ro/w/promotional-styles-3vvvm`, dar cererea directă cu același profil a dat 200 (875 KB, titlu real) și `classify()` pe chiar acel corp întoarce `OK`. Al doilea caz după flanco. Afirmația SNK-2 (fără preț server-side pe listări) rămâne **netestată** — poarta n-a livrat corpul. |

### 8. Limitele oneste

1. **brickdepot intră fără imagini** (0/91). `src` e cale relativă fără slash inițial
   (`bmz_cache/…`), pe care normalizatorul o refuză deliberat: fără o bază măsurată n-are cum
   s-o rezolve, iar a ghici ar produce 404-uri tăcute. Nu e o alegere proastă de selector.
2. **URL-ul brickdepot e o CAMPANIE** („Până la 40% reducere…") și poate expira. Dacă un scan
   dă 0 carduri, intrarea se re-măsoară din navigația home-ului.
3. **`%20` pentru U+00A0 e neverificat live** (v. §3).
4. **`max_pages: 40` la footshop e pur buget:** `page-500` întoarce 24 de produse reale, deci
   oprirea nu s-a atins. La sneakersnstuff, în schimb, `?page=500` dă grila goală — oprire
   măsurată.
5. **16 din 384 de carduri carrefour** primesc un banner de campanie în loc de poza produsului.
6. **`/products.json` la sneakersnstuff n-a fost măsurat.** Dacă enumerarea Shopify e deschisă,
   `method: shopify` ar bate descriptorul (același caz ca sneakerindustry la SNK-1).
7. **Clasele cu hash de build** (carrefour `__BWFkK`/`__EvRr7`, footshop `_2egST`/`_1Go7D`/
   `_1NHjx`) se schimbă la fiecare deploy și n-au alternativă în dump. Dacă un scan dă 0
   carduri, se re-măsoară.

---

## GATE-1/GATE-2 — poarta re-cerea `Location`-ul literal (flanco 308 → www.flanco.ro:443 → challenge)

Două sonde independente (LST-D2 §3.12 pe flanco, LST-D3 §3.8 pe nike) raportaseră același
tipar: `_fetch_shop_url_guarded` întoarce `None` fără WARN, iar o cerere directă `curl_cffi`
cu ACELAȘI profil întoarce 200 cu pagina reală, pe care `classify()` o dă `OK`. Concluzia de
atunci — „cauza e în lanțul de hopuri al porții, nu în sit" — era pe jumătate adevărată, dar
mecanismul era altul decât se presupunea.

GATE-1 a măsurat poarta **din interior**, hop cu hop, fără s-o modifice.

### 1. Măsurătoarea (GATE-1, 5 cereri interne din 16)

| apel | hop | URL cerut | status | octeți | `Location` | header decisiv | `<title>` |
|---|---|---|---|---|---|---|---|
| `flanco_apex` | 1 | `https://flanco.ro/` | 308 | 1 463 | `https://www.flanco.ro:443` | `cf-cache-status: DYNAMIC` | `308 Permanent Redirect` |
| `flanco_apex` | 2 | `https://www.flanco.ro:443` | **403** | 5 767 | — | **`cf-mitigated: challenge`** | `Just a moment...` |
| `flanco_www` | 1 | `https://www.flanco.ro/` | **200** | 883 150 | — | **`cf-cache-status: HIT`**, `age: 6381` | `Flanco Smart Discounter…` |
| `nike_listare` | 1 | `…/ro/w/promotional-styles-3vvvm` | 200 | 875 548 | — | `cdn-cache; desc=REVALIDATE` | `UNLOCK 25% OFF. Nike RO` |
| `nike_home` | 1 | `https://www.nike.com/ro/` | 200 | 706 200 | — | `cdn-cache; desc=HIT` | `Nike. Just Do It. Nike RO` |

Ramura e **(d) ZID**, nu una dintre cele trei tăcute — și fiecare alternativă e exclusă
printr-o observație, nu prin raționament: niciun hop n-are excepție (a); hop 1 e 308 **cu**
`Location` (b); bucla a folosit 2 hop-uri din 4 și a ieșit prin `return None, rezultat`, nu
prin `return None, None`-ul de la capăt (c); allow-list-ul a dat `permis=True` pe ambele
URL-uri, inclusiv pe cel cu `:443` (e) — `parsed.hostname` taie portul.

Poarta clasifica deci **corect**. Ce lipsea era normalizarea URL-ului de hop: `Location`-ul
emis de sit e `https://www.flanco.ro:443` — **cale goală și port implicit scris explicit** —
iar `urljoin(current_url, loc)` pe un `Location` absolut întoarce exact șirul primit.

### 2. Corecția la concluzia LST-D2/LST-D3

Afirmația „poarta refuză o pagină pe care `classify` o dă OK" compara **două corpuri
diferite**. Cererea directă din sondele anterioare avea `allow_redirects=True`, deci curl
urma singur redirectul și `classify` vedea pagina finală de 881 KB. Poarta vede corpul
hop-ului 2 — pagina de challenge. `classify()` rulat offline pe **corpul porții** întoarce
tot `BLOCKED`. Nu există nicio divergență între poartă și clasificator; există o diferență
între ce URL ajunge să fie cerut.

| | cererea directă | poarta |
|---|---|---|
| `allow_redirects` | `True` (curl urmează singur) | `False` (hop-uri manuale) |
| URL cerut după 308 | normalizat de libcurl | **literal din `Location`** |
| cookie-uri între hop-uri | păstrate de curl în sesiune | **niciunul** (flanco/nike n-au jar) |
| corpul văzut de `classify` | pagina finală, 200 | pagina hop-ului care a oprit bucla |

### 3. Reparația (GATE-2)

`_normalizeaza_url_hop(url)` — funcție pură, RFC 3986 §6.2.3 — aplicată pe rezultatul lui
`urljoin`, deci și pe `Location` relativ, și pe cel absolut:

* schema și gazda în minuscule;
* cale goală → `/`;
* portul **implicit** șters (`:443` pe https, `:80` pe http); orice alt port rămâne;
* query, fragment și `userinfo` neatinse; **niciun caracter nu se codifică** aici (spațiile
  se codifică la intrare, `_fara_spatii`, DEAL-D3).

O singură linie schimbată în `_parcurge_hopuri`:

```python
current_url = _normalizeaza_url_hop(urllib.parse.urljoin(current_url, loc))
```

**Riscul pentru celelalte ~95 de domenii e mic, și se poate argumenta punctual.**
Normalizarea nu poate schimba gazda contactată, deci nu atinge decizia anti-SSRF:
`_is_allowed_shop_url` citește `parsed.hostname` și îl compară oricum cu `.lower()`, iar
verificarea allow-list se face **din nou**, la începutul hop-ului următor, pe URL-ul deja
normalizat. „Cale goală → `/`" nu schimbă nimic pe fir — linia de cerere HTTP poartă oricum
minimum `/`. Un test pinuiește invarianța verdictului allow-list pe un set care include cele
două forme înșelătoare din C-14 (sufix fals `evil-altex.ro.attacker.com` și `userinfo` care
imită un domeniu permis, `https://altex.ro@evil.com/`).

Nu s-au atins: `max_hops`, cookie-urile/jar-urile, `_impersonate_for`, `_clasifica_raspuns`,
ramura de excepție.

### 4. Verificarea funcțională (GATE-2, 1 apel de poartă, 2 cereri interne)

`_fetch_shop_url_guarded("https://flanco.ro/")` prin poarta REPARATĂ:

| hop | URL cerut | status | octeți | header decisiv |
|---|---|---|---|---|
| 1 | `https://flanco.ro/` | 308 | 1 463 | `cf-cache-status: DYNAMIC`, `Location: https://www.flanco.ro:443` |
| 2 | **`https://www.flanco.ro/`** (normalizat) | **200** | **883 150** | `cf-cache-status: HIT`, `age: 7339` |

`_clasifica_raspuns` → `OK`, poarta întoarce răspunsul (`poarta_none = False`), zero jar-uri
scrise. Situl emite în continuare `Location`-ul nenormalizat; poarta nu-l mai re-cere ca atare.

Mărimea corpului e identică la octet cu cea măsurată la GATE-1 pe `flanco_www` (883 150) —
o verificare încrucișată gratuită că e aceeași pagină.

### 5. Ce rămâne neexplicat

* **nike.com nu reproduce.** GATE-1 i-a cerut listarea și home-ul: 3 × 200, fiecare dintr-un
  singur hop. `None`-ul din LST-D3 a fost **tranzitoriu** și nu se repară pe baza unei
  observații care nu se repetă. Ce diferă față de atunci: ora și, probabil, reputația IP-ului
  la Akamai. Ce nu diferă: profilul (`chrome`), URL-ul, lipsa jar-ului.
* **Ipoteză pentru blocaje intermitente, notată dar nemăsurată:** răspunsurile nike setează
  **14 cookie-uri** (`ak_bmsc`, `AKA_A2` ×6, `geoloc`, `rc`, `tp`, `tz`, `la`, `lo`, `ni_d`)
  — Akamai Bot Manager. Poarta le aruncă pe toate, fiindcă `jar_pentru("nike.com")` e `None`.
  Aici n-a contat (un singur hop, 200 din prima), dar pe lanțuri mai lungi sau la cereri
  repetate e un mecanism plauzibil.
* **Care dintre cele două variabile declanșa challenge-ul** (calea goală sau portul explicit)
  rămâne nedeterminat: GATE-1 avea o singură observație per formă, iar o a cincea cerere era
  în afara bugetului. Normalizarea le acoperă pe amândouă, iar ambele sunt no-op-uri standard,
  deci reparația e sigură fără să fie nevoie de separarea cauzelor. GATE-2 arată însă că, pe
  forma normalizată, flanco răspunde 200 prin poartă — deci reparația chiar rezolvă cazul.
* **Challenge-urile Cloudflare au și o componentă nedeterministă.** Două observații nu
  dovedesc un mecanism; `cf-cache-status: HIT` pe una și `cf-mitigated: challenge` pe cealaltă
  sunt însă două semnale independente care merg în aceeași direcție, iar GATE-2 adaugă o a
  treia observație pe forma normalizată (tot HIT, tot 200).

---

## DEAL-D4 — lotul fashion + beauty pe axa D (sonda LST-D4, 2026-09-08)

Al patrulea val al axei D, transcris din raportul LST-D4
(`backend/scripts/diagnostics/dumps_lstd4/raport.md`, §3.1–3.16 și §4). Cei 11 descriptori
de mai jos trecuseră deja prin `extrage_carduri()` real acolo; runda a adăugat fixture-uri,
teste, o cheie nouă și **trei cereri live** pentru ce rămăsese nemăsurat.

**Cifra: `listing_domains()` 29 → 40.**

### Cele 16 verdicte ale sondei

| domeniu | verdict | intrat pe axa D |
|---|---|---|
| zalando.ro | CSS_GRID | **DA** |
| aboutyou.ro | CSS_GRID | **DA** |
| answear.ro | FĂRĂ_LISTARE | nu |
| fashiondays.ro | CSS_GRID | **DA** |
| epantofi.ro | CSS_GRID | **DA** |
| spartoo.ro | CSS_GRID | **DA** |
| officeshoes.ro | CSS_GRID | **DA** |
| prm.com | CSS_GRID + STATE | **DA** |
| trendyol.com | JS_ONLY | nu |
| asos.com | CSS_GRID pe vitrină GBP | nu |
| notino.ro | CSS_GRID | **DA** |
| douglas.ro | CSS_GRID | **DA** |
| marionnaud.ro | STATE | nu |
| parfumdreams.de | CSS_GRID | **DA** |
| nichiduta.ro | CSS_GRID + `entries` | **DA** |
| jb-spielwaren.de | FĂRĂ_LISTARE | nu |

### Cei 11 intrați

| domeniu | intrare | volum / pagină | paginare | referință | monedă |
|---|---|---|---|---|---|
| zalando.ro | `/sale/?sale=true` | 24 | **niciuna** (`max_pages: 1`) | min30 pe 3/24 | RON |
| aboutyou.ro | `/c/femei/sale-32543` | 30 | niciuna | min30 pe 30/30 | RON |
| fashiondays.ro | `/s/sale-sale-sale-w` | 90 (6993 total) | `?page={n}`, 404 la coadă | min30 pe 90/90 | RON |
| epantofi.ro | `akcja:extraseptember_lp` | 76 | `?p={n}`, 404 la coadă | min30 pe 28/76 | RON |
| spartoo.ro | `/pantofi-ieftina.php` | 144 | niciuna | nemarcat pe 144/144 | RON |
| officeshoes.ro | `/sale` | 48 | infinite scroll | nemarcat pe 48/48 | RON |
| prm.com | `/ro/s/final-sale` | 80 | `?page={n}`, **500** la coadă | nemarcat pe 34/80 | RON |
| notino.ro | `/shopping-days/` | 28 | niciuna | **fără** | RON |
| douglas.ro | `/ro/c/reduceri/05` | 48 | `?page={n}`, **fără oprire** | min30 pe 47/48 | RON |
| parfumdreams.de | `/Angebote` | 30 (449 total) | `?p={n}`, grilă goală | prp pe 30/30 | EUR |
| nichiduta.ro | **`entries` × 17** | 60/fațetă | infixată, doar 2 fațete | **fără** | RON |

### Cele trei cereri live

| cerere | rezultat | ce a decis |
|---|---|---|
| `nichiduta …/carucioare-2-in-1/p2/produse-cu:reducere` | 200, **60 de carduri, 0 comune cu p1** | paginarea infixată e reală; template-ul intră |
| `nichiduta …/p500/…` | 200, 60 de carduri, **40 comune cu p1** | **NU e o oprire** — v. mai jos |
| `epantofi /c/epantofi/akcja:new_sale` | **404**, 0 carduri | analogia modivo NU se transferă; rămâne campania |

**A treia formă de „sfârșit de paginare" care nu e un sfârșit.** Pe nichiduta, o pagină peste
adâncimea reală a fațetei nu dă 404 și nu dă grilă goală: magazinul **aruncă fațeta** și
servește categoria întreagă. Măsurat pe `p500`: răspuns 200, 60 de carduri, `canonical` devine
`/carucioare-copii/carucioare-2-in-1/` (fără `produse-cu:reducere`), `<h1>` pierde „Cu
Reducere", iar numărul de produse sare de la **201 la 520**. Cardurile alea sunt produse
NEREDUSE, iar scannerul nu le poate deosebi: clamp-ul lui cere ca pagina să fie *submulțime* a
celor deja văzute, și aici 20 din 60 sunt noi.

Consecința în registru: descriptorul are `max_pages: 1`, iar **doar cele două fațete cărora
li s-a măsurat adâncimea** paginează, cu plafon propriu — `carucioare-2-in-1` (201 produse, 4
pagini) și `perne-de-alaptat` (134 produse, 3 pagini), citite din widget-ul de paginare al
fiecăreia. Celelalte 15 stau pe o pagină până când cineva le măsoară volumul.

### `title_from: "link_title"` (cheia nouă a rundei)

officeshoes are, pe card, două ancore: prima e **sigla mărcii**
(`<a class="logo" href=".../branduri/calvin-klein">`), a doua e produsul
(`a.send-search`). Un `link: "a"` scotea 48 de carduri cu 10 URL-uri distincte — o măsurătoare
falsă care arată exact ca duplicatele responsive. Iar ancora corectă **n-are text**, doar un
`<img>`: numele complet stă în `title="Calvin Klein Pantofi sport Kobe M 1C"`, în timp ce
`h2.product_list_title` dă doar modelul, fără marcă.

`_titlu_of` primește deci a doua valoare de `title_from`, lângă `link_aria_label` (caseking).
Fallback-ul e deliberat: dacă atributul dispare la un deploy, titlul cade pe selectorul
`title` — se pierde marca, nu produsul. Garda descriptorilor pinuiește acum mulțimea
`{link_aria_label, link_title}`: o valoare necunoscută ar cădea TACIT pe `title`.

### Referința: trei decizii care nu se citesc din formă

* **aboutyou** — cardul poartă „Preț original: 489,00 lei" (PRP) **și** „Ultimul preț minim:
  218,61 lei" (Omnibus). Se citește Omnibus-ul. Fixture-ul a scos la iveală și un bug:
  pe cardurile unde prețul curent e sub minim, nodul de valoare are doi copii
  (`<span><s>70,32 lei</s></span><span> -2%</span>`), iar fără `> span:first-child`
  `_pret_eu_comma` lipea cifra procentului — **70.322 în loc de 70.32**. Controlul LST-D4 se
  uitase doar la primul card, unde nodul e simplu.
* **douglas** — „PRP 798,00 RON" + „453,00 RON" + „Cel mai mic preț din ultimele 30 de zile
  429,00 RON", toate etichetate. Se citește Omnibus-ul. Al patrulea preț de pe card,
  `price-base-unit` („5,66 RON / 1 ml"), NU se citește.
* **prm** — „Preț normal: 94,90 LEI" e referința; fraza „Cel mai mic preț **de la lansare**"
  de pe același card **nu e Omnibus** (nu e „în ultimele 30 de zile"), deci `reference_kind`
  rămâne `nemarcat`.

Și două absențe deliberate: **notino** n-are `compare_*` fiindcă al doilea preț de pe card e
un CUPON („2.362 RON folosind codul shoppingdays"), nu o referință tăiată; **nichiduta** n-are
`compare_*` fiindcă prețul tăiat e text DIRECT al lui `div.prices`, fără nod propriu. Ambele
rafturi sunt R2-only.

### Formele noi de paginare

* **infixată** — nichiduta pune numărul la MIJLOC:
  `/carucioare-copii/carucioare-2-in-1/p2/produse-cu:reducere`.
* **redirect la pagina 1** — zalando (`/sale/2/` și `/sale/500/` → `/sale/`) și douglas
  (`?page=500` → pagina 1). Dovedit prin intersecția identităților de card, nu prin numărare:
  la zalando p1 ∩ plast = 24/24, la douglas 48/48. La zalando raftul nici măcar nu e stabil
  între două cereri (19 din 24 comune între p1 și p2), deci `max_pages: 1`; la douglas
  paginarea e reală (p1 ∩ p2 = 0), dar fără nicio semnătură de oprire — `max_pages` e plafon
  DUR, pinuit de test.

### Ce face scannerul pe 5xx (contează pentru prm)

`_scaneaza_domeniu` tratează ca **sfârșit de paginare doar 404**, și doar pe o pagină > 1 a
unei intrări care a citit deja cel puțin o pagină. Orice alt status non-200 — inclusiv 5xx —
ridică `RuntimeError`, iar excepția cade **înainte de `db.commit()`**: se pierde tot scanul
domeniului, consemnat în `ShopScanState`. Comentariul din cod e explicit („DOAR 404. Un 403
sau un 5xx e zid ori defecțiune și trebuie să se vadă ca eroare").

Pentru prm asta e o plasă, nu o problemă rezolvată: coada listării dă **HTTP 500**, deci dacă
`/ro/s/final-sale` are mai puțin de 25 de pagini, primul scan care trece de ea va eșua
ZGOMOTOS. E de preferat unei erori tăcute, dar cere măsurarea adâncimii reale la o rundă
viitoare.

### Rămase în afară, cu motivul

* **answear.ro** — home-ul are 219 de ancore și un nav de catalog complet, dar niciuna nu
  poartă `reduceri|sale|outlet`. Singura campanie, `/s/back-to-school` („până la -25%"), ar fi
  ieșit dacă lista de cuvinte a sondei ar fi conținut `procent`. Deci „nicio candidată sub
  lista de cuvinte", nu „magazinul n-are reduceri".
* **trendyol.com** — JS_ONLY. Candidata din home a fost un BANNER, nu o ancoră de navigație;
  pagina de campanie are 0 jetoane de preț, 0 carduri și 0 colecții de produse în starea din
  corp. O CATEGORIE (nu o campanie) rămâne nemăsurată.
* **asos.com** — grila e curată (`li.productTile_U0clN`, 72 de plăci, paginare `?page={n}`
  reală), dar servește **GBP** pe 72 din 72, iar locala validată pe axa L e
  `store=ROE&currency=EUR&country=RO`, prin API-ul public `stockprice`. Lipsește doar
  comutatorul de magazin; până atunci ar fi alt magazin.
* **marionnaud.ro** — STATE. În DOM există doar 15 elemente cu link și preț, și alea sunt bara
  de NAVIGAȚIE; raftul e în `searchModel.products` (20 pe pagină, 834 în total). Candidat
  pentru un `state_extractor`.
* **jb-spielwaren.de** — FĂRĂ_LISTARE, confirmat a doua oară cu cuvinte extinse
  (`restposten|auslaufartikel|%`) pe un home proaspăt de 428 de ancore. plentyShop marchează
  produsele cu `storeSpecial: Sonderangebot` în DATE, dar magazinul nu expune o categorie de
  oferte în navigația server-side.

Separat, o **corecție de monedă** la nota DEAL-D3 a lui endclothing: dump-ul aceleiași pagini,
recitit cu un jeton de preț care cunoaște toate monedele, arată `RON972` / `RON294` — pagina
servea RON, nu GBP. Verdictul JS_ONLY nu se schimbă (DOM-ul e gol), doar moneda din notă.

---

## DEAL-D5 — coada axei D (sonda LST-D5, 2026-09-08)

Ultimul lot al axei D: 10 domenii triate cu 27 de cereri, plus 3 cereri de bisecție. Doar
**două** au trecut — cel mai mic randament al axei, și motivele sunt informative în sine.

### Verdictele

| domeniu | verdict | de ce |
|---|---|---|
| **action.com** | **CSS_GRID → în registru** | 23 de carduri/pagină, referință tăiată pe 23/23 |
| **senetic.ro** | **CSS_GRID → în registru** | grilă SSR de 24; verdictul DEAL-D2 fusese dat pe carusel |
| trendyol.com | CERE_MECANISM | categoria poartă `ld+json ItemList` cu 36/36 prețuri RON |
| foto-erhardt.com | NEPOTRIVIT | bucăți unice second-hand, 0/155 prețuri tăiate |
| alternate.de | FĂRĂ_LISTARE | `/Angebote` hub editorial, `/Outlet` carusel de 15 |
| reichelt.de | JS_ONLY | `landingpage/-2568`: 214 KB, 0 linkuri de produs |
| flanco.ro | FĂRĂ_LISTARE | singura candidată = regulamente; zero „resigilat" pe home |
| hornbach.ro | FĂRĂ_LISTARE | 171 de ancore, 0 candidate — nav client-side |
| biciclop.eu | FĂRĂ_LISTARE | produse cu `-51%` pe home, dar niciun raft adresabil |
| computeruniverse.net | **POARTĂ** | poarta noastră refuză; direct dă 200/1,1 MB |

### Bisecția adâncimii pe action.com

`?page=500` întoarce **pagina 1**, nu 404 — deci nu există semnătură de oprire, iar
`max_pages` trebuie măsurat. Trei cereri, fiecare la 90 s impuși de
`min_fetch_interval_s` (poarta doarme singură în `_asteapta_intervalul`; sonda a
măsurat, n-a ocolit):

| cerere | rezultat | pagina activă | carduri | interval real |
|---|---|---|---|---|
| `?page=6` | conținut NOU | 6 | 18 | — (prima) |
| `?page=12` | **CLAMP** | 1 | 23, subset al p1 | 90,5 s în poartă |
| `?page=7` | **CLAMP** | 1 | 23, subset al p1 | 90,8 s între plecări |

Ultima pagină cu conținut nou = 6 → **`max_pages: 7`**, unde plusul e chiar pagina care
confirmă clamp-ul, plătită o dată per scan de garda `linkuri_pagina <= linkuri_vazute` din
`_scaneaza_domeniu`. Verificare independentă, gratuită: 5 pagini pline × 23 + 18 pe ultima =
**133**, exact totalul anunțat pe pagina 1 („133 rezultate"). Paginatorul arată `1..6` și pe
p1, și pe p2 — nu e fereastră glisantă, ceea ce a făcut din `?page=7` alegerea cu cea mai mare
informație pentru a treia cerere.

Plafonul e mic și din **cost**: la 90 s/pagină, un scan plătește `max_pages × 90 s`, adică
~10 minute pe acest domeniu.

### Forme noi, de reținut

**Plafonare la pagina 1 vs la ultima pagină.** Amândouă întorc 200 cu carduri, deci niciuna nu
seamănă cu o oprire. action duce `?page=500` la **pagina 1** (URL final fără query, aceleași 23
de URL-uri, corp byte-identic) — periculoasă, fiindcă fără `max_pages` un scanner ar re-citi
pagina 1 la nesfârșit dacă n-ar avea garda de clamp. foto-erhardt duce `/500` la **pagina 10**,
ultima (paginator activ 10, `canonical` și `h1` neschimbate) — prietenoasă, fiindcă adâncimea
se citește direct din paginator. A treia formă, deja cunoscută, e 404 la coadă.

**Cardul care E ancora — punct orb al sondelor.** La foto-erhardt cardul e chiar
`<a class="product product--used">`, iar atât sonda cât și analiza cer o ancoră **descendentă**
(`find_all` nu se întoarce pe sine). Rezultatul a fost „0 carduri" pe o pagină cu 36 de produse,
o cerere irosită și un verdict automat de oprire greșit. La action același tipar n-a costat
nimic, doar fiindcă ancora are întâmplător un părinte cu `data-testid`. Mecanismul care ar
închide golul e `link: "@self"` — simetricul lui `@parent_a`, câteva linii; simulat cu un shim
peste `_link_of`, ar da 35/36/17/48 de carduri curate. **Nu e implementat**: foto-erhardt rămâne
oricum NEPOTRIVIT, deci mecanismul trebuie plătit de un domeniu care chiar are nevoie de el.
Două domenii din zece au forma asta — merită numărat câte din cele 42 cu `listing` o au, înainte
ca al treilea să coste iar cereri.

**Sloganul care seamănă cu Omnibus.** „Întotdeauna cel mai mic preț" apare de 6 ori pe pagina
lui action, în antet și în teaserul de aplicație. Detectorul n-a numărat niciuna, fiindcă
lucrează **pe card**, nu pe pagină — regula scrisă la LST-D4 și-a arătat valoarea aici. Pe
listare referința există totuși, tăiată și neetichetată: `reference_kind: nemarcat`.

**Preț pe unitate, a doua oară.** După `price-base-unit` la douglas (DEAL-D4), action pune
„16,04 lei/kg" într-un câmp care arată exact ca un preț de card
(`product-card-price-description`) și diferă de cel plătit pe **7 din 12** carduri verificate.
Nu se citește; prețul plătit e spart pe două noduri și cere `eu_sup`.

**Net vs brut.** senetic scrie amândouă prețurile pe card, etichetate: `.price-net` „921,49 RON
fara TVA" și `.price-gross` „1 115,00 RON cu TVA", pe 24/24. Pe axa D se ia brutul — netul ar
raporta cu ~19% mai puțin pe tot raftul. Numele claselor explică și divergența față de nota
DEAL-D2: **caruselul** folosește `price_our_net`/`price_our_gross`, **grila** folosește
`price-net`/`price-gross`; în cele 24 de `div.product-block` există 24 din fiecare și zero
`price_our_*`. Cele două runde măsuraseră zone diferite ale aceleiași pagini.

### Rămase în afară, cu ce ar cere fiecare

* **trendyol.com** — verdictul JS_ONLY de la DEAL-D4 se **nuanțează, nu se răstoarnă**: el a
  fost dat pe o *campanie* din banner, și acolo rămâne valabil. O *categorie* din nav
  (`/ro/rochii-x-c56`, `/ro/bluze-x-c1019`) poartă `ld+json` `ItemList` cu 36 de produse
  complete server-side, 36/36 cu `offers.price` și `priceCurrency: RON`, formă identică pe
  amândouă. Mecanismul candidat: **listare din `ItemList`**, ruda `state_extractor`-ului.
  Rezerve măsurate: `numberOfItems` anunță 156 754 dar lista poartă 36 (prima pagină), `offers`
  n-are preț de referință (deci R2), iar categoriile sunt catalog întreg, nu listări de
  reduceri — fațeta de reducere rămâne nemăsurată.
* **computeruniverse.net** — **GATE-3**. Poarta întoarce `None`, cererea directă pe același hop
  (`allow_redirects=False`, lecția GATE-1) dă 200 cu 1,1 MB și titlu real, iar `classify()` pe
  corp dă `OK`. Corpul n-are niciunul dintre cei doi markeri WAF, domeniul n-are
  `block_markers`, n-a existat redirect, profilul `impersonate` a fost identic. Cauza **nu e
  stabilită** — cere o sondă hop-cu-hop, adică a treia rundă la rând în care poarta e subiectul
  măsurătorii.
* **senetic.ro**, ca material viitor: 6 sub-categorii de outlet cu numere anunțate
  (`outlet-computer-equipment-9315` 39, `outlet-accesorii-9317` 34, `outlet-reelistic-9313` 24,
  `outlet-electrocasnice-24919` 10, `outlet-servers-and-storage-9314` 3,
  `outlet-power-solutions-9318` 2) — materia pentru o formă `entries` dacă paginarea rămâne
  negăsibilă. Nemăsurate: niciuna n-a fost cerută.

---

## STATE-1 — flip.ro și marionnaud.ro pe axa D prin extractoare de stare; 5xx la pagina > 1

Două domenii care așteptau de trei runde („candidat `state_extractor`") intră acum pe axa D,
plus o robustețe în scanner măsurată la DEAL-D4. Familia `state_extractor` ajunge la **șase**,
iar axa D la **44** de domenii.

### 5xx la pagina > 1 = sfârșit de intrare, nu scan pierdut

Regula veche era „DOAR 404 e tolerat; un 403/500 pe pagina 2 e un zid sau o defecțiune".
Semantica era corectă — un 500 chiar nu e un sfârșit de paginare — dar prețul era greșit:
`RuntimeError` cade **înainte** de `db.commit()`, deci un singur 500 la pagina 30 arunca și
cele 29 de pagini deja citite. prm servește exact așa (HTTP 500 la coada listării, măsurat la
LST-D4), iar cu 44 de domenii pe axă un 5xx tranzitoriu nu mai e o ipoteză.

Acum, pe pagina > 1 a unei intrări care a citit deja cel puțin o pagină, **orice** non-200
(5xx, 403, 429, sau `None` din poartă) încheie *intrarea*, lasă comis ce s-a citit și trece la
intrarea următoare, cu un `logger.warning`. Două granițe rămân neatinse: pe **pagina 1** orice
non-200 ridică în continuare (acolo înseamnă intrare moartă, care trebuie să se audă), iar
**404** rămâne oprire **tăcută**. Diferența dintre cele două ramuri e tocmai zgomotul: un 500 e
o anomalie a magazinului și merită o linie în log, un 404 e finalul normal al paginării.

### flip.ro — `__NEXT_DATA__`, cache de react-query

Calea, verbatim: `props.pageProps.dehydratedState.queries[*].state.data.data.productsPage` —
array plat, 32 de obiecte, `total: 604`. Cheile unui produs:

| cheie | valoare | ce facem |
|---|---|---|
| `price` | `1429.99` | prețul plătit |
| `retailPrice` | `2250` | **referința**: prețul unității NOI a aceluiași model |
| `previousPrice` | `1429.99` | **egal cu `price` pe 32/32** — NU se citește |
| `lowestPriceOfTheYear` | `false` | constant pe 32/32 — NU se citește |
| `naming.title` | „Apple iPhone 13, Midnight, 128 GB, Excelent" | gradul vine gratis în titlu |
| `pdpUrl` | absolut, cu `?shape=Excelent` | identitate exactă |
| `imagePath` | absolut, pe `cdn.flip.ro` | imaginea |

Trei decizii, fiecare plătită de o măsurătoare:

1. **Query-ul se alege după conținut, nu după indice.** `queries` are două elemente; al doilea
   (`plp-promotional-cards`) are `state.data` None. Azi indicele 0 ar nimeri, dar ordinea unui
   cache de react-query nu e un contract, iar ziua în care se inversează n-ar da o eroare — ar
   da zero produse, adică „magazinul n-are reduceri".
2. **`previousPrice` nu e referință** (capcana constantei, lecția vivre). Citit ca `compare_at`,
   ar produce reduceri de 0% pe tot catalogul.
3. **`compare_at = retailPrice` doar când e > `price`.** `retailPrice` există pe 32/32 dar e mai
   mare decât prețul doar pe 27/32 — restul au `retailPrice: 0`, deci fără gardă ar fi ieșit o
   „reducere" de la zero. Semantica („prețul unității NOI") e aceeași cu „NOU" la eMAG și „Nou:"
   la altex, de unde `reference_kind: nemarcat`, nu `min30`.

**Identitatea include query-ul.** Registrul spunea deja `url_identity: "exact"` (LOT1): starea
unității — `?shape=Excelent` — face parte din identitate, iar același model în două grade are
**aceeași cale** și două prețuri. `_external_id` hashează doar calea, pe bună dreptate pentru
restul axei, deci extractorul îl recalculează local pe cale + query. Fără asta, cele două grade
ar primi același id și al doilea ar fi sărit de garda SCAN-1 — jumătate de catalog dispărută
tăcut. Pe pagina măsurată cele 32 de căi sunt distincte, deci coliziunea nu se vede pe o
singură pagină; ea apare între cele 19.

### marionnaud.ro — `<script type="application/json">` (SAP Commerce/Spartacus)

Pagina are **un singur** bloc `application/json`, **fără** atribut `id`, iar `searchModel` nu e
la rădăcină: calea verbatim e `$["e2-breadcrumb-pageBreadCrumbs$"].searchModel.products`. Cheia
aia e un ID de componentă CMS, deci extractorul caută `searchModel` în adâncime în loc să lege
un literal fragil. Cheile unui produs:

| cheie | valoare | ce facem |
|---|---|---|
| `price.value` | `374` (numeric) | **prețul** |
| `price.formattedValue` | `"374,00 RON"` | NU se citește — numărul există deja |
| `url` | `/lancome/…/p/BP_45540` | **relativ**, se rezolvă la rădăcină |
| `images.PRIMARY.list.url` | absolut, pe `media.marionnaud.ro` | imaginea |
| `code`, `name`, `masterBrand.name` | `BP_45540`, „La Vie est Belle Apa de Parfum", „Lancôme" | — |

**Referința lipsește, măsurat pe 20/20:** `otherPrices` e listă goală, `otherPricesMap` gol,
`priceRange` gol, `price.savePrice` e șirul vid. Există `promotions` pe 20/20, dar recompensa e
un **procent** („33%"), nu un preț anterior — iar dintr-un procent nu se reconstituie prețul
vechi fără să presupui baza de calcul. Deci fără `compare_at`, `reference_kind: nemarcat`,
axa D doar pe R2. O rezervă de semantică, consemnată fiindcă se vede în date: `priceType` are
două valori, iar `FROM` înseamnă „de la" — prețul celei mai ieftine variante de gramaj.

### Paginarea, măsurată live (4 cereri)

| cerere | status | carduri | noi față de p1 | concluzie |
|---|---|---|---|---|
| flip `?page=2` | 200 | 32 | **30** | `?page={n}` **e onorat** |
| flip `?page=500` | 200 | **0** | 0 | **grilă goală** = oprire curată |
| marionnaud `?page=1` | 200 | 20 | 1 | `currentPage: 0` — **parametru ignorat** |
| marionnaud `?page=500` | 200 | 20 | 1 | `currentPage: 0` — același set |

**flip**: `?page=2` schimbă `queryKey`-ul stării în `limit=32|offset=32` — dovada că parametrul
se traduce în offset. `?page=500` întoarce 200 cu grila goală, deci oprirea e curată și nu
depinde de un plafon ghicit; `max_pages: 19` vine din `total`/`pageSize` (604/32), iar `total`
însuși driftează (577 la măsurătoarea live — stoc de refurbished).

**marionnaud**: paginarea din stare e **zero-indexată** (`currentPage: 0`, `totalPages: 42`),
dar parametrul `?page=` e **ignorat server-side** — și `?page=1`, și `?page=500` întorc
`currentPage: 0` și exact același set de 20 de produse. Restul celor 42 de pagini se aduc
client-side, după hidratare, prin API-ul Spartacus. De aceea `max_pages: 1` și **fără**
template: un `?page={n}` ar cere 41 de pagini identice cu prima și le-ar tăia abia garda de
clamp, după ce le-a descărcat pe toate.

## JSON-0/STATE-2 — lotul „API" era SSR: altex/mediagalaxy la adâncime prin stare, sportvision și booztlet pe CSS

Runda JSON-0 a pornit de la o ipoteză și a infirmat-o. Șase domenii validate pe axa L aveau
listări pe care HTTP-ul nu le vedea — paginare client-side, grile goale, RSC fără produse — și
explicația de lucru era că produsele vin dintr-un apel XHR. Sonda a deschis fiecare domeniu
într-un browser real, cu captura de rețea pornită, și a înregistrat tot ce a cerut pagina
singură.

**Rezultatul: 640+ răspunsuri, 123 XHR/fetch, ZERO apeluri de listare.** Niciunul dintre cele
șase nu-și aduce produsele prin API.

| domeniu | încărcări | XHR | apel de listare | verdict JSON-0 |
|---|---|---|---|---|
| altex.ro | 3 încercări, **0 pagini** | 0 | — | NEMĂSURAT — `ERR_HTTP2_PROTOCOL_ERROR` de 3× |
| sizeer.ro | 2 | 0 | — | BLOCAT — 403 Akamai |
| sportvision.ro | 1 | 18 | **niciunul** | FĂRĂ API — 24 de produse SSR |
| booztlet.com | 4 | 36 | **niciunul** | FĂRĂ API — 86 de produse SSR |
| bstn.com | 1 | 0 | — | BLOCAT — 403 tăcut |
| sivasdescalzo.com | 1 | 4 | — | BLOCAT — Cloudflare Turnstile |

Ce a găsit în loc, pe altex și mediagalaxy: produsele erau **de la început în același răspuns**
pe care îl descărcam oricum, în `__NEXT_DATA__`, împreună cu URL-urile **tuturor** paginilor.
Nu era nevoie nici de API, nici de browser — doar de citit altă parte a paginii. STATE-2 le-a
cablat, și a măsurat live restul.

### Cele trei capcane ale stării altex

**1. Semantica prețurilor e inversată față de nume.** `price` NU e prețul plătit: e prețul
unității NOI a aceluiași SKU, exact ce DOM-ul etichetează „Nou:" și ce descriptorul CSS de la
DEAL-D2 citea drept `compare_text`. Prețul plătit e `lowest_price`, cel afișat ca
„de la 1.919,92 lei". Deci `price ← lowest_price`, `compare_at ← price`. Un mapper care ar lua
`price` drept preț plătit ar raporta prețul de nou pe tot catalogul — adică ar rata fix
reducerea pentru care există scanul.

**2. URL-ul se compune cu `sku`, nu cu `id`.** Ancorele reale sunt
`/laptop-msi-modern-15-…/cpd/LAP9S715S121071/#resigilate`. Prima variantă a controlului JSON-0 a
folosit `id`-ul numeric (844256) și a raportat liniștit **„48/48 carduri complete"** — cu toate
cele 48 de URL-uri greșite, fiindcă un control de completitudine se uită doar dacă URL-ul e
nevid. Proba tare a fost comparația cu ancorele din DOM: cu `sku`, **48/48 coincid exact**.
Lecția e mai generală decât cazul: *un control care numără câmpuri nevide nu validează
conținutul lor* — are nevoie de o a doua sursă cu care să se confrunte.

**3. Imaginea — o cerere care a schimbat răspunsul.** JSON-0 observase că starea dă
`/media/catalog/product/m/o/<nume>.jpg`, iar DOM-ul servește
`https://lcdn.altex.ro/resize/media/catalog/product/m/o/<hash>/<nume>` — un segment de hash în
plus, absent din obiectul produsului — și a concluzionat că imaginea „nu se poate compune".
STATE-2 a cheltuit o cerere ca să **verifice în loc să deducă**:

```
https://lcdn.altex.ro/media/catalog/product/m/o/modern_15_f13mg_071xro_01_24e97af1.jpg
-> 200, content-type: image/jpeg, 95.192 octeți
```

CDN-ul servește calea din stare direct; segmentul cu hash e doar varianta redimensionată pe care
o cere DOM-ul. `image_url` a trecut deci de la „None, documentat" la o valoare reală, pe 48/48.

### Un extractor, doi frați

DEAL-D2 măsurase frăția altex↔mediagalaxy pe DOM (Jaccard 1.000 pe clasele cardului). JSON-0 a
măsurat-o și pe stare — aceeași cale de chei, același `id: 844256` la aceleași prețuri — iar
STATE-2 a confirmat-o live pe pagina 2. Gazda și CDN-ul se citesc din
**`runtimeConfig.settings`** (`baseUrl`, `cdn`), nu din cod, deci un singur `altex_next` acoperă
ambele vitrine. Corecție de traseu, consemnată fiindcă e ușor de greșit: `settings` **nu** stă
sub `initialReduxState`, cum sugerează vecinătatea din pagină, ci sub `runtimeConfig`, frate cu
`props`. O cale greșită ar fi făcut extractorul să cadă tăcut pe rezervă și să lege produsele
mediagalaxy de gazda altex — carduri perfect valide la vedere, care duc în alt magazin.
Gateway-urile diferă și ele (`fenrir.altex.ro` vs `cerberus.mediagalaxy.ro`) — pistă
neexplorată, dar orice mecanism care le-ar folosi trebuie să le citească din pagină.

### Cele 8 cereri de verificare (7 consumate, 1 rezervă nefolosită)

| # | cerere | status | rezultat |
|---|---|---|---|
| 1 | altex `/resigilate/filtru/p/2/` | 200 | **48 de carduri**, 46 noi față de p1 |
| 2 | altex `/resigilate/filtru/p/500/` | **200** | **grilă goală** — `products: []`, `pagination: []`, `<h1>` neschimbat |
| 3 | mediagalaxy `/resigilate/filtru/p/2/` | 200 | 48 de carduri, toate pe gazda `mediagalaxy.ro` |
| 4 | sportvision `/produse/noua-colectie` (HTTP) | 200 | **24 `div.product-item`** — identic cu browserul |
| 5 | sportvision `…/page-2` | 200 | 24 de carduri, **0 comune** cu p1 |
| 6 | booztlet `/eu/en/women/view-all` (HTTP) | 200 | **86 `[data-product-id]`** — identic cu browserul, NU e cochilie |
| 7 | altex `{cdn}{image}` | 200 | `image/jpeg`, 95.192 B — imaginea **se compune** |
| 8 | rezervă: booztlet p2 | — | **neconsumată**: p1 nu expune nicio paginare în brut |

Oprirea paginării pe altex e deci **grila goală pe 200** — a patra semnătură de final din
codebase, după 404 (buzzsneakers), pagina repetată și 5xx (STATE-1).

Cererile 4 și 6 au avut o miză proprie, ușor de trecut cu vederea: **JSON-0 măsurase randarea de
browser, dar scannerul citește HTTP**. Un descriptor scris pe ce vede browserul ar fi putut
descrie noduri pe care HTTP-ul nu le servește. Ambele au ieșit identice, deci niciunul dintre
cele două domenii nu cere browser.

### sportvision.ro — SSR, cu paginare care există dar nu se vedea

Nota veche spunea „paginarea nu e clasică — `a[rel='next']` cu textul «Arată mai multe», deci
încărcare client-side, nemăsurată". Adevărat despre **click** (JSON-0: clickul avansează
contorul la `page-3` și nu aduce nimic, zero cereri de rețea), dar URL-ul din `href` există și e
servit server-side. Cererea 5 l-a cerut: 200, alte 24 de carduri, zero comune. `page-{n}` intră
în descriptor.

**Fără referință, și e o măsurătoare:** `data-productprevprice` e EGAL cu `data-productprice` pe
24/24, iar `data-productdiscount` e „0" pe 24/24 — exact capcana constantei de la vivre și
`previousPrice` de la flip. Citită ca referință, ar produce reduceri de 0% pe tot catalogul.
Deci axa D doar pe R2.

Prețul vine din **text**, nu din atribut: `data-productprice="249,99"` are virgulă zecimală, iar
calea `price_attr` merge prin parserul strict (punct zecimal) și ar întoarce None — verificat.

### booztlet.com — SSR, EUR, cu punct zecimal

86 de produse randate server-side, aceleași pe HTTP și în browser. `/eu/en/women` e o
**aterizare** de departament (1,24 MB, ZERO carduri); frunza de listare e `view-all`.

Trei decizii, fiecare plătită de o măsurătoare:

* **`us_dot`, nu `eu_comma`.** Prețurile sunt „69.50 €" — punctul e ZECIMAL. Cu `eu_comma` ar
  ieși 6950.0, de 100 de ori mai mult. Sigur pe tot dump-ul: valorile merg de la 9.0 la 433.3 și
  niciuna n-are separator de mii, deci ambiguitatea „1.299" nu apare.
* **Prețul din text, nu din atributul numeric.** `data-cnstrc-item-price="78.000"` ar fi mers
  prin parserul strict, dar e prezent doar pe **80/86** — iar cele șase care-i lipsesc sunt
  produse REALE (Enkel Studio by PWT, cu href și preț). Calea aia ar fi pierdut tăcut șase
  carduri. `data-actual-price="78 €"` e pe 86/86 dar are „€", pe care parserul strict îl refuză.
* **Selectorul trebuie să numească eticheta.** Prețul plătit și referința au ACEEAȘI clasă
  (`palette-product-card-price__price-tag`); le deosebește doar `span` vs `s`.

Referința e un `<s>` **nemarcat** (79/86; cele 7 fără sunt exact cele fără reducere). Cele trei
potriviri de „lowest price" din pagină sunt numele unei rubrici de meniu
(`/campaigns/women/lowest-prices`), nu o etichetă de câmp — lecția bergfreunde.

`max_pages: 1` e măsurătoare: HTML-ul brut n-are `rel=next` și nicio ancoră cu `page=`, iar în
browser scroll-ul până la capătul grilei — dovedit de 65 de imagini leneșe încărcate — n-a
declanșat nicio cerere de produse. Adâncimea ar cere API-ul **Constructor.io**, sugerat de
atributele `data-cnstrc-*`; pistă neexplorată.

### GUARD-1 — două găuri în `_detecteaza_blocare`, de reparat într-o rundă proprie

Ambele domenii de mai jos au primit **403 și o pagină de blocare**, și în ambele cazuri garda a
întors **`None`** — adică producția ar fi tratat răspunsul ca pe conținut real.

**(a) sivasdescalzo — markerul e DOAR în `<title>`.** Verificat pe HTML-ul capturat:
`'just a moment' in BODY text: False`, `in <title>: True`. Garda caută markerele în
`page.inner_text("body")`; pagina Cloudflare pune „Just a moment..." în titlu, iar în body scrie
„Performing security verification" / „verifies you are not a bot" — niciunul în
`_MARKERE_BLOCARE`. E bug-ul semnalat la G4-V3, încă neplombat, acum reprodus cu fragment
verbatim.

**(b) bstn — shell cu titlu nevid.** Regula de shell cere **trei** condiții simultan: corp sub
15 000 de octeți, zero `<a `, ȘI titlu gol-sau-lipsă. Pagina bstn are 2641 de octeți și zero
ancore, dar are `<title>BSTN Store</title>` — deci conjuncția pică și 403-ul trece drept pagină
bună.

Amândouă se repară în același loc: **markerele să se caute și în `<title>`, iar statusul HTTP să
conteze**. Forma exactă e o rundă de cod (GUARD-1), nu una de sondă.

### Ce rămâne deschis

* **sizeer.ro** — 403 Akamai în browser, dar G2C-1b îl măsurase deschis pe HTTP cu `impersonate`
  (1,8–2,1 MB, ld+json complet). Verdictul „nu e blocaj" era legat de CALEA pe care a fost dat.
  **De re-măsurat pe HTTP** înainte de orice concluzie.
* **altex prin browser** — `ERR_HTTP2_PROTOCOL_ERROR` de trei ori, zero octeți transferați. Nu e
  zid, e o incompatibilitate de transport; calea `curl_cffi` a producției merge fără probleme.
  Orice sondă pe `fenrir.altex.ro` se face **prin poartă**, nu prin browser.
* **Adâncimea plafonată.** `max_pages: 30` pe altex și mediagalaxy e plafon de **buget**, nu
  măsurătoare: realele sunt 168 și 157. 30 × 48 = 1.440 de produse per scan; restul intră prin
  rotația zilelor următoare. La fel pe sportvision (30 din ~97). De ridicat când scanul își
  permite.
* **computeruniverse.net** — GATE-3 **nu reproduce** eșecul de la LST-D5: același `/de`, prin
  aceeași poartă, a dat 200 din primul hop, iar apexul urcă `computeruniverse.net/` → 301 →
  `www.` → 307 → `/en` → 200. Deci storefront-ul de aterizare e `/en`, nu `/de`. Cauza eșecului
  inițial rămâne neexplicată.

## GUARD-1 — detectorul de blocare din browser vede titlul și statusul; retry unic pe pagina 1

Două reparații independente, amândouă din măsurători deja făcute, niciuna din speculație.

### A. `_detecteaza_blocare` lăsa să treacă două ziduri

Runda JSON-0 a deschis șase domenii într-un browser real. Două dintre ele au răspuns **403 cu o
pagină de blocare**, și în ambele cazuri garda a întors **`None`** — adică producția le-ar fi
citit ca pe conținut real, iar extractorul ar fi raportat „nicio dată de produs" în loc de
„blocat". Diferența contează: primul verdict trimite domeniul într-o rundă de descriptori, al
doilea într-una de acces.

**sivasdescalzo.com — markerul e DOAR în `<title>`.** Verificat pe HTML-ul capturat:

```
'just a moment' in inner_text("body")  ->  False
'just a moment' in <title>             ->  True
```

Corpul paginii Turnstile spune „Performing security verification" și „This page is displayed
while the website verifies you are not a bot" — niciuna în lista de atunci. Garda căuta exclusiv
în `page.inner_text("body")`, care nu vede `<head>`. Era bug-ul semnalat la G4-V3 și rămas
neplombat.

**bstn.com — shell cu titlu nevid.** 2 641 de octeți, **zero** ancore, dar
`<title>BSTN Store</title>` (corpul spune doar „REQUEST NOT ALLOWED"). Regula de shell cere
**toate trei** condițiile — corp sub 15 000 de octeți, zero `<a `, ȘI titlu gol-sau-lipsă — deci
titlul nevid o dezamorsează.

**Ce s-a schimbat**, în ordinea de evaluare:

1. **Statusul HTTP, verificat primul.** 401/403/429/503 → `status <cod>`, indiferent de corp.
   `_sesiune` păstrează acum răspunsul lui `page.goto` și îi transmite `.status`.
2. **Markerele se caută și în `<title>`**, citit din HTML (nu din `page`, care nu vede `<head>`)
   → `marker in title: '<marker>'`.
3. **Trei markere noi, verbatim din măsurători:** `performing security verification` și
   `verifies you are not a bot` (corpul Turnstile, JSON-0 §3.7), `doar un moment` (varianta RO a
   interstițiului Cloudflare, G4-V2).

**Regula de shell NU s-a relaxat**, deși bstn ar fi „cerut-o". Relaxarea evidentă — renunțarea
la condiția de titlu gol — ar transforma orice pagină legitimă mică fără ancore (o confirmare,
un 200 de tip „nu s-a găsit nimic", o categorie goală) în fals pozitiv; iar un fals pozitiv aici
înseamnă că un magazin sănătos e declarat blocat și **iese tăcut din feed**. bstn e prins de
status, care e semnalul corect pentru cazul lui. Un test pinuiește exact asta: același HTML, cu
`status=200`, trebuie să întoarcă `None`.

De ce statusul primează: e singurul semnal care nu depinde de cum arată pagina. Un magazin poate
servi orice pe 403 — un shell, o pagină de marcă, chiar un catalog fals — iar euristicile pe corp
vor fi mereu cu un pas în urma fanteziei WAF-ului.

`status` e opțional (`None` implicit), deci apelanții care nu au răspunsul navigării — sondele
din `scripts/diagnostics` — rămân neatinși și primesc exact comportamentul de dinainte.

### B. Un singur retry pe `None` tranzitoriu, la pagina 1

Trei observații independente, toate cu aceeași formă: poarta a întors `None` **o dată** și a mers
la cererea următoare, pe același URL, cu același profil.

| rundă | domeniu | ce s-a văzut |
|---|---|---|
| GATE-1 | nike.com | `None`, apoi 200 |
| GATE-3 | computeruniverse.net | `/de` a dat `None` la LST-D5; sonda a cerut **exact același URL prin aceeași poartă** și a primit 200 din primul hop (1 101 369 B, 1,23 s) |
| LST-D5 | action.com | `prod1`, `None` o dată |

GATE-3 a exclus cu cifre RATE, allow-list, normalizarea de hop și interstițiul; cauza a rămas
nestabilită.

**Regula:** pe pagina 1 a unei intrări, dacă poarta întoarce `None`, scannerul așteaptă
`_pauza()` + 10 s și mai cere **o singură dată**. A doua oară `None` sau non-200 → `RuntimeError`
cu „după retry". Reușită → `logger.warning`.

**Strict pe `None`, nu pe orice eșec.** `None` înseamnă „n-am ajuns la magazin" (excepție de
rețea, poartă închisă); un 403 sau un 500 e un răspuns **real**, iar repetarea lui n-ar face
decât să mai bată o dată la o ușă tocmai închisă — exact ce a produs Access Denied-ul de la G4b,
unde insistența pe același URL a înrăutățit situația. Pagina > 1 rămâne cum a lăsat-o STATE-1:
orice non-200 acolo e sfârșit de intrare, nu eșec.

**Ce urmează să se măsoare din WARN-uri.** Linia de log nu e decor — e măsurătoarea care
lipsește. Din frecvența ei se va vedea dacă `None`-urile tranzitorii se adună pe domeniile din
spatele Cloudflare (ipoteza `__cf_bm` din GATE-3: un cookie de edge care se așază abia la a doua
cerere) sau sunt uniforme pe catalog. Prima interpretare ar face din retry o soluție permanentă;
a doua l-ar face un plasture peste o problemă de poartă, care atunci s-ar repara la sursă. Până
la cifre, nu se poate alege între ele — de aceea runda asta măsoară în loc să presupună.

### O notă de metodă: un sabotaj care nu schimbă comportamentul nu dovedește nimic

Prima variantă a sabotajului „retry de două ori" înconjura blocul cu `for _ in range(2):`. A
trecut suita — dar nu fiindcă testele ar fi fost slabe: la a doua trecere `raspuns` nu mai era
`None` (fusese reatribuit), deci ramura nici nu se mai intra, iar codul se comporta **identic**.
Sabotajul real e altul — încă o cerere în locul ridicării — și acela pică imediat
(`test_none_dublu_pe_pagina_1_ridica`, care numără exact două cereri). Când un sabotaj nu
declanșează, prima ipoteză e că mutația e inertă, nu că gardul lipsește.

## DEAL-D6 — lego.com (`lego_apollo`, `entries`) și 43einhalb.com; sizeer închis (sonda LST-D6)

Trei domenii, trei verdicte — și în **două din trei** cazuri verdictul vechi fusese dat pe o
măsurătoare greșită, nu pe o realitate a magazinului. Asta e rezultatul rundei, nu o notă de
subsol.

| domeniu | verdict vechi | verdict DEAL-D6 |
|---|---|---|
| lego.com | „navigația n-are categorie de sale, doar campania" (DEAL-D3) | **INTRĂ** — categoria există; două intrări, un extractor de stare |
| 43einhalb.com | „grila randează duplicate responsive" (DEAL-D3) | **INTRĂ** — duplicatele erau megameniu; selector scopat, zero cod nou |
| sizeer.ro | „zgomotul îneacă produsele" (G2C-1b) | **NU INTRĂ**, dar acum cu dovadă: JS_ONLY |

### 1. lego.com — cache Apollo, două forme ale aceluiași cache

Listarea reală, `/ro-ro/categories/sales-and-deals`, **nu s-a ghicit**: URL-ul e în cache-ul
paginii de campanie, în CTA-ul chiar al caruselului de reduceri
(`SKUCarousel:<id>.cta.link`), și e **singurul șir `/ro-ro/` din tot cache-ul**. 18 produse pe
p1, 4 pe p2, `p1 ∩ p2 = 0`; `?page=500` → 200 cu grilă goală, adică oprirea curată deja
cunoscută de la altex și flip.

Cache-ul stă la `props.pageProps.__APOLLO_STATE__` și e **normalizat** — o hartă plată de la
chei `<Tip>:<id>` la obiecte, legate prin referințe:

```
SingleVariantProduct:<cod>   -> slug, name, primaryImage, variant
ProductVariant:<sku>         -> price, listPrice
$ProductVariant:<sku>.price  -> {formattedAmount, centAmount, currencyCode, formattedValue}
```

**Subtilitatea care contează: setul de câmpuri depinde de QUERY-ul din spatele paginii, nu de
produs.** Pe campanie obiectul `listPrice` are `formattedValue` și `currencyCode` (20/20); pe
categorie n-are niciunul — doar `formattedAmount` („84,99 lei", text localizat, inutilizabil) și
`centAmount` (8499), pe 22/22. Un resolver oprit la `formattedValue` dă deci **zero referințe pe
categorie**: un catalog fără nicio reducere, tăcut. De aceea valoarea se citește
`formattedValue` dacă e numeric, **altfel `centAmount / 100`**.

Aceeași dependență de query explică și alegerea imaginii: `primaryImage` simplu e pe 42/42,
în timp ce forma cu argumente `primaryImage({"size":"THUMBNAIL"})` e emisă **doar** de query-ul
de categorie (18/18 acolo, 0/20 pe campanie). Un extractor legat de ea ar fi mers pe o intrare
și ar fi dat rame goale pe cealaltă.

**O corecție la raportul sondei (§3.2).** Raportul spunea că „pe categorie varianta nu leagă
`listPrice`, el există doar sub cheia construită". Măsurat pe dump-uri: varianta **leagă**
câmpul pe 18/18, 4/4 și 20/20 — dar referința e `generated: true`, iar `id`-ul ei **este** cheia
construită `$ProductVariant:<sku>.listPrice`. Cele două căi ale resolverului converg deci pe
lego; rezerva pe cheia construită rămâne în cod pentru o serializare care ar lăsa câmpul afară
din obiectul variantei, și e păzită printr-o **mutație explicită în test**, nu prin fixture —
fixture-ul rămâne reducere verbatim a dump-ului. Ce era real din observația raportului e
cealaltă jumătate: `formattedValue` chiar lipsește pe categorie.

Tot așa, forma de referință `{"__ref": ...}` (Apollo 3) **nu apare deloc** în dump-uri: toate
cele 42 de produse folosesc forma veche `{"type": "id", "generated": <bool>, "id": ...}`. E
acceptată totuși, fiindcă cele două serializări nu coexistă într-un build.

**Moneda se citește din cache, nu din locală.** `currencyCode` e `RON` pe `price` 42/42; o
nepotrivire cu `currency` din descriptor sare cardul, cu WARN. Absența codului **nu** e
nepotrivire — pe `listPrice` de categorie el lipsește pe 22/22, și acolo referința se citește ca
atare (aceeași variantă, același coș). O referință în altă monedă pierde referința, nu cardul:
prețul plătit rămâne valid, doar reducerea ar fi calculată din două unități diferite.

**Ordinea cardurilor e ordinea cheilor** — și asta s-a măsurat, nu s-a presupus: pagina poartă
și o listă ordonată (`ProductQueryResult:<uuid>.results` pe categorie,
`SKUCarousel:<id>.products` pe campanie) și ea iese **identică** cu ordinea cheilor pe toate
cele trei pagini cu produse (18, 4, 20). Deci nu se plimbă nimeni prin referințele listei ca să
afle ce se știe deja.

#### De ce NU CSS

Selectorii există și funcționează (18/18, 4/4, referință 22/22) — dar dau **imagine 0/22**
(`img[data-test='product-leaf-image-1']` n-are nici `src`, nici `srcset` în brut) și, mai grav,
atributele de test sunt **inversate** față de intuiție, exact ca la altex:

```html
<span data-test="product-leaf-price">84,99 lei</span>              <!-- TĂIAT -->
<span data-test="product-leaf-discounted-price">50,99 lei</span>   <!-- PLĂTIT -->
```

Verificat 22/22: `discounted` e mereu strict mai mic. Un descriptor care ar lua
`product-leaf-price` drept preț plătit ar raporta prețul vechi pe tot catalogul. Din cache
ambiguitatea dispare — `price` și `listPrice` sunt câmpuri **numite**, nu poziții într-un șablon
— și tot din cache se ocolesc pragurile de livrare pe care pagina le poartă ca text alături de
prețuri (`100` / `300` / `500` / `1000 lei`), capcană consemnată încă de la G4-V2b.

`listPrice` e prețul de listă LEGO, adică un PRP fără nicio etichetă legală pe pagină →
`reference_kind: "nemarcat"`.

#### `entries` cu două secțiuni ale aceleiași vitrine

A treia folosire a mecanismului `entries` (după eMAG și nichiduta), dar prima în care intrările
nu sunt categorii-surori, ci **secțiuni diferite ale aceluiași magazin**: categoria de reduceri
(`max_pages: 5`, plafon cu marjă peste cele 22 de produse de azi) și pagina de campanie
(`max_pages: 1`, fără template — e un carusel CMS, iar garda de paginare respinge pe bună
dreptate un template care n-ar fi citit niciodată). Suprapunerea dintre ele e reală (calendarul
din campanie e și în categorie) și inofensivă: `vazute` deduplică pe `external_id`, iar ambele
intrări au fost **măsurate**.

### 2. 43einhalb.com — o lecție despre selectoare, nu despre pagină

DEAL-D3 raportase „69 de `div.item-wrapper` pentru 16 URL-uri distincte" și bănuise variante de
layout responsive. **Niciun strămoș n-are vreo clasă de breakpoint.** Urmărirea containerelor a
dat răspunsul adevărat:

| container | `.pInfo` | ce e |
|---|---|---|
| `div#prodList` | **36** | grila de produse |
| `header#header` | 30 | previzualizări de MEGA-MENIU (5 dropdown-uri + 5 offcanvas × 3) |

36 + 30 = 66. Scopat la `#prodList`: **36 de carduri, 36 de URL-uri distincte, zero duplicate**.
Domeniul a intrat fără nicio linie de cod — a fost de ajuns un selector scopat.

**Lecția, și ea e pentru sonde, nu pentru magazin:** clasamentul de selectoare al sondelor n-are
noțiunea de *container de grilă*. El numără noduri care poartă preț și link și le ordonează după
scor, deci un card de megameniu arată exact ca un card de produs. De aici verdictul „duplicate
responsive" — o explicație plauzibilă lipită peste o măsurătoare care nu privise unde stau
nodurile. Sondele viitoare trebuie să raporteze, pentru selectorul câștigător, **și distribuția
pe strămoși** (`#prodList` vs `header`), nu doar numărul de potriviri.

Miza scopării nu e doar curățenia. Cele 30 de carduri de meniu apar pe **fiecare** pagină,
inclusiv pe cea de după capăt, unde grila e goală: nescopat, pagina de coadă ar fi părut plină
și **semnalul de oprire s-ar fi pierdut**. (Pentru completitudine: duplicatele meniu-vs-grilă au
preț identic, 0 URL-uri divergente, deci dedup-ul SCAN-1 le-ar fi absorbit fără pierdere de
date — dar oprirea, nu.)

Restul descriptorului, tot măsurat:

* **Referința e etichetată pe câmp**, verbatim în nota de subsol: „² UVP = unverbindliche
  Preisempfehlung des Herstellers" → `prp`, nu Omnibus. `eu_comma` citește corect
  „€ 119,95 UVP ²" → 119.95, fiindcă `²` (U+00B2) nu e cifră zecimală.
* **Imaginea a cerut `image_attr: ["data-srcset", "src"]`**: 32 din 36 de carduri sunt leneșe,
  cu `src="/images/noimage.png"` (placeholder respins corect de `normalizeaza_imagine`) și poza
  reală în `data-srcset`. Cu `["src"]` singur: 4/36. Cu rezerva: 36/36. Același tipar ca
  intersport la IMG-1a.
* **Oprirea și zidul.** `/sale/page/48` → 200 cu grilă goală (`url_final`, `canonical` și
  `<title>` spun toate „Seite 48", deci nu e clamp). Două capcane în jurul ei: pagina goală
  **încă anunță** `<link rel="next" href="/sale/page/49">` — deci `rel=next` nu e semnal de
  final aici, grila goală e — iar `page/500` dă **403** (`classify` → BLOCKED), deci coada e zid
  și plafonul nu se poate ridica prin bisecție pe pagini mari. `max_pages: 30` rămâne plafon de
  buget peste o adâncime reală de ~47, ea însăși **derivată** (1 663 de produse ÷ 36), nu
  numărată; totalul driftează (1 664 pe 7 septembrie → 1 663 pe 8).

### 3. sizeer.ro — JS_ONLY, cu dovada care lipsea

Prima jumătate a ipotezei se confirmă: **HTTP-ul nu e zid.** `/outlet` a răspuns 200 cu 1,71 MB,
acolo unde browserul primise 403 Akamai (JSON-0). Verdictul G2C-1b „nu e blocaj" rămâne valid
pentru calea HTTP.

A doua jumătate nu. Pe cele 1,71 MB: **4** carduri cu preț propriu (un raft de recomandări, nu
grila), **0** carduri pe `/promotii-actuale`, și **zero bloburi de stare** — nici `__NUXT__`,
nici `__NEXT_DATA__`, nici `<script type=application/json>`, nici `window.__*`. Nota din august
(„din 92 de carduri candidate, 87 poartă cele două componente partajate") era **corectă, dar din
motivul greșit**: nu zgomotul îneacă produsele, ci **grila nu e servită deloc**. Verificarea
blobului era pasul care lipsea, și e cel care schimbă „n-am găsit produse" în „nu există produse
de găsit".

Nu intră, și nu se propune descriptor. Reintrarea cere captura API-ului din spatele grilei — pe
HTTP, unde poarta e deschisă, nu în browser, unde e 403.

### 4. Ce s-a scris

`lego_apollo` e al **optulea** extractor de stare (`listing_state_extractors.py`); 43einhalb n-a
cerut niciunul. Domeniile de listare: 46 → **48**. Cele patru sabotaje ale rundei — `listPrice`
doar prin referință, `formattedValue` fără rezervă, card nescopat, `image_attr` doar pe `src` —
au fost verificate întâi că schimbă textul fișierului și apoi că fiecare pică exact garda ei.
