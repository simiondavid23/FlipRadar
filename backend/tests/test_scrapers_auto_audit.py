"""SCRAPE-AUDIT (auto) — fix-urile auditului modulului auto.

Bug-urile reparate: routerul de cautare pasa dict-ul de filtre pe pozitia `model`
la 3 din 6 platforme (crash inghitit de gather -> 0 rezultate tacut); modelul era
ignorat complet pe autovit; fuel_type se pierdea pe autoscout24 (alias lipsa, desi
confirmat in auto_categories); parse_money facea "€ 12.500" -> 12.5 pe loturi;
extract_km lua PRIMUL "N km" din text ("la 20 km de Bucuresti" -> rulaj 20);
firstRegistrationDate era salvat drept data postarii; km_max/year_to fara plasa
locala pe platformele fara parametri server-side.
"""
import asyncio
import inspect

import pytest

from app.scrapers.auto.listings import _common as lc
from app.scrapers.auto.lots import _common as lot
from app.scrapers.auto.listings import autovit_scraper as av
from app.scrapers.auto.listings import autoscout24_scraper as as24


# ── parse_money (loturi): formate europene si americane ─────────────────────────

def test_parse_money_format_european():
    assert lot.parse_money("€ 12.500") == 12500.0
    assert lot.parse_money("1.234.567") == 1234567.0


def test_parse_money_format_american_neschimbat():
    assert lot.parse_money("$1,234.56") == 1234.56
    assert lot.parse_money("$1,234") == 1234.0


def test_parse_money_zecimal_simplu():
    assert lot.parse_money("12.5") == 12.5
    assert lot.parse_money(1500) == 1500.0


# ── extract_km: cel mai mare candidat plauzibil ──────────────────────────────────

def test_extract_km_ignora_distanta_pana_la_oras():
    assert lc.extract_km("la 20 km de Bucuresti, 150.000 km") == 150000


def test_extract_km_formate_normale_neschimbate():
    assert lc.extract_km("85 000 km") == 85000
    assert lc.extract_km("123.456 km rulaj real") == 123456


def test_extract_km_garda_de_garbage_ramane():
    assert lc.extract_km("11202035000 km") is None


# ── autovit: modelul din filters + filtrarea locala pe titlu ─────────────────────

def _fake_autovit_html(titles):
    cards = "".join(
        f'<article data-id="id{i}"><a href="/anunt/x-{i}"><h2>{t}</h2></a></article>'
        for i, t in enumerate(titles))
    return f"<html><body>{cards}</body></html>"


class _FakeResp:
    def __init__(self, text):
        self.status_code = 200
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


