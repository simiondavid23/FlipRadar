"""RETAIL-1 — extractorul generic de pagina de produs (functii PURE, fara retea, fara DB).

Acopera:
  - parse_product_html  (JSON-LD Product/Offer, fallback OpenGraph, overrides, erori)
  - _parse_price_any    (formatele de pret intalnite pe magazinele romanesti)

Fixture-urile sunt HTML sintetic minim, inline: aici se testeaza logica de
parsare, nu structura reala a unui magazin (capturile reale stau in tests/fixtures/).
Din `extract_product` se testeaza DOAR bucla de erori adaugata la FASHION-4
(retry pe no_product_data + precedenta parse > challenge > fetch_failed), cu
poarta de fetch mock-uita; restul buclei ramane acoperit in scraper_service.
"""
import json

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
                        "image_url", "canonical_url", "domain", "method", "override_applied",
                        "variants"}   # FASHION-1b — cheie aditiva, None aici
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


# ── RETAIL-5: price_regex (override pe starea JS incorporata) ─────────────────

FAKE_URL = "https://magazin-fake.ro/p/1"


def _ld_plus_state(ld_price, state_price, extra_body=""):
    """Pagina in stilul eMAG: JSON-LD cu un pret, stare JS incorporata cu altul."""
    return _page(
        head=_ld(f"""
            {{"@type": "Product", "name": "Laptop Test",
              "offers": {{"@type": "Offer", "price": "{ld_price}", "priceCurrency": "RON"}}}}
        """),
        body=(f'<script>EM.product = {{\n  id: 42,\n  offer: {{\n    price: {{\n'
              f'      current: {state_price},\n    }}\n  }},\n}};</script>{extra_body}'),
    )


STATE_REGEX = r'EM\.product\s*=\s*\{.*?price:\s*\{\s*current:\s*([0-9]+(?:\.[0-9]+)?)'


def test_price_regex_bate_jsonld(monkeypatch):
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {"price_regex": STATE_REGEX})

    res = parse_product_html(_ld_plus_state("5689.42", "3459.99"), FAKE_URL)

    assert res["price"] == 3459.99
    assert res["override_applied"] is True
    # Metoda ramane a sursei de baza: override-ul patch-uieste, nu inlocuieste lantul.
    assert res["method"] == "jsonld"
    assert res["name"] == "Laptop Test"


def test_price_regex_parsare_stricta_format_masina(monkeypatch):
    """Punctul din starea JS e MEREU zecimal. _parse_price_any ar citi "1234.567"
    ca separator de mii (1234567) — de aceea regexul foloseste float() direct."""
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {"price_regex": STATE_REGEX})

    res = parse_product_html(_ld_plus_state("99,00", "1234.567"), FAKE_URL)

    assert res["price"] == 1234.567


def test_price_regex_fara_match_lasa_jsonld(monkeypatch):
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro",
                        {"price_regex": r"NU_EXISTA_IN_PAGINA:\s*([0-9.]+)"})

    res = parse_product_html(_ld_plus_state("5689.42", "3459.99"), FAKE_URL)

    assert res["price"] == 5689.42
    assert res["override_applied"] is False  # nimic nu s-a aplicat efectiv


def test_price_regex_captura_neparsabila_e_ignorata(monkeypatch):
    """Captura exista dar nu e numar -> se cade inapoi pe JSON-LD, fara exceptie."""
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro",
                        {"price_regex": r'"eticheta":\s*"([^"]+)"'})
    html = _ld_plus_state("5689.42", "3459.99", extra_body='<script>{"eticheta": "la cerere"}</script>')

    res = parse_product_html(html, FAKE_URL)

    assert res["price"] == 5689.42
    assert res["override_applied"] is False


def test_price_regex_zero_e_ignorat(monkeypatch):
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {"price_regex": STATE_REGEX})

    res = parse_product_html(_ld_plus_state("5689.42", "0"), FAKE_URL)

    assert res["price"] == 5689.42
    assert res["override_applied"] is False


def test_price_regex_are_precedenta_peste_price_selector(monkeypatch):
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {
        "price_regex": STATE_REGEX,
        "price_selector": "span.pret-final",
    })
    html = _ld_plus_state("5689.42", "3459.99", extra_body='<span class="pret-final">777,00 lei</span>')

    res = parse_product_html(html, FAKE_URL)

    assert res["price"] == 3459.99   # regexul, nu selectorul


def test_price_selector_ramane_fallback_cand_regexul_rateaza(monkeypatch):
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-fake.ro", {
        "price_regex": r"NU_EXISTA:\s*([0-9.]+)",
        "price_selector": "span.pret-final",
    })
    html = _ld_plus_state("5689.42", "3459.99", extra_body='<span class="pret-final">777,00 lei</span>')

    res = parse_product_html(html, FAKE_URL)

    assert res["price"] == 777.0
    assert res["override_applied"] is True


