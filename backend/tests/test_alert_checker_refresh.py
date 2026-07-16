"""C-17 — last_checked_at se persista si in ciclurile FARA schimbari de pret.

Bug-ul: _refresh_all_scrapeable_products seta ps.last_checked_at pe toate sursele,
dar comitea doar `if refreshed > 0 or touched_products` — intr-un ciclu in care
toate preturile raman identice, sesiunea se inchidea fara commit si timestamp-ul
se pierdea (UI-ul "Verificat: ..." ramanea inghetat). Testul ruleaza refresh-ul
pe o sesiune SEPARATA, o inchide, si verifica persistenta dintr-o sesiune noua.
"""
from app.database import SessionLocal
from app.models.product import Product
from app.models.product_source import ProductSource
from app.services import catalog_health_watchdog
from app.utils.alert_checker import _refresh_all_scrapeable_products


def test_last_checked_at_persistat_cand_pretul_nu_se_schimba(monkeypatch):
    catalog_health_watchdog._reset_state()
    # Pret identic cu cel stocat -> refreshed=0, touched_products gol.
    monkeypatch.setattr("app.utils.alert_checker.refresh_price_from_source",
                        lambda **kw: 100.0)

    db = SessionLocal()
    try:
        p = Product(name="C17 produs", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro",
                             source_url="https://www.emag.ro/c17-produs/pd/X/",
                             current_price=100.0, currency="RON",
                             last_checked_at=None))
        db.commit()
        source_id = db.query(ProductSource).filter(
            ProductSource.product_id == p.id).one().id
    finally:
        db.close()

    work = SessionLocal()
    try:
        _refresh_all_scrapeable_products(work)
    finally:
        work.close()

    check = SessionLocal()
    try:
        ps = check.query(ProductSource).filter(ProductSource.id == source_id).one()
        assert ps.last_checked_at is not None, (
            "last_checked_at NU a fost persistat intr-un ciclu fara schimbari de pret"
        )
    finally:
        check.close()