def _run_autovit(monkeypatch, titles, model="", filters=None):
    html = _fake_autovit_html(titles)
    monkeypatch.setattr(av, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(av.log_manager, "emit", lambda *a, **k: None)
    return asyncio.run(av.search_autovit(make="bmw", model=model,
                                         filters=filters or {}))


def test_autovit_modelul_din_filters_filtreaza_titlurile(monkeypatch):
    out = _run_autovit(monkeypatch,
                       ["BMW Seria 3 320d", "BMW X5 xDrive", "BMW Seria 3 Touring"],
                       filters={"model": "Seria 3"})
    assert len(out) == 2
    assert all("seria 3" in (r.get("titlu") or "").lower() for r in out)


def test_autovit_model_cu_diacritice_straine(monkeypatch):
    out = _run_autovit(monkeypatch, ["Skoda Octavia 2.0", "BMW X5"],
                       filters={"model": "Škoda"})
    assert len(out) == 1 and "Skoda" in out[0]["titlu"]


def test_autovit_fara_model_pastreaza_tot(monkeypatch):
    out = _run_autovit(monkeypatch, ["BMW Seria 3", "BMW X5"])
    assert len(out) == 2


# ── autoscout24: fuel_type ajunge in parametri (prin CALL SITE-ul real) ──────────

class _CapturingSession:
    """Sesiune falsa care captureaza params trimisi de scraper la GET."""
    captured: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        _CapturingSession.captured = dict(kw.get("params") or {})
        return _FakeResp("<html><body></body></html>")


def test_autoscout24_fuel_ajunge_in_parametri(monkeypatch):
    # Prin search_autoscout24 REAL, nu prin apel direct la apply_confirmed_filters
    # cu aliasuri proprii — altfel testul nu vede call site-ul din scraper.
    _CapturingSession.captured = {}
    monkeypatch.setattr(as24, "AsyncSession", lambda: _CapturingSession())
    asyncio.run(as24.search_autoscout24(make="bmw", filters={"fuel": "diesel"}))
    assert _CapturingSession.captured.get("fuel") == "D"


# ── router: semnaturile primesc modelul si filtrele pe pozitiile corecte ─────────

def test_router_builders_respecta_semnaturile():
    # Garda structurala: apelurile din router trebuie sa lege `filters` pe
    # parametrul `filters`, nu pe `model` (bug-ul original crapa cu orice filtru).
    import app.routers.auto as ar
    src = inspect.getsource(ar)
    assert "search_mobile_de(\n            f.get(\"make_id\", \"\") or make, f.get(\"model\", \"\"), q, f)" in src
    assert 'search_autoscout24(make, f.get("model", ""), f)' in src
    assert "search_kleinanzeigen_auto(\n            q, make, f.get(\"model\", \"\"), f)" in src


# ── detail: firstRegistrationDate nu mai e data postarii ─────────────────────────

def test_detail_nu_mai_mapeaza_prima_inmatriculare_pe_listed_at():
    from app.scrapers.auto.listings import detail as dt
    src = inspect.getsource(dt)
    assert 'for k in ("firstRegistrationDate", "firstRegistration"):' not in src


# ── scanner: plasa locala km_max / year_from / year_to ───────────────────────────

def test_scanner_plasa_km_si_an(monkeypatch):
    # Verificam direct predicatul inline: un listing cu km peste kw.km_max sau an
    # peste kw.year_to nu ajunge la _save_listing (fail-open pe valori lipsa).
    from app.services import auto_listings_scanner as als
    src = inspect.getsource(als)
    assert 'if kw.km_max and r.get("km") and int(r["km"]) > int(kw.km_max):' in src
    assert 'if kw.year_to and r.get("year") and int(r["year"]) > int(kw.year_to):' in src
    # FB-AUDIT A4 — year_from pleaca server-side ca "year_min", dar facebook_auto
    # nu trimite la sursa decat pretul; fara plasa locala keyword-ul "2015+" primea
    # masini din 2003.
    assert 'if kw.year_from and r.get("year") and int(r["year"]) < int(kw.year_from):' in src


def _seed_auto_kw(db, **campuri):
    """User + un keyword facebook_auto (platforma FARA filtre server-side de an).
    resale_price ramane None ca _resale_price_ron sa nu ceara cursul BNR (retea)."""
    import uuid

    from app.models.auto_keyword import AutoKeyword
    from app.models.user import User

    email = f"a4_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    kw = AutoKeyword(user_id=u.id, name="kw a4", platform="facebook_auto", is_active=True,
                     active_hours_start=None, active_hours_end=None, **campuri)
    db.add(kw)
    db.commit()
    return u, kw


