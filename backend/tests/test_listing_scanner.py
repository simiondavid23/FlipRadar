"""DEAL-2 — scannerul de listari HTML pe magazine non-Shopify.

Toate testele sunt OFFLINE: fetch-ul e monkeypatch-uit peste tot, ZERO retea
(doctrina BNR-1c). Fixture-urile de parsare NU sunt inventate — sunt fragmente
DECUPATE din dump-urile reale ale sondelor LST-1/LST-1b
(`scripts/diagnostics/dumps_lst1/<domeniu>_p1.html`), cu 3 carduri complete
fiecare, iar preturile asteptate mai jos sunt exact cele masurate acolo.
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
        return _Raspuns(pagini[indice] if indice < len(pagini) else "<html></html>")

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

def test_listing_domains_exact_cele_patru_pilot():
    assert listing_domains() == {"otter.ro", "caseking.de", "noriel.ro", "bergfreunde.eu"}


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
