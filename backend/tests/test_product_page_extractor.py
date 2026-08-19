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
import os

import pytest

from app.services import product_page_extractor as ppe
from app.services.product_page_extractor import (
    DOMAIN_OVERRIDES, ProductExtractionError, _parse_price_any, parse_product_html,
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


def test_jsonld_lax_recupereaza_caractere_de_control():
    """LOT5b: SINGURUL bloc are newline LITERAL intr-o valoare de string.

    Forma brickdepot/nichiduta, redusa la esential: descriere multi-linie scrisa
    direct in ld+json. `json.loads` strict o refuza (caracter de control neescapat),
    deci pana la treapta laxa pagina parea fara date.
    """
    payload = (
        '{"@context": "https://schema.org", "@type": "Product",\n'
        ' "name": "Set constructie 1234",\n'
        ' "description": "Setul contine:\n- 379 piese\n- instructiuni",\n'
        ' "offers": {"@type": "Offer", "price": "158.99", "priceCurrency": "RON",\n'
        '            "availability": "https://schema.org/InStock"}}'
    )
    # Premisa testului: strictul chiar pica, iar laxul chiar recupereaza.
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload)
    assert json.loads(payload, strict=False)["offers"]["price"] == "158.99"

    res = parse_product_html(_page(head=_ld(payload)), URL)

    assert res["name"] == "Set constructie 1234"
    assert res["price"] == 158.99
    assert res["currency"] == "RON"
    assert res["in_stock"] is True
    assert res["method"] == "jsonld"


def test_jsonld_lax_nu_salveaza_sintaxa_stricata():
    """LOT5b: laxul acopera DOAR caractere de control, nu si sintaxa stricata.

    Forma paginii 5 brickdepot — ghilimea dublata care inchide descrierea de doua
    ori. Nici strictul, nici laxul nu o pot citi, deci blocul ramane aruncat si
    comportamentul e cel de azi.
    """
    payload = (
        '{"@context": "https://schema.org", "@type": "Product",\n'
        ' "name": "Set constructie 5678",\n'
        ' "description": "Proiectele realizate sunt salvate local"",\n'
        ' "offers": {"@type": "Offer", "price": "3021.99", "priceCurrency": "RON"}}'
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload)
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload, strict=False)

    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_page(head=_ld(payload)), URL)

    assert exc.value.reason == "no_product_data"


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


def test_aggregate_offer_stoc_din_oferte_imbricate():
    """VTX-2 — a treia forma de `offers`: agregatul poarta preturile, iar ofertele
    REALE stau intr-o lista imbricata, care duce `availability`.

    Structura e COPIATA VERBATIM din sonda VTX-1 pe f64.ro (VTEX),
    `dumps_vtx1/f64.ro_prod1.html`: agregatul n-are `availability`, deci citirea
    lui dadea `in_stock=None` si stocul se pierdea desi era publicat corect.
    """
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Godox iT32 Mini Blit TTL iFlash", "sku": "00381218",
         "offers": {"@type": "AggregateOffer", "lowPrice": 475.9, "highPrice": 475.9,
                    "priceCurrency": "RON", "offerCount": 1,
                    "offers": [{"@type": "Offer", "price": 475.9, "priceCurrency": "RON",
                                "availability": "http://schema.org/InStock",
                                "sku": "00381218",
                                "seller": {"@type": "Organization", "name": "F64"}}]}}
    """))

    res = parse_product_html(html, URL)

    assert res["price"] == 475.9
    assert res["currency"] == "RON"
    assert res["is_aggregate"] is True
    assert res["in_stock"] is True, "stocul vine din oferta imbricata, nu din agregat"


def test_aggregate_offer_stoc_imbricat_epuizat():
    """Toate ofertele imbricate epuizate -> False, nu None: informatia EXISTA."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Blit epuizat",
         "offers": {"@type": "AggregateOffer", "lowPrice": 100.0, "priceCurrency": "RON",
                    "offers": [{"@type": "Offer", "price": 100.0,
                                "availability": "http://schema.org/OutOfStock"}]}}
    """))

    assert parse_product_html(html, URL)["in_stock"] is False


def test_aggregate_offer_stoc_imbricat_necunoscut_ramane_none():
    """Nicio disponibilitate publicata -> None. Nu se inventeaza un True."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Blit fara stoc declarat",
         "offers": {"@type": "AggregateOffer", "lowPrice": 100.0, "priceCurrency": "RON",
                    "offers": [{"@type": "Offer", "price": 100.0}]}}
    """))

    assert parse_product_html(html, URL)["in_stock"] is None


def test_aggregate_offer_availability_pe_agregat_are_precedenta():
    """Cand agregatul DECLARA disponibilitatea, ea castiga — coborarea in ofertele
    imbricate e doar plasa pentru cazul in care agregatul tace."""
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs cu stoc pe agregat",
         "offers": {"@type": "AggregateOffer", "lowPrice": 100.0, "priceCurrency": "RON",
                    "availability": "http://schema.org/OutOfStock",
                    "offers": [{"@type": "Offer", "price": 100.0,
                                "availability": "http://schema.org/InStock"}]}}
    """))

    assert parse_product_html(html, URL)["in_stock"] is False


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


# ── BR-1: price_selector pe purtator fara text (meta content=) ────────────────

def test_price_selector_din_meta_content(monkeypatch):
    """Cand elementul selectat n-are text, pretul se citeste din `content`.

    Cazul makeup.ro: purtatorul e un <meta itemprop="price">, iar pagina are mai
    multe (unul principal + unul per varianta de culoare), deci regula de siguranta
    din microdata refuza pe ambiguitate si baza ramane FARA pret. Selectorul
    dezambiguizeaza, dar are ce citi doar din atribut.
    """
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-meta.ro",
                        {"price_selector": ".principal [itemprop='price']"})
    corp = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<h1 itemprop="name">Fond de ten Test</h1>'
        '<div class="principal" itemprop="offers" itemscope '
        'itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="49.29">'
        '<meta itemprop="priceCurrency" content="RON">'
        '</div>'
        '<div class="varianta"><meta itemprop="price" content="55.29"></div>'
        '<div class="varianta"><meta itemprop="price" content="54.48"></div>'
        '</div>'
    )

    # Fara override, ambiguitatea de pret face pagina neextractibila.
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_page(body=corp), "https://alt-magazin.ro/p/1")
    assert exc.value.reason == "no_product_data"

    res = parse_product_html(_page(body=corp), "https://magazin-meta.ro/p/1")

    assert res["price"] == 49.29           # cel principal, nu al vreunei variante
    assert res["currency"] == "RON"
    assert res["override_applied"] is True

    # Garda: cand elementul ARE text de pret, textul castiga si `content` se
    # ignora — extensia nu poate schimba sursa niciunui override existent.
    monkeypatch.setitem(ppe.DOMAIN_OVERRIDES, "magazin-meta.ro",
                        {"price_selector": "span.pret"})
    html = _page(head=_ld("""
        {"@type": "Product", "name": "Produs cu pret afisat",
         "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "RON"}}
    """), body='<span class="pret" content="999.00">1.234,00 lei</span>')

    res = parse_product_html(html, "https://magazin-meta.ro/p/2")

    assert res["price"] == 1234.0