def _prin_plasa(monkeypatch, carduri: list[dict], **campuri) -> list[str]:
    """Ruleaza scanul pe carduri false si intoarce external_id-urile care au TRECUT
    de plasa locala (adica au ajuns la _save_listing). Fara retea, fara notificari:
    _call_scraper e stubuit, iar _save_listing doar inregistreaza (False = nu e nou)."""
    from app.database import SessionLocal
    from app.services import auto_listings_scanner as als

    ajunse: list[str] = []
    monkeypatch.setattr(als, "_call_scraper",
                        lambda kw, *a, **k: [dict(c) for c in carduri] if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(als, "_save_listing",
                        lambda db, kw, raw, resale: (ajunse.append(raw["external_id"]), False)[1])
    monkeypatch.setattr(als.log_manager, "emit", lambda *a, **k: None)

    db = SessionLocal()
    try:
        _seed_auto_kw(db, **campuri)
        als.run_auto_scan(db, platform="facebook_auto")
    finally:
        db.close()
    return ajunse


def _card(ext: str, year=None, km=None) -> dict:
    c = {"external_id": ext, "titlu": f"masina {ext}", "pret": 5000}
    if year is not None:
        c["year"] = year
    if km is not None:
        c["km"] = km
    return c


def test_plasa_respinge_masina_sub_year_from(monkeypatch):
    # FB-AUDIT A4: keyword "2015+", card din 2003 -> respins LOCAL (facebook_auto
    # nu are parametru server-side de an minim).
    ajunse = _prin_plasa(monkeypatch, [_card("vechi", year=2003)], year_from=2015)
    assert ajunse == []


def test_plasa_lasa_masina_de_la_year_from_in_sus(monkeypatch):
    ajunse = _prin_plasa(monkeypatch,
                         [_card("exact", year=2015), _card("nou", year=2018)],
                         year_from=2015)
    assert ajunse == ["exact", "nou"]


def test_plasa_fail_open_pe_an_lipsa(monkeypatch):
    # Anul lipseste de pe card -> nu putem verifica, deci NU respingem (ca la year_to/km).
    ajunse = _prin_plasa(monkeypatch, [_card("fara_an")], year_from=2015)
    assert ajunse == ["fara_an"]


def test_plasa_year_to_ramane_neatins(monkeypatch):
    # Control de regresie: capatul superior filtreaza in continuare.
    ajunse = _prin_plasa(monkeypatch,
                         [_card("prea_nou", year=2020), _card("bun", year=2016)],
                         year_from=2015, year_to=2018)
    assert ajunse == ["bun"]


# ── scanner: fara pret nu se intra in feed (paritate SCRAPE-1a / FBM-1a) ─────────

def _scan_real(monkeypatch, db, carduri: list[dict]) -> None:
    """Scan cu _save_listing REAL (spre deosebire de _prin_plasa): doar scraperul
    e stubuit, deci se vede exact ce ajunge rand in AutoFeedListing."""
    from app.services import auto_listings_scanner as als

    monkeypatch.setattr(als, "_call_scraper",
                        lambda kw, *a, **k: [dict(c) for c in carduri] if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(als.log_manager, "emit", lambda *a, **k: None)
    als.run_auto_scan(db, platform="facebook_auto")


def _randuri(db, user_id: int) -> list:
    from app.models.auto_feed_listing import AutoFeedListing
    return (db.query(AutoFeedListing)
            .filter(AutoFeedListing.user_id == user_id)
            .order_by(AutoFeedListing.id).all())


def test_anunt_fara_pret_nu_intra_in_feed(monkeypatch):
    # Card fara pret parsat -> niciun rand (ar fi ramas gunoi vizual: pret gol,
    # grad None, scor 0). Notificari false nu existau oricum (garda din scorer).
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u, _ = _seed_auto_kw(db)
        _scan_real(monkeypatch, db, [{"external_id": "fara_pret", "titlu": "masina"}])
        assert _randuri(db, u.id) == []
    finally:
        db.close()


def test_anunt_cu_pret_valid_intra_in_feed(monkeypatch):
    # Control pozitiv: garda nu inchide calea normala.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u, _ = _seed_auto_kw(db)
        _scan_real(monkeypatch, db,
                   [{"external_id": "cu_pret", "titlu": "masina", "price": 12500}])
        randuri = _randuri(db, u.id)
        assert len(randuri) == 1
        assert randuri[0].external_id == "cu_pret" and float(randuri[0].price) == 12500.0
    finally:
        db.close()


def test_pret_zero_sau_neparsabil_e_sarit(monkeypatch):
    # 0 si "N/A" nu sunt preturi. Bonus: "N/A" arunca ValueError din float() daca
    # parsarea nu e aparata -> keyword-ul intreg se oprea, nu doar cardul.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u, _ = _seed_auto_kw(db)
        _scan_real(monkeypatch, db, [
            {"external_id": "zero", "titlu": "masina", "price": 0},
            {"external_id": "text", "titlu": "masina", "price": "N/A"},
            {"external_id": "bun", "titlu": "masina", "price": 7000},
        ])
        assert [r.external_id for r in _randuri(db, u.id)] == ["bun"]
    finally:
        db.close()


# ── facebook_auto: post-filtru de model pe titlu (A5) ───────────────────────────

def _fb_obj(oid: str, title: str, cat=None, amount="10000.00") -> dict:
    """Obiect de listare Marketplace, forma minima citita de search_facebook_auto."""
    from app.scrapers.auto.listings import facebook_auto_scraper as fa
    return {
        "id": oid,
        "marketplace_listing_title": title,
        "marketplace_listing_category_id": cat if cat is not None else fa._vehicles_category_id(),
        "listing_price": {"amount": amount, "formatted_amount": f"RON{amount}"},
    }


def _fb_auto(monkeypatch, obiecte: list, filters=None, logs=None) -> list:
    """Ruleaza search_facebook_auto REAL (deci si post-filtrele), cu sesiunea, fetch-ul
    si iterarea JSON stubuite — piesele importate din radar/facebook_scraper se
    monkeypatch-uiesc pe modulul care le-a importat. `logs` (lista) colecteaza
    (nivel, mesaj) din log_manager.emit."""
    from app.scrapers.auto.listings import facebook_auto_scraper as fa

    monkeypatch.setattr(fa, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fa, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fa, "_fetch",
                        lambda url, cookies: ("<html></html>", "https://www.facebook.com/marketplace/search/"))
    monkeypatch.setattr(fa, "_iter_listing_objects", lambda html: list(obiecte))
    monkeypatch.setattr(fa.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)) if logs is not None else None)
    return fa.search_facebook_auto(query="bmw seria 3", filters=filters or {},
                                   session_path="sesiune.json")


