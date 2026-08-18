"""FB-2 — registrul de 51 de ancore geografice si rezolvatorul de scope.

Totul pur: date si functii, zero retea, zero DB.

Testele de geometrie CALCULEAZA cu haversine peste registru; nu asertam pe liste
fixe de localitati, ca sa nu ajungem sa testam ca cineva a copiat corect o lista in
doua locuri. O cifra gresita intr-o coordonata trebuie sa pice un test.
"""
import pytest

from app.services.log_manager import log_manager
from app.scrapers.facebook.anchors import (
    ANCORE, RAZA_KM, Ancora, dupa_slug, haversine_km, selecteaza,
)

# Dreptunghiul Romaniei, generos: prinde o cifra scapata la tastat, nu granita reala.
LAT_MIN, LAT_MAX = 43.5, 48.3
LON_MIN, LON_MAX = 20.2, 29.8


@pytest.fixture
def warns(monkeypatch):
    mesaje = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: mesaje.append((modul, nivel, mesaj)))
    return mesaje


def _warn_uri(mesaje):
    return [m for _, nivel, m in mesaje if nivel == "WARN"]


def _cel_mai_apropiat_vecin(a: Ancora) -> float:
    return min(haversine_km(a.lat, a.lon, b.lat, b.lon) for b in ANCORE if b.slug != a.slug)


# ── 11. structura registrului si geometria ───────────────────────────────────
def test_registrul_are_51_de_ancore_cu_distributia_asteptata():
    assert len(ANCORE) == 51
    pe_tier = {t: sum(1 for a in ANCORE if a.tier == t) for t in (1, 2, 3)}
    assert pe_tier == {1: 15, 2: 26, 3: 10}


def test_tier1_si_tier2_acopera_exact_41_de_unitati_administrative():
    """40 de judete + B. Ilfov (IF) lipseste DELIBERAT: e inelul din jurul
    Bucurestiului, integral sub raza ancorei `bucuresti`, deci o ancora proprie ar
    fi redundanta."""
    coduri = {a.judet for a in ANCORE if a.tier in (1, 2)}
    assert len(coduri) == 41
    assert "IF" not in coduri
    assert "B" in coduri
    # fiecare cod apare exact o data in tier 1+2 (o resedinta per judet)
    lista = [a.judet for a in ANCORE if a.tier in (1, 2)]
    assert len(lista) == len(set(lista))


def test_nicio_ancora_nu_e_aruncata_departe_de_retea():
    """Garda anti-typo: o cifra gresita la o coordonata muta ancora cu sute de km.
    Pragul e generos INTENTIONAT — vezi testul urmator pentru de ce nu e 65."""
    for a in ANCORE:
        d = _cel_mai_apropiat_vecin(a)
        assert d < 120.0, f"{a.slug} e la {d:.1f} km de orice alta ancora"


def test_ancorele_izolate_sunt_exact_cele_masurate():
    """Briefingul FB-2 cerea sa asertam ca fiecare ancora de tier 3 e la mai putin de
    65 km de o alta ancora. Pe coordonatele DATE in briefing, asta e FALS: calafat
    (75.3 km), corabia (70.8) si moldova-noua (66.0) n-au niciun vecin sub 65 km.

    Nu am corectat coordonatele (briefingul cere raportare, nu corectie). Asertia a
    fost inlocuita cu una adevarata si mai stricta: setul ancorelor izolate e
    inghetat exact, deci ORICE mutare de coordonata il schimba si pica testul.

    De fapt izolarea nici nu e un defect: ancorele sunt centre de discuri de 65 km
    care trebuie sa ACOPERE teritoriu, nu sa se suprapuna. Doua ancore la 66 km una
    de alta sunt vecine bune; daca ar fi la 20 km, una din ele ar fi risipa. Ce nu
    se poate verifica aici e acoperirea reala (99.8%% din suprafata): ar cere
    poligonul granitei Romaniei, care nu exista in proiect.
    """
    izolate = {a.slug for a in ANCORE if _cel_mai_apropiat_vecin(a) >= RAZA_KM}
    assert izolate == {
        # tier 1: pe coasta / la granita, fara vecin apropiat
        "constanta", "oradea",
        # tier 2
        "targu-mures", "buzau", "drobeta", "focsani", "tulcea", "resita",
        # tier 3: exact cele trei pe care briefingul le credea neizolate
        "calafat", "corabia", "moldova-noua",
    }


def test_haversine_pe_valori_cunoscute():
    assert haversine_km(44.4325, 26.1025, 44.4325, 26.1025) == 0.0
    cluj = dupa_slug("cluj-napoca")
    campeni = dupa_slug("campeni")
    d = haversine_km(cluj.lat, cluj.lon, campeni.lat, campeni.lon)
    assert 62.0 < d < 63.0, f"{d:.2f}"          # ~62.55 km, chiar sub raza
    # simetrie
    assert haversine_km(campeni.lat, campeni.lon, cluj.lat, cluj.lon) == pytest.approx(d)


# ── 12. igiena datelor ───────────────────────────────────────────────────────
def test_slugurile_sunt_unice():
    sluguri = [a.slug for a in ANCORE]
    assert len(sluguri) == len(set(sluguri))
    assert all(s == s.strip().lower() for s in sluguri)


def test_coordonatele_sunt_in_dreptunghiul_romaniei():
    for a in ANCORE:
        assert LAT_MIN <= a.lat <= LAT_MAX, f"{a.slug} lat={a.lat}"
        assert LON_MIN <= a.lon <= LON_MAX, f"{a.slug} lon={a.lon}"


