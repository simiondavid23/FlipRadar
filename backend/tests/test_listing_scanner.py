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

# Parserele de TEXT pe care un descriptor le poate numi. Citite din scanner, nu
# rescrise aici: o treapta noua adaugata acolo si uitata aici ar face garda sa
# respinga un descriptor perfect valid, iar una stearsa acolo ar trece nevazuta.
_PARSERE_ADMISE_TEXT = set(listing_scanner._PARSERE_TEXT)


def _fixture(domeniu: str) -> str:
    with open(os.path.join(FIXTURI, f"{domeniu}_cards.html"), encoding="utf-8") as f:
        return f.read()
def _fixture_stare(domeniu: str) -> str:
    """Fixture-ul de STARE al unui domeniu (`<domeniu>_state.html`).

    Separat de `_fixture` fiindca cele doua familii au sufixe diferite: calea CSS
    citeste `<domeniu>_cards.html`, calea de stare `<domeniu>_state.html`.
    """
    with open(os.path.join(FIXTURI, f"{domeniu}_state.html"),
              encoding="utf-8") as f:
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


def test_alte_statusuri_incheie_intrarea_dupa_o_pagina_buna(scan):
    """STATE-1 — regula de aici s-a SCHIMBAT, si merita spus de ce.

    Pana la STATE-1 testul asta cerea invers: „DOAR 404 e tolerat; un 403/500 pe
    pagina 2 e un zid sau o defectiune". Rationamentul era corect ca semantica —
    un 500 chiar NU e un sfarsit de paginare — dar gresit ca pret platit:
    `RuntimeError` cade INAINTE de `db.commit()`, deci un singur 500 la pagina 30
    arunca si cele 29 de pagini deja citite. prm serveste chiar asa (HTTP 500 la
    coada listarii, masurat la LST-D4), iar cu 44 de domenii pe axa un 5xx
    tranzitoriu nu mai e o ipoteza.

    Deci: pe pagina > 1, dupa cel putin o pagina reusita in ACEEASI intrare, orice
    non-200 incheie INTRAREA si lasa comis ce s-a citit. Ce ramane neschimbat e
    granita care conteaza — pe pagina 1 acelasi status ridica in continuare, si
    exista un test separat pentru asta (`test_5xx_pe_pagina_1_ridica`).

    Diferenta fata de 404 nu dispare, se muta in ZGOMOT: 404 se opreste tacut,
    restul scriu un WARN, fiindca sunt anomalii, nu granite normale.
    """
    for status in (403, 410, 500):
        rezumat = scan([_fixture("otter.ro"), (_CORP_404, status)],
                       descriptor=_descriptor_test())
        assert rezumat["erori"] == 0, (
            f"status {status} pe pagina 2 nu mai pierde scanul")
        assert rezumat["magazine"] == 1, f"status {status}: scanul s-a incheiat"


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
    intersport.ro (LST-2) + regatuljocurilor.ro (LST-3a) + modivo.ro (LST-3c) —
    toate trei intrate fara nicio linie de scanner — plus cele PATRU pe calea de
    stare: toolnation.nl (4a, care a cerut punctul de plug) si ro.vivre.eu /
    cellini.ro / bonami.ro (4b, intrate pe arhitectura deja existenta)."""
    assert listing_domains() == {"otter.ro", "caseking.de", "noriel.ro",
                                 "bergfreunde.eu", "tezyo.ro", "powerup.ro",
                                 "buzzsneakers.ro", "intersport.ro",
                                 "regatuljocurilor.ro", "modivo.ro",
                                 "toolnation.nl", "ro.vivre.eu", "cellini.ro",
                                 "bonami.ro",
                                 # DEAL-D1 — Bucket A al axei D, din sonda LST-D1.
                                 # sneakerindustry.ro NU e aici desi a fost sondat:
                                 # enumerarea lui Shopify s-a masurat DESCHISA, deci
                                 # a intrat pe `method: shopify`, nu pe descriptor.
                                 "zooplus.ro", "footlocker.ro", "forit.ro",
                                 "direct-running.com",
                                 # EMAG-D — primul descriptor pe forma `entries`
                                 # (12 categorii de resigilate).
                                 "emag.ro",
                                 # DEAL-D2 — lotul „electronice RO", din sonda
                                 # LST-D2. Cele cinci care au trecut controlul:
                                 # altex si mediagalaxy sunt frati de platforma
                                 # (descriptor identic in afara lui `url`), cel.ro
                                 # intra FARA referinta, itgalaxy e primul care
                                 # citeste pretul din atribut si referinta din
                                 # text, iar evomag a cerut treapta `eu_sup`.
                                 "altex.ro", "mediagalaxy.ro", "cel.ro",
                                 "itgalaxy.ro", "evomag.ro",
                                 # DEAL-D3 — lotul „jucarii + sneakers", din sonda
                                 # LST-D3. carrefour intra la a doua incercare (la
                                 # LST-D2 sonda alesese o pagina de regulamente),
                                 # brickdepot e primul magazin ROMANESC cu pret
                                 # zecimal cu punct (`us_dot`), iar carrefour e al
                                 # doilea consumator al treptei `eu_sup`.
                                 "carrefour.ro", "brickdepot.ro", "snipes.com",
                                 "sneakersnstuff.com", "footshop.ro",
                                 # DEAL-D4 - lotul „fashion + beauty", din sonda
                                 # LST-D4. nichiduta e al DOILEA descriptor pe
                                 # forma `entries` (17 fatete), dupa eMAG;
                                 # officeshoes a cerut cheia `title_from:
                                 # link_title`; epantofi e frate de platforma cu
                                 # modivo (eobuwie). Raman in afara: answear
                                 # (nicio candidata), trendyol (JS_ONLY), asos
                                 # (grila curata dar pe vitrina GBP) si marionnaud
                                 # (STATE, candidat de `state_extractor`).
                                 "aboutyou.ro", "fashiondays.ro", "epantofi.ro",
                                 "spartoo.ro", "officeshoes.ro", "prm.com",
                                 "notino.ro", "douglas.ro", "parfumdreams.de",
                                 "zalando.ro", "nichiduta.ro",
                                 # DEAL-D5 - coada axei D, din sonda LST-D5. Doar
                                 # doua din zece domenii sondate au trecut:
                                 # action.com (cu `max_pages` MASURAT prin
                                 # bisectie, fiindca plafoneaza la pagina 1 in loc
                                 # sa dea 404) si senetic.ro (re-masurat pe GRILA;
                                 # verdictul NEPOTRIVIT de la DEAL-D2 fusese dat pe
                                 # carusel). Raman in afara: trendyol
                                 # (CERE_MECANISM - `ld+json ItemList`),
                                 # foto-erhardt (NEPOTRIVIT: bucati unice, 0/155
                                 # taiate), alternate/flanco/hornbach/biciclop
                                 # (FARA_LISTARE), reichelt (JS_ONLY) si
                                 # computeruniverse (POARTA).
                                 "action.com", "senetic.ro",
                                 # STATE-1 - doua listari care nu sunt in DOM:
                                 # flip.ro (`__NEXT_DATA__`, cache react-query) si
                                 # marionnaud.ro (blob `application/json`,
                                 # SAP Commerce). Cu ele, familia
                                 # `state_extractor` ajunge la SASE.
                                 "flip.ro", "marionnaud.ro",
                                 # STATE-2 - doua listari SSR pe care JSON-0 le
                                 # cautase (gresit) ca API-uri. altex si
                                 # mediagalaxy NU sunt aici: erau deja in lista de
                                 # la DEAL-D2, si doar au trecut de pe calea CSS pe
                                 # `altex_next`. Raman in afara, ca ziduri masurate
                                 # in browser: sizeer (403 Akamai), bstn (403) si
                                 # sivasdescalzo (Cloudflare Turnstile).
                                 "sportvision.ro", "booztlet.com",
                                 # DEAL-D6 - doua domenii pe care sondele
                                 # anterioare le respinsesera pe masuratori
                                 # gresite. lego.com intra pe STARE (cache Apollo,
                                 # al OPTULEA `state_extractor`) si e primul
                                 # magazin cu `entries` din DOUA sectiuni ale
                                 # aceleiasi vitrine - categoria de reduceri,
                                 # gasita in cache la DEAL-D6 dupa ce DEAL-D3 o
                                 # declarase inexistenta, plus campania.
                                 # 43einhalb.com intra pe CSS, fara nicio linie de
                                 # cod: „duplicatele responsive" erau carduri de
                                 # megameniu, deci a fost de ajuns un selector
                                 # scopat la `#prodList`. sizeer.ro RAMANE afara,
                                 # dar acum cu dovada: pe HTTP poarta e deschisa
                                 # (200, 1,71 MB) si totusi grila nu e servita -
                                 # zero bloburi de stare, deci JS_ONLY.
                                 "lego.com", "43einhalb.com"}


def test_descriptorul_e_copie_nu_referinta():
    """Scannerul plimba descriptorul prin functii; o referinta ar lasa un bug de
    acolo sa rescrie registrul pentru tot procesul."""
    d = listing_descriptor("otter.ro")
    d["card"] = "MUTAT"

    assert listing_descriptor("otter.ro")["card"] == "li.product-item"


def test_fiecare_descriptor_are_cheile_obligatorii():
    """VAL D runda 4a — contractul are acum DOUA cai, si exact una per descriptor.

    Cheile comune raman comune. Peste ele, un descriptor descrie ori o listare in
    DOM (selectori CSS: `card` + `price_parse`), ori una in STARE
    (`state_extractor`). Regula e SAU-EXCLUSIV, nu „macar una": un descriptor cu
    ambele ar fi ambiguu — plugul din `extrage_carduri` ar prefera tacut starea si
    selectorii ar deveni cod mort care pare viu.
    """
    from app.services.listing_state_extractors import LISTING_STATE_EXTRACTORS

    for domeniu in listing_domains():
        d = listing_descriptor(domeniu)
        _verifica_descriptor(domeniu, d)


def _verifica_descriptor(domeniu, d):
    """Contractul unui descriptor de listare. Extras din bucla la EMAG-D ca sa
    poata fi chemat SI pe dicturi sintetice — o garda care se poate verifica doar
    pe registrul real n-are cum sa dovedeasca ce RESPINGE."""
    from app.services.listing_state_extractors import LISTING_STATE_EXTRACTORS

    for cheie in ("max_pages", "currency", "reference_kind"):
        assert d.get(cheie), f"{domeniu} nu are `{cheie}`"
    assert d["reference_kind"] in {"prp", "min30", "nemarcat"}
    # DEAL-D4 — `title_from` e optional, dar cand exista trebuie sa numeasca un mod
    # pe care `_titlu_of` chiar il stie: o valoare necunoscuta ar cadea TACUT pe
    # selectorul `title`, adica exact felul de descriptor care pare sa mearga.
    if d.get("title_from"):
        assert d["title_from"] in {"link_aria_label", "link_title"}, (
            f"{domeniu}: `title_from` necunoscut {d['title_from']!r}")

    # EMAG-D — intrarile: ori `url`, ori `entries`, niciodata amandoua si
    # niciodata niciuna. Ambele deodata ar fi ambiguu exact ca `card` +
    # `state_extractor`: `_intrari` prefera tacut `entries`, iar `url` ar deveni
    # configuratie moarta care pare vie.
    are_url = bool(d.get("url"))
    are_entries = "entries" in d
    assert are_url != are_entries, (
        f"{domeniu}: exact una din `url` / `entries`, nu ambele si nu niciuna")

    if are_entries:
        assert d["entries"], f"{domeniu}: `entries` gol"
        for i, intrare in enumerate(d["entries"]):
            assert intrare.get("url"), f"{domeniu}: intrarea {i} n-are `url`"
            # Plafonul EFECTIV al intrarii decide, nu cel scris: o intrare fara
            # `max_pages` mosteneste plafonul descriptorului, deci poate avea
            # nevoie de template chiar daca nu-si declara niciun numar.
            efectiv = int(intrare.get("max_pages") or d["max_pages"])
            _verifica_paginare(f"{domeniu}: intrarea {i}", intrare, efectiv)
    else:
        _verifica_paginare(domeniu, d, int(d["max_pages"]))

    pe_stare = bool(d.get("state_extractor"))
    pe_css = bool(d.get("card"))
    assert pe_stare != pe_css, (
        f"{domeniu}: exact una din `card` / `state_extractor`, nu ambele si nu "
        f"niciuna")
    if pe_stare:
        assert d["state_extractor"] in LISTING_STATE_EXTRACTORS, (
            f"{domeniu}: `state_extractor` necunoscut in registru")
        for interzisa in ("card", "link", "title", "price_text", "price_attr",
                          "compare_text", "compare_attr", "price_parse"):
            assert interzisa not in d, (
                f"{domeniu}: `{interzisa}` n-are sens pe calea de stare")
    else:
        assert d.get("price_parse"), f"{domeniu} nu are `price_parse`"
        if d.get("price_attr"):
            assert d["price_parse"] == "attr_float", (
                f"{domeniu}: `price_attr` merge prin parserul strict, deci "
                f"`price_parse` trebuie sa fie `attr_float`")
            # DEAL-D2 — cand pretul vine din atribut dar REFERINTA din text, o
            # singura cheie n-are cum sa descrie amandoua caile: `attr_float` ar
            # ajunge in `_PARSERE_TEXT` si ar ridica ValueError la primul card.
            # Latura de referinta trebuie deci sa-si declare parserul ei
            # (itgalaxy.ro, primul descriptor care amesteca cele doua cai).
            if d.get("compare_text"):
                assert d.get("compare_parse") in _PARSERE_ADMISE_TEXT, (
                    f"{domeniu}: `price_attr` + `compare_text` cere "
                    f"`compare_parse` din {sorted(_PARSERE_ADMISE_TEXT)}, "
                    f"nu {d.get('compare_parse')!r}")
        else:
            assert d["price_parse"] in _PARSERE_ADMISE_TEXT, (
                f"{domeniu}: pe `price_text` valorile admise sunt "
                f"{' / '.join(sorted(_PARSERE_ADMISE_TEXT))}, "
                f"nu {d['price_parse']!r}")
        # `compare_parse` e optional peste tot, dar cand exista trebuie sa
        # numeasca un parser de TEXT real.
        if d.get("compare_parse"):
            assert d["compare_parse"] in _PARSERE_ADMISE_TEXT, (
                f"{domeniu}: `compare_parse` necunoscut "
                f"{d['compare_parse']!r}")


def _verifica_paginare(eticheta, sursa, max_pages):
    """`page_url_template` e obligatoriu EXACT cand scannerul chiar il citeste:
    `_pagina_url` intoarce `url` pentru pagina 1 si abia de la 2 in sus formateaza
    template-ul. Un domeniu masurat ca PAGINA-UNICA (bonami: `nextPagePath` None,
    zero `rel=next`, zero `?page=`) are `max_pages: 1`, deci bucla face o singura
    tura si template-ul n-ar fi citit niciodata — a-l cere ar insemna sa inventam
    un URL nemasurat doar ca sa treaca garda."""
    if max_pages > 1:
        assert sursa.get("page_url_template"), f"{eticheta} nu are `page_url_template`"
        assert "{n}" in sursa["page_url_template"]
    else:
        assert "page_url_template" not in sursa, (
            f"{eticheta}: max_pages=1 dar declara un template care nu se citeste")


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


# ── LST-3c — modivo.ro (eobuwie / Nuxt, fateta `omnibus_discount`) ───────────
def test_modivo_grila_intreaga_masurata_la_lst3b():
    """LST-3b: pagina 1 a fatetei de reduceri, INTREAGA, 73 de carduri.

    Ca la intersport, decupajul ar transforma in proxy chiar invariantele masurate:
    73 pe pagina (cifra care inchide si totalul — `offerCount` 1490 / 73 ≈ 21 de
    pagini, iar linkurile din DOM merg pana la `p=21`), referinta Omnibus pe 73/73,
    si divergenta celor doua linii pe 32 din 73.
    """
    fixture = _fixture("modivo.ro")
    carduri = extrage_carduri(fixture, listing_descriptor("modivo.ro"), "modivo.ro")

    assert len(carduri) == 73
    assert all(c["compare_at"] is not None for c in carduri), \
        "referinta Omnibus e pe 73/73 — o fateta de reduceri n-are carduri la pret plin"
    assert all(c["price"] > 0 for c in carduri)
    assert all(c["compare_at"] > c["price"] for c in carduri), \
        "ambele referinte sunt strict peste pretul curent — masurat pe 146/146 la LST-3b"

    primul = carduri[0]
    assert primul["title"] == "G-STAR Blugi · Bleumarin · Relaxed Fit"
    assert primul["price"] == 659.90
    assert primul["compare_at"] == 732.90


def test_modivo_compare_ia_linia_a_doua_cel_mai_mic_pret():
    """Miezul rundei: `.omnibus` are DOUA linii etichetate, iar alegerea schimba marja.

    Pe cardul 13 al fixture-ului („Polo Ralph Lauren Pulover") ele DIVERG:
        „Prețul inițial"   1.378,90 Lei
        „Cel mai mic preț" 1.129,90 Lei      <- asta se ia
    la un pret curent de 1.072,90 Lei. Daca descriptorul ar cadea pe prima linie,
    `compare_at` ar fi 1378.9 si marja raportata ar fi umflata cu ~23 de puncte.
    Divergenta e masurata pe 32 din 73 de carduri, deci nu e un caz izolat.
    """
    fixture = _fixture("modivo.ro")
    carduri = extrage_carduri(fixture, listing_descriptor("modivo.ro"), "modivo.ro")

    card = carduri[13]
    assert card["title"] == "Polo Ralph Lauren Pulover · Alb · Slim Fit"
    assert card["price"] == 1072.90
    assert card["compare_at"] == 1129.90, "linia 2 = Cel mai mic pret"
    assert card["compare_at"] != 1378.90, "NU linia 1 = Pretul initial"


def test_modivo_linia_a_doua_chiar_poarta_eticheta_cel_mai_mic_pret():
    """`:nth-child(2)` e POZITIONAL — eticheta e un nod-text, neselectabil CSS. Deci
    pozitia se pinuieste pe TEXT, nu invers: daca platforma inverseaza liniile sau
    materializeaza placeholderul Vue `<!-- -->` din `.omnibus`, testul asta cade
    inaintea oricarui scan si spune exact unde s-a mutat referinta."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_fixture("modivo.ro"), "html.parser")
    carduri = soup.select(".product-card-small")
    assert len(carduri) == 73

    for card in carduri:
        linii = card.select(".omnibus .line")
        assert len(linii) == 2
        assert "Prețul inițial" in linii[0].get_text(" ", strip=True)
        assert "Cel mai mic preț" in linii[1].get_text(" ", strip=True)

    divergente = [c for c in carduri
                  if c.select(".omnibus .line")[0].select_one(".value").get_text(strip=True)
                  != c.select(".omnibus .line")[1].select_one(".value").get_text(strip=True)]
    assert len(divergente) == 32, \
        "divergenta masurata la LST-3b — fara ea testul de mai sus n-ar dovedi nimic"


def test_modivo_eu_comma_digera_separatorul_de_mii_si_nbsp():
    """Doua forme masurate pe acelasi domeniu, in noduri DIFERITE: pretul platit are
    separator de mii cu punct dar spatii normale („1.072,90 Lei", 15 din 73 de
    carduri), iar referinta are si NBSP („1.129,90\xa0Lei"). Ambele prin acelasi
    parser. Textul pretului include si eticheta sr-only „Prețul actual" — inofensiva
    fiindca n-are nicio cifra."""
    assert _pret_eu_comma("Prețul actual 1.072,90 Lei") == 1072.90
    assert _pret_eu_comma("1.129,90\xa0Lei") == 1129.90
    assert _pret_eu_comma("Prețul actual 659,90 Lei") == 659.90


def test_modivo_ldjson_e_capcana_de_pret_nu_sursa():
    """Singurul `Product` din ld+json e la nivel de CATEGORIE: `name: "Femei"` cu un
    `AggregateOffer` `lowPrice: 55`. Citit ca pret de produs ar da 55 de lei pe orice
    card — de aici `price_text` pe DOM, desi domeniul e `method: jsonld` pe axa L.
    Blocurile sunt in fixture tocmai ca sa se vada capcana."""
    import json as _json

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_fixture("modivo.ro"), "html.parser")
    blocuri = [_json.loads(s.string, strict=False)
               for s in soup.select('script[type="application/ld+json"]')]
    produse = [b for b in blocuri if b.get("@type") == "Product"]

    assert len(produse) == 1, "un singur Product, si ala e categoria"
    assert produse[0]["name"] == "Femei"
    assert produse[0]["offers"]["@type"] == "AggregateOffer"
    assert produse[0]["offers"]["lowPrice"] == 55
    assert produse[0]["offers"]["offerCount"] == 1490, "singura sursa a totalului"

    descriptor = listing_descriptor("modivo.ro")
    assert "price_text" in descriptor and "price_attr" not in descriptor

    colectie = [b for b in blocuri if b.get("@type") == "CollectionPage"][0]
    primul = colectie["mainEntity"]["itemListElement"][0]["item"]["name"]
    assert "Jeansy" in primul, "ItemList-ul e in poloneza netradusa — nici el nu e titlu"