# ── RETAIL-5b: override-ul de PRODUCTIE pentru eMAG ──────────────────────────

def test_emag_are_price_selector():
    """Santinela: continutul EXACT al override-ului de productie. Orice schimbare
    (alt selector, camp in plus) trebuie facuta constient, cu dovada din sonda."""
    assert ppe.DOMAIN_OVERRIDES["emag.ro"] == {"price_selector": ".product-new-price"}


def _emag_page(jsonld_price, afisat, availability="https://schema.org/InStock"):
    """Pagina in stilul eMAG: JSON-LD cu oferta principala, elementul vizibil cu
    pretul afisat (spart in span-uri, exact ca in HTML-ul real)."""
    whole, cents = afisat.split(",")
    return _page(
        head=_ld(f"""
            {{"@type": "Product", "name": "Laptop Lenovo IdeaPad",
              "offers": {{"@type": "Offer", "price": "{jsonld_price}",
                          "priceCurrency": "RON", "availability": "{availability}"}}}}
        """),
        body=(f'<p class="product-new-price">{whole}<sup>,</sup>'
              f'<sup>{cents}</sup> Lei</p>'),
    )


def test_emag_multi_oferta_ia_pretul_afisat():
    """Cazul care a motivat override-ul: pagina cu mai multe oferte arata
    "de la <minim>", iar JSON-LD poarta oferta principala, mai scumpa."""
    html = _emag_page("5689.42", "de la 3.459,99")

    res = parse_product_html(html, "https://www.emag.ro/laptop-lenovo/pd/DWNRDP3BM/")

    assert res["price"] == 3459.99          # afisat, NU cel din JSON-LD
    assert res["override_applied"] is True
    assert res["method"] == "jsonld"        # override-ul patch-uieste, nu inlocuieste lantul
    assert res["name"] == "Laptop Lenovo IdeaPad"
    assert res["currency"] == "RON"
    # Nuanta documentata: stocul ramane al ofertei PRINCIPALE din JSON-LD.
    assert res["in_stock"] is True


def test_emag_oferta_unica_da_acelasi_pret_ca_jsonld():
    html = _emag_page("4840.00", "4.840,00")

    res = parse_product_html(html, "https://www.emag.ro/laptop-acer/pd/D46YX5YBM/")

    assert res["price"] == 4840.0
    assert res["override_applied"] is True


def test_emag_fara_elementul_de_pret_cade_curat_pe_jsonld():
    """Daca eMAG redenumeste clasa, nu ramanem fara pret: selectorul nu se
    potriveste, override_applied ramane False si JSON-LD preia."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Laptop fara element de pret",
         "offers": {"@type": "Offer", "price": "1999.00", "priceCurrency": "RON"}}
    """))

    res = parse_product_html(html, "https://www.emag.ro/laptop/pd/XYZ/")

    assert res["price"] == 1999.0
    assert res["override_applied"] is False


# ── FASHION-1b: ProductGroup / hasVariant ─────────────────────────────────────
#
# Fixture-urile de mai jos reproduc FORMELE REALE masurate de sonda fashion
# (2026-07-26): eobuwie (epantofi.ro / modivo.ro) publica WebSite +
# BreadcrumbList + ProductGroup, unde hasVariant e o lista de produse-varianta cu
# `size` la nivelul variantei si o singura oferta fiecare; answear publica un
# Product simplu care poarta doar LISTA de marimi, fara oferta per marime.

def _variant(size, price, availability="InStock", *, name="Sneakers Nike Dunk Low"):
    """O intrare hasVariant in forma eobuwie. `availability=None` = cheie absenta."""
    offer = {"@type": "Offer", "price": price, "priceCurrency": "RON"}
    if availability is not None:
        offer["availability"] = f"https://schema.org/{availability}"
    return {"@type": "Product", "name": name, "size": size, "offers": offer}


def _group_page(variants, *, name="Sneakers Nike Dunk Low", in_graph=False):
    """Pagina eobuwie: WebSite + BreadcrumbList + ProductGroup (optional in @graph)."""
    group = {"@type": "ProductGroup", "name": name,
             "image": ["https://img.eobuwie.cloud/dunk.jpg"],
             "brand": {"@type": "Brand", "name": "Nike"},
             "variesBy": ["https://schema.org/Size"],
             "hasVariant": variants}
    if in_graph:
        return _page(head=_ld(json.dumps({"@context": "https://schema.org", "@graph": [
            {"@type": "WebSite", "name": "Epantofi"},
            {"@type": "BreadcrumbList", "itemListElement": []},
            group]})))
    return _page(head=(_ld(json.dumps({"@type": "WebSite", "name": "Epantofi"}))
                       + _ld(json.dumps({"@type": "BreadcrumbList", "itemListElement": []}))
                       + _ld(json.dumps(group))))


