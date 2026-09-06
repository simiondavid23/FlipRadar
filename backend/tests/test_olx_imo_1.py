"""OLX-IMO-1 — anunturile Storia incrucisate pe listarea OLX Imobiliare.

Masurat pe `olx_re_listing_state.html` (captura 2026-09-06): 25 din cele 51 de carduri
ale paginii de apartamente Bucuresti nu trimit la OLX, ci la
`storia.ro/ro/oferta/<slug>-ID<token>` — anunturi Storia pe care OLX le incruciseaza in
propria lista. Pana acum `_olx_id` cerea sufixul `.html`, deci ieseau din scraper fara
`external_id` si scannerul le arunca tacut ca "invalid": un keyword doar pe OLX pierdea
jumatate din pagina.

Runda asta le pastreaza, cu `external_id = storia-<token>`, si adauga un dedup
cross-platform pe URL, ca Storia sa ramana sursa primara.

Totul offline: fixture + baza de test. Zero retea.
"""
import asyncio
import os
import uuid

import pytest

from app.scrapers.real_estate._common import url_dedup_key
from app.scrapers.real_estate.olx_real_estate import _external_id_card, _olx_id

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


# ── dubluri de retea (acelasi tipar ca test_date_2) ─────────────────────────────

class _FakeResp:
    def __init__(self, text, status=200):
        self.status_code = status
        self.text = text


class _FakeSession:
    def __init__(self, text):
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        return _FakeResp(self._text)


