"""SCRAPE-AUDIT (imobiliare) — fix-urile auditului modulului imobiliare.

Bug-urile reparate: pretul din regex-ul pe descriere batea pretul structurat al
scraperului ("avans 15.000 euro" > pretul real de card); "54.5 mp" devenea 545
(€/mp de 10x mai mic -> scor A fals); zonele picau pe diacritice si pe substringuri
fara granita ("interior renovat" -> IOR); criteriul de zona respingea "dorobanti"
vs "Dorobanți"; "Reactualizat azi" pierdea data; "69,500" (mii EN) devenea 69.5;
fallback-ul Storia salva "lei" ca EUR; o exceptie pe un anunt omora tot run-ul.

SCRAPE-1d: cardul Facebook Marketplace decidea "linia e pret" pe criteriul "incepe
cu o cifra" -> un titlu ca "2 camere de inchiriat" devenea price=2.0 (trecea de
pret_max) si impingea pretul real in pozitia de titlu; moneda se lua de pe tot
textul cardului, deci un € din titlu facea un pret in lei sa fie salvat ca EUR.
"""
import re

import pytest

from app.scrapers.real_estate._common import extract_surface
from app.services.real_estate.extractor import _clean_number, extract_price
from app.services.real_estate.zones import normalize_zone
from app.scrapers.real_estate.facebook_real_estate import (
    _parse_card_lines as fb_card, _parse_price as fb_price)


# ── suprafata: punctul zecimal nu mai inzeceste ──────────────────────────────────

def test_suprafata_cu_punct_zecimal():
    assert extract_surface("Apartament 54.5 mp decomandat") == 54.5


def test_suprafata_formate_vechi_neschimbate():
    assert extract_surface("65 mp utili") == 65.0
    assert extract_surface("65,5 mp") == 65.5
    assert extract_surface("teren 1.500 mp") == 1500.0


# ── _clean_number: mii in format EN ──────────────────────────────────────────────

def test_clean_number_mii_englezesti():
    assert _clean_number("69,500") == 69500.0


def test_clean_number_formate_ro_neschimbate():
    assert _clean_number("15.000") == 15000.0
    assert _clean_number("1.234,56") == 1234.56
    assert _clean_number("54,5") == 54.5


def test_fb_price_mii_englezesti():
    assert fb_price("RON 1,500") == 1500.0
    assert fb_price("€1.500") == 1500.0


# ── Facebook RE: cardul se imparte in pret / titlu / locatie ────────────────────

def test_fb_card_tipic_cu_pretul_pe_prima_linie():
    price, cur, title, loc = fb_card(
        ["1.500 lei", "Apartament 2 camere Titan", "București"])
    assert (price, cur) == (1500.0, "RON")
    assert title == "Apartament 2 camere Titan"
    assert loc == "București"


def test_fb_card_titlu_cu_cifra_initiala_nu_mai_e_luat_drept_pret():
    # BUG REPRODUS: criteriul re.match(r"^\d", line) dadea price=2.0 (2 RON trecea
    # de filtrul de pret maxim) si title="350 €".
    price, cur, title, loc = fb_card(
        ["2 camere de închiriat, mobilat", "350 €", "Cluj-Napoca"])
    assert price == 350.0
    assert cur == "EUR"
    assert title == "2 camere de închiriat, mobilat"
    assert loc == "Cluj-Napoca"


def test_fb_card_fara_pret_da_none():
    price, cur, title, loc = fb_card(["Garsonieră de închiriat", "Iași"])
    assert price is None
    assert cur is None
    assert title == "Garsonieră de închiriat"
    assert loc == "Iași"


def test_fb_bucla_sare_cardul_fara_pret():
    # bucla reala cere Playwright + sesiune FB, deci pinuim garda pe sursa:
    # fara pret cardul e sarit inainte de a intra in rezultate (precedent SCRAPE-1a).
    import inspect
    from app.scrapers.real_estate import facebook_real_estate as fb
    src = inspect.getsource(fb._search_sesiune)
    assert "_parse_card_lines(lines)" in src
    assert "if price is None or price <= 0:" in src


