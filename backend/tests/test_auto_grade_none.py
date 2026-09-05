"""AUTO-GRADE — fara pret de revanzare nu exista grad; anuntul merge tot pe `auto_all`.

DE CE EXISTA: `AutoFeedListing` avea `score = Column(Integer, default=50)` si
`grade = Column(String(5), default="C")`. Un keyword fara `resale_price` nu poate calcula
marja, deci anunturile lui primeau la INSERT „C"/50 — o valoare de UMPLERE care arata ca
un grad calculat. Trei consecinte: in feed aparea ca „C", nedistins de un C real;
`_notify` alerta pe orice grad A-D, deci fiecare anunt al unui asemenea keyword pleca pe
Discord cu grad fals; iar statisticile `by_grade` numarau gunoiul.

Deciziile aparate aici:
  D-AG1  randurile EXISTENTE cu C/50 raman cum sunt — fara migrare de date. Se repara
         doar de acum incolo, iar fisierul asta masoara „de acum incolo".
  D-AG2b anunturile fara grad NU devin tacute: merg pe canalul `auto_all` (cel care
         primeste azi si C/D), cu titlul marcat „Fara grad". Canalele de A si B raman
         curate, iar `@here` nu se declanseaza niciodata pe ele.

REGULA DE TEST: cablarea se masoara prin `run_auto_scan`, nu apeland `_save_listing`.
Fara retea: `_call_scraper`, cursurile si catalogul sunt pinuite.
"""
import uuid

import pytest

from app.services import auto_listings_scanner as als


_CATALOG = {"RON": 1.0, "EUR": 5.0, "GBP": 6.0}


def _seed(db, resale_price=None, resale_currency="RON", webhookuri=None):
    """User + keyword facebook_auto. `webhookuri` populeaza RadarSettings, ca sa se poata
    verifica PE CE CANAL ajunge alerta."""
    from app.models.auto_keyword import AutoKeyword
    from app.models.radar_settings import RadarSettings
    from app.models.user import User

    email = f"ag_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    kw = AutoKeyword(user_id=u.id, name="kw ag", platform="facebook_auto",
                     is_active=True, active_hours_start=None, active_hours_end=None,
                     resale_price=resale_price, resale_price_currency=resale_currency,
                     notify_discord=True, notify_email=False)
    db.add(kw)
    setari = RadarSettings(user_id=u.id, **(webhookuri or {}))
    db.add(setari)
    db.commit()
    return u, kw


_TOATE_CANALELE = {
    "discord_webhook_auto_all": "https://discord.test/all",
    "discord_webhook_auto_b": "https://discord.test/b",
    "discord_webhook_auto": "https://discord.test/a",
}


def _card(ext: str, pret: float, moneda="RON") -> dict:
    return {"external_id": ext, "titlu": f"BMW X5 {ext}", "pret": pret,
            "currency": moneda, "url": f"https://autovit.ro/{ext}",
            "an": 2018, "km": 100000}


