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
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.user import User
from app.services import deal_scanner
from app.services.shop_registry import listing_domains, shopify_domains
from app.utils import alert_checker

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


# ── SHOP-2b: campuri de afisare + endpointuri de suport ──────────────────────

def test_price_ron_in_listare(auth_client, monkeypatch):
    # Conversia e determinista in test: masuram MAPAREA, nu cursul BNR.
    monkeypatch.setattr("app.routers.deals.convert",
                        lambda valoare, din, catre: valoare * 5.0)
    db = SessionLocal()
    try:
        db.add(Deal(shop_domain=DOM, external_id="eur", title="EUR", url="https://x",
                    currency="EUR", price=100.0, compare_at_price=200.0,
                    discount_pct=50.0, reason="compare_at"))
        db.add(Deal(shop_domain="rocashoes.ro", external_id="ron", title="RON",
                    url="https://y", currency="RON", price=300.0,
                    discount_pct=25.0, reason="istoric"))
        db.commit()
    finally:
        db.close()

    items = {d["external_id"]: d for d in auth_client.get("/api/deals/").json()}

    assert items["eur"]["price_ron"] == 500.0
    assert items["eur"]["compare_at_price_ron"] == 1000.0
    # RON trece direct, fara apel de conversie (altfel ar fi devenit 1500).
    assert items["ron"]["price_ron"] == 300.0
    # compare_at_price_ron apare DOAR cand exista compare_at.
    assert "compare_at_price_ron" not in items["ron"]


def test_stats_si_shops(auth_client):
    from datetime import datetime, timezone

    from app.models.shop_scan_state import ShopScanState

    acum = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        db.add(Deal(shop_domain=DOM, external_id="a", title="A", url="https://a",
                    currency="EUR", price=10.0, discount_pct=40.0, reason="compare_at",
                    state="nou"))
        db.add(Deal(shop_domain=DOM, external_id="b", title="B", url="https://b",
                    currency="EUR", price=10.0, discount_pct=20.0, reason="istoric",
                    state="vazut"))
        # Incheiat -> nu intra nici in `active`, nici in medie.
        db.add(Deal(shop_domain=DOM, external_id="c", title="C", url="https://c",
                    currency="EUR", price=10.0, discount_pct=90.0, reason="istoric",
                    state="nou", ended_at=acum))
        db.add(ShopScanState(shop_domain=DOM, last_scan_at=acum, last_status="ok",
                             products_seen=42, deals_active=2))
        # Un magazin dezactivat, ca sa verificam reflectarea in /shops. Setarile
        # TREBUIE sa fie ale userului lui auth_client — /shops le citeste pe ale
        # apelantului. clean_db goleste inaintea fiecarui test, deci userul
        # inregistrat de fixture e singurul din baza.
        user = db.query(User).first()
        setari = (db.query(RadarSettings)
                  .filter(RadarSettings.user_id == user.id).first())
        if setari is None:
            setari = RadarSettings(user_id=user.id)
            db.add(setari)
        setari.deal_shops_disabled = ["patta.nl"]
        db.commit()
    finally:
        db.close()

    stats = auth_client.get("/api/deals/stats").json()
    assert stats["active"] == 2
    assert stats["noi"] == 1
    assert stats["avg_discount_active"] == 30.0
    assert stats["last_scan_at"] is not None

    shops = {s["domain"]: s for s in auth_client.get("/api/deals/shops").json()}
    # DEAL-2: universul e REUNIUNEA celor doua capabilitati — enumerarea Shopify si
    # descriptorii de listare. Starile vin din acelasi ShopScanState pentru amandoua.
    assert shops.keys() == shopify_domains() | listing_domains(), \
        "universul vine din registru"
    assert shops["patta.nl"]["disabled"] is True
    assert shops[DOM]["disabled"] is False
    assert shops[DOM]["label"] and shops[DOM]["currency"] == "EUR"
    # Starea de scan e atasata unde exista, si absenta unde nu.
    assert shops[DOM]["last_status"] == "ok"
    assert shops[DOM]["products_seen"] == 42
    assert shops["patta.nl"]["last_status"] is None


