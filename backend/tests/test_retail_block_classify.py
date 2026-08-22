"""AMZ-1a — clasificarea blocajelor in poarta de fetch retail.

Pana la runda asta calea retail n-avea nicio notiune de „blocat": un interstitiu
anti-bot servit cu HTTP 200 ajungea la extractor ca HTML valid si iesea ca
`no_product_data` — adica „markup schimbat", nu „blocat". Sonda AMZ-0 a dovedit
unghiul mort in modul cel mai direct: propria ei masuratoare a fost citita gresit
exact asa.

Doua niveluri de verificare, deliberat:
  * POARTA (`_fetch_shop_url_guarded`) — ce FORMA de rezultat iese pe fiecare clasa
    de raspuns. Aici se vede diferenta „None (zid)" vs „response (continut)".
  * CAPAT-LA-CAPAT (`extract_product`) — cu `parse_product_html` inlocuit de un SPY.
    Asta e proprietatea care conteaza: body-ul unui zid nu are voie sa ajunga la
    parser. Un test doar pe poarta ar trece si daca cineva ar re-parsa mai jos.

Fara retea: `curl_requests.get` e stubuit in ambele module, iar fixture-ul autouse
din conftest ramane in vigoare.
"""
import pytest

from app.services import product_page_extractor as ppe
from app.services import scraper_service as ss
from app.services.product_page_extractor import ProductExtractionError
from app.services.radar.base_scraper import INTERSTITIAL_MAX_BYTES

DOMENIU = "test.example"
URL = f"https://{DOMENIU}/p/1"