def test_makeup_pe_fragment_real():
    """Fragmentul din dump-ul G4b (makeup.ro/product/181283/, redus la esential),
    trecut prin override-ul de PRODUCTIE. Structura pastrata verbatim: containerul
    principal e el insusi scope-ul Offer si isi poarta pretul ca meta, iar fiecare
    varianta de culoare are al ei — de aici cele 11 elemente itemprop=price din
    pagina reala. Clasele au sufixe generate la build (shop_1hy48pa_l3p3ge), deci
    selectorul se ancoreaza pe partea stabila a numelui.

    BR-1b: selectorul e pe COPIL DIRECT. Variantele fiind nested in container, forma
    cu descendenti se potrivea cu toate (11 pe pagina asta) si se baza pe faptul ca
    prima din document e cea principala — corect azi, fragil la orice reordonare de
    template. Copilul direct e unic prin constructie, iar asertia de mai jos o
    verifica pe fragmentul real, cu selectorul CITIT DIN REGISTRU.
    """
    from bs4 import BeautifulSoup

    selector = ppe.DOMAIN_OVERRIDES["makeup.ro"]["price_selector"]
    assert ppe.DOMAIN_OVERRIDES["makeup.ro"] == {
        "price_selector": '[class*="ProductBuySection__container"] > [itemprop="price"]'}

    corp = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<h1 class="ProductInformation__title shop_ewhpz6_1wdcs99" itemprop="name">'
        'Paese Long Cover Fluid</h1>'
        '<div class="ProductBuySection__container shop_1hy48pa_l3p3ge" '
        'itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="49.29">'
        '<meta itemprop="priceCurrency" content="RON">'
        '<link itemprop="availability" href="https://schema.org/InStock">'
        '<div class="ProductBuySection__variant shop_16hrxvi_l3p3ge">'
        '<div class="ProductBuySection__title shop_1v5nkdl_l3p3ge">02 - Natural</div>'
        '<meta itemprop="name" content="Fond de ten - Paese Long Cover Fluid  02 - Natural">'
        '<meta itemprop="price" content="55.29">'
        '<meta itemprop="priceCurrency" content="RON">'
        '</div>'
        '<div class="ProductBuySection__variant shop_16hrxvi_l3p3ge">'
        '<div class="ProductBuySection__title shop_1v5nkdl_l3p3ge">4.5 - Toffee</div>'
        '<meta itemprop="name" content="Fond de ten - Paese Long Cover Fluid  4.5 - Toffee">'
        '<meta itemprop="price" content="54.48">'
        '<meta itemprop="priceCurrency" content="RON">'
        '</div>'
        '</div></div>'
    )

    # Determinist, nu "primul din document": o singura potrivire pe tot fragmentul.
    potriviri = BeautifulSoup(_page(body=corp), "html.parser").select(selector)
    assert len(potriviri) == 1, f"selectorul da {len(potriviri)} potriviri, nu una"
    assert potriviri[0].get("content") == "49.29"

    res = parse_product_html(_page(body=corp), "https://makeup.ro/product/181283/")

    assert res["price"] == 49.29
    assert res["currency"] == "RON"
    # Numele vine din microdata: singurul itemprop="name" al Product-ului INSUSI
    # (cele ale variantelor apartin scope-urilor lor, filtrate de _in_scope).
    assert res["name"] == "Paese Long Cover Fluid"
    assert res["override_applied"] is True
    assert res["domain"] == "makeup.ro"


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


def test_offers_lista_fara_size_da_minimul_nu_primul():
    """REGRESIE PINUITA (forma sneakersnstuff), REVIZUITA la G2F-4.

    Fara `size` pe niciun element, `_variants_from_offer_list` refuza forma si
    nu se fabrica variante — asta ramane. Ce s-a schimbat e ALEGEREA pretului:
    pana la G2F-4 castiga PRIMUL element cotat (aici 149.99, epuizat), fiindca
    ordinea listei era luata drept semnificativa; acum castiga MINIMUL (99.99),
    ca la `lowPrice` si ca la minimul marimilor. Stocul si moneda vin de la
    oferta care a castigat, nu de la prima — altfel pretul ar fi al unei
    variante si disponibilitatea a alteia.
    """
    html = _offers_page([
        _offer(None, 149.99, "OutOfStock"),
        _offer(None, 99.99, "InStock"),
    ])

    res = parse_product_html(html, "https://www.sneakersnstuff.com/p/x")

    assert res["variants"] is None
    assert res["price"] == 99.99            # MINIMUL, nu primul element
    assert res["in_stock"] is True          # stocul ofertei castigatoare
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


# ── DISCOVERY-2: microdata CAMELCASE (forma footshop.ro) ─────────────────────

def test_microdata_camelcase_este_citita():
    """footshop.ro emite atributele camelCase (SSR React): itemProp/itemScope/itemType.

    Pe HTML brut `itemprop` da 0 potriviri si `itemProp` 41 — exact capcana care a
    facut ca FASHION-2 sa clasifice site-ul drept CSR. BeautifulSoup normalizeaza
    numele atributelor la lowercase cand parseaza HTML, deci selectorii merg; testul
    pinuieste asta, fiindca e o proprietate a parserului, nu a codului nostru.

    Forma reprodusa e cea reala: `content` pe pretul curent, availability ca <link
    href>, iar pretul TAIAT fara itemProp (deci imposibil de confundat).
    """
    html = _page(body="""
        <div itemScope="" itemType="https://schema.org/Product">
          <h1 itemProp="name">Nike Air Force 1</h1>
          <div class="_priceWrapper" itemProp="offers" itemScope=""
               itemType="https://schema.org/Offer">
            <link itemProp="availability" href="https://schema.org/InStock"/>
            <div class="_price _hasSale" itemProp="price" content="501">
              <strong class="_priceValue">501 RON</strong><span>cu TVA</span></div>
            <div class="_price"><span class="_retailPriceValue">589 RON</span>
              <span class="_retailPriceSale">-15 %</span></div>
            <meta itemProp="priceCurrency" content="RON"/>
          </div>
        </div>""")

    assert "itemprop" not in html          # chiar asa arata pagina reala
    data = parse_product_html(html, URL)

    assert data["price"] == 501.0          # curentul, nu 589 (taiatul n-are itemProp)
    assert data["currency"] == "RON"
    assert data["in_stock"] is True        # din <link ... href>, nu din content
    assert data["method"] == "microdata"


# ── DISCOVERY-2: extractorul custom asos.com ─────────────────────────────────

ASOS_URL = "https://www.asos.com/nike/nike-p-6000-trainers/prd/209724066"

_ASOS_PAGINA = _page(head=_ld("""
    {"@context": "https://schema.org", "@type": "Product",
     "name": "Nike P-6000 trainers in off white suede", "sku": "209724066",
     "brand": {"@type": "Brand", "name": "Nike"}}
""") + '<meta property="og:image" content="https://images.asos.com/p6000.jpg"/>')

_ASOS_API = json.dumps([
    {"productId": 205774480,                       # alt produs, PRIMUL in lista
     "productPrice": {"current": {"value": 19.5, "text": "19.50"}, "currency": "EUR"},
     "isInStock": True},
    {"productId": 209724066,
     "productPrice": {"current": {"value": 119.99, "text": "119.99"}, "currency": "EUR"},
     "isInStock": True},
])


@pytest.fixture
def asos_gate(monkeypatch):
    """Poarta guarded falsa: inregistreaza URL-urile si serveste raspunsuri la rand."""
    from app.services import scraper_service

    monkeypatch.setattr(ppe.time, "sleep", lambda *_a, **_kw: None)

    def _install(*raspunsuri):
        state = {"urls": [], "calls": 0}

        def _fake(url, **_kwargs):
            state["urls"].append(url)
            index = min(state["calls"], len(raspunsuri) - 1)
            state["calls"] += 1
            corp = raspunsuri[index]
            if isinstance(corp, tuple):
                return _FakeResponse(corp[0], status_code=corp[1])
            return _FakeResponse(corp)

        monkeypatch.setattr(scraper_service, "_fetch_shop_url_guarded", _fake)
        return state

    return _install


def test_asos_extrage_din_api_ul_de_stockprice(asos_gate):
    """Cazul fericit: nume din ld+json-ul paginii, pret/moneda/stoc din API."""
    state = asos_gate(_ASOS_PAGINA, _ASOS_API)

    data = ppe.extract_product(ASOS_URL)

    assert data["name"] == "Nike P-6000 trainers in off white suede"
    assert data["price"] == 119.99          # intrarea NOASTRA, nu prima din lista
    assert data["currency"] == "EUR"
    assert data["in_stock"] is True
    assert data["method"] == "asos_stockprice"
    assert data["domain"] == "asos.com"

    # AMBELE fetch-uri trec prin poarta guarded, si al doilea e API-ul cu codurile RO.
    assert state["calls"] == 2
    assert state["urls"][0] == ASOS_URL
    assert "/api/product/catalogue/v4/stockprice" in state["urls"][1]
    assert "productIds=209724066" in state["urls"][1]
    for cod in ("store=ROE", "currency=EUR", "country=RO"):
        assert cod in state["urls"][1]


def test_asos_url_fara_prd_nu_face_niciun_fetch(asos_gate):
    """Id-ul vine din cale; fara el nu avem ce cere, deci nici nu iesim pe retea."""
    state = asos_gate(_ASOS_PAGINA, _ASOS_API)

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product("https://www.asos.com/women/ctas/cat/?cid=4169")

    assert exc.value.reason == "no_product_data"
    assert state["calls"] == 0


