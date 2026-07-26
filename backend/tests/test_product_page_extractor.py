"""RETAIL-1 — extractorul generic de pagina de produs (functii PURE, fara retea, fara DB).

Acopera:
  - parse_product_html  (JSON-LD Product/Offer, fallback OpenGraph, overrides, erori)
  - _parse_price_any    (formatele de pret intalnite pe magazinele romanesti)

Fixture-urile sunt HTML sintetic minim, inline: aici se testeaza logica de
parsare, nu structura reala a unui magazin (capturile reale stau in tests/fixtures/).
`extract_product` nu se testeaza — face retea si e doar bucla de retry peste
_fetch_shop_url_guarded, deja acoperit in scraper_service.
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
