"""SHOP-2a — scannerul de deal-uri Shopify.

Toate testele sunt OFFLINE: enumerarea e monkeypatch-uita cu payload-uri sintetice
in forma MASURATA la sonda Grup 1 (pret string zecimal, `compare_at_price` string
sau None, `available` boolean). Magazinul de test e un domeniu REAL din registru,
ca moneda sa vina pe drumul adevarat.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.user import User
from app.services import deal_scanner

DOM = "asphaltgold.com"          # intrare reala in registru, currency EUR


# ── ajutoare ─────────────────────────────────────────────────────────────────

def _varianta(pret, compare_at=None, disponibil=True, titlu="42"):
    return {"title": titlu, "option1": titlu, "price": pret,
            "compare_at_price": compare_at, "available": disponibil}


def _produs(pid, variante, titlu="Sneaker test", handle="sneaker-test"):
    return {"id": pid, "handle": handle, "title": titlu,
            "images": [{"src": "https://cdn.example/x.jpg"}], "variants": variante}


class _Raspuns:
    def __init__(self, produse):
        self.status_code = 200
        self._produse = produse

    def json(self):
        return {"products": self._produse}


@pytest.fixture
def scan(monkeypatch):
    """Instaleaza enumerarea falsa + un singur magazin. Intoarce un runner care
    primeste paginile (lista de liste de produse) si ruleaza scanul."""
    cutie = {"pagini": []}
    cereri = []

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        numar = int(url.split("page=")[1])
        pagini = cutie["pagini"]
        return _Raspuns(pagini[numar - 1] if numar <= len(pagini) else [])

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(deal_scanner, "shopify_domains", lambda: {DOM})
    monkeypatch.setattr(deal_scanner, "_pauza", lambda: None)

    def ruleaza(pagini, **setari):
        cutie["pagini"] = pagini
        db = SessionLocal()
        try:
            _seteaza(db, **setari)
            return deal_scanner.run_deal_scan(db)
        finally:
            db.close()

    ruleaza.cereri = cereri
    return ruleaza


def _seteaza(db, **campuri):
    """User + RadarSettings (scannerul ia primul rand — instanta e single-user)."""
    if db.query(RadarSettings).first() is not None:
        s = db.query(RadarSettings).first()
        for k, v in campuri.items():
            setattr(s, k, v)
        db.commit()
        return s
    email = f"deal_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    s = RadarSettings(user_id=u.id, **campuri)
    db.add(s)
    db.commit()
    return s


def _deals():
    db = SessionLocal()
    try:
        return db.query(Deal).order_by(Deal.id).all()
    finally:
        db.close()


def _memorie():
    db = SessionLocal()
    try:
        return db.query(ShopPriceMemory).order_by(ShopPriceMemory.id).all()
    finally:
        db.close()


# ── testele ──────────────────────────────────────────────────────────────────

def test_pret_minim_al_variantelor_disponibile(scan):
    # Pretul e string zecimal ('249.99'), NU int in bani ca la endpointul .js din
    # SHOP-1. Minimul se ia doar peste variantele disponibile.
    scan([[
        _produs(1, [_varianta("199.00", disponibil=False),   # mai ieftin, dar epuizat
                    _varianta("249.99"),
                    _varianta("299.00")]),
        # Produs INTEGRAL epuizat: nu e chilipir cumparabil, deci se sare complet —
        # nici deal, nici rand de memorie (altfel ar contamina minimul istoric).
        _produs(2, [_varianta("50.00", disponibil=False)]),
    ]], deal_discount_threshold=20.0)

    memorie = _memorie()
    assert [m.external_id for m in memorie] == ["1"]
    assert memorie[0].min_price == 249.99


def test_r1_compare_at(scan):
    # Peste prag -> deal cu reason compare_at.
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    deals = _deals()
    assert len(deals) == 1
    assert deals[0].reason == "compare_at"
    assert deals[0].discount_pct == pytest.approx(50.0)

    # Sub prag, compare_at <= pret si compare_at absent -> niciun deal nou.
    scan([[_produs(2, [_varianta("190.00", compare_at="200.00")]),   # 5%
           _produs(3, [_varianta("200.00", compare_at="180.00")]),   # referinta sub pret
           _produs(4, [_varianta("150.00", compare_at=None)])]])
    assert {d.external_id for d in _deals()} == {"1"}


def test_r2_minim_istoric(scan):
    # Prima vedere n-are istoric -> fara R2, dar memoria se creeaza.
    scan([[_produs(1, [_varianta("200.00")])]], deal_discount_threshold=20.0)
    assert _deals() == []
    assert _memorie()[0].min_price == 200.0

    # Scadere peste prag, evaluata pe minimul VECHI (200), nu pe cel actualizat.
    scan([[_produs(1, [_varianta("140.00")])]])
    deals = _deals()
    assert len(deals) == 1
    assert deals[0].reason == "istoric"
    assert deals[0].discount_pct == pytest.approx(30.0)
    assert deals[0].min_price_seen == 200.0
    assert _memorie()[0].min_price == 140.0

    # Scadere sub prag pe un produs nou -> fara deal, dar minimul coboara.
    scan([[_produs(2, [_varianta("100.00")])]])
    scan([[_produs(2, [_varianta("95.00")])]])
    assert {d.external_id for d in _deals()} == {"1"}
    memorie = {m.external_id: m.min_price for m in _memorie()}
    assert memorie["2"] == 95.0


def test_ambele_referinte(scan):
    scan([[_produs(1, [_varianta("200.00")])]], deal_discount_threshold=20.0)
    # Pret 100: fata de compare_at 250 -> 60%; fata de minimul vechi 200 -> 50%.
    scan([[_produs(1, [_varianta("100.00", compare_at="250.00")])]])

    deal = _deals()[0]
    assert deal.reason == "ambele"
    assert deal.discount_pct == pytest.approx(60.0)


def test_upsert_dedup(scan):
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    db = SessionLocal()
    try:
        d = db.query(Deal).first()
        d.state = "vazut"
        db.commit()
    finally:
        db.close()

    scan([[_produs(1, [_varianta("90.00", compare_at="200.00")])]])

    deals = _deals()
    assert len(deals) == 1, "al doilea scan trebuie sa ACTUALIZEZE, nu sa duplice"
    assert deals[0].price == 90.0
    assert deals[0].state == "vazut", "starea e a userului, scannerul n-o atinge"


def test_ciclu_de_viata(scan):
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    db = SessionLocal()
    try:
        db.query(Deal).first().state = "ignorat"
        db.commit()
    finally:
        db.close()

    # Disparut din scan -> se INCHEIE, nu se sterge; starea ramane.
    scan([[]])
    deal = _deals()[0]
    assert deal.ended_at is not None
    assert deal.state == "ignorat"

    # Reaparut -> redevine activ, dar `ignorat` NU redevine `nou`.
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]])
    deal = _deals()[0]
    assert deal.ended_at is None
    assert deal.state == "ignorat"


def test_discord_doar_la_nou(scan, monkeypatch):
    apeluri = []
    monkeypatch.setattr("app.services.discord_service.discord_service.enqueue",
                        lambda **kw: apeluri.append(kw))

    # Fara webhook configurat -> niciun enqueue.
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    assert apeluri == []

    # Cu webhook -> exact o alerta la crearea deal-ului.
    scan([[_produs(2, [_varianta("100.00", compare_at="200.00")])]],
         discord_webhook_deals="https://discord.com/api/webhooks/1/abc")
    assert len(apeluri) == 1
    assert apeluri[0]["module"] == "deals"
    assert apeluri[0]["grade"] == "DL"

    # Reaparitia aceluiasi deal NU realerteaza.
    scan([[_produs(2, [_varianta("95.00", compare_at="200.00")])]])
    assert len(apeluri) == 1


def test_paginare_si_cap(scan):
    # Se opreste la prima pagina goala: pagina 3 nu mai e ceruta.
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])],
          [_produs(2, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    assert len(scan.cereri) == 3, "doua pagini cu produse + una goala care opreste"
    assert {d.external_id for d in _deals()} == {"1", "2"}

    # Capacul de pagini opreste o enumerare care nu se termina niciodata.
    scan.cereri.clear()
    pagina = [_produs(9, [_varianta("100.00", compare_at="200.00")])]
    scan([pagina] * (deal_scanner._MAX_PAGES_DEAL + 5))
    assert len(scan.cereri) == deal_scanner._MAX_PAGES_DEAL


def test_toggle_magazin_si_global(scan):
    # Magazinul dezactivat explicit e sarit.
    rezumat = scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
                   deal_discount_threshold=20.0, deal_shops_disabled=[DOM])
    assert rezumat["magazine"] == 0
    assert _deals() == []

    # Toggle-ul global opreste scanul intreg, inaintea oricarui fetch.
    scan.cereri.clear()
    rezumat = scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
                   deal_shops_disabled=[], deal_scan_enabled=False)
    assert rezumat.get("skipped")
    assert scan.cereri == []
    assert _deals() == []


def test_promovare(auth_client, scan, monkeypatch):
    scan([[_produs(1, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    deal_id = _deals()[0].id

    # Calea add-by-link e refolosita integral -> extractia se monkeypatch-uieste
    # acolo unde traieste, iar task-urile de fundal (EAN, cross-shop) nu ies pe retea.
    monkeypatch.setattr("app.routers.products.extract_product", lambda url, **kw: {
        "name": "Sneaker test", "price": 100.0, "currency": "EUR", "in_stock": True,
        "is_aggregate": False, "variants": None, "image_url": None,
        "canonical_url": f"https://{DOM}/products/sneaker-test", "domain": DOM,
        "method": "shopify", "override_applied": False,
    })
    monkeypatch.setattr("app.routers.products._backfill_ean", lambda *a, **k: None)
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda *a, **k: None)

    raspuns = auth_client.post(f"/api/deals/{deal_id}/promote")
    assert raspuns.status_code == 200, raspuns.text
    product_id = raspuns.json()["product_id"]

    deal = _deals()[0]
    assert deal.state == "promovat"
    assert deal.promoted_product_id == product_id

    db = SessionLocal()
    try:
        from app.models.tracked_product import TrackedProduct
        tracked = (db.query(TrackedProduct)
                   .filter(TrackedProduct.product_id == product_id).first())
        assert tracked is not None and tracked.monitoring_active is True
    finally:
        db.close()

    # `promovat` nu poate fi setat direct din UI — vine doar din promovare.
    r = auth_client.patch(f"/api/deals/{deal_id}", json={"state": "promovat"})
    assert r.status_code == 422