# ── SHOP-2c: declansare manuala + garda de concurenta ────────────────────────

def test_scan_manual_porneste(auth_client, monkeypatch):
    import threading as _th

    pornit = _th.Event()
    monkeypatch.setattr(deal_scanner, "run_deal_scan",
                        lambda db: (pornit.set(), {"magazine": 0})[1])

    raspuns = auth_client.post("/api/deals/scan")

    assert raspuns.status_code == 200, raspuns.text
    assert raspuns.json() == {"started": True}
    # Scanul ruleaza pe thread daemon, deci il asteptam explicit — fara asta,
    # testul ar putea trece si daca thread-ul nu porneste niciodata.
    assert pornit.wait(timeout=5), "runnerul nu a fost invocat pe thread-ul de fundal"


def test_scan_concurent_409(auth_client, monkeypatch):
    cereri = []
    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded",
                        lambda url, **kw: cereri.append(url))

    # Lock-ul tinut simuleaza o scanare in curs (jobul de la 6h sau un dublu-click).
    deal_scanner._SCAN_LOCK.acquire()
    try:
        assert deal_scanner.is_scan_running() is True
        assert auth_client.post("/api/deals/scan").status_code == 409

        # Chiar apelat direct, runnerul iese imediat: nu atinge reteaua.
        db = SessionLocal()
        try:
            rezultat = deal_scanner.run_deal_scan(db)
        finally:
            db.close()
        assert rezultat.get("skipped") == "scan deja in curs"
        assert cereri == [], "scanul a pornit desi lock-ul era tinut"
    finally:
        deal_scanner._SCAN_LOCK.release()

    # Dupa eliberare, garda nu mai blocheaza.
    assert deal_scanner.is_scan_running() is False


# ── DEAL-1: scaderile de la refresh ca randuri de feed ───────────────────────

def _sursa(db, *, pret, sursa, in_stock=True, variant="", nume="Produs urmarit"):
    """Product + ProductSource, minimul cerut de calea de refresh."""
    p = Product(name=nume, image_url="https://cdn.example/p.jpg", current_price=pret)
    db.add(p)
    db.flush()
    ps = ProductSource(product_id=p.id, source=sursa,
                       source_url=f"https://{sursa}/produs", current_price=pret,
                       currency="RON", in_stock=in_stock, variant=variant)
    db.add(ps)
    db.commit()
    return p, ps


def test_refresh_diff_creeaza_deal(monkeypatch):
    apeluri = []
    monkeypatch.setattr("app.services.discord_service.send_deal_notification",
                        lambda *a, **k: apeluri.append(a) or True)
    db = SessionLocal()
    try:
        _seteaza(db, deal_discount_threshold=20.0)
        produs, ps = _sursa(db, pret=200.0, sursa="magazin-deal1.ro")

        deal = deal_scanner.record_refresh_diff_deal(
            db, product=produs, ps=ps, old_price=200.0, new_price=100.0, min30=90.0)

        assert deal is not None
        assert deal.deal_source == "refresh_diff"
        assert deal.reason == "istoric"
        assert deal.external_id == f"src:{ps.id}"
        assert deal.shop_domain == "magazin-deal1.ro"
        assert deal.state == "nou"
        assert deal.price == 100.0
        assert deal.discount_pct == pytest.approx(50.0)
        assert deal.compare_at_price is None
        assert deal.min_price_seen == 90.0
        assert deal.currency == "RON"
        assert deal.url == ps.source_url
        # Dezambiguizare: momentul e deja acoperit de flash-deal pe canalul lui.
        assert apeluri == []
    finally:
        db.close()


