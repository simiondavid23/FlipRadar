"""UI-1 — Imobiliare serializeaza `pret_anterior`, cheia unica a badge-ului de scadere.

DE CE EXISTA: pana la UI-1 erau doua mecanisme paralele pentru aceeasi informatie —
Radar trimitea `pret_anterior` (scalar, din `radar_listings`), iar Imobiliare isi
calcula procentul in pagina, din `price_history`. Doua badge-uri, doua culori, doua
locuri in care se putea strica garda. Acum badge-ul e unul singur si citeste o singura
cheie, deci Imobiliare trebuie sa o PRODUCA — derivata din propriul istoric.

Ce apara testul: `istoric[0]` e PRIMUL pret vazut, fiindca scannerul face `append` cu
pretul vechi la fiecare scadere >= 5% (real_estate_scanner.py). Daca cineva ar lua
`istoric[-1]` (ultimul pret inainte de scaderea curenta), badge-ul ar arata o scadere
mai mica decat cea reala — exact ce D-S1 evita si pe Radar.
"""
from decimal import Decimal

import pytest

from app.routers.real_estate_keywords import _pret_anterior


def _ist(*preturi):
    return [{"price": p, "currency": "EUR", "date": None} for p in preturi]


# ── cazul viu ──────────────────────────────────────────────────────────────────
def test_ia_primul_pret_din_istoric():
    """500 -> 450 -> 400: referinta e 500, nu 450."""
    assert _pret_anterior(_ist(500, 450), 400.0) == 500.0


def test_o_singura_scadere():
    assert _pret_anterior(_ist(500), 450.0) == 500.0


# ── inertitate ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("istoric", [None, [], "nu e lista", [None], ["fara dict"]])
def test_fara_istoric_util_da_none(istoric):
    assert _pret_anterior(istoric, 400.0) is None


def test_pretul_vechi_nu_e_mai_mare_da_none():
    """Garda oglindeste badge-ul: strict mai mare. Egal inseamna „n-a scazut nimic"."""
    assert _pret_anterior(_ist(400), 400.0) is None
    assert _pret_anterior(_ist(350), 400.0) is None


def test_pretul_curent_lipsa_da_none():
    assert _pret_anterior(_ist(500), None) is None


def test_pretul_din_istoric_neparsabil_da_none():
    assert _pret_anterior([{"price": "n/a"}], 400.0) is None
    assert _pret_anterior([{"currency": "EUR"}], 400.0) is None


# ── Decimal: coloana `price` e Numeric in model ────────────────────────────────
def test_merge_cu_decimal():
    """`_listing_dict` converteste `price` la float inainte, dar helperul nu are voie sa
    presupuna asta — coloana e `Numeric`, deci un apelant viitor poate trimite Decimal."""
    assert _pret_anterior(_ist(Decimal("500.00")), Decimal("400.00")) == 500.0
    assert _pret_anterior(_ist(Decimal("400.00")), Decimal("400.00")) is None


# ── integrarea in serializare ──────────────────────────────────────────────────
def test_listing_dict_pune_cheia(auth_client):
    """Cheia trebuie sa existe MEREU in raspuns (None cand n-a scazut), ca frontendul
    sa n-o trateze ca pe un camp optional per modul."""
    from app.database import SessionLocal
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing
    from app.routers.real_estate_keywords import _listing_dict

    uid = auth_client.get("/api/auth/me").json()["id"]
    db = SessionLocal()
    try:
        rand = RealEstateMonitorListing(
            user_id=uid, external_id="ui1-test", platform="storia",
            title="Apartament de test", price=400, currency="EUR",
            url="https://storia.ro/x", status="active",
            price_history=_ist(500, 450),
        )
        d = _listing_dict(rand)
        assert d["pret_anterior"] == 500.0
        assert d["price"] == 400.0
        assert d["price_history"], "istoricul ramane serializat (modalul il afiseaza)"

        rand.price_history = None
        assert _listing_dict(rand)["pret_anterior"] is None
    finally:
        db.close()