def test_productgroup_epantofi_pretul_e_minimul_marimilor_in_stoc():
    """Forma epantofi cu 8 marimi, mix de disponibilitate: pretul product-level e
    minimul marimilor CUMPARABILE, nu minimul absolut."""
    html = _group_page([
        _variant("40_5", 652.0, "OutOfStock"),
        _variant("41", 652.0, "OutOfStock"),
        _variant("42", 699.0, "InStock"),
        _variant("42_5", 679.0, "InStock"),
        _variant("43", 652.0, "OutOfStock"),
        _variant("44", 719.0, "InStock"),
        _variant("44_5", 729.0, "OutOfStock"),
        _variant("46", 749.0, "InStock"),
    ])

    res = parse_product_html(html, "https://epantofi.ro/p/dunk-low")

    assert res["method"] == "jsonld"
    assert res["name"] == "Sneakers Nike Dunk Low"
    assert res["price"] == 679.0            # minimul din InStock (652 e epuizat)
    assert res["in_stock"] is True
    assert res["is_aggregate"] is True      # pretul e "de la"
    assert res["currency"] == "RON"
    assert res["image_url"] == "https://img.eobuwie.cloud/dunk.jpg"
    assert len(res["variants"]) == 8
    assert res["variants"][0] == {"variant": "40_5", "price": 652.0, "in_stock": False}
    assert res["variants"][2] == {"variant": "42", "price": 699.0, "in_stock": True}
    assert [v["variant"] for v in res["variants"]] == [
        "40_5", "41", "42", "42_5", "43", "44", "44_5", "46"]


def test_productgroup_toate_epuizate_cade_pe_minimul_tuturor():
    """Cazul masurat live pe epantofi: toate marimile OutOfStock. Produsul ramane
    monitorizabil, cu pretul minim al grupului si stocul False."""
    html = _group_page([
        _variant("41", 652.0, "OutOfStock"),
        _variant("42", 640.0, "OutOfStock"),
        _variant("43", 660.0, "OutOfStock"),
    ])

    res = parse_product_html(html, "https://epantofi.ro/p/dunk-low")

    assert res["price"] == 640.0
    assert res["in_stock"] is False
    assert [v["in_stock"] for v in res["variants"]] == [False, False, False]


def test_productgroup_availability_lipsa_da_none_pe_varianta_si_pe_agregat():
    """Fara availability, varianta e necunoscuta (None). Agregatul e None cand nu
    exista nici macar o marime in stoc, dar nici toate nu-s explicit epuizate."""
    html = _group_page([
        _variant("41", 652.0, "OutOfStock"),
        _variant("42", 640.0, availability=None),
    ])

    res = parse_product_html(html, "https://epantofi.ro/p/dunk-low")

    assert [v["in_stock"] for v in res["variants"]] == [False, None]
    assert res["in_stock"] is None
    assert res["price"] == 640.0            # nicio marime in stoc -> minimul tuturor


def test_productgroup_varianta_fara_pret_valid_e_sarita():
    """O marime necotata (pret 0 / fara oferta) nu invalideaza grupul."""
    html = _group_page([
        _variant("41", 0, "InStock"),
        {"@type": "Product", "name": "fara oferta", "size": "42"},
        _variant("43", 559.0, "InStock"),
    ])

    res = parse_product_html(html, "https://modivo.ro/p/x")

    assert len(res["variants"]) == 1
    assert res["variants"][0] == {"variant": "43", "price": 559.0, "in_stock": True}
    assert res["price"] == 559.0
    assert res["in_stock"] is True


def test_productgroup_in_graph_e_gasit():
    html = _group_page([_variant("42", 331.0, "InStock")], in_graph=True)

    res = parse_product_html(html, "https://modivo.ro/p/x")

    assert res["price"] == 331.0
    assert [v["variant"] for v in res["variants"]] == ["42"]


def test_productgroup_marimile_compuse_raman_string_liber():
    """Talia modivo '28_32' si jumatatea '40_5' se pastreaza EXACT — orice
    normalizare numerica ar pierde a doua componenta."""
    html = _group_page([
        _variant("28_32", 225.9, "OutOfStock"),
        _variant("29_32", 225.9, "InStock"),
        _variant("40_5", 225.9, "InStock"),
        _variant("XXL", 225.9, "InStock"),
    ])

    res = parse_product_html(html, "https://modivo.ro/p/blugi")

    assert [v["variant"] for v in res["variants"]] == ["28_32", "29_32", "40_5", "XXL"]
    assert all(isinstance(v["variant"], str) for v in res["variants"])


