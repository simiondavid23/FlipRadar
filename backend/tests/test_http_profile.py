"""Profilul de impersonare TLS/HTTP2 — o singura sursa (app/utils/http_profile.py).

Fiecare scraper Radar isi definea propriul `_IMPERSONATE = "chrome110"` (Chrome 110 =
februarie 2023): amprenta devenise ea insasi un semnal de detectie, iar actualizarea
cerea editat 9 fisiere. Testele de aici sunt STRUCTURALE — suita e offline, deci nu pot
valida ca profilul chiar trece de WAF-uri; validarea aia se face live cu
scripts/test_scrapers.py (rulata inainte si dupa schimbare).
"""
import pathlib

import pytest

from app.utils.http_profile import (
    DEFAULT_IMPERSONATE, PLATFORM_IMPERSONATE, impersonate_for,
)

# Modulele care aveau profil propriu si acum trebuie sa-l ia din sursa centrala.
_MODULE_NAMES = [
    "autovit_scraper", "cleanup_service", "facebook_scraper", "lajumate_scraper",
    "mobilede_scraper", "okazii_scraper", "olx_scraper", "publi24_scraper",
]

_APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def test_profilul_implicit_e_o_tinta_reala_curl_cffi():
    """Garda anti-typo: un profil inexistent ar arunca abia la primul request LIVE
    (suita e offline), deci l-ar prinde doar productia."""
    from curl_cffi.requests.impersonate import BrowserTypeLiteral

    assert DEFAULT_IMPERSONATE in BrowserTypeLiteral.__args__


def test_aliasul_chrome_se_rezolva_determinist():
    """`chrome` nu e o valoare vaga: cu curl_cffi pinuit in requirements se rezolva
    mereu la acelasi profil concret (0.15.0 -> chrome146), identic pe Windows si pe Pi."""
    from curl_cffi.requests.impersonate import REAL_TARGET_MAP

    assert DEFAULT_IMPERSONATE == "chrome"
    assert REAL_TARGET_MAP["chrome"].startswith("chrome")


@pytest.mark.parametrize("modul", _MODULE_NAMES)
def test_scraperele_iau_profilul_din_sursa_centrala(modul):
    import importlib

    mod = importlib.import_module(f"app.services.radar.{modul}")
    assert mod._IMPERSONATE == DEFAULT_IMPERSONATE


def test_niciun_profil_hardcodat_vechi_in_app():
    """Grep-test: "chrome110" nu mai are voie sa apara in cod. Singura exceptie e
    docstring-ul lui http_profile.py, care explica de ce a fost scos."""
    ramase = []
    for p in _APP.rglob("*.py"):
        if p.name == "http_profile.py":
            continue
        if "chrome110" in p.read_text(encoding="utf-8"):
            ramase.append(str(p.relative_to(_APP)))
    assert ramase == [], f"profil vechi hardcodat in: {ramase}"


def test_dictionarul_de_exceptii_gol_nu_schimba_nimic():
    """Cat timp nu exista exceptii masurate, orice platforma primeste implicitul."""
    assert PLATFORM_IMPERSONATE == {}
    for platforma in ("olx", "mobilede", "facebook", "publi24", "inexistenta", ""):
        assert impersonate_for(platforma) == DEFAULT_IMPERSONATE


def test_exceptia_are_precedenta_si_e_case_insensitive(monkeypatch):
    """Mecanismul de exceptii chiar functioneaza cand se pune ceva in el."""
    monkeypatch.setitem(PLATFORM_IMPERSONATE, "mobilede", "chrome110")
    assert impersonate_for("mobilede") == "chrome110"
    assert impersonate_for(" MobileDe ") == "chrome110"
    assert impersonate_for("olx") == DEFAULT_IMPERSONATE     # restul, neatinse


def test_headerele_proprii_nu_mai_contrazic_amprenta():
    """build_headers nu mai suprascrie User-Agent (masurat live: UA de Firefox peste
    Sec-Ch-Ua de Chrome, contradictie pe care niciun browser real n-o produce).
    Ce nu trimitem noi pune curl_cffi coerent cu profilul impersonat."""
    from app.services.radar.base_scraper import build_headers

    h = build_headers()
    for cheie in ("User-Agent", "Accept", "Accept-Encoding", "Connection",
                  "Sec-Fetch-Dest", "Upgrade-Insecure-Requests"):
        assert cheie not in h, f"{cheie} suprascris — contrazice profilul impersonat"
    assert h["Accept-Language"].startswith("ro-RO")
    # `extra` ramane suveran (Referer etc.)
    assert build_headers({"Referer": "https://x.ro"})["Referer"] == "https://x.ro"
