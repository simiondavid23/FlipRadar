"""AA-1 — teste pure pentru extractia de thumbnails auto (fara retea, fara DB).

thumb_from_img (helper comun) + _photos_map_from_state / _olx_id (olx_auto), plus
compunerea lor: fallback pe __PRERENDERED_STATE__ cand imaginea din card e placeholder.
"""
import json

from bs4 import BeautifulSoup

from app.scrapers.auto.listings._common import thumb_from_img
from app.scrapers.auto.listings.olx_auto import (
    _olx_id, _olx_upgrade_thumb, _photos_map_from_state,
)


def _img(html: str):
    """Primul tag <img> dintr-un fragment HTML."""
    return BeautifulSoup(html, "html.parser").find("img")


# ── thumb_from_img ────────────────────────────────────────────────────────────────
def test_thumb_src_valid():
    assert thumb_from_img(_img('<img src="https://cdn/x/a.jpg">')) == "https://cdn/x/a.jpg"


def test_thumb_placeholder_src_falls_to_data_src():
    img = _img('<img src="https://cdn/no_thumbnail.png" data-src="https://cdn/real.jpg">')
    assert thumb_from_img(img) == "https://cdn/real.jpg"


def test_thumb_data_uri_only_is_empty():
    # data:-URI nu incepe cu http -> respins (filtrul "trebuie sa inceapa cu http").
    assert thumb_from_img(_img('<img src="data:image/gif;base64,R0lGODlhAQABAAAAADs=">')) == ""


def test_thumb_no_thumbnail_is_empty():
    assert thumb_from_img(_img('<img src="https://cdn/x/no_thumbnail.png">')) == ""


def test_thumb_svg_is_empty():
    assert thumb_from_img(_img('<img src="https://cdn/x/placeholder.svg">')) == ""


def test_thumb_srcset_first_url():
    img = _img('<img srcset="https://cdn/x/a.jpg 1x, https://cdn/x/b.jpg 2x">')
    assert thumb_from_img(img) == "https://cdn/x/a.jpg"


def test_thumb_data_imgsrc_kleinanzeigen():
    # Kleinanzeigen pune URL-ul real in data-imgsrc; src e placeholder relativ (non-http).
    img = _img('<img src="/static/placeholder.png" data-imgsrc="https://cdn.kleinanzeigen/real.jpg">')
    assert thumb_from_img(img) == "https://cdn.kleinanzeigen/real.jpg"


def test_thumb_none_is_empty():
    assert thumb_from_img(None) == ""


# ── _photos_map_from_state ─────────────────────────────────────────────────────────
_APOLLO = "https://frankfurt.apollo.olxcdn.com:443/v1/files"


def _state_html(ads: list) -> str:
    """HTML sintetic cu window.__PRERENDERED_STATE__ = <string JSON dublu-encodat>,
    exact forma pe care o parseaza scraperul (regex + dublu json.loads)."""
    inner = json.dumps({"listing": {"listing": {"ads": ads}}})
    return (
        "<html><body><script>window.__PRERENDERED_STATE__ = "
        f"{json.dumps(inner)};</script></body></html>"
    )


def test_photos_map_two_ads():
    html = _state_html([
        {"url": "https://www.olx.ro/d/oferta/masina-unu-IDaaa111.html",
         "photos": [f"{_APOLLO}/tok1-RO/image;s=1600x1067", f"{_APOLLO}/tok1b-RO/image;s=800x600"]},
        {"urlPath": "/d/oferta/masina-doi-IDbbb222.html",
         "photos": [f"{_APOLLO}/tok2-RO/image;s=3024x4032"]},
    ])
    # Cheia = tokenul din -ID<token>.html; valoarea = prima poza, normalizata la 1000x1000.
    assert _photos_map_from_state(html) == {
        "aaa111": f"{_APOLLO}/tok1-RO/image;s=1000x1000",
        "bbb222": f"{_APOLLO}/tok2-RO/image;s=1000x1000",
    }


def test_photos_map_no_state_returns_empty():
    assert _photos_map_from_state("<html><body>fara state</body></html>") == {}


def test_photos_map_malformed_state_returns_empty():
    # __PRERENDERED_STATE__ prezent dar continutul nu e JSON valid -> {} fara exceptie.
    bad = '<script>window.__PRERENDERED_STATE__ = "{ not valid json ";</script>'
    assert _photos_map_from_state(bad) == {}


def test_photos_map_ad_without_photos_skipped():
    html = _state_html([
        {"url": "https://www.olx.ro/d/oferta/fara-poza-IDccc333.html"},               # fara photos
        {"url": "https://www.olx.ro/d/oferta/lista-goala-IDddd444.html", "photos": []},  # lista goala
        {"url": "https://www.olx.ro/d/oferta/ok-IDeee555.html",
         "photos": [f"{_APOLLO}/z-RO/image;s=500x500"]},
    ])
    assert _photos_map_from_state(html) == {"eee555": f"{_APOLLO}/z-RO/image;s=1000x1000"}


def test_olx_upgrade_thumb_keeps_url_without_size():
    # URL fara ;s= ramane neatins; gol -> "".
    assert _olx_upgrade_thumb(f"{_APOLLO}/tok-RO/image") == f"{_APOLLO}/tok-RO/image"
    assert _olx_upgrade_thumb("") == ""


# ── Compunere: expresia din search_olx_auto (thumb_from_img OR poza din state) ──────
def test_card_placeholder_falls_back_to_state():
    href = "/d/oferta/vand-masina-IDkHB4R.html"
    img = _img('<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=" data-src="">')  # placeholder
    photos_map = _photos_map_from_state(_state_html([
        {"url": f"https://www.olx.ro{href}", "photos": [f"{_APOLLO}/real-RO/image;s=1600x1067"]},
    ]))
    thumb = thumb_from_img(img) or photos_map.get(_olx_id(href) or "", "")
    assert thumb == f"{_APOLLO}/real-RO/image;s=1000x1000"


def test_card_real_img_wins_over_state():
    href = "/d/oferta/vand-masina-IDkHB4R.html"
    img = _img(f'<img src="{_APOLLO}/din-card-RO/image;s=389x272">')
    photos_map = _photos_map_from_state(_state_html([
        {"url": f"https://www.olx.ro{href}", "photos": [f"{_APOLLO}/din-state-RO/image;s=1600x1067"]},
    ]))
    thumb = thumb_from_img(img) or photos_map.get(_olx_id(href) or "", "")
    # Imaginea reala din card castiga si NU e transformata (transformarea e doar pe state).
    assert thumb == f"{_APOLLO}/din-card-RO/image;s=389x272"