def test_asos_produsul_lipseste_din_raspuns(asos_gate):
    """Lista poate contine doar recomandari. Fara intrarea noastra NU ghicim —
    primul element ar fi pretul altui produs (capcana masurata la DISCOVERY-1)."""
    fara_noi = json.dumps([{"productId": 111111,
                            "productPrice": {"current": {"value": 19.5}, "currency": "EUR"},
                            "isInStock": True}])
    asos_gate(_ASOS_PAGINA, fara_noi)

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(ASOS_URL)

    assert exc.value.reason == "no_product_data"


def test_asos_json_invalid(asos_gate):
    asos_gate(_ASOS_PAGINA, "<html>nu e json</html>")

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(ASOS_URL)

    assert exc.value.reason == "no_product_data"


def test_asos_pret_zero_e_invalid_price(asos_gate):
    zero = json.dumps([{"productId": 209724066,
                        "productPrice": {"current": {"value": 0}, "currency": "EUR"},
                        "isInStock": True}])
    asos_gate(_ASOS_PAGINA, zero)

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(ASOS_URL)

    assert exc.value.reason == "invalid_price"


def test_asos_challenge_pe_api(asos_gate):
    """403 pe al doilea fetch = challenge, acelasi reason ca in fluxul generic."""
    asos_gate(_ASOS_PAGINA, ("Just a moment...", 403))

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(ASOS_URL)

    assert exc.value.reason == "challenge"


# ── DISCOVERY-2: dispatch-ul registrului ─────────────────────────────────────

def test_dispatch_trimite_asos_la_extractorul_custom(monkeypatch):
    """Un URL asos.com NU trebuie sa intre in fluxul HTML generic."""
    apeluri = []

    def _fals(url):
        apeluri.append(url)
        return {"price": 1.0, "method": "asos_stockprice"}

    monkeypatch.setitem(ppe.CUSTOM_EXTRACTORS, "asos.com", _fals)

    assert ppe.extract_product(ASOS_URL)["method"] == "asos_stockprice"
    assert apeluri == [ASOS_URL]


def test_dispatch_nu_atinge_domeniile_fara_extractor(fetch_mock):
    """emag.ro nu e in registru, deci merge pe fluxul generic, neschimbat."""
    state = fetch_mock(_HTML_OK)

    res = ppe.extract_product("https://www.emag.ro/produs/pd/XYZ/")

    assert res["method"] == "jsonld"
    assert state["calls"] == 1


@pytest.mark.parametrize("url,asteptat", [
    ("https://www.asos.com/x/prd/1", True),
    ("https://asos.com/x/prd/1", True),
    ("https://marketplace.asos.com/x/prd/1", True),          # subdomeniu legitim
    ("https://evil-asos.com.attacker.com/x/prd/1", False),   # sufix inselator
    ("https://www.emag.ro/x", False),
    ("not a url", False),
])
def test_custom_extractor_for_e_suffix_safe(url, asteptat):
    assert (ppe._custom_extractor_for(url) is not None) is asteptat