def test_produs_simplu_are_cheia_variants_dar_e_none():
    """REGRESIE: cheia e aditiva, deci exista pe toate caile — cu valoarea None."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Casti Bluetooth XZ",
         "offers": {"@type": "Offer", "price": "249.99", "priceCurrency": "RON",
                    "availability": "https://schema.org/InStock"}}
    """))

    res = parse_product_html(html, URL)

    assert "variants" in res
    assert res["variants"] is None
    assert res["is_aggregate"] is False


def test_lista_de_marimi_fara_oferte_nu_fabrica_variante():
    """Forma answear: Product simplu cu `size` = lista de marimi si o singura
    oferta. Fara pret/stoc pe marime nu avem ce monitoriza -> variants None."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "U.S. Polo Assn. camasa safari",
         "size": ["S", "M", "L", "XL", "XXL"],
         "offers": {"@type": "Offer", "price": "209.9", "priceCurrency": "RON",
                    "availability": "https://schema.org/InStock"}}
    """))

    res = parse_product_html(html, "https://answear.ro/p/camasa")

    assert res["price"] == 209.9
    assert res["in_stock"] is True
    assert res["variants"] is None


def test_productgroup_fara_nicio_varianta_cotata_da_eroarea_existenta():
    """Grup gol de preturi: clasificarea erorii ramane cea de azi — invalid_price
    cand a existat un candidat de pret, no_product_data cand nu a existat deloc."""
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_group_page([_variant("41", 0, "InStock")]),
                           "https://epantofi.ro/p/x")
    assert exc.value.reason == "invalid_price"

    fara_oferte = _group_page([{"@type": "Product", "name": "x", "size": "41"}])
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(fara_oferte, "https://epantofi.ro/p/x")
    assert exc.value.reason == "no_product_data"


def test_productul_valid_are_precedenta_peste_productgroup():
    """ProductGroup e plasa de dedesubt: cand pagina publica si un Product cotat,
    acela ramane sursa (si variants ramane None)."""
    html = _page(head=(
        _ld(json.dumps({"@type": "ProductGroup", "name": "Grup",
                        "hasVariant": [_variant("42", 100.0, "InStock")]}))
        + _ld(json.dumps({"@type": "Product", "name": "Produs cotat",
                          "offers": {"@type": "Offer", "price": 149.0,
                                     "priceCurrency": "RON"}}))))

    res = parse_product_html(html, "https://www.magazin-test.ro/p/x")

    assert res["name"] == "Produs cotat"
    assert res["price"] == 149.0
    assert res["variants"] is None


def test_productgroup_preia_cand_produsul_simplu_nu_are_pret():
    """Product prezent dar necotat -> grupul preia, cu variante cu tot."""
    html = _page(head=(
        _ld(json.dumps({"@type": "Product", "name": "Produs fara pret"}))
        + _ld(json.dumps({"@type": "ProductGroup", "name": "Grup cu marimi",
                          "hasVariant": [_variant("42", 100.0, "InStock"),
                                         _variant("43", 120.0, "InStock")]}))))

    res = parse_product_html(html, "https://epantofi.ro/p/x")

    assert res["name"] == "Grup cu marimi"
    assert res["price"] == 100.0
    assert len(res["variants"]) == 2


def test_og_are_variants_none():
    """Calea OG (fara JSON-LD) pastreaza cheia aditiva, goala."""
    html = _page(head="""
        <meta property="og:title" content="Produs OG"/>
        <meta property="product:price:amount" content="99.90"/>
        <meta property="product:price:currency" content="RON"/>
    """)

    res = parse_product_html(html, URL)

    assert res["method"] == "og"
    assert res["variants"] is None


# ── FASHION-2: forma #2 — Product cu offers-lista cu `size` per oferta ────────
#
# Masurata pe BSTN (sonda 2026-07-26): un singur Product, fara ProductGroup, cu
# `offers` = lista de oferte purtand fiecare propria marime. Etichetele reale au
# spatii si fractii ('4,0 US', '36 2/3 EU'), deci raman string liber.
# Contra-forma, pinuita mai jos: sneakersnstuff publica tot offers-lista, dar
# FARA size — acolo comportamentul trebuie sa ramana exact cel dinainte.

