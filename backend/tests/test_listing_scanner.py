"""DEAL-2 — scannerul de listari HTML pe magazine non-Shopify.

Toate testele sunt OFFLINE: fetch-ul e monkeypatch-uit peste tot, ZERO retea
(doctrina BNR-1c). Fixture-urile de parsare NU sunt inventate — sunt fragmente
DECUPATE din dump-urile reale ale sondelor, iar preturile asteptate mai jos sunt
exact cele masurate acolo. Cele sase de la LST-1/LST-1b
(`scripts/diagnostics/dumps_lst1/<domeniu>_p1.html`) au 3 carduri complete
fiecare; buzzsneakers vine de la SNK-1 (`dumps_snk1/`), tot cu 3. Exceptie
DELIBERATA: intersport (LST-2, `dumps_lst2/`) pastreaza PAGINA INTREAGA, toate
cele 30 de carduri — acolo „30 pe pagina" si „pret taiat pe 30/30" sunt ele
insele invariante masurate, iar un decupaj de 3 le-ar transforma in proxy.
"""
import os
import uuid

import pytest

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.models.user import User
from app.services import listing_scanner
from app.services.listing_scanner import (
    _external_id, _pret_eu_comma, extrage_carduri,
)
from app.services.shop_registry import listing_descriptor, listing_domains

FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "listing")

DOM = "otter.ro"          # intrare reala in registru, cu descriptor de listare


def _fixture(domeniu: str) -> str:
    with open(os.path.join(FIXTURI, f"{domeniu}_cards.html"), encoding="utf-8") as f:
        return f.read()


class _Raspuns:
    def __init__(self, html, status=200):
        self.status_code = status
        self.text = html


def _seteaza(db, **campuri):
    """User + RadarSettings (scannerul ia primul rand — instanta e single-user)."""
    email = f"lst_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    s = RadarSettings(user_id=u.id, **campuri)
    db.add(s)
    db.commit()
    return s


@pytest.fixture
def scan(monkeypatch):
    """Runner: primeste paginile (HTML, in ordinea cererilor) si ruleaza scanul.

    Paginile se servesc dupa ORDINEA cererii, nu dupa URL, fiindca cele patru
    domenii pilot au scheme de paginare diferite (query la trei, cale la unul).
    """
    cutie = {"pagini": [], "descriptor": None}
    cereri = []

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        pagini = cutie["pagini"]
        indice = len(cereri) - 1
        pagina = pagini[indice] if indice < len(pagini) else "<html></html>"
        # O intrare poate fi si `(html, status)`: valul D masoara oprirea pe 404,
        # deci statusul nu mai e mereu 200. Sirurile simple raman neatinse.
        if isinstance(pagina, tuple):
            return _Raspuns(pagina[0], pagina[1])
        return _Raspuns(pagina)

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(listing_scanner, "listing_domains", lambda: {DOM})
    monkeypatch.setattr(listing_scanner, "_pauza", lambda: None)

    def ruleaza(pagini, descriptor=None, **setari):
        # Jurnalul se goleste la fiecare rulare: testele cu DOUA scanari (linia de
        # baza + valul urmator) servesc paginile dupa ordinea cererii, deci un
        # contor care ar continua de la scanul anterior ar indexa in gol.
        cereri.clear()
        cutie["pagini"] = pagini
        if descriptor is not None:
            monkeypatch.setattr(listing_scanner, "listing_descriptor",
                                lambda _dom: dict(descriptor))
        db = SessionLocal()
        try:
            if db.query(RadarSettings).first() is None:
                _seteaza(db, **setari)
            return listing_scanner.run_listing_scan(db)
        finally:
            db.close()

    ruleaza.cereri = cereri
    return ruleaza


def _deals():
    db = SessionLocal()
    try:
        return db.query(Deal).order_by(Deal.id).all()
    finally:
        db.close()


# ── 1. Parsarea fixture-urilor reale, per domeniu ────────────────────────────

@pytest.mark.parametrize("domeniu,pret,taiat", [
    ("otter.ro", 98.0, 379.0),            # data-price-amount, Magento
    ("caseking.de", 619.90, 759.70),      # content="619.90", zecimala cu punct
    ("noriel.ro", 49.99, 99.99),          # ".special-price .price", "49,99\xa0lei"
    ("bergfreunde.eu", 47.97, 79.95),     # data-codecept, "€ 47,97"
    ("tezyo.ro", 244.0, 349.0),           # G1-2: Magento, AMBELE ramuri in atribut
    ("powerup.ro", 197.01, 199.0),        # G2A-2: OpenCart, zecimalele in <sup>
    # SNK-2: NBSHOP. `taiat` e None DELIBERAT — pretul vechi exista doar ca
    # `data-productprevprice="759,99"`, cu virgula, deci necitibil pe calea de
    # atribut, si nu se randeaza niciun <del>/<s>. Domeniul califica pe R2, nu R1.
    ("buzzsneakers.ro", 455.99, None),
])
def test_parsare_fixture_real(domeniu, pret, taiat):
    """Descriptorul din registru extrage din dump-ul REAL exact valorile masurate."""
    carduri = extrage_carduri(_fixture(domeniu), listing_descriptor(domeniu), domeniu)

    assert len(carduri) == 3, f"{domeniu}: fixture-ul are 3 carduri"
    primul = carduri[0]
    assert primul["price"] == pret
    assert primul["compare_at"] == taiat
    assert primul["url"].startswith("https://"), "linkul trebuie absolutizat"
    assert domeniu.split(".")[0] in primul["url"]
    assert primul["title"], "titlul nu poate fi gol"
    assert primul["external_id"].startswith("lst:")