def test_fb_card_euro_in_titlu_nu_schimba_moneda_pretului():
    # moneda se decide pe LINIA de pret, nu pe tot textul cardului.
    price, cur, title, _ = fb_card(
        ["Apartament de închiriat, se accepta plata si in €", "1.500 lei", "Sibiu"])
    assert price == 1500.0
    assert cur == "RON"
    assert title == "Apartament de închiriat, se accepta plata si in €"


def test_fb_card_pret_cu_perioada_pe_aceeasi_linie():
    # linie PUR pret chiar cu perioada lipita — se consuma, nu ajunge titlu.
    price, cur, title, _ = fb_card(
        ["1.500 lei / lună", "Garsonieră ultracentral", "Cluj-Napoca"])
    assert (price, cur) == (1500.0, "RON")
    assert title == "Garsonieră ultracentral"


# ── FBM-1b: titlul care contine el insusi pretul ─────────────────────────────────

def test_fb_card_titlu_cu_pret_inclus_nu_bate_linia_pur_pret():
    # RESTUL semnalat de FBM-1a: titlul are SI cifre SI valuta, iar _parse_price pe
    # toata linia lipea cifrele in "2,350" -> price=2350. Pretul trebuie luat de pe
    # linia PUR pret, iar titlul sa ramana intreg.
    price, cur, title, loc = fb_card(
        ["2 camere, 350 €/lună", "350 €", "Cluj-Napoca"])
    assert price == 350.0
    assert cur == "EUR"
    assert title == "2 camere, 350 €/lună"
    assert loc == "Cluj-Napoca"


def test_fb_card_fallback_pe_titlu_nu_consuma_linia():
    # fara linie pur-pret: pretul vine din substringul lipit de valuta, dar linia
    # ramane titlu (altfel titlul ar fi fost "Cluj-Napoca").
    price, cur, title, loc = fb_card(["2 camere, 350 €/lună", "Cluj-Napoca"])
    assert price == 350.0
    assert cur == "EUR"
    assert title == "2 camere, 350 €/lună"
    assert loc == "Cluj-Napoca"


# ── FBM-1d: post-filtrul local de pret (ambele margini) ─────────────────────────

def test_fb_pret_sub_minim_respins():
    from app.scrapers.real_estate.facebook_real_estate import _price_in_bounds
    assert _price_in_bounds(200.0, {"pret_min": 300}) is False


def test_fb_pret_peste_maxim_respins():
    from app.scrapers.real_estate.facebook_real_estate import _price_in_bounds
    assert _price_in_bounds(900.0, {"pret_max": 500}) is False


def test_fb_pret_in_interval_acceptat():
    from app.scrapers.real_estate.facebook_real_estate import _price_in_bounds
    assert _price_in_bounds(400.0, {"pret_min": 300, "pret_max": 500}) is True
    # marginile sunt inclusive
    assert _price_in_bounds(300.0, {"pret_min": 300, "pret_max": 500}) is True
    assert _price_in_bounds(500.0, {"pret_min": 300, "pret_max": 500}) is True


def test_fb_fara_margini_accepta_orice():
    from app.scrapers.real_estate.facebook_real_estate import _price_in_bounds
    assert _price_in_bounds(1.0, {}) is True
    assert _price_in_bounds(999999.0, {}) is True
    # o singura margine ramane nelimitata pe cealalta parte
    assert _price_in_bounds(999999.0, {"pret_min": 300}) is True
    assert _price_in_bounds(1.0, {"pret_max": 500}) is True


def test_fb_cheile_alias_engleze_functioneaza():
    from app.scrapers.real_estate.facebook_real_estate import _price_in_bounds
    assert _price_in_bounds(200.0, {"price_min": 300}) is False
    assert _price_in_bounds(900.0, {"price_max": 500}) is False
    assert _price_in_bounds(400.0, {"price_min": 300, "price_max": 500}) is True