def test_modivo_price_wrapper_discount_nu_e_semnal_de_reducere():
    """Clasa `discount` e pusa de componenta, nu de starea produsului: aici e pe
    73/73, dar pe categoria masurata GRESIT la LST-3 era pe 70 din 72 de carduri cu
    ZERO preturi taiate. Semnalul bun e prezenta blocului `.omnibus`."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_fixture("modivo.ro"), "html.parser")
    assert len(soup.select(".price-wrapper.discount")) == 73
    assert len(soup.select(".product-card-small .omnibus")) == 73
    assert ".price-wrapper" not in str(listing_descriptor("modivo.ro"))


def test_modivo_paginarea_din_registru_reproduce_url_ul_masurat():
    """Fateta canonica, FARA parametrii `itm_*` de atributie, si `?p={n}` — exact ce
    a dat 200 la LST-3b pe ambele capete (`rel=next` pe p1, `rel=prev` pe p2)."""
    descriptor = listing_descriptor("modivo.ro")
    baza = "https://modivo.ro/c/femei/akcja:new_sale/omnibus_discount:~r-5-99"

    assert descriptor["url"] == baza
    assert listing_scanner._pagina_url(descriptor, 2) == baza + "?p=2"
    assert "itm_source" not in descriptor["page_url_template"]
    assert descriptor["currency"] == "RON"
    assert descriptor["reference_kind"] == "min30"


# ── VAL D runda 4a — punctul de plug al extractoarelor de stare ──────────────
def test_state_extractor_preia_locul_selectorilor_css(monkeypatch):
    """T-arh: cand descriptorul declara `state_extractor`, bucla de scan NU mai
    atinge selectorii CSS — deleaga extractorului inregistrat.

    Asertia e pe APEL, cu un extractor fals inregistrat in registru: daca plugul
    s-ar face altundeva (sau deloc), `chemat` ramane gol si testul cade."""
    from app.services import listing_state_extractors as lse

    chemat = {}

    def fals(html, descriptor):
        chemat["html"] = html
        chemat["descriptor"] = descriptor
        return [{"url": "https://x.ro/p/1", "external_id": "lst:fals",
                 "handle": "/p/1", "title": "T", "price": 1.0, "compare_at": None}]

    monkeypatch.setitem(lse.LISTING_STATE_EXTRACTORS, "_fals_de_test", fals)

    descriptor = {"state_extractor": "_fals_de_test", "currency": "RON",
                  # selectori DELIBERAT imposibili: daca ar fi folositi, ies 0 carduri
                  "card": "nu.exista", "link": "nu.exista", "price_text": "nu.exista"}
    carduri = extrage_carduri("<html>marcaj</html>", descriptor, "x.ro")

    assert chemat["html"] == "<html>marcaj</html>", "extractorul primeste HTML-ul brut"
    assert chemat["descriptor"] is descriptor, "si descriptorul, pentru campurile lui"
    assert len(carduri) == 1 and carduri[0]["external_id"] == "lst:fals"


class _RegistruExploziv(dict):
    """Dict care refuza orice citire — dovedeste ca nici macar nu e consultat."""

    def __getitem__(self, cheie):                # pragma: no cover
        raise AssertionError(f"registrul de stare consultat pentru {cheie!r}")

    def __contains__(self, cheie):               # pragma: no cover
        raise AssertionError(f"registrul de stare consultat pentru {cheie!r}")


def test_fara_state_extractor_calea_css_e_neatinsa(monkeypatch):
    """Reversul: un descriptor FARA cheia noua nu trebuie sa treaca nici macar pe
    langa registrul de stare. Daca cineva inverseaza conditia, testul cade."""
    from app.services import listing_state_extractors as lse

    monkeypatch.setattr(lse, "LISTING_STATE_EXTRACTORS", _RegistruExploziv())

    carduri = extrage_carduri(_fixture("otter.ro"), listing_descriptor("otter.ro"),
                              "otter.ro")
    assert len(carduri) == 3, "otter iese exact ca inainte, pe selectori"


@pytest.mark.parametrize("domeniu,asteptat", [
    ("otter.ro", 3), ("caseking.de", 3), ("noriel.ro", 3), ("bergfreunde.eu", 3),
    ("tezyo.ro", 3), ("powerup.ro", 3), ("buzzsneakers.ro", 3),
    ("intersport.ro", 30), ("regatuljocurilor.ro", 20), ("modivo.ro", 73),
])
def test_regresie_toate_fixture_urile_pe_calea_css(domeniu, asteptat):
    """T-regresie: dupa adaugarea plugului, FIECARE fixture existent trebuie sa dea
    exact aceleasi carduri ca inainte. Predictia e ZERO diferente — niciunul dintre
    cele 10 descriptoare nu declara `state_extractor`, deci niciunul nu intra pe
    ramura noua. Numerele de mai jos sunt cele masurate INAINTE de runda 4a."""
    descriptor = listing_descriptor(domeniu)
    assert "state_extractor" not in descriptor

    carduri = extrage_carduri(_fixture(domeniu), descriptor, domeniu)

    assert len(carduri) == asteptat
    assert all(set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at", "image_url"} for c in carduri)
    assert all(c["price"] > 0 for c in carduri)


# ── IMG-1b: extractia imaginii pe calea CSS ─────────────────────────────────

CSS_CU_POZA = ["bergfreunde.eu", "buzzsneakers.ro", "caseking.de", "intersport.ro",
               "modivo.ro", "noriel.ro", "otter.ro", "powerup.ro",
               "regatuljocurilor.ro", "tezyo.ro"]


@pytest.mark.parametrize("domeniu", CSS_CU_POZA)
def test_img1b_toate_cardurile_css_au_poza(domeniu):
    """T1 — pe TOATE cele zece domenii cu selector CSS, FIECARE card iese cu o poza
    absoluta, si nu una dintre capcanele masurate de sonde.

    Cele trei excluderi nu sunt decorative, fiecare e o capcana reala:
      * `placeholder`/`lazyimage` — intersport are acelasi fisier fix in `src` pe
        toate cardurile, deci un extractor care ia `src` ar raporta 30 de poze
        identice si ar parea ca merge;
      * `label_` — otter si tezyo pun 2-4 INSIGNE (`label_nou_1.png`) ca primele
        `<img>` din card, inaintea fotografiei;
      * `.svg` — caseking are eticheta energetica drept al doilea `<img>`.
    """
    carduri = extrage_carduri(_fixture(domeniu), listing_descriptor(domeniu), domeniu)

    assert carduri, "fixture-ul trebuie sa produca carduri"
    for c in carduri:
        poza = c["image_url"]
        assert poza, f"{domeniu}: card fara poza -> {c['url']}"
        assert poza.startswith("https://"), f"{domeniu}: poza neabsoluta -> {poza}"
        for capcana in ("placeholder", "lazyimage", "label_"):
            assert capcana not in poza.lower(), f"{domeniu}: {capcana} in {poza}"
        assert not poza.split("?")[0].lower().endswith(".svg"), poza


@pytest.mark.parametrize("brut, asteptat", [
    # srcset: primul candidat, fara descriptorul de latime (caseking)
    ("https://a/b.jpg 150w, https://a/c.jpg 300w", "https://a/b.jpg"),
    ("https://a/b.jpg 2x", "https://a/b.jpg"),
    # protocol-relativ (intersport) si relativ la radacina (buzzsneakers)
    ("//cdn.x/b.jpg", "https://cdn.x/b.jpg"),
    ("/files/b.jpg", "https://exemplu.ro/files/b.jpg"),
    ("https://a/b.jpg?lm=deadbeef", "https://a/b.jpg?lm=deadbeef"),
    # IMG-1b2 — markerii se potrivesc pe TOKEN, deci un cuvant care doar ii CONTINE
    # nu mai respinge poza. Amandoua erau respinse inainte, tacut.
    ("https://x/media/sleeping-blanket-blue.jpg",
     "https://x/media/sleeping-blanket-blue.jpg"),          # „blank" in „blanket"
    ("https://x/a/unloading-dock.jpg",
     "https://x/a/unloading-dock.jpg"),                     # „loading" in „unloading"
])
def test_img1b_normalizator_forme_acceptate(brut, asteptat):
    """T2 — cele patru forme masurate de sonde ajung la acelasi URL absolut."""
    assert listing_scanner.normalizeaza_imagine(brut, "exemplu.ro") == asteptat


@pytest.mark.parametrize("brut", [
    None, "", "   ",
    "data:image/gif;base64,R0lGODlh",                     # placeholder inline
    "https://a/lazyimage/photogallerynormal.jpg",         # intersport, src fix
    "https://a/placeholder/default/no-image-2_3.jpg",     # toolnation, ld+json
    "https://a/b.svg",                                    # caseking, eticheta energetica
    "https://a/b.gif",
    "poza.jpg",                                           # nume gol, fara baza masurata
    # IMG-1b2 — token-ul CHIAR delimitat ramane respins, pe toti delimitatorii.
    "https://x/img/blank.gif",                            # respins de extensie
    "https://x/img/blank.jpg",                            # respins de token
    "https://x/lazyimage/photogallerynormal.jpg",         # token intre doua `/`
    "https://x/no-image.jpg",                             # token cu cratima
])
def test_img1b_normalizator_respinge(brut):
    """T2 — tot ce nu e o fotografie de produs utilizabila iese None, nu un URL rupt."""
    assert listing_scanner.normalizeaza_imagine(brut, "exemplu.ro") is None


# ── DEAL-D1 — Bucket A al axei D (sonda LST-D1, 2026-09-07) ──────────────────
#
# Cele patru fixture-uri de mai jos sunt fragmente DECUPATE din dump-urile
# `dumps_lstd1/<domeniu>_p1.html` (taietorul: `scripts/diagnostics/
# taie_fixtures_deald1.py`), iar valorile asteptate sunt exact cele masurate in
# raportul sondei. Toate testele trec prin `extrage_carduri()` cu descriptorul
# DIN REGISTRU, niciodata cu unul copiat aici: un descriptor copiat ar continua
# sa treaca dupa ce cel real s-ar strica, ceea ce e opusul unei gardei.


def test_pret_us_dot():
    """Treapta noua, pe cele cinci forme masurate.

    `1,299.00` conteaza cel mai mult dintre ele: e singura care dovedeste ca
    VIRGULA se sterge ca separator de mii. Fara acea stergere valoarea ar iesi
    None (nu 1299.0), fiindca `fullmatch` respinge virgula ramasa — deci un card
    de peste o mie de dolari ar disparea tacut din feed, nu ar aparea gresit.
    """
    from app.services.listing_scanner import _pret_us_dot

    assert _pret_us_dot("$117.63") == 117.63
    assert _pret_us_dot("$1,299.00") == 1299.0
    assert _pret_us_dot("170.00") == 170.0
    assert _pret_us_dot("$") is None, "fara cifre nu e pret, e simbol"
    assert _pret_us_dot("12.34.56") is None, "doua puncte zecimale nu sunt un numar"


def test_pret_of_alege_parserul_din_price_parse():
    """ACELASI fragment, doua valori, in functie de un singur camp de registru.

    Asta e defectul pe care treapta il evita, scris ca test: `$117.63` citit cu
    parserul european da 11763.0 — de 100x prea mult, si perfect plauzibil intr-un
    feed de sneakers. Nu se poate deduce din sir care parser e corect (`1.299,00`
    si `1,299.00` inseamna acelasi lucru cu separatorii inversati), deci alegerea
    trebuie sa vina din registru; testul pinuieste ca ea CHIAR e citita.
    """
    from bs4 import BeautifulSoup

    from app.services.listing_scanner import _pret_of

    card = BeautifulSoup(
        '<div><span class="price">$117.63</span></div>', "html.parser").div

    assert _pret_of(card, {"price_text": ".price", "price_parse": "us_dot"},
                    "price_attr", "price_text", "direct-running.com") == 117.63
    assert _pret_of(card, {"price_text": ".price", "price_parse": "eu_comma"},
                    "price_attr", "price_text", "direct-running.com") == 11763.0
    # Absent = eu_comma, pentru cei zece descriptori CSS scrisi inaintea DEAL-D1.
    assert _pret_of(card, {"price_text": ".price"},
                    "price_attr", "price_text", "x.ro") == 11763.0


def test_price_parse_necunoscut_cade_zgomotos():
    """O valoare necunoscuta ridica, nu cade inapoi pe un implicit.

    Un fallback tacut ar transforma o greseala de tastare in registru intr-un feed
    intreg de preturi gresite care arata normal. Asa, scanul domeniului moare la
    primul card si apelantul ii scrie esecul in `ShopScanState`, fara sa opreasca
    celelalte magazine.
    """
    descriptor = dict(listing_descriptor("direct-running.com"))
    descriptor["price_parse"] = "xyz"

    with pytest.raises(ValueError) as exc:
        extrage_carduri(_fixture("direct-running.com"), descriptor,
                        "direct-running.com")

    assert "xyz" in str(exc.value)
    assert "direct-running.com" in str(exc.value), "mesajul trebuie sa spuna CINE"


def test_zooplus_pret_din_meta_fara_compare():
    """zooplus: pretul din atribut, si NICIUN pret taiat — deliberat.

    Fixture-ul are doua carduri anume: unul CU referinta in DOM (`Individual`,
    23,70 lei) si unul fara. `compare_at` trebuie sa iasa None pe AMANDOUA. Daca
    ar iesi None doar pe al doilea, testul n-ar dovedi nimic: ar putea insemna
    „nu era nimic de citit", nu „am ales sa nu citim". Referinta aia e suma
    acelorasi produse cumparate separat, nu un pret anterior — citita ca
    `compare_at`, ar fabrica un deal pe fiecare multipack.
    """
    carduri = extrage_carduri(_fixture("zooplus.ro"),
                              listing_descriptor("zooplus.ro"), "zooplus.ro")

    assert len(carduri) == 2
    assert all(c["compare_at"] is None for c in carduri), \
        "referinta `Individual` NU se citeste, nici acolo unde exista"

    primul = carduri[0]
    assert primul["price"] == 20.9, "din meta[itemprop=price] content=20.9"
    assert primul["title"] == "Felix KnabberMix Grill (3 x 60 g)"
    assert primul["image_url"].startswith("https://media.zooplus.com/")

    # Perechea afirmatiei de mai sus: nodul de referinta CHIAR e in fixture. Fara
    # asta, `compare_at is None` s-ar putea multumi cu un fixture din care
    # referinta lipseste, iar in ziua in care descriptorul ar capata din greseala
    # un `compare_text`, garda ar tacea. Eticheta se pinuieste fiindca ea e
    # argumentul: daca zooplus trece de la `Individual` la „Pret normal", decizia
    # de a nu citi campul trebuie recantarita, si aici se vede prima.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_fixture("zooplus.ro"), "html.parser")
    cu_referinta = [c for c in soup.select("[data-zta='product-card']")
                    if c.select_one("[data-zta='reducedPriceRefPriceAmount']")]
    assert len(cu_referinta) == 1, "fixture-ul are exact un card CU referinta"
    assert "23,70" in cu_referinta[0].select_one(
        "[data-zta='reducedPriceRefPriceAmount']").get_text()
    assert cu_referinta[0].select_one(
        "[data-zta='reducedPriceRefPriceLabel']").get_text(strip=True) == "Individual"


def test_footlocker_prp_egal_cu_pretul():
    """footlocker: referinta exista, e etichetata, si totusi nu produce niciun deal.

    Pe cele 60 de carduri masurate la LST-D1 pretul curent era IDENTIC cu cel
    recomandat. Testul pinuieste egalitatea ca fapt, nu ca defect: `compare_at ==
    price` inseamna ca R1 nu califica (pragul cere o marja), deci baseline-ul
    tacut al primului scan e asteptat, nu un simptom.
    """
    carduri = extrage_carduri(_fixture("footlocker.ro"),
                              listing_descriptor("footlocker.ro"),
                              "footlocker.ro")

    assert len(carduri) == 1
    c = carduri[0]
    assert c["price"] == 274.99
    assert c["compare_at"] == 274.99, "PRP == pretul platit: categoria n-avea reduceri"
    assert c["title"] == "adidas Taekwondo Shoes"
    assert c["url"] == ("https://footlocker.ro/ro/special-prices/"
                        "adidas-adidas-taekwondo-shoes_1202852/")
    # `src` e protocol-relativ in dump (`//footlockerroazure.lhscdn.com/...`).
    assert c["image_url"].startswith("https://footlockerroazure.lhscdn.com/")


def test_forit_pret_spart_si_old_price():
    """forit: pretul e SPART intre noduri, iar taiatul e rar (4 din 60).

    HANNSpad-ul are `1.393,94` in `div.p-price` si „ lei" intr-un `span.cur`
    copil: o citire pe textul PROPRIU al nodului n-ar gasi nicio moneda si ar
    rata cardul. Asus-ul are si `div.p-price-old`, deci fixture-ul acopera
    ambele stari cu acelasi descriptor.
    """
    carduri = extrage_carduri(_fixture("forit.ro"),
                              listing_descriptor("forit.ro"), "forit.ro")

    assert len(carduri) == 2
    hannspad, asus = carduri

    assert hannspad["price"] == 1393.94
    assert hannspad["compare_at"] is None, "cardul asta n-are `p-price-old`"
    assert "Desigilata" in hannspad["title"], \
        "starea de resigilat ajunge in feed prin TITLU (57/60 la LST-D1)"

    assert asus["price"] == 4435.30
    assert asus["compare_at"] == 5092.74
    assert asus["compare_at"] > asus["price"]


def test_direct_running_us_dot_prin_registru():
    """direct-running: singurul consumator al treptei `us_dot`, prin registru.

    Verifica si ca o singura intrare iese dintr-un card cu PATRU ancore catre
    trei tinte (poza, „+-3 culori", titlul si `/brands/adidas`): daca `link` ar
    fi un `a[href]` generic, cardul ar putea ajunge in feed sub URL-ul marcii.
    """
    carduri = extrage_carduri(_fixture("direct-running.com"),
                              listing_descriptor("direct-running.com"),
                              "direct-running.com")

    assert len(carduri) == 1, "un card = o intrare, desi are 4 ancore"
    c = carduri[0]
    assert c["price"] == 117.63, "cu eu_comma ar fi iesit 11763.0"
    assert c["compare_at"] == 170.0
    assert c["title"] == "Puffer jacket Helionic"
    assert c["url"] == ("https://direct-running.com/"
                        "jn2099-puffer-jacket-adidas-helionic-black")
    assert "/brands/" not in c["url"]


def test_pagina_url_forit_si_footlocker():
    """Cele doua forme de paginare in CALE, pinuite din registru.

    Pagina 1 e URL-ul MASURAT, nu template-ul cu n=1 — `/resigilate/p1/c` si
    `/special-prices/p1/` n-au fost cerute niciodata, deci nu se presupune ca
    exista. Coada `/c` a lui forit e neobisnuita si tocmai de aceea se pinuieste:
    fara ea, cererea cade pe alt URL si scanul se opreste dupa prima pagina.
    """
    forit = listing_descriptor("forit.ro")
    assert listing_scanner._pagina_url(forit, 1) == "https://www.forit.ro/resigilate/"
    assert listing_scanner._pagina_url(forit, 2) == "https://www.forit.ro/resigilate/p2/c"

    fl = listing_descriptor("footlocker.ro")
    assert listing_scanner._pagina_url(fl, 1) == \
        "https://www.footlocker.ro/ro/special-prices/"
    assert listing_scanner._pagina_url(fl, 2) == \
        "https://www.footlocker.ro/ro/special-prices/p2/"


def test_istyle_pe_shopify():
    """istyle.ro: `jsonld` -> `shopify` la DEAL-D1, dupa ce sonda a masurat
    enumerarea deschisa. Moneda e obligatorie pe calea shopify — payload-ul nu
    o poarta, extractorul o citeste din registru — iar `listing` ar fi de
    prisos: enumerarea acopera catalogul, nu doar grila de reduceri."""
    from app.services.shop_registry import SHOP_REGISTRY, shopify_domains

    assert "istyle.ro" in shopify_domains()
    assert SHOP_REGISTRY["istyle.ro"]["currency"] == "RON"
    assert "istyle.ro" not in listing_domains()


def test_sneakerindustry_pe_shopify():
    """sneakerindustry.ro: `og` -> `shopify`, a doua corectie de platforma pe
    acelasi domeniu si in sens invers fata de prima (SNK-1 il mutase de pe
    Shopify pe PrestaShop). Descriptorul CSS masurat de LST-D1 §2.3 ramane in
    raport ca rezerva, dar NU in registru: enumerarea deschisa il face inutil."""
    from app.services.shop_registry import SHOP_REGISTRY, shopify_domains

    assert "sneakerindustry.ro" in shopify_domains()
    assert SHOP_REGISTRY["sneakerindustry.ro"]["currency"] == "RON"
    assert "sneakerindustry.ro" not in listing_domains()


# ── EMAG-D — lista de intrari per descriptor + eMAG Resigilate ───────────────
#
# Fixture-ul `emag.ro_cards.html` e decupat din `scripts/diagnostics/
# dumps_emag_rs/emag.ro_rs_listare.html` (20 august): trei carduri intregi, al
# doilea cu `<p class="pricing rrp"></p>` GOL — cazul real in care nodul de
# referinta exista dar n-are valoare, masurat pe 1 din 60.

def _descriptor_entries(intrari, max_pages=5):
    """Descriptor de test pe forma `entries`, cu selectorii otter (fixture-ul lui
    e cel folosit de restul testelor de scan)."""
    return {"entries": intrari, "max_pages": max_pages, "currency": "RON",
            "card": "li.product-item", "link": "a.product-item-photo",
            "title": "h3.product-item-name",
            "price_attr": ("[data-price-type='finalPrice']", "data-price-amount"),
            "compare_attr": ("[data-price-type='oldPrice']", "data-price-amount"),
            "price_parse": "attr_float", "reference_kind": "prp"}


def _scaneaza_direct(monkeypatch, pagini, descriptor):
    """`_scaneaza_domeniu` chemat direct, cu fetch-ul stub-uit.

    `run_listing_scan` intoarce un rezumat pe MAGAZINE si inghite exceptiile per
    domeniu; contoarele care dovedesc semantica per-intrare (`pagini`, `produse`)
    sunt in valoarea de retur a functiei de dedesubt. De aceea testele de intrari
    coboara un nivel.
    """
    cereri = []

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        indice = len(cereri) - 1
        pagina = pagini[indice] if indice < len(pagini) else "<html></html>"
        if isinstance(pagina, tuple):
            return _Raspuns(pagina[0], pagina[1])
        return _Raspuns(pagina)

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(listing_scanner, "_pauza", lambda: None)
    monkeypatch.setattr(listing_scanner, "listing_descriptor", lambda _dom: descriptor)

    db = SessionLocal()
    try:
        if db.query(RadarSettings).first() is None:
            _seteaza(db)
        rezultat = listing_scanner._scaneaza_domeniu(
            db, DOM, db.query(RadarSettings).first(), 50.0)
    finally:
        db.close()
    return rezultat, cereri


def test_intrari_forma_simpla():
    """Forma cu `url` da o singura intrare, cu aceleasi valori — asa raman cei
    optsprezece descriptori de dinaintea EMAG-D neatinsi."""
    d = _descriptor_test(max_pages=7)
    intrari = listing_scanner._intrari(d)

    assert len(intrari) == 1
    assert intrari[0]["url"] == "https://www.otter.ro/reduceri"
    assert intrari[0]["page_url_template"] == "https://www.otter.ro/reduceri?p={n}"
    assert intrari[0]["max_pages"] == 7

    assert listing_scanner._pagina_url(intrari[0], 1) == "https://www.otter.ro/reduceri"
    assert (listing_scanner._pagina_url(intrari[0], 2)
            == "https://www.otter.ro/reduceri?p=2")


def test_intrari_forma_entries_mosteneste_max_pages():
    """O intrare fara `max_pages` primeste plafonul descriptorului, iar ORDINEA se
    pastreaza — pe eMAG ea e ordinea hub-ului, deci nu e cosmetica."""
    d = _descriptor_entries([
        {"url": "https://x.ro/a", "page_url_template": "https://x.ro/a/p{n}",
         "max_pages": 2},
        {"url": "https://x.ro/b", "page_url_template": "https://x.ro/b/p{n}"},
    ], max_pages=9)
    intrari = listing_scanner._intrari(d)

    assert [i["url"] for i in intrari] == ["https://x.ro/a", "https://x.ro/b"]
    assert intrari[0]["max_pages"] == 2, "plafonul propriu bate"
    assert intrari[1]["max_pages"] == 9, "fara plafon propriu -> cel al descriptorului"


def test_scan_itereaza_intrarile_cu_dedup_pe_scan(monkeypatch):
    """Doua intrari x o pagina: ambele se parcurg, dar un produs prezent in
    AMANDOUA se numara O SINGURA data.

    Asta e granita dintre per-intrare si per-scan, si se verifica pe CONTOARE, nu
    pe unicitatea randurilor din baza: commit-ul e per pagina (D6), deci cand
    intrarea a doua ajunge la `preincarca_pagina` randul scris de prima e deja
    vizibil si o dublura ar fi absorbita tacut de ramura de UPDATE. Ce nu poate fi
    absorbit e numaratoarea — cu `vazute` resetat per intrare, fiecare produs comun
    ar fi numarat de doua ori SI reevaluat a doua oara fata de un minim pe care
    tocmai acest scan l-a coborat, adica exact „inventarea unei reduceri" impotriva
    careia a fost scrisa garda SCAN-1.
    """
    fixture = _fixture("otter.ro")
    rezultat, cereri = _scaneaza_direct(monkeypatch, [fixture, fixture],
                                        _descriptor_entries([
                                            {"url": "https://www.otter.ro/a",
                                             "max_pages": 1},
                                            {"url": "https://www.otter.ro/b",
                                             "max_pages": 1},
                                        ]))

    assert cereri == ["https://www.otter.ro/a", "https://www.otter.ro/b"], \
        "ambele intrari se cer, in ordinea din descriptor"
    assert rezultat["pagini"] == 2, "amandoua paginile au fost procesate"

    distincte = len({c["external_id"] for c in extrage_carduri(
        fixture, _descriptor_entries([]), DOM)})
    assert distincte > 0
    assert rezultat["produse"] == distincte, (
        "produsele comune celor doua intrari se numara O data — cu `vazute` "
        "resetat per intrare ar fi iesit dublu")


def test_clamp_e_per_intrare(monkeypatch):
    """Aceleasi linkuri in a DOUA intrare nu sunt un clamp; in a doua PAGINA, da.

    Se masoara pe `pagini`, nu pe numarul de cereri, si diferenta conteaza:
    conditia de clamp se evalueaza DUPA fetch, deci o pagina taiata de clamp a
    fost oricum ceruta. Cu `linkuri_vazute` partajat intre intrari, cererea catre
    a doua categorie ar pleca la fel — dar continutul ei ar fi aruncat, si tocmai
    asta trebuie sa se vada.
    """
    fixture = _fixture("otter.ro")

    # (a) doua INTRARI cu acelasi continut -> AMBELE pagini se proceseaza.
    rezultat, cereri = _scaneaza_direct(monkeypatch, [fixture, fixture],
                                        _descriptor_entries([
                                            {"url": "https://www.otter.ro/a",
                                             "max_pages": 1},
                                            {"url": "https://www.otter.ro/b",
                                             "max_pages": 1},
                                        ]))
    assert len(cereri) == 2
    assert rezultat["pagini"] == 2, (
        "a doua intrare NU e un clamp — doua categorii care impart produse sunt "
        "normale, iar cu `linkuri_vazute` partajat pagina ei ar fi fost aruncata")

    # (b) aceeasi INTRARE, pagina 2 identica -> clamp real, o singura pagina.
    rezultat, cereri = _scaneaza_direct(monkeypatch, [fixture, fixture, fixture],
                                        _descriptor_entries([
                                            {"url": "https://www.otter.ro/a",
                                             "page_url_template":
                                                 "https://www.otter.ro/a?p={n}",
                                             "max_pages": 5},
                                        ]))
    assert cereri == ["https://www.otter.ro/a", "https://www.otter.ro/a?p=2"], \
        "pagina 2 repetata opreste intrarea, deci pagina 3 nu se mai cere"
    assert rezultat["pagini"] == 1, "pagina 2 a fost aruncata de clamp"


def test_eroare_pe_pagina_1_a_intrarii_2_ridica(monkeypatch):
    """O categorie moarta e semnal ca hub-ul s-a schimbat, nu ceva de tacut.

    Se cheama `_scaneaza_domeniu` DIRECT, nu prin `run_listing_scan`: acolo sus,
    exceptia e prinsa deliberat per domeniu si scrisa in `ShopScanState`, ca un
    magazin mort sa nu opreasca restul. Testul asta e despre stratul de dedesubt,
    unde ridicarea chiar se intampla.

    Randurile primei intrari sunt deja COMISE cand exceptia cade — commit-ul e per
    pagina de la D6, iar `_scaneaza_domeniu` nu le atinge inapoi.
    """
    pagini = [_fixture("otter.ro"), ("<html></html>", 500)]
    cereri = []

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        pagina = pagini[len(cereri) - 1]
        if isinstance(pagina, tuple):
            return _Raspuns(pagina[0], pagina[1])
        return _Raspuns(pagina)

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(listing_scanner, "_pauza", lambda: None)
    monkeypatch.setattr(listing_scanner, "listing_descriptor",
                        lambda _dom: _descriptor_entries([
                            {"url": "https://www.otter.ro/a", "max_pages": 1},
                            {"url": "https://www.otter.ro/moarta", "max_pages": 1},
                        ]))

    db = SessionLocal()
    try:
        if db.query(RadarSettings).first() is None:
            _seteaza(db)
        with pytest.raises(RuntimeError):
            listing_scanner._scaneaza_domeniu(db, DOM, db.query(RadarSettings).first(),
                                              50.0)
        assert cereri == ["https://www.otter.ro/a", "https://www.otter.ro/moarta"]
        db.rollback()
        assert (db.query(ShopPriceMemory)
                .filter(ShopPriceMemory.shop_domain == DOM).count()) > 0, \
            "paginile deja comise raman comise chiar si dupa rollback"
    finally:
        db.close()


def test_404_pe_pagina_2_a_intrarii_e_final_de_intrare(scan):
    """404 dupa o pagina reusita A INTRARII inchide intrarea, nu scanul.

    Contorul verificat e `pagini_intrare`, nu cel global: cu cel global, un 404 pe
    pagina 1 a intrarii a doua ar fi fost inghitit ca „final de paginare" doar
    fiindca prima intrare citise deja pagini.
    """
    fixture = _fixture("otter.ro")
    scan([fixture, ("<html></html>", 404), fixture],
         descriptor=_descriptor_entries([
             {"url": "https://www.otter.ro/a",
              "page_url_template": "https://www.otter.ro/a?p={n}", "max_pages": 4},
             {"url": "https://www.otter.ro/b", "max_pages": 1},
         ]))

    assert scan.cereri == ["https://www.otter.ro/a",
                           "https://www.otter.ro/a?p=2",
                           "https://www.otter.ro/b"], \
        "404 inchide intrarea 1 si se trece la intrarea 2, fara exceptie"


def test_emag_carduri_din_fixture():
    """eMAG, prin descriptorul REAL din registru.

    Cardul din mijloc are `<p class="pricing rrp"></p>` gol — `compare_at` iese
    None, nu 0 si nici o exceptie. Titlul poarta deja „RESIGILAT: " din HTML, deci
    feed-ul nu poate arata un iPhone la 60% fara sa spuna ce e.
    """
    carduri = extrage_carduri(_fixture("emag.ro"),
                              listing_descriptor("emag.ro"), "emag.ro")

    assert len(carduri) == 3
    assert all(c["title"].startswith("RESIGILAT: ") for c in carduri), \
        "starea vine din HTML, nu dintr-un prefix adaugat de noi"
    assert all(c["url"].startswith("https://www.emag.ro/") for c in carduri)
    assert all(c["image_url"].startswith("https://") for c in carduri)

    primul, mijloc, ultimul = carduri
    assert primul["price"] == 4599.99, "pret spart pe noduri, citit corect"
    assert primul["compare_at"] == 4999.99, "pretul de NOU al aceluiasi produs"
    assert mijloc["price"] == 2359.99
    assert mijloc["compare_at"] is None, "`p.pricing.rrp` gol -> None"
    assert ultimul["compare_at"] > ultimul["price"]


def test_emag_descriptor_pe_entries():
    """Forma descriptorului eMAG, plus ce RESPINGE garda.

    Partea a doua e miezul: o garda verificata doar pe registrul real nu poate
    dovedi ca refuza ceva. `_verifica_descriptor` primeste dicturi sintetice.
    """
    d = listing_descriptor("emag.ro")

    assert "emag.ro" in listing_domains()
    assert "url" not in d, "forma cu lista nu declara si `url`"
    assert len(d["entries"]) == 12, "cele 12 departamente din hub"
    urluri = [i["url"] for i in d["entries"]]
    assert len(set(urluri)) == 12, "intrari distincte"
    assert urluri[0] == "https://www.emag.ro/resigilate/laptop-tablete-telefoane/d", \
        "ordinea e a hub-ului (`category_panel_1_0`)"
    for intrare in d["entries"]:
        assert "{n}" in intrare["page_url_template"]
        # Numarul de pagina sta la MIJLOC pe eMAG, nu la coada.
        assert intrare["page_url_template"].endswith("/d")
    _verifica_descriptor("emag.ro", d)

    baza = {"max_pages": 2, "currency": "RON", "reference_kind": "nemarcat",
            "card": "div", "price_text": "p", "price_parse": "eu_comma"}
    intrare_buna = {"url": "https://x.ro/b",
                    "page_url_template": "https://x.ro/b/p{n}"}

    # Sanatatea cazurilor negative: forma cu lista, altfel VALIDA, chiar trece.
    # Fara asta, fiecare `raises` de mai jos ar putea sa se aprinda din alt motiv
    # decat cel testat — si exact asa a scapat prima versiune a acestui test.
    _verifica_descriptor("sintetic", {**baza, "entries": [intrare_buna]})

    with pytest.raises(AssertionError):                  # ambele forme deodata
        _verifica_descriptor("sintetic", {**baza, "url": "https://x.ro/a",
                                          "page_url_template": "https://x.ro/a/p{n}",
                                          "entries": [intrare_buna]})
    with pytest.raises(AssertionError):                  # niciuna din forme
        _verifica_descriptor("sintetic", dict(baza))
    with pytest.raises(AssertionError):                  # `entries` gol
        _verifica_descriptor("sintetic", {**baza, "entries": []})
    with pytest.raises(AssertionError):                  # intrare fara template
        _verifica_descriptor("sintetic", {**baza, "entries": [{"url": "https://x.ro/b"}]})


# ── DEAL-D2 — lotul „electronice RO" (sonda LST-D2, 2026-09-07) ──────────────
#
# Fixture-urile sunt decupate din `dumps_lstd2/<domeniu>_p1.html`, cu cardurile
# VERBATIM. Numerele de mai jos nu sunt inventate: fiecare apare in raportul
# sondei (`dumps_lstd2/raport.md`, §3.1-3.11 si controlul din §4).
#
# altex/mediagalaxy pastreaza cardurile 1 si 3, nu 1 si 2: primele doua carduri
# ale listarii au din intamplare acelasi pret (46 de preturi distincte pe 48 de
# carduri), iar un fixture cu doua valori identice n-ar deosebi o citire per card
# de una care scapa din scopul cardului.

def test_pret_eu_sup():
    """Treapta care a intrat pentru evomag: zecimalele vin dintr-un `<sup>` FARA
    separator, iar `get_text(" ")` lasa in urma un spatiu.

    Ultimele doua cazuri sunt cele care conteaza cel mai mult: parserul e STRICT,
    deci o forma pe care n-o recunoaste intoarce None si cardul se pierde — nu se
    ghiceste un numar plauzibil.
    """
    from app.services.listing_scanner import _pret_eu_sup

    assert _pret_eu_sup("529 99 lei") == 529.99
    assert _pret_eu_sup("NOU: 1.474 99 lei") == 1474.99
    assert _pret_eu_sup("529 lei") == 529.0
    # Delegare: cu virgula in sir, magazinul randeaza forma europeana normala.
    assert _pret_eu_sup("1.474,99 lei") == 1474.99
    assert _pret_eu_sup("529 9 lei") is None          # o singura zecimala
    assert _pret_eu_sup("52 99 99") is None           # doua grupuri, ambiguu


def test_pret_of_eu_sup_prin_price_parse():
    """Acelasi fragment, doua trepte, doua rezultate — si asta e tot rostul cheii.

    `eu_comma` pe markup-ul evomag da 52999.0: de 100 de ori pretul real, pe un
    card care arata perfect normal. Testul pastreaza defectul EVITAT alaturi de
    valoarea corecta, ca sa nu redevina o surpriza.
    """
    from bs4 import BeautifulSoup
    from app.services.listing_scanner import _pret_of

    card = BeautifulSoup(
        '<div class="c"><span class="real_price">529'
        '<sup class="price_sup">99</sup> lei</span></div>',
        "html.parser").select_one(".c")

    def _citeste(treapta):
        return _pret_of(card, {"price_text": "span.real_price",
                               "price_parse": treapta},
                        "price_attr", "price_text", "evomag.ro")

    assert _citeste("eu_sup") == 529.99
    assert _citeste("eu_comma") == 52999.0


def test_cel_fara_compare():
    """cel.ro intra pe axa D FARA referinta, si asta e o masuratoare, nu o scapare:
    pe 60/60 de carduri parintele pretului poarta chiar clasa `noDiscount`."""
    carduri = extrage_carduri(_fixture("cel.ro"), listing_descriptor("cel.ro"),
                              "cel.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 219.0
    assert primul["compare_at"] is None
    assert primul["title"].endswith("Resigilat")       # starea e SUFIX in titlu
    assert primul["url"].startswith("https://www.cel.ro/")
    assert all(c["compare_at"] is None for c in carduri)


def test_itgalaxy_pret_din_atribut_si_prp():
    """Pretul platit vine din `data-pprice` (parser strict), referinta din textul
    `.old-price` (virgula zecimala) — doua cai, doua parsere, un singur card.

    Primul card N-ARE referinta: `.old-price` e pe 9/36 pe pagina 1, deci un
    `compare_at is None` acolo e corect, nu o citire ratata.
    """
    carduri = extrage_carduri(_fixture("itgalaxy.ro"),
                              listing_descriptor("itgalaxy.ro"), "itgalaxy.ro")

    assert len(carduri) == 2
    assert carduri[0]["price"] == 2815.99              # data-pprice="2815.99"
    assert carduri[0]["compare_at"] is None
    assert carduri[1]["price"] == 461.99
    assert carduri[1]["compare_at"] == 525.0           # „PRP: 525,00 lei"


def test_pagina_url_deal_d2():
    """Cele trei sabloane de paginare ale rundei, confirmate LIVE (4 cereri).

    Pagina 1 foloseste URL-ul MASURAT al intrarii, nu template-ul cu n=1 — de aia
    prima asertie e pe `url`, nu pe forma template-ului.
    """
    from app.services.listing_scanner import _pagina_url

    asteptat = {
        "cel.ro": "https://www.cel.ro/resigilate/0i-2",
        "itgalaxy.ro": "https://www.itgalaxy.ro/promotii/pagina2/",
        "evomag.ro": ("https://www.evomag.ro/resigilate-produse-resigilate/"
                      "filtru/pagina:2"),
    }
    for domeniu, pagina2 in asteptat.items():
        d = listing_descriptor(domeniu)
        intrare = {"url": d["url"],
                   "page_url_template": d.get("page_url_template")}
        assert _pagina_url(intrare, 1) == d["url"]
        assert _pagina_url(intrare, 2) == pagina2


def test_evomag_sup_prin_registru():
    """Lantul intreg, prin descriptorul REAL: markup evomag -> `eu_sup` -> preturi
    corecte. Fara treapta noua, ambele numere ar fi de 100 de ori mai mari."""
    carduri = extrage_carduri(_fixture("evomag.ro"),
                              listing_descriptor("evomag.ro"), "evomag.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 529.99                   # „529 99 lei"
    assert primul["compare_at"] == 1474.99             # „NOU: 1.474 99 lei"
    # Titlul poarta DEJA starea; de aia descriptorul nu adauga niciun prefix.
    assert primul["title"].startswith("Resigilat!")
    # Fara `www`: href-urile cardului sunt RELATIVE, iar `_link_of` le rezolva
    # fata de cheia din registru (`https://<domeniu>/`). Identitatea nu sufera —
    # `external_id` si `handle` se calculeaza pe CALE.
    assert primul["url"].startswith(
        "https://evomag.ro/resigilate-produse-resigilate/")
    assert carduri[1]["price"] == 1999.99


def test_altex_mediagalaxy_frati_de_platforma():
    """Jaccard 1.000 pe clasele cardului (LST-D2 §3.2), si aceeasi cale de chei in
    STARE (JSON-0): cele doua vitrine stau peste acelasi catalog.

    Testul nu e decorativ — el impune ca o reparatie facuta la unul sa nu-l lase pe
    celalalt in urma, exact felul de divergenta tacuta pe care registrul a fost
    creat s-o previna.

    STATE-2 — acum difera DOUA chei, nu una: pe langa `url`, si
    `page_url_template`, fiindca fiecare vitrina isi pagineaza propria gazda.
    `max_pages` RAMANE egal (acelasi plafon de buget), si asta e verificat
    explicit: daca s-ar desincroniza, unul dintre frati ar scana mai adanc decat
    celalalt fara ca nimeni s-o observe.
    """
    a = listing_descriptor("altex.ro")
    m = listing_descriptor("mediagalaxy.ro")

    assert a["url"] != m["url"]
    assert a["page_url_template"] != m["page_url_template"]
    assert a["max_pages"] == m["max_pages"] == 30
    difera = {"url", "page_url_template"}
    assert {k: v for k, v in a.items() if k not in difera} == \
           {k: v for k, v in m.items() if k not in difera}


# ── DEAL-D3 — lotul „jucarii + sneakers" (sonda LST-D3, 2026-09-07) ──────────
#
# Fixture-urile sunt decupate din `dumps_lstd3/<domeniu>_p1.html` (brickdepot: `p1b`),
# cu cardurile VERBATIM. Fiecare pastreaza DOUA carduri cu preturi DISTINCTE — regula
# DEAL-D2: doua valori identice n-ar deosebi o citire per card de una care scapa din
# scopul cardului. Pe carrefour al doilea card e ales deliberat FARA referinta.

def test_carrefour_eu_sup_si_imagine_reala():
    """Doua masuratori intr-un singur test, fiindca amandoua tin de acelasi card.

    Pretul: intregul si zecimalele stau pe noduri SEPARATE, fara separator, deci
    `_text_of` da „8 79 LEI"; `eu_comma` ar citi 879.0. Imaginea: PRIMUL `<img>` al
    fiecarui card e un placeholder `data:image/gif;base64,…`, iar poza reala vine
    de pe al doilea — daca garda `data:` din normalizator ar cadea, `image_url` ar
    deveni chiar placeholderul si ar arata perfect valid.
    """
    carduri = extrage_carduri(_fixture("carrefour.ro"),
                              listing_descriptor("carrefour.ro"), "carrefour.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 8.79                     # „8 79 LEI"
    assert primul["compare_at"] == 10.99               # „10 99 LEI"
    assert primul["title"] == "Naut si sare Noirmoutier Carrefour Bio, 265g"
    assert primul["image_url"].startswith("https://cdn-media.carrefour.ro/")
    assert not primul["image_url"].lower().startswith("data:")
    # Al doilea card N-ARE pret taiat — referinta e pe 181/384, deci `None` acolo e
    # corect, nu o citire ratata. Si are alt pret: citirea e per card.
    assert carduri[1]["compare_at"] is None
    assert carduri[1]["price"] == 6.79


def test_brickdepot_us_dot_si_url_fara_spatii():
    """`us_dot` pe un magazin ROMANESC (`569.99Lei` — punct zecimal, fara separator
    de mii; `eu_comma` ar da 56999.0), plus gardul DEAL-D3 pe spatiile din `href`.

    Caracterul din dump NU e `U+0020`, ci `U+00A0` — de aia asertia verifica ambele.
    """
    carduri = extrage_carduri(_fixture("brickdepot.ro"),
                              listing_descriptor("brickdepot.ro"), "brickdepot.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 569.99
    assert primul["compare_at"] == 949.99
    assert primul["title"] == "Mario Kart™ – Luigi și Mach 8"
    assert " " not in primul["url"] and " " not in primul["url"]
    assert "%20mario-kart" in primul["url"]
    # Limita DECLARATA, nu o scapare: `src` e cale relativa fara slash initial
    # (`bmz_cache/…`), pe care normalizatorul o refuza deliberat.
    assert not primul["image_url"]
    assert carduri[1]["price"] == 437.99


def test_snipes_carduri():
    carduri = extrage_carduri(_fixture("snipes.com"),
                              listing_descriptor("snipes.com"), "snipes.com")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 95.99                    # „Preis 95,99 €"
    assert primul["compare_at"] == 119.99              # „Originalpreis 119,99 €"
    assert primul["title"] == "Samba OG"
    # Fara `www`: href-ul cardului e RELATIV, iar `_link_of` il rezolva fata de
    # cheia din registru (`https://<domeniu>/`). `external_id` si `handle` se
    # calculeaza pe CALE, deci identitatea nu sufera.
    assert primul["url"].startswith("https://snipes.com/de-de/p/")
    assert carduri[1]["price"] == 120.0


def test_sneakersnstuff_carduri():
    carduri = extrage_carduri(_fixture("sneakersnstuff.com"),
                              listing_descriptor("sneakersnstuff.com"),
                              "sneakersnstuff.com")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 147.0                    # „€147", preturi INTREGI
    assert primul["compare_at"] == 210.0
    assert primul["url"].startswith("https://sneakersnstuff.com/products/")
    # `src` e protocol-relativ (`//www.sneakersnstuff.com/cdn/…`); normalizatorul
    # ii pune schema.
    assert primul["image_url"].startswith("https://")
    assert carduri[1]["price"] == 114.0


def test_footshop_pret_din_strong():
    """Pretul se ia de pe `strong`, nu de pe div-ul de pret: referinta e IMBRICATA
    in el, deci textul div-ului contine ambele sume („477 RON 529 RON") si ar iesi
    477529.0 — o valoare care arata a pret si nu e."""
    carduri = extrage_carduri(_fixture("footshop.ro"),
                              listing_descriptor("footshop.ro"), "footshop.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 477.0
    assert primul["price"] != 477529.0
    assert primul["compare_at"] == 529.0
    assert primul["title"] == "Asics Gel-1130"
    assert carduri[1]["price"] == 736.0


def test_pagina_url_deal_d3():
    """Cele doua sabloane de paginare ale rundei, amandoua MASURATE pe p2 in
    dump-uri (p1 si p2 n-au niciun handle comun pe niciunul din domenii)."""
    from app.services.listing_scanner import _pagina_url

    asteptat = {
        "sneakersnstuff.com": "https://www.sneakersnstuff.com/collections/sale?page=2",
        "footshop.ro": "https://www.footshop.ro/ro/872-reduceri/page-2",
    }
    for domeniu, pagina2 in asteptat.items():
        d = listing_descriptor(domeniu)
        intrare = {"url": d["url"],
                   "page_url_template": d.get("page_url_template")}
        assert _pagina_url(intrare, 1) == d["url"]
        assert _pagina_url(intrare, 2) == pagina2


def test_normalizeaza_imagine_respinge_data_uri():
    """Garda `data:` exista din IMG-1a; testul o PINUIESTE, fiindca de ea depinde
    ca poza lui carrefour sa fie cea reala si nu placeholderul lazy de 1x1."""
    from app.services.listing_scanner import normalizeaza_imagine

    placeholder = ("data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///"
                   "yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    assert normalizeaza_imagine(placeholder, "carrefour.ro") is None
    assert normalizeaza_imagine("DATA:image/png;base64,AAAA", "x.ro") is None
    assert normalizeaza_imagine("  data:image/gif;base64,AAAA", "x.ro") is None
    # Fara regresie pe forma normala.
    real = "https://cdn-media.carrefour.ro/media/catalog/product/cache/a40/x.webp"
    assert normalizeaza_imagine(real, "carrefour.ro") == real


def test_link_cu_spatiu_se_codifica():
    """Gardul DEAL-D3: un `href` cu spatiu interior nu e un URL, iar fara garda
    ajungea asa in `deals.url` si in orice fetch de refresh de pe axa L."""
    from bs4 import BeautifulSoup

    descriptor = {"card": "div.c", "link": "a", "title": "a",
                  "price_text": "span", "price_parse": "eu_comma",
                  "currency": "RON"}
    html = ('<html><body><div class="c">'
            '<a href="/a b/c.html">Produs</a><span>10,00 lei</span>'
            '</div></body></html>')
    carduri = extrage_carduri(html, descriptor, "exemplu.ro")

    assert len(carduri) == 1
    assert carduri[0]["url"] == "https://exemplu.ro/a%20b/c.html"

    # Si spatiul NESEPARATOR (U+00A0), care e chiar forma masurata pe brickdepot.
    html_nbsp = html.replace("/a b/c.html", "/a b/c.html")
    assert (extrage_carduri(html_nbsp, descriptor, "exemplu.ro")[0]["url"]
            == "https://exemplu.ro/a%20b/c.html")
    assert BeautifulSoup(html_nbsp, "html.parser").select_one("a")["href"] == \
        "/a b/c.html"


# ── DEAL-D4 ───────────────────────────────────────────────────────────────────
# Lotul „fashion + beauty” din sonda LST-D4: 11 magazine, unul pe forma `entries`.
# Fixture-urile sunt decupate din dump-urile care AU LIVRAT acolo (fashiondays din
# `p1b`, restul din `p1`), iar valorile de mai jos sunt exact cele masurate — nu
# rotunjite, nu recalculate. Unde exista carduri CU si FARA referinta (epantofi,
# prm, zalando, douglas), fixture-ul are cate unul din fiecare: „compare_at e None
# aici” e o afirmatie despre MAGAZIN, nu despre un selector rupt.


def test_aboutyou_omnibus():
    """Omnibus scris pe card sub numele „Ultimul preț minim”, langa un „Preț
    original” care e PRP — descriptorul il alege explicit pe primul.

    Al doilea card pinuieste bug-ul pe care fixture-ul l-a scos la iveala: acolo
    `div[data-value="true"]` are DOI copii (`<span><s>70,32 lei</s></span>` si
    `<span> -2%</span>`), iar fara `> span:first-child` `_pret_eu_comma` lipea
    cifra procentului si dadea 70.322. Controlul LST-D4 se uitase doar la primul
    card, unde nodul e simplu — de aia numarul gresit a supravietuit pana aici.
    """
    carduri = extrage_carduri(_fixture("aboutyou.ro"),
                              listing_descriptor("aboutyou.ro"), "aboutyou.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 242.9
    assert primul["compare_at"] == 218.61
    assert primul["title"] == "Poșete 'Rue St-Guillaume'"
    assert primul["url"] == ("https://aboutyou.ro/p/karl-lagerfeld/"
                             "po-ete-rue-st-guillaume-30413495")
    assert carduri[1]["compare_at"] == 70.32, "nu 70.322: procentul nu e pret"


def test_fashiondays_din_atribute():
    """Pretul si Omnibus-ul vin din ATRIBUTE, nu din text.

    Textul vizibil are zecimalele intr-un `<sup>` („299 99 lei”), deci ar cere
    `eu_sup`; ancora poarta insa chiar numarul, cu punct zecimal. Referinta e
    `data-cmmp30-price` (Cel Mai Mic Pret 30 de zile), NU `data-gtm-price-rrp`
    (599.99, PRP-ul) — amandoua sunt pe acelasi card, iar alegerea trebuie sa se
    vada aici, nu doar in comentariul din registru.
    """
    d = listing_descriptor("fashiondays.ro")
    carduri = extrage_carduri(_fixture("fashiondays.ro"), d, "fashiondays.ro")

    assert d["price_parse"] == "attr_float"
    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 299.99
    assert primul["compare_at"] == 339.99, "cmmp30, nu rrp (599.99)"
    # `src` e un placeholder (`/images/blank_310x465.png`), poza reala e in
    # `data-original` — ordinea din `image_attr` e cea care decide.
    assert primul["image_url"].startswith("https://fdcdn.akamaized.net/")
    assert "blank_310x465" not in primul["image_url"]


def test_epantofi_omnibus_partial():
    """Omnibus pe 28 din 76 de carduri: prezenta lui e o proprietate a CARDULUI.

    Fixture-ul are unul din fiecare fel tocmai ca `compare_at is None` sa nu poata
    fi confundat cu un selector care nu prinde niciodata.
    """
    carduri = extrage_carduri(_fixture("epantofi.ro"),
                              listing_descriptor("epantofi.ro"), "epantofi.ro")

    assert len(carduri) == 2
    cu_ref, fara_ref = carduri
    assert cu_ref["price"] == 174.9
    assert cu_ref["compare_at"] == 196.0
    assert fara_ref["price"] == 369.9
    assert fara_ref["compare_at"] is None, "cardul asta n-are linia de Omnibus"


def test_spartoo_preturi_separate():
    """`span.productlist_prix` contine AMBELE preturi, deci nu poate fi citit.

    Textul lui unit e „841,00 Lei 630,75 Lei”; citit ca atare, `_pret_eu_comma` ar
    da 841630.75. Se citesc nodurile dinauntru: `s` = referinta, `span` = platit.
    Linkul cardului e relativ FARA slash initial, iar `_link_of` il rezolva fata de
    radacina domeniului — exact unde stau PDP-urile spartoo.
    """
    carduri = extrage_carduri(_fixture("spartoo.ro"),
                              listing_descriptor("spartoo.ro"), "spartoo.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 630.75
    assert primul["compare_at"] == 841.0
    assert primul["price"] != 841630.75
    assert primul["url"] == ("https://spartoo.ro/"
                             "Helly-Hansen-GARIBALDI-V4-x15480018.php")


def test_officeshoes_link_title():
    """Ancora produsului e A DOUA, iar titlul sta in atributul ei `title`.

    Prima ancora a cardului e sigla MARCII (`a.logo` -> `/branduri/calvin-klein`):
    un `link: "a"` ar scoate 48 de carduri cu 10 URL-uri distincte, adica o
    masuratoare falsa care arata a duplicate responsive. Iar `a.send-search` n-are
    text (doar un `<img>`), deci titlul vine din `title_from: "link_title"` —
    `h2.product_list_title` ar da doar modelul, fara marca.
    """
    d = listing_descriptor("officeshoes.ro")
    carduri = extrage_carduri(_fixture("officeshoes.ro"), d, "officeshoes.ro")

    assert d["title_from"] == "link_title"
    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 359.0
    assert primul["compare_at"] == 599.0
    assert primul["title"] == "Calvin Klein Pantofi sport Kobe M 1C"
    assert "/branduri/" not in primul["url"], "sigla marcii nu e produsul"
    assert primul["url"].endswith(
        "/incaltaminte-calvin-klein-pantofi-sport-kobe-m-1c/100156")


def test_prm_doua_noduri_de_pret():
    """Cardurile NEREDUSE au alt nod de pret decat cele reduse.

    46 din 80 n-au `priceSaleMinimal`, ci `priceRegular__`. Cu un singur selector,
    descriptorul citea 34 de carduri din 80 — o pierdere de 57% care arata a
    succes, fiindca cele citite erau corecte.
    """
    d = listing_descriptor("prm.com")
    carduri = extrage_carduri(_fixture("prm.com"), d, "prm.com")

    assert "priceSaleMinimal" in d["price_text"]
    assert "priceRegular__" in d["price_text"]
    assert len(carduri) == 2
    redus, neredus = carduri
    assert redus["price"] == 84.9
    # „Preț normal”, nu „Cel mai mic preț de la lansare” — alta semantica.
    assert redus["compare_at"] == 94.9
    assert neredus["price"] > 0
    assert neredus["compare_at"] is None
    assert d["reference_kind"] == "nemarcat"


def test_notino_fara_compare():
    """Al doilea pret de pe card e un CUPON, nu o referinta — deci nu se citeste.

    „2.362 RON folosind codul shoppingdays” sta intr-un nod separat. Citit ca
    referinta, ar fabrica reduceri care nu exista fara cod: raftul e R2-only.
    """
    d = listing_descriptor("notino.ro")
    carduri = extrage_carduri(_fixture("notino.ro"), d, "notino.ro")

    assert "compare_text" not in d and "compare_attr" not in d
    assert len(carduri) == 2
    assert carduri[0]["price"] == 2953.0
    assert all(c["compare_at"] is None for c in carduri)


def test_douglas_variante_si_lazy():
    """Doua variante de camp pe acelasi raft, plus placi cu poza LENESA.

    13 din 48 de carduri folosesc `-color` in loc de `price-type-discount`, iar
    Omnibus-ul lor e taiat (`-strikethrough`); cu un singur `data-testid` pe
    fiecare latura, descriptorul citea 35 din 48. Separat, placile de sub pliu au
    `src` GOL si poza in `data-lazy-src` — fara el ieseau 15 din 35 fara imagine.
    """
    carduri = extrage_carduri(_fixture("douglas.ro"),
                              listing_descriptor("douglas.ro"), "douglas.ro")

    assert len(carduri) == 3
    standard, varianta_color, lenes = carduri
    assert standard["price"] == 453.0
    assert standard["compare_at"] == 429.0
    assert varianta_color["price"] == 399.0
    assert varianta_color["compare_at"] == 405.0, "`-strikethrough`, tot Omnibus"
    # Cardul lenes: `src` GOL in HTML, poza citita din `data-lazy-src`.
    assert lenes["image_url"].startswith("https://media.douglas.ro/")
    assert lenes["price"] == 231.0
    # Pretul pe UNITATE („5,66 RON / 1 ml”) exista pe card si NU trebuie citit.
    assert standard["price"] != 5.66


def test_parfumdreams_pret_public_si_uvp():
    """Se citeste pretul PUBLIC, nu cel de membru.

    Cardul poarta trei preturi: 76,95 € (public), 69,26 € (premium, in nodul cu
    variante Tailwind `premium:` si clasa `hidden`) si UVP 139,00 €. Citit gresit,
    pretul de membru ar inventa o reducere pe care un vizitator n-o primeste.
    """
    d = listing_descriptor("parfumdreams.de")
    carduri = extrage_carduri(_fixture("parfumdreams.de"), d, "parfumdreams.de")

    assert d["currency"] == "EUR"
    assert d["reference_kind"] == "prp"
    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 76.95, "pretul public, nu 69.26 (membru)"
    assert primul["compare_at"] == 139.0, "UVP"


def test_zalando_structural():
    """Selectori STRUCTURALI, fiindca magazinul n-are niciun carlig stabil.

    Omnibus („Cel mai mic preț recent”) exista doar pe 3 din 24 de carduri, deci
    al doilea card din fixture n-are referinta si asta e corect. `max_pages: 1` e
    masurat, nu prudent: `/sale/2/` si `/sale/500/` redirecteaza amandoua la
    pagina 1, iar p1 si plast au aceleasi 24 de URL-uri.
    """
    d = listing_descriptor("zalando.ro")
    carduri = extrage_carduri(_fixture("zalando.ro"), d, "zalando.ro")

    assert d["max_pages"] == 1
    assert "page_url_template" not in d, "n-avem un URL de pagina 2 care sa mearga"
    assert len(carduri) == 2
    cu_ref, fara_ref = carduri
    assert cu_ref["price"] == 127.0
    assert cu_ref["compare_at"] == 134.0
    assert fara_ref["compare_at"] is None


def test_nichiduta_entries_si_pret():
    """Forma `entries` (17 fatete) + pretul citit din nodul dinauntru.

    `div.prices` contine si referinta („899 lei 503 lei”), deci se citeste
    `.prices span`. Referinta n-are nod propriu — e text DIRECT al div-ului — deci
    descriptorul n-are `compare_text` si raftul e R2-only.

    URL-ul cardului: ancorele sunt relative FARA slash initial, iar pagina poarta
    `<base href="https://www.nichiduta.ro/" />`. `_link_of` rezolva fata de
    radacina domeniului din registru (`nichiduta.ro`, fara `www`), adica exact
    ierarhia pe care o prescrie `<base>`: produsul e la RADACINA, nu sub categorie.
    """
    d = listing_descriptor("nichiduta.ro")
    carduri = extrage_carduri(_fixture("nichiduta.ro"), d, "nichiduta.ro")

    assert "compare_text" not in d and "compare_attr" not in d
    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 503.0
    assert primul["compare_at"] is None
    assert primul["url"].startswith("https://nichiduta.ro/carucior-")
    assert "/carucioare-copii/" not in primul["url"], "produsul e la RADACINA"
    assert carduri[1]["price"] == 605.0

    # A doua fateta, cu ACELASI descriptor: asta e ce face `entries` legitim.
    with open(os.path.join(FIXTURI, "nichiduta.ro_cards_alt.html"),
              encoding="utf-8") as f:
        alt = extrage_carduri(f.read(), d, "nichiduta.ro")
    assert alt and alt[0]["price"] > 0
    assert alt[0]["url"].startswith("https://nichiduta.ro/perna-")

    assert "url" not in d
    urluri = [i["url"] for i in d["entries"]]
    assert len(urluri) == len(set(urluri)) == 17
    assert all("produse-cu:reducere" in u for u in urluri)
    # Paginarea e INFIXATA — numarul sta la MIJLOC. Pagineaza doar fatetele carora
    # li s-a MASURAT adancimea: peste ea magazinul ARUNCA fateta si serveste
    # categoria intreaga, iar scannerul n-are cum sa deosebeasca asta.
    cu_template = [i for i in d["entries"] if i.get("page_url_template")]
    assert len(cu_template) == 2
    for intrare in cu_template:
        assert intrare["page_url_template"].endswith("/produse-cu:reducere")
        assert "/p{n}/" in intrare["page_url_template"]


def test_title_from_link_title():
    """`title_from: "link_title"` — titlul din atributul ancorei, cu fallback.

    Cheia s-a nascut din officeshoes, unde ancora produsului n-are text.
    Fallback-ul conteaza la fel de mult: un deploy care scoate atributul trebuie sa
    piarda MARCA, nu produsul.
    """
    descriptor = {"card": "div.c", "link": "a.p", "title": "h2",
                  "title_from": "link_title", "price_text": "span",
                  "price_parse": "eu_comma", "currency": "RON"}
    cu_atribut = ('<div class="c"><a class="p" href="/x" title="X Y"><img/></a>'
                  '<h2>doar modelul</h2><span>10,00 lei</span></div>')
    assert extrage_carduri(cu_atribut, descriptor, "exemplu.ro")[0]["title"] == "X Y"

    fara_atribut = cu_atribut.replace(' title="X Y"', "")
    assert (extrage_carduri(fara_atribut, descriptor, "exemplu.ro")[0]["title"]
            == "doar modelul")


def test_pagina_url_deal_d4():
    """Formele de paginare ale rundei, inclusiv cea INFIXATA.

    `_pagina_url` intoarce `url` pentru pagina 1 si formateaza template-ul abia de
    la 2 in sus, deci pagina 2 e locul unde forma se vede.
    """
    from app.services.listing_scanner import _intrari, _pagina_url

    asteptat = {
        "fashiondays.ro": "https://www.fashiondays.ro/s/sale-sale-sale-w?page=2",
        "epantofi.ro": "https://epantofi.ro/c/epantofi/akcja:extraseptember_lp?p=2",
        "prm.com": "https://prm.com/ro/s/final-sale?page=2",
        "douglas.ro": "https://www.douglas.ro/ro/c/reduceri/05?page=2",
        "parfumdreams.de": "https://www.parfumdreams.de/Angebote?p=2",
    }
    for domeniu, url in asteptat.items():
        intrare = _intrari(listing_descriptor(domeniu))[0]
        assert _pagina_url(intrare, 2) == url, domeniu
        assert _pagina_url(intrare, 1) == listing_descriptor(domeniu)["url"]

    # nichiduta: numarul de pagina la MIJLOC, nu la coada.
    paginate = [i for i in _intrari(listing_descriptor("nichiduta.ro"))
                if i.get("page_url_template")]
    assert _pagina_url(paginate[0], 2) == (
        "https://www.nichiduta.ro/carucioare-copii/carucioare-2-in-1/p2/"
        "produse-cu:reducere")


def test_douglas_max_pages_plafon():
    """`max_pages` la douglas e PLAFON DUR, nu buget.

    Masurat: `?page=2` da 48 de carduri disjuncte de pagina 1 (paginare reala), dar
    `?page=500` intoarce PAGINA 1 — p1 si plast au aceleasi 48 de URL-uri. Nu
    exista nicio semnatura de oprire: nici 404 (pe care scannerul il trateaza ca
    final de paginare), nici grila goala. Clamp-ul lui `_scaneaza_domeniu` o prinde
    abia dupa ce a re-citit o pagina intreaga, deci plafonul declarat aici e
    singura oprire pe care descriptorul o poate garanta.
    """
    d = listing_descriptor("douglas.ro")

    assert d["max_pages"] <= 20
    assert d["page_url_template"], "plafon > 1 fara template n-ar fi citit"
    assert "{n}" in d["page_url_template"]


# ── DEAL-D5 ──────────────────────────────────────────────────────────────────
def test_action_eu_sup_si_nu_pret_pe_unitate():
    """Pretul PLATIT, spart pe doua noduri — si NU cel pe unitate de langa el.

    Doua capcane pe acelasi card, amandoua masurate la LST-D5:

    1. `…price-whole` = 12 si `…price-fractional` = 99 stau in noduri separate,
       deci containerul lor da textul „12 99". `eu_sup` il citeste 12.99;
       `eu_comma` l-ar citi 1299.0 — bugul LST-D1, cu doua ordine de marime peste
       pretul real, si fara nicio eroare care sa-l tradeze.
    2. `product-card-price-description` arata „16,04 lei/kg" pe al doilea card:
       pretul pe UNITATE, care difera de cel platit pe 7 din 12 carduri
       verificate. E capcana douglas (`price-base-unit`), a doua oara in lot — iar
       un descriptor scris „la prima vedere" ar raporta kilogramul drept produs.
    """
    from app.services.listing_scanner import _intrari, _pagina_url
    from app.services.shop_registry import SHOP_REGISTRY

    d = listing_descriptor("action.com")
    carduri = extrage_carduri(_fixture("action.com"), d, "action.com")

    assert d["price_parse"] == "eu_sup"
    assert "price-description" not in d["price_text"]
    assert "price-description" not in (d.get("compare_text") or "")

    assert len(carduri) == 2
    farfurie, rola = carduri

    assert farfurie["price"] == 12.95
    assert farfurie["compare_at"] == 14.95
    assert farfurie["title"] == "Farfurie pentru micul dejun Dahlia"

    # Al doilea card: se citeste pretul PLATIT (12,99), nu cei 16,04 lei/kg.
    assert rola["price"] == 12.99
    assert rola["price"] != 16.04, "16,04 e pretul pe KILOGRAM, nu al produsului"
    assert rola["compare_at"] == 14.95

    # `eu_comma` pe acelasi text ar da 1299.0: santinela care arata ca alegerea
    # parserului nu e cosmetica.
    assert all(c["price"] < 100 for c in carduri)

    intrare = _intrari(d)[0]
    assert _pagina_url(intrare, 1) == "https://www.action.com/ro-ro/oferta-saptamanala/"
    assert (_pagina_url(intrare, 2)
            == "https://www.action.com/ro-ro/oferta-saptamanala/?page=2")

    # `max_pages` MASURAT prin bisectie (DEAL-D5, 3 cereri la 90 s fiecare):
    # pagina 6 are continut nou (18 carduri), 7 si 12 plafoneaza la pagina 1.
    # 6 + 1, unde plusul e pagina care confirma clamp-ul. Verificare independenta:
    # 5 x 23 + 18 = 133, exact totalul anuntat pe pagina 1.
    # Pinuit si din COST: la `min_fetch_interval_s: 90`, un scan plateste
    # `max_pages` x 90 s, adica ~10 minute pe acest domeniu.
    assert d["max_pages"] == 7
    assert SHOP_REGISTRY["action.com"]["min_fetch_interval_s"] == 90

    # Referinta e taiata dar NEETICHETATA: „Intotdeauna cel mai mic pret" din
    # fixture e slogan de marca, nu Omnibus, si sta in afara cardurilor.
    assert d["reference_kind"] == "nemarcat"


def test_senetic_brut_nu_net():
    """Se citeste BRUTUL („cu TVA"), adica pretul platit de client.

    Cardul poarta amandoua preturile, etichetate explicit: `.price-net` „921,49
    RON fara TVA" si `.price-gross` „1 115,00 RON cu TVA". Citirea netului ar
    raporta preturi cu ~19% mai mici pe tot raftul si ar face magazinul sa para
    plin de chilipiruri — capcana B2B, masurata pe 24/24 de carduri la LST-D5.
    Separatorul de mii e SPATIU insecabil, pe care `eu_comma` il inghite.

    Fara `compare_*`: zero preturi taiate pe 24/24, deci axa D ramane doar pe R2.
    Verdictul NEPOTRIVIT de la DEAL-D2 fusese dat pe CARUSEL, nu pe grila asta.
    """
    d = listing_descriptor("senetic.ro")
    carduri = extrage_carduri(_fixture("senetic.ro"), d, "senetic.ro")

    assert d["price_text"] == "div.price-gross"
    assert "compare_text" not in d and "compare_attr" not in d
    assert d["reference_kind"] == "nemarcat"

    assert len(carduri) == 2
    ssd, switch = carduri

    assert ssd["price"] == 1115.0, "brutul; 921.49 e netul, fara TVA"
    assert ssd["price"] != 921.49
    assert ssd["compare_at"] is None
    assert ssd["title"] == "SSD 1TB Samsung M.2 PCI-E NVMe Gen4 990 PRO Basic retail"
    # Poza produsului, nu indicatorul de incarcare al widgetului de comparatie
    # (primul `<img>` din card e `ajax-loader-new.gif`).
    assert "akeneo-catalog" in ssd["image_url"]

    assert switch["price"] == 6468.82, "tot brutul; netul e 5 346,13"
    assert switch["compare_at"] is None

    # Fara paginare: `rel=next` de pe pagina trimite la HOME (artefact de sit),
    # deci descriptorul n-are template si scanul citeste o singura pagina.
    assert d["max_pages"] == 1
    assert "page_url_template" not in d


# ── STATE-1 ──────────────────────────────────────────────────────────────────
def test_5xx_pe_pagina_2_e_sfarsit_de_intrare(monkeypatch, caplog):
    """Un 500 la coada unei intrari nu mai arunca paginile deja citite.

    Masurat pe prm (LST-D4): `/ro/s/final-sale?page=<coada>` da HTTP 500. Pana
    acum orice non-200 ridica `RuntimeError`, iar `RuntimeError` cade INAINTE de
    `db.commit()` — deci un singur 500 la pagina 30 pierdea tot ce citisera
    primele 29. Aceeasi pierdere pe care VAL D o reparase pentru 404, doar pe alt
    cod de stare.

    Se verifica pe CONTOARE si pe log, nu doar pe absenta exceptiei: „n-a crapat"
    ar fi adevarat si daca scanul ar fi iesit fara sa comita nimic.
    """
    import logging

    with caplog.at_level(logging.WARNING,
                         logger="app.services.listing_scanner"):
        rezultat, cereri = _scaneaza_direct(
            monkeypatch,
            [_fixture("otter.ro"), ("<html></html>", 500)],
            _descriptor_test(max_pages=5))

    assert len(cereri) == 2, "pagina 2 a fost ceruta, si acolo a venit 500-ul"
    assert rezultat["pagini"] == 1, "pagina 1 ramane citita si numarata"
    assert rezultat["produse"] > 0, "produsele din pagina 1 raman comise"

    mesaje = [r.getMessage() for r in caplog.records
              if r.levelno == logging.WARNING]
    assert any("500" in m and "pagina 2" in m for m in mesaje), mesaje

    # (b) Aceeasi pozitie, dar 404: sfarsit TACUT, ca inainte. Granita dintre cele
    # doua ramuri e chiar zgomotul — un 500 e o anomalie a magazinului si merita o
    # linie in log, un 404 e finalul normal al paginarii. Scenariul sta aici, nu
    # intr-un test separat, ca sa se vada ca cele doua ramuri se ating.
    caplog.clear()
    with caplog.at_level(logging.WARNING,
                         logger="app.services.listing_scanner"):
        rezultat_404, cereri_404 = _scaneaza_direct(
            monkeypatch,
            [_fixture("otter.ro"), ("<html></html>", 404)],
            _descriptor_test(max_pages=5))

    assert len(cereri_404) == 2
    assert rezultat_404["pagini"] == 1
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == [],         "404 ramane sfarsit tacut: WARN-ul e doar pentru anomalii"


def test_5xx_pe_pagina_1_ridica(monkeypatch):
    """Pe pagina 1 orice non-200 ramane EROARE — granita nu s-a mutat.

    Acolo un 500 nu inseamna „gata lista", ci intrare moarta (URL mutat, categorie
    stearsa), si trebuie sa se auda. Daca s-ar inghiti si aici, un magazin cazut
    ar raporta linistit „0 produse" la fiecare scan.
    """
    with pytest.raises(RuntimeError):
        _scaneaza_direct(monkeypatch, [("<html></html>", 500)],
                         _descriptor_test(max_pages=5))


def test_flip_next_carduri():
    """flip.ro - cardurile din `__NEXT_DATA__`, cu cele trei capcane ale lui.

    1. `previousPrice` e EGAL cu `price` pe 32/32 in dump - capcana constantei de
       la vivre. Citit ca referinta, ar da reduceri de 0% pe tot catalogul.
    2. `retailPrice` e referinta REALA (pretul unitatii NOI a aceluiasi model),
       dar exista si cu valoarea 0: acolo `compare_at` trebuie sa iasa None, nu o
       reducere de la zero.
    3. `?shape=` face parte din IDENTITATE (`url_identity: "exact"` in registru),
       deci `external_id` si `handle` se calculeaza pe cale + query. Fara asta,
       acelasi model in doua grade ar primi acelasi id, iar al doilea ar fi sarit
       de garda SCAN-1 - jumatate de catalog disparut tacut.
    """
    from app.services.listing_state_extractors import flip_next

    d = listing_descriptor("flip.ro")
    carduri = flip_next(_fixture_stare("flip.ro"), d)

    assert d["state_extractor"] == "flip_next"
    assert len(carduri) == 2
    iphone, ipad = carduri

    assert iphone["price"] == 1429.99
    assert iphone["compare_at"] == 2250.0
    assert iphone["title"].endswith("Excelent")
    assert "?shape=" in iphone["url"]
    assert iphone["image_url"].startswith("https://cdn.flip.ro/")

    # `retailPrice: 0` <= `price` -> fara referinta inventata.
    assert ipad["price"] == 1099.99
    assert ipad["compare_at"] is None

    # Identitatea include query-ul: `handle` il poarta, iar cele doua carduri au
    # `external_id` distincte chiar daca ar imparti calea.
    assert "?shape=" in iphone["handle"]
    assert iphone["external_id"] != ipad["external_id"]
    din_cale = _external_id(iphone["url"])
    assert iphone["external_id"] != din_cale, (
        "id-ul pe CALEA goala ar pierde gradul si ar uni doua oferte diferite")


def test_flip_next_alege_query_ul_cu_productsPage():
    """Query-ul se alege dupa CONTINUT, nu dupa indice.

    Fixture-ul are `queries[0]` fara `productsPage` (`state.data` None), exact
    inversul dump-ului. Ordinea unui cache de react-query nu e un contract, iar
    ziua in care se schimba n-ar da o eroare, ci zero produse - adica „magazinul
    n-are reduceri azi", tacut si fals.
    """
    import json as _json

    from app.services.listing_state_extractors import flip_next, next_data

    html = _fixture_stare("flip.ro")
    interogari = (next_data(html)["props"]["pageProps"]["dehydratedState"]
                  ["queries"])
    assert (interogari[0].get("state") or {}).get("data") is None, (
        "fixture-ul trebuie sa aiba PRIMUL query fara produse")
    assert _json.dumps(interogari[1])  # al doilea e cel cu `productsPage`

    assert len(flip_next(html, listing_descriptor("flip.ro"))) == 2


def test_marionnaud_json_carduri():
    """marionnaud.ro - pret NUMERIC, URL RELATIV rezolvat, zero referinta.

    `price.value` (374) se citeste, `price.formattedValue` („374,00 RON") nu:
    parsarea unui sir cu virgula cand exista deja numarul ar fi o treapta in plus
    care poate gresi, fara nimic de castigat. `url` e relativ la radacina si
    trebuie rezolvat - nerezolvat, ar ajunge asa in `deals.url`.

    Referinta lipseste, masurat pe 20/20 (`otherPrices`, `otherPricesMap` si
    `priceRange` goale, `savePrice` sirul vid), deci raftul intra doar pe R2.
    """
    from app.services.listing_state_extractors import marionnaud_json

    d = listing_descriptor("marionnaud.ro")
    carduri = marionnaud_json(_fixture_stare("marionnaud.ro"), d)

    assert d["state_extractor"] == "marionnaud_json"
    assert len(carduri) == 2
    lancome, idole = carduri

    assert lancome["price"] == 374.0, "din `price.value`, nu din „374,00 RON\""
    assert lancome["title"] == "La Vie est Belle Apa de Parfum"
    assert lancome["url"] == (
        "https://www.marionnaud.ro/lancome/la-vie-est-belle/"
        "la-vie-est-belle-apa-de-parfum/p/BP_45540"), "URL-ul relativ, rezolvat"
    assert lancome["image_url"].startswith("https://media.marionnaud.ro/")
    assert idole["price"] == 334.0

    assert all(c["compare_at"] is None for c in carduri)
    assert d["reference_kind"] == "nemarcat"
    # Paginarea e ignorata server-side (B3), deci o singura pagina si niciun sablon.
    assert d["max_pages"] == 1
    assert "page_url_template" not in d


def test_state_extractors_inregistrati():
    """Cei doi extractori noi sunt legati corect in toate cele trei locuri.

    Un nume de `state_extractor` care nu exista in harta ridica `KeyError` in
    scanner - deliberat, fiindca o listare goala ar arata ca „azi n-are reduceri"
    si ar inchide tacit dealurile. Testul verifica legatura in ambele sensuri.
    """
    from app.services.listing_state_extractors import LISTING_STATE_EXTRACTORS

    for domeniu, nume in (("flip.ro", "flip_next"),
                          ("marionnaud.ro", "marionnaud_json")):
        assert nume in LISTING_STATE_EXTRACTORS
        assert domeniu in listing_domains()
        d = listing_descriptor(domeniu)
        assert d["state_extractor"] == nume
        # Forma `state_extractor` e SAU-EXCLUSIV cu forma CSS.
        assert "card" not in d and "price_parse" not in d
        _verifica_descriptor(domeniu, d)


# ── STATE-2 — altex/mediagalaxy la adancime prin stare; sportvision + booztlet CSS
#
# Runda JSON-0 cautase un API de listare pe sase domenii si NU l-a gasit pe niciunul
# (640 de raspunsuri, zero apeluri de produse). Pe altex si mediagalaxy a gasit in
# schimb produsele in `__NEXT_DATA__`, in acelasi raspuns pe care il descarcam deja,
# impreuna cu URL-urile TUTUROR paginilor. STATE-2 le-a cablat, si a masurat live
# (8 cereri) paginarea, oprirea, imaginea si cele doua listari SSR.

def test_altex_next_pret_inversat_si_url_cu_sku():
    """Cele DOUA capcane ale starii altex, amandoua pinuite aici.

    1. Semantica preturilor e INVERSATA fata de nume: `lowest_price` (1919.92) e
       pretul RESIGILAT, adica cel platit; `price` (2399.9) e al unitatii NOI,
       „Nou:” in DOM. Un mapper care ar lua `price` drept pret platit ar raporta
       pretul de nou pe tot catalogul — adica fix reducerea pentru care exista
       scanul.
    2. URL-ul se compune cu `sku`, NU cu `id`-ul numeric. Controlul din JSON-0 a
       cazut exact aici: cu `id` raporta „48/48 carduri complete” si toate cele 48
       de URL-uri erau gresite, fiindca un control de completitudine se uita doar
       daca URL-ul e nevid. Proba tare a fost comparatia cu ancorele din DOM.

    Al treilea card e SINTETIC (v. antetul fixture-ului): `price` coborat la
    `lowest_price`, fiindca in cele 96 de produse capturate (p1 + p2) nu exista
    niciun produs fara reducere, iar ramura `compare_at is None` are nevoie de unul.
    """
    carduri = extrage_carduri(_fixture_stare("altex.ro"),
                              listing_descriptor("altex.ro"), "altex.ro")

    assert len(carduri) == 3
    primul = carduri[0]
    assert primul["price"] == 1919.92                  # `lowest_price` = resigilat
    assert primul["compare_at"] == 2399.9              # `price` = unitatea NOUA
    assert primul["title"].startswith("Laptop MSI Modern 15")
    assert primul["url"].endswith("/cpd/LAP9S715S121071/#resigilate"), (
        "URL-ul se compune cu `sku`, nu cu `id`-ul numeric (844256)")
    assert "844256" not in primul["url"]
    # Fragmentul e PASTRAT (duce la sectiunea de resigilate a PDP-ului), dar
    # `handle` se calculeaza pe CALE, deci dedup-ul nu-l vede.
    assert "#" not in primul["handle"]
    assert primul["image_url"] == (
        "https://lcdn.altex.ro/media/catalog/product/m/o/"
        "modern_15_f13mg_071xro_01_24e97af1.jpg"), (
        "`{cdn}{image}` — masurat live: 200, image/jpeg, 95.192 octeti")

    # Al doilea are ALTE valori: citirea e per produs, nu o scapare de scop.
    assert carduri[1]["price"] == 1759.92
    assert carduri[1]["compare_at"] == 2199.9
    # Al treilea (sintetic): fara reducere -> fara referinta, niciodata 0%.
    assert carduri[2]["compare_at"] is None


def test_altex_next_baseurl_din_stare():
    """UN extractor, DOI frati: gazda vine din `runtimeConfig.settings`, nu din cod.

    Fixture-ul mediagalaxy trece prin ACELASI `altex_next` si trebuie sa iasa pe
    gazda LUI — si la URL-ul produsului, si la CDN-ul imaginii. Daca `baseUrl` ar fi
    hardcodat pe altex, produsele mediagalaxy ar primi linkuri catre magazinul
    celalalt: carduri perfect valide la vedere, care duc in alta parte.

    Frateria pe STARE, nu doar pe DOM: acelasi prim produs, cu acelasi SKU si
    acelasi pret, in dump-urile ambelor vitrine (JSON-0 §2).
    """
    a = extrage_carduri(_fixture_stare("altex.ro"),
                        listing_descriptor("altex.ro"), "altex.ro")
    m = extrage_carduri(_fixture_stare("mediagalaxy.ro"),
                        listing_descriptor("mediagalaxy.ro"), "mediagalaxy.ro")

    assert len(m) == len(a) == 3
    assert m[0]["url"].startswith("https://mediagalaxy.ro/")
    assert m[0]["image_url"].startswith("https://lcdn.mediagalaxy.ro/")
    assert all(c["url"].startswith("https://mediagalaxy.ro/") for c in m)
    assert not any("altex" in c["url"] for c in m)
    # Acelasi catalog: acelasi SKU, acelasi pret, aceeasi referinta.
    assert m[0]["url"].split("/cpd/")[1] == a[0]["url"].split("/cpd/")[1]
    assert (m[0]["price"], m[0]["compare_at"]) == (a[0]["price"], a[0]["compare_at"])


def test_altex_next_fara_produse_e_final():
    """Grila goala = final de paginare, nu eroare.

    MASURAT live (STATE-2, cererea 2): `/resigilate/filtru/p/500/` raspunde 200 —
    nu 404 — cu `products: []`, `toolbar.pagination: []` si acelasi
    `<h1>Produse resigilate</h1>`. Deci semnalul de oprire e lista goala, si
    extractorul trebuie s-o intoarca asa, nu sa ridice.
    """
    from app.services.listing_state_extractors import altex_next

    descriptor = listing_descriptor("altex.ro")
    gol = ('<html><head><script id="__NEXT_DATA__" type="application/json">'
           '{"props": {"initialReduxState": {"resealed": {"currentCategory": '
           '{"products": []}}}}}</script></head><body></body></html>')

    assert altex_next(gol, descriptor) == []
    # Si formele degenerate, care nu trebuie sa ridice: fara `__NEXT_DATA__` si
    # fara calea de chei.
    assert altex_next("<html><body>nimic</body></html>", descriptor) == []
    assert altex_next('<html><script id="__NEXT_DATA__" type="application/json">'
                      '{"props": {}}</script></html>', descriptor) == []


def test_altex_mediagalaxy_pe_state_extractor():
    """Ambii descriptori au trecut de pe calea CSS pe cea de STARE.

    Cheile CSS (`card`, `price_text`, `compare_text`, `price_parse`, ...) trebuie sa
    fi DISPARUT: garda contractului le interzice pe calea de stare tocmai ca sa nu
    ramana configuratie moarta care pare vie.
    """
    from app.services.listing_state_extractors import LISTING_STATE_EXTRACTORS

    assert "altex_next" in LISTING_STATE_EXTRACTORS
    for domeniu, gazda in (("altex.ro", "altex.ro"),
                           ("mediagalaxy.ro", "mediagalaxy.ro")):
        d = listing_descriptor(domeniu)
        assert d["state_extractor"] == "altex_next"
        assert "card" not in d and "price_parse" not in d
        assert d["max_pages"] == 30, "plafon de BUGET (real: 168 / 157)"
        assert d["page_url_template"] == f"https://{gazda}/resigilate/filtru/p/{{n}}/"
        assert d["currency"] == "RON"
        assert d["reference_kind"] == "nemarcat"
        _verifica_descriptor(domeniu, d)


def test_sportvision_carduri():
    """NBSHOP, masurat pe dump-ul HTTP — nu pe randarea de browser.

    Distinctia e chiar miza cererii 4: JSON-0 vazuse pagina intr-un browser, dar
    scannerul citeste HTTP. Cele 24 de carduri sunt aceleasi pe ambele cai.

    FARA referinta, si e o MASURATOARE: `data-productprevprice` e EGAL cu
    `data-productprice` pe 24/24, iar `data-productdiscount` e „0” pe 24/24 — exact
    capcana constantei de la vivre si `previousPrice` de la flip. Citita ca
    referinta, ar produce reduceri de 0% pe tot catalogul.

    Pretul vine din TEXT, nu din atribut: `data-productprice="249,99"` are virgula
    zecimala, iar calea `price_attr` merge prin parserul STRICT si ar da None.
    """
    carduri = extrage_carduri(_fixture("sportvision.ro"),
                              listing_descriptor("sportvision.ro"),
                              "sportvision.ro")

    assert len(carduri) == 2
    primul = carduri[0]
    assert primul["price"] == 249.99                   # „Pret 249,99 RON”
    assert primul["compare_at"] is None
    assert primul["title"] == "adidas Pantofi Sport RESPONSE RUNNER 2"
    assert primul["url"].startswith("https://www.sportvision.ro/pantofi-sport/")
    # Poza sta in `data-original-img` si e RELATIVA — `src` lipseste (lazy `lozad`),
    # acelasi tipar ca buzzsneakers, tot NBSHOP.
    assert primul["image_url"].startswith("https://sportvision.ro/files/thumbs/")
    assert carduri[1]["price"] == 564.99
    assert all(c["compare_at"] is None for c in carduri)


def test_booztlet_carduri():
    """Outlet EUR, cu pret in PUNCT zecimal si referinta taiata nemarcata.

    Trei masuratori pinuite:

    1. `us_dot`, nu `eu_comma`: preturile sunt „69.50 €”, deci punctul e ZECIMAL.
       Cu `eu_comma` ar iesi 6950.0 — de 100 de ori mai mult. Sigur pe tot dump-ul:
       valorile merg de la 9.0 la 433.3 si niciuna n-are separator de mii.
    2. Pretul platit si referinta au ACEEASI clasa; ii deosebeste doar eticheta
       (`span` vs `s`), de aceea selectorii o numesc.
    3. Al doilea card e ales deliberat FARA `<s>` (7 din 86 n-au), ca ramura
       `compare_at is None` sa fie pinuita pe un card REAL, nu pe unul sintetic.

    Atributul `data-cnstrc-item-price="78.000"` ar fi mers prin parserul strict,
    dar e prezent doar pe 80/86 — iar cele sase care-i lipsesc sunt produse reale.
    """
    carduri = extrage_carduri(_fixture("booztlet.com"),
                              listing_descriptor("booztlet.com"), "booztlet.com")

    assert len(carduri) == 2
    primul = carduri[0]
    # PUNCT zecimal, si de asta e ales cardul asta: pe „78 €" cele doua parsere ar
    # da acelasi raspuns, deci fixture-ul n-ar deosebi `us_dot` de `eu_comma`.
    # Prima varianta a fixture-ului avea exact defectul asta, si sabotajul l-a prins.
    assert primul["price"] == 69.5                     # „69.50 €", nu 6950.0
    assert primul["compare_at"] == 139.0               # <s>139 €</s>, nemarcat
    assert primul["title"] == "NORVIG Jane Short Cardigan - Cardigans"
    assert primul["url"].startswith("https://www.booztlet.com/eu/en/")
    assert primul["image_url"].startswith("https://image-resizing.booztcdn.com/")
    assert carduri[1]["price"] == 9.0
    assert carduri[1]["compare_at"] is None, "cardul fara <s> n-are referinta"
    assert listing_descriptor("booztlet.com")["currency"] == "EUR"


def test_pagina_url_state2():
    """Cele trei sabloane noi, toate confirmate LIVE (cererile 1, 3 si 5).

    Pagina 1 foloseste URL-ul MASURAT al intrarii, nu template-ul cu n=1 — de aia
    prima asertie e pe `url`.
    """
    from app.services.listing_scanner import _pagina_url

    asteptat = {
        "altex.ro": "https://altex.ro/resigilate/filtru/p/2/",
        "mediagalaxy.ro": "https://mediagalaxy.ro/resigilate/filtru/p/2/",
        "sportvision.ro": ("https://www.sportvision.ro/produse/"
                           "noua-colectie/page-2"),
    }
    for domeniu, pagina2 in asteptat.items():
        d = listing_descriptor(domeniu)
        intrare = {"url": d["url"],
                   "page_url_template": d.get("page_url_template")}
        assert _pagina_url(intrare, 1) == d["url"]
        assert _pagina_url(intrare, 2) == pagina2

    # booztlet NU are sablon, si asta e o masuratoare: HTML-ul brut n-are `rel=next`
    # si nicio ancora cu `page=`, iar scroll-ul pana la capatul grilei n-a cerut
    # nimic. Garda contractului interzice un sablon la plafon 1.
    b = listing_descriptor("booztlet.com")
    assert b["max_pages"] == 1
    assert "page_url_template" not in b


# ── GUARD-1 — un singur retry pe `None` tranzitoriu, la pagina 1 ─────────────
#
# Trei observatii independente, aceeasi forma: poarta a intors `None` o data si a
# mers la cererea urmatoare, pe ACELASI URL, cu acelasi profil — GATE-1 (nike.com),
# GATE-3 (computeruniverse.net `/de`: `None` la LST-D5, apoi 200 din primul hop cu
# 1.101.369 de octeti, dupa ce runda a exclus cu cifre RATE, allow-list, normalizarea
# si interstitiul) si LST-D5 (action.com, `prod1`).
#
# `None` inseamna „n-am ajuns la magazin", nu „magazinul a spus nu" — de aia
# retry-ul e strict pe `None`, si de aia e UNUL singur.

def _scaneaza_cu_none(monkeypatch, raspunsuri, descriptor, cereri=None,
                      dormite=None):
    """Ca `_scaneaza_direct`, dar o intrare `None` inseamna „poarta a dat None".

    `_scaneaza_direct` nu poate exprima cazul: el impacheteaza orice intrare in
    `_Raspuns`, iar `_Raspuns(None)` e un raspuns 200 cu corpul None — exact
    altceva decat absenta raspunsului.

    `cereri` si `dormite` se pot da de AFARA, ca sa ramana inspectabile si cand
    scanul ridica: pe caile de eroare valoarea de retur nu mai ajunge la apelant.
    """
    cereri = [] if cereri is None else cereri
    dormite = [] if dormite is None else dormite

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        indice = len(cereri) - 1
        pagina = raspunsuri[indice] if indice < len(raspunsuri) else "<html></html>"
        if pagina is None:
            return None
        if isinstance(pagina, tuple):
            return _Raspuns(pagina[0], pagina[1])
        return _Raspuns(pagina)

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(listing_scanner, "_pauza", lambda: None)
    monkeypatch.setattr(listing_scanner, "listing_descriptor", lambda _dom: descriptor)
    # Asteptarea se INREGISTREAZA, nu doar se scurtcircuiteaza: testul dovedeste si
    # ca retry-ul chiar asteapta, nu doar ca nu incetineste suita.
    monkeypatch.setattr(listing_scanner.time, "sleep", lambda s: dormite.append(s))

    db = SessionLocal()
    try:
        if db.query(RadarSettings).first() is None:
            _seteaza(db)
        rezultat = listing_scanner._scaneaza_domeniu(
            db, DOM, db.query(RadarSettings).first(), 50.0)
    finally:
        db.close()
    return rezultat, cereri, dormite


def test_none_tranzitoriu_pe_pagina_1_reuseste_la_retry(monkeypatch, caplog):
    """`None` o data, 200 la a doua — scanul merge mai departe, si se AUDE.

    WARN-ul nu e decor: e masuratoarea care lipseste. Din frecventa lui se va vedea
    daca `None`-urile tranzitorii se aduna pe domeniile din spatele Cloudflare
    (ipoteza `__cf_bm` din GATE-3) sau sunt uniforme pe catalog.
    """
    import logging

    with caplog.at_level(logging.WARNING,
                         logger="app.services.listing_scanner"):
        rezultat, cereri, dormite = _scaneaza_cu_none(
            monkeypatch, [None, _fixture("otter.ro")],
            _descriptor_test(max_pages=1))

    assert len(cereri) == 2, "exact doua cereri: originalul plus UN retry"
    assert cereri[0] == cereri[1], "retry-ul cere ACELASI URL"
    assert rezultat["pagini"] == 1
    assert rezultat["produse"] > 0, "produsele paginii 1 intra in scan"
    assert dormite == [listing_scanner._PAUZA_RETRY_S], "retry-ul asteapta o data"
    assert listing_scanner._PAUZA_RETRY_S == 10

    mesaje = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("tranzitoriu" in m and "pagina 1" in m for m in mesaje), mesaje


def test_none_dublu_pe_pagina_1_ridica(monkeypatch):
    """Doua `None`-uri la rand nu mai sunt un accident: e defectiune, si se aude.

    Exact DOUA cereri, nu trei: retry-ul e unul singur, nu o bucla. Daca ar fi
    bucla, un domeniu cazut ar fi batut la usa de N ori pe fiecare scan.
    """
    cereri = []
    with pytest.raises(RuntimeError, match="dupa retry"):
        _scaneaza_cu_none(monkeypatch, [None, None], _descriptor_test(max_pages=5),
                          cereri=cereri)

    assert len(cereri) == 2, f"un singur retry, nu o bucla — cereri: {len(cereri)}"


def test_status_403_pe_pagina_1_nu_se_reincearca(monkeypatch):
    """Un 403 e un raspuns REAL: se ridica din prima, fara a doua cerere.

    Granita e chiar miza rundei. `None` inseamna „n-am ajuns la magazin"; un 403
    inseamna „magazinul a spus nu", si repetarea lui n-ar face decat sa mai bata o
    data la o usa tocmai inchisa — exact ce a produs Access Denied-ul de la G4b,
    unde insistenta pe acelasi URL a inrautatit situatia.
    """
    cereri = []
    dormite = []
    with pytest.raises(RuntimeError) as exc:
        _scaneaza_cu_none(monkeypatch, [("<html></html>", 403)],
                          _descriptor_test(max_pages=5), cereri=cereri,
                          dormite=dormite)

    assert len(cereri) == 1, "un 403 nu se reincearca deloc"
    assert dormite == [], "si nici nu asteapta degeaba"
    assert "dupa retry" not in str(exc.value), "403 nu trece prin calea de retry"


# ── DEAL-D6 — lego.com pe cache Apollo, 43einhalb.com pe CSS scopat la grila ──
#
# Sonda LST-D6 a masurat trei domenii, si in doua din trei cazuri PREMISA era
# gresita: sizeer nu era „grila inecata in zgomot" ci grila neservita deloc
# (JS_ONLY, iesit din axa D), iar duplicatele de pe 43einhalb nu erau variante
# responsive, ci previzualizari de MEGAMENIU — adica un selector nescopat, nu o
# pagina ciudata.

def _stare_lego(nume: str):
    """`(html, cache)` dintr-un fixture lego — pentru testele care au nevoie sa
    MUTE forma cache-ului inainte de a o da extractorului.

    Citeste fisierul pe nume intreg, nu prin `_fixture_stare`: lego are DOUA
    fixture-uri de stare pe acelasi domeniu (categorie si campanie), fiindca cele
    doua intrari ale descriptorului emit seturi diferite de campuri — iar
    conventia `<domeniu>_state.html` nu poate exprima decat unul.
    """
    from app.services.listing_state_extractors import next_data

    with open(os.path.join(FIXTURI, f"{nume}.html"), encoding="utf-8") as f:
        html = f.read()
    return html, next_data(html)["props"]["pageProps"]["__APOLLO_STATE__"]


def _html_lego(stare) -> str:
    """Forma inversa: un `__NEXT_DATA__` care poarta cache-ul dat."""
    import json

    date = {"props": {"pageProps": {"__APOLLO_STATE__": stare}}}
    return ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(date, ensure_ascii=False) + "</script>")


def test_lego_apollo_categorie():
    """Categoria de reduceri — forma cu `centAmount` si FARA `formattedValue`.

    Pe `/ro-ro/categories/sales-and-deals` obiectul `listPrice` are doar
    `formattedAmount` si `centAmount` (8499): zero `formattedValue` pe 22/22, in
    timp ce pe campanie il are pe 20/20. Un resolver care s-ar opri la
    `formattedValue` ar da deci ZERO referinte aici — un catalog fara nicio
    reducere, tacut. De aia a doua asertie a testului e chiar `compare_at`.
    """
    from app.services.listing_state_extractors import lego_apollo

    d = listing_descriptor("lego.com")
    html, stare = _stare_lego("lego.com_state_categorie")
    carduri = lego_apollo(html, d)

    assert d["state_extractor"] == "lego_apollo"
    assert len(carduri) == 2
    calendar, caine = carduri

    assert calendar["price"] == 50.99, "din `formattedValue`, nu din text"
    assert calendar["compare_at"] == 84.99, (
        "din `centAmount` 8499, fiindca aici `formattedValue` LIPSESTE")
    assert calendar["title"] == "Calendar de perete 2026"
    assert calendar["url"] == ("https://www.lego.com/ro-ro/product/"
                               "2026-wall-calendar-5009303")
    assert calendar["image_url"].startswith("https://www.lego.com/cdn/"), (
        "imaginea e chiar motivul pentru care nu s-a mers pe CSS: acolo e 0/22")

    assert caine["price"] == 113.99
    assert caine["compare_at"] == 189.99
    assert caine["url"].endswith("/pickle-dog-plush-5009235")

    # A doua cale catre obiectul `Price`, si singura care ramane cand varianta NU
    # poarta campul: cheia CONSTRUITA `$<varianta>.<camp>`. Pe lego cele doua cai
    # duc in acelasi loc (referinta e `generated: true`, iar `id`-ul ei ESTE cheia
    # construita — masurat 42/42), deci forma de mai jos NU exista in dump. De aia
    # sta aici, ca mutatie explicita, si nu in fixture: fixture-ul ramane reducere
    # verbatim, iar rezerva are totusi ce sa dovedeasca.
    fara_camp = {k: (dict(v) if k.startswith("ProductVariant:") else v)
                 for k, v in stare.items()}
    for cheie, obiect in fara_camp.items():
        if cheie.startswith("ProductVariant:"):
            obiect.pop("listPrice", None)
    mutate = lego_apollo(_html_lego(fara_camp), d)
    assert [c["compare_at"] for c in mutate] == [84.99, 189.99], (
        "fara referinta pe varianta, `listPrice` se ia prin cheia construita")


def test_lego_apollo_campanie_forma_cu_referinta():
    """Campania — ACELASI extractor, alt set de campuri emis de query.

    `/ro-ro/page/lego-offers-promotions` e a doua intrare din `entries`. Aici
    `listPrice` are si `formattedValue`, si `currencyCode`, deci se citeste pe
    drumul „bogat". Doua intrari, un singur extractor: exact ce justifica alegerea
    starii in locul CSS-ului.
    """
    from app.services.listing_state_extractors import lego_apollo

    d = listing_descriptor("lego.com")
    html, stare = _stare_lego("lego.com_state_campanie")
    carduri = lego_apollo(html, d)

    assert len(carduri) == 2
    calendar, caine = carduri
    assert (calendar["price"], calendar["compare_at"]) == (50.99, 84.99)
    assert (caine["price"], caine["compare_at"]) == (113.99, 189.99)
    assert calendar["url"] == ("https://www.lego.com/ro-ro/product/"
                               "2026-wall-calendar-5009303")
    assert calendar["image_url"].startswith("https://www.lego.com/cdn/")

    # Ramura „bogata" nu e cod mort: pe campanie referinta CHIAR are campul.
    assert (stare["$ProductVariant:6576805.listPrice"]["formattedValue"]
            == 84.99), "fixture-ul campaniei trebuie sa poarte `formattedValue`"
    assert (stare["$ProductVariant:6576805.listPrice"]["currencyCode"]
            == "RON"), "moneda se citeste din cache, nu din locala vitrinei"

    # A doua serializare Apollo: `{"__ref": ...}` in loc de `{"type": "id", ...}`.
    # NEMASURATA pe lego (dump-urile au numai forma a doua, 42/42), acceptata
    # fiindca cele doua nu coexista intr-un build.
    def in_dunder(o):
        if isinstance(o, dict):
            if o.get("type") == "id" and isinstance(o.get("id"), str):
                return {"__ref": o["id"]}
            return {k: in_dunder(v) for k, v in o.items()}
        if isinstance(o, list):
            return [in_dunder(x) for x in o]
        return o

    mutate = lego_apollo(_html_lego(in_dunder(stare)), d)
    assert [(c["price"], c["compare_at"]) for c in mutate] == [
        (50.99, 84.99), (113.99, 189.99)], "forma `__ref` se rezolva la fel"


def test_lego_apollo_fara_produse_e_final():
    """`?page=500` -> 200 cu grila goala: cache fara nicio cheie
    `SingleVariantProduct:*`, deci `[]`.

    E semnatura de oprire pe care conditia compozita din scanner o asteapta —
    aceeasi ca la altex si flip. Un extractor care ar ridica acolo ar transforma
    finalul normal al paginarii in eroare; unul care ar intoarce ultimele carduri
    ar tine bucla pornita pana la plafon.
    """
    from app.services.listing_state_extractors import lego_apollo

    d = listing_descriptor("lego.com")
    # Cache real ca FORMA (chei de alte tipuri), dar fara niciun produs.
    gol = {"ROOT_QUERY": {"__typename": "Query"},
           "SKUCarousel:blt393e31916f7d0934": {"products": []}}
    assert lego_apollo(_html_lego(gol), d) == []
    # Si pagina care n-are deloc `__NEXT_DATA__`, nu doar cache-ul gol.
    assert lego_apollo("<html><body>nimic</body></html>", d) == []


def test_43einhalb_scopat_la_grila():
    """Cardul e `#prodList div.item-wrapper`, SCOPAT — si scoparea se masoara.

    LST-D3 raportase „69 de `div.item-wrapper` pentru 16 URL-uri distincte" si
    banuise variante responsive. LST-D6 a aratat altceva: niciun stramos n-are
    clasa de breakpoint, iar cele 66 de `.pInfo` se impart 36 in `div#prodList`
    (grila) si 30 in `header#header` (previzualizari de megameniu). Fixture-ul
    poarta ambele familii, deci selectorul nescopat CHIAR scoate un card in plus.

    Miza nu e doar curatenia: pe pagina de coada grila e goala, iar cardurile de
    megameniu ar face-o sa para plina, adica ar sterge chiar semnalul de oprire.
    """
    d = listing_descriptor("43einhalb.com")
    html = _fixture("43einhalb.com")
    carduri = extrage_carduri(html, d, "43einhalb.com")

    assert d["card"] == "#prodList div.item-wrapper"
    assert len(carduri) == 2, "megameniul nu intra in grila"
    assert len({c["url"] for c in carduri}) == 2
    samba, nb = carduri

    assert samba["price"] == 80.0
    assert samba["compare_at"] == 119.95, (
        "referinta e '119,95 UVP' cu exponentul notei de subsol dupa ea: "
        "U+00B2 nu e cifra, deci `eu_comma` citeste 119.95")
    assert samba["url"].endswith(
        "/p/adidas-samba-og-w-wonder-white-dark-brown-gold-metallic-1454553")

    # Al doilea card e LENES — forma majoritara (32/36): `src` e placeholderul
    # `/images/noimage.png`, iar poza reala sta in `data-srcset`. Cu `image_attr`
    # doar pe `src`, controlul dadea 4/36.
    assert nb["price"] == 101.0
    assert "noimage" not in (nb["image_url"] or "")
    assert nb["image_url"].startswith("https://www.43einhalb.com/media/")

    # Aceeasi pagina cu selectorul NESCOPAT: cardul de megameniu apare, si e chiar
    # un duplicat al primului produs din grila.
    nescopat = extrage_carduri(html, dict(d, card="div.item-wrapper"),
                               "43einhalb.com")
    assert len(nescopat) == 3
    assert len({c["url"] for c in nescopat}) == 2, "al treilea e duplicat"


def test_pagina_url_deal_d6():
    """Paginarea celor doua domenii, prin `_intrari` + `_pagina_url`.

    Pe lego intrarile sunt DOUA si numai prima pagineaza: campania e o pagina CMS
    cu carusel, fara `?page=`, deci `max_pages: 1` si niciun template — garda de
    paginare respinge un template care n-ar fi citit oricum niciodata.
    """
    from app.services.listing_scanner import _intrari, _pagina_url

    lego = _intrari(listing_descriptor("lego.com"))
    assert len(lego) == 2
    categorie, campanie = lego

    assert categorie["max_pages"] == 5
    assert (_pagina_url(categorie, 1)
            == "https://www.lego.com/ro-ro/categories/sales-and-deals")
    assert (_pagina_url(categorie, 2)
            == "https://www.lego.com/ro-ro/categories/sales-and-deals?page=2")

    assert campanie["max_pages"] == 1
    assert campanie["page_url_template"] is None, "campania nu pagineaza"
    assert (_pagina_url(campanie, 1)
            == "https://www.lego.com/ro-ro/page/lego-offers-promotions")

    e43 = _intrari(listing_descriptor("43einhalb.com"))[0]
    assert _pagina_url(e43, 1) == "https://www.43einhalb.com/sale"
    assert _pagina_url(e43, 2) == "https://www.43einhalb.com/sale/page/2"


def test_deal_d6_in_registru():
    """Cele doua descriptoare, cu plafoanele explicate.

    `max_pages: 30` pe 43einhalb NU e masuratoare: adancimea reala e ~47 (1.663 de
    produse la 36/pagina, DERIVAT), iar coada e ZID — `page/500` da 403, deci nici
    nu se poate bisecta. 30 e plafonul de buget, conventia altex/mediagalaxy.
    Oprirea REALA e grila goala de la `page/48`; `rel=next` nu e semnal de final
    acolo, fiindca pagina goala inca il anunta.
    """
    from app.services.listing_state_extractors import LISTING_STATE_EXTRACTORS

    assert "lego_apollo" in LISTING_STATE_EXTRACTORS

    lego = listing_descriptor("lego.com")
    assert lego["state_extractor"] == "lego_apollo"
    assert lego["currency"] == "RON"
    assert lego["reference_kind"] == "nemarcat"
    assert [i["max_pages"] for i in lego["entries"]] == [5, 1]
    assert "card" not in lego, "pe calea de stare selectorii CSS n-au ce cauta"

    e43 = listing_descriptor("43einhalb.com")
    assert e43["max_pages"] == 30
    assert e43["image_attr"] == ["data-srcset", "src"]
    assert e43["price_parse"] == "eu_comma"
    assert e43["reference_kind"] == "prp"

    assert {"lego.com", "43einhalb.com"} <= listing_domains()
