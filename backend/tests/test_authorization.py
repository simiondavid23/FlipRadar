"""AN-1 — suita sistematica de autorizare (IDOR / acces cross-user).

DE CE EXISTA. Odata cu stergerea dashboard-ului de admin a disparut si singurul
gard de rol din aplicatie; ce a ramas sunt garduri de autorizare per-endpoint
(fiecare handler filtreaza resursa dupa `user_id == current_user.id`). Nimic nu
garanta insa ca *toate* endpointurile cu ID chiar fac asta, si nimic nu impiedica
adaugarea unui endpoint nou cu ID fara verificare de ownership. Acest fisier:

  1. Dovedeste — pentru FIECARE endpoint cu parametru de path din aplicatie — ca
     userul B nu poate atinge resursa userului A (raspuns 403/404, niciodata 200
     cu datele lui A, niciodata 500).
  2. Are un GARDIAN (`test_authorization_table_covers_all_id_endpoints`) care pica
     daca cineva monteaza un endpoint cu ID nou fara sa-l treaca prin tabelul de
     mai jos — imposibil sa adaugi o ruta cu ID fara test de autorizare.

STRUCTURA
  - fixture `two_users`         : doi clienti autentificati independent (A, B),
                                  ambii cu toate flag-urile can_use_* = True (altfel
                                  un 403 de feature-gate ar masca ownership-ul).
  - RESOURCE_FACTORIES          : per tip de resursa, o functie care insereaza prin
                                  ORM un rand minim-valid DETINUT de un user si
                                  intoarce lista de ID-uri din path.
  - ENDPOINTS                   : (method, path, resource, body, cross_user_expected)
                                  pentru TOATE endpointurile cu ID (enumerate din cod).
  - test_cross_user_access_denied         : A creeaza, B acceseaza -> 403/404.
  - test_unauthenticated_denied           : client fara token -> 401/403.
  - test_owner_can_access                 : A pe propria resursa (GET-uri pure-DB) -> 200.
  - test_impact_endpoints_no_cross_user_leak / test_tracked_delete_is_user_scoped_noop:
        dovada POZITIVA ca cele 4 endpointuri care raspund legitim 200 (cele 3
        `.../impact` + bulk-delete-ul scoped-pe-user de la tracked-products) NU scurg
        datele lui A — un IDOR aici ar aparea ca o valoare non-zero pentru B.
  - test_authorization_table_covers_all_id_endpoints : gardianul de acoperire.

Nota anti-fals-verde: daca un request cross-user primeste 422, testul pica EXPLICIT
cu mesaj — un 422 inseamna ca body-ul din tabel e invalid si requestul nici n-a
ajuns la verificarea de autorizare (ar da un verde inselator).
"""
import re
import uuid
from contextlib import contextmanager

import pytest

# conftest.py a setat deja DATABASE_URL pe baza de test + FLIPRADAR_TESTING inainte
# de orice import din `app`; importul de aici doar inregistreaza modelele + rutele.
import app.main  # noqa: F401  (efect secundar: mapeaza toate modelele si monteaza rutele)
from app.main import app
from app.database import Base, SessionLocal


# ── Rezolvarea claselor de model dupa nume (fara a ghici caile de import) ─────────
def _model(name):
    for m in Base.registry.mappers:
        if m.class_.__name__ == name:
            return m.class_
    raise LookupError(f"Modelul {name!r} nu a fost gasit in registry")


Alert = _model("Alert")
InventoryItem = _model("InventoryItem")
Sale = _model("Sale")
Product = _model("Product")
ProductSourceSuggestion = _model("ProductSourceSuggestion")
TrackedProduct = _model("TrackedProduct")
MarketplaceKeywordAlert = _model("MarketplaceKeywordAlert")
MarketplaceSaved = _model("MarketplaceSaved")
AutoFeedListing = _model("AutoFeedListing")
AutoKeyword = _model("AutoKeyword")
AutoLot = _model("AutoLot")
AutoLotKeyword = _model("AutoLotKeyword")
AutoListing = _model("AutoListing")
FacebookGroupConfig = _model("FacebookGroupConfig")
RadarKeyword = _model("RadarKeyword")
RadarListing = _model("RadarListing")
RadarMessageTemplate = _model("RadarMessageTemplate")
RealEstateMonitorKeyword = _model("RealEstateMonitorKeyword")
RealEstateMonitorListing = _model("RealEstateMonitorListing")
RealEstateListing = _model("RealEstateListing")  # tabelul vechi (deprecat), /real-estate/saved