def test_fb_bucla_foloseste_post_filtrul_de_pret():
    # pin pe sursa: o refactorizare sa nu piarda plasa locala de pret.
    import inspect
    from app.scrapers.real_estate import facebook_real_estate as fb
    src = inspect.getsource(fb._search_sesiune)
    assert "_price_in_bounds(price, filters)" in src


def test_fb_masca_user_agent_nu_mai_e_headless():
    # browserul emitea "HeadlessChrome/141.0" pe sesiunea REALA a utilizatorului.
    from app.scrapers.real_estate.facebook_real_estate import _CONTEXT_KWARGS
    ua = _CONTEXT_KWARGS["user_agent"]
    assert "Headless" not in ua
    assert "Chrome/" in ua


def test_fb_masca_init_script_ascunde_webdriver():
    from app.scrapers.real_estate.facebook_real_estate import _STEALTH_INIT_JS
    assert "webdriver" in _STEALTH_INIT_JS


def test_fb_masca_aplicata_pe_ambele_ramuri_de_context():
    # pin pe sursa: o refactorizare viitoare sa nu piarda masca pe una din ramuri
    # (cea cu storage_state sau fallback-ul fara).
    import inspect
    from app.scrapers.real_estate import facebook_real_estate as fb
    src = inspect.getsource(fb._search_sesiune)
    assert src.count("new_context(") == 2
    assert src.count("**_CONTEXT_KWARGS") == 2
    assert "add_init_script" in src
    assert "args=_LAUNCH_ARGS" in src


def test_fb_card_fallback_cu_simbolul_inaintea_numarului():
    # "€350" — ordinea inversa a adiacentei; _parse_price pe toata linia ar da 2350.
    price, cur, title, loc = fb_card(["Apartament 2 camere €350/lună", "Brașov"])
    assert price == 350.0
    assert cur == "EUR"
    assert title == "Apartament 2 camere €350/lună"
    assert loc == "Brașov"


# ── FBM-1e (F5): login wall servit IN pagina, pe 200, fara redirect ─────────────

_HTML_MARKETPLACE = """
<html><body><div role="main">
  <a href="/marketplace/item/111/">Garsonieră mobilată</a>
  <a href="/marketplace/item/222/">Apartament 3 camere</a>
  <form action="/search/" method="get"><input name="q"></form>
</div></body></html>
"""


def test_login_wall_prinde_royal_login_form():
    from app.scrapers.real_estate.facebook_real_estate import _looks_like_login_wall
    assert _looks_like_login_wall(
        '<html><body><form id="royal_login_form">...</form></body></html>') is True


def test_login_wall_prinde_perechea_email_si_pass():
    from app.scrapers.real_estate.facebook_real_estate import _looks_like_login_wall
    assert _looks_like_login_wall(
        '<form><input name="email"><input type="password" name="pass"></form>') is True
    # ghilimele simple + majuscule
    assert _looks_like_login_wall(
        "<FORM><INPUT NAME='EMAIL'><INPUT NAME='PASS'></FORM>") is True


def test_login_wall_prinde_form_action_login():
    from app.scrapers.real_estate.facebook_real_estate import _looks_like_login_wall
    assert _looks_like_login_wall(
        '<form method="post" action="/login/?next=https%3A%2F%2Ffb.com%2Fmarketplace">'
        '</form>') is True


def test_login_wall_fals_pe_pagina_de_marketplace():
    # 0 rezultate legitime nu trebuie sa alarmeze.
    from app.scrapers.real_estate.facebook_real_estate import _looks_like_login_wall
    assert _looks_like_login_wall(_HTML_MARKETPLACE) is False


def test_login_wall_fals_pe_pagina_goala():
    from app.scrapers.real_estate.facebook_real_estate import _looks_like_login_wall
    assert _looks_like_login_wall("") is False
    assert _looks_like_login_wall(None) is False
    assert _looks_like_login_wall("<html><body></body></html>") is False


