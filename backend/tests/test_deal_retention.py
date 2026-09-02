"""DEAL-4 — curatenia zilnica a feed-ului de deal-uri.

Toate testele sunt OFFLINE: nu porneste niciun scanner si nu se atinge nicio
retea. Se scriu direct randuri in `deals` cu varstele dorite si se masoara ce
face `run_deal_cleanup` cu ele. Fixture-ul `clean_db` (autouse, in conftest)
goleste tabelele inaintea fiecarui test.
"""
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.product import Product
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.services import deal_retention
from app.services.deal_retention import run_deal_cleanup

DOM = "asphaltgold.com"          # intrare reala in registru, ca in test_deal_scanner


def _acum():
    return datetime.now(timezone.utc)


def _deal(db, ext, *, vazut_acum_zile=0, incheiat_acum_zile=None,
          stare="nou", produs_id=None, domeniu=DOM):
    """Un rand de deal cu varsta ceruta. `incheiat_acum_zile=None` inseamna ACTIV."""
    acum = _acum()
    db.add(Deal(
        shop_domain=domeniu, external_id=ext, title=ext.upper(),
        url=f"https://x/{ext}", currency="EUR", price=10.0,
        discount_pct=30.0, reason="compare_at", state=stare,
        first_seen_at=acum - timedelta(days=vazut_acum_zile + 1),
        last_seen_at=acum - timedelta(days=vazut_acum_zile),
        ended_at=(None if incheiat_acum_zile is None
                  else acum - timedelta(days=incheiat_acum_zile)),
        promoted_product_id=produs_id))


def _stari(db):
    """{external_id: ended_at} pentru tot ce a ramas in tabela."""
    return {d.external_id: d.ended_at for d in db.query(Deal).all()}


def test_garda_de_stale_inchide_doar_ce_e_vechi():
    """T1 — activele nevazute de peste DEAL_STALE_DAYS (3) primesc `ended_at`;
    cele vazute recent raman neatinse. Asta e plasa pentru scanul care pica: fara
    ea, un domeniu cazut isi tine deal-urile active la nesfarsit."""
    db = SessionLocal()
    try:
        for ext in ("vechi1", "vechi2", "vechi3"):
            _deal(db, ext, vazut_acum_zile=4)
        for ext in ("proaspat1", "proaspat2"):
            _deal(db, ext, vazut_acum_zile=1)
        db.commit()

        rezultat = run_deal_cleanup(db)

        # Cheile care conteaza pentru ACEST test, nu dict-ul intreg: contractul de
        # retur a crescut la D4, iar un test despre garda de stale n-are motiv sa
        # pice cand se adauga un pas nou de curatenie. Forma completa e fixata in
        # `test_d4_contractul_de_retur`.
        assert rezultat["stale_inchise"] == 3
        assert rezultat["sterse"] == 0
        dupa = _stari(db)
        assert len(dupa) == 5, "garda inchide, nu sterge"
        for ext in ("vechi1", "vechi2", "vechi3"):
            assert dupa[ext] is not None, f"{ext} trebuia inchis"
        for ext in ("proaspat1", "proaspat2"):
            assert dupa[ext] is None, f"{ext} a fost vazut ieri, nu se atinge"
    finally:
        db.close()


def test_retentia_sterge_doar_incheiatele_vechi_nepromovate():
    """T2 — se sterg deal-urile incheiate de peste DEAL_RETENTION_DAYS (30), mai
    putin cele promovate. Promovatele raman si dupa oricat: `promoted_product_id`
    e cheie straina spre `products`, iar promovarea e decizia userului."""
    db = SessionLocal()
    try:
        produs = Product(name="Produs promovat", current_price=99.0)
        db.add(produs)
        db.flush()

        _deal(db, "vechi_nou", incheiat_acum_zile=40, stare="nou")
        _deal(db, "vechi_ignorat", incheiat_acum_zile=40, stare="ignorat")
        _deal(db, "vechi_promovat", incheiat_acum_zile=40, stare="promovat",
              produs_id=produs.id)
        _deal(db, "recent_incheiat", incheiat_acum_zile=10, stare="nou")
        db.commit()

        rezultat = run_deal_cleanup(db)

        # Niciun rand activ, deci garda de stale n-are ce inchide.
        assert rezultat["stale_inchise"] == 0
        assert rezultat["sterse"] == 2
        assert set(_stari(db)) == {"vechi_promovat", "recent_incheiat"}
        # Produsul promovat n-a fost atins de stergere.
        assert db.query(Product).count() == 1
    finally:
        db.close()


