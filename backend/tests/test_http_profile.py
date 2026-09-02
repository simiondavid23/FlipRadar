"""Profilul de impersonare TLS/HTTP2 — o singura sursa (app/utils/http_profile.py).

Fiecare scraper Radar isi definea propriul `_IMPERSONATE = "chrome110"` (Chrome 110 =
februarie 2023): amprenta devenise ea insasi un semnal de detectie, iar actualizarea
cerea editat 9 fisiere. Testele de aici sunt STRUCTURALE — suita e offline, deci nu pot
valida ca profilul chiar trece de WAF-uri; validarea aia se face live cu
scripts/test_scrapers.py (rulata inainte si dupa schimbare).
"""
import pathlib
import re

import pytest

from app.utils.http_profile import (
    DEFAULT_IMPERSONATE, PLATFORM_IMPERSONATE, impersonate_for,
)

# Modulele care aveau profil propriu si acum trebuie sa-l ia din sursa centrala.
_MODULE_NAMES = [
    "autovit_scraper", "cleanup_service", "facebook_scraper", "lajumate_scraper",
    "mobilede_scraper", "okazii_scraper", "olx_scraper", "publi24_scraper",
]

# IMP-1b — modulele comune ale scraperelor din app/scrapers/.
# MKT-DEAD: `app.scrapers.marketplace._common` a cazut odata cu calea legacy, deci
# lista a scazut de la patru la trei.
_COMMON_MODULES = [
    "app.scrapers.auto.listings._common",
    "app.scrapers.auto.lots._common",
    "app.scrapers.real_estate._common",
]

# Fisiere care au voie sa pastreze un profil propriu, hardcodat, cu motivul:
_PROFIL_PROPRIU_PERMIS = {
    # Vorbeste cu MODEMUL, nu cu un site anti-bot — amprenta nu conteaza acolo.
    "services/network/rotator.py",
    # Vinted: cookie de sesiune + DataDome, deci nu poate fi validat live de aici.
    "services/radar/vinted_html.py",
    "services/radar/vinted_catalog_service.py",
    # Sursa centrala: docstring-ul ei explica de ce s-au scos profilele vechi.
    "utils/http_profile.py",
}

# IMP-2 — `services/scraper_service.py` NU mai e pe lista de mai sus.
#
# Motivul cu care intrase era „nu poate fi validata live aici", nu „profilul vechi
# e necesar": IMP-1 a lasat poarta retail pe `chrome131` fiindca la momentul acela
# nu exista o masuratoare pe magazine. IMP-2 a facut-o — 73 de domenii validate
# prin poarta plus cele 5 scrapere de cautare care cheama curl direct — si a gasit
# 3 DEBLOCARI pe profilul centralizat (altex.ro, mediagalaxy.ro, vexio.ro, toate
# 2/2 blocate pe cel vechi si 2/2 OK pe cel nou) contra unei singure regresii,
# `sivasdescalzo.com`, intermitenta (2/4) si pinuita in registru. Exceptia s-a
# stins odata cu motivul ei.
#
# Ce ramane permis, si DOAR atat: literalul unui profil vechi ca VALOARE a cheii
# `impersonate` din registru — adica exact forma prin care un domeniu masurat sta
# pinuit pe un profil anterior. Nu se pune `shop_registry.py` pe lista alba,
# fiindca asta ar permite orice profil hardcodat oriunde in registru, inclusiv in
# prosa din `notes`. Tiparul e ingust prin constructie:
_OVERRIDE_MASURAT_IN_REGISTRU = re.compile(
    r'"impersonate"\s*:\s*"(?:chrome110|chrome131)"')

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


@pytest.mark.parametrize("modul", _COMMON_MODULES)
def test_modulele_comune_iau_profilul_din_sursa_centrala(modul):
    """IMP-1b: fiecare `_common.py` isi definea propriul IMPERSONATE = "chrome131"."""
    import importlib

    mod = importlib.import_module(modul)
    assert mod.IMPERSONATE == DEFAULT_IMPERSONATE


def test_niciun_profil_hardcodat_vechi_in_app():
    """Grep-test: profilele vechi nu mai au voie sa apara in cod, in afara fisierelor
    din `_PROFIL_PROPRIU_PERMIS` — care sunt exceptii DOCUMENTATE, nu scapari.

    IMP-2 a scos poarta retail de pe lista si a inlocuit-o cu o exceptie de TIPAR:
    `"impersonate": "<profil vechi>"` (override masurat, per domeniu, in registru).
    Restul aparitiilor raman interzise oriunde — inclusiv in acelasi fisier.
    """
    ramase = []
    for p in _APP.rglob("*.py"):
        rel = p.relative_to(_APP).as_posix()
        if rel in _PROFIL_PROPRIU_PERMIS:
            continue
        text = _OVERRIDE_MASURAT_IN_REGISTRU.sub("", p.read_text(encoding="utf-8"))
        if "chrome110" in text or "chrome131" in text:
            ramase.append(rel)
    assert ramase == [], f"profil vechi hardcodat in: {ramase}"


def test_exceptia_de_override_e_INGUSTA():
    """Garda gardei: exceptia acopera DOAR valoarea cheii `impersonate`.

    Fara testul asta, cineva ar putea largi regexul (sau ar putea crede ca e larg)
    si un `_IMPERSONATE = "chrome131"` re-hardcodat ar trece neobservat — exact
    scaparea pe care IMP-2 a reparat-o.
    """
    permis = '"impersonate": "chrome131"'
    assert _OVERRIDE_MASURAT_IN_REGISTRU.sub("", permis) == ""

    for interzis in (
        '_IMPERSONATE = "chrome131"',
        'impersonate="chrome131"',            # apel, nu cheie de registru
        '"notes": "ramane pe chrome131"',     # prosa, nu configuratie
        "'impersonate': 'chrome131'",         # ghilimele simple: nu e forma din registru
        '"impersonate": "chrome146"',         # profil care nu e vechi -> nimic de iertat
    ):
        ramas = _OVERRIDE_MASURAT_IN_REGISTRU.sub("", interzis)
        assert ramas == interzis, f"exceptia a inghitit ceva ce nu trebuia: {interzis}"


@pytest.mark.parametrize("modul", _COMMON_MODULES)
def test_modulele_comune_nu_mai_contrazic_amprenta(modul):
    """Nici aici nu se mai suprascrie ce pune curl_cffi coerent cu profilul; raman
    doar Accept-Language si ce trimite explicit call site-ul prin `extra`."""
    import importlib

    build_headers = importlib.import_module(modul).build_headers
    h = build_headers()
    for cheie in ("User-Agent", "Accept", "Accept-Encoding", "Connection",
                  "Upgrade-Insecure-Requests"):
        assert cheie not in h, f"{modul}: {cheie} suprascris — contrazice profilul"
    assert "Accept-Language" in h
    # Header-ele FUNCTIONALE ale call site-urilor raman suverane.
    extra = {"Referer": "https://x.ro/", "Accept": "application/json",
             "X-Requested-With": "XMLHttpRequest", "Accept-Language": "de-DE,de;q=0.9"}
    assert build_headers(extra) | extra == build_headers(extra)


def test_pool_urile_de_user_agents_au_disparut():
    """Listele de UA rotite erau exact sursa contradictiei; sa nu reapara."""
    import importlib

    for modul in _COMMON_MODULES + ["app.services.radar.base_scraper"]:
        assert not hasattr(importlib.import_module(modul), "_USER_AGENTS"), modul


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