# ── DISCOVERY-2: domeniile noi in allow-list-ul C-14 ─────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.footshop.ro/ro/categorie/98497-produs.html",
    "https://footshop.ro/ro/categorie/98497-produs.html",
    "https://www.asos.com/nike/produs/prd/209724066",
])
def test_domeniile_discovery2_sunt_permise(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is True


@pytest.mark.parametrize("url", [
    "https://evil-footshop.ro.attacker.com/p",
    "https://footshop.ro.attacker.com/p",
    "https://asos.com.attacker.com/prd/1",
])
def test_sufixele_inselatoare_discovery2_raman_respinse(url):
    from app.services.scraper_service import _is_allowed_shop_url

    assert _is_allowed_shop_url(url) is False


# ── LOT1: scoparea nested pe nume + preturi duale cu/fara TVA ─────────────────

def test_microdata_scopare_nested():
    """Forma pcgarage: numele produsului convietuieste cu cel al brandului.

    Brandul e un obiect NESTED cu propriul `itemscope`, deci poarta si el un
    `itemprop="name"`. Inainte de LOT1, regula "un singur candidat sau h1-ul" vedea
    doi candidati si niciun h1, deci intorcea None si domeniul cadea pe
    no_product_data — desi pretul era acolo, corect.
    """
    html = _page(body='<div itemscope itemtype="http://schema.org/Product">'
                      '<td itemprop="name">Procesor AMD Ryzen 7 9800X3D</td>'
                      '<div itemscope itemtype="http://schema.org/Brand">'
                      '<meta itemprop="name" content="AMD"/></div>'
                      '<div itemscope itemtype="http://schema.org/Offer">'
                      '<meta itemprop="priceCurrency" content="RON"/>'
                      '<meta itemprop="price" content="2249.990039"/>'
                      '<link itemprop="availability" href="https://schema.org/InStock"/>'
                      '</div></div>')

    res = parse_product_html(html, "https://www.pcgarage.ro/procesoare/amd/test/")

    assert res["name"] == "Procesor AMD Ryzen 7 9800X3D"
    assert res["price"] == 2249.990039
    assert res["currency"] == "RON"
    assert res["in_stock"] is True
    assert res["method"] == "microdata"

    # Caz-limita: TOATE numele stau in scope-uri nested -> lista filtrata e goala,
    # deci regula "un singur candidat" nu are ce alege si numele ramane None.
    fara_nume = _page(body='<div itemscope itemtype="http://schema.org/Product">'
                           '<div itemscope itemtype="http://schema.org/Brand">'
                           '<meta itemprop="name" content="AMD"/></div>'
                           '<meta itemprop="price" content="99.00"/></div>')
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(fara_nume, "https://www.pcgarage.ro/x/")
    assert exc.value.reason == "no_product_data"


def _senetic(*, net="3394.59", brut="4107.45") -> str:
    """Forma senetic: ld+json poarta NETUL, microdata BRUTUL (raport 1.21 = TVA)."""
    return _page(
        head=_ld(json.dumps({
            "@context": "https://schema.org", "@type": "Product",
            "name": "Monitor Dell U4025QW",
            "offers": {"@type": "Offer", "price": net, "priceCurrency": "RON",
                       "availability": "https://schema.org/InStock"},
        })),
        body='<div itemscope itemtype="http://schema.org/Product">'
             '<h1 itemprop="name">Monitor Dell U4025QW</h1>'
             '<div itemscope itemtype="http://schema.org/Offer">'
             f'<meta itemprop="price" content="{brut}"/>'
             '</div></div>')


def test_vat_prices_variante_duale(monkeypatch):
    monkeypatch.setitem(DOMAIN_OVERRIDES, "senetic.ro", {"vat_prices": True})

    res = parse_product_html(_senetic(), "https://www.senetic.ro/product/DELL-U4025QW")

    # Pretul principal devine BRUTUL — comparabilul de consumator.
    assert res["price"] == 4107.45
    assert res["variants"] == [
        {"variant": "cu TVA", "price": 4107.45, "in_stock": True},
        {"variant": "fara TVA", "price": 3394.59, "in_stock": True},
    ]
    assert res["override_applied"] is True


def test_vat_prices_garda(monkeypatch):
    """Garda de sens: fara un brut STRICT mai mare ca netul, flag-ul nu face nimic."""
    monkeypatch.setitem(DOMAIN_OVERRIDES, "senetic.ro", {"vat_prices": True})
    URL_SEN = "https://www.senetic.ro/product/X"

    # microdata <= jsonld: nu e raport de TVA, deci comportament normal.
    res = parse_product_html(_senetic(net="4107.45", brut="3394.59"), URL_SEN)
    assert res["price"] == 4107.45      # pretul din ld+json, ca pana acum
    assert res["variants"] is None
    assert res["override_applied"] is False

    # microdata lipseste cu totul -> la fel.
    fara_micro = _page(head=_ld(
        '{"@context": "https://schema.org", "@type": "Product", "name": "X",'
        ' "offers": {"@type": "Offer", "price": "100.00", "priceCurrency": "RON"}}'))
    res = parse_product_html(fara_micro, URL_SEN)
    assert res["price"] == 100.0
    assert res["variants"] is None
    assert res["override_applied"] is False


# ── LOT2: eticheta compusa pentru variatia multi-dimensionala ─────────────────

def _grup(*, varies=None, variante=()) -> str:
    """ProductGroup in forma bergfreunde: hasVariant + variesBy optional."""
    grup = {"@context": "https://schema.org", "@type": "ProductGroup",
            "name": "Tricou Merino", "hasVariant": list(variante)}
    if varies is not None:
        grup["variesBy"] = varies
    return _page(head=_ld(json.dumps(grup)))


def _var(pret, *, disponibil=True, **dimensiuni) -> dict:
    return {"@type": "Product", "name": f"Tricou {dimensiuni}", **dimensiuni,
            "offers": {"@type": "Offer", "price": pret, "priceCurrency": "EUR",
                       "availability": ("https://schema.org/InStock" if disponibil
                                        else "https://schema.org/OutOfStock")}}


def test_eticheta_compusa_bidimensionala():
    """Forma bergfreunde: variesBy [size, color], preturi diferite pe culoare.

    Etichetate doar cu `size`, cele trei "S" ar fi fost NEunice, iar selectia
    per-varianta din add-by-link (care ia prima potrivire) ar fi dat tacut pretul
    si stocul altei culori.
    """
    html = _grup(
        varies=["https://schema.org/size", "https://schema.org/color"],
        variante=[
            _var("67.96", size="S", color="Olive Green", disponibil=True),
            _var("67.96", size="S", color="Summer Blue", disponibil=False),
            _var("63.96", size="S", color="Timber Red", disponibil=False),
            _var("71.96", size="M", color="Olive Green", disponibil=True),
        ])

    res = parse_product_html(html, "https://www.bergfreunde.eu/tricou/")

    etichete = [v["variant"] for v in res["variants"]]
    # Ordinea partilor o da `variesBy`, nu alfabetul.
    assert etichete == ["S / Olive Green", "S / Summer Blue", "S / Timber Red",
                        "M / Olive Green"]
    assert len(set(etichete)) == len(etichete), "etichetele trebuie sa fie UNICE"
    # Agregatul ramane regula existenta: minimul marimilor IN STOC (63.96 e epuizat).
    assert res["price"] == 67.96
    assert res["is_aggregate"] is True


def test_eticheta_compusa_garda_monodimensionala():
    """Cu o singura dimensiune sau fara `variesBy`, eticheta ramane cea de azi."""
    variante = [_var("67.96", size="S", color="Olive Green"),
                _var("71.96", size="M", color="Summer Blue")]

    o_dimensiune = parse_product_html(
        _grup(varies=["https://schema.org/size"], variante=variante), URL)
    assert [v["variant"] for v in o_dimensiune["variants"]] == ["S", "M"]

    # `variesBy` absent — forma eobuwie/About You, pinuita de testele existente.
    fara = parse_product_html(_grup(variante=variante), URL)
    assert [v["variant"] for v in fara["variants"]] == ["S", "M"]

    # `variesBy` neparsabil (nu e string) — tot pe comportamentul de azi.
    neparsabil = parse_product_html(_grup(varies=[{"x": 1}, 42], variante=variante), URL)
    assert [v["variant"] for v in neparsabil["variants"]] == ["S", "M"]


def test_eticheta_compusa_parti_lipsa():
    html = _grup(
        varies=["https://schema.org/size", "https://schema.org/color"],
        variante=[
            _var("10.0", size="S", color="Olive Green"),
            _var("11.0", size="M"),                       # fara culoare -> doar marimea
            _var("12.0", color="Timber Red"),             # fara marime -> doar culoarea
            _var("13.0"),                                 # niciuna -> plasa _variant_label
            _var("14.0", size=42, color="Black"),         # numeric, ca la `size`
        ])

    res = parse_product_html(html, URL)
    etichete = [v["variant"] for v in res["variants"]]

    assert etichete[0] == "S / Olive Green"
    assert etichete[1] == "M"
    assert etichete[2] == "Timber Red"
    # Fara nicio dimensiune, cade pe _variant_label -> `size` lipsa, deci numele.
    assert etichete[3] == "Tricou {}"
    assert etichete[4] == "42 / Black"


# ── LOT3: variesBy monodimensional + pin pe forma reala otter ─────────────────

def test_variesby_o_dimensiune():
    """C2 — compunerea porneste si la o singura dimensiune declarata.

    Pe `[size]` rezultatul e identic cu cel de dinainte. Ce castiga extinderea e
    cazul NON-size: boozt/booztlet declara `variesBy: [color]`, iar fara compunere
    eticheta cadea pe plasa de nume — numele intreg al produsului in loc de culoare.
    """
    culori = _grup(
        varies=["https://schema.org/color"],
        variante=[_var("195.0", color="CHERRY RED", size=None),
                  _var("195.0", color="WHITE", size=None)])
    res = parse_product_html(culori, "https://www.boozt.com/eu/en/x")
    assert [v["variant"] for v in res["variants"]] == ["CHERRY RED", "WHITE"]

    # Garda: pe `[size]` singur, exact ce dadea si inainte de extindere.
    marimi = _grup(varies=["https://schema.org/size"],
                   variante=[_var("67.96", size="S", color="Olive Green"),
                             _var("71.96", size="M", color="Summer Blue")])
    assert [v["variant"] for v in parse_product_html(marimi, URL)["variants"]] == ["S", "M"]

    # Garda: `variesBy` absent -> plasa de nume, neschimbata.
    fara = _grup(variante=[_var("10.0", size="S"), _var("11.0", size="M")])
    assert [v["variant"] for v in parse_product_html(fara, URL)["variants"]] == ["S", "M"]


def test_forma_otter_ramane_pe_calea_grupului():
    """PIN pe forma REALA otter.ro, masurata la LOT3b.

    Raportul LOT3b a descris gresit forma ca "Product-uri FRATI cu sku comun" —
    doua artefacte ale sondei: walker-ul ei recursiv numara variantele NESTED ca
    obiecte de nivel inalt, iar print-ul de diagnostic trunchia sku-ul la 14
    caractere, deci sku-uri distincte pareau identice. Masurat corect, otter e
    FASHION-1b curat: `_iter_jsonld_objects` vede UN singur obiect (ProductGroup),
    variantele ies din `hasVariant`, iar sku-urile difera de la o marime la alta.
    Testul pinuieste asta ca eroarea sa nu se repete si sa nu justifice cod nou.
    """
    def _marime(sku, size, pret, disponibil=True):
        return {"@type": "Product", "name": f"Pantofi SKECHERS kaki, din {size}",
                "sku": sku, "size": size,
                "offers": {"@type": "Offer", "price": pret, "priceCurrency": "RON",
                           "availability": ("https://schema.org/InStock" if disponibil
                                            else "https://schema.org/OutOfStock")}}

    marimi = [
        _marime("KZNZ40111BK220613923", "45", "409.00"),
        _marime("KZNZ40111BK220613918", "42 ½", "409.00"),
        _marime("KZNZ40111BK220613913", "40", "389.00", disponibil=False),
    ]
    # Sku-urile DIFERA intre marimi — presupunerea de "sku comun" era falsa, si e
    # motivul pentru care o activare pe sku partajat n-ar fi pornit niciodata aici.
    assert len({m["sku"] for m in marimi}) == 3

    html = _page(head=_ld(json.dumps({
        "@context": "https://schema.org", "@type": "ProductGroup",
        "name": "Pantofi sport SKECHERS kaki, 220613, din material textil",
        "sku": "KZNZ40111BK2206139", "productGroupID": "KZNZ40111BK2206139",
        "variesBy": ["https://schema.org/size"],
        "hasVariant": marimi,
    })))

    res = parse_product_html(html, "https://www.otter.ro/pantofi-sport-skechers")

    # Numele CURAT vine de la grup, nu de la vreo varianta ("... din 45").
    assert res["name"] == "Pantofi sport SKECHERS kaki, 220613, din material textil"
    assert [v["variant"] for v in res["variants"]] == ["45", "42 ½", "40"]
    # Agregatul e minimul marimilor IN STOC: 389.00 e epuizat, deci nu castiga.
    assert res["price"] == 409.0
    assert res["is_aggregate"] is True


# ── LOT4: moneda din priceSpecification ──────────────────────────────────────

def _parfumdreams(*, moneda_oferta=None, moneda_spec="EUR", pret=59.9) -> str:
    """Forma parfumdreams: oferta poarta pretul si moneda DOAR in priceSpecification.

    `moneda_oferta` seteaza si un `priceCurrency` la nivelul ofertei, pentru garda
    de neutralitate; None = exact forma masurata la LOT4.
    """
    oferta = {"@type": "Offer", "size": "50 ml",
              "availability": "https://schema.org/InStock",
              "priceSpecification": {"@type": "UnitPriceSpecification",
                                     "price": pret}}
    if moneda_spec is not None:
        oferta["priceSpecification"]["priceCurrency"] = moneda_spec
    if moneda_oferta is not None:
        oferta["priceCurrency"] = moneda_oferta
    return _page(head=_ld(json.dumps({
        "@context": "https://schema.org", "@type": "ProductGroup",
        "name": "Issey Miyake L'Eau d'Issey Eau Essentielle",
        "variesBy": ["https://schema.org/size"],
        "hasVariant": [{"@type": "Product", "sku": "1284803", "size": "50 ml",
                        "name": "L'Eau d'Issey Eau Essentielle 50 ml",
                        "offers": oferta}],
    })))


def test_moneda_din_price_specification():
    """Fara fix, moneda cadea pe implicitul romanesc si 59.90 EUR devenea 59.90 RON
    — produsul parea de ~5 ori mai ieftin decat e."""
    res = parse_product_html(_parfumdreams(), "https://www.parfumdreams.de/x")

    assert res["currency"] == "EUR"
    assert res["price"] == 59.9          # pretul NU se schimba prin fix
    assert [v["variant"] for v in res["variants"]] == ["50 ml"]


def test_moneda_price_specification_garda():
    # Nivelul ofertei CASTIGA cand isi declara propria moneda — neutralitate pe
    # domeniile deja validate, care o publica acolo.
    res = parse_product_html(_parfumdreams(moneda_oferta="USD", moneda_spec="EUR"),
                             "https://www.parfumdreams.de/x")
    assert res["currency"] == "USD"

    # Fara moneda nicaieri -> implicitul de azi, neschimbat.
    res = parse_product_html(_parfumdreams(moneda_spec=None), URL)
    assert res["currency"] == "RON"
    assert res["price"] == 59.9


# ── ELF-2: extractorul custom Intershop pentru elefant.ro ────────────────────
#
# Fixture-urile NU sunt sintetice: sunt fragmente taiate VERBATIM din dump-urile
# sondelor ELF-1/ELF-1b (bloc de pret + zona butonului + payload GTM), pastrand
# inclusiv capcanele masurate acolo — bara sticky cu ambele butoane ascunse si
# butonul de cos prezent pe produsul indisponibil. Singura exceptie e marcata
# explicit in numele fisierului (`_SINTETIC`).

_ELEFANT_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "elefant")

