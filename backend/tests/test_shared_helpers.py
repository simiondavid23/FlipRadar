"""REF-1 — helperi partajați după unificarea duplicatelor. Funcții pure + lacăt de regresie
pe extractorul FB Groups mutat (output înghețat înainte de mutare).
"""
from app.utils.id_csv import parse_id_csv
from app.scrapers.real_estate._common import norm_city_slug
from app.services.real_estate.extractor import extract_real_estate_data


# ── parse_id_csv (unificat radar/auto/RE) ────────────────────────────────────
def test_parse_id_csv_tolerant():
    # comportamentul EXACT al funcției existente (testez CE face, nu ce descrie taskul):
    # None/"" -> [] (NU None), tokeni non-numerici ignorați, strip pe fiecare token.
    assert parse_id_csv("1,abc,3,") == [1, 3]
    assert parse_id_csv("") == []
    assert parse_id_csv(None) == []
    assert parse_id_csv("  10 , 20 ") == [10, 20]


def test_parse_id_csv_importabil_din_routere():
    # aceeași funcție unificată e folosită de cele 3 routere (identitate, nu doar egalitate)
    from app.routers.radar import parse_id_csv as radar_fn
    from app.routers.auto_listings_keywords import parse_id_csv as auto_fn
    from app.routers.real_estate_keywords import parse_id_csv as re_fn
    assert parse_id_csv is radar_fn is auto_fn is re_fn


# ── norm_city_slug (storia folosește acum helperul din _common) ──────────────
def test_norm_city_slug_orase():
    assert norm_city_slug("București") == "bucuresti"
    assert norm_city_slug("Cluj-Napoca") == "cluj-napoca"
    assert norm_city_slug("Piatra Neamț") == "piatra-neamt"


def test_norm_city_slug_echivalent_loc_key():
    # pe cele 10 orașe din dropdown, slug-ul rămâne cheie validă în _STORIA_LOCATION_PATHS
    # (nicio cheie orfană după înlocuirea _loc_key cu norm_city_slug).
    from app.scrapers.real_estate.storia_scraper import _STORIA_LOCATION_PATHS
    cities = ["București", "Cluj-Napoca", "Iași", "Timișoara", "Brașov",
              "Constanța", "Sibiu", "Oradea", "Arad", "Pitești"]
    for c in cities:
        assert norm_city_slug(c) in _STORIA_LOCATION_PATHS, f"{c} -> {norm_city_slug(c)} orfan"


# ── extract_real_estate_data (mutat din real_estate_extractor.py, comportament identic) ──
# Lacătele de regresie: output-ul EXACT capturat ÎNAINTE de mutare (rulat pe funcția veche).
_T1 = "Inchiriez apartament 2 camere Floreasca, 450 euro/luna, mobilat, parcare, balcon."
_T2 = "Vand garsoniera Sector 3, 42000 euro, etaj 2, 38 mp, renovat."


def test_extract_real_estate_data_regresie_pret():
    assert extract_real_estate_data(_T1) == {
        "pret": 450, "moneda": "EUR", "tip_anunt": "inchiriere",
        "tip_proprietate": "2 camere", "zona": "Floreasca",
        "facilitati": "parcare, balcon, mobilat", "camere": 2,
    }


def test_extract_real_estate_data_regresie_zona():
    assert extract_real_estate_data(_T2) == {
        "pret": 42000, "moneda": "EUR", "tip_anunt": "vanzare",
        "tip_proprietate": "garsoniera", "suprafata_mp": 38, "etaj": "etaj 2",
        "zona": "Sector 3", "facilitati": "renovat", "camere": 1,
    }
