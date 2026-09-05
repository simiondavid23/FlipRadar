"""CUR-2 — Auto si Imobiliare convertesc prin catalogul BNR, nu „EUR sau 1:1".

DE CE EXISTA: CUR-1 a adus catalogul (38 de monede) DOAR in Radar. In celelalte doua
module orice cod diferit de EUR era tratat tacut ca si cum ar fi fost deja RON (Auto) sau
deja EUR (Imobiliare):

  * Auto — `pret * (get_eur_ron() if cur == "EUR" else 1.0)` in trei locuri: pragul de
    revanzare al keyword-ului, scorarea initiala si re-scorarea de la reaparitie (SEEN-3).
    Un anunt de 15 000 GBP se scora ca 15 000 RON: marja uriasa, grad A fals, alerta.
  * Imobiliare — `price_eur = price / eur_ron if currency == "RON" else price`, deci un
    anunt in GBP era scorat si filtrat ca si cum ar fi fost in EUR.

POLITICA PE NECUNOSCUT, diferita de Radar si deliberat: Radar e fail-open (D2, „prefer sa
nu pierd un deal") fiindca acolo un anunt fara scor nu apare in feed. Pe Auto, gradul
`None` e o stare de prima clasa — anuntul ramane vizibil, dar fara marja falsa si fara
alerta. Pe Imobiliare scorul cade pe neutrul existent (50, "C"), iar filtrul de pret
ramane TOLERANT cand nu poate compara (ca azi pe `eur_ron=None`): un filtru n-are voie sa
respinga pe ceva ce nu stie sa masoare.

Fara retea: `catalog_ron` si cursurile sunt pinuite in fiecare test.
"""
import uuid

import pytest

from app.services import auto_listings_scanner as als


_CATALOG = {"RON": 1.0, "EUR": 5.0, "USD": 4.5, "GBP": 6.0, "MDL": 0.26}


# ══════════════════════════════ AUTO ══════════════════════════════
def _seed(db, resale_price=None, resale_currency="RON", notify_discord=True):
    from app.models.auto_keyword import AutoKeyword
    from app.models.radar_settings import RadarSettings
    from app.models.user import User

    email = f"cur2_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    kw = AutoKeyword(user_id=u.id, name="kw cur2", platform="facebook_auto",
                     is_active=True, active_hours_start=None, active_hours_end=None,
                     resale_price=resale_price, resale_price_currency=resale_currency,
                     notify_discord=notify_discord, notify_email=False)
    db.add(kw)
    db.add(RadarSettings(user_id=u.id))
    db.commit()
    return u, kw


def _card(ext: str, pret: float, moneda="EUR") -> dict:
    return {"external_id": ext, "titlu": f"BMW {ext}", "pret": pret,
            "currency": moneda, "url": f"https://autovit.ro/{ext}",
            "an": 2018, "km": 100000}


def _scan(monkeypatch, db, carduri, notif=None, warns=None, catalog=None):
    """Un ciclu complet prin `run_auto_scan`, cu catalogul si cursul pinuite."""
    from app.services import currency_service
    import app.services.discord_service as ds

    monkeypatch.setattr(als, "_call_scraper",
                        lambda kw, *a, **k: [dict(c) for c in carduri]
                        if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(als, "get_eur_ron", lambda: 5.0)
    monkeypatch.setattr(currency_service, "catalog_ron",
                        lambda: dict(_CATALOG if catalog is None else catalog))
    monkeypatch.setattr(ds, "send_auto_notification",
                        lambda *a, **k: (notif.append(a) if notif is not None else None) or 1)

    def _emit(modul, nivel, mesaj):
        if warns is not None and nivel == "WARN":
            warns.append(mesaj)
    monkeypatch.setattr(als.log_manager, "emit", _emit)
    als.run_auto_scan(db, platform="facebook_auto")


def _rand(db, ext: str):
    from app.models.auto_feed_listing import AutoFeedListing
    db.expire_all()
    return (db.query(AutoFeedListing)
            .filter(AutoFeedListing.external_id == ext).first())


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ── 1. anunt intr-o moneda din catalog ─────────────────────────────────────────
def test_auto_anunt_in_gbp_se_scoreaza_convertit(monkeypatch, db):
    """10 000 GBP × 6.0 = 60 000 RON fata de 100 000 revanzare -> marja 40% -> grad A.
    Inainte de CUR-2, 10 000 GBP se citea ca 10 000 RON -> marja 90%, tot grad A dar pe
    o cifra inventata; aici verificam MARJA, care e discriminanta."""
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, db, [_card(ext, 10000.0, moneda="GBP")])

    rand = _rand(db, ext)
    assert rand is not None
    assert rand.score == 40, "40% marja pe 60 000 RON; fara catalog ar fi fost 90%"
    assert float(rand.margin_value) == 40000.0