def test_tezyo_titlul_vine_din_textul_ancorei():
    """G1-2: primul descriptor la care `title` tinteste CHIAR ancora produsului.

    Pe otter/noriel/bergfreunde `title` e un element separat (h3/h2/div); aici
    cardul n-are asa ceva, iar numele sta in textul lui `a.product-item-link`.
    Nu a fost nevoie de o conventie noua — `_titlu_of` ia textul oricarui selector
    — dar tiparul merita fixat, ca o refactorizare a titlurilor sa nu-l rupa tacit.
    """
    carduri = extrage_carduri(_fixture("tezyo.ro"), listing_descriptor("tezyo.ro"),
                              "tezyo.ro")

    assert [c["title"] for c in carduri] == [
        "Sandale elegante EPICA albe, 551, din piele ecologica",
        "Mocasini ALDO bej, CARROBRERIA 110, din piele naturala lacuita",
        "Pantofi sport EPICA albi, 6159290, din material textil si piele naturala",
    ]


def test_powerup_products5_tine_caruselul_afara():
    """G2A-2 — `products5` din selectorul de card nu e decorativ.

    Pe dump-ul real al listarii SH exista 55 de noduri `div.item-display-box`:
    40 in grila (`.products5`) si 15 intr-un carusel de recomandari. Fixture-ul
    reproduce proportia — 3 carduri de grila + 2 de carusel — iar descriptorul
    trebuie sa vada exact cele 3. Fara `products5` ar intra si caruselul, adica
    fix capcana din LOT5 (nichiduta).
    """
    from bs4 import BeautifulSoup

    html = _fixture("powerup.ro")
    supa = BeautifulSoup(html, "html.parser")
    assert len(supa.select("div.item-display-box")) == 5, "fixture: 3 grila + 2 carusel"

    carduri = extrage_carduri(html, listing_descriptor("powerup.ro"), "powerup.ro")

    assert len(carduri) == 3


def test_powerup_quickview_ul_nu_devine_link_de_produs():
    """Fiecare card poarta DOUA ancore catre acelasi produs: slug-ul si
    `index.php?route=product/quickview&product_id=<id>`. Sonda G2A-1 a cazut exact
    aici — a ales quickview-ul drept „al doilea produs" — deci descriptorul il
    exclude prin `a:not(.quickview)`, iar fixture-ul pastreaza ancorele quickview
    ca excluderea sa fie chiar testata."""
    html = _fixture("powerup.ro")
    assert "route=product/quickview" in html, "fixture: quickview-urile sunt pastrate"

    carduri = extrage_carduri(html, listing_descriptor("powerup.ro"), "powerup.ro")

    assert carduri, "descriptorul trebuie sa dea carduri"
    for card in carduri:
        assert "quickview" not in card["url"]
        assert "/refurbished-sh/" in card["url"]


def test_intersport_pagina_intreaga_masurata_la_lst2():
    """LST-2: pagina 1 de pe /sale/, INTREAGA, nu un decupaj de 3 carduri.

    Trei invariante masurate pe dump-ul real (`dumps_lst2/I1_listare_p1.html`),
    toate trei pierdute daca fixture-ul s-ar trunchia:
      * 30 de carduri pe pagina — cifra care inchide si totalul afisat
        (`data-total-pages="305"` x 30 = 9150, iar pagina scrie „9148 produse");
      * pret taiat pe 30/30, deci R1 poate porni pe domeniul asta din primul scan
        (spre deosebire de buzzsneakers, unde referinta nu e citibila);
      * pretul e pe TEXT cu virgula („189,99 LEI"), nu pe atribut — atributul
        `data-current-price="189,99"` ar trece prin parserul strict cu punct si ar
        da tacut None.
    """
    carduri = extrage_carduri(_fixture("intersport.ro"),
                              listing_descriptor("intersport.ro"), "intersport.ro")

    assert len(carduri) == 30, "pagina masurata are 30 de carduri"
    primul = carduri[0]
    assert primul["title"] == "adidas PANTOFI GALAXY 8"
    assert primul["price"] == 189.99
    assert primul["compare_at"] == 299.99
    assert all(c["compare_at"] is not None for c in carduri), \
        "referinta taiata e prezenta pe 30/30 — masurat la LST-2"
    assert all(c["price"] > 0 for c in carduri)


def test_intersport_capcana_points_gain_nu_e_pe_listare():
    """G2F-2 a masurat pe PDP o capcana: `span.points-gain` poarta ACEEASI cifra ca
    pretul, cu alt inteles („305,99 puncte" de fidelitate). LST-2 a masurat ca pe
    LISTARE ea nu apare deloc — deci `.current-price` e neambiguu aici. Testul
    pinuieste faptul, ca o schimbare de markup sa nu-l reintroduca tacit."""
    assert "points-gain" not in _fixture("intersport.ro")