def test_fb_auto_modelul_din_titlu_trece_si_restul_e_exclus(monkeypatch):
    # TINTA A5: cautarea FB e fuzzy — fara post-filtru, X5-ul intra in feed.
    out = _fb_auto(monkeypatch,
                   [_fb_obj("1", "BMW Seria 3 320d 2016"), _fb_obj("2", "BMW X5 xDrive 2015")],
                   filters={"model": "Seria 3"})
    assert [r["title"] for r in out] == ["BMW Seria 3 320d 2016"]


def test_fb_auto_diacritice_in_ambele_sensuri(monkeypatch):
    out = _fb_auto(monkeypatch, [_fb_obj("1", "Skoda Octavia 2.0 TDI")],
                   filters={"model": "Škoda Octavia"})
    assert len(out) == 1
    out = _fb_auto(monkeypatch, [_fb_obj("2", "Škoda Octavia 2.0 TDI")],
                   filters={"model": "Skoda Octavia"})
    assert len(out) == 1


def test_fb_auto_fara_model_nu_filtreaza_nimic(monkeypatch):
    # Fail-open: fara model in filters (sau cu model gol) trec toate anunturile.
    obiecte = [_fb_obj("1", "BMW Seria 3 320d"), _fb_obj("2", "Dacia Logan")]
    assert len(_fb_auto(monkeypatch, obiecte)) == 2
    assert len(_fb_auto(monkeypatch, obiecte, filters={"model": "   "})) == 2


# ── facebook_auto: filtru de marca (dur) + supapa pe model (A5.1) ───────────────

def test_fb_auto_marca_exclude_alte_marci(monkeypatch):
    # Zgomotul documentat in scraper (Opel Mokka, camioane MAN) pica pe marca.
    out = _fb_auto(monkeypatch,
                   [_fb_obj("1", "BMW 320d Touring 2016"), _fb_obj("2", "Opel Mokka 1.4")],
                   filters={"make": "BMW"})
    assert [r["title"] for r in out] == ["BMW 320d Touring 2016"]


def test_fb_auto_fara_marca_nu_filtreaza_nimic(monkeypatch):
    obiecte = [_fb_obj("1", "BMW 320d"), _fb_obj("2", "Opel Mokka")]
    assert len(_fb_auto(monkeypatch, obiecte)) == 2
    assert len(_fb_auto(monkeypatch, obiecte, filters={"make": "  "})) == 2


def test_fb_auto_marca_cu_diacritice_in_ambele_sensuri(monkeypatch):
    out = _fb_auto(monkeypatch, [_fb_obj("1", "Skoda Octavia 2.0 TDI")],
                   filters={"make": "Škoda"})
    assert len(out) == 1
    out = _fb_auto(monkeypatch, [_fb_obj("2", "Škoda Octavia 2.0 TDI")],
                   filters={"make": "Skoda"})
    assert len(out) == 1


def test_supapa_modelul_fara_potrivire_pastreaza_anunturile_marcii(monkeypatch):
    """TINTA A5.1: pe Facebook un "Seria 3" real se numeste "BMW 320d Touring".

    Filtrul strict de model ar fi golit feed-ul, TACUT. Supapa pastreaza anunturile
    marcii (Opel-ul tot cade, pe marca) si semnaleaza cu WARN.
    """
    logs = []
    out = _fb_auto(monkeypatch,
                   [_fb_obj("1", "BMW 320d Touring 2016"), _fb_obj("2", "BMW 318i 2014"),
                    _fb_obj("3", "Opel Astra 1.6")],
                   filters={"make": "BMW", "model": "Seria 3"}, logs=logs)
    assert [r["title"] for r in out] == ["BMW 320d Touring 2016", "BMW 318i 2014"]
    warns = [m for lvl, m in logs if lvl == "WARN"]
    assert len(warns) == 1 and "Seria 3" in warns[0] and "BMW" in warns[0]