# ── 2. cod din afara catalogului: fara grad, un singur WARN ────────────────────
def test_auto_moneda_necunoscuta_da_rand_fara_grad(monkeypatch, db):
    _seed(db, resale_price=100000.0)
    e1, e2 = f"a{uuid.uuid4().hex[:8]}", f"a{uuid.uuid4().hex[:8]}"
    notif, warns = [], []

    _scan(monkeypatch, db, [_card(e1, 10000.0, moneda="XXX"),
                            _card(e2, 12000.0, moneda="XXX")], notif, warns)

    for ext in (e1, e2):
        rand = _rand(db, ext)
        assert rand is not None, "anuntul RAMANE in feed, vizibil"
        assert rand.grade is None and rand.score is None
        assert rand.margin_value is None
    assert notif == [], "fara grad nu pleaca nicio alerta"
    xxx = [w for w in warns if "XXX" in w]
    assert len(xxx) == 1, f"un singur WARN per moneda per scan, nu unul per anunt: {warns}"


# ── 3. pragul de revanzare intr-o moneda din catalog ───────────────────────────
def test_auto_resale_in_gbp_se_converteste(monkeypatch, db):
    """20 000 GBP × 6.0 = 120 000 RON prag; anunt la 100 000 RON -> marja 16.7%."""
    _seed(db, resale_price=20000.0, resale_currency="GBP")
    ext = f"a{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, db, [_card(ext, 100000.0, moneda="RON")])

    rand = _rand(db, ext)
    assert rand.score == 17, "(120000-100000)/120000 = 16.7%"
    assert float(rand.margin_value) == 20000.0


# ── 4. prag intr-o moneda necunoscuta -> keyword fara grade ────────────────────
def test_auto_resale_in_moneda_necunoscuta(monkeypatch, db):
    _seed(db, resale_price=20000.0, resale_currency="XXX")
    ext = f"a{uuid.uuid4().hex[:10]}"
    warns = []

    _scan(monkeypatch, db, [_card(ext, 100000.0, moneda="RON")], warns=warns)

    rand = _rand(db, ext)
    assert rand is not None
    assert rand.margin_value is None, "niciun prag utilizabil -> nicio marja calculata"
    assert any("XXX" in w and "resale_price" in w for w in warns), warns
    # `grade` ramane default-ul modelului ("C"), ca la ORICE keyword fara resale_price —
    # comportament dinainte de CUR-2, neschimbat aici. Ce conteaza e ca marja lipseste,
    # deci nu se pretinde niciun deal.
    assert rand.grade == "C"


# ── 5. re-scorarea de la reaparitie (SEEN-3) trece tot prin catalog ────────────
def test_auto_reaparitia_in_gbp_se_rescoreaza_convertit(monkeypatch, db):
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, db, [_card(ext, 15000.0, moneda="GBP")])   # 90 000 RON -> marja 10%
    assert _rand(db, ext).score == 10

    _scan(monkeypatch, db, [_card(ext, 10000.0, moneda="GBP")])   # 60 000 RON -> marja 40%

    rand = _rand(db, ext)
    assert float(rand.price) == 10000.0
    assert rand.score == 40, "re-scorat pe 60 000 RON, nu pe 10 000"
    assert float(rand.pret_anterior) == 15000.0


# ── 6. fara catalog: contractul vechi pe EUR, nimic pe GBP ─────────────────────
def test_auto_fara_catalog_eur_merge_gbp_nu(monkeypatch, db):
    _seed(db, resale_price=100000.0)
    e_eur, e_gbp = f"a{uuid.uuid4().hex[:8]}", f"a{uuid.uuid4().hex[:8]}"

    _scan(monkeypatch, db, [_card(e_eur, 10000.0, moneda="EUR"),
                            _card(e_gbp, 10000.0, moneda="GBP")], catalog={})

    assert _rand(db, e_eur).score == 50, "10 000 EUR × 5.0 = 50 000 -> marja 50%"
    assert _rand(db, e_gbp).grade is None, "fara catalog, GBP nu se poate converti"


# ══════════════════════════════ IMOBILIARE ══════════════════════════════
class _KwRE:
    """Forma minima de RealEstateKeyword citita de `_matches_re_keyword`.

    `__getattr__` intoarce None pentru orice camp necerut explicit: filtrul citeste multe
    criterii si e TOLERANT pe fiecare None, deci un stub cu lista fixa s-ar rupe la
    fiecare criteriu nou adaugat in filtru — exact ce nu vrem intr-un test de moneda.
    """
    def __init__(self, price_min=None, price_max=None, price_currency="EUR"):
        self.price_min = price_min
        self.price_max = price_max
        self.price_currency = price_currency

    def __getattr__(self, nume):
        return None


