"""VAL D runda 4a — extractoare de listare pe STARE (nu pe selectori CSS).

Familia „listare-din-stare" (masurata la extractia R4 + sonda LST-4): magazine
la care datele de produs ale unei LISTARI nu stau in DOM, ci intr-un payload
structurat — ld+json, `__NEXT_DATA__`, RSC, sau un array JS. Selectorii
`card`/`link`/`title`/`price_text` n-au ce descrie acolo.

Primul domeniu intrat: toolnation.nl (`toolnation_ldjson`). Fixture-urile sunt
DECUPATE din dump-uri reale — p1 din `scripts/diagnostics/dumps_g2f/` (sonda
G2F-1/G2F-2) si p2 din `dumps_lst4/` (sonda LST-4) — si pastreaza TOATE cele 7
blocuri ld+json ale paginii, nu doar pe cel cu produsele: alegerea blocului
corect e ea insasi invarianta pe care testele o pinuiesc.
"""
import os

import pytest

from app.services.listing_scanner import extrage_carduri
from app.services.listing_state_extractors import (
    LISTING_STATE_EXTRACTORS, ldjson_product_list,
)
from app.services.shop_registry import listing_descriptor

FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "listing")


def _fixture(nume: str) -> str:
    with open(os.path.join(FIXTURI, f"{nume}_cards.html"), encoding="utf-8") as f:
        return f.read()


# ── registrul de extractoare ────────────────────────────────────────────────
def test_registrul_expune_extractorul_toolnation():
    """Registrul e un dict {nume -> functie}, iar `state_extractor` din descriptor
    e o CHEIE in el. Un nume necunoscut trebuie sa cada tare, nu sa iasa gol."""
    assert "toolnation_ldjson" in LISTING_STATE_EXTRACTORS
    assert callable(LISTING_STATE_EXTRACTORS["toolnation_ldjson"])


def test_nume_necunoscut_de_extractor_cade_tare():
    """Un `state_extractor` gresit scris nu trebuie sa dea o listare GOALA — aia
    ar arata ca „magazinul n-are reduceri azi" si ar inchide tacit toate dealurile.
    """
    descriptor = {"state_extractor": "nu_exista", "currency": "EUR"}
    with pytest.raises(KeyError):
        extrage_carduri(_fixture("toolnation.nl"), descriptor, "toolnation.nl")


# ── helperul de selectie a blocului ─────────────────────────────────────────
def test_ldjson_product_list_alege_blocul_lista_nu_primul():
    """Pagina are 7 blocuri ld+json; doar UNUL e o lista de `Product`. Primul bloc
    e `WebSite`, iar intre ele mai sunt `HardwareStore`, doua `BreadcrumbList` si
    `Organization`. Helperul trebuie sa-l gaseasca pe cel corect — nu primul bloc,
    nu concatenarea tuturor."""
    fixture = _fixture("toolnation.nl")
    assert fixture.count("application/ld+json") == 7

    produse = ldjson_product_list(fixture)

    assert produse is not None
    assert len(produse) == 24
    assert {p["@type"] for p in produse} == {"Product"}


def test_ldjson_product_list_intoarce_none_cand_nu_exista_lista():
    """Fara bloc-lista, helperul intoarce None si extractorul iese cu lista goala —
    e cazul unei pagini de final de paginare, nu o eroare."""
    assert ldjson_product_list("<html><head></head><body></body></html>") is None
    assert ldjson_product_list(
        '<script type="application/ld+json">{"@type":"WebSite"}</script>') is None