# URL-uri reale, din meta-urile dump-urilor.
ELEFANT_URL_REDUS = ("https://www.elefant.ro/"
                     "marea-carte-de-colorat-si-activitati-dorinta_"
                     "e51b5fde-7f5b-432c-9976-79bca49eb88d")
ELEFANT_URL_NEREDUS = ("https://www.elefant.ro/puzzle-d-toys-tropical-240-piese_"
                       "7fcfa5a6-a268-41bb-9558-141c135572e3")
ELEFANT_URL_EPUIZAT = ("https://www.elefant.ro/INTERSHOP/web/WFS/"
                       "elefant-elefantRO-Site/ro_RO/-/RON/ViewProduct-Start"
                       "?SKU=7bf57638-e749-4309-870a-146746b44648")


def _elefant_fixture(nume: str) -> str:
    with open(os.path.join(_ELEFANT_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fisier,url,pret,nume", [
    ("prod_redus.html", ELEFANT_URL_REDUS, 19.31,
     "Marea carte de colorat si activitati. Dorinta"),
    ("prod_neredus.html", ELEFANT_URL_NEREDUS, 89.99,
     "Puzzle D-Toys - Tropical, 240 piese"),
    ("prod_epuizat.html", ELEFANT_URL_EPUIZAT, 10.99, "Spirala magica"),
])
def test_elefant_extrage_pret_moneda_si_stoc_necunoscut(fetch_mock, fisier, url, pret, nume):
    """Cele trei stari masurate: redus, neredus si clasat INDISPONIBIL de catalog.

    Toate trei dau pret + moneda din acelasi atribut, si toate trei dau
    `in_stock=None` — inclusiv cea epuizata. Asta NU e o scapare: ELF-1b a
    masurat ca pagina produsului indisponibil e identica cu a unuia in stoc.
    """
    state = fetch_mock(_elefant_fixture(fisier))

    data = ppe.extract_product(url)

    assert data["price"] == pret
    assert data["currency"] == "RON"
    assert data["name"] == nume
    assert data["in_stock"] is None
    assert data["method"] == "elefant_intershop"
    assert data["domain"] == "elefant.ro"
    assert data["is_aggregate"] is False
    # UN singur fetch, si acela prin poarta guarded C-14.
    assert state["calls"] == 1


def test_elefant_nu_deduce_stocul_din_butoane_desi_exista_in_pagina(fetch_mock):
    """Anti-regresie pe capcanele enumerate in comentariul extractorului.

    Fixture-ul produsului INDISPONIBIL contine si butonul de adaugare in cos, si
    bara sticky cu 'Indisponibil' — exact semnalele care par a spune stocul.
    Daca cineva 'repara' extractorul citindu-le, testul asta cade.
    """
    html = _elefant_fixture("prod_epuizat.html")
    assert 'data-testing-id="addToCartButton"' in html
    assert 'name="StickyNotAvailable"' in html

    fetch_mock(html)

    assert ppe.extract_product(ELEFANT_URL_EPUIZAT)["in_stock"] is None


def test_elefant_rezerva_gtm_da_pretul_dar_nu_inventeaza_moneda(fetch_mock):
    """Fara ancora primara se cade pe payload-ul GTM, care n-are moneda.

    Moneda ramane None DELIBERAT: pagina din care a disparut `current-price` e o
    pagina schimbata, iar un 'RON' presupus ar ascunde tocmai schimbarea.
    """
    html = _elefant_fixture("prod_fara_testingid_SINTETIC.html")
    assert 'data-price-currencymnemonic="RON"' in html   # RON E in pagina...

    fetch_mock(html)
    data = ppe.extract_product(ELEFANT_URL_REDUS)

    assert data["price"] == 19.31                        # ...pretul vine din GTM
    assert data["currency"] is None                      # ...dar moneda NU se presupune
    assert data["method"] == "elefant_intershop"
    assert data["in_stock"] is None


@pytest.mark.parametrize("text,asteptat", [
    ("19,31 lei", 19.31),
    ("89,99 lei", 89.99),
    ("1.603,00\xa0lei", 1603.0),          # mii cu punct + nbsp, ca in pagina
    ("  10,99   lei  ", 10.99),
    ("100 lei", 100.0),                    # pret rotund, fara zecimale
    ("39,99 lei19,31 lei", None),          # doua preturi lipite -> esec curat
    ("Pret la cerere", None),
    ("", None),
    (None, None),
])
def test_parse_pret_elefant_strict(text, asteptat):
    """Parserul acopera formatul MASURAT si refuza restul, fara reparatii tacute."""
    assert ppe._parse_pret_elefant(text) == asteptat


def test_elefant_fara_nicio_sursa_de_pret_ridica_no_product_data(fetch_mock):
    """Ambele ramuri esuate -> eroarea standard a extractoarelor."""
    # SINTETIC: pagina pastreaza numele, dar nu are nici testing-id, nici GTM.
    fetch_mock("<html><body><h1>Produs fara pret</h1></body></html>")

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product(ELEFANT_URL_REDUS)
    assert exc.value.reason == "no_product_data"


def test_elefant_e_inregistrat_ca_extractor_custom():
    """Rutarea: domeniul nu mai trece prin fluxul generic, care n-are ce citi."""
    assert ppe.CUSTOM_EXTRACTORS["elefant.ro"] is ppe._extract_elefant
    assert ppe._custom_extractor_for(ELEFANT_URL_REDUS) is ppe._extract_elefant
    # si pe subdomeniu, ca la allow-list-ul C-14
    assert ppe._custom_extractor_for("https://elefant.ro/x_1") is ppe._extract_elefant


def test_elefant_fluxul_generic_chiar_nu_poate_citi_pagina():
    """Justificarea extractorului custom, verificata pe fixture-ul REAL.

    Daca elefant ar capata candva ld+json/OG, testul asta cade si intrebarea
    'mai avem nevoie de cod bespoke?' se pune singura.
    """
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_elefant_fixture("prod_redus.html"), ELEFANT_URL_REDUS)
    assert exc.value.reason == "no_product_data"


