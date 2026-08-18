"""FBS-2 — `city_page_id` in registru, SSR cu recenta, scara inversata.

Totul OFFLINE, pe dubluri cu `get`/`post`.

Ce fixeaza fisierul, dincolo de comportament:
  · URL-ul CODIFICA termenul. Pana la FBS-2 se interpola brut, ceea ce rupea orice
    termen cu spatiu sau diacritice — adica majoritatea termenilor romanesti reali.
  · filtrul local de varsta se aplica DOAR pe calea SSR, unde am CERUT recenta.
    Pe GraphQL nu se aplica: acolo n-am cerut nicio fereastra, iar anunturile masurate
    ajungeau la 3581 h — un filtru de 24 h ar fi golit calea veche in tacere.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.scrapers.facebook import bootstrap as fb_bootstrap
from app.scrapers.facebook.anchors import ANCORE, dupa_slug
from app.scrapers.facebook.bootstrap import URL_SEARCH
from app.scrapers.facebook.client import search, search_cu_stare
from app.scrapers.facebook.parse import filtreaza_dupa_varsta
from app.scrapers.facebook.ssr import construieste_url

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
_ID_CLUJ = "109529709065736"


def _fix(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _izolare(monkeypatch, tmp_path):
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fb_bootstrap._memo = None
    monkeypatch.delenv("FB_VARSTA_MAX_ORE", raising=False)
    yield
    fb_bootstrap._memo = None


class ClientFals:
    def __init__(self, rute=None, post_rezultate=None):
        self.rute = rute or {}
        self.post_rezultate = list(post_rezultate or [])
        self.cereri = []
        self.sesiune_invalida = False
        self.santinela_ultima = False
        self.blocat = False
        self.c_user = None

    def get(self, url):
        self.cereri.append(("get", url))
        for fragment, rezultat in self.rute.items():
            if fragment in url:
                corp = rezultat[0]
                self.santinela_ultima = "SERP_NO_RESULTS" in corp
                return rezultat
        self.santinela_ultima = False
        return "", 404

    def post(self, url, data=None, headers=None):
        self.cereri.append(("post", url))
        self.santinela_ultima = False
        return self.post_rezultate.pop(0) if self.post_rezultate else ("", 500)


# ── 1-4. URL-ul ──────────────────────────────────────────────────────────────
def test_urlul_poarta_idul_si_recenta():
    u = construieste_url(_ID_CLUJ, "canapea")

    assert u.startswith(f"https://www.facebook.com/marketplace/{_ID_CLUJ}/search?")
    assert "query=canapea" in u
    assert "sortBy=creation_time_descend" in u
    assert "daysSinceListed=1" in u


def test_termenul_cu_spatii_si_diacritice_e_codificat():
    """DEFECTIUNE LATENTA reparata la FBS-2: pana acum termenul se interpola brut
    intr-un f-string. „canapea extensibila" producea un URL cu spatiu in el, iar un
    termen cu diacritice unul cu octeti ne-escapati. Sondele n-au prins-o fiindca au
    rulat toate pe „canapea" — un cuvant fara spatii si fara diacritice."""
    u = construieste_url(_ID_CLUJ, "canapea extensibilă")

    assert " " not in u, u
    assert "ă" not in u, u
    assert "canapea+extensibil%C4%83" in u or "canapea%20extensibil%C4%83" in u, u


def test_termenul_cu_ampersand_nu_sparge_parametrii():
    u = construieste_url(_ID_CLUJ, "masa&scaune")

    assert u.count("&") == 2, f"doar separatorii reali de parametri: {u}"
    assert "sortBy=creation_time_descend" in u


def test_recenta_se_poate_opri():
    u = construieste_url(_ID_CLUJ, "canapea", recenta=False)

    assert "sortBy" not in u and "daysSinceListed" not in u
    assert "query=canapea" in u


# ── 5-8. filtrul de varsta ───────────────────────────────────────────────────
def _anunt(ext, ore=None):
    la = None if ore is None else datetime.now(timezone.utc) - timedelta(hours=ore)
    return {"external_id": str(ext), "listed_at": la}


def test_filtrul_taie_peste_prag_si_pastreaza_sub():
    lista = [_anunt(1, 2), _anunt(2, 23.9), _anunt(3, 38.03), _anunt(4, 300)]

    ramase = filtreaza_dupa_varsta(lista, 24)

    assert [c["external_id"] for c in ramase] == ["1", "2"]


def test_filtrul_pastreaza_anunturile_fara_data():
    """Decizie declarata: un anunt nedatat NU se arunca tacit. `creation_time` e 100%
    populat in masuratori, deci cazul e teoretic — dar un filtru care arunca in tacere
    e exact defectul care se prezinta mai tarziu drept „gol"."""
    ramase = filtreaza_dupa_varsta([_anunt(1, 2), _anunt(2, None), _anunt(3, 999)], 24)

    assert [c["external_id"] for c in ramase] == ["1", "2"]


def test_filtrul_accepta_si_datetime_naiv():
    naiv = {"external_id": "n", "listed_at": datetime.now() - timedelta(hours=1)}

    assert filtreaza_dupa_varsta([naiv], 24) == [naiv]


