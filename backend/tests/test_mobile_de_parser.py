"""AA-4 — parser mobile.de (_parse_mobilede_html) pe structura DOM reala confirmata live 2026-07.

Fixture HTML sintetic INLINE (fara nume reale de dealeri), functii pure, fara retea/DB.
Structura reala: cardul e ancora <a href="/fahrzeuge/details.html?id=NNN">, titlu din alt-ul
imaginii (fallback aria-labelledby), pret in [data-testid=price-label], text cu "EZ MM/YYYY •
N.NNN km • ... N l/100km".
"""
from app.scrapers.auto.listings.mobile_de_scraper import _parse_mobilede_html
from app.scrapers.auto.listings._common import MAX_LISTINGS

_IMG = "https://img.classistatic.de/api/v1/mo-prod/images/ab/abc123?rule=mo-160w"


def _card(id="111222333", title="Volkswagen Golf 1.4 TSI", price="12.999 €",
          specs="EZ 05/2016 • 98.500 km • 92 kW (125 PS) • Benzin 5,2 l/100km (komb.)",
          href=None, img_src=_IMG, with_title=True):
    href = href if href is not None else f"/fahrzeuge/details.html?id={id}&s=Car"
    img = f'<img alt="{title if with_title else ""}" src="{img_src}">' if img_src is not None else ""
    tnode = f'<span id="rl-{id}-title">{title}</span>' if with_title else ""
    return (f'<a href="{href}" data-testid="result-listing-{id}" aria-labelledby="rl-{id}-title">'
            f'{img}{tnode}<span data-testid="price-label">{price}</span>'
            f'<div>{specs}</div></a>')


def _page(*cards):
    return "<html><body><main>" + "".join(cards) + "</main></body></html>"


def test_card_complet():
    r = _parse_mobilede_html(_page(_card()))
    assert len(r) == 1
    c = r[0]
    assert c["platform"] == "mobile_de"
    assert c["external_id"] == "111222333"
    assert c["titlu"] == "Volkswagen Golf 1.4 TSI"
    assert c["year"] == 2016
    assert c["km"] == 98500          # din "98.500 km", NU 5 din "5,2 l/100km"
    assert c["pret"] == 12999.0
    assert c["moneda"] == "EUR"
    assert c["source_url"] == "https://suchen.mobile.de/fahrzeuge/details.html?id=111222333&s=Car"
    assert c["thumbnail_url"] == _IMG


def test_km_nu_ia_consumul():
    # Neuwagen fara kilometraj: text cu "5,7 l/100km" dar fara "N km" real -> km None (nu 100).
    r = _parse_mobilede_html(_page(_card(specs="Neuwagen • 110 kW (150 PS) • Benzin 5,7 l/100km (komb.)")))
    assert len(r) == 1
    assert r[0]["km"] is None


def test_titlu_fallback_aria():
    # img fara alt -> titlu din elementul referit de aria-labelledby.
    card = ('<a href="/fahrzeuge/details.html?id=777" aria-labelledby="rl-777-title">'
            f'<img src="{_IMG}"><span id="rl-777-title">VW Passat Variant 2.0 TDI</span>'
            '<span data-testid="price-label">9.500 €</span><div>EZ 03/2018 • 120.000 km</div></a>')
    r = _parse_mobilede_html(_page(card))
    assert len(r) == 1
    assert r[0]["titlu"] == "VW Passat Variant 2.0 TDI"


def test_chrome_ignorat():
    # ancora de detaliu fara titlu (fara img/alt, fara element de titlu) + element de chrome
    # fara link de detaliu -> ambele ignorate; ramane doar cardul valid.
    fara_titlu = '<a href="/fahrzeuge/details.html?id=999" data-testid="result-listing-9"></a>'
    chrome = "<article><h2>Werbung</h2><p>Kein Fahrzeug</p></article>"
    r = _parse_mobilede_html(_page(_card(), fara_titlu, chrome))
    assert len(r) == 1
    assert r[0]["external_id"] == "111222333"


def test_thumbnail_data_uri_devine_none():
    # placeholder data:-URI -> thumb_from_img "" -> thumbnail_url None (conventia fisierului),
    # dar cardul e tot parsat (titlu din alt).
    r = _parse_mobilede_html(_page(_card(img_src="data:image/gif;base64,R0lGODlhAQABAAAAADs=")))
    assert len(r) == 1
    assert r[0]["thumbnail_url"] is None
    assert r[0]["titlu"] == "Volkswagen Golf 1.4 TSI"


def test_html_gol_sau_challenge():
    assert _parse_mobilede_html("") == []
    assert _parse_mobilede_html("<html><body>Access denied. Error Reference: 0.abc123</body></html>") == []


def test_respecta_max_listings():
    cards = [_card(id=str(1000000 + i)) for i in range(MAX_LISTINGS + 5)]
    r = _parse_mobilede_html(_page(*cards))
    assert len(r) == MAX_LISTINGS


def test_href_relativ_prefixat():
    r = _parse_mobilede_html(_page(_card(href="/fahrzeuge/details.html?id=555")))
    assert len(r) == 1
    assert r[0]["source_url"] == "https://suchen.mobile.de/fahrzeuge/details.html?id=555"
    assert r[0]["external_id"] == "555"
