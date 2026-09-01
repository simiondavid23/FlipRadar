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

def test_produs_repetat_intre_pagini_nu_dubleaza_memoria(scan):
    """SCAN-1, perechea simetrica a testului din test_listing_scanner.

    Enumerarea Shopify e paginata, deci un produs poate reaparea daca magazinul se
    modifica intre cereri. A doua aparitie reintra in blocul de memorie, iar cu
    `SessionLocal(autoflush=False)` randul adaugat la prima nu e inca vizibil
    interogarii — se adauga al doilea si commit-ul cade pe cheia unica.

    Produsele n-au `compare_at_price` DELIBERAT: fara el nu califica drept deal,
    deci nu se executa `db.add(deal)` + `db.flush()`, iar acel flush ar persista tot
    ce e pending — inclusiv memoria — si ar masca bugul. Fereastra periculoasa e
    tocmai secventa de produse necalificate dintre cele doua aparitii.
    """
    repetat = _produs(1, [_varianta("100.00")], handle="repetat")
    p1 = [repetat, _produs(2, [_varianta("110.00")], handle="al-doilea")]
    p2 = [repetat, _produs(3, [_varianta("120.00")], handle="al-treilea")]

    rezumat = scan([p1, p2, []])

    assert rezumat["erori"] == 0, "produsul repetat nu are voie sa pice scanul"
    externe = [m.external_id for m in _memorie()]
    assert len(externe) == len(set(externe)), "un external_id = un singur rand"
    assert sorted(externe) == ["1", "2", "3"]


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


# ── DEAL-2b — prag separat pentru R1 + inchiderea pe calificare ──────────────

def test_evalueaza_prag_r1_separat_pentru_r1():
    """R1 se compara cu pragul LUI: peste pragul global, dar sub cel dedicat R1,
    produsul NU mai califica."""
    # 25% reducere fata de compare_at: trece de 20, dar nu de 40.
    assert deal_scanner._evalueaza(75.0, 100.0, None, 20.0, prag_r1=40.0) == (None, None)
    assert deal_scanner._evalueaza(75.0, 100.0, None, 20.0)[1] == "compare_at"


def test_evalueaza_prag_r1_nu_atinge_r2():
    """R2 ramane pe pragul global — el e semnalul curat si nu se muta."""
    discount, reason = deal_scanner._evalueaza(75.0, None, 100.0, 20.0, prag_r1=90.0)

    assert reason == "istoric"
    assert discount == pytest.approx(25.0)


def test_evalueaza_ambele_cu_praguri_diferite():
    """Cand amandoua trec, fiecare s-a comparat cu pragul EI, iar procentul
    raportat e maximul lor."""
    # R1 = 50% (compare_at 200 -> 100), R2 = 20% (minim vechi 125 -> 100).
    discount, reason = deal_scanner._evalueaza(100.0, 200.0, 125.0, 15.0, prag_r1=40.0)

    assert reason == "ambele"
    assert discount == pytest.approx(50.0)

    # Acelasi caz, dar R1 sub pragul lui -> ramane doar R2.
    discount, reason = deal_scanner._evalueaza(100.0, 200.0, 125.0, 15.0, prag_r1=60.0)
    assert reason == "istoric"
    assert discount == pytest.approx(20.0)


def test_evalueaza_fara_prag_r1_identic_cu_vechiul_comportament():
    """Apelurile existente (fara `prag_r1`) trebuie sa dea EXACT ce dadeau —
    schimbarea e backward-compatible, nu o a doua implementare."""
    for pret, compare_at, minim, prag in ((75.0, 100.0, None, 20.0),
                                          (75.0, None, 100.0, 20.0),
                                          (100.0, 200.0, 125.0, 15.0),
                                          (99.0, 100.0, 100.0, 20.0)):
        assert (deal_scanner._evalueaza(pret, compare_at, minim, prag)
                == deal_scanner._evalueaza(pret, compare_at, minim, prag, prag_r1=None))


