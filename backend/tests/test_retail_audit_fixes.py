"""RETAIL-AUDIT (5.3e) — fix-urile auditului de retail arbitrage + gaurile de
acoperire demonstrate prin mutatii care supravietuiau intregii suite.

Bug-urile reparate (fiecare cu testul lui): parserul Farmacia Tei dadea 0.0 tacut
pe orice pret >= 1000 RON; diacriticele omorau filtrul de relevanta; un pret 0
atasat devenea snapshot 0 si declansa alerta la fiecare ciclu; flash deal-ul pleca
pe surse iesite din stoc, cu moneda si link-ul ALTUI magazin; restock-ul afisa
pretul vechi; o exceptie neprevazuta pe o sursa omora tot ciclul; subdomeniile
(m.emag.ro, comenzi.farmaciatei.ro) scapau de override si de refresh.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services import catalog_health_watchdog
from app.services import scraper_service as ss
from app.services import product_page_extractor as ppe
from app.routers.products import attach_source_to_product
from app.utils.alert_checker import _refresh_all_scrapeable_products, check_alerts

URL_A = "https://www.emag.ro/produs-audit/pd/AAA/"
URL_B = "https://altex.ro/produs-audit/cpd/BBB/"


@pytest.fixture(autouse=True)
def _clean_watchdog():
    catalog_health_watchdog._reset_state()


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr("app.utils.alert_checker.send_price_alert_notification",
                        lambda embed, settings, listing_id: calls.append((embed, listing_id)) or True)
    return calls


def _mk_user(db):
    uniq = uuid.uuid4().hex[:10]
    user = User(email=f"ra_{uniq}@example.com", username=f"ra_{uniq}", hashed_password="x")
    db.add(user)
    db.flush()
    db.add(RadarSettings(user_id=user.id,
                         discord_webhook_alerts="https://discord.com/api/webhooks/t/t"))
    return user


def _mk_product(db, user, price=200.0, currency="RON", source="emag.ro", url=URL_A,
                in_stock=True):
    prod = Product(user_id=user.id, name=f"Produs audit {uuid.uuid4().hex[:6]}",
                   current_price=price, currency=currency, source=source, source_url=url)
    db.add(prod)
    db.flush()
    ps = ProductSource(product_id=prod.id, source=source, source_url=url,
                       current_price=price, currency=currency, in_stock=in_stock)
    db.add(ps)
    db.commit()
    return prod, ps


# ── parserul Farmacia Tei: punctul e separator de MII ────────────────────────────

def test_farmaciatei_pret_cu_mii():
    assert ss._parse_farmaciatei_price("1.299,00 LEI") == 1299.0
    assert ss._parse_farmaciatei_price("1.049,50 LEI") == 1049.5


def test_farmaciatei_pret_simplu_neschimbat():
    assert ss._parse_farmaciatei_price("29,00 LEI") == 29.0
    assert ss._parse_farmaciatei_price("299,00 LEI") == 299.0
    assert ss._parse_farmaciatei_price("") == 0.0


# ── diacritice in filtrul de relevanta ───────────────────────────────────────────

def test_relevanta_query_cu_diacritice_gaseste_nume_fara():
    prods = [{"name": "Casti gaming HyperX Cloud II", "price": 300}]
    assert ss.filter_by_relevance(prods, "căști gaming") == prods


def test_relevanta_nume_cu_diacritice_gasit_de_query_fara():
    prods = [{"name": "Căști fără fir Șmecher Țipător", "price": 100}]
    assert ss.filter_by_relevance(prods, "casti smecher tipator") == prods


def test_relevanta_tot_nu_potriveste_ce_nu_trebuie():
    prods = [{"name": "Mouse gaming", "price": 50}]
    out = ss.filter_by_relevance(prods, "căști gaming")
    assert out and "message" in out[0]


# ── filter_by_code: campul poate veni lista ──────────────────────────────────────

def test_filter_by_code_ean_lista_nu_arunca():
    prods = [{"name": "X", "ean": ["5901234123457"], "price": 10}]
    assert ss.filter_by_code(prods, "5901234123457", "ean") == prods


# ── garda price > 0 la atasare ───────────────────────────────────────────────────

def test_atasarea_cu_pret_zero_nu_scrie_pret_si_nu_strica_snapshotul():
    db = SessionLocal()
    try:
        user = _mk_user(db)
        prod, _ = _mk_product(db, user, price=200.0)
        attach_source_to_product(db, prod, "altex.ro", URL_B, price=0.0, currency="RON")
        db.refresh(prod)
        ps_b = next(s for s in prod.sources if s.source == "altex.ro")
        assert ps_b.current_price is None          # sursa exista, pretul nu
        assert prod.current_price == 200.0         # snapshot-ul NU a devenit 0
        zero_rows = db.query(PriceHistory).filter(
            PriceHistory.product_id == prod.id, PriceHistory.price <= 0).count()
        assert zero_rows == 0
    finally:
        db.close()


# ── flash deal: doar in stoc, cu moneda si link-ul SURSEI ────────────────────────

def _stub_refresh(monkeypatch, result):
    monkeypatch.setattr("app.utils.alert_checker.refresh_source", lambda **kw: result)


def test_flash_deal_nu_pleaca_pe_sursa_iesita_din_stoc(monkeypatch, sent):
    db = SessionLocal()
    try:
        user = _mk_user(db)
        _mk_product(db, user, price=200.0, in_stock=True)
        db.commit()
        # Scaderea vine IMPREUNA cu iesirea din stoc — artefactul agregatului de
        # marimi (toate epuizate -> minim global). Nu e o oferta cumparabila.
        _stub_refresh(monkeypatch, {"price": 100.0, "in_stock": False, "method": "url"})
        _refresh_all_scrapeable_products(db)
        assert [lid for _, lid in sent if lid.startswith("flashdeal-")] == []
    finally:
        db.close()


def test_flash_deal_foloseste_moneda_si_linkul_sursei(monkeypatch, sent):
    db = SessionLocal()
    try:
        user = _mk_user(db)
        # Snapshot-ul primar e pe emag/RON; sursa care scade e in EUR, pe alt URL.
        prod, _ = _mk_product(db, user, price=90.0, currency="RON",
                              source="emag.ro", url=URL_A)
        eur_url = "https://www.bstn.com/eu_en/produs-audit"
        db.add(ProductSource(product_id=prod.id, source="bstn.com", source_url=eur_url,
                             current_price=100.0, currency="EUR", in_stock=True))
        db.commit()
        captured = {}

        def _embed(**kw):
            captured.update(kw)
            return {"title": "fd"}

        monkeypatch.setattr("app.utils.alert_checker.build_flash_deal_embed", _embed)

        def _refresh(**kw):
            if kw["source_url"] == eur_url:
                return {"price": 60.0, "in_stock": True, "method": "url"}
            return {"price": 90.0, "in_stock": True, "method": "url"}

        monkeypatch.setattr("app.utils.alert_checker.refresh_source", _refresh)
        _refresh_all_scrapeable_products(db)
        assert captured["currency"] == "EUR"            # moneda SURSEI, nu RON
        assert captured["product_url"] == eur_url       # link-ul SURSEI care a scazut
    finally:
        db.close()


# ── restock cu pretul NOU ────────────────────────────────────────────────────────

def test_restock_afiseaza_pretul_nou(monkeypatch, sent):
    db = SessionLocal()
    try:
        user = _mk_user(db)
        _mk_product(db, user, price=100.0, in_stock=False)
        db.commit()
        captured = {}

        def _embed(**kw):
            captured.update(kw)
            return {"title": "rs"}

        monkeypatch.setattr("app.utils.alert_checker.build_restock_embed", _embed)
        _stub_refresh(monkeypatch, {"price": 80.0, "in_stock": True, "method": "url"})
        _refresh_all_scrapeable_products(db)
        assert captured["price"] == 80.0                # nu 100.0 (cel vechi)
    finally:
        db.close()


# ── o exceptie pe o sursa nu opreste ciclul ──────────────────────────────────────

def test_exceptia_pe_o_sursa_nu_opreste_ciclul(monkeypatch):
    db = SessionLocal()
    try:
        user = _mk_user(db)
        prod_a, ps_a = _mk_product(db, user, price=100.0, source="emag.ro", url=URL_A)
        prod_b, ps_b = _mk_product(db, user, price=100.0, source="altex.ro", url=URL_B)
        db.commit()

        def _refresh(**kw):
            if kw["source_url"] == URL_A:
                raise RuntimeError("sursa otravita")
            return {"price": 90.0, "in_stock": True, "method": "url"}

        monkeypatch.setattr("app.utils.alert_checker.refresh_source", _refresh)
        refreshed, _ = _refresh_all_scrapeable_products(db)
        db.refresh(ps_b)
        assert refreshed == 1                           # B a fost procesat
        assert ps_b.current_price == 90.0               # in ciuda exploziei pe A
    finally:
        db.close()


# ── alerta deja declansata NU re-trage (gaura M4 din audit) ──────────────────────

def test_alerta_declansata_nu_se_redeclanseaza(monkeypatch, sent):
    db = SessionLocal()
    try:
        user = _mk_user(db)
        prod, _ = _mk_product(db, user, price=50.0)     # sub tinta
        db.add(Alert(user_id=user.id, product_id=prod.id, target_price=100.0,
                     currency="RON", is_active=True, is_triggered=True))
        db.commit()
        _stub_refresh(monkeypatch, {"price": 50.0, "in_stock": True, "method": "url"})
        assert check_alerts() == 0                      # nimic re-declansat
        assert [lid for _, lid in sent if lid.startswith("alert-")] == []
    finally:
        db.close()


# ── subdomenii: override, refresh si granita pe punct ────────────────────────────

def test_match_shop_domain_granita_pe_punct():
    assert ppe.match_shop_domain("m.emag.ro", ppe.VALIDATED_DOMAINS) == "emag.ro"
    assert ppe.match_shop_domain("www.emag.ro", ppe.VALIDATED_DOMAINS) == "emag.ro"
    # sufix inselator: NU se potriveste (granita e punctul)
    assert ppe.match_shop_domain("evilcel.ro", ppe.VALIDATED_DOMAINS) is None
    # intrarea CU subdomeniu ramane fail-closed pentru parintele gol
    assert ppe.match_shop_domain("afew-store.com", ppe.VALIDATED_DOMAINS) is None
    assert ppe.match_shop_domain("en.afew-store.com", ppe.VALIDATED_DOMAINS) == "en.afew-store.com"


def test_subdomeniul_emag_primeste_override(monkeypatch):
    # Pagina multi-oferta: JSON-LD poarta oferta principala (5689.42), afisat e
    # 3459.99 — fara override pe m.emag.ro s-ar salva tacut pretul gresit.
    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "Product", "name": "Laptop Lenovo", '
        '"offers": {"@type": "Offer", "price": "5689.42", "priceCurrency": "RON"}}'
        '</script></head><body>'
        '<p class="product-new-price">3.459<sup>,99</sup> <span>Lei</span></p>'
        '</body></html>'
    )
    out = ppe.parse_product_html(html, "https://m.emag.ro/produs/pd/XYZ/")
    assert out["price"] == 3459.99


def test_refresh_source_cu_subdomeniu_validat_merge_pe_extractor(monkeypatch):
    calls = []
    monkeypatch.setattr(ss, "extract_product",
                        lambda url, max_retries=3: (calls.append(url),
                                                    {"price": 42.0, "in_stock": True,
                                                     "variants": None})[1])
    res = ss.refresh_source(source="m.emag.ro", source_url="https://m.emag.ro/p/pd/X/",
                            product_name="Produs")
    assert res == {"price": 42.0, "in_stock": True, "method": "url"}
    assert len(calls) == 1


def test_allowlist_respinge_sufixul_fara_punct():
    # Pinuiaza invariantul granitei-punct din _is_allowed_shop_url: mutatia
    # endswith(domain) fara punct ar accepta "evilcel.ro".
    assert ss._is_allowed_shop_url("https://evilcel.ro/produs") is False
    assert ss._is_allowed_shop_url("https://sub.cel.ro/produs") is True
