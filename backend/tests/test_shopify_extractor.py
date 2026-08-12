"""SHOP-1 — extractorul generic Shopify (endpoint-ul Ajax /products/<handle>.js).

Toate testele sunt OFFLINE: payload-uri sintetice inline, iar `_fetch_text_guarded`
e monkeypatch-uit. Formele folosite aici sunt cele MASURATE la sonda SHOP-1a pe 39
de produse reale (pret int in unitati minore, `available` boolean per varianta,
`title` de varianta care concateneaza optiunile, "Default Title" pentru produsele
fara optiuni).
"""
import json

import pytest

from app.services import product_page_extractor as ppe
from app.services.product_page_extractor import ProductExtractionError

# Domenii REALE din registru, ca testele sa pinuiasca si legatura cu el.
DOM_EUR = "asphaltgold.com"
DOM_RON = "redgoblin.ro"
DOM_JSONLD = "altex.ro"


def _v(titlu, pret, disponibil=True):
    """Varianta in forma Ajax: pretul e int in bani, `title` concateneaza optiunile."""
    return {"title": titlu, "option1": titlu.split(" / ")[0],
            "price": pret, "available": disponibil}


def _payload(variante, **extra):
    p = {"title": "Produs test", "handle": "produs-test",
         "url": "/products/produs-test",
         "featured_image": "//cdn.shopify.com/s/files/x.jpg",
         "variants": variante}
    p.update(extra)
    return p


@pytest.fixture
def fetch_fals(monkeypatch):
    """Instaleaza un fetch fals; intoarce (seteaza_payload, urluri_cerute)."""
    urluri = []
    cutie = {"payload": _payload([_v("42", 10000)])}

    def fals(url, max_retries=3):
        urluri.append(url)
        continut = cutie["payload"]
        return continut if isinstance(continut, str) else json.dumps(continut)

    monkeypatch.setattr(ppe, "_fetch_text_guarded", fals)

    def seteaza(payload):
        cutie["payload"] = payload

    return seteaza, urluri


def test_handle_din_url(fetch_fals):
    _, urluri = fetch_fals

    cazuri = [
        (f"https://{DOM_EUR}/products/air-max-90", "air-max-90"),
        (f"https://{DOM_EUR}/products/air-max-90?variant=123", "air-max-90"),
        (f"https://{DOM_EUR}/en/products/air-max-90", "air-max-90"),
        (f"https://{DOM_EUR}/products/air-max-90.js", "air-max-90"),
        (f"https://{DOM_EUR}/products/air-max-90.json", "air-max-90"),
    ]
    for url, handle in cazuri:
        urluri.clear()
        ppe._extract_shopify(url)
        assert urluri == [f"https://{DOM_EUR}/products/{handle}.js"], f"pentru {url}"

    # Fara /products/ in cale nu exista handle, deci nu exista produs.
    with pytest.raises(ProductExtractionError) as exc:
        ppe._extract_shopify(f"https://{DOM_EUR}/collections/sneakers")
    assert exc.value.reason == "no_product_data"


def test_pret_minim_al_marimilor_disponibile(fetch_fals):
    # RAMURA DISCRIMINANTA a regulii FASHION-2, pe care sonda live NU a exercitat-o:
    # cea mai ieftina marime e EPUIZATA, deci candidatul trebuie sa fie urmatoarea
    # disponibila, nu minimul absolut.
    seteaza, _ = fetch_fals
    seteaza(_payload([
        _v("40", 9900, disponibil=False),   # cel mai ieftin, dar epuizat
        _v("41", 14900, disponibil=True),
        _v("42", 19900, disponibil=True),
    ]))

    rezultat = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")

    assert rezultat["price"] == 149.0
    assert rezultat["in_stock"] is True


def test_toate_epuizate(fetch_fals):
    seteaza, _ = fetch_fals
    seteaza(_payload([
        _v("40", 24900, disponibil=False),
        _v("41", 19900, disponibil=False),
    ]))

    rezultat = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")

    assert rezultat["price"] == 199.0
    assert rezultat["in_stock"] is False


def test_default_title_produs_simplu(fetch_fals):
    seteaza, _ = fetch_fals
    seteaza(_payload([_v("Default Title", 12500)]))

    rezultat = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")

    assert rezultat["variants"] is None
    assert rezultat["price"] == 125.0


def test_pret_int_in_bani(fetch_fals):
    seteaza, _ = fetch_fals
    seteaza(_payload([
        _v("40", 24861),        # int -> 248.61
        _v("41", "24861"),      # string numai-cifre, aceeasi valoare
        _v("42", "24,861"),     # virgula -> varianta se SARE
        _v("43", 248.61),       # float exotic -> varianta se SARE
    ]))

    rezultat = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")

    assert rezultat["price"] == 248.61
    assert [v["variant"] for v in rezultat["variants"]] == ["40", "41"]


def test_moneda_din_registru(fetch_fals):
    # Payload-ul Ajax NU poarta moneda: singura sursa e campul din registru.
    eur = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")
    ron = ppe._extract_shopify(f"https://{DOM_RON}/products/x")

    assert eur["currency"] == "EUR"
    assert ron["currency"] == "RON"


def test_forma_variantelor(fetch_fals):
    seteaza, _ = fetch_fals
    seteaza(_payload([
        _v("42 / Black", 14900, disponibil=True),
        _v("43 / Black", 14900, disponibil=False),
    ]))

    rezultat = ppe._extract_shopify(f"https://{DOM_EUR}/products/x")

    assert rezultat["variants"] == [
        {"variant": "42 / Black", "price": 149.0, "in_stock": True},
        {"variant": "43 / Black", "price": 149.0, "in_stock": False},
    ]
    for v in rezultat["variants"]:
        assert set(v.keys()) == {"variant", "price", "in_stock"}


def test_dispecerizare_prin_metoda(fetch_fals):
    _, urluri = fetch_fals

    # Domeniu cu method="shopify": extract_product ajunge in _extract_shopify, deci
    # se cere endpointul .js — NU se face fetch de HTML si nu se parseaza pagina.
    rezultat = ppe.extract_product(f"https://{DOM_EUR}/products/air-max-90")

    assert rezultat["method"] == "shopify"
    assert urluri == [f"https://{DOM_EUR}/products/air-max-90.js"]

    # Domeniu cu method="jsonld": nu intra pe calea Shopify (ramane fluxul generic).
    assert ppe._shopify_extractor_for(f"https://{DOM_JSONLD}/produs/ceva") is False
    assert ppe._shopify_extractor_for(f"https://{DOM_EUR}/products/x") is True
