"""RETAIL-1 — extractorul generic de pagina de produs (functii PURE, fara retea, fara DB).

Acopera:
  - parse_product_html  (JSON-LD Product/Offer, fallback OpenGraph, overrides, erori)
  - _parse_price_any    (formatele de pret intalnite pe magazinele romanesti)

Fixture-urile sunt HTML sintetic minim, inline: aici se testeaza logica de
parsare, nu structura reala a unui magazin (capturile reale stau in tests/fixtures/).
`extract_product` nu se testeaza — face retea si e doar bucla de retry peste
_fetch_shop_url_guarded, deja acoperit in scraper_service.
"""
import pytest

from app.services import product_page_extractor as ppe
from app.services.product_page_extractor import (
    ProductExtractionError, _parse_price_any, parse_product_html,
)

URL = "https://www.magazin-test.ro/p/produs-1"


def _page(*, head: str = "", body: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def _ld(payload: str) -> str:
    return f'<script type="application/ld+json">{payload}</script>'


# ── JSON-LD: forme de document ────────────────────────────────────────────────

def test_jsonld_simplu_toate_cheile():
    html = _page(head=_ld("""
        {"@context": "https://schema.org", "@type": "Product",
         "name": "Casti Bluetooth XZ", "image": "https://cdn.magazin-test.ro/xz.jpg",
         "offers": {"@type": "Offer", "price": "249,99", "priceCurrency": "RON",
                    "availability": "https://schema.org/InStock"}}
    """) + '<link rel="canonical" href="https://www.magazin-test.ro/p/casti-xz"/>')

    res = parse_product_html(html, URL + "#tab-review")

    assert set(res) == {"name", "price", "currency", "in_stock", "is_aggregate",
                        "image_url", "canonical_url", "domain", "method", "override_applied"}
    assert res["name"] == "Casti Bluetooth XZ"
    assert res["price"] == 249.99
    assert res["currency"] == "RON"
    assert res["in_stock"] is True
    assert res["is_aggregate"] is False
    assert res["image_url"] == "https://cdn.magazin-test.ro/xz.jpg"
    assert res["canonical_url"] == "https://www.magazin-test.ro/p/casti-xz"
    assert res["domain"] == "magazin-test.ro"
    assert res["method"] == "jsonld"
    assert res["override_applied"] is False


def test_jsonld_in_graph():
    html = _page(head=_ld("""
        {"@context": "https://schema.org", "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": []},
            {"@type": "Product", "name": "SSD 1TB NVMe",
             "offers": {"@type": "Offer", "price": "399.00", "priceCurrency": "RON"}}
        ]}
    """))

    res = parse_product_html(html, URL)

    assert res["name"] == "SSD 1TB NVMe"
    assert res["price"] == 399.0
    assert res["method"] == "jsonld"


def test_jsonld_lista_top_level():
    html = _page(head=_ld("""
        [{"@type": "WebSite", "name": "Magazin Test"},
         {"@type": "Product", "name": "Adidasi Runner 42",
          "offers": {"@type": "Offer", "price": "319", "priceCurrency": "RON"}}]
    """))

    res = parse_product_html(html, URL)

    assert res["name"] == "Adidasi Runner 42"
    assert res["price"] == 319.0


def test_jsonld_type_lista():
    html = _page(head=_ld("""
        {"@type": ["Product", "Thing"], "name": "Vitamina C 1000mg",
         "offers": {"@type": "Offer", "price": "34,50", "priceCurrency": "RON"}}
    """))

    res = parse_product_html(html, URL)

    assert res["name"] == "Vitamina C 1000mg"
    assert res["price"] == 34.5


def test_jsonld_bloc_corupt_tolerat():
    """Primul bloc are JSON invalid (template neinlocuit) — al doilea trebuie citit."""
    html = _page(head=_ld('{"@type": "Product", "name": {{PRODUCT_NAME}}, }') + _ld("""
        {"@type": "Product", "name": "Placa video RTX",
         "offers": {"@type": "Offer", "price": "3.499,00", "priceCurrency": "RON"}}
    """))

    res = parse_product_html(html, URL)

    assert res["name"] == "Placa video RTX"
    assert res["price"] == 3499.0


# ── JSON-LD: forme de pret ────────────────────────────────────────────────────

def test_aggregate_offer_lowprice():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Telefon ABC",
         "offers": {"@type": "AggregateOffer", "lowPrice": "1299.00", "highPrice": "1499.00",
                    "priceCurrency": "RON"}}
    """))

    res = parse_product_html(html, URL)

    assert res["price"] == 1299.0
    assert res["is_aggregate"] is True


def test_offers_price_specification():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Aspirator ZZ",
         "offers": {"@type": "Offer", "priceCurrency": "RON",
                    "priceSpecification": {"@type": "UnitPriceSpecification", "price": "749,90"}}}
    """))

    res = parse_product_html(html, URL)

    assert res["price"] == 749.90
    assert res["is_aggregate"] is False


