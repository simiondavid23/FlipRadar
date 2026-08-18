"""FBS-5 — consumatorii citesc din bazin, cu retentie pe durata fixa.

Testul care conteaza cel mai mult e `test_forma_identica_*`: aceleasi date, o data
prin calea vie (nucleu) si o data prin bazin, trebuie sa produca EXACT aceeasi
structura. Daca difera o cheie sau un tip, interfata se rupe TACIT la comutare.

Garantia nu e „am scris cu atentie doua implementari" — e ca ambele cai trec prin
ACELASI formator (`_din_canonice`, `_din_canonice_auto`, `_adauga_canonice_re`),
extras la FBS-5 exact ca sa nu existe doua forme de intretinut.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.models.fb_pool import FbPoolListing
from app.scrapers.facebook import bazin
from app.services.log_manager import log_manager

import app.services.radar.facebook_scraper as rad
import app.scrapers.auto.listings.facebook_auto_scraper as auto
import app.scrapers.real_estate.facebook_real_estate as re_m


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _curat(monkeypatch):
    for v in ("FB_MOD", "FB_BAZIN_RETENTIE_ZILE"):
        monkeypatch.delenv(v, raising=False)
    yield


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda m, n, msg: capturate.append((n, msg)))
    return capturate


def _canonic(ext="111", *, price=1000.0, title="Canapea extensibila",
             cat="1583634935226685", listed=None):
    return {
        "external_id": ext, "title": title, "price": price, "currency": "RON",
        "location": "Cluj-Napoca", "image_url": "https://img/1.jpg",
        "listed_at": listed or datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc),
        "category_id": cat, "source_url": f"https://www.facebook.com/marketplace/item/{ext}/",
    }


def _in_bazin(db, modul, keyword_id, c, *, ultima=None, prima=None):
    acum = datetime.utcnow()
    listed = c.get("listed_at")
    r = FbPoolListing(
        modul=modul, keyword_id=keyword_id, external_id=c["external_id"],
        ancora="cluj-napoca", title=c["title"], price=c["price"],
        currency=c["currency"], location=c["location"],
        source_url=c["source_url"], image_url=c["image_url"],
        category_id=c["category_id"],
        listed_at=(listed.isoformat() if hasattr(listed, "isoformat") else listed),
        prima_vedere_at=prima or acum, ultima_vedere_at=ultima or acum)
    db.add(r)
    db.commit()
    return r


# ── 1-3. dispecerul: implicitul si redenumirea ───────────────────────────────
def test_fara_fb_mod_comportamentul_e_neschimbat(monkeypatch):
    """Cea mai importanta garantie a rundei: runda NU inlocuieste nimic."""
    chemat = {"n": 0}
    for modul, fn, args in (
        (rad, "_search_sesiune", ("canapea", 1000.0, None, None, [], None, None, None, 1, 10)),
        (auto, "_search_sesiune", ("bmw", {}, 1, 10, None)),
        (re_m, "_search_sesiune", ("garsoniera", {}, None)),
    ):
        monkeypatch.setattr(modul, fn, lambda *a, **k: chemat.__setitem__("n", chemat["n"] + 1) or [])
    rad.search_facebook(keyword="canapea", max_price=1000.0)
    auto.search_facebook_auto(query="bmw")
    re_m.search_facebook_real_estate(query="garsoniera")

    assert chemat["n"] == 3, "toate trei trebuie sa mearga pe calea de sesiune"


def test_fb_mod_nucleu_merge_la_nucleu(monkeypatch, logs):
    monkeypatch.setenv("FB_MOD", "nucleu")
    monkeypatch.setattr(rad, "_search_logout", lambda *a, **k: [{"marca": "nucleu"}])

    assert rad.search_facebook(keyword="canapea", max_price=0) == [{"marca": "nucleu"}]
    assert not any("INVECHIT" in m for _n, m in logs)


def test_fb_mod_logout_e_alias_cu_warn(monkeypatch, logs):
    """`logout` trimitea la nucleu — iar nucleul e AUTENTIFICAT din FBS-1. Numele
    descria ceva ce nu mai e adevarat, deci ramane alias, dar zgomotos."""
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setattr(rad, "_search_logout", lambda *a, **k: [{"marca": "nucleu"}])

    assert rad.search_facebook(keyword="canapea", max_price=0) == [{"marca": "nucleu"}]
    assert any("INVECHIT" in m and "nucleu" in m for _n, m in logs)


# ── 4-6. bazinul nu atinge reteaua ───────────────────────────────────────────
def test_bazin_nu_atinge_reteaua(db, monkeypatch, clean_db=None):
    monkeypatch.setenv("FB_MOD", "bazin")
    apeluri = {"n": 0}

    def _explodeaza(*a, **k):
        apeluri["n"] += 1
        raise AssertionError("calea `bazin` nu are voie sa scrapeze")

    monkeypatch.setattr(rad, "nucleu_search", _explodeaza)
    monkeypatch.setattr(rad, "_search_sesiune", _explodeaza)

    _in_bazin(db, "radar", 42, _canonic("111"))
    rez = rad.search_facebook(keyword="canapea", max_price=0, keyword_id=42)

    assert apeluri["n"] == 0
    assert len(rez) == 1 and rez[0]["external_id"] == "fb_111"


def test_bazin_fara_keyword_id_cade_pe_nucleu_cu_marcaj_manual(monkeypatch, logs):
    """FBS-5b, varianta 1: cererile FARA `keyword_id` sunt cele manuale (dupa cablarea
    celor trei scanneri), iar pentru omul care a apasat «cauta acum» lista goala ar
    fi zero rezultate fara explicatie. Cad pe NUCLEU, si linia de jurnal o marcheaza
    ca manuala, ca traficul manual sa fie vizibil separat."""
    monkeypatch.setenv("FB_MOD", "bazin")
    monkeypatch.setattr(rad, "_search_logout", lambda *a, **k: [{"marca": "nucleu"}])
    monkeypatch.setattr(rad, "_search_sesiune",
                        lambda *a, **k: pytest.fail("scutirea merge la NUCLEU, nu la sesiune"))

    rez = rad.search_facebook(keyword="canapea", max_price=0)

    assert rez == [{"marca": "nucleu"}]
    assert any(m.startswith("FBMANUAL") and "cautare manuala" in m for _n, m in logs)


def test_bazin_gol_intoarce_lista_goala_nu_exceptie(db, monkeypatch):
    monkeypatch.setenv("FB_MOD", "bazin")

    assert rad.search_facebook(keyword="canapea", max_price=0, keyword_id=99999) == []


# ── 7-9. FORMA IDENTICA — testul central al rundei ───────────────────────────
def test_forma_identica_radar(db, monkeypatch):
    c = _canonic("111")
    monkeypatch.setenv("FB_MOD", "nucleu")
    monkeypatch.setattr(rad, "nucleu_search", lambda *a, **k: [dict(c)])
    viu = rad.search_facebook(keyword="canapea", max_price=0)

    _in_bazin(db, "radar", 7, c)
    monkeypatch.setenv("FB_MOD", "bazin")
    din_bazin = rad.search_facebook(keyword="canapea", max_price=0, keyword_id=7)

    assert viu == din_bazin, "aceleasi date -> aceeasi structura, cheie cu cheie"
    assert {k: type(v).__name__ for k, v in viu[0].items()} == \
           {k: type(v).__name__ for k, v in din_bazin[0].items()}


def test_forma_identica_auto(db, monkeypatch):
    c = _canonic("222", title="BMW 320d 2015 180000 km", cat=None)
    monkeypatch.setattr(auto, "_vehicles_category_id", lambda: None)
    monkeypatch.setenv("FB_MOD", "nucleu")
    monkeypatch.setattr(auto, "nucleu_search", lambda *a, **k: [dict(c)])
    viu = auto.search_facebook_auto(query="bmw")

    _in_bazin(db, "auto", 8, c)
    monkeypatch.setenv("FB_MOD", "bazin")
    din_bazin = auto.search_facebook_auto(query="bmw", keyword_id=8)

    assert viu == din_bazin
    assert viu and viu[0]["platform"] == "facebook_auto"


def test_forma_identica_imobiliare(db, monkeypatch):
    cat = sorted(re_m._categorii_permise())[0]
    c = _canonic("333", title="Garsoniera de inchiriat", cat=cat)
    monkeypatch.setenv("FB_MOD", "nucleu")
    monkeypatch.setattr(re_m, "nucleu_search", lambda *a, **k: [dict(c)])
    viu = re_m.search_facebook_real_estate(query="garsoniera", filters={})

    _in_bazin(db, "real_estate", 9, c)
    monkeypatch.setenv("FB_MOD", "bazin")
    din_bazin = re_m.search_facebook_real_estate(query="garsoniera", filters={},
                                                 keyword_id=9)

    assert viu == din_bazin
    assert viu and isinstance(viu[0]["listed_at"], str), "Imobiliare vrea ISO string"


def test_listed_at_supravietuieste_dus_intors(db):
    """Bazinul tine `listed_at` ca string ISO; `canonic` il da aware. Conversia
    inversa se face in `bazin`, o singura data — altfel Radar ar primi string si ar
    crapa in `_naiv_local`, iar Imobiliare ar face `fromisoformat` pe un obiect."""
    c = _canonic("444")
    _in_bazin(db, "radar", 11, c)

    din_bazin = bazin.citeste(db, "radar", 11)

    assert isinstance(din_bazin[0]["listed_at"], datetime)
    assert din_bazin[0]["listed_at"].tzinfo is not None
    assert din_bazin[0]["listed_at"] == c["listed_at"]


# ── 10-12. filtrele client-side ──────────────────────────────────────────────
def test_filtrele_de_pret_se_aplica_pe_bazin(db, monkeypatch):
    monkeypatch.setenv("FB_MOD", "bazin")
    _in_bazin(db, "radar", 21, _canonic("a", price=500.0))
    _in_bazin(db, "radar", 21, _canonic("b", price=5000.0))

    ieftine = rad.search_facebook(keyword="canapea", max_price=1000.0, keyword_id=21)
    scumpe = rad.search_facebook(keyword="canapea", max_price=0, min_price=2000.0,
                                 keyword_id=21)

    assert [r["external_id"] for r in ieftine] == ["fb_a"]
    assert [r["external_id"] for r in scumpe] == ["fb_b"]


def test_cuvintele_excluse_se_aplica_pe_bazin(db, monkeypatch):
    monkeypatch.setenv("FB_MOD", "bazin")
    _in_bazin(db, "radar", 22, _canonic("a", title="Canapea buna"))
    _in_bazin(db, "radar", 22, _canonic("b", title="Canapea stricata"))

    rez = rad.search_facebook(keyword="canapea", max_price=0, keyword_id=22,
                              exclude_words=["stricata"])

    assert [r["external_id"] for r in rez] == ["fb_a"]


def test_filtrul_de_categorie_se_aplica_pe_bazin(db, monkeypatch):
    monkeypatch.setenv("FB_MOD", "bazin")
    _in_bazin(db, "radar", 23, _canonic("a", cat="111"))
    _in_bazin(db, "radar", 23, _canonic("b", cat="222"))

    rez = rad.search_facebook(keyword="canapea", max_price=0, keyword_id=23,
                              category="111")

    assert [r["external_id"] for r in rez] == ["fb_a"]


def test_bazinul_e_filtrat_pe_modul_si_keyword(db, monkeypatch):
    monkeypatch.setenv("FB_MOD", "bazin")
    _in_bazin(db, "radar", 31, _canonic("al-meu"))
    _in_bazin(db, "radar", 32, _canonic("al-altui-keyword"))
    _in_bazin(db, "auto", 31, _canonic("al-altui-modul"))

    rez = rad.search_facebook(keyword="canapea", max_price=0, keyword_id=31)

    assert [r["external_id"] for r in rez] == ["fb_al-meu"]


# ── 13. garda de paginare, inaintea dispecerului ─────────────────────────────
def test_page_mai_mare_de_1_intoarce_gol_in_toate_modurile(db, monkeypatch):
    for mod in ("sesiune", "nucleu", "bazin"):
        monkeypatch.setenv("FB_MOD", mod)
        assert rad.search_facebook(keyword="c", max_price=0, page=2, keyword_id=1) == []
        assert auto.search_facebook_auto(query="c", page=2, keyword_id=1) == []


# ── 14-16. retentia ──────────────────────────────────────────────────────────
def test_retentia_sterge_pe_ultima_vedere_nu_pe_prima(db):
    """Testul central al retentiei: un anunt VECHI dar inca vazut e VIU. Stergerea pe
    `prima_vedere_at` ar arunca exact anunturile de lunga durata."""
    acum = datetime.utcnow()
    _in_bazin(db, "radar", 41, _canonic("vechi-dar-viu"),
              prima=acum - timedelta(days=30), ultima=acum - timedelta(hours=2))
    _in_bazin(db, "radar", 41, _canonic("nou-dar-mort"),
              prima=acum - timedelta(days=1), ultima=acum - timedelta(days=20))

    sterse = bazin.sterge_vechi(db, 7)

    ramase = [r.external_id for r in db.query(FbPoolListing).all()]
    assert sterse == 1
    assert ramase == ["vechi-dar-viu"]


def test_retentia_respecta_pragul(db):
    acum = datetime.utcnow()
    _in_bazin(db, "radar", 42, _canonic("x"), ultima=acum - timedelta(days=5))

    assert bazin.sterge_vechi(db, 7) == 0, "5 zile < prag 7"
    assert bazin.sterge_vechi(db, 3) == 1, "5 zile > prag 3"


def test_marimea_bazinului_raporteaza_pe_module(db):
    acum = datetime.utcnow()
    _in_bazin(db, "radar", 51, _canonic("a"), ultima=acum - timedelta(days=3))
    _in_bazin(db, "auto", 51, _canonic("b"))

    m = bazin.marime(db)

    assert m["total"] == 2
    assert m["pe_modul"] == {"radar": 1, "auto": 1}
    assert 2.9 < m["varsta_maxima_zile"] < 3.1


# ── 17. jobul de retentie e implicit PORNIT ──────────────────────────────────
def test_jobul_de_retentie_e_implicit_pornit():
    """Spre deosebire de restul seriei: un bazin care creste nemarginit e o problema
    GARANTATA, deci stergerea e comportamentul sigur, nu cel riscant."""
    sursa = Path("app/main.py").read_text(encoding="utf-8")

    assert 'os.getenv("FB_BAZIN_RETENTIE") or "1"' in sursa, "implicitul e PORNIT"
    assert 'id="fb_bazin_retentie"' in sursa
    assert "FB_BAZIN_RETENTIE_ZILE" in sursa
    assert "ultima_vedere_at" in sursa or "ultima_vedere" in sursa


# ── 18-21. FBS-5b: cablarea `keyword_id` in cei trei scanneri ────────────────
def _kw_radar(**kw):
    from types import SimpleNamespace
    baza = dict(id=101, name="canapea", platform="facebook", max_price=1000.0,
                min_price=None, judet=None, oras=None, category=None,
                exclude_words=None, condition=None)
    baza.update(kw)
    return SimpleNamespace(**baza)


def test_radar_scanner_paseaza_keyword_id(monkeypatch):
    """Valoarea pasata, nu doar prezenta parametrului."""
    from app.utils import radar_scanner as rs
    primite = {}
    monkeypatch.setattr(rs, "search_facebook",
                        lambda **k: (primite.update(k), [])[1])
    settings = type("S", (), {"facebook_session_path": None})()

    rs._run_scraper("facebook", _kw_radar(id=101), settings, [], page=1, db=None)

    assert primite.get("keyword_id") == 101


def test_auto_scanner_paseaza_keyword_id(monkeypatch):
    from types import SimpleNamespace
    from app.services import auto_listings_scanner as als
    primite = {}
    monkeypatch.setattr("app.scrapers.auto.listings.facebook_auto_scraper.search_facebook_auto",
                        lambda **k: (primite.update(k), [])[1])
    monkeypatch.setattr("app.services.facebook_session.resolve_facebook_session_path",
                        lambda db, uid: "sesiune.json")
    kw = SimpleNamespace(id=202, platform="facebook_auto", user_id=1, make="BMW",
                         model="Seria 3", query=None, year_from=None, year_to=None,
                         km_max=None, price_max=None, fuel_type=None,
                         transmission=None, body_type=None, category=None,
                         tech_filters=None)

    als._call_scraper(kw, page=1, db=None)

    assert primite.get("keyword_id") == 202


def test_real_estate_scanner_paseaza_keyword_id(monkeypatch):
    """Se foloseste MODELUL real, nu un namespace construit de mana: `_call_scraper`
    citeste vreo douazeci de atribute, iar o dublura incompleta pica pe primul care
    lipseste — nu pe ce vrem sa masuram."""
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword
    from app.services import real_estate_scanner as res
    primite = {}
    monkeypatch.setattr(
        "app.scrapers.real_estate.facebook_real_estate.search_facebook_real_estate",
        lambda **k: (primite.update(k), [])[1])
    monkeypatch.setattr("app.services.facebook_session.resolve_facebook_session_path",
                        lambda db, uid: "sesiune.json")
    kw = RealEstateMonitorKeyword(id=303, user_id=1, query="garsoniera",
                                  platform="facebook_marketplace")

    res._call_scraper(kw, None, db=None)

    assert primite.get("keyword_id") == 303


def test_cablarea_nu_schimba_nimic_fara_fb_mod(monkeypatch):
    """`keyword_id` e inert cat timp `FB_MOD` nu e `bazin`: dispecerul nici nu-l
    citeste pe calea de sesiune."""
    monkeypatch.delenv("FB_MOD", raising=False)
    chemat = {"n": 0}
    monkeypatch.setattr(rad, "_search_sesiune",
                        lambda *a, **k: chemat.__setitem__("n", 1) or [])

    rad.search_facebook(keyword="canapea", max_price=0, keyword_id=101)

    assert chemat["n"] == 1