# ── toolnation, pe fixture-ul REAL p1 ───────────────────────────────────────
def test_toolnation_p1_24_carduri_normalizate():
    """Contractul de card e IDENTIC cu cel al caii CSS — aceleasi 6 chei — fiindca
    restul scannerului (memoria R2, `_evalueaza`, `Deal`) nu stie si nu trebuie sa
    stie din ce sursa a venit cardul."""
    carduri = extrage_carduri(_fixture("toolnation.nl"),
                              listing_descriptor("toolnation.nl"), "toolnation.nl")

    assert len(carduri) == 24
    assert all(set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at", "image_url"} for c in carduri)

    primul = carduri[0]
    assert primul["title"] == "E-00016 Schroefbitset 31-delig 25mm"
    assert primul["price"] == 20.93
    assert isinstance(primul["price"], float)
    assert primul["url"] == ("https://www.toolnation.nl/"
                             "makita-accessoires-e-00016-schroefbitset-31-delig-25mm.html")
    assert primul["external_id"].startswith("lst:")
    assert primul["handle"].startswith("/makita-accessoires-")


def test_toolnation_nu_are_referinta_taiata_deci_doar_R2():
    """Masurat pe AMBELE pagini: zero chei de tip `highPrice`/`listPrice`/`was` in
    ld+json. `compare_at` e None pe 24/24, deci R1 nu poate porni niciodata pe
    domeniul asta si dealurile vin exclusiv din minimul istoric (R2) — acelasi
    regim ca buzzsneakers. Asertia e EXPLICITA ca sa nu para o scapare."""
    for pagina in ("toolnation.nl", "toolnation.nl_p2"):
        carduri = extrage_carduri(_fixture(pagina),
                                  listing_descriptor("toolnation.nl"), "toolnation.nl")
        assert all(c["compare_at"] is None for c in carduri), pagina


def test_toolnation_moneda_vine_din_descriptor_nu_din_stare():
    """`priceCurrency: EUR` exista pe 24/24 in stare, dar moneda dealului o pune
    scannerul din `descriptor["currency"]` — la fel ca pe calea CSS. Testul leaga
    cele doua, ca o divergenta sa se vada."""
    descriptor = listing_descriptor("toolnation.nl")
    assert descriptor["currency"] == "EUR"

    produse = ldjson_product_list(_fixture("toolnation.nl"))
    monede = {o["priceCurrency"] for p in produse for o in p["offers"]}
    assert monede == {"EUR"}


def test_toolnation_p2_disjunct_de_p1():
    """LST-4: `?p=2` da tot 24 de produse, cu aceleasi chei, si ZERO suprapunere cu
    p1 — starea chiar traieste pe paginare, nu re-randeaza prima pagina."""
    p1 = extrage_carduri(_fixture("toolnation.nl"),
                         listing_descriptor("toolnation.nl"), "toolnation.nl")
    p2 = extrage_carduri(_fixture("toolnation.nl_p2"),
                         listing_descriptor("toolnation.nl"), "toolnation.nl")

    assert len(p2) == 24
    assert not ({c["url"] for c in p1} & {c["url"] for c in p2})
    assert not ({c["external_id"] for c in p1} & {c["external_id"] for c in p2})


def test_toolnation_descrierea_partajata_nu_ajunge_titlu():
    """Capcana masurata: `description` e IDENTIC pe toate cele 24 de produse — e
    text de categorie („Sale % bij Toolnation..."), nu descriere de produs. Titlul
    vine din `name`, care e distinct pe 24/24."""
    produse = ldjson_product_list(_fixture("toolnation.nl"))
    assert len({p["description"] for p in produse}) == 1
    assert len({p["name"] for p in produse}) == 24

    carduri = extrage_carduri(_fixture("toolnation.nl"),
                              listing_descriptor("toolnation.nl"), "toolnation.nl")
    assert len({c["title"] for c in carduri}) == 24
    assert not any("Ontdek alle producten" in c["title"] for c in carduri)


def test_toolnation_descriptorul_nu_declara_stoc():
    """`availability` e `InStock` pe 24/24 pe AMBELE pagini masurate — nu se poate
    deosebi de o constanta de sablon (capcana dovedita pe vivre, unde PDP-urile
    emiteau `OutOfStock` pe produse pe care listarea le dadea in stoc). Cat timp e
    nedecis, stocul NU se citeste: 24/24 e la fel de compatibil cu „tot catalogul e
    in stoc" ca si cu „campul e decorativ"."""
    descriptor = listing_descriptor("toolnation.nl")
    assert "stock_attr" not in descriptor
    assert "stock_field" not in descriptor

    produse = ldjson_product_list(_fixture("toolnation.nl"))
    disponibilitati = {o["availability"] for p in produse for o in p["offers"]}
    assert disponibilitati == {"https://schema.org/InStock"}


# ── ro.vivre.eu — payload RSC (`vivre_rsc`) ─────────────────────────────────
def test_vivre_24_carduri_din_rsc():
    """Fixture-ul e dump-ul LST-2 real: 23 de bucati `self.__next_f.push` care se
    CONCATENEAZA inainte de dezescapare — `initialData` cade la granita dintre ele,
    deci o singura bucata nu s-ar putea parsa."""
    carduri = extrage_carduri(_fixture("ro.vivre.eu"),
                              listing_descriptor("ro.vivre.eu"), "ro.vivre.eu")

    assert len(carduri) == 24
    assert all(set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at", "image_url"} for c in carduri)
    primul = carduri[0]
    assert primul["price"] == 352.87
    assert primul["title"] == ("Birou pentru copii cu rafturi, dulap, sertar "
                               "și scaun, alb")


def test_vivre_compare_e_lowestPrice_nu_originalPrice():
    """MIEZUL domeniului. `price` are DOUA campuri de referinta si unul e momeala:
    `originalPrice` e 0 pe 19 din 24, in timp ce `lowestPrice` e populat pe 24/24
    si strict peste pretul curent pe 24/24.

    Pe item[0]: price 352.87, originalPrice 0, lowestPrice 415.15. Daca extractorul
    ar lua `originalPrice`, cardul ar iesi cu compare_at 0 -> None si reducerea ar
    disparea; pe cele 5 unde e nenul ar raporta o marja UMFLATA (masurat: 3586.99
    fata de 1799.99 lowest, la un pret de 1151.99).
    """
    carduri = extrage_carduri(_fixture("ro.vivre.eu"),
                              listing_descriptor("ro.vivre.eu"), "ro.vivre.eu")

    assert carduri[0]["compare_at"] == 415.15, "lowestPrice"
    assert carduri[0]["compare_at"] != 0, "NU originalPrice (0 pe item[0])"
    assert all(c["compare_at"] is not None for c in carduri), "lowestPrice e pe 24/24"
    assert all(c["compare_at"] > c["price"] for c in carduri)


def test_vivre_linkul_construit_coincide_cu_DOM_ul():
    """`/p-{id}/{slug}` nu e ghicit: fixture-ul pastreaza si cele 24 de ancore
    randate de pagina, iar linkurile construite din stare le reproduc exact.
    Ancorele poarta in plus `?ch_type=0&ch_id=products` — sufix de urmarire,
    irelevant pentru `external_id`, care ia doar calea."""
    from bs4 import BeautifulSoup

    fixture = _fixture("ro.vivre.eu")
    dom = {a["href"].split("?")[0]
           for a in BeautifulSoup(fixture, "html.parser").select('a[href^="/p-"]')}
    assert len(dom) == 24

    carduri = extrage_carduri(fixture, listing_descriptor("ro.vivre.eu"),
                              "ro.vivre.eu")

    assert {c["handle"] for c in carduri} == dom
    assert carduri[0]["url"].startswith("https://ro.vivre.eu/p-9056050/")


def test_vivre_moneda_si_min30():
    """`currency: RON` pe 24/24 in stare, si e singurul domeniu din familie cu
    fereastra Omnibus scrisa EXPLICIT — i18n-ul din payload spune verbatim
    „Cel mai mic pret in ultimele 30 de zile" (modivo o lasa implicita)."""
    descriptor = listing_descriptor("ro.vivre.eu")
    assert descriptor["currency"] == "RON"
    assert descriptor["reference_kind"] == "min30"
    assert "Cel mai mic pret in ultimele 30 de zile" in _fixture("ro.vivre.eu")


# ── cellini.ro — array JS (`cellini_js`) ────────────────────────────────────
def test_cellini_48_carduri_cu_pret_compus():
    """Pretul e SPART in stare: `price` e intregul de lei si `decimalprice` e sirul
    de bani. Se recompun, ca sa nu se piarda tacit banii — 14739 + "00" = 14739.00.
    Referinta e `oldprice`, care e deja sir zecimal ("17340.00")."""
    carduri = extrage_carduri(_fixture("cellini.ro"),
                              listing_descriptor("cellini.ro"), "cellini.ro")

    assert len(carduri) == 48
    primul = carduri[0]
    assert primul["price"] == 14739.00
    assert primul["compare_at"] == 17340.00
    assert all(c["compare_at"] is not None for c in carduri), "oldprice nenul 48/48"


def test_cellini_titlul_vine_din_campul_product():
    """IMG-1b — CORECTIE de masuratoare. `name` chiar e `null` pe 48/48, si pe asta
    se baza decizia veche (titlul umanizat din slug). Sonda IMG-1a2 a tiparit insa
    elementul BRUT al array-ului si acolo se vede cheia `product`, cu numele complet
    si corect capitalizat: „Lant cu pandantiv Maria Granacci cu turmaline si
    diamante, din aur galben de 18K". `master_product` o dubleaza.

    Slug-ul umanizat ramane rezerva, pentru randurile fara `product` — dar pe fixture
    nu exista niciunul, deci calea principala e cea masurata aici. Diferenta e
    vizibila: din slug ieseau nume cu majuscule pierdute („maria granacci") si cu
    sufixul de cod lipit la coada.
    """
    carduri = extrage_carduri(_fixture("cellini.ro"),
                              listing_descriptor("cellini.ro"), "cellini.ro")

    assert carduri[0]["title"] == ("Lant cu pandantiv  Maria Granacci cu turmaline "
                                   "si diamante, din aur galben de 18K")
    assert "Maria Granacci" in carduri[0]["title"], "capitalizarea reala, nu din slug"
    assert not carduri[0]["title"].endswith(".html")
    assert all(c["title"] for c in carduri), "niciun titlu gol pe 48/48"


def test_cellini_linkul_e_calea_RADACINA_canonica():
    """`url` din stare e un nume de fisier GOL, ancorat de `<base href=".../">` la
    RADACINA. Sonda LST-4 (C6) a masurat ca forma-radacina raspunde 200 fara
    redirect si e SELF-CANONICAL, in timp ce varianta `/bijuterii/filtre/<fisier>`
    canonicalizeaza spre categorie. Deci radacina e calea corecta — si, fiindca
    `external_id` e sha1 pe CALE, ea decide identitatea produsului."""
    carduri = extrage_carduri(_fixture("cellini.ro"),
                              listing_descriptor("cellini.ro"), "cellini.ro")

    primul = carduri[0]
    assert primul["url"] == ("https://www.cellini.ro/lant-cu-pandantiv-maria-"
                             "granacci-cu-turmaline-si-diamante-din-aur-galben-"
                             "de-18k-ad-ct18co27927.html")
    assert "/bijuterii/filtre/" not in primul["url"]
    assert primul["handle"].count("/") == 1, "cale de un singur segment, la radacina"


# ── bonami.ro — __NEXT_DATA__ (`bonami_next`) ───────────────────────────────
def test_bonami_48_carduri_din_toate_blocurile():
    """`blocks` are SAPTE elemente si doar 4, 5 si 6 poarta `products` (16 fiecare).
    Blocurile 0-3 sunt breadcrumbs / banner / carusel si trebuie sarite CURAT — un
    extractor care ar lua doar primul bloc cu produse ar raporta 16 din 48."""
    carduri = extrage_carduri(_fixture("bonami.ro"),
                              listing_descriptor("bonami.ro"), "bonami.ro")

    assert len(carduri) == 48, "toate cele trei blocuri, nu doar unul"
    assert all(set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at", "image_url"} for c in carduri)


def test_bonami_pretul_vine_din_units_si_scale():
    """Pretul e un obiect, nu un numar: `{"amount": {"scale": 2, "units": 57290}}`
    = 572,90. Referinta e `retailPrice`, in aceeasi forma (67400 / 10^2 = 674,00).
    Valoarea se incruciseaza cu ld+json-ul PDP-ului masurat pe axa L (`price` 572.9),
    deci doua surse independente ale aceluiasi produs, de acord."""
    carduri = extrage_carduri(_fixture("bonami.ro"),
                              listing_descriptor("bonami.ro"), "bonami.ro")

    primul = carduri[0]
    assert primul["price"] == 572.90
    assert primul["compare_at"] == 674.00
    assert primul["title"] == "Covor Universal Moar Hakuna, 160 x 230 cm"
    assert primul["url"] == ("https://www.bonami.ro/p/"
                             "covor-universal-moar-hakuna-160-x-230-cm")


def test_bonami_blocurile_fara_products_sunt_ignorate_curat():
    """Garda ceruta explicit: blocurile fara cheia `products` nu trebuie sa ridice
    exceptie si nici sa produca un card gol."""
    import json as _json
    import re as _re

    fixture = _fixture("bonami.ro")
    nd = _json.loads(_re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                fixture, _re.S).group(1))
    blocuri = nd["props"]["pageProps"]["initialCataloguePageState"]["blocks"]
    assert len(blocuri) == 7
    assert sum(1 for b in blocuri if "products" not in b) == 4

    carduri = extrage_carduri(fixture, listing_descriptor("bonami.ro"), "bonami.ro")
    assert len(carduri) == 48
    assert all(c["title"] and c["price"] > 0 for c in carduri)


def test_bonami_e_pagina_unica_masurat():
    """Zero paginare server-side: `nextPagePath` e None, nu exista `rel=next` si
    nici href cu `?page=`; `productList` (magazinul de infinite-scroll) e GOL la
    randare. De aici `max_pages: 1` si lipsa lui `page_url_template` — scannerul
    nu-l atinge niciodata, fiindca `_pagina_url` intoarce `url` pentru pagina 1."""
    from app.services import listing_scanner

    descriptor = listing_descriptor("bonami.ro")
    assert descriptor["max_pages"] == 1
    assert "page_url_template" not in descriptor
    assert listing_scanner._pagina_url(descriptor, 1) == descriptor["url"]


# ── toate patru: contractul si filtrele ─────────────────────────────────────
@pytest.mark.parametrize("domeniu,asteptat", [
    ("ro.vivre.eu", 24),
    ("cellini.ro", 48),
    ("bonami.ro", 48),
    ("toolnation.nl", 24),
])
def test_contractul_de_card_e_identic_pe_toate_extractoarele(domeniu, asteptat):
    """Restul scannerului (memoria R2, `_evalueaza`, `Deal`) nu stie din ce sursa a
    venit cardul, deci cele patru extractoare trebuie sa produca EXACT aceeasi
    forma — si sa aplice aceleasi filtre ca pe calea CSS."""
    carduri = extrage_carduri(_fixture(domeniu), listing_descriptor(domeniu), domeniu)

    assert len(carduri) == asteptat
    for c in carduri:
        assert set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at", "image_url"}
        assert c["url"].startswith("https://")
        assert isinstance(c["price"], float) and c["price"] > 0
        assert c["external_id"].startswith("lst:")
        assert c["compare_at"] is None or c["compare_at"] > 0


# ── IMG-1b: image_url pe calea de stare ─────────────────────────────────────

def test_img1b_vivre_poza_din_photo_main_thumb():
    """T3 — vivre are o singura cheie image-like pe produs, `photo.main.thumb`
    (masurat de IMG-1a2), si e un URL absolut pe CDN-ul propriu."""
    carduri = extrage_carduri(_fixture("ro.vivre.eu"),
                              listing_descriptor("ro.vivre.eu"), "ro.vivre.eu")

    assert all(c["image_url"] for c in carduri), "poza pe 24/24"
    assert all(c["image_url"].startswith("https://s9.vivre.eu/") for c in carduri)


def test_img1b_cellini_poza_din_picture_thumb():
    """T3 — `picture` e un dict de variante de marime; se ia `thumb`. `brand_picture`
    (sigla marcii) si `secondPicture` (o poza de ambalaj, `punga_cellini.jpg`) sunt
    ignorate deliberat — niciuna nu e produsul."""
    carduri = extrage_carduri(_fixture("cellini.ro"),
                              listing_descriptor("cellini.ro"), "cellini.ro")

    assert all(c["image_url"] for c in carduri), "poza pe 48/48"
    assert all(c["image_url"].startswith("https://cdn.contentspeed.ro/")
               for c in carduri)
    assert "punga_cellini" not in carduri[0]["image_url"], "nu poza de ambalaj"
    assert "/brands/" not in carduri[0]["image_url"], "nu sigla marcii"


def test_img1b_toolnation_poza_e_none_fiindca_magazinul_da_placeholder():
    """T3 — REZULTAT NEGATIV ASTEPTAT, nu un extractor stricat. `image` exista pe
    toate obiectele ld+json, dar valoarea e acelasi
    `/placeholder/default/toolnation-no-image-2_3.jpg` (IMG-1a2, verificat pe doua
    obiecte). Normalizatorul il respinge dupa nume, deci cardul iese fara poza."""
    carduri = extrage_carduri(_fixture("toolnation.nl"),
                              listing_descriptor("toolnation.nl"), "toolnation.nl")

    assert carduri, "extractorul trebuie sa produca oricum carduri"
    assert all(c["image_url"] is None for c in carduri)


def test_img1b_bonami_poza_e_none_fiindca_starea_are_hash_uri():
    """T3 — bonami nu poarta URL-uri de imagine in stare, ci HASH-uri (`imageHash`,
    `productImages[].hash`). Sonda IMG-1a2 a cautat hash-ul primului produs in tot
    dump-ul: doua aparitii, ambele in JSON, ZERO in `src`/`srcset`/`data-src`, deci
    sablonul de URL nu e deductibil din pagina. Ramane pentru IMG-1c."""
    carduri = extrage_carduri(_fixture("bonami.ro"),
                              listing_descriptor("bonami.ro"), "bonami.ro")

    assert carduri, "extractorul trebuie sa produca oricum carduri"
    assert all(c["image_url"] is None for c in carduri)