def _offer(size, price, availability="InStock", currency="USD"):
    """O oferta in forma BSTN. `size=None` = oferta fara marime declarata."""
    offer = {"@type": "Offer", "price": price, "priceCurrency": currency}
    if size is not None:
        offer["size"] = size
    if availability is not None:
        offer["availability"] = f"https://schema.org/{availability}"
    return offer


def _offers_page(offers, *, name="530 DRW"):
    return _page(head=_ld(json.dumps({
        "@context": "https://schema.org", "@type": "Product", "name": name,
        "image": "https://cdn.bstn.com/530.jpg", "offers": offers})))


def test_offers_lista_cu_size_da_variante_si_minimul_in_stoc():
    """Pretul product-level NU mai e al primului element: primul e epuizat la
    84.99, dar cea mai ieftina marime CUMPARABILA e 99.99."""
    html = _offers_page([
        _offer("4,0 US", 84.99, "OutOfStock"),
        _offer("4,5 US", 89.99, "OutOfStock"),
        _offer("5,0 US", 109.99, "InStock"),
        _offer("36 2/3 EU", 99.99, "InStock"),
        _offer("37 1/3 EU", 119.99, "InStock"),
        _offer("38 EU", 129.99, "OutOfStock"),
    ])

    res = parse_product_html(html, "https://www.bstn.com/us_en/p/new-balance-530-drw")

    assert res["method"] == "jsonld"
    assert res["price"] == 99.99            # minimul din InStock, nu 84.99 (primul)
    assert res["in_stock"] is True
    assert res["is_aggregate"] is True
    assert res["currency"] == "USD"
    assert len(res["variants"]) == 6
    # Etichetele raman EXACT cum le publica magazinul (spatii, virgule, fractii).
    assert [v["variant"] for v in res["variants"]] == [
        "4,0 US", "4,5 US", "5,0 US", "36 2/3 EU", "37 1/3 EU", "38 EU"]
    assert res["variants"][0] == {"variant": "4,0 US", "price": 84.99, "in_stock": False}
    assert res["variants"][3] == {"variant": "36 2/3 EU", "price": 99.99, "in_stock": True}


def test_offers_lista_toate_epuizate_cade_pe_minimul_tuturor():
    html = _offers_page([
        _offer("4,0 US", 84.99, "OutOfStock"),
        _offer("4,5 US", 79.99, "OutOfStock"),
    ])

    res = parse_product_html(html, "https://www.bstn.com/us_en/p/x")

    assert res["price"] == 79.99
    assert res["in_stock"] is False


def test_offers_lista_oferta_necotata_e_sarita():
    html = _offers_page([
        _offer("4,0 US", 0, "InStock"),
        _offer("4,5 US", 89.99, "InStock"),
    ])

    res = parse_product_html(html, "https://www.bstn.com/us_en/p/x")

    assert [v["variant"] for v in res["variants"]] == ["4,5 US"]
    assert res["price"] == 89.99


def test_offers_lista_availability_lipsa_da_none_pe_varianta():
    html = _offers_page([
        _offer("4,0 US", 84.99, "OutOfStock"),
        _offer("4,5 US", 79.99, availability=None),
    ])

    res = parse_product_html(html, "https://www.bstn.com/us_en/p/x")

    assert [v["in_stock"] for v in res["variants"]] == [False, None]
    assert res["in_stock"] is None          # nici in stoc, nici toate epuizate
    assert res["price"] == 79.99


def test_offers_lista_fara_size_ramane_exact_ca_azi():
    """REGRESIE PINUITA (forma sneakersnstuff): fara `size` pe niciun element,
    calea ramane cea dinainte de FASHION-2 — primul cu pret, fara variante."""
    html = _offers_page([
        _offer(None, 149.99, "OutOfStock"),
        _offer(None, 99.99, "InStock"),
    ])

    res = parse_product_html(html, "https://www.sneakersnstuff.com/p/x")

    assert res["variants"] is None
    assert res["price"] == 149.99           # PRIMUL element, nu minimul
    assert res["in_stock"] is False         # stocul primei oferte
    assert res["is_aggregate"] is False


def test_offers_lista_cu_un_singur_element_fara_size_ramane_ca_azi():
    """REGRESIE (forma afew): offers-lista cu un element, fara marime."""
    html = _offers_page([_offer(None, 129.0, "InStock", currency="EUR")])

    res = parse_product_html(html, "https://en.afew-store.com/products/x")

    assert res["variants"] is None
    assert res["price"] == 129.0
    assert res["in_stock"] is True
    assert res["currency"] == "EUR"