def test_refresh_diff_sub_prag(monkeypatch):
    db = SessionLocal()
    try:
        _seteaza(db, deal_discount_threshold=20.0)
        produs, ps = _sursa(db, pret=200.0, sursa="magazin-deal2.ro")

        # 5% — scadere reala, dar sub pragul de feed.
        deal = deal_scanner.record_refresh_diff_deal(
            db, product=produs, ps=ps, old_price=200.0, new_price=190.0, min30=None)

        assert deal is None
        assert db.query(Deal).filter(Deal.shop_domain == "magazin-deal2.ro").count() == 0
    finally:
        db.close()


def test_refresh_diff_garda_stoc(monkeypatch):
    """5.3e acopera si feed-ul: o scadere pe sursa epuizata nu ajunge la helper.

    Doua surse pe acelasi produs, amandoua cu aceeasi scadere de 50% — singura
    diferenta e stocul. Doar cea cumparabila trebuie sa treaca.
    """
    vazute = []
    monkeypatch.setattr(alert_checker, "_SCRAPE_DELAY_RANGE", (0, 0))
    monkeypatch.setattr(alert_checker, "_check_and_send_flash_deals",
                        lambda *a, **k: None)
    monkeypatch.setattr(alert_checker, "record_refresh_diff_deal",
                        lambda db, *, product, ps, old_price, new_price, min30:
                        vazute.append(ps.id))

    db = SessionLocal()
    try:
        _, ps_epuizat = _sursa(db, pret=200.0, sursa="magazin-epuizat.ro", in_stock=False)
        _, ps_stoc = _sursa(db, pret=200.0, sursa="magazin-stoc.ro", in_stock=True)
        cunoscute = {"magazin-epuizat.ro", "magazin-stoc.ro"}

        def fals(*, source, source_url, product_name, sku, variant):
            # None pe sursele straine: testul nu are voie sa depinda de ce a lasat
            # alt test in DB. `in_stock` None = NECUNOSCUT, deci nu suprascrie.
            if source not in cunoscute:
                return None
            return {"price": 100.0, "in_stock": None}

        monkeypatch.setattr(alert_checker, "refresh_source", fals)
        alert_checker._refresh_all_scrapeable_products(db)

        assert ps_stoc.id in vazute
        assert ps_epuizat.id not in vazute
    finally:
        db.close()


def test_refresh_diff_upsert_si_incheiere():
    db = SessionLocal()
    try:
        _seteaza(db, deal_discount_threshold=20.0)
        produs, ps = _sursa(db, pret=200.0, sursa="magazin-deal4.ro", variant="42")

        primul = deal_scanner.record_refresh_diff_deal(
            db, product=produs, ps=ps, old_price=200.0, new_price=100.0, min30=None)
        assert primul.state == "nou"
        assert primul.title.endswith("— 42")     # varianta intra in titlu
        primul.state = "vazut"                   # D7: starea e a userului
        db.commit()

        al_doilea = deal_scanner.record_refresh_diff_deal(
            db, product=produs, ps=ps, old_price=100.0, new_price=60.0, min30=None)

        assert al_doilea.id == primul.id         # ACELASI rand, nu unul nou
        assert al_doilea.state == "vazut"        # starea userului, neatinsa
        assert al_doilea.price == 60.0
        assert al_doilea.discount_pct == pytest.approx(40.0)
        assert al_doilea.ended_at is None
        assert db.query(Deal).filter(Deal.shop_domain == "magazin-deal4.ro").count() == 1

        # Pretul urca peste cel al deal-ului -> oferta se INCHEIE, randul ramane.
        incheiat = deal_scanner.record_refresh_diff_deal(
            db, product=produs, ps=ps, old_price=60.0, new_price=195.0, min30=None)

        assert incheiat is None
        db.refresh(primul)
        assert primul.ended_at is not None
        assert primul.state == "vazut"
        assert db.query(Deal).filter(Deal.shop_domain == "magazin-deal4.ro").count() == 1
    finally:
        db.close()


def test_scanner_seteaza_shopify_enum(scan):
    scan([[_produs(9001, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)

    deals = [d for d in _deals() if d.shop_domain == DOM and d.external_id == "9001"]
    assert len(deals) == 1
    assert deals[0].deal_source == "shopify_enum"