def _cauta_re(monkeypatch, html: str) -> list:
    from app.scrapers.real_estate import olx_real_estate as re_olx

    monkeypatch.setattr(re_olx, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(re_olx.log_manager, "emit", lambda *a, **k: None)
    # enrichment-ul on-demand ar iesi la retea: il taiem.
    monkeypatch.setattr(re_olx, "_fetch_offer_details", lambda nid: {})
    monkeypatch.setattr(re_olx.time, "sleep", lambda s: None)
    return asyncio.run(re_olx.search_olx_real_estate({}))


# ── T1 — `_olx_id` pe cele patru forme de link ──────────────────────────────────

@pytest.mark.parametrize("href,asteptat", [
    # forma OLX clasica, NESCHIMBATA
    ("https://www.olx.ro/d/oferta/apartament-2-camere-IDkTodo.html", "kTodo"),
    ("/d/oferta/2-camere-megamall-IDkRDRx.html", "kRDRx"),
    # anunt Storia incrucisat: acelasi tipar, FARA `.html`
    ("https://www.storia.ro/ro/oferta/2-camere-piata-alba-iulia-IDHE6J", "HE6J"),
    # fara token deloc
    ("https://www.olx.ro/imobiliare/apartamente-garsoniere-de-vanzare/", None),
    ("https://www.storia.ro/ro/oferta/", None),
    ("", None),
    (None, None),
    # query string / fragment DUPA token, pe ambele forme -> tokenul, curat
    ("/d/oferta/x-IDkTodo.html?search_reason=search%7Cpromoted", "kTodo"),
    ("https://www.storia.ro/ro/oferta/x-IDHE6J?utm_source=olx", "HE6J"),
    ("https://www.storia.ro/ro/oferta/x-IDHE6J#galerie", "HE6J"),
])
def test_t1_olx_id_pe_ambele_forme(href, asteptat):
    assert _olx_id(href) == asteptat


def test_t1b_external_id_prefixat_doar_pe_anunturile_incrucisate():
    """Prefixul `storia-` marcheaza anuntul incrucisat; cardurile OLX raman neatinse."""
    assert _external_id_card(
        "https://www.storia.ro/ro/oferta/2-camere-IDHE6J") == "storia-HE6J"
    # si fara `www`, si pe http — tot anunt Storia
    assert _external_id_card("http://storia.ro/ro/oferta/2-camere-IDHE6J") == "storia-HE6J"
    assert _external_id_card("https://www.olx.ro/d/oferta/x-IDkTodo.html") == "kTodo"
    assert _external_id_card("/d/oferta/x-IDkTodo.html") == "kTodo"
    assert _external_id_card("https://www.olx.ro/imobiliare/") is None
    # un host care doar CONTINE "storia" nu e storia.ro (slug-uri gen "Estoria" exista
    # chiar in baza de dev)
    assert _external_id_card(
        "https://www.olx.ro/d/oferta/estoria-l2-IDkI5OW.html") == "kI5OW"


# ── T2 — fixture: toate cele 51 de carduri au acum external_id ──────────────────

def test_t2_toate_cardurile_au_external_id(monkeypatch):
    """51/51 carduri identificate (MAX_RESULTS taie feed-ul la 50), 25 dintre ele incrucisate.

    Inainte: 26 cu `external_id`, 25 fara — deci 25 de anunturi aruncate de scanner.
    """
    from bs4 import BeautifulSoup

    html = _fixture("olx_re_listing_state.html")
    carduri = BeautifulSoup(html, "html.parser").select('div[data-cy="l-card"]')
    assert len(carduri) == 51
    ids = [_external_id_card(c.find("a", href=True)["href"]) for c in carduri]
    assert [i for i in ids if not i] == [], "niciun card fara external_id"
    assert sum(1 for i in ids if i.startswith("storia-")) == 25

    rezultate = _cauta_re(monkeypatch, html)
    assert len(rezultate) == 50          # MAX_RESULTS
    assert [r for r in rezultate if not r.get("external_id")] == []
    # 24, nu 25: al 51-lea card al paginii (`storia-GPcM`) e taiat de MAX_RESULTS,
    # si se intampla sa fie unul incrucisat.
    incrucisate = [r for r in rezultate if r["external_id"].startswith("storia-")]
    assert len(incrucisate) == 24
    assert ids[50] == "storia-GPcM"


def test_t2b_incrucisatele_primesc_datele_din_state(monkeypatch):
    """Cele 25 iau `listed_at`/`refreshed_at` din meta, ca oricare alt anunt.

    Puntea e id-ul numeric al cardului: state-ul tine anuntul sub tokenul OLX (`kGsBz`),
    cardul trimite la tokenul Storia (`HE6J`).
    """
    rezultate = _cauta_re(monkeypatch, _fixture("olx_re_listing_state.html"))
    incrucisate = [r for r in rezultate if r["external_id"].startswith("storia-")]
    assert len(incrucisate) == 24        # 25 pe pagina, al 51-lea card taiat de MAX_RESULTS
    assert [r["external_id"] for r in incrucisate if not r.get("listed_at")] == []
    assert [r["external_id"] for r in incrucisate if not r.get("refreshed_at")] == []

    # anuntul din brief: card storia.ro/...-IDHE6J <-> ad-ul `kGsBz` din state
    prin_id = {r["external_id"]: r for r in rezultate}
    ad = prin_id["storia-HE6J"]
    assert ad["listed_at"].startswith("2026-06-19")
    assert ad["refreshed_at"].startswith("2026-09-03")


def test_t2c_source_url_e_linkul_storia(monkeypatch):
    """`source_url` ramane URL-ul Storia de pe card — baza dedup-ului cross-platform."""
    rezultate = _cauta_re(monkeypatch, _fixture("olx_re_listing_state.html"))
    incrucisate = [r for r in rezultate if r["external_id"].startswith("storia-")]
    for r in incrucisate:
        assert url_dedup_key(r["source_url"]).startswith("https://storia.ro/ro/oferta/")
    prin_id = {r["external_id"]: r for r in rezultate}
    assert prin_id["storia-HE6J"]["source_url"] == (
        "https://www.storia.ro/ro/oferta/"
        "2-camere-piata-alba-iulia-piscina-spa-rate-fara-dobanda-IDHE6J")
    # cardurile OLX proprii raman pe olx.ro
    proprii = [r for r in rezultate if not r["external_id"].startswith("storia-")]
    assert proprii and all("olx.ro" in r["source_url"] for r in proprii)


def test_t2d_numericul_de_pe_card_e_puntea_catre_state():
    """Dovada mecanismului: meta N-are cheia Storia, dar are id-ul numeric al cardului."""
    from bs4 import BeautifulSoup

    from app.utils.olx_state import extract_olx_ad_meta

    html = _fixture("olx_re_listing_state.html")
    meta = extract_olx_ad_meta(html)
    assert "HE6J" not in meta and "storia-HE6J" not in meta   # cheia Storia lipseste
    assert meta["kGsBz"]["numeric_id"] == 305646457           # dar ad-ul e acolo

    card = BeautifulSoup(html, "html.parser").select_one('div[id="305646457"]')
    assert card is not None
    assert _external_id_card(card.find("a", href=True)["href"]) == "storia-HE6J"


# ── T3 — normalizarea de URL ────────────────────────────────────────────────────

def test_t3_url_dedup_key_ignora_ce_nu_e_identitate():
    canonic = "https://www.storia.ro/ro/oferta/2-camere-alba-iulia-IDHE6J"
    cheie = url_dedup_key(canonic)
    for varianta in [
        canonic,
        canonic + "?utm_source=olx&search_reason=promoted",   # query
        canonic + "#galerie",                                 # fragment
        canonic + "/",                                        # slash final
        canonic.replace("https://www.", "https://"),          # fara www
        canonic.replace("https://www.", "http://www."),       # schema
        canonic.replace("www.storia.ro", "WWW.Storia.RO"),    # majuscule in host
        "  " + canonic + "  ",                                # spatii
    ]:
        assert url_dedup_key(varianta) == cheie, varianta
    assert cheie == "https://storia.ro/ro/oferta/2-camere-alba-iulia-IDHE6J"
    # tokenul e case-sensitive, deci doua anunturi diferite NU se confunda
    assert url_dedup_key(canonic.replace("IDHE6J", "IDhe6j")) != cheie
    assert url_dedup_key("") == "" and url_dedup_key(None) == ""


def test_t3b_storia_si_olx_produc_acelasi_source_url():
    """Pe acelasi token, cele doua scrapere emit URL-uri IDENTICE — nu doar echivalente.

    Storia construieste `_BASE + /ro/oferta/ + slug` din `__NEXT_DATA__`; OLX ia linkul
    de pe card. Masurat pe cele doua fixture-uri: acelasi host (`www.storia.ro`), acelasi
    prefix de path, fara query si fara `.html` pe niciuna dintre parti — de aceea
    `source_url` se stocheaza neatins pe ambele parti, iar normalizarea ramane doar
    cheie de comparare.
    """
    from app.scrapers.real_estate.storia_scraper import _parse_item

    slug = "2-camere-piata-alba-iulia-piscina-spa-rate-fara-dobanda-IDHE6J"
    din_storia = _parse_item({"id": 10502931, "slug": slug, "title": "x"},
                             "vanzare", "apartament")["source_url"]
    # exact forma pe care o poarta cardul OLX pentru acelasi anunt (vezi T2c)
    de_pe_card = f"https://www.storia.ro/ro/oferta/{slug}"
    assert din_storia == de_pe_card
    assert url_dedup_key(din_storia) == url_dedup_key(de_pe_card)


# ── T4/T5 — dedup cross-platform in scanner ─────────────────────────────────────

def _user(db):
    from app.models.user import User

    email = f"olximo1_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0],
             hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _keyword(db, user_id, platform="olx"):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    kw = RealEstateMonitorKeyword(user_id=user_id, name="kw", platform=platform,
                                  property_type="apartament", city="București",
                                  is_active=True)
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


_URL_STORIA = ("https://www.storia.ro/ro/oferta/"
               "2-camere-piata-alba-iulia-piscina-spa-rate-fara-dobanda-IDHE6J")


def _rand_storia(db, user_id, url=_URL_STORIA, external_id="10502931"):
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing

    rand = RealEstateMonitorListing(user_id=user_id, platform="storia",
                                    external_id=external_id, title="2 camere",
                                    price=120000, currency="EUR", url=url)
    db.add(rand)
    db.commit()
    return rand


def _raw_incrucisat(url=_URL_STORIA):
    return {"external_id": "storia-HE6J", "titlu": "2 camere Piata Alba Iulia",
            "pret": 120000, "moneda": "EUR", "source_url": url,
            "suprafata_mp": 55, "camere": 2}


def test_t4_dedup_cand_storia_are_deja_anuntul():
    from app.database import SessionLocal
    from app.services import real_estate_scanner as rs

    db = SessionLocal()
    try:
        u = _user(db)
        kw = _keyword(db, u.id)
        _rand_storia(db, u.id)
        listing, motiv = rs._save_listing(db, kw, _raw_incrucisat(), None, {})
        assert (listing, motiv) == (None, "dedup_storia")
    finally:
        db.close()


@pytest.mark.parametrize("stocat", [
    _URL_STORIA + "?utm=1",
    _URL_STORIA.replace("https://www.", "https://"),
    _URL_STORIA + "/",
])
def test_t4b_dedup_si_cand_urlul_stocat_difera_prin_forma(stocat):
    """Randul Storia salvat cu alta forma de URL blocheaza tot inserarea."""
    from app.database import SessionLocal
    from app.services import real_estate_scanner as rs

    db = SessionLocal()
    try:
        u = _user(db)
        kw = _keyword(db, u.id)
        _rand_storia(db, u.id, url=stocat)
        _, motiv = rs._save_listing(db, kw, _raw_incrucisat(), None, {})
        assert motiv == "dedup_storia", stocat
    finally:
        db.close()


def test_t4c_fara_rand_storia_anuntul_se_insereaza_ca_olx():
    from app.database import SessionLocal
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing
    from app.services import real_estate_scanner as rs

    db = SessionLocal()
    try:
        u = _user(db)
        kw = _keyword(db, u.id)
        listing, motiv = rs._save_listing(db, kw, _raw_incrucisat(), None, {})
        assert motiv == "nou" and listing is not None
        rand = db.query(RealEstateMonitorListing).filter_by(
            external_id="storia-HE6J").one()
        assert rand.platform == "olx"
        assert rand.url == _URL_STORIA
        assert rand.user_id == u.id
    finally:
        db.close()


def test_t4d_un_anunt_olx_obisnuit_nu_atinge_verificarea_de_url(monkeypatch):
    """Regresie: pentru un `external_id` normal nu se face niciun query pe URL.

    Numaram apelurile la `_url_deja_salvat` — verificarea trebuie sa ramana strict
    rezervata anunturilor incrucisate, altfel fiecare anunt OLX ar costa un query in plus.
    """
    from app.database import SessionLocal
    from app.services import real_estate_scanner as rs

    apeluri = []
    original = rs._url_deja_salvat

    def _spion(db, uid, url):
        apeluri.append(url)
        return original(db, uid, url)

    monkeypatch.setattr(rs, "_url_deja_salvat", _spion)
    db = SessionLocal()
    try:
        u = _user(db)
        kw = _keyword(db, u.id)
        _rand_storia(db, u.id)   # randul Storia exista, dar nu trebuie consultat
        raw = {"external_id": "kTodo", "titlu": "Apartament 2 camere",
               "pret": 95000, "moneda": "EUR", "suprafata_mp": 55, "camere": 2,
               "source_url": _URL_STORIA}   # chiar si cu URL identic!
        _, motiv = rs._save_listing(db, kw, raw, None, {})
        assert motiv == "nou"
        assert apeluri == [], "anunturile OLX obisnuite nu trec prin dedup-ul pe URL"
    finally:
        db.close()


def test_t5_dedup_e_per_user():
    """Acelasi URL la ALT utilizator nu blocheaza inserarea."""
    from app.database import SessionLocal
    from app.services import real_estate_scanner as rs

    db = SessionLocal()
    try:
        altul = _user(db)
        u = _user(db)
        db.commit()
        _rand_storia(db, altul.id)          # randul Storia e al ALTUI user
        kw = _keyword(db, u.id)
        _, motiv = rs._save_listing(db, kw, _raw_incrucisat(), None, {})
        assert motiv == "nou"
    finally:
        db.close()


def test_t5b_al_doilea_scan_da_duplicat_nu_dedup():
    """Dupa ce anuntul e salvat sub OLX, scanul urmator il vede ca `duplicat`.

    Ordinea conteaza: ramura `existing` (care actualizeaza pretul) e INAINTEA
    dedup-ului, altfel un anunt incrucisat salvat de noi n-ar mai primi update-uri.
    """
    from app.database import SessionLocal
    from app.services import real_estate_scanner as rs

    db = SessionLocal()
    try:
        u = _user(db)
        kw = _keyword(db, u.id)
        assert rs._save_listing(db, kw, _raw_incrucisat(), None, {})[1] == "nou"
        assert rs._save_listing(db, kw, _raw_incrucisat(), None, {})[1] == "duplicat"
    finally:
        db.close()