def test_inchide_dealul_prezent_dar_necalificat(scan):
    """DEFECTUL reparat: pana acum se inchideau doar produsele DISPARUTE, deci un
    produs inca prezent al carui pret a urcat ramanea „activ" cu date vechi."""
    scan([[_produs(7001, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    deal = [d for d in _deals() if d.external_id == "7001"][0]
    assert deal.ended_at is None

    # Acelasi produs, tot prezent, dar pretul a urcat: 190 fata de 200 = 5%.
    scan([[_produs(7001, [_varianta("190.00", compare_at="200.00")])]])

    deal = [d for d in _deals() if d.external_id == "7001"][0]
    assert deal.ended_at is not None, "produs prezent dar necalificat -> inchis"


def test_inchiderea_nu_atinge_starea_userului(scan):
    """D7: inchiderea scrie `ended_at`, nu se atinge de starea userului."""
    scan([[_produs(7002, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    db = SessionLocal()
    try:
        db.query(Deal).filter(Deal.external_id == "7002").first().state = "ignorat"
        db.commit()
    finally:
        db.close()

    scan([[_produs(7002, [_varianta("190.00", compare_at="200.00")])]])

    deal = [d for d in _deals() if d.external_id == "7002"][0]
    assert deal.ended_at is not None
    assert deal.state == "ignorat"


def test_inchiderea_shopify_nu_atinge_refresh_diff(scan):
    """Protectia pe `deal_source` e EXPLICITA: un rand `refresh_diff` poate sta pe
    acelasi domeniu (produs urmarit prin link) si scanul nu spune nimic despre el."""
    scan([[_produs(7003, [_varianta("100.00", compare_at="200.00")])]],
         deal_discount_threshold=20.0)
    db = SessionLocal()
    try:
        db.add(Deal(shop_domain=DOM, external_id="src:4242", title="urmarit prin link",
                    url=f"https://{DOM}/x", currency="EUR", price=10.0,
                    discount_pct=50.0, reason="istoric", state="nou",
                    deal_source="refresh_diff"))
        db.commit()
    finally:
        db.close()

    scan([[]])                      # totul a disparut din enumerare

    strain = [d for d in _deals() if d.external_id == "src:4242"][0]
    shopify = [d for d in _deals() if d.external_id == "7003"][0]
    assert strain.ended_at is None, "randul refresh_diff ramane neatins"
    assert shopify.ended_at is not None


# ── DEAL-2b — filtrul de sursa in feed ──────────────────────────────────────

def _deal_de_sursa(db, sursa, external_id):
    db.add(Deal(shop_domain=DOM, external_id=external_id, title=f"deal {sursa}",
                url="https://x", currency="EUR", price=10.0, discount_pct=50.0,
                reason="istoric", state="nou", deal_source=sursa))


def test_list_deals_filtreaza_pe_sursa(auth_client):
    db = SessionLocal()
    try:
        _deal_de_sursa(db, "shopify_enum", "s1")
        _deal_de_sursa(db, "listing_scan", "l1")
        _deal_de_sursa(db, "refresh_diff", "r1")
        db.commit()
    finally:
        db.close()

    toate = auth_client.get("/api/deals/").json()
    assert len(toate) == 3
    assert all("deal_source" in d for d in toate), "proveniența pleaca spre UI"

    doar_listari = auth_client.get("/api/deals/?source=listing_scan").json()
    assert [d["external_id"] for d in doar_listari] == ["l1"]


def test_list_deals_sursa_invalida_da_422(auth_client):
    raspuns = auth_client.get("/api/deals/?source=xyz")

    assert raspuns.status_code == 422
    assert "Sursă invalidă" in raspuns.json()["detail"]


# ── SET-1 — setarile de deal-uri se intorc din GET + rand determinist ────────

def test_get_settings_intoarce_setarile_de_dealuri(auth_client):
    """Testul-regresie al pierderii de date: PUT-ul persista de la SHOP-2a, dar
    GET-ul omitea cheile, iar frontend-ul citeste de aici. `toggleDealShop`
    construia setul din `deal_shops_disabled || []` — mereu undefined dupa reload
    — deci prima dezactivare STERGEA toate celelalte."""
    pus = auth_client.put("/api/radar/settings", json={
        "deal_discount_threshold": 25.0,
        "listing_r1_threshold": 60.0,
        "deal_scan_enabled": False,
        "deal_shops_disabled": ["patta.nl", "otter.ro"],
    })
    assert pus.status_code == 200, pus.text

    date = auth_client.get("/api/radar/settings").json()

    assert date["deal_discount_threshold"] == 25.0
    assert date["listing_r1_threshold"] == 60.0
    assert date["deal_scan_enabled"] is False
    assert sorted(date["deal_shops_disabled"]) == ["otter.ro", "patta.nl"]


def test_get_settings_dezactivari_ramane_lista_dupa_a_doua_dezactivare(auth_client):
    """Scenariul exact al bug-ului, jucat pe server: doua dezactivari succesive,
    fiecare trimisa ca reuniune peste ce a intors GET-ul, ca in UI."""
    auth_client.put("/api/radar/settings", json={"deal_shops_disabled": ["patta.nl"]})

    curent = auth_client.get("/api/radar/settings").json()["deal_shops_disabled"]
    auth_client.put("/api/radar/settings",
                    json={"deal_shops_disabled": sorted(set(curent) | {"otter.ro"})})

    final = auth_client.get("/api/radar/settings").json()["deal_shops_disabled"]
    assert sorted(final) == ["otter.ro", "patta.nl"], \
        "a doua dezactivare nu are voie sa stearga prima"


def test_get_settings_dezactivari_gol_e_lista_nu_none(auth_client):
    """Consumatorul face `new Set(...)` pe valoare, deci None ar fi o capcana."""
    date = auth_client.get("/api/radar/settings").json()

    assert date["deal_shops_disabled"] == []
    assert date["deal_scan_enabled"] is True, "default-ul modelului, nu None"


def test_settings_randul_e_determinist_pe_user_id():
    """`.first()` fara ORDER BY lasa randul castigator la mila planului de query:
    asa a fost ignorat pragul de 60 al userului 1 la scanul DEAL-2b."""
    db = SessionLocal()
    try:
        for user_id, prag in ((13, None), (1, 60.0)):
            email = f"set1_{user_id}_{uuid.uuid4().hex[:8]}@example.com"
            u = User(id=user_id, email=email, username=email.split("@")[0],
                     hashed_password="x", is_active=True)
            db.add(u)
            db.flush()
            db.add(RadarSettings(user_id=user_id, listing_r1_threshold=prag,
                                 deal_discount_threshold=prag))
        db.commit()

        setari = deal_scanner._settings(db)

        assert setari.user_id == 1, "guverneaza userul cu id-ul cel mai mic"
        assert setari.listing_r1_threshold == 60.0
        assert deal_scanner._prag(setari) == 60.0
        from app.services.listing_scanner import _prag_r1
        assert _prag_r1(setari) == 60.0, "listing_scanner mosteneste randul prin import"
    finally:
        db.close()


def test_settings_un_singur_rand_neschimbat():
    """Regresie de context: pe instanta impachetata (un singur rand) nimic nu se
    schimba fata de comportamentul de dinainte de SET-1."""
    db = SessionLocal()
    try:
        email = f"set1_solo_{uuid.uuid4().hex[:8]}@example.com"
        u = User(email=email, username=email.split("@")[0], hashed_password="x",
                 is_active=True)
        db.add(u)
        db.flush()
        db.add(RadarSettings(user_id=u.id, deal_discount_threshold=33.0))
        db.commit()

        setari = deal_scanner._settings(db)

        assert setari.user_id == u.id
        assert deal_scanner._prag(setari) == 33.0
    finally:
        db.close()


# ── DEAL-3: paginare, numaratoare, filtre si sortare pe SERVER ───────────────
# Fixture-urile sunt cele existente (`auth_client` + `clean_db` autouse). Toate
# cele cinci randuri stau pe DOM, ca filtrul de categorie sa aiba ce potrivi.

def _cinci_active(db):
    """Cinci deal-uri active, cu discounturi SI preturi distincte, ca ordinea sa
    fie neambigua indiferent de sortarea ceruta."""
    for ext, disc, pret, moneda, stare in (
            ("p1", 50.0, 5.0, "EUR", "nou"),
            ("p2", 40.0, 80.0, "RON", "nou"),
            ("p3", 30.0, 60.0, "RON", "vazut"),
            ("p4", 20.0, 40.0, "RON", "vazut"),
            ("p5", 10.0, 20.0, "RON", "vazut")):
        db.add(Deal(shop_domain=DOM, external_id=ext, title=ext.upper(),
                    url=f"https://x/{ext}", currency=moneda, price=pret,
                    discount_pct=disc, reason="compare_at", state=stare))
    db.commit()


def test_deal3_limit_offset_si_count(auth_client):
    """T1 — paginarea taie in SQL, nu in browser, iar /count raspunde pe aceleasi
    filtre ca lista."""
    db = SessionLocal()
    try:
        _cinci_active(db)
    finally:
        db.close()

    prima = auth_client.get("/api/deals/?limit=2").json()
    assert [d["external_id"] for d in prima] == ["p1", "p2"], "discount descrescator"

    ultima = auth_client.get("/api/deals/?limit=2&offset=4").json()
    assert [d["external_id"] for d in ultima] == ["p5"], "ultima pagina are un rand"

    assert auth_client.get("/api/deals/count").json() == {"total": 5}


def test_deal3_exclude_state_categorie_si_sortare(auth_client, monkeypatch):
    """T2 — `exclude_state` inlocuieste filtrul client-side de pe tab-ul „Active",
    iar categoria si sortarea au coborat si ele pe server."""
    # Cursul e fixat in test: masuram ORDINEA, nu valorile BNR.
    monkeypatch.setattr("app.routers.deals.get_all_rates",
                        lambda: {"EUR_RON": 5.0, "USD_RON": 4.0})
    monkeypatch.setattr("app.routers.deals.convert",
                        lambda valoare, din, catre: valoare * 5.0)
    db = SessionLocal()
    try:
        _cinci_active(db)
    finally:
        db.close()

    ids = {d["external_id"]: d["id"] for d in auth_client.get("/api/deals/").json()}
    assert auth_client.patch(f"/api/deals/{ids['p3']}",
                             json={"state": "ignorat"}).status_code == 200

    assert len(auth_client.get("/api/deals/?exclude_state=ignorat").json()) == 4
    assert (auth_client.get("/api/deals/count?exclude_state=ignorat").json()
            == {"total": 4}), "numaratoarea vede EXACT filtrele listei"

    # sort=price compara in RON: p1 e 5 EUR = 25 RON, deci ajunge al doilea cel
    # mai ieftin. Fara conversie ar fi iesit PRIMUL, cu "5 lei" — exact greseala
    # pe care o prinde acest assert.
    dupa_pret = [d["external_id"]
                 for d in auth_client.get("/api/deals/?sort=price").json()]
    assert dupa_pret == ["p5", "p1", "p4", "p3", "p2"]

    # Categoria e a MAGAZINULUI (SHOP_REGISTRY), nu a randului: toate cele cinci
    # stau pe DOM, care e `sneakers`.
    assert len(auth_client.get("/api/deals/?category=sneakers").json()) == 5
    # O categorie fara niciun magazin filtreaza la ZERO, nu se ignora.
    assert auth_client.get("/api/deals/?category=inexistenta").json() == []

    assert auth_client.get("/api/deals/?sort=invalid").status_code == 422
    assert auth_client.get("/api/deals/?exclude_state=inventat").status_code == 422


def test_deal3_stats_agregat(auth_client):
    """T3 — cifrele calculate acum in SQL (COUNT/SUM/AVG) sunt identice cu cele
    numarate manual din fixture, inclusiv pe baza GOALA, unde SUM da NULL."""
    db = SessionLocal()
    try:
        _cinci_active(db)
    finally:
        db.close()

    stats = auth_client.get("/api/deals/stats").json()
    assert stats["active"] == 5
    assert stats["noi"] == 2                        # p1 si p2
    assert stats["avg_discount_active"] == 30.0     # (50+40+30+20+10)/5

    db = SessionLocal()
    try:
        db.query(Deal).delete()
        db.commit()
    finally:
        db.close()

    gol = auth_client.get("/api/deals/stats").json()
    assert gol["active"] == 0
    # SUM peste zero randuri da NULL -> 0, dar AVG ramane None: „nu exista active
    # de mediat" nu e acelasi lucru cu „media e zero".
    assert gol["noi"] == 0
    assert gol["avg_discount_active"] is None