def test_pragul_de_stale_vine_din_mediu(monkeypatch):
    """T3 — pragurile sunt constante de modul, citite la fiecare rulare: cu
    DEAL_STALE_DAYS=1, un activ nevazut de doua zile se inchide, desi cu
    implicitul de 3 ar fi ramas activ."""
    db = SessionLocal()
    try:
        _deal(db, "de_doua_zile", vazut_acum_zile=2)
        db.commit()

        # Control cu implicitul (3 zile): nu se intampla nimic. Fara el, testul
        # ar dovedi doar ca randul se inchide cumva, nu ca pragul e cel care
        # decide.
        assert run_deal_cleanup(db)["stale_inchise"] == 0
        assert _stari(db)["de_doua_zile"] is None

        monkeypatch.setattr(deal_retention, "DEAL_STALE_DAYS", 1)
        assert run_deal_cleanup(db)["stale_inchise"] == 1
        assert _stari(db)["de_doua_zile"] is not None
    finally:
        db.close()


# ── D4a: memoria de pret prea veche ─────────────────────────────────────────

def _memorie(db, ext, *, vazuta_acum_zile, domeniu=DOM):
    db.add(ShopPriceMemory(
        shop_domain=domeniu, external_id=ext, min_price=10.0, last_price=10.0,
        last_seen_at=_acum() - timedelta(days=vazuta_acum_zile)))


def test_d4a_memoria_veche_se_sterge_cea_recenta_ramane():
    """T4 — peste DEAL_MEMORY_DAYS (90) memoria nu mai e o referinta utila: pretul
    de acum trei luni nu spune nimic despre magazinul de azi. Sub prag ramane
    neatinsa, altfel R2 ar pierde minime inca valide."""
    db = SessionLocal()
    try:
        for ext in ("veche1", "veche2", "veche3"):
            _memorie(db, ext, vazuta_acum_zile=100)
        for ext in ("recenta1", "recenta2"):
            _memorie(db, ext, vazuta_acum_zile=10)
        db.commit()

        rezultat = run_deal_cleanup(db)

        assert rezultat["memorie_sterse"] == 3
        ramase = {m.external_id for m in db.query(ShopPriceMemory).all()}
        assert ramase == {"recenta1", "recenta2"}
    finally:
        db.close()


# ── D4b: domeniile scoase din registru ──────────────────────────────────────