# ── G2A-2: extractorul custom OpenCart pentru powerup.ro ─────────────────────
#
# Fixture-urile sunt fragmente taiate VERBATIM din dump-urile sondei G2A-1
# (`dumps_g2a/`), pastrand capcanele masurate acolo: blocul de pret al produsului
# IMPREUNA cu dublura `.discount-price.nav-price` din bara de sus, si doua carduri
# de carusel FARA `.full-price` (produse nereduse).

_POWERUP_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "powerup")

# URL-uri reale, din meta-urile dump-urilor.
POWERUP_URL_1 = ("https://www.powerup.ro/amd-ryzen-9-9950x3d-16core-5-7ghz-rtx-5090-"
                 "32gb-gddr7-128gb-ddr5-ssd-2tb-m-2-1000w-watercooling-aio-powerup-"
                 "micro-179352")
POWERUP_URL_2 = ("https://www.powerup.ro/16-port-gigabit-desktop-switch-with-16-port-"
                 "poe-port-16-gigabit-poe-ports-spec-802-3at-af-120-w-poe-power-"
                 "desktop-steel-case-feature-extend-mode-for-250m-poe-transmitting-"
                 "priority-mode-for-port1-4-isolation-mode-poe-auto-recovery-plug-"
                 "and-play-227146")


def _powerup_fixture(nume: str) -> str:
    with open(os.path.join(_POWERUP_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fisier,url,pret", [
    ("pdp_179352.html", POWERUP_URL_1, 19990.0),
    ("pdp_227146.html", POWERUP_URL_2, 637.78),
])
def test_powerup_extrage_pret_si_moneda_din_cod(fetch_mock, fisier, url, pret):
    """Cele doua PDP-uri cu reducere reala pe care s-a transat capcana in G2A-1.

    Moneda e RON din COD — pagina n-o poarta nicaieri ca data structurata — iar
    stocul e None fiindca nicio pagina de produs epuizat n-a fost sondata.
    """
    state = fetch_mock(_powerup_fixture(fisier))

    data = ppe.extract_product(url)

    assert data["price"] == pret
    assert data["currency"] == "RON"
    assert data["in_stock"] is None
    assert data["method"] == "powerup_opencart"
    assert data["domain"] == "powerup.ro"
    assert data["is_aggregate"] is False
    assert state["calls"] == 1


def test_powerup_nu_citeste_dublura_nav_price_din_bara(fetch_mock):
    """Ancorarea in `.product-price` e ceruta de structura, nu de eleganta.

    `.discount-price` apare de DOUA ori pe pagina: o data in blocul produsului si
    o data in bara de sus, ca `.discount-price.nav-price`. Fixture-ul contine
    dublura INAINTEA blocului de produs, deci un selector neancorat ar citi-o pe
    ea. Ii dam bara o valoare vizibil diferita ca testul sa poata discrimina.
    """
    html = _powerup_fixture("pdp_179352.html")
    stricat = html.replace(
        '<span class="discount-price nav-price">',
        '<span class="discount-price nav-price">1,11 LEI</span>'
        '<span class="discount-price nav-price">', 1)
    state = fetch_mock(stricat)

    data = ppe.extract_product(POWERUP_URL_1)

    assert data["price"] == 19990.0, "pretul vine din .product-price, nu din bara"
    assert state["calls"] == 1


def test_powerup_pretul_ignora_unitatea_de_masura():
    """`.price-unit` ('/ buc.') apare doar la unele produse.

    Se scoate INAINTE de parsare: parserul e strict si ar respinge textul cu
    sufix, deci pretul s-ar pierde exact pe produsele vandute la bucata.
    """
    assert "/ buc." in _powerup_fixture("pdp_179352.html")


@pytest.mark.parametrize("brut,asteptat", [
    ("19.990,00LEI", 19990.0),        # forma masurata: zecimalele in <sup>
    ("637,78 LEI", 637.78),
    ("26.900,00LEI", 26900.0),        # pretul taiat, acelasi format
    ("19.990 ,00 LEI", 19990.0),      # get_text(" ") insereaza spatiul
    ("1.045,69 lei", 1045.69),
])
def test_powerup_parser_formele_masurate(brut, asteptat):
    assert ppe._parse_pret_powerup(brut) == asteptat


@pytest.mark.parametrize("brut", ["abc", "", "19.990", "19,9 LEI", None, 42])
def test_powerup_parser_respinge_ce_nu_e_formatul_masurat(brut):
    """Strict prin design, ca la elefant: o abatere inseamna ca pagina s-a
    schimbat, iar asta se vede ca esec curat, nu ca reparatie tacuta."""
    assert ppe._parse_pret_powerup(brut) is None


def test_powerup_fara_full_price_inseamna_produs_neredus():
    """Regula masurata pe caruselul SH: 15/15 carduri au `.discount-price`, dar
    doar 8/15 au `.full-price`. Referinta NU intra in contractul extractorului de
    pagina — dar absenta ei e semnalul „neredus", folosit de descriptorul de
    listare, deci merita pinuita pe fixture-ul real."""
    from bs4 import BeautifulSoup

    supa = BeautifulSoup(_powerup_fixture("carusel_nereduse.html"), "html.parser")
    carduri = supa.select("div.item-display-box")

    assert len(carduri) == 2
    for card in carduri:
        assert card.select_one(".discount-price") is not None
        assert card.select_one(".full-price") is None


def test_powerup_e_in_registrul_de_extractoare_custom():
    assert ppe.CUSTOM_EXTRACTORS["powerup.ro"] is ppe._extract_powerup
    assert ppe._custom_extractor_for(POWERUP_URL_1) is ppe._extract_powerup
    assert ppe._custom_extractor_for("https://powerup.ro/x-1") is ppe._extract_powerup


def test_powerup_fluxul_generic_chiar_nu_poate_citi_pagina():
    """Justificarea extractorului custom, pe fixture-ul REAL — tiparul elefant.

    Daca powerup capata candva ld+json/microdata/OG, testul cade si intrebarea
    'mai avem nevoie de cod bespoke?' se pune singura.
    """
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_powerup_fixture("pdp_179352.html"), POWERUP_URL_1)
    assert exc.value.reason == "no_product_data"


# ── G2F-2: extractorul custom pentru intersport.ro ───────────────────────────
#
# Fixture-urile sunt fragmente taiate VERBATIM din dump-urile sondei G2F-1b
# (`dumps_g2f_intersport/`), si pastreaza DELIBERAT capcana masurata acolo:
# `span.points-gain` poarta ACEEASI valoare ca pretul, dar inseamna puncte de
# fidelitate. Fara ea in fixture, testul de ancorare n-ar dovedi nimic.

_INTERSPORT_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "intersport")

# URL-uri reale, din meta-urile dump-urilor.
INTERSPORT_URL_1 = ("https://www.intersport.ro/sale/incaltaminte-sale/"
                    "jordan-pantofi-barbati-jordan-stay-loyal-3_911597/")
INTERSPORT_URL_2 = ("https://www.intersport.ro/sale/imbracaminte-sale/"
                    "adidas-costum-2p-j-3s-tiberio-ts_944648/")


def _intersport_fixture(nume: str) -> str:
    with open(os.path.join(_INTERSPORT_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fisier,url,pret", [
    ("pdp_911597.html", INTERSPORT_URL_1, 305.99),
    ("pdp_944648.html", INTERSPORT_URL_2, 169.99),
])
def test_intersport_extrage_pret_din_atribut(fetch_mock, fisier, url, pret):
    """Cele doua PDP-uri cu preturi distincte pe care s-a masurat structura.

    Moneda e RON din COD — pagina scrie „LEI" doar in textul de langa pret — iar
    stocul e None fiindca semnalele se contrazic pe aceeasi pagina (stoc per marime).
    """
    state = fetch_mock(_intersport_fixture(fisier))

    data = ppe.extract_product(url)

    assert data["price"] == pret
    assert data["currency"] == "RON"
    assert data["in_stock"] is None
    assert data["method"] == "intersport_custom"
    assert data["domain"] == "intersport.ro"
    assert data["is_aggregate"] is False
    assert state["calls"] == 1