def test_offers_lista_mixta_ia_doar_ofertele_cu_marime():
    """Pe o lista mixta, ofertele fara marime NU devin variante (altfel eticheta
    ar fi inventata din numele produsului) si nu intra in agregare."""
    html = _offers_page([
        _offer(None, 59.99, "InStock"),      # oferta generica, ignorata ca varianta
        _offer("4,0 US", 84.99, "InStock"),
        _offer("4,5 US", 94.99, "OutOfStock"),
    ])

    res = parse_product_html(html, "https://www.bstn.com/us_en/p/x")

    assert [v["variant"] for v in res["variants"]] == ["4,0 US", "4,5 US"]
    assert res["price"] == 84.99            # minimul marimilor, nu oferta de 59.99
    assert res["in_stock"] is True


def test_ambele_forme_trec_prin_aceeasi_agregare():
    """Santinela de refactor: ProductGroup si offers-lista trebuie sa dea acelasi
    rezultat pentru aceleasi marimi, preturi si stocuri."""
    from app.services.product_page_extractor import _aggregate_variants

    trei = [
        {"variant": "41", "price": 200.0, "in_stock": False},
        {"variant": "42", "price": 150.0, "in_stock": True},
        {"variant": "43", "price": 180.0, "in_stock": True},
    ]
    assert _aggregate_variants(trei) == (150.0, True)

    grup = parse_product_html(_group_page([
        _variant("41", 200.0, "OutOfStock"),
        _variant("42", 150.0, "InStock"),
        _variant("43", 180.0, "InStock"),
    ]), "https://epantofi.ro/p/x")
    lista = parse_product_html(_offers_page([
        _offer("41", 200.0, "OutOfStock", currency="RON"),
        _offer("42", 150.0, "InStock", currency="RON"),
        _offer("43", 180.0, "InStock", currency="RON"),
    ]), "https://www.bstn.com/us_en/p/x")

    for res in (grup, lista):
        assert (res["price"], res["in_stock"], res["is_aggregate"]) == (150.0, True, True)
    assert [v["variant"] for v in grup["variants"]] == [v["variant"] for v in lista["variants"]]


# ── FASHION-4: retry defensiv pe no_product_data in extract_product ───────────
# Singurele teste din fisier care ating extract_product. Reteaua e taiata la
# radacina: _fetch_shop_url_guarded se patch-uieste in namespace-ul
# app.services.scraper_service (nu in ppe), fiindca extract_product il importa
# LENES, in corpul functiei — un patch pe ppe n-ar fi vazut. time.sleep se
# neutralizeaza ca bucla sa nu astepte 1-3s intre incercari.

_HTML_OK = _page(head=_ld("""
    {"@type": "Product", "name": "Produs servit corect",
     "offers": {"@type": "Offer", "price": "199.99", "priceCurrency": "RON"}}
"""))
_HTML_FARA_DATE = _page(head="<title>Produs</title>", body="<div>pagina reala, fara ld+json</div>")
_HTML_PRET_ZERO = _page(head=_ld("""
    {"@type": "Product", "name": "Produs cu pret 0",
     "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RON"}}
"""))


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {}


@pytest.fixture
def fetch_mock(monkeypatch):
    """Inlocuieste poarta de fetch cu o coada de raspunsuri HTML si numara apelurile."""
    from app.services import scraper_service

    monkeypatch.setattr(ppe.time, "sleep", lambda *_a, **_kw: None)

    def _install(*pagini):
        state = {"calls": 0}

        def _fake(url, **_kwargs):
            index = min(state["calls"], len(pagini) - 1)
            state["calls"] += 1
            return _FakeResponse(pagini[index])

        monkeypatch.setattr(scraper_service, "_fetch_shop_url_guarded", _fake)
        return state

    return _install


SHOP_URL = "https://www.aboutyou.ro/p/marca/produs-123"


def test_no_product_data_reintra_in_bucla_si_reuseste(fetch_mock):
    """Servire inconsistenta simulata: prima pagina vine fara date de produs, a
    doua e completa. Retry-ul defensiv trebuie sa salveze extractia."""
    state = fetch_mock(_HTML_FARA_DATE, _HTML_OK)

    res = ppe.extract_product(SHOP_URL)

    assert (res["price"], res["currency"], res["name"]) == (199.99, "RON", "Produs servit corect")
    assert state["calls"] == 2          # a doua incercare a fost chiar ceruta


def test_no_product_data_pe_toate_incercarile_pastreaza_reason_ul(fetch_mock):
    """Recidiva LIPITA (3/3): apelantul vede exact eroarea de azi, nu una degradata
    in fetch_failed/challenge — precedenta erorilor pune parse-ul primul."""
    state = fetch_mock(_HTML_FARA_DATE)

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(SHOP_URL)

    assert exc.value.reason == "no_product_data"
    assert state["calls"] == 3


