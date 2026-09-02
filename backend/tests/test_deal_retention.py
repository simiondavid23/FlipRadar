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
from app.services import deal_retention
from app.services.deal_retention import run_deal_cleanup

DOM = "asphaltgold.com"          # intrare reala in registru, ca in test_deal_scanner


def _acum():
    return datetime.now(timezone.utc)


def _deal(db, ext, *, vazut_acum_zile=0, incheiat_acum_zile=None,
          stare="nou", produs_id=None):
    """Un rand de deal cu varsta ceruta. `incheiat_acum_zile=None` inseamna ACTIV."""
    acum = _acum()
    db.add(Deal(
        shop_domain=DOM, external_id=ext, title=ext.upper(),
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

        assert rezultat == {"stale_inchise": 3, "sterse": 0}
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
        assert rezultat == {"stale_inchise": 0, "sterse": 2}
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