_NAME = "AN1-authz"


@contextmanager
def _session():
    """Sesiune ORM scurta care face commit la iesire normala (rollback pe exceptie)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Fixture: doi useri autentificati independent ─────────────────────────────────
@pytest.fixture
def two_users():
    """(clientA, clientB, userA_id, userB_id) — doi clienti cu jar-uri de cookie
    separate, fiecare logat ca un user distinct. Ambii primesc toate flag-urile
    can_use_* = True: altfel un feature-gate (403) ar masca verificarea de ownership
    si testul ar deveni fals-verde. Modelat pe fixture-ul `auth_client` din conftest,
    dublat cu al doilea client (nu putem avea doi useri intr-un singur cookie jar)."""
    from fastapi.testclient import TestClient

    def _register(client):
        uniq = uuid.uuid4().hex[:12]
        payload = {
            "email": f"authz_{uniq}@example.com",
            "username": f"authz_{uniq}",
            "password": "testpass123",
            "full_name": "Authz Test",
            "security_question": "Care e culoarea preferata?",
            "security_answer": "albastru",
        }
        r = client.post("/api/auth/register", json=payload)
        assert r.status_code == 200, f"register a esuat: {r.status_code} {r.text}"
        r = client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert r.status_code == 200, f"login a esuat: {r.status_code} {r.text}"
        return payload["email"]

    client_a, client_b = TestClient(app), TestClient(app)
    email_a, email_b = _register(client_a), _register(client_b)

    with _session() as db:
        user_a = db.query(_model("User")).filter_by(email=email_a).first()
        user_b = db.query(_model("User")).filter_by(email=email_b).first()
        for u in (user_a, user_b):
            # Toate feature-gate-urile pornite ca sa nu mascheze ownership-ul cu un 403.
            u.can_use_ai = True
            u.can_use_scraping = True
            u.can_use_alerts = True
            u.can_use_import_export = True
        id_a, id_b = user_a.id, user_b.id
    return client_a, client_b, id_a, id_b


# ── RESOURCE_FACTORIES: creeaza un rand minim-valid DETINUT de `uid` ─────────────
# Fiecare intoarce lista de ID-uri care umplu, in ordine, placeholderele din path.
# Coloanele nullable=False fara default sunt setate explicit (citite din model, nu
# ghicite); parintii cu FK obligatoriu (Product pentru Alert/Tracked/Suggestion,
# RadarKeyword pentru RadarListing) se creeaza si ei, ca randul sa fie realmente valid.

def _f_alert(uid):
    with _session() as db:
        p = Product(user_id=uid, name=_NAME); db.add(p); db.flush()
        a = Alert(user_id=uid, product_id=p.id, target_price=1.0); db.add(a); db.flush()
        return [a.id]


def _f_inventory(uid):
    with _session() as db:
        it = InventoryItem(user_id=uid, name=_NAME, purchase_price=1.0)
        db.add(it); db.flush()
        return [it.id]


def _f_sale(uid):
    with _session() as db:
        s = Sale(user_id=uid, product_name=_NAME, sale_price=1.0); db.add(s); db.flush()
        return [s.id]


def _f_product(uid):
    with _session() as db:
        p = Product(user_id=uid, name=_NAME); db.add(p); db.flush()
        return [p.id]


def _f_product_suggestion(uid):
    with _session() as db:
        p = Product(user_id=uid, name=_NAME); db.add(p); db.flush()
        sg = ProductSourceSuggestion(product_id=p.id, source="olx", source_url="http://x")
        db.add(sg); db.flush()
        return [p.id, sg.id]


def _f_tracked_product(uid):
    # Path-ul e Product.id (FK-ul TrackedProduct.product_id), nu TrackedProduct.id.
    with _session() as db:
        p = Product(user_id=uid, name=_NAME); db.add(p); db.flush()
        db.add(TrackedProduct(user_id=uid, product_id=p.id))
        return [p.id]


def _f_mkt_keyword_alert(uid):
    with _session() as db:
        a = MarketplaceKeywordAlert(user_id=uid); db.add(a); db.flush()
        return [a.id]


def _f_mkt_saved(uid):
    with _session() as db:
        s = MarketplaceSaved(user_id=uid); db.add(s); db.flush()
        return [s.id]


def _f_auto_feed_listing(uid):
    with _session() as db:
        li = AutoFeedListing(user_id=uid, platform="olx"); db.add(li); db.flush()
        return [li.id]


def _f_auto_keyword(uid):
    with _session() as db:
        kw = AutoKeyword(user_id=uid, name=_NAME, platform="olx"); db.add(kw); db.flush()
        return [kw.id]


def _f_auto_lot(uid):
    with _session() as db:
        lot = AutoLot(user_id=uid); db.add(lot); db.flush()
        return [lot.id]


def _f_auto_lot_keyword(uid):
    with _session() as db:
        kw = AutoLotKeyword(user_id=uid, name=_NAME, platform="copart")
        db.add(kw); db.flush()
        return [kw.id]


def _f_auto_saved_listing(uid):
    with _session() as db:
        li = AutoListing(user_id=uid); db.add(li); db.flush()
        return [li.id]


def _f_facebook_config(uid):
    with _session() as db:
        cfg = FacebookGroupConfig(user_id=uid, group_name=_NAME, group_url="http://x")
        db.add(cfg); db.flush()
        return [cfg.id]


def _f_radar_keyword(uid):
    with _session() as db:
        kw = RadarKeyword(user_id=uid, name=_NAME, max_price=1.0, resale_price=1.0)
        db.add(kw); db.flush()
        return [kw.id]


def _f_radar_listing(uid):
    with _session() as db:
        kw = RadarKeyword(user_id=uid, name=_NAME, max_price=1.0, resale_price=1.0)
        db.add(kw); db.flush()
        li = RadarListing(user_id=uid, keyword_id=kw.id, external_id="e1",
                          platform="olx", title=_NAME, price=1.0, url="http://x")
        db.add(li); db.flush()
        return [li.id]


def _f_radar_template(uid):
    with _session() as db:
        t = RadarMessageTemplate(user_id=uid, name=_NAME, template_text="salut {titlu}")
        db.add(t); db.flush()
        return [t.id]


def _f_re_monitor_listing(uid):
    with _session() as db:
        li = RealEstateMonitorListing(user_id=uid, platform="olx"); db.add(li); db.flush()
        return [li.id]


def _f_re_monitor_keyword(uid):
    with _session() as db:
        kw = RealEstateMonitorKeyword(user_id=uid, name=_NAME, platform="olx")
        db.add(kw); db.flush()
        return [kw.id]


def _f_re_saved_listing(uid):
    with _session() as db:
        li = RealEstateListing(user_id=uid); db.add(li); db.flush()
        return [li.id]


RESOURCE_FACTORIES = {
    "alert": _f_alert,
    "inventory": _f_inventory,
    "sale": _f_sale,
    "product": _f_product,
    "product_suggestion": _f_product_suggestion,
    "tracked_product": _f_tracked_product,
    "mkt_keyword_alert": _f_mkt_keyword_alert,
    "mkt_saved": _f_mkt_saved,
    "auto_feed_listing": _f_auto_feed_listing,
    "auto_keyword": _f_auto_keyword,
    "auto_lot": _f_auto_lot,
    "auto_lot_keyword": _f_auto_lot_keyword,
    "auto_saved_listing": _f_auto_saved_listing,
    "facebook_config": _f_facebook_config,
    "radar_keyword": _f_radar_keyword,
    "radar_listing": _f_radar_listing,
    "radar_template": _f_radar_template,
    "re_monitor_listing": _f_re_monitor_listing,
    "re_monitor_keyword": _f_re_monitor_keyword,
    "re_saved_listing": _f_re_saved_listing,
}


# ── ENDPOINTS: (method, path, resource, body, cross_user_expected) ───────────────
# `path` = string-ul EXACT al rutei (asa cum apare in app.routes; gardianul compara
# pe egalitate). `body` = JSON minim-valid ca requestul sa treaca de validarea
# Pydantic si sa AJUNGA la verificarea de ownership (None = fara body). `expected` =
# statusuri acceptabile pentru un request cross-user.
DENIED = frozenset({403, 404})            # cazul normal: resursa lui A e invizibila lui B
# 4 endpointuri raspund legitim 200 la un ID strain FARA a scurge date: cele 3
# `.../impact` nu incarca niciodata keyword-ul (numara doar randurile
# APELANTULUI), iar DELETE /tracked-products/{id} e un bulk-delete scoped pe user
# (no-op cand nu detii). Dovada ca nu scurg nimic e in testele dedicate mai jos.
SAFE_200 = frozenset({200})

ENDPOINTS = [
    # ── alerts ──
    ("DELETE", "/api/alerts/{alert_id}", "alert", None, DENIED),
    ("PUT", "/api/alerts/{alert_id}/toggle", "alert", None, DENIED),
    # ── auto-listings (feed + keywords) ──
    ("DELETE", "/api/auto-listings/feed/{listing_id}", "auto_feed_listing", None, DENIED),
    ("GET", "/api/auto-listings/feed/{listing_id}/detail", "auto_feed_listing", None, DENIED),
    ("POST", "/api/auto-listings/feed/{listing_id}/generate-review", "auto_feed_listing", None, DENIED),
    ("POST", "/api/auto-listings/feed/{listing_id}/render-template", "auto_feed_listing", {"template_id": 1}, DENIED),
    ("PATCH", "/api/auto-listings/feed/{listing_id}/status", "auto_feed_listing", {"status": "saved"}, DENIED),
    ("GET", "/api/auto-listings/keywords/{keyword_id}/impact", "auto_keyword", None, SAFE_200),
    ("DELETE", "/api/auto-listings/keywords/{kw_id}", "auto_keyword", None, DENIED),
    ("PUT", "/api/auto-listings/keywords/{kw_id}", "auto_keyword", {"name": "x", "platform": "olx"}, DENIED),
    # ── auto-lots (feed + keywords) ──
    ("PATCH", "/api/auto-lots/feed/{lot_id}/status", "auto_lot", {"status": "saved"}, DENIED),
    ("DELETE", "/api/auto-lots/keywords/{kw_id}", "auto_lot_keyword", None, DENIED),
    ("PUT", "/api/auto-lots/keywords/{kw_id}", "auto_lot_keyword", {"name": "x", "platform": "copart"}, DENIED),
    # ── auto (saved, tabele vechi) ──
    ("DELETE", "/api/auto/listings/saved/{listing_id}", "auto_saved_listing", None, DENIED),
    ("DELETE", "/api/auto/lots/saved/{lot_id}", "auto_lot", None, DENIED),
    # ── facebook-groups ──
    ("DELETE", "/api/facebook-groups/{config_id}", "facebook_config", None, DENIED),
    ("PUT", "/api/facebook-groups/{config_id}", "facebook_config", {}, DENIED),
    ("DELETE", "/api/facebook-groups/{config_id}/cookies", "facebook_config", None, DENIED),
    ("POST", "/api/facebook-groups/{config_id}/cookies", "facebook_config", {"cookies_json": "{}"}, DENIED),
    ("GET", "/api/facebook-groups/{config_id}/posts", "facebook_config", None, DENIED),
    ("POST", "/api/facebook-groups/{config_id}/test-run", "facebook_config", None, DENIED),
    # ── inventory ──
    ("DELETE", "/api/inventory/{item_id}", "inventory", None, DENIED),
    ("PUT", "/api/inventory/{item_id}", "inventory", {}, DENIED),
    # ── marketplace ──
    ("DELETE", "/api/marketplace/keyword-alerts/{alert_id}", "mkt_keyword_alert", None, DENIED),
    ("PUT", "/api/marketplace/keyword-alerts/{alert_id}", "mkt_keyword_alert", {}, DENIED),
    ("DELETE", "/api/marketplace/saved/{saved_id}", "mkt_saved", None, DENIED),
    # ── products (+ suggestions) ──
    ("DELETE", "/api/products/{product_id}", "product", None, DENIED),
    ("GET", "/api/products/{product_id}", "product", None, DENIED),
    ("PUT", "/api/products/{product_id}", "product", {}, DENIED),
    ("POST", "/api/products/{product_id}/refresh-price", "product", None, DENIED),
    ("DELETE", "/api/products/{product_id}/suggestions/{suggestion_id}", "product_suggestion", None, DENIED),
    ("POST", "/api/products/{product_id}/suggestions/{suggestion_id}/confirm", "product_suggestion", None, DENIED),
    # ── radar keywords ──
    ("DELETE", "/api/radar/keywords/{keyword_id}", "radar_keyword", None, DENIED),
    ("PUT", "/api/radar/keywords/{keyword_id}", "radar_keyword", {}, DENIED),
    ("GET", "/api/radar/keywords/{keyword_id}/impact", "radar_keyword", None, SAFE_200),
    ("GET", "/api/radar/keywords/{keyword_id}/price-trend", "radar_keyword", None, DENIED),
    ("POST", "/api/radar/keywords/{keyword_id}/test-exclusion", "radar_keyword", {"title": "x"}, DENIED),
    ("PATCH", "/api/radar/keywords/{keyword_id}/toggle", "radar_keyword", None, DENIED),
    # ── radar listings ──
    ("DELETE", "/api/radar/listings/{listing_id}", "radar_listing", None, DENIED),
    ("GET", "/api/radar/listings/{listing_id}", "radar_listing", None, DENIED),
    ("GET", "/api/radar/listings/{listing_id}/ai-review", "radar_listing", None, DENIED),
    ("GET", "/api/radar/listings/{listing_id}/facebook-detail", "radar_listing", None, DENIED),
    ("PATCH", "/api/radar/listings/{listing_id}/status", "radar_listing", {"status": "saved"}, DENIED),
    ("GET", "/api/radar/listings/{listing_id}/vinted-detail", "radar_listing", None, DENIED),
    # ── radar templates ──
    ("DELETE", "/api/radar/templates/{template_id}", "radar_template", None, DENIED),
    ("PUT", "/api/radar/templates/{template_id}", "radar_template", {}, DENIED),
    ("POST", "/api/radar/templates/{template_id}/render", "radar_template", {"listing_id": 1}, DENIED),
    # ── real-estate-monitor (feed + keywords) ──
    ("DELETE", "/api/real-estate-monitor/feed/{listing_id}", "re_monitor_listing", None, DENIED),
    ("PATCH", "/api/real-estate-monitor/feed/{listing_id}/status", "re_monitor_listing", {"status": "saved"}, DENIED),
    ("GET", "/api/real-estate-monitor/keywords/{keyword_id}/impact", "re_monitor_keyword", None, SAFE_200),
    ("DELETE", "/api/real-estate-monitor/keywords/{kw_id}", "re_monitor_keyword", None, DENIED),
    ("PUT", "/api/real-estate-monitor/keywords/{kw_id}", "re_monitor_keyword", {"name": "x", "platform": "olx"}, DENIED),
    # ── real-estate (saved, tabel vechi) ──
    ("DELETE", "/api/real-estate/listings/saved/{listing_id}", "re_saved_listing", None, DENIED),
    # ── sales ──
    ("DELETE", "/api/sales/{sale_id}", "sale", None, DENIED),
    ("PUT", "/api/sales/{sale_id}", "sale", {}, DENIED),
    # ── tracked-products ──
    ("DELETE", "/api/tracked-products/{product_id}", "tracked_product", None, SAFE_200),
    ("PATCH", "/api/tracked-products/{product_id}/monitoring", "tracked_product", {}, DENIED),
]

_PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _fill(path, ids):
    """Umple placeholderele {..} din path, in ordine, cu ID-urile date."""
    it = iter(ids)
    return _PLACEHOLDER.sub(lambda _m: str(next(it)), path)


def _case_id(method, path):
    return f"{method} {path}"


# ── Testul principal: acces cross-user ───────────────────────────────────────────
@pytest.mark.parametrize(
    "method,path,resource,body,expected",
    ENDPOINTS,
    ids=[_case_id(m, p) for m, p, *_ in ENDPOINTS],
)
def test_cross_user_access_denied(two_users, method, path, resource, body, expected):
    """A isi creeaza resursa; B incearca sa o atinga cu ID-ul lui A -> respins."""
    client_a, client_b, id_a, id_b = two_users
    ids = RESOURCE_FACTORIES[resource](id_a)          # resursa DETINUTA de A
    url = _fill(path, ids)
    resp = client_b.request(method, url, json=body)
    status = resp.status_code

    # 422 = body invalid: requestul a picat pe validare INAINTE de gardul de
    # ownership -> verde inselator. Semnaleaza-l explicit ca sa reparam body-ul.
    assert status != 422, (
        f"{method} {url}: body invalid (422) — testul NU a ajuns la verificarea de "
        f"autorizare; corecteaza body-ul in ENDPOINTS. Raspuns: {resp.text[:300]}"
    )
    assert status != 500, f"{method} {url}: 500 (crash), nu respingere de autorizare — {resp.text[:300]}"
    assert status in expected, (
        f"{method} {url}: userul B a primit {status} pe resursa lui A "
        f"(asteptat {sorted(expected)}). Un 200 neasteptat inseamna IDOR real — "
        f"NU repara testul, raporteaza endpointul."
    )


# ── Acces neautentificat: fara token -> 401/403, inainte de orice logica ─────────
@pytest.mark.parametrize(
    "method,path,resource,body,expected",
    ENDPOINTS,
    ids=[_case_id(m, p) for m, p, *_ in ENDPOINTS],
)
def test_unauthenticated_denied(client, method, path, resource, body, expected):
    """Fara cookie/Bearer, get_current_user respinge inainte sa se atinga resursa,
    deci nici nu conteaza daca ID-ul exista."""
    url = _PLACEHOLDER.sub("1", path)
    resp = client.request(method, url, json=body)
    assert resp.status_code in (401, 403), (
        f"{method} {url}: request neautentificat a primit {resp.status_code}, "
        f"asteptat 401/403 (endpoint fara gard de autentificare?)"
    )


# ── Sanity: proprietarul CHIAR isi poate accesa resursa (altfel 404-urile de mai ─
#    sus ar putea fi 'totul da 404', nu 'ownership functioneaza'). GET-uri pure-DB. ─
OWNER_GET_CHECKS = [
    ("GET", "/api/products/{product_id}", "product"),
    ("GET", "/api/radar/listings/{listing_id}", "radar_listing"),
    ("GET", "/api/radar/keywords/{keyword_id}/price-trend", "radar_keyword"),
    ("GET", "/api/radar/keywords/{keyword_id}/impact", "radar_keyword"),
    ("GET", "/api/facebook-groups/{config_id}/posts", "facebook_config"),
    ("GET", "/api/auto-listings/keywords/{keyword_id}/impact", "auto_keyword"),
    ("GET", "/api/real-estate-monitor/keywords/{keyword_id}/impact", "re_monitor_keyword"),
]


@pytest.mark.parametrize(
    "method,path,resource",
    OWNER_GET_CHECKS,
    ids=[_case_id(m, p) for m, p, _ in OWNER_GET_CHECKS],
)
def test_owner_can_access(two_users, method, path, resource):
    """Proprietarul A pe propria resursa -> 200 (dovada ca respingerea cross-user
    e ownership real, nu un 404 generic pe orice)."""
    client_a, client_b, id_a, id_b = two_users
    ids = RESOURCE_FACTORIES[resource](id_a)
    url = _fill(path, ids)
    resp = client_a.request(method, url)
    assert resp.status_code == 200, (
        f"proprietarul A NU-si poate accesa {method} {url}: "
        f"{resp.status_code} {resp.text[:200]}"
    )


# ── Dovada pozitiva ca cele 4 endpointuri 'safe-200' NU scurg datele lui A ───────
def test_impact_endpoints_no_cross_user_leak(two_users):
    """Cele 3 `.../impact` numara doar randurile apelantului. Cu A avand 1 anunt sub
    keyword-ul lui, A vede count>=1, iar B (cu ID-ul keyword-ului lui A) trebuie sa
    vada 0 — altfel e IDOR (scurgere de volum de date intre useri)."""
    client_a, client_b, id_a, id_b = two_users

    # radar
    with _session() as db:
        kw = RadarKeyword(user_id=id_a, name=_NAME, max_price=1.0, resale_price=1.0)
        db.add(kw); db.flush()
        db.add(RadarListing(user_id=id_a, keyword_id=kw.id, external_id="e1",
                            platform="olx", title=_NAME, price=1.0, url="http://x"))
        radar_kw = kw.id
    a = client_a.get(f"/api/radar/keywords/{radar_kw}/impact").json()
    b = client_b.get(f"/api/radar/keywords/{radar_kw}/impact").json()
    assert a["listing_count"] >= 1
    assert b["listing_count"] == 0, "IDOR radar: B vede anunturile lui A prin /impact"

    # auto-listings
    with _session() as db:
        kw = AutoKeyword(user_id=id_a, name=_NAME, platform="olx"); db.add(kw); db.flush()
        db.add(AutoFeedListing(user_id=id_a, keyword_id=kw.id, platform="olx"))
        auto_kw = kw.id
    a = client_a.get(f"/api/auto-listings/keywords/{auto_kw}/impact").json()
    b = client_b.get(f"/api/auto-listings/keywords/{auto_kw}/impact").json()
    assert a["listing_count"] >= 1
    assert b["listing_count"] == 0, "IDOR auto: B vede anunturile lui A prin /impact"

    # real-estate-monitor
    with _session() as db:
        kw = RealEstateMonitorKeyword(user_id=id_a, name=_NAME, platform="olx")
        db.add(kw); db.flush()
        db.add(RealEstateMonitorListing(user_id=id_a, keyword_id=kw.id, platform="olx"))
        re_kw = kw.id
    a = client_a.get(f"/api/real-estate-monitor/keywords/{re_kw}/impact").json()
    b = client_b.get(f"/api/real-estate-monitor/keywords/{re_kw}/impact").json()
    assert a["listing_count"] >= 1
    assert b["listing_count"] == 0, "IDOR real-estate: B vede anunturile lui A prin /impact"


def test_tracked_delete_is_user_scoped_noop(two_users):
    """DELETE /tracked-products/{product_id} sterge doar randurile APELANTULUI. B il
    apeleaza cu product_id-ul lui A: raspunsul e benign, dar randul lui A trebuie sa
    supravietuiasca — altfel B a putut sterge datele lui A."""
    client_a, client_b, id_a, id_b = two_users
    with _session() as db:
        p = Product(user_id=id_a, name=_NAME); db.add(p); db.flush()
        db.add(TrackedProduct(user_id=id_a, product_id=p.id))
        pid = p.id

    resp = client_b.request("DELETE", f"/api/tracked-products/{pid}")
    assert resp.status_code != 500, resp.text[:200]

    with _session() as db:
        survived = db.query(TrackedProduct).filter(
            TrackedProduct.user_id == id_a, TrackedProduct.product_id == pid
        ).count()
    assert survived == 1, "IDOR tracked-products: B a sters produsul urmarit al lui A"


# ── GARDIANUL de acoperire ───────────────────────────────────────────────────────
def test_authorization_table_covers_all_id_endpoints():
    """Pica daca exista o ruta montata cu parametru de path care NU e in ENDPOINTS
    (endpoint nou cu ID fara test de autorizare) sau o intrare din ENDPOINTS care nu
    mai corespunde niciunei rute (test putred). Face imposibila adaugarea unei rute
    cu ID fara a-i scrie si testul de autorizare."""
    live = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if "{" not in path or not methods:
            continue
        # Exclus: catch-all-ul care serveste frontend-ul static (`serve_frontend`,
        # /{full_path:path}) — nu are resursa/ownership, prinde orice cale ne-API.
        if "{full_path:path}" in path:
            continue
        # Exclus: rutele de documentatie generate de FastAPI (/docs, /redoc,
        # /openapi.json) — in practica niciuna n-are parametru de path, dar le
        # excludem explicit ca gardianul sa nu depinda de acel detaliu.
        if path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        for m in methods:
            if m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                live.add((m, path))

    table = {(m, p) for m, p, *_ in ENDPOINTS}
    missing = live - table
    extra = table - live

    assert not missing, (
        "Endpointuri cu ID montate FARA test de autorizare (adauga-le in ENDPOINTS "
        "cu factory + body):\n" + "\n".join(f"  {m} {p}" for m, p in sorted(missing))
    )
    assert not extra, (
        "Intrari in ENDPOINTS care nu mai corespund niciunei rute (elimina-le sau "
        "corecteaza path-ul):\n" + "\n".join(f"  {m} {p}" for m, p in sorted(extra))
    )