def test_invalid_price_propaga_imediat_fara_retry(fetch_mock):
    """Doar no_product_data reintra in bucla. Cand pagina CHIAR poarta un pret,
    doar ca invalid, un re-fetch n-ar schimba nimic — deci un singur fetch."""
    state = fetch_mock(_HTML_PRET_ZERO)

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(SHOP_URL)

    assert exc.value.reason == "invalid_price"
    assert state["calls"] == 1


# ── FASHION-4: domeniile noi intra in allow-list-ul C-14 ──────────────────────

@pytest.mark.parametrize("url", [
    "https://www.aboutyou.ro/p/x",
    "https://aboutyou.ro/p/x",
    "https://www.trendyol.com/ro/marca/produs-p-123",
])
def test_domeniile_fashion4_sunt_permise(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is True


@pytest.mark.parametrize("url", [
    "https://evil-aboutyou.ro.attacker.com/p/x",
    "https://trendyol.com.attacker.com/ro/x",
])
def test_sufixele_inselatoare_raman_respinse(url):
    """Promovarea nu slabeste allow-list-ul: potrivirea ramane pe egalitate sau
    pe "."+domeniu, deci un sufix atasat nu trece."""
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is False


# ── ACCESS-2: domeniile noi intra in allow-list-ul C-14 ───────────────────────

@pytest.mark.parametrize("url", [
    "https://www.endclothing.com/eu/produs.html",
    "https://endclothing.com/eu/produs.html",
    "https://www.zalando.ro/produs-x.html",
    "https://www.43einhalb.com/p/produs",
])
def test_domeniile_access2_sunt_permise(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is True


@pytest.mark.parametrize("url", [
    "https://evil-endclothing.com.attacker.com/x",
    "https://zalando.ro.attacker.com/x",
    "https://43einhalb.com.attacker.com/p/x",
])
def test_sufixele_inselatoare_access2_raman_respinse(url):
    """Promovarea nu slabeste allow-list-ul: potrivirea ramane pe egalitate sau
    pe "."+domeniu, deci un sufix atasat nu trece."""
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is False


def test_override_de_amprenta_nu_deschide_singur_poarta(monkeypatch):
    """Un domeniu cu treapta in _IMPERSONATE_OVERRIDES nu devine prin asta permis:
    validarea (VALIDATED_DOMAINS) ramane singura conditie de intrare in allow-list.

    Testul foloseste un domeniu SINTETIC, nu unul real: la ACCESS-2 rolul asta il
    juca flanco.ro, dar a fost promovat la CONTENT-2 si invariantul ar fi disparut
    odata cu el. Cele doua liste au scopuri diferite (una spune CUM ceri, cealalta
    DACA ai voie sa ceri) si trebuie sa ramana independente.
    """
    import app.services.scraper_service as ss

    monkeypatch.setitem(ss._IMPERSONATE_OVERRIDES, "magazin-inchis.ro", "firefox135")

    assert ss._impersonate_for("https://magazin-inchis.ro/p/1") == "firefox135"
    assert "magazin-inchis.ro" not in ppe.VALIDATED_DOMAINS
    assert ss._is_allowed_shop_url("https://magazin-inchis.ro/p/1") is False


# ── CONTENT-2: microdata ca a patra sursa, dupa override/JSON-LD/OG ───────────
# Forma reprodusa e cea masurata pe evomag.ro (sonda CONTENT-1b, 2026-07-28):
# scope Product, meta priceCurrency, span itemprop=price cu atribut `content` in
# format masina, span availability cu URL-ul schema.org.

def _microdata(*, price='<span itemprop="price" content="1349.99">1349.99</span>',
               currency='<meta itemprop="priceCurrency" content="RON"/>',
               availability='<span itemprop="availability" '
                            'content="http://schema.org/InStock">In stock</span>',
               name='<h1 itemprop="name">Televizor LED TCL 55V6C</h1>') -> str:
    """Pagina fara Product in ld+json si fara pret OG — doar microdata."""
    return _page(body=f'<div itemscope itemtype="http://schema.org/Product">{name}'
                      f'<div itemscope itemtype="http://schema.org/Offer">'
                      f'{currency}{price}{availability}</div></div>')


def test_microdata_completa_da_pret_moneda_si_stoc():
    """Cazul evomag: tot ce descrie produsul sta in microdata."""
    data = parse_product_html(_microdata(), URL)

    assert data["price"] == 1349.99
    assert data["currency"] == "RON"
    assert data["in_stock"] is True
    assert data["method"] == "microdata"
    assert data["name"] == "Televizor LED TCL 55V6C"


def test_microdata_cu_doua_preturi_nu_furnizeaza_nimic():
    """Regula de siguranta: la ambiguitate microdata TACE. Un pret gresit ajunge in
    istoric si in alerte, deci ambiguitatea ramane esec, nu ghicitoare.

    Reason-ul e no_product_data, nu invalid_price: cu doua elemente nu se seteaza
    nici macar price_seen — nu stim ca am "vazut" un pret, stim ca n-am putut alege.
    """
    html = _microdata(price='<span itemprop="price" content="1349.99">1349.99</span>'
                            '<span itemprop="price" content="1449.99">1449.99</span>')

    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(html, URL)

    assert exc.value.reason == "no_product_data"


def test_microdata_fara_content_parseaza_textul_formatat():
    """Fara atribut `content` ramane textul, deci formatarea romaneasca trece prin
    _parse_price_any (1.349,99 -> 1349.99), nu prin float() strict."""
    data = parse_product_html(
        _microdata(price='<span itemprop="price">1.349,99 lei</span>'), URL)

    assert data["price"] == 1349.99
    assert data["method"] == "microdata"


def test_jsonld_are_precedenta_peste_microdata():
    """Preturi DIFERITE in cele doua surse: castiga JSON-LD, iar `method` ramane
    jsonld — microdata nu suprascrie niciodata, doar completeaza."""
    html = _page(
        head=_ld("""
        {"@context": "https://schema.org", "@type": "Product", "name": "Produs JSONLD",
         "offers": {"@type": "Offer", "price": "999.00", "priceCurrency": "RON"}}
        """),
        body='<div itemscope itemtype="http://schema.org/Product">'
             '<h1 itemprop="name">Produs MICRODATA</h1>'
             '<span itemprop="price" content="111.00">111.00</span></div>')

    data = parse_product_html(html, URL)

    assert data["price"] == 999.00
    assert data["name"] == "Produs JSONLD"
    assert data["method"] == "jsonld"


def test_og_are_precedenta_peste_microdata():
    """Acelasi test pentru treapta a treia: OG bate microdata."""
    html = _page(
        head='<meta property="og:title" content="Produs OG"/>'
             '<meta property="product:price:amount" content="777.00"/>'
             '<meta property="product:price:currency" content="RON"/>',
        body='<div itemscope itemtype="http://schema.org/Product">'
             '<h1 itemprop="name">Produs MICRODATA</h1>'
             '<span itemprop="price" content="111.00">111.00</span></div>')

    data = parse_product_html(html, URL)

    assert data["price"] == 777.00
    assert data["name"] == "Produs OG"
    assert data["method"] == "og"


def test_microdata_completeaza_doar_stocul_cand_pretul_vine_din_jsonld():
    """Fallback-ul e PER CAMP: JSON-LD da pretul dar nu si availability, deci stocul
    se ia din microdata. Masurat live pe flanco.ro — pret neschimbat, stoc completat.
    """
    html = _page(
        head=_ld("""
        {"@context": "https://schema.org", "@type": "Product", "name": "Produs JSONLD",
         "offers": {"@type": "Offer", "price": "999.00", "priceCurrency": "RON"}}
        """),
        body='<div itemscope itemtype="http://schema.org/Product">'
             '<span itemprop="availability" content="https://schema.org/OutOfStock">'
             'Stoc epuizat</span></div>')

    data = parse_product_html(html, URL)

    assert data["price"] == 999.00          # neatins
    assert data["method"] == "jsonld"       # neatins
    assert data["in_stock"] is False        # completat din microdata


# ── CONTENT-2: domeniile noi intra in allow-list-ul C-14 ─────────────────────

@pytest.mark.parametrize("url", [
    "https://www.flanco.ro/produs.html",
    "https://flanco.ro/produs.html",
    "https://www.evomag.ro/categorie/produs-4207097.html",
])
def test_domeniile_content2_sunt_permise(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is True


@pytest.mark.parametrize("url", [
    "https://evil-flanco.ro.attacker.com/produs.html",
    "https://flanco.ro.attacker.com/produs.html",
    "https://evomag.ro.attacker.com/produs.html",
])
def test_sufixele_inselatoare_content2_raman_respinse(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is False


def test_flanco_are_si_treapta_de_impersonate():
    """flanco.ro e in allow-list DOAR impreuna cu treapta lui: pe chrome ia 403, deci
    fara override-ul din scraper_service ar fi validat dar necitibil."""
    from app.services.scraper_service import _IMPERSONATE_OVERRIDES, _impersonate_for

    assert _IMPERSONATE_OVERRIDES["flanco.ro"] == "firefox135"
    assert _impersonate_for("https://www.flanco.ro/produs.html") == "firefox135"