def test_slugurile_au_disparut_din_registru():
    """FBS-0b a masurat ca slugurile textuale sunt moarte si AUTENTIFICAT (toate trei
    cele testate au dat acelasi set, Jaccard 1.000 intre ele). Campul a fost STERS, nu
    lasat pe None: un camp care arata utilizabil si nu e costa o runda intreaga."""
    assert not hasattr(ANCORE[0], "fb_slug")


def test_optsprezece_ancore_au_city_page_id():
    cu_id = {a.slug: a.city_page_id for a in ANCORE if a.city_page_id is not None}

    assert len(cu_id) == 18, sorted(cu_id)
    assert all(v.isdigit() for v in cu_id.values()), "ID-urile sunt NUMERICE"
    assert len(set(cu_id.values())) == 18, "niciun ID duplicat intre ancore"
    # cele patru masurate direct ca ancoreaza corect, plus Constanta din bucla
    assert cu_id["cluj-napoca"] == "109529709065736"
    assert cu_id["iasi"] == "101882609853782"
    assert cu_id["timisoara"] == "107982459236366"
    assert cu_id["brasov"] == "114791928537378"
    assert cu_id["constanta"] == "110967512261687"


def test_restul_ancorelor_raman_fara_id():
    """Cele 33 fara ID nu sunt un bug: descoperirea lor e FBS-2b, o runda de DATE.
    Pentru ele scara incepe direct de la GraphQL, exact ca inainte de FBS-2."""
    fara = [a.slug for a in ANCORE if a.city_page_id is None]

    assert len(fara) == 33
    assert "alexandria" in fara


def test_alexandria_nu_are_slug_dar_poate_primi_id():
    """Coliziune internationala masurata la FB-0: `alexandria` era slug VALID pe
    Facebook, dar rezolva spre alta Alexandria (0 rezultate la termen romanesc). Un
    `city_page_id` NUMERIC nu poate avea coliziunea asta, deci ancora intra normal in
    descoperirea de la FBS-2b — testul fixeaza distinctia, ca sa nu se piarda."""
    a = dupa_slug("alexandria")

    assert not hasattr(a, "fb_slug")
    assert a.city_page_id is None


def test_dupa_slug():
    assert dupa_slug("iasi").nume == "Iași"
    assert dupa_slug("IASI") is dupa_slug("iasi")     # tolerant la majuscule
    assert dupa_slug("inexistent") is None
    assert dupa_slug("") is None


def test_ancorele_sunt_imutabile():
    with pytest.raises(Exception):
        ANCORE[0].lat = 0.0


# ── 13. rezolvatorul de scope ────────────────────────────────────────────────
def test_national_da_tot_registrul():
    assert selecteaza("national") == ANCORE
    assert selecteaza("") == ANCORE
    assert selecteaza(None) == ANCORE


def test_tier1_da_exact_15():
    rez = selecteaza("tier1")
    assert len(rez) == 15
    assert all(a.tier == 1 for a in rez)


def test_judet_include_ancorele_din_raza():
    rez = {a.slug for a in selecteaza("judet:CJ")}
    assert "cluj-napoca" in rez
    # Campeni e la ~62.6 km de Cluj: intra, dar aproape de margine — asertia
    # testeaza exact granita, nu o lista memorata
    assert "campeni" in rez
    assert "constanta" not in rez


def test_judet_e_case_insensitive():
    assert selecteaza("judet:cj") == selecteaza("judet:CJ")
    assert selecteaza(" JUDET:CJ ") == selecteaza("judet:CJ")


def test_judet_pastreaza_ordinea_din_registru():
    rez = selecteaza("judet:CJ")
    indici = [ANCORE.index(a) for a in rez]
    assert indici == sorted(indici)


def test_ancore_explicite_in_ordinea_registrului_cu_warn_pe_necunoscute(warns):
    rez = selecteaza("ancore:iasi,inexistent,arad")

    assert tuple(a.slug for a in rez) == ("iasi", "arad"), "ordinea e cea din registru"
    assert any("inexistent" in m for m in _warn_uri(warns)), _warn_uri(warns)


def test_scope_invalid_cade_pe_national_cu_warn(warns):
    rez = selecteaza("oras:cluj")

    assert rez == ANCORE
    assert any("oras:cluj" in m for m in _warn_uri(warns)), _warn_uri(warns)


def test_judet_necunoscut_cade_pe_national_cu_warn(warns):
    """Caz pe care briefingul nu-l enumera: format valid, cod inexistent. Se aplica
    aceeasi regula de fail-open — un keyword cu scope stricat trebuie sa scaneze,
    nu sa taca."""
    rez = selecteaza("judet:XX")

    assert rez == ANCORE
    assert any("XX" in m for m in _warn_uri(warns)), _warn_uri(warns)


def test_dezactivate_scot_ancore_din_orice_rezultat():
    rez = selecteaza("national", dezactivate=("bucuresti",))

    assert len(rez) == 50
    assert "bucuresti" not in {a.slug for a in rez}
    # se aplica si pe celelalte formate
    assert "cluj-napoca" not in {a.slug for a in
                                 selecteaza("judet:CJ", dezactivate=("cluj-napoca",))}
    assert selecteaza("tier1", dezactivate=("bucuresti", "arad")) == tuple(
        a for a in ANCORE if a.tier == 1 and a.slug not in ("bucuresti", "arad"))


def test_selectia_e_determinista():
    for scope in ("national", "tier1", "judet:CJ", "ancore:iasi,arad"):
        assert selecteaza(scope) == selecteaza(scope)
    assert selecteaza("national", dezactivate=("iasi",)) == \
        selecteaza("national", dezactivate=("iasi",))