def test_offers_lista_primul_cu_pret():
    """Prima oferta n-are pret — castiga a doua, cu tot cu disponibilitatea EI."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Monitor 27",
         "offers": [{"@type": "Offer", "availability": "https://schema.org/OutOfStock"},
                    {"@type": "Offer", "price": "1150", "priceCurrency": "RON",
                     "availability": "https://schema.org/InStock"},
                    {"@type": "Offer", "price": "9999", "priceCurrency": "RON"}]}
    """))

    res = parse_product_html(html, URL)

    assert res["price"] == 1150.0
    assert res["in_stock"] is True


# ── disponibilitate ───────────────────────────────────────────────────────────

def test_availability_out_of_stock():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs epuizat",
         "offers": {"@type": "Offer", "price": "99", "priceCurrency": "RON",
                    "availability": "OutOfStock"}}
    """))

    assert parse_product_html(html, URL)["in_stock"] is False


def test_availability_lipsa_ramane_none():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs fara availability",
         "offers": {"@type": "Offer", "price": "99", "priceCurrency": "RON"}}
    """))

    assert parse_product_html(html, URL)["in_stock"] is None


# ── OpenGraph ─────────────────────────────────────────────────────────────────

def test_og_fallback_fara_jsonld():
    html = _page(head="""
        <meta property="og:title" content="Laptop Gaming 15"/>
        <meta property="og:image" content="https://cdn.magazin-test.ro/laptop.jpg"/>
        <meta property="product:price:amount" content="1.299,00"/>
        <meta property="product:price:currency" content="lei"/>
    """)

    res = parse_product_html(html, URL)

    assert res["method"] == "og"
    assert res["name"] == "Laptop Gaming 15"
    assert res["price"] == 1299.0
    assert res["currency"] == "RON"
    assert res["in_stock"] is None
    assert res["image_url"] == "https://cdn.magazin-test.ro/laptop.jpg"


def test_currency_lipsa_devine_ron():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs fara moneda",
         "offers": {"@type": "Offer", "price": "59,90"}}
    """))

    assert parse_product_html(html, URL)["currency"] == "RON"


# ── normalizarea preturilor ───────────────────────────────────────────────────

def test_pret_mii_cu_punct():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Bicicleta MTB",
         "offers": {"@type": "Offer", "price": "2.499", "priceCurrency": "RON"}}
    """))

    assert parse_product_html(html, URL)["price"] == 2499.0
    assert _parse_price_any("2.499") == 2499.0


def test_pret_zecimal_cu_punct():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Cablu USB-C",
         "offers": {"@type": "Offer", "price": "24.99", "priceCurrency": "RON"}}
    """))

    assert parse_product_html(html, URL)["price"] == 24.99
    assert _parse_price_any("24.99") == 24.99


def test_parse_price_any_formate():
    assert _parse_price_any("1.234,56") == 1234.56      # RO: mii "." + zecimal ","
    assert _parse_price_any("1,234.56") == 1234.56      # EN: mii "," + zecimal "."
    assert _parse_price_any("1\xa0299,00 lei") == 1299.0  # nbsp + sufix moneda
    assert _parse_price_any("349") == 349.0
    assert _parse_price_any(1299) == 1299.0
    assert _parse_price_any(24.99) == 24.99
    assert _parse_price_any("") is None
    assert _parse_price_any("La cerere") is None
    assert _parse_price_any(None) is None


# ── erori ─────────────────────────────────────────────────────────────────────

def test_pagina_fara_date_no_product_data():
    html = _page(head="<title>404</title>", body="<p>Pagina nu a fost gasita</p>")

    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(html, URL)
    assert exc.value.reason == "no_product_data"


def test_pret_zero_invalid_price():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs cu pret 0",
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RON"}}
    """))

    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(html, URL)
    assert exc.value.reason == "invalid_price"


# ── overrides & canonical ─────────────────────────────────────────────────────

def test_override_pe_domeniu(monkeypatch):
    """Override-ul patch-uieste doar campurile definite: pretul si stocul vin din
    pagina, numele ramane din JSON-LD."""
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {
        "price_selector": "span.pret-final",
        "out_of_stock_text": "Stoc epuizat",
    })
    html = _page(
        head=_ld("""
            {"@type": "Product", "name": "Frigider XL",
             "offers": {"@type": "Offer", "price": "999,00", "priceCurrency": "RON",
                        "availability": "https://schema.org/InStock"}}
        """),
        body='<span class="pret-final">1.499,00 lei</span><p>Stoc epuizat momentan</p>',
    )

    res = parse_product_html(html, "https://magazin-fake.ro/p/frigider")

    assert res["price"] == 1499.0          # selectorul bate JSON-LD
    assert res["in_stock"] is False        # markerul de stoc bate availability
    assert res["name"] == "Frigider XL"    # necontrolat de override -> ramane din JSON-LD
    assert res["override_applied"] is True


def test_canonical_absent_si_www_eliminat():
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs fara canonical",
         "offers": {"@type": "Offer", "price": "49,99", "priceCurrency": "RON"}}
    """))

    res = parse_product_html(html, "https://www.shop-fake.ro/produs?ref=x#galerie")

    assert res["canonical_url"] == "https://www.shop-fake.ro/produs?ref=x"
    assert res["domain"] == "shop-fake.ro"
    assert res["override_applied"] is False