def test_pragul_zero_sau_negativ_dezactiveaza_filtrul():
    lista = [_anunt(1, 5000)]

    assert filtreaza_dupa_varsta(lista, 0) == lista
    assert filtreaza_dupa_varsta(lista, None) == lista


def test_filtrul_e_pur_ceasul_se_injecteaza():
    acum = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    lista = [{"external_id": "vechi",
              "listed_at": datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)},
             {"external_id": "nou",
              "listed_at": datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc)}]

    ramase = filtreaza_dupa_varsta(lista, 24, acum=acum)

    assert [c["external_id"] for c in ramase] == ["nou"]


# ── 9-10. unde se aplica filtrul: SSR da, GraphQL nu ─────────────────────────
def test_filtrul_se_aplica_pe_calea_ssr(monkeypatch):
    """Fixture-ul SSR are anunturi vechi de zile. Cu pragul implicit de 24 h, calea
    SSR le taie pe toate si intoarce `gol` — fara sa cada la GraphQL."""
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice == []
    assert stare.eticheta == "gol"
    assert [m for m, _ in cl.cereri] == ["get"], \
        "filtrul care goleste NU e un motiv de cadere la GraphQL"


def test_filtrul_NU_se_aplica_pe_calea_graphql():
    """Pe GraphQL n-am cerut nicio fereastra, iar anunturile masurate ajungeau la
    3581 h. Un filtru de 24 h ar fi golit calea veche in tacere."""
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert canonice, "GraphQL intoarce anunturi indiferent de varsta lor"
    assert stare.eticheta == "ok"


def test_pragul_se_citeste_din_mediu(monkeypatch):
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice, "cu pragul ridicat, aceleasi anunturi trec"
    assert stare.eticheta == "ok"


# ── 11-13. scara inversata ───────────────────────────────────────────────────
def test_santinela_pe_treapta_1_nu_cheltuie_graphql():
    """Cel mai important test al rundei: fara asta, inversarea ar adauga o cerere per
    cautare pe toate zonele linistite — si alea sunt majoritatea (randament masurat:
    1-6 anunturi per oras per termen)."""
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_santinela.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice == []
    assert stare.eticheta == "gol"
    assert stare.zero_confirmat is True
    assert [m for m, _ in cl.cereri] == ["get"], "zero cereri GraphQL"
    assert stare.trepte_incercate == 1


def test_apelul_vechi_cu_fb_slug_rupe_zgomotos():
    """Parametrii sunt keyword-only, deci un apel ramas cu `fb_slug=` ridica TypeError
    la apel, nu ancoreaza tacit in alt oras."""
    with pytest.raises(TypeError):
        search("canapea", 44.43, 26.10, fb_slug="bucharest", client=ClientFals())


def test_toate_ancorele_cu_id_trec_prin_ssr(monkeypatch):
    """Contra-proba pe registru: fiecare ancora cu ID chiar ajunge pe URL-ul ei."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cu_id = [a for a in ANCORE if a.city_page_id][:4]

    for a in cu_id:
        cl = ClientFals(rute={f"/marketplace/{a.city_page_id}/search":
                              (_fix("fb_ssr_search.html"), 200)})

        canonice = search("canapea", a.lat, a.lon,
                          city_page_id=a.city_page_id, client=cl)

        assert canonice, a.slug
        assert a.city_page_id in cl.cereri[0][1], a.slug


def test_ancora_fara_id_nu_atinge_ssr():
    # `galati` avea rolul asta pana la FBS-2c, cand a primit ID. Se foloseste una
    # dintre cele 4 ramase FARA ID, si testul verifica intai premisa — altfel ar
    # trece degeaba in ziua in care si asta primeste ID.
    a = dupa_slug("miercurea-ciuc")
    assert a.city_page_id is None, "premisa testului: ancora asta n-are ID"
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    search("canapea", a.lat, a.lon, city_page_id=a.city_page_id, client=cl)

    assert [m for m, _ in cl.cereri] == ["get", "post"]
    assert all("/marketplace/None/" not in u for _m, u in cl.cereri)


def test_golul_produs_de_filtru_e_zero_confirmat():
    """Un gol produs de FILTRU e cel mai bine explicat gol posibil: transportul a
    reusit si avem dovada POZITIVA a ce a venit — anunturi reale, doar prea vechi.
    E o explicatie mai tare decat santinela, unde avem doar cuvantul serverului.

    Conteaza pentru FBS-1b: detectorul de anomalie numara drept suspect orice tick
    fara niciun `ok` in care NU toate golurile sunt confirmate. Fara steagul asta,
    exact zonele linistite — alea cu 1-6 anunturi per termen, adica majoritatea — ar
    fi strans frana degeaba.
    """
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice == [], "fixture-ul are anunturi, dar toate peste pragul de 24 h"
    assert stare.eticheta == "gol"
    assert stare.zero_confirmat is True
    assert [m for m, _ in cl.cereri] == ["get"], "zero cereri GraphQL"


def test_ok_ul_nu_e_marcat_ca_zero_confirmat(monkeypatch):
    """Contra-proba: steagul are inteles DOAR pe `gol`. Cand filtrul lasa anunturi sa
    treaca, verdictul e `ok` si steagul ramane fals."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice
    assert stare.eticheta == "ok"
    assert stare.zero_confirmat is False