def test_d4b_domeniile_orfane_se_curata_din_toate_tabelele(monkeypatch):
    """T5 — lectia caliroots. Un domeniu scos din registru nu mai e scanat niciodata,
    deci nimeni nu-i mai scrie `ended_at` si nimeni nu-i mai curata memoria.

    Doua exceptii, amandoua deliberate: deal-ul PROMOVAT ramane (cheie straina spre
    `products` plus decizia userului), si cel `refresh_diff` ramane fiindca acolo
    `shop_domain` vine din `ps.source` si poate sa nu fie deloc un domeniu de
    registru — l-am fi sters ca orfan desi e valid.
    """
    monkeypatch.setattr("app.services.shop_registry.SHOP_REGISTRY",
                        {"a.ro": {"label": "A", "category": "test"}})
    db = SessionLocal()
    try:
        produs = Product(name="Promovat", current_price=9.0)
        db.add(produs)
        db.flush()

        # Domeniu CUNOSCUT: nimic nu trebuie atins. Domeniul se da la CREARE, nu
        # printr-un UPDATE ulterior: cu `autoflush=False`, un update in masa nu vede
        # randul inca neflushuit, iar deal-ul ar fi ramas pe DOM si ar fi facut si
        # domeniul ALA orfan fata de registrul monkeypatch-uit.
        _deal(db, "a_activ", stare="nou", domeniu="a.ro")
        _memorie(db, "a_mem", vazuta_acum_zile=1, domeniu="a.ro")
        db.add(ShopScanState(shop_domain="a.ro", last_status="ok"))

        # Domeniu ORFAN, cu cele trei feluri de deal-uri.
        for ext, stare, sursa, pid in (("v_nou", "nou", "shopify_enum", None),
                                       ("v_promovat", "promovat", "shopify_enum", produs.id),
                                       ("v_refresh", "nou", "refresh_diff", None)):
            db.add(Deal(shop_domain="vechi.ro", external_id=ext, title=ext,
                        url=f"https://vechi.ro/{ext}", currency="EUR", price=10.0,
                        discount_pct=30.0, reason="compare_at", state=stare,
                        deal_source=sursa, promoted_product_id=pid,
                        first_seen_at=_acum(), last_seen_at=_acum()))
        _memorie(db, "v_mem", vazuta_acum_zile=1, domeniu="vechi.ro")
        db.add(ShopScanState(shop_domain="vechi.ro", last_status="ok"))
        db.commit()

        rezultat = run_deal_cleanup(db)

        assert rezultat["orfane"] == ["vechi.ro"], "doar domeniul absent din registru"
        assert rezultat["orfane_deals"] == 1        # doar `v_nou`
        assert rezultat["orfane_mem"] == 1
        assert rezultat["orfane_state"] == 1

        ramase = {(d.shop_domain, d.external_id) for d in db.query(Deal).all()}
        assert ("vechi.ro", "v_nou") not in ramase
        assert ("vechi.ro", "v_promovat") in ramase, "promovatul nu se sterge"
        assert ("vechi.ro", "v_refresh") in ramase, "refresh_diff nu se atinge"
        assert ("a.ro", "a_activ") in ramase, "domeniul din registru e neatins"

        assert db.query(ShopPriceMemory).filter(
            ShopPriceMemory.shop_domain == "vechi.ro").count() == 0
        assert db.query(ShopPriceMemory).filter(
            ShopPriceMemory.shop_domain == "a.ro").count() == 1
        assert db.query(ShopScanState).filter(
            ShopScanState.shop_domain == "vechi.ro").count() == 0
        assert db.query(ShopScanState).filter(
            ShopScanState.shop_domain == "a.ro").count() == 1
    finally:
        db.close()


def test_d4b_fara_orfane_nu_se_sterge_nimic(monkeypatch):
    """T6 — cand toate domeniile sunt in registru, pasul e un no-op. Contorul zero e
    la fel de important ca cel nenul: un `orfane` care iese nevid pe o baza sanatoasa
    ar insemna ca stergem randuri bune."""
    monkeypatch.setattr("app.services.shop_registry.SHOP_REGISTRY",
                        {DOM: {"label": "Test", "category": "test"}})
    db = SessionLocal()
    try:
        _deal(db, "p1", stare="nou")
        _memorie(db, "m1", vazuta_acum_zile=1)
        db.add(ShopScanState(shop_domain=DOM, last_status="ok"))
        db.commit()

        rezultat = run_deal_cleanup(db)

        assert rezultat["orfane"] == []
        assert rezultat["orfane_deals"] == 0
        assert rezultat["orfane_mem"] == 0
        assert rezultat["orfane_state"] == 0
        assert db.query(Deal).count() == 1
        assert db.query(ShopPriceMemory).count() == 1
        assert db.query(ShopScanState).count() == 1
    finally:
        db.close()


def test_d4_contractul_de_retur(monkeypatch):
    """Forma COMPLETA a dict-ului intors, intr-un singur loc. Celelalte teste verifica
    doar cheile care le privesc, ca sa nu pice toate cand se adauga un pas nou."""
    monkeypatch.setattr("app.services.shop_registry.SHOP_REGISTRY",
                        {DOM: {"label": "Test", "category": "test"}})
    db = SessionLocal()
    try:
        rezultat = run_deal_cleanup(db)
    finally:
        db.close()

    assert rezultat == {"stale_inchise": 0, "sterse": 0, "memorie_sterse": 0,
                        "orfane_deals": 0, "orfane_mem": 0, "orfane_state": 0,
                        "orfane": []}