def test_supapa_nu_se_declanseaza_cand_modelul_potriveste(monkeypatch):
    # Cand modelul chiar apare intr-un titlu, filtrul se aplica normal.
    logs = []
    out = _fb_auto(monkeypatch,
                   [_fb_obj("1", "BMW Seria 3 320d"), _fb_obj("2", "BMW X5 xDrive")],
                   filters={"make": "BMW", "model": "Seria 3"}, logs=logs)
    assert [r["title"] for r in out] == ["BMW Seria 3 320d"]
    assert [m for lvl, m in logs if lvl == "WARN"] == []


def test_supapa_nu_inventeaza_rezultate_pe_lista_goala(monkeypatch):
    # Lista era deja goala dupa filtrul de marca -> nu e nimic de salvat.
    logs = []
    out = _fb_auto(monkeypatch, [_fb_obj("1", "Opel Astra 1.6")],
                   filters={"make": "BMW", "model": "Seria 3"}, logs=logs)
    assert out == []
    assert [m for lvl, m in logs if lvl == "WARN"] == []


def test_scanner_trimite_marca_in_filters_la_facebook_auto(monkeypatch):
    # Cablarea marcii, ca la model (A5): fara ea, filtrul de marca ar fi inert.
    from types import SimpleNamespace

    from app.services import auto_listings_scanner as als

    primite = {}
    monkeypatch.setattr("app.scrapers.auto.listings.facebook_auto_scraper.search_facebook_auto",
                        lambda **k: (primite.update(k), [])[1])
    monkeypatch.setattr("app.services.facebook_session.resolve_facebook_session_path",
                        lambda db, uid: "sesiune.json")
    kw = SimpleNamespace(platform="facebook_auto", user_id=1, make="BMW", model="Seria 3",
                         query=None, year_from=None, year_to=None, km_max=None,
                         price_max=None, fuel_type=None, transmission=None,
                         body_type=None, category=None, tech_filters=None)
    als._call_scraper(kw, page=1, db=None)
    assert primite["filters"]["make"] == "BMW"


def test_scanner_trimite_modelul_in_filters_la_facebook_auto(monkeypatch):
    # Cablarea: post-filtrul citeste filters["model"], dar _call_scraper construia
    # filters FARA model (doar autovit primea `{**filters, "model": ...}`), deci
    # filtrul ar fi ramas inert in productie. Aici verificam ca ajunge.
    from types import SimpleNamespace

    from app.services import auto_listings_scanner as als

    primite = {}
    monkeypatch.setattr("app.scrapers.auto.listings.facebook_auto_scraper.search_facebook_auto",
                        lambda **k: (primite.update(k), [])[1])
    monkeypatch.setattr("app.services.facebook_session.resolve_facebook_session_path",
                        lambda db, uid: "sesiune.json")
    kw = SimpleNamespace(platform="facebook_auto", user_id=1, make="BMW", model="Seria 3",
                         query=None, year_from=None, year_to=None, km_max=None,
                         price_max=None, fuel_type=None, transmission=None,
                         body_type=None, category=None, tech_filters=None)
    als._call_scraper(kw, page=1, db=None)
    assert primite["filters"]["model"] == "Seria 3"
    assert primite["query"] == "BMW Seria 3"     # modelul ramane SI in query


def test_fb_auto_filtrul_de_categorie_ramane(monkeypatch):
    # Control de regresie: jantele/piesele (alta categorie) raman excluse, iar
    # post-filtrul de model nu le "salveaza" chiar daca titlul contine modelul.
    out = _fb_auto(monkeypatch,
                   [_fb_obj("1", "BMW Seria 3 320d"),
                    _fb_obj("2", "Jante BMW Seria 3", cat="999999")],
                   filters={"model": "Seria 3"})
    assert [r["external_id"] for r in out] == ["fb_1"]


def test_reaparitia_fara_pret_nu_pierde_pretul_vechi(monkeypatch):
    # Calea de UPDATE ramane neatinsa: randul existent isi pastreaza pretul bun si
    # primeste doar bump de last_checked_at (dovada de viata), nu un pret zero-at.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u, _ = _seed_auto_kw(db)
        _scan_real(monkeypatch, db,
                   [{"external_id": "acelasi", "titlu": "masina", "price": 9000}])
        _scan_real(monkeypatch, db, [{"external_id": "acelasi", "titlu": "masina"}])
        randuri = _randuri(db, u.id)
        assert len(randuri) == 1
        assert float(randuri[0].price) == 9000.0
        assert randuri[0].last_checked_at is not None
    finally:
        db.close()