def test_fb_bucla_verifica_login_wall_doar_pe_ramura_goala():
    # pin pe sursa: plasa sa nu dispara la refactor, iar page.content() sa nu ajunga
    # pe calea cu iteme (cost inutil).
    import inspect
    from app.scrapers.real_estate import facebook_real_estate as fb
    src = inspect.getsource(fb._search_sesiune)
    assert "_looks_like_login_wall" in src
    assert "page.content()" in src
    assert src.count("page.content()") == 1


# ── zone: diacritice + granita de cuvant + criteriul keyword-ului ────────────────

def test_zone_cu_diacritice_se_potrivesc():
    assert normalize_zone("Apărătorii Patriei", "bucuresti") is not None
    assert normalize_zone("Grivița", "bucuresti") is not None


def test_zone_substring_nu_mai_prinde_interiorul_cuvintelor():
    # "interior renovat" continea "ior" (alias Titan/IOR) — acum granita de cuvant.
    z = normalize_zone("apartament cu interior renovat complet", "bucuresti")
    assert z is None or "ior" not in z.lower()


class _Kw:
    price_min = None
    price_max = None
    price_currency = None
    rooms = None
    furnished = None
    zone = None


def _ext(zone_normalized):
    return {"zone_normalized": zone_normalized, "price": None,
            "rooms": None, "furnished": None}


def test_criteriul_de_zona_pliaza_diacriticele():
    from app.services.real_estate_scanner import _matches_re_keyword
    kw = _Kw()
    kw.zone = "dorobanti"
    assert _matches_re_keyword(_ext("Dorobanți"), kw) is True


def test_criteriul_de_zona_compusa():
    from app.services.real_estate_scanner import _matches_re_keyword
    kw = _Kw()
    kw.zone = "Piata Unirii"
    assert _matches_re_keyword(_ext("Unirii / Centru"), kw) is True


def test_criteriul_de_zona_tot_respinge_nepotrivirile():
    from app.services.real_estate_scanner import _matches_re_keyword
    kw = _Kw()
    kw.zone = "Baneasa"
    assert _matches_re_keyword(_ext("Berceni"), kw) is False


# ── precedenta pretului: scraperul bate regex-ul ─────────────────────────────────

def test_pretul_scraperului_bate_regexul_pe_descriere(monkeypatch):
    # extract_price pe text ar da 15000 ("avans"); seed-ul scraperului are 89500.
    from app.services import real_estate_scanner as rs
    text = "Apartament superb, avans 15.000 euro, merita vazut"
    p, cur = extract_price(text)
    assert p == 15000.0                      # regex-ul chiar prinde avansul
    # _save_listing e greu de rulat izolat; pinuim ordinea overlay-ului pe sursa:
    import inspect
    src = inspect.getsource(rs)
    idx_seed_first = src.find('if seed["price"] is not None:\n        extracted["price"] = seed["price"]')
    assert idx_seed_first != -1              # seed-ul se aplica NECONDITIONAT


# ── Storia fallback: lei -> RON ──────────────────────────────────────────────────

def test_storia_fallback_detecteaza_lei():
    import inspect
    from app.scrapers.real_estate import storia_scraper as st
    src = inspect.getsource(st)
    assert 'moneda=_cur' in src
    assert '"RON" if (price_el and re.search(r"lei|ron"' in src


# ── OLX imobiliare: data pe anunturi repromovate ─────────────────────────────────

def test_olx_re_reactualizat_azi_are_data():
    from datetime import datetime
    from app.scrapers.real_estate.olx_real_estate import _parse_olx_date
    now = datetime(2026, 7, 11, 12, 0, 0)
    dt = _parse_olx_date("Reactualizat azi la 14:30", now)
    assert dt is not None and dt.hour == 14 and dt.minute == 30