def _match(pret, moneda, kw, cursuri=None):
    from app.services.real_estate_scanner import _matches_re_keyword
    return _matches_re_keyword({"price": pret, "currency": moneda}, kw,
                               eur_ron=5.0, cursuri=cursuri)


# ── 7. RON vs EUR: comportamentul de azi, pastrat ──────────────────────────────
def test_re_filtru_ron_vs_eur_neschimbat():
    kw = _KwRE(price_max=1000, price_currency="EUR")
    assert _match(6000, "RON", kw) is False, "6000 RON = 1200 EUR > 1000"
    assert _match(4000, "RON", kw) is True                # 800 EUR


# ── 8. GBP: convertit, nu presupus EUR ─────────────────────────────────────────
def test_re_filtru_gbp_se_converteste(monkeypatch):
    """900 GBP × 6.0 = 5400 RON = 1080 EUR > plafonul de 1000. Inainte de CUR-2 ramura
    `p_eur = p` il citea ca 900 EUR si il lasa sa treaca."""
    kw = _KwRE(price_max=1000, price_currency="EUR")
    assert _match(900, "GBP", kw, _CATALOG) is False
    assert _match(800, "GBP", kw, _CATALOG) is True       # 4800 RON = 960 EUR


# ── 9. cod necunoscut: tolerant + WARN ─────────────────────────────────────────
def test_re_filtru_moneda_necunoscuta_e_tolerant(monkeypatch):
    from app.services import real_estate_scanner as res

    warns = []
    monkeypatch.setattr(res.log_manager, "emit",
                        lambda m, n, msg: warns.append(msg) if n == "WARN" else None)
    res._monede_necunoscute_warned.clear()

    kw = _KwRE(price_max=1000, price_currency="EUR")
    assert _match(900, "XXX", kw, _CATALOG) is True, "filtrul nu respinge ce nu poate masura"
    assert _match(900, "XXX", kw, _CATALOG) is True
    assert len(warns) == 1, f"un singur WARN per pereche de monede per scan: {warns}"


# ── 10. scorerul ───────────────────────────────────────────────────────────────
def test_re_scorer_converteste_din_catalog(monkeypatch):
    from app.services.real_estate import scorer

    monkeypatch.setattr("app.services.bnr_exchange.get_eur_ron", lambda: 5.0)
    # 100 GBP × 6.0 = 600 RON = 120 EUR pe 60 mp -> 2 EUR/mp fata de o medie de 10 -> A.
    scor_gbp, grad_gbp = scorer.compute_re_score(
        100, "GBP", 60, 2, "zona", "Cluj", zone_avg_ppm=10.0,
        tip_anunt="inchiriere", cursuri=_CATALOG)
    scor_eur, grad_eur = scorer.compute_re_score(
        120, "EUR", 60, 2, "zona", "Cluj", zone_avg_ppm=10.0,
        tip_anunt="inchiriere", cursuri=_CATALOG)
    assert (scor_gbp, grad_gbp) == (scor_eur, grad_eur), (
        "100 GBP si 120 EUR sunt aceeasi suma — trebuie sa dea acelasi scor")


def test_re_scorer_moneda_necunoscuta_da_neutru(monkeypatch):
    from app.services.real_estate import scorer

    monkeypatch.setattr("app.services.bnr_exchange.get_eur_ron", lambda: 5.0)
    assert scorer.compute_re_score(100, "XXX", 60, 2, "zona", "Cluj",
                                   zone_avg_ppm=10.0, tip_anunt="inchiriere",
                                   cursuri=_CATALOG) == (50, "C")


# ── 11. WARN-ul se goleste intre scanuri (Auto) ────────────────────────────────
def test_auto_warnul_reapare_la_scanul_urmator(monkeypatch, db):
    """Contorul e stare de MODUL: fara golire la inceputul scanului, a doua rulare ar
    ramane tacuta si o problema persistenta ar disparea din jurnal dupa primul ciclu."""
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"

    w1, w2 = [], []
    _scan(monkeypatch, db, [_card(ext, 10000.0, moneda="XXX")], warns=w1)
    # Pret DIFERIT: la pret egal, ramura `existing` iese inainte de conversie (garda
    # veche „pret neschimbat -> doar bump"), deci n-ar avea ce sa avertizeze.
    _scan(monkeypatch, db, [_card(ext, 9000.0, moneda="XXX")], warns=w2)

    assert [w for w in w1 if "XXX" in w], w1
    assert [w for w in w2 if "XXX" in w], "WARN-ul trebuie sa reapara la scanul urmator"