def test_intersport_out_of_stock_e_sablon_pe_toate_cardurile():
    """Motivul pentru care descriptorul NU are `stock_attr`: marcajul exista pe
    TOATE cele 30 de carduri (sablon ascuns prin CSS extern, tiparul elefant), deci
    ca semnal ar declara tot catalogul indisponibil. Daca cineva adauga cheia,
    testul de mai jos cade pe descriptor, iar asta explica de ce."""
    fixture = _fixture("intersport.ro")
    assert fixture.count("out-of-stock") == 30
    assert "stock_attr" not in listing_descriptor("intersport.ro")


def test_card_fara_pret_valid_e_sarit():
    """Un card caruia ii lipseste pretul platit se SARE, nu se repara tacit."""
    descriptor = dict(listing_descriptor("otter.ro"))
    descriptor["price_attr"] = ("[data-price-type='nuExista']", "data-price-amount")

    assert extrage_carduri(_fixture("otter.ro"), descriptor, "otter.ro") == []


def test_link_parent_a_urca_la_stramos():
    """Conventia `@parent_a` (link ca STRAMOS al cardului) — niciun pilot nu o
    foloseste azi, dar ramane in scanner, deci ramane si acoperita.

    Marcaj sintetic DELIBERAT (`example.test`): nu e date masurate.
    """
    html = ('<a href="/produs-x"><div class="card">'
            '<span class="p">10,00 lei</span></div></a>')
    descriptor = {"card": "div.card", "link": "@parent_a",
                  "price_text": ".p", "price_parse": "eu_comma"}

    carduri = extrage_carduri(html, descriptor, "example.test")

    assert len(carduri) == 1
    assert carduri[0]["url"] == "https://example.test/produs-x"
    assert carduri[0]["price"] == 10.0


# ── 2. Parserul de preturi europene ──────────────────────────────────────────

@pytest.mark.parametrize("brut,asteptat", [
    ("€ 47,97", 47.97),             # bergfreunde: simbol prefixat
    ("49,99\xa0lei", 49.99),        # noriel: spatiu INSECABIL intre numar si moneda
    ("1.299,99 lei", 1299.99),      # punctul e separator de mii
    ("from € 37,07", 37.07),        # eticheta de pret "de la"
])
def test_eu_comma_formate_masurate(brut, asteptat):
    assert _pret_eu_comma(brut) == asteptat


@pytest.mark.parametrize("brut", ["abc", "12,34,56", "", None, "lei"])
def test_eu_comma_intrare_corupta_da_none(brut):
    """Parsare STRICTA: ce nu iese numar curat intoarce None si cardul se sare."""
    assert _pret_eu_comma(brut) is None


# ── 3. Identitatea produsului ────────────────────────────────────────────────

def test_external_id_determinist_scurt_si_fara_query():
    """Acelasi produs = acelasi id, indiferent de query string; sub String(64)."""
    baza = _external_id("https://www.otter.ro/pantofi-x")

    assert baza == _external_id("https://www.otter.ro/pantofi-x")
    assert baza == _external_id("https://www.otter.ro/pantofi-x?utm_source=nl")
    assert baza == _external_id("https://www.otter.ro/pantofi-x/#detalii")
    assert baza != _external_id("https://www.otter.ro/pantofi-y")
    assert len(baza) < 64


# ── 4. Conditia de oprire compusa (masurata in LST-1b) ───────────────────────

def _descriptor_test(max_pages=5):
    return {"url": "https://www.otter.ro/reduceri",
            "page_url_template": "https://www.otter.ro/reduceri?p={n}",
            "max_pages": max_pages, "currency": "RON",
            "card": "li.product-item", "link": "a.product-item-photo",
            "title": "h3.product-item-name",
            "price_attr": ("[data-price-type='finalPrice']", "data-price-amount"),
            "compare_attr": ("[data-price-type='oldPrice']", "data-price-amount"),
            "price_parse": "attr_float", "reference_kind": "prp"}


def test_oprire_pe_grila_goala(scan):
    """otter/caseking: pagina de dincolo de final da 200 cu grila GOALA."""
    scan([_fixture("otter.ro"), "<html><body></body></html>"],
         descriptor=_descriptor_test())

    assert len(scan.cereri) == 2, "a doua pagina (goala) opreste bucla"


def _pagina_cu_produs_repetat():
    """(p1, p2) — p2 repeta PRIMUL produs al lui p1 si aduce doua produse noi.

    SINTETICA, marcata ca atare: cardurile sunt cele reale din fixture-ul otter,
    doar href-urile ultimelor doua sunt rescrise ca sa fie produse distincte.
    Fenomenul reprodus e insa real, observat in G1-2 pe scanul complet tezyo (69 de
    pagini): catalogul se re-sorteaza intre cereri, iar un produs de la granita unei
    pagini aluneca pe urmatoarea si e vazut de DOUA ori in acelasi scan.

    p2 NU e submultime a lui p1 (are linkuri noi), deci conditia de oprire
    `linkuri_pagina <= linkuri_vazute` nu se activeaza si bucla chiar proceseaza
    produsul repetat a doua oara — exact drumul pe care apare dublura.
    """
    from bs4 import BeautifulSoup

    supa = BeautifulSoup(_fixture("otter.ro"), "html.parser")
    carduri = supa.select("li.product-item")
    repetat = str(carduri[0])                      # verbatim: acelasi external_id
    noi = []
    for i, card in enumerate(carduri[1:], start=1):
        copie = BeautifulSoup(str(card), "html.parser")
        for a in copie.find_all("a", href=True):
            a["href"] = a["href"].replace("https://www.otter.ro/",
                                          f"https://www.otter.ro/p2-{i}-")
        noi.append(str(copie))
    p2 = '<html><body><div id="grid">' + repetat + "".join(noi) + "</div></body></html>"
    return _fixture("otter.ro"), p2