def test_intersport_nu_citeste_punctele_de_fidelitate(fetch_mock):
    """Ancorarea in `.current-price` e ceruta de structura, nu de eleganta.

    `span.points-gain` poarta ACEEASI valoare ca pretul, dar inseamna puncte de
    fidelitate, si sta INAINTEA blocului de pret in fixture. Ii dam o valoare
    vizibil diferita: un selector neancorat ar citi-o pe ea.
    """
    html = _intersport_fixture("pdp_911597.html")
    assert "points-gain" in html, "fixture: capcana trebuie sa fie prezenta"
    stricat = html.replace("Puncte unitare acumulate:",
                           'Puncte: <span class="points-gain" '
                           'data-current-price="1,11">1,11 puncte</span>', 1)
    state = fetch_mock(stricat)

    data = ppe.extract_product(INTERSPORT_URL_1)

    assert data["price"] == 305.99, "pretul vine din .current-price, nu din puncte"
    assert state["calls"] == 1


def test_intersport_referinta_taiata_nu_intra_in_contract():
    """`span.deleted-price` (611,99) exista in pagina, dar NU e in rezultat:
    contractul extractorului de pagina poarta doar pretul platit. Referinta e
    materie pentru descriptorul de listare, la valul D."""
    html = _intersport_fixture("pdp_911597.html")

    assert "deleted-price" in html and "611,99" in html


@pytest.mark.parametrize("brut,asteptat", [
    ("305,99", 305.99),          # formatul masurat: atribut cu virgula zecimala
    ("169,99", 169.99),
    ("1.234,56", 1234.56),       # punct de mii
])
def test_intersport_parser_formele_masurate(brut, asteptat):
    assert ppe._parse_pret_intersport(brut) == asteptat


@pytest.mark.parametrize("brut", ["305.99", "abc", "", "305,9", "305", None, 42])
def test_intersport_parser_respinge_ce_nu_e_formatul_masurat(brut):
    """Strict prin design, ca la elefant si powerup: o abatere inseamna ca pagina
    s-a schimbat, iar asta se vede ca esec curat, nu ca reparatie tacuta."""
    assert ppe._parse_pret_intersport(brut) is None


def test_intersport_e_in_registrul_de_extractoare_custom():
    assert ppe.CUSTOM_EXTRACTORS["intersport.ro"] is ppe._extract_intersport
    assert ppe._custom_extractor_for(INTERSPORT_URL_1) is ppe._extract_intersport


def test_intersport_fluxul_generic_chiar_nu_poate_citi_pagina():
    """Justificarea extractorului custom, pe fixture-ul REAL.

    `itemprop="price"` EXISTA in pagina, dar e ORFAN — fara `itemscope` de Product
    in jur — deci fluxul de microdata nu-l vede. Daca intersport capata candva
    ld+json sau microdata completa, testul cade si intrebarea „mai avem nevoie de
    cod bespoke?" se pune singura.
    """
    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(_intersport_fixture("pdp_911597.html"), INTERSPORT_URL_1)
    assert exc.value.reason == "no_product_data"


# ── G2F-4: pretul pe lista de oferte = minimul; zooplus (ProductGroup) ────────

_ZOOPLUS_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "zooplus")

# URL-uri reale, din meta-urile dump-urilor sondei G2F-3.
ZOOPLUS_URL_1 = "https://www.zooplus.ro/shop/pisici/jucarii_pisici/mingiute/364856"
ZOOPLUS_URL_2 = ("https://www.zooplus.ro/shop/pisici/hrana_uscata_pisici/purizon/"
                 "pachete_de_testare/1347045")