def _scan(monkeypatch, db, carduri, cozi=None, catalog=None):
    """Un ciclu prin `run_auto_scan`. `cozi` capteaza APELURILE DE ENQUEUE, deci se vede
    pe ce webhook ajunge fiecare alerta — nu doar ca `send_auto_notification` s-a chemat."""
    from app.services import currency_service
    from app.services import discord_service as ds

    monkeypatch.setattr(als, "_call_scraper",
                        lambda kw, *a, **k: [dict(c) for c in carduri]
                        if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(als, "get_eur_ron", lambda: 5.0)
    monkeypatch.setattr(currency_service, "catalog_ron",
                        lambda: dict(_CATALOG if catalog is None else catalog))
    monkeypatch.setattr(als.log_manager, "emit", lambda *a, **k: None)
    if cozi is not None:
        monkeypatch.setattr(ds.discord_service, "enqueue",
                            lambda **kw2: cozi.append(kw2))
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


# ── 1. keyword fara resale: fara grad, alerta DOAR pe auto_all ─────────────────
def test_fara_resale_da_rand_fara_grad_si_alerteaza_doar_pe_auto_all(monkeypatch, db):
    _seed(db, resale_price=None, webhookuri=_TOATE_CANALELE)
    ext = f"a{uuid.uuid4().hex[:10]}"
    cozi = []

    _scan(monkeypatch, db, [_card(ext, 50000.0)], cozi)

    rand = _rand(db, ext)
    assert rand is not None, "anuntul RAMANE in feed"
    assert rand.grade is None, "fara pret de revanzare nu exista grad — nici default"
    assert rand.score is None
    assert rand.margin_value is None

    assert len(cozi) == 1, f"exact un canal, nu trei: {[c['webhook_url'] for c in cozi]}"
    apel = cozi[0]
    assert apel["webhook_url"] == _TOATE_CANALELE["discord_webhook_auto_all"]
    assert apel["grade"] is None
    assert apel["mention_here"] is False, "@here nu se declanseaza pe un anunt fara grad"
    assert apel["embed"]["title"].startswith("🚗 [Fără grad]")


# ── 2. reaparitie mai ieftina pe un anunt fara grad (SEEN-3 pe None) ───────────
def test_scadere_pe_anunt_fara_grad_alerteaza_doar_daca_e_salvat(monkeypatch, db):
    """SEEN-3 alerteaza pe scadere cand randul e `saved` SAU cand gradul nou e A/B/C.
    Cu grad `None`, a doua conditie e falsa prin constructie — deci alerta de scadere
    depinde EXCLUSIV de `saved`. Masuram ambele ramuri."""
    from app.models.auto_feed_listing import AutoFeedListing

    _seed(db, resale_price=None, webhookuri=_TOATE_CANALELE)
    e_activ, e_salvat = f"a{uuid.uuid4().hex[:8]}", f"a{uuid.uuid4().hex[:8]}"
    cozi = []

    _scan(monkeypatch, db, [_card(e_activ, 50000.0), _card(e_salvat, 50000.0)], cozi)
    r = db.query(AutoFeedListing).filter(AutoFeedListing.external_id == e_salvat).first()
    r.status = "saved"
    db.commit()
    cozi.clear()

    _scan(monkeypatch, db, [_card(e_activ, 42000.0), _card(e_salvat, 42000.0)], cozi)

    for ext in (e_activ, e_salvat):
        rand = _rand(db, ext)
        assert float(rand.pret_anterior) == 50000.0, "referinta se scrie oricum (-16%)"
        assert rand.grade is None
    assert len(cozi) == 1, "doar randul SALVAT alerteaza; cel activ n-are grad de urcat"
    assert cozi[0]["embed"]["title"].startswith("🚗 [Fără grad] Pret scazut 16%: ")


# ── 3. moneda neconvertibila: fara golire post-insert (a fost stearsa) ─────────
def test_moneda_necunoscuta_da_grad_none_fara_golire_explicita(monkeypatch, db):
    """Dovada ca scoaterea default-ului din model e SUFICIENTA: CUR-2 avea nevoie de un
    UPDATE dupa insert ca sa goleasca „C"/50; codul acela a disparut."""
    import inspect

    _seed(db, resale_price=100000.0, webhookuri=_TOATE_CANALELE)
    ext = f"a{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, db, [_card(ext, 10000.0, moneda="XXX")])

    rand = _rand(db, ext)
    assert rand.grade is None and rand.score is None and rand.margin_value is None
    sursa = inspect.getsource(als._save_listing)
    assert "listing.grade = None" not in sursa, "golirea post-insert trebuia sa dispara"


# ── 4. regresie: cu resale, gradele raman exact ca inainte ─────────────────────
@pytest.mark.parametrize("pret,grad_asteptat", [
    (50000.0, "A"),      # marja 50%
    (75000.0, "B"),      # marja 25%
    (85000.0, "C"),      # marja 15%
    (95000.0, "D"),      # marja 5%, sub min_margin implicit de 10%
])
def test_cu_resale_gradele_raman_neschimbate(monkeypatch, db, pret, grad_asteptat):
    _seed(db, resale_price=100000.0, webhookuri=_TOATE_CANALELE)
    ext = f"a{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, db, [_card(ext, pret)])

    rand = _rand(db, ext)
    assert rand.grade == grad_asteptat
    assert rand.score is not None


# ── 5. embed-ul nu crapa pe None ───────────────────────────────────────────────
def test_build_auto_embed_pe_grad_lipsa():
    from app.services.discord_service import build_auto_embed

    embed = build_auto_embed({"title": "BMW X5", "price": 50000, "currency": "RON"},
                             None, None, "kw-test")

    assert "Fără grad" in embed["title"]
    assert "None" not in embed["title"]
    assert embed["footer"]["text"].endswith("—"), embed["footer"]
    assert isinstance(embed["color"], int)


def test_build_auto_embed_pe_grad_normal_neschimbat():
    """Regresie: A-D arata exact ca inainte."""
    from app.services.discord_service import GRADE_COLORS, build_auto_embed

    embed = build_auto_embed({"title": "BMW X5", "price": 50000, "currency": "RON"},
                             "A", 60, "kw-test")
    assert embed["title"] == "🚗 [A] BMW X5"
    assert embed["color"] == GRADE_COLORS["A"]
    assert embed["footer"]["text"].endswith("Score 60/100")


# ── 6 + 7. feed-ul: serializare si filtru ──────────────────────────────────────
def test_feed_serializeaza_null_si_filtreaza_fara_grad(auth_client):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing

    uid = auth_client.get("/api/auth/me").json()["id"]
    fara, cu = f"a{uuid.uuid4().hex[:8]}", f"a{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(AutoFeedListing(user_id=uid, keyword_id=None, platform="autovit",
                               external_id=fara, title="fara grad", price=1000,
                               currency="RON", status="active"))
        db.add(AutoFeedListing(user_id=uid, keyword_id=None, platform="autovit",
                               external_id=cu, title="cu grad", price=1000,
                               currency="RON", status="active", grade="A", score=60))
        db.commit()
    finally:
        db.close()

    items = auth_client.get("/api/auto-listings/feed").json()["items"]
    dupa_ext = {x["external_id"]: x for x in items}
    assert dupa_ext[fara]["grade"] is None, "null, nu „C"
    assert dupa_ext[cu]["grade"] == "A"

    doar_fara = auth_client.get("/api/auto-listings/feed?grade=none").json()["items"]
    ext_uri = {x["external_id"] for x in doar_fara}
    assert fara in ext_uri and cu not in ext_uri