def test_produs_repetat_intre_pagini_nu_dubleaza_memoria(scan):
    """SCAN-1 — regresie: un `external_id` vazut a doua oara in ACELASI scan.

    Pe codul de dinainte de fix scanul cadea cu
    `IntegrityError: UNIQUE constraint failed: shop_price_memory.shop_domain,
    shop_price_memory.external_id`: `SessionLocal` are `autoflush=False`, deci randul
    adaugat cu `db.add(ShopPriceMemory(...))` NU era vizibil interogarii de la a doua
    aparitie, iar codul mai adauga unul. Caderea nu iese la suprafata ca exceptie —
    `run_listing_scan` o prinde per domeniu si o scrie ca `state="error"` — de aceea
    asertia e pe rezumat + numarul de randuri, nu pe `pytest.raises`.

    `compare_attr` tinteste DELIBERAT un selector inexistent, si asta e miezul
    reproducerii: fara pret taiat niciun produs nu califica drept deal, deci nu se
    executa `db.add(deal)` + `db.flush()`. Acel flush persista TOATE obiectele
    pending, inclusiv memoria de pret, si de aceea masca bugul — cu el, a doua
    aparitie isi gaseste randul si totul pare in regula. Fereastra periculoasa e
    exact secventa de produse NECALIFICATE dintre cele doua aparitii, adica situatia
    normala pe paginile tarzii ale unei listari mari, unde dealurile sunt deja in
    baza si nu se mai creeaza randuri noi. Asta explica si de ce cei 4 piloti au
    scapat empiric, desi codul lor e identic.
    """
    p1, p2 = _pagina_cu_produs_repetat()
    descriptor = _descriptor_test()
    descriptor["compare_attr"] = ("[data-price-type='nuExista']", "data-price-amount")

    rezumat = scan([p1, p2, "<html><body></body></html>"], descriptor=descriptor)

    assert rezumat["erori"] == 0, "produsul repetat nu are voie sa pice scanul"

    db = SessionLocal()
    try:
        randuri = (db.query(ShopPriceMemory)
                   .filter(ShopPriceMemory.shop_domain == DOM).all())
    finally:
        db.close()

    externe = [r.external_id for r in randuri]
    assert len(externe) == len(set(externe)), "un external_id = un singur rand"
    # 3 din p1 + 2 noi din p2; al treilea card al lui p2 e produsul repetat.
    assert len(randuri) == 5


def test_oprire_pe_pagina_repetata(scan):
    """noriel clameaza la pagina 1, bergfreunde la ultima: statusul ramane 200 si
    grila e PLINA, deci fara regula linkurilor deja vazute bucla ar merge la
    infinit pana la max_pages."""
    pagina = _fixture("otter.ro")
    scan([pagina, pagina, pagina], descriptor=_descriptor_test())

    assert len(scan.cereri) == 2, "pagina 2 repeta integral pagina 1 -> stop"


def test_oprire_pe_max_pages(scan):
    """Plasa de siguranta: chiar cu pagini mereu noi, `max_pages` opreste."""
    import re
    pagini = []
    for i in range(10):
        # Acelasi markup REAL, cu href-urile prefixate ca sa fie produse distincte.
        pagini.append(re.sub(r'href="https://www\.otter\.ro/',
                             f'href="https://www.otter.ro/p{i}-', _fixture("otter.ro")))
    scan(pagini, descriptor=_descriptor_test(max_pages=3))

    assert len(scan.cereri) == 3