def _zooplus_fixture(nume: str) -> str:
    with open(os.path.join(_ZOOPLUS_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


def test_zooplus_pdp1_ia_pretul_post_voucher_din_ldjson():
    """Un singur gramaj: ld+json publica pretul POST-VOUCHER, nu cel de lista.

    Masurat pe dump: corpul arata 16,90 LEI si un -20%, iar ld+json da 13,52
    (= 16,90 x 0,8). E pretul REAL PLATIBIL, deci il luam ca atare — fapt de
    exploatare, nu defect. Fixture-ul pastreaza DELIBERAT si 16,90 in textul
    vizibil: daca vreodata extractia ar aluneca pe text, testul cade aici.
    """
    res = parse_product_html(_zooplus_fixture("pdp1_364856.html"), ZOOPLUS_URL_1)

    assert res["price"] == 13.52
    assert res["currency"] == "RON"
    assert res["method"] == "jsonld"
    assert res["in_stock"] is True
    assert [v["price"] for v in res["variants"]] == [13.52]


def test_zooplus_pdp2_pretul_e_minimul_gramajelor_in_stoc():
    """Zece gramaje sub un ProductGroup: pretul produsului e minimul celor in stoc.

    ATENTIE la forma reala, masurata: zooplus NU e un `Product` cu offers-lista,
    ci un `ProductGroup` cu `hasVariant`, fiecare varianta cu propriul Offer.
    Prin urmare pretul iese din `_aggregate_variants` — regula care exista de la
    FASHION-1 — nu din calea de lista atinsa la G2F-4. Al zecelea gramaj e tot
    4,90 dar EPUIZAT, deci minimul in stoc coincide aici cu minimul global.
    """
    res = parse_product_html(_zooplus_fixture("pdp2_1347045.html"), ZOOPLUS_URL_2)

    assert res["price"] == 4.9
    assert res["currency"] == "RON"
    assert res["method"] == "jsonld"
    assert res["in_stock"] is True
    assert len(res["variants"]) == 10
    assert min(v["price"] for v in res["variants"] if v["in_stock"]) == 4.9


def test_zooplus_pdp2_ordinea_variantelor_nu_schimba_pretul():
    """Aceleasi zece gramaje, ordinea `hasVariant` INVERSATA — acelasi pret.

    Inversiunea se face aici, pe fixture-ul real, nu intr-un al doilea fisier de
    45 KB. Garda tine calea variantelor independenta de ordinea de serializare,
    exact proprietatea pe care G2F-4 o cere si pe calea de lista.
    """
    brut = _zooplus_fixture("pdp2_1347045.html")
    inceput = brut.index(">", brut.index("application/ld+json")) + 1
    sfarsit = brut.index("</script>", inceput)
    doc = json.loads(brut[inceput:sfarsit])
    grup = [n for n in doc["@graph"] if n.get("@type") == "ProductGroup"][0]
    grup["hasVariant"] = list(reversed(grup["hasVariant"]))
    inversat = brut[:inceput] + json.dumps(doc, ensure_ascii=False) + brut[sfarsit:]

    res = parse_product_html(inversat, ZOOPLUS_URL_2)

    assert res["price"] == 4.9
    assert len(res["variants"]) == 10


def test_zooplus_turnat_in_offers_lista_da_tot_minimul():
    """SINTETIC, si de aceea singurul care dovedeste regula G2F-4.

    Pe dump-ul real minimul cade din intamplare pe prima pozitie a variantelor,
    deci "minim" si "primul" nu se pot deosebi acolo. Fixture-ul asta ia exact
    preturile masurate pe zooplus pdp2 si le toarna in forma pe care G2F-4 o
    schimba — un `Product` cu `offers` LISTA, fara `size` — ordonate DESCRESCATOR,
    ca minimul (4,90) sa stea spre coada listei, iar primul sa fie 50,26.
    Inainte de G2F-4 rezultatul ar fi fost 50,26.
    """
    res = parse_product_html(_zooplus_fixture("pdp2_offers_lista_SINTETIC.html"),
                             ZOOPLUS_URL_2)

    assert res["price"] == 4.9              # minimul, desi primul element e 50,26
    assert res["currency"] == "RON"
    assert res["variants"] is None          # fara `size` nu se fabrica variante
    assert res["is_aggregate"] is False


def test_offers_lista_moneda_si_stocul_vin_din_oferta_castigatoare():
    """Oferta INTOARSA e cea cu pretul minim, nu prima — altfel pretul ar fi al
    unei variante, iar moneda si stocul ale alteia."""
    html = _offers_page([
        _offer(None, 300.0, "InStock", currency="EUR"),
        _offer(None, 120.0, "OutOfStock", currency="RON"),
    ])

    res = parse_product_html(html, URL)

    assert res["price"] == 120.0
    assert res["currency"] == "RON"         # moneda ofertei castigatoare
    assert res["in_stock"] is False         # stocul ofertei castigatoare


def test_offers_lista_elementul_corupt_e_ignorat_nu_invalideaza_lista():
    """Un element fara pret valid se SARE; restul listei decide pretul."""
    html = _page(head=_ld(json.dumps({
        "@type": "Product", "name": "Hrana uscata",
        "offers": [{"@type": "Offer", "price": "n/a", "priceCurrency": "RON"},
                   {"@type": "Offer", "price": None, "priceCurrency": "RON"},
                   "sir-in-loc-de-oferta",
                   {"@type": "Offer", "price": "89,90", "priceCurrency": "RON",
                    "availability": "https://schema.org/InStock"},
                   {"@type": "Offer", "price": "129,90", "priceCurrency": "RON"}]})))

    res = parse_product_html(html, URL)

    assert res["price"] == 89.9
    assert res["in_stock"] is True


def test_offers_lista_fara_niciun_pret_valid_pastreaza_eroarea_existenta():
    """Lista in care NICIUN element nu are pret valid: comportamentul de eroare
    ramane cel de dinainte — `invalid_price`, fiindca preturile EXISTA in pagina
    (doar ca sunt de necitit), spre deosebire de absenta lor totala."""
    html = _page(head=_ld(json.dumps({
        "@type": "Product", "name": "Hrana uscata",
        "offers": [{"@type": "Offer", "price": "n/a"},
                   {"@type": "Offer", "price": "-"}]})))

    with pytest.raises(ProductExtractionError) as exc:
        parse_product_html(html, URL)
    assert exc.value.reason == "invalid_price"


def test_g2f4_nu_atinge_minimul_pe_marimi_cand_cel_mai_ieftin_e_epuizat():
    """GARDA: regula "minimul global" NU s-a scurs pe calea marimilor.

    Pe o lista CU `size`, semantica ramane cea de la FASHION-2 — minimul
    marimilor IN STOC. Aici cel mai ieftin element (79.99) e epuizat: daca
    minimul global ar fi luat locul agregarii, pretul ar cadea la 79.99 si
    variantele ar disparea. Trebuie sa iasa 119.99, cu toate cele trei marimi.
    """
    html = _offers_page([
        _offer("42", 79.99, "OutOfStock"),
        _offer("43", 119.99, "InStock"),
        _offer("44", 149.99, "InStock"),
    ])

    res = parse_product_html(html, "https://www.bstn.com/p/x")

    assert res["price"] == 119.99           # minimul IN STOC, nu minimul global
    assert res["in_stock"] is True
    assert [v["variant"] for v in res["variants"]] == ["42", "43", "44"]
    assert [v["price"] for v in res["variants"]] == [79.99, 119.99, 149.99]


# ── G2F-6: flagul de registru `ldjson_availability: "untrusted"` (vivre) ──────

_VIVRE_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "vivre")

# URL-uri reale, din meta-urile dump-urilor sondei G2F-5. Domeniul e pe SUBDOMENIU
# fiindca acolo duce redirectul masurat www.vivre.ro -> ro.vivre.eu.
VIVRE_URL_1 = ("https://ro.vivre.eu/p-8831337/masa-de-dining-rotunda-si-moderna-"
               "pentru-2-persoane-din-otel-neagra")
VIVRE_URL_2 = ("https://ro.vivre.eu/p-1977409/homcom-canapea-chesterfiel-doua-"
               "locuri-matlasat-in-catifea-gri")
# Domeniu FARA flag, folosit ca martor pe ACELASI fixture.
URL_FARA_FLAG = "https://www.magazin-test.ro/p/produs-1"


def _vivre_fixture(nume: str) -> str:
    with open(os.path.join(_VIVRE_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fisier,url,pret", [
    ("pdp_8831337.html", VIVRE_URL_1, 288.99),
    ("pdp_1977409.html", VIVRE_URL_2, 1151.99),
])
def test_vivre_flagul_face_stocul_necunoscut_nu_epuizat(fisier, url, pret):
    """Pe ro.vivre.eu `availability` din ld+json e o CONSTANTA de sablon.

    Ambele PDP-uri masurate emit `OutOfStock`, desi datele proprii de listare ale
    aceluiasi site dau `"inStock":true` pentru EXACT aceste doua produse. Flagul
    `ldjson_availability: "untrusted"` transforma minciuna in NECUNOSCUT: `None`,
    nu `False`. Distinctia nu e cosmetica — pe 46.536 de produse, `False` ar
    ascunde din feed exact marfa cumparabila, si ar face-o tacut.
    """
    res = parse_product_html(_vivre_fixture(fisier), url)

    assert res["in_stock"] is None          # NU False
    assert res["price"] == pret
    assert res["currency"] == "RON"
    assert res["method"] == "jsonld"


@pytest.mark.parametrize("fisier,pret", [
    ("pdp_8831337.html", 288.99),
    ("pdp_1977409.html", 1151.99),
])
def test_vivre_acelasi_fixture_fara_flag_da_stocul_din_sablon(fisier, pret):
    """MARTORUL care face testul de mai sus sa insemne ceva.

    ACELASI fixture, cerut ca de pe un domeniu fara flag, da `False` — adica exact
    comportamentul de dinainte de G2F-6. Deci `None`-ul de mai sus vine din FLAG,
    nu din vreo particularitate a fixture-ului, si nu din faptul ca l-am redus.
    """
    res = parse_product_html(_vivre_fixture(fisier), URL_FARA_FLAG)

    assert res["in_stock"] is False
    assert res["price"] == pret


def test_flagul_nu_atinge_nimic_in_afara_stocului():
    """Restul extractiei ramane bit cu bit aceeasi cu si fara flag."""
    html = _vivre_fixture("pdp_8831337.html")

    cu = parse_product_html(html, VIVRE_URL_1)
    fara = parse_product_html(html, URL_FARA_FLAG)

    assert cu["in_stock"] is None and fara["in_stock"] is False
    for cheie in ("name", "price", "currency", "is_aggregate", "method",
                  "image_url", "variants"):
        assert cu[cheie] == fara[cheie], f"flagul a atins {cheie}"


def test_flagul_neutralizeaza_si_stocul_variantelor():
    """Variantele se neutralizeaza odata cu produsul.

    Stocul lor vine din exact aceeasi `availability` de sablon, deci a lasa
    `in_stock` pe variante ar contrazice produsul care tocmai a spus „nu stiu".
    Pretul ramane insa cel agregat — flagul e despre stoc, nu despre pret.
    (Sintetic: PDP-urile vivre masurate n-au variante.)
    """
    html = _group_page([
        _variant("40", 100.0, "OutOfStock"),
        _variant("41", 120.0, "InStock"),
    ])

    cu = parse_product_html(html, VIVRE_URL_1)
    fara = parse_product_html(html, URL_FARA_FLAG)

    assert [v["in_stock"] for v in cu["variants"]] == [None, None]
    assert cu["in_stock"] is None
    # Martorul: fara flag, aceleasi variante isi pastreaza stocul.
    assert [v["in_stock"] for v in fara["variants"]] == [False, True]
    # Pretul e neatins de flag pe ambele cai.
    assert cu["price"] == fara["price"] == 120.0


def test_flagul_nu_se_scurge_pe_domeniul_parinte():
    """Cheia e `ro.vivre.eu`, deci NU acopera `vivre.ro`.

    Nu e o scapare, ci consecinta cinstita a masuratorii: redirectul duce mereu pe
    ro.vivre.eu, deci acolo ajunge si productia. Un URL pe vechiul domeniu ramane
    tratat ca orice domeniu fara flag — si testul asta o pinuieste, ca sa nu para
    mai tarziu ca flagul „nu merge".
    """
    html = _vivre_fixture("pdp_8831337.html")

    res = parse_product_html(html, "https://www.vivre.ro/p-8831337/x")

    assert res["in_stock"] is False


def test_registrul_pune_flagul_doar_unde_e_dovedit():
    """G2F-6 a intrat cu 4 domenii, dar DOAR unul are contradictia masurata."""
    from app.services.shop_registry import SHOP_REGISTRY

    assert SHOP_REGISTRY["ro.vivre.eu"]["ldjson_availability"] == "untrusted"
    for domeniu in ("hornbach.ro", "bonami.ro", "action.com"):
        assert "ldjson_availability" not in SHOP_REGISTRY[domeniu], \
            f"{domeniu}: flagul s-a pus fara dovada"