class _Resp:
    """Raspuns minimal, cu exact campurile pe care le atinge poarta."""

    def __init__(self, status, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


def _pagina_normala(marker: str = "", octeti: int = 0) -> str:
    """HTML de produs valid, optional umflat peste un prag si cu un marker inclus."""
    corp = ('<html><head><title>Produs</title></head><body>'
            '<div itemscope itemtype="http://schema.org/Product">'
            '<span itemprop="name">Produs</span>'
            '<span itemprop="price">10.00</span>'
            f'</div>{marker}')
    if octeti and len(corp) < octeti:
        corp += "<!--" + ("x" * (octeti - len(corp))) + "-->"
    return corp + "</body></html>"


@pytest.fixture
def mediu(monkeypatch):
    """Domeniu permis, fara retea, fara log, fara sleep. Intoarce un dispecer."""
    monkeypatch.setattr(ss, "VALIDATED_DOMAINS", set(ss.VALIDATED_DOMAINS) | {DOMENIU})
    monkeypatch.setattr(ss.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(ppe.time, "sleep", lambda s: None)
    monkeypatch.setattr(ss.time, "sleep", lambda s: None)

    stare = {"raspunsuri": [], "cereri": 0, "spy": 0, "warn": []}

    def emit(modul, nivel, mesaj):
        if nivel == "WARN":
            stare["warn"].append(mesaj)

    monkeypatch.setattr(ss.log_manager, "emit", emit)

    def fake_get(url, **kw):
        stare["cereri"] += 1
        item = (stare["raspunsuri"][stare["cereri"] - 1]
                if stare["cereri"] <= len(stare["raspunsuri"])
                else stare["raspunsuri"][-1])
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(ss.curl_requests, "get", fake_get)

    real_parse = ppe.parse_product_html

    def spy_parse(html, url):
        stare["spy"] += 1
        return real_parse(html, url)

    monkeypatch.setattr(ppe, "parse_product_html", spy_parse)

    def seteaza(*raspunsuri):
        stare["raspunsuri"] = list(raspunsuri)
        stare["cereri"] = 0
        stare["spy"] = 0
        stare["warn"] = []

    stare["seteaza"] = seteaza
    return stare


def _poarta(url=URL):
    return ss._fetch_shop_url_guarded(url, headers={}, timeout=5)


def _motiv_extract(url=URL):
    """Motivul ProductExtractionError ridicat de extract_product, sau None la succes."""
    try:
        ppe.extract_product(url)
        return None
    except ProductExtractionError as exc:
        return exc.reason


# ── 1a. interstitiu de 200 cu marker GENERIC ────────────────────────────────────
def test_01a_200_marker_generic_e_blocaj_iar_parserul_nu_e_atins(mediu):
    mediu["seteaza"](_Resp(200, "<html>captcha-delivery</html>"))
    assert _poarta() is None
    mediu["seteaza"](_Resp(200, "<html>captcha-delivery</html>"))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


# ── 1b. acelasi caz, dar cu markerul REAL al lui amazon.de ──────────────────────
def test_01b_200_validatecaptcha_cere_marker_per_domeniu(mediu, monkeypatch):
    """`validateCaptcha` NU e marker generic — vezi nota din raport.

    Fara cheia per-domeniu pagina trece de poarta; cu ea, e blocaj. Exact
    configuratia cu care intra amazon.de la AMZ-1.
    """
    corp = "<html>validateCaptcha</html>"
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is not None, "fara cheia per-domeniu nu e marker"

    monkeypatch.setitem(ss._MARKERI_BLOCAJ_DOMENIU, DOMENIU, ("validatecaptcha",))
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is None
    mediu["seteaza"](_Resp(200, corp))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


# ── 2. „just a moment" — ancorat pe <title> ─────────────────────────────────────
def test_02_200_just_a_moment_pe_titlu_e_blocaj(mediu):
    mediu["seteaza"](_Resp(200, "<html><title>Just a moment...</title></html>"))
    assert _poarta() is None
    mediu["seteaza"](_Resp(200, "<html><title>Just a moment...</title></html>"))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


def test_02b_just_a_moment_in_proza_NU_e_blocaj(mediu):
    """Ancora pe titlu e deliberata: proza dintr-o descriere nu blocheaza POARTA.

    Delimitare importanta, gasita rulind testul: extractorul are, de dinaintea lui
    AMZ-1a, propriul test `"just a moment" in text[:2000]` — FARA ancora pe <title> —
    deci el respinge pagina asta cu `challenge` chiar daca poarta o lasa sa treaca.
    Contractul lui AMZ-1a e despre POARTA, iar aici il verificam pe acela; verificarea
    de mai jos pinuieste si divergenta, ca sa se vada daca cineva o repara candva.
    """
    corp = _pagina_normala(marker="<p>just a moment, hai sa vad</p>")
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is not None, "poarta NU blocheaza proza — ancora e pe <title>"
    assert mediu["warn"] == []
    mediu["seteaza"](_Resp(200, corp))
    assert _motiv_extract() == "challenge", (
        "divergenta cunoscuta: verificarea veche din extractor e neancorata")


# ── 3. marker pe pagina MARE: pragul il face neconcludent ───────────────────────
def test_03_marker_peste_prag_nu_blocheaza(mediu):
    corp = _pagina_normala(marker="captcha-delivery",
                           octeti=INTERSTITIAL_MAX_BYTES + 5_000)
    assert len(corp) > INTERSTITIAL_MAX_BYTES
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is not None
    mediu["seteaza"](_Resp(200, corp))
    assert _motiv_extract() is None
    assert mediu["spy"] == 1


# ── 4. pagina curata: nimic schimbat ────────────────────────────────────────────
def test_04_200_curat_ajunge_la_parser(mediu):
    corp = _pagina_normala()
    mediu["seteaza"](_Resp(200, corp))
    raspuns = _poarta()
    assert raspuns is not None and raspuns.status_code == 200
    mediu["seteaza"](_Resp(200, corp))
    assert _motiv_extract() is None
    assert mediu["spy"] == 1
    assert mediu["warn"] == []


# ── 5 / 6. status care e zid prin el insusi ─────────────────────────────────────
def test_05_403_e_blocaj(mediu):
    mediu["seteaza"](_Resp(403, "<html>orice</html>"))
    assert _poarta() is None
    assert any("outcome=blocked" in m for m in mediu["warn"])
    mediu["seteaza"](_Resp(403, "<html>orice</html>"))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


def test_06_429_e_rate_limited(mediu):
    mediu["seteaza"](_Resp(429, "<html>orice</html>"))
    assert _poarta() is None
    assert any("outcome=rate_limited" in m for m in mediu["warn"])
    mediu["seteaza"](_Resp(429, "<html>orice</html>"))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


# ── 7 / 8. ce NU se schimba ─────────────────────────────────────────────────────
def test_07_404_ajunge_NESCHIMBAT_la_apelant(mediu):
    """404 e NOT_FOUND, nu blocaj: listing_scanner il citeste ca sfarsit de paginare,
    deci trebuie sa primeasca RASPUNSUL, nu None (comportamentul de dinainte)."""
    mediu["seteaza"](_Resp(404, "<html>nu exista</html>"))
    raspuns = _poarta()
    assert raspuns is not None and raspuns.status_code == 404
    assert mediu["warn"] == []


def test_08_exceptia_de_retea_da_None_ca_inainte(mediu):
    mediu["seteaza"](RuntimeError("conexiune picata"))
    assert _poarta() is None
    assert mediu["warn"] == [], "eroarea de retea nu e blocaj, deci fara WARN"


# ── 9 / 10 / 11. chei per domeniu ───────────────────────────────────────────────
def test_09_marker_propriu_de_domeniu_blocheaza(mediu, monkeypatch):
    monkeypatch.setitem(ss._MARKERI_BLOCAJ_DOMENIU, DOMENIU, ("marker-propriu",))
    mediu["seteaza"](_Resp(200, "<html>marker-propriu</html>"))
    assert _poarta() is None
    mediu["seteaza"](_Resp(200, "<html>marker-propriu</html>"))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


def test_10_acelasi_domeniu_fara_marker_trece(mediu, monkeypatch):
    monkeypatch.setitem(ss._MARKERI_BLOCAJ_DOMENIU, DOMENIU, ("marker-propriu",))
    corp = _pagina_normala()
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is not None
    mediu["seteaza"](_Resp(200, corp))
    assert _motiv_extract() is None
    assert mediu["spy"] == 1


def test_11_prag_propriu_de_domeniu_prinde_pagina_mare(mediu, monkeypatch):
    monkeypatch.setitem(ss._MARKERI_BLOCAJ_DOMENIU, DOMENIU, ("validatecaptcha",))
    monkeypatch.setitem(ss._PRAG_INTERSTITIU_DOMENIU, DOMENIU, 100_000)
    corp = "<html>validateCaptcha" + ("x" * 60_000) + "</html>"
    assert INTERSTITIAL_MAX_BYTES < len(corp) < 100_000
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is None, "cu pragul generic ar fi trecut; cu cel propriu, nu"

    # controlul simetric: fara pragul propriu, ACEEASI pagina trece
    monkeypatch.delitem(ss._PRAG_INTERSTITIU_DOMENIU, DOMENIU)
    mediu["seteaza"](_Resp(200, corp))
    assert _poarta() is not None


# ── 12. apelantii care reactioneaza la rezultat gol ─────────────────────────────
def test_12_deal_scanner_ridica_in_loc_sa_inchida_dealuri(mediu):
    """PASUL 0.2: `_pagini` ridica RuntimeError la fetch esuat, iar exceptia escapa
    INAINTE de blocul care inchide deal-urile si inainte de commit. Un blocaj nu
    are voie sa arate ca „magazinul n-are produse"."""
    from app.services.deal_scanner import _pagini

    mediu["seteaza"](_Resp(403, "<html>zid</html>"))
    with pytest.raises(RuntimeError):
        list(_pagini(DOMENIU))


def test_12b_listing_scanner_ridica_pe_blocaj(mediu, monkeypatch):
    """Simetric, pe calea de listari: acelasi contract de eroare."""
    from app.services import listing_scanner as ls

    monkeypatch.setattr(ls, "listing_descriptor",
                        lambda d: {"url": URL, "max_pages": 1, "card": "div"})
    mediu["seteaza"](_Resp(403, "<html>zid</html>"))
    with pytest.raises(Exception) as info:
        ls._scaneaza_domeniu(None, DOMENIU, None, 40.0)
    assert not isinstance(info.value, AssertionError)


def test_12c_blocajul_nu_scrie_in_stock_False(mediu):
    """`refresh_source` prinde ProductExtractionError si cade pe cautare — NU
    intoarce un dict cu in_stock=False. Un blocaj nu marcheaza produsul epuizat."""
    mediu["seteaza"](_Resp(403, "<html>zid</html>"))
    rezultat = ss.refresh_source(DOMENIU, URL, "Produs")
    assert rezultat is None or rezultat.get("in_stock") is not False


# ── 13 / 14. AWS WAF pe status 202 ──────────────────────────────────────────────
def test_13_202_cu_marker_waf_e_blocaj(mediu):
    """`classify()` verifica markerii DOAR pe 200, deci fara ramura proprie
    provocarea AWS WAF ar iesi OK. Masurat in AMZ-0: 2 008 octeti pe 202."""
    corp = ("<html><script>window.awsWafCookieDomainList=[];</script>"
            "<script src='https://x.token.awswaf.com/challenge.js'></script></html>")
    mediu["seteaza"](_Resp(202, corp))
    assert _poarta() is None
    assert any("outcome=blocked" in m for m in mediu["warn"])
    mediu["seteaza"](_Resp(202, corp))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0


def test_14_202_curat_ajunge_la_apelant_ca_inainte(mediu):
    """Un 202 fara markeri WAF nu e zid: ramane comportamentul de dinainte."""
    corp = _pagina_normala()
    mediu["seteaza"](_Resp(202, corp))
    raspuns = _poarta()
    assert raspuns is not None and raspuns.status_code == 202
    assert mediu["warn"] == []


# ── 15. 5xx ramane TRANSIENT ────────────────────────────────────────────────────
def test_15_503_e_transient_nu_blocaj(mediu):
    """503 cu `api-services-support@amazon.com` in body: markerul e prezent, dar
    ordinea din `classify()` da TRANSIENT pe 5xx INAINTE de a privi body-ul.
    Deci raspunsul ajunge la apelant ca pana acum, iar parserul nu e atins."""
    corp = "<html>api-services-support@amazon.com</html>"
    mediu["seteaza"](_Resp(503, corp))
    raspuns = _poarta()
    assert raspuns is not None and raspuns.status_code == 503
    assert mediu["warn"] == [], "5xx nu e blocaj -> fara WARN"

    mediu["seteaza"](_Resp(503, corp))
    assert _motiv_extract() == "fetch_failed"
    assert mediu["spy"] == 0
    # fara retry SUPLIMENTAR: exact cele 3 incercari de dinainte
    assert mediu["cereri"] == 3


# ── garda: `parsed=None`, nu `parsed=0` ────────────────────────────────────────
def test_17_pagina_curata_e_OK_nu_SITE_CHANGED(mediu):
    """Poarta n-a parsat inca nimic, deci NU are voie sa spuna „markup schimbat".

    `classify(parsed=0)` inseamna „am parsat si n-am gasit nimic" -> SITE_CHANGED.
    Poarta trebuie sa trimita `parsed=None` = „n-am parsat inca". Verificarea e pe
    OUTCOME, nu pe „a blocat sau nu": nici OK, nici SITE_CHANGED nu blocheaza, deci
    un test doar pe comportament ar trece si cu valoarea gresita — exact ce s-a
    intamplat la controlul negativ S2 inainte ca `_clasifica_raspuns` sa intoarca
    Outcome-ul.
    """
    from app.services.radar.base_scraper import Outcome

    assert ss._clasifica_raspuns(URL, _Resp(200, _pagina_normala())) is Outcome.OK


def test_17b_outcome_uri_care_NU_opresc_fluxul(mediu):
    """Setul care opreste fluxul e exact {BLOCKED, RATE_LIMITED} — pinuit."""
    from app.services.radar.base_scraper import Outcome

    assert set(ss._REZULTATE_ZID) == {Outcome.BLOCKED, Outcome.RATE_LIMITED}
    assert ss._clasifica_raspuns(URL, _Resp(404, "x")) is Outcome.NOT_FOUND
    assert ss._clasifica_raspuns(URL, _Resp(503, "x")) is Outcome.TRANSIENT
    assert ss._clasifica_raspuns(URL, _Resp(403, "x")) is Outcome.BLOCKED
    assert ss._clasifica_raspuns(URL, _Resp(429, "x")) is Outcome.RATE_LIMITED


# ── garda: 404 nu devine blocaj din cauza unui marker in body ───────────────────
def test_16_404_cu_marker_ramane_not_found(mediu, monkeypatch):
    """Masurat la AMZ-0: paginile 404 ale Amazonului poarta chiar
    `api-services-support@amazon.com`. E sigur DOAR fiindca `classify()` verifica
    statusul 404 inaintea markerilor — testul pinuieste ordinea aia."""
    monkeypatch.setitem(ss._MARKERI_BLOCAJ_DOMENIU, DOMENIU,
                        ("api-services-support@amazon.com",))
    mediu["seteaza"](_Resp(404, "<html>api-services-support@amazon.com</html>"))
    raspuns = _poarta()
    assert raspuns is not None and raspuns.status_code == 404