def test_pagina_1_foloseste_url_ul_masurat(scan):
    """Pagina 1 e URL-ul de intrare masurat, nu template-ul cu n=1."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    assert scan.cereri[0] == "https://www.otter.ro/reduceri"
    assert scan.cereri[1] == "https://www.otter.ro/reduceri?p=2"


# ── 4b. VAL D — 404 la finalul paginarii (masurat pe buzzsneakers, SNK-1/SNK-2) ─

# Corpul REAL al paginii de dincolo de final, din `buzzsneakers.ro_plast.html`
# (dump SNK-1, 228.229 de octeti): NU e un document gol, ci pagina de eroare cu tot
# chrome-ul site-ului, iar grila ei are ZERO `.product-item`. Aici se pastreaza doar
# titlul, verbatim din dump; restul e navigatie fara efect asupra parsarii. Corpul
# nevid conteaza: dovedeste ca oprirea vine din STATUS, nu din „grila goala".
_CORP_404 = ('<html><head><title>Pagina inexistenta | BuzzSneakers Romania'
             '</title></head><body><div id="grid"></div></body></html>')


def _descriptor_buzz(max_pages=5):
    """Descriptorul MASURAT la SNK-2 (docs/catalog_domain_log.md), fara cheie de
    pret taiat: `data-productprevprice` e cu VIRGULA, deci calea de atribut ar da
    tacut None, iar vizibil nu se randeaza niciun pret taiat (zero <del>/<s>)."""
    return {"url": "https://www.buzzsneakers.ro/produse/outlet",
            "page_url_template": "https://www.buzzsneakers.ro/produse/outlet/page-{n}",
            "max_pages": max_pages, "currency": "RON",
            "card": ".product-item", "link": "a.product-link", "title": ".title",
            "price_text": "div.current-price span.value",
            "price_parse": "eu_comma", "reference_kind": "nemarcat"}


def test_404_dupa_prima_pagina_e_oprire_curata(scan):
    """buzzsneakers foloseste 404 drept sfarsit de paginare: masurat live la SNK-2
    („scanul a mers pe cele 39 de pagini, iar pagina 40 a dat 404") si in dump pe
    `/produse/outlet/page-999` (`buzzsneakers.ro_plast.meta.json`: `"status": 404`).

    Pana la valul D orice status != 200 ridica RuntimeError, iar exceptia cade
    INAINTE de `db.commit()` — deci se pierdea TOT scanul, inclusiv paginile deja
    citite. Pagina 1 e buna, pagina 2 da 404: scanul trebuie sa iasa ca SUCCES.
    """
    rezumat = scan([_fixture("otter.ro"), (_CORP_404, 404)],
                   descriptor=_descriptor_test())

    assert rezumat["erori"] == 0, "404 dupa o pagina reusita nu e eroare de scan"
    assert rezumat["magazine"] == 1
    assert rezumat["produse"] == 3, "cele 3 carduri ale paginii 1 sunt procesate"
    assert len(scan.cereri) == 2, "oprire curata: pagina 3 nu se mai cere"

    deals = _deals()
    assert len(deals) == 1, "cardul redus 98/379 califica pe R1, ca la scanul normal"
    assert deals[0].price == 98.0 and deals[0].compare_at_price == 379.0
    assert deals[0].deal_source == "listing_scan"


def test_404_dupa_prima_pagina_scrie_starea_ok(scan):
    """Consecinta vizibila in panoul de sanatate: domeniul ramane `ok`, nu `error`."""
    scan([_fixture("otter.ro"), (_CORP_404, 404)], descriptor=_descriptor_test())

    db = SessionLocal()
    try:
        stare = db.query(ShopScanState).filter(
            ShopScanState.shop_domain == DOM).first()
        assert stare is not None and stare.last_status == "ok"
    finally:
        db.close()


def test_404_pe_buzzsneakers_cu_descriptorul_masurat(scan):
    """Acelasi lucru pe pacientul real: fixture-ul decupat din
    `dumps_snk1/buzzsneakers.ro_listare_p1.html` plus 404-ul de final.

    Domeniul n-are pret taiat citibil, deci pe primul scan nu califica nimic pe R1
    — „procesat normal" inseamna aici cele 3 randuri de memorie de pret, temelia
    lui R2.
    """
    rezumat = scan([_fixture("buzzsneakers.ro"), (_CORP_404, 404)],
                   descriptor=_descriptor_buzz())

    assert rezumat["erori"] == 0
    assert rezumat["produse"] == 3
    assert len(scan.cereri) == 2
    assert scan.cereri[1] == "https://www.buzzsneakers.ro/produse/outlet/page-2"

    db = SessionLocal()
    try:
        memorie = db.query(ShopPriceMemory).all()
    finally:
        db.close()
    assert len(memorie) == 3, "tot ce s-a citit pana la 404 intra in memorie"


def test_404_pe_prima_pagina_ramane_eroare(scan):
    """Granita semanticii aprobate: fara nicio pagina reusita in ACELASI scan, un
    404 pe pagina 1 e o listare moarta (URL mutat, categorie stearsa), nu un
    sfarsit de paginare — si trebuie sa se vada ca eroare."""
    rezumat = scan([(_CORP_404, 404)], descriptor=_descriptor_test())

    assert rezumat["erori"] == 1, "404 pe prima pagina ramane eroare de scan"
    assert rezumat["magazine"] == 0
    assert len(scan.cereri) == 1


def test_alte_statusuri_raman_eroare_si_dupa_o_pagina_buna(scan):
    """DOAR 404 e tolerat. Un 403/500 pe pagina 2 e un zid sau o defectiune, nu un
    sfarsit de paginare, si nu are voie sa fie confundat cu el."""
    for status in (403, 410, 500):
        rezumat = scan([_fixture("otter.ro"), (_CORP_404, status)],
                       descriptor=_descriptor_test())
        assert rezumat["erori"] == 1, f"status {status} trebuie sa ramana eroare"


# ── 5. Deal-uri, memorie si sursa ────────────────────────────────────────────

def test_creeaza_deal_cu_sursa_listing_scan(scan):
    """R1 pe pretul taiat din card; proveniența se scrie EXPLICIT."""
    rezumat = scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    deals = _deals()
    assert rezumat["magazine"] == 1
    assert deals, "cardul redus 98/379 trebuie sa devina deal"
    assert all(d.deal_source == "listing_scan" for d in deals)
    assert all(d.currency == "RON" for d in deals)
    assert all(d.sizes_available == [] for d in deals)
    primul = deals[0]
    assert primul.price == 98.0 and primul.compare_at_price == 379.0
    assert primul.reason == "compare_at"


def test_memoria_de_pret_se_scrie_pentru_tot_ce_se_vede(scan):
    """R2 are nevoie de memorie pentru TOT catalogul, nu doar pentru deal-uri."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    db = SessionLocal()
    try:
        memorie = db.query(ShopPriceMemory).all()
    finally:
        db.close()
    assert len(memorie) == 3, "toate cele 3 carduri intra in memorie"


def test_inchide_doar_dealurile_de_listare(scan):
    """`ended_at` se pune doar pe deal-urile ACESTEI surse: un deal `refresh_diff`
    pe acelasi domeniu nu are legatura cu ce vede scanul de listari."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    db = SessionLocal()
    try:
        strain = Deal(shop_domain=DOM, external_id="src:999", title="urmarit prin link",
                      url=f"https://{DOM}/x", currency="RON", price=10.0,
                      discount_pct=50.0, reason="istoric", state="nou",
                      deal_source="refresh_diff")
        db.add(strain)
        db.commit()
    finally:
        db.close()

    scan([""], descriptor=_descriptor_test())      # nimic nu mai apare

    db = SessionLocal()
    try:
        raman = db.query(Deal).filter(Deal.deal_source == "refresh_diff").all()
        listare = db.query(Deal).filter(Deal.deal_source == "listing_scan").all()
    finally:
        db.close()
    assert all(d.ended_at is None for d in raman), "refresh_diff ramane neatins"
    assert all(d.ended_at is not None for d in listare)


# ── 6. Anti-avalansa Discord ─────────────────────────────────────────────────

def test_primul_scan_nu_notifica(scan, monkeypatch):
    """R1 e gratuit pe calea asta, deci primul scan al unui domeniu ar genera sute
    de alerte pentru produse aflate la reducere de saptamani. Se stabileste linia
    de baza in tacere."""
    trimise = []
    monkeypatch.setattr("app.services.discord_service.send_deal_notification",
                        lambda deal, settings: trimise.append(deal) or True)

    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    assert trimise == []
    assert _deals(), "deal-urile intra totusi in feed, doar alerta lipseste"


def test_al_doilea_scan_notifica_doar_produsele_noi(scan, monkeypatch):
    """Dupa ce domeniul are un scan `ok` in spate, deal-urile NOI alerteaza."""
    import re
    trimise = []
    monkeypatch.setattr("app.services.discord_service.send_deal_notification",
                        lambda deal, settings: trimise.append(deal) or True)

    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())
    assert trimise == []

    db = SessionLocal()
    try:
        stare = db.query(ShopScanState).filter(ShopScanState.shop_domain == DOM).first()
        assert stare is not None and stare.last_status == "ok"
    finally:
        db.close()

    # Acelasi markup REAL, alt produs (href diferit) -> deal NOU.
    alta = re.sub(r'href="https://www\.otter\.ro/',
                  'href="https://www.otter.ro/nou-', _fixture("otter.ro"))
    scan([alta, ""], descriptor=_descriptor_test())

    assert len(trimise) == 1, "doar produsul nou alerteaza, nu si cele reaparute"


def test_plafonul_de_alerte_per_domeniu(scan, monkeypatch):
    """Chiar dupa linia de baza, o reducere pe tot magazinul nu poate inunda."""
    import re
    trimise = []
    monkeypatch.setattr("app.services.discord_service.send_deal_notification",
                        lambda deal, settings: trimise.append(deal) or True)
    monkeypatch.setattr(listing_scanner, "_MAX_ALERTE", 1)

    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())   # linia de baza
    inainte = len(_deals())

    # Doua pagini cu produse NOI: fixture-ul da un singur card redus per pagina,
    # deci valul are nevoie de doua pagini ca sa produca doua deal-uri noi.
    val = [re.sub(r'href="https://www\.otter\.ro/',
                  f'href="https://www.otter.ro/val{i}-', _fixture("otter.ro"))
           for i in range(2)]
    scan(val + [""], descriptor=_descriptor_test())

    assert len(_deals()) - inainte == 2, "doua deal-uri noi au intrat in feed"
    assert len(trimise) == 1, "plafonul taie restul, care intra tacut in feed"


def test_plafonul_de_productie_este_zece():
    """Valoarea reala din cod, nu doar mecanismul testat cu plafon mic mai sus."""
    assert listing_scanner._MAX_ALERTE == 10


# ── 7. Registrul ─────────────────────────────────────────────────────────────

def test_listing_domains_exact_cele_din_registru():
    """Cei 4 piloti DEAL-2 + tezyo.ro (G1-2) + powerup.ro (G2A-2) +
    buzzsneakers.ro (SNK-2, intrat odata cu oprirea pe 404) +
    intersport.ro (LST-2) + regatuljocurilor.ro (LST-3) — ultimele doua intrate
    fara nicio linie de scanner."""
    assert listing_domains() == {"otter.ro", "caseking.de", "noriel.ro",
                                 "bergfreunde.eu", "tezyo.ro", "powerup.ro",
                                 "buzzsneakers.ro", "intersport.ro",
                                 "regatuljocurilor.ro"}


def test_descriptorul_e_copie_nu_referinta():
    """Scannerul plimba descriptorul prin functii; o referinta ar lasa un bug de
    acolo sa rescrie registrul pentru tot procesul."""
    d = listing_descriptor("otter.ro")
    d["card"] = "MUTAT"

    assert listing_descriptor("otter.ro")["card"] == "li.product-item"


def test_fiecare_descriptor_are_cheile_obligatorii():
    for domeniu in listing_domains():
        d = listing_descriptor(domeniu)
        for cheie in ("url", "page_url_template", "max_pages", "currency",
                      "card", "price_parse", "reference_kind"):
            assert d.get(cheie), f"{domeniu} nu are `{cheie}`"
        assert d["reference_kind"] in {"prp", "min30", "nemarcat"}
        assert "{n}" in d["page_url_template"]


# ── 8. DEAL-2b — pragul separat al lui R1 + inchiderea pe calificare ─────────

def test_prag_r1_implicit_este_40():
    """None inseamna implicitul, nu 0 — altfel tot catalogul ar califica."""
    assert listing_scanner.DEFAULT_LISTING_R1_THRESHOLD == 40.0
    assert listing_scanner._prag_r1(None) == 40.0

    class _Gol:
        listing_r1_threshold = None
    assert listing_scanner._prag_r1(_Gol()) == 40.0

    class _Zero:
        listing_r1_threshold = 0
    assert listing_scanner._prag_r1(_Zero()) == 40.0, "0 nu e un prag valid"


def test_prag_r1_valoarea_userului_e_respectata():
    class _Setari:
        listing_r1_threshold = 65.0
    assert listing_scanner._prag_r1(_Setari()) == 65.0


def _seteaza_prag(valoare):
    """Muta pragul R1 pe randul de setari existent (fixture-ul `scan` creeaza
    setarile doar la prima rulare)."""
    db = SessionLocal()
    try:
        s = db.query(RadarSettings).first()
        s.listing_r1_threshold = valoare
        db.commit()
    finally:
        db.close()


def test_r1_sub_pragul_de_listare_nu_califica(scan):
    """Cardul otter e 98 fata de 379 = 74%. Peste pragul global (20), dar sub un
    prag de listare de 80 — deci NU e deal pe calea asta."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())
    assert _deals(), "cu implicitul de 40% cardul califica"

    db = SessionLocal()
    try:
        db.query(Deal).delete()
        db.commit()
    finally:
        db.close()
    _seteaza_prag(80.0)

    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    assert _deals() == [], "74% < 80% -> niciun deal"


def test_r2_nu_e_afectat_de_pragul_de_listare(scan):
    """Pragul R1 urcat nu trebuie sa taie si semnalul curat (minim istoric)."""
    import re
    # Prima trecere: stabileste memoria de pret, fara compare_at (deci fara R1).
    fara_taiat = re.sub(r'data-price-type="oldPrice"', 'data-price-type="fostPret"',
                        _fixture("otter.ro"))
    scan([fara_taiat, ""], descriptor=_descriptor_test())
    assert _deals() == [], "prima vedere n-are istoric, deci nici R2"

    _seteaza_prag(95.0)          # R1 practic dezactivat
    # A doua trecere: acelasi produs la jumatate de pret -> R2 pe pragul GLOBAL.
    mai_ieftin = fara_taiat.replace('data-price-amount="98"', 'data-price-amount="40"')
    scan([mai_ieftin, ""], descriptor=_descriptor_test())

    deals = [d for d in _deals() if d.reason == "istoric"]
    assert deals, "R2 ramane pe pragul global, neatins de pragul R1"


def test_inchide_dealul_prezent_dar_necalificat(scan):
    """Efectul retroactiv prin design: primul scan de dupa marirea pragului isi
    face singur curatenia, fara SQL manual si fara migratie de date."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())
    active = [d for d in _deals() if d.ended_at is None]
    assert active, "linia de baza: dealul e activ"

    _seteaza_prag(90.0)
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    assert all(d.ended_at is not None for d in _deals()), \
        "produsul e tot pe pagina, dar nu mai califica -> inchis"


def test_inchiderea_pe_calificare_nu_atinge_starea(scan):
    """D7 ramane valabil si pe calea noua de inchidere."""
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())
    db = SessionLocal()
    try:
        for d in db.query(Deal).all():
            d.state = "ignorat"
        db.commit()
    finally:
        db.close()

    _seteaza_prag(90.0)
    scan([_fixture("otter.ro"), ""], descriptor=_descriptor_test())

    for d in _deals():
        assert d.ended_at is not None
        assert d.state == "ignorat", "inchiderea nu rescrie starea userului"


# ── LST-3 — regatuljocurilor.ro (PrestaShop `prices-drop`) ───────────────────
def test_regatuljocurilor_grila_scopata_taie_caruselul():
    """LST-3: motivul pentru care `card` e SCOPAT pe `#js-product-list`.

    Fixture-ul pastreaza pagina cu patologia ei: doua blocuri de bara laterala
    („Produse noi") cu 9 `.product-item` in total, fiecare cu `.price` propriu, si
    ele apar INAINTEA grilei in sursa reala (offset 42974 vs 908892). Un selector
    nescopat le-ar prinde primele si ar amesteca recomandari in listarea de
    reduceri — a doua aparitie a capcanei pe domeniul asta, dupa cea de pe PDP
    consemnata in `notes`.

    Cele doua numere de mai jos sunt masurate pe `dumps_lst3/RJ2_listare_p1.html`.
    """
    from bs4 import BeautifulSoup

    fixture = _fixture("regatuljocurilor.ro")
    soup = BeautifulSoup(fixture, "html.parser")

    assert len(soup.select("#js-product-list .js-product-miniature")) == 20
    assert len(soup.select(".product-item")) == 9, \
        "caruselul e in fixture DELIBERAT — fara el testul n-ar dovedi nimic"
    assert not soup.select("#js-product-list .product-item"), \
        "caruselul e in AFARA grilei, deci scoparea singura il taie"

    carduri = extrage_carduri(fixture, listing_descriptor("regatuljocurilor.ro"),
                              "regatuljocurilor.ro")
    assert len(carduri) == 20, "descriptorul real vede doar grila"


def test_regatuljocurilor_valori_masurate_pe_primul_card():
    """Titlu / pret / referinta taiata, exact cum au fost masurate la LST-3.

    Pretul poarta NBSP intre suma si moneda („291,60\xa0RON"), forma pe care
    `_pret_eu_comma` o digera deja — e chiar cazul noriel din docstringul lui.
    Testul o pinuieste aici fiindca e primul domeniu cu NBSP *si* cu „RON" scris
    in litere langa suma.
    """
    carduri = extrage_carduri(_fixture("regatuljocurilor.ro"),
                              listing_descriptor("regatuljocurilor.ro"),
                              "regatuljocurilor.ro")

    primul = carduri[0]
    assert primul["title"] == "1989: Dawn of Freedom (2020 English Second Edition)"
    assert primul["price"] == 291.60
    assert primul["compare_at"] == 324.00
    assert primul["url"] == ("https://regatuljocurilor.ro/ro/acasa/"
                             "1989-dawn-of-freedom-2020-english-second-edition")
    assert all(c["price"] > 0 for c in carduri)


def test_regatuljocurilor_nbsp_trece_prin_eu_comma():
    """Forma verbatim din dump, izolata de restul cardului: daca parserul pierde
    vreodata tratarea NBSP-ului, testul asta cade primul si spune de ce."""
    assert _pret_eu_comma("291,60\xa0RON") == 291.60
    assert _pret_eu_comma("324,00\xa0RON") == 324.00


def test_regatuljocurilor_ramura_pret_plin_e_nemasurata_dar_nu_crapa():
    """LST-3, A3: pe AMBELE pagini masurate toate cele 20+20 de carduri au si
    `.price` si `.regular-price` — o pagina `prices-drop` nu serveste, prin
    definitie, carduri la pret plin. Ramura e deci NEMASURATA live.

    Ce se poate totusi dovedi offline e CONTRACTUL: cu un selector de compare care
    nu exista pe niciun card, `_pret_of` intoarce None (nodul lipsa iese pe
    `select_one`, fara exceptie) si cardul ramane valid cu pretul lui — nu se sare
    si nu crapa. Asta face ca absenta lui `.regular-price` sa fie sigura daca apare.
    """
    fixture = _fixture("regatuljocurilor.ro")
    descriptor = listing_descriptor("regatuljocurilor.ro")
    assert all(c["compare_at"] is not None
               for c in extrage_carduri(fixture, descriptor, "regatuljocurilor.ro")), \
        "linia de baza: 20/20 au referinta taiata"

    fara_compare = dict(descriptor)
    fara_compare["compare_text"] = ".nu-exista-pe-niciun-card"
    carduri = extrage_carduri(fixture, fara_compare, "regatuljocurilor.ro")

    assert len(carduri) == 20, "cardul supravietuieste fara referinta taiata"
    assert all(c["compare_at"] is None for c in carduri)
    assert all(c["price"] > 0 for c in carduri)


def test_regatuljocurilor_descriptorul_nu_declara_stoc_nici_insigna():
    """Doua absente DELIBERATE din descriptor, ca sa nu para omisiuni.

    (1) Fara `stock_attr`: listarea chiar contine epuizate („Nu este momentan in
        stoc"), dar semnalul e TEXT, iar schema n-are decat varianta pe atribut.
    (2) Fara ancorare pe `.discount-percentage`: insigna LIPSESTE pe carduri care
        au totusi `.regular-price` (masurat pe cardul 4), deci „e redus?" nu se
        poate citi de pe ea.
    """
    descriptor = listing_descriptor("regatuljocurilor.ro")
    assert "stock_attr" not in descriptor
    assert "stock_text" not in descriptor
    assert ".discount-percentage" not in str(descriptor)

    fixture = _fixture("regatuljocurilor.ro")
    assert "Nu este momentan in stoc" in fixture, \
        "epuizatele sunt in fixture: se ingereaza, inerte cat timp pretul e valid"

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fixture, "html.parser")
    carduri = soup.select("#js-product-list .js-product-miniature")
    fara_insigna = [c for c in carduri
                    if c.select_one(".regular-price") and not c.select_one(".discount-percentage")]
    assert fara_insigna, "cardul 4 masurat la LST-3: redus, dar fara insigna"


def test_regatuljocurilor_paginarea_din_registru_reproduce_url_ul_masurat():
    """`rel=next` de pe p1 arata verbatim spre `?page=2` (LST-3), iar p1 si p2 sunt
    disjuncte. Testul leaga template-ul din registru de URL-ul chiar masurat."""
    descriptor = listing_descriptor("regatuljocurilor.ro")
    assert descriptor["url"] == "https://regatuljocurilor.ro/ro/reduceri-de-pret"
    assert (listing_scanner._pagina_url(descriptor, 2)
            == "https://regatuljocurilor.ro/ro/reduceri-de-pret?page=2")
    assert descriptor["currency"] == "RON"
    assert descriptor["price_parse"] == "eu_comma"
    assert descriptor["reference_kind"] == "nemarcat"
