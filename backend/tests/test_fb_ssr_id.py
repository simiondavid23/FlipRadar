"""FBS-2 — `city_page_id` in registru, SSR cu recenta, scara inversata.

Totul OFFLINE, pe dubluri cu `get`/`post`.

Ce fixeaza fisierul, dincolo de comportament:
  · URL-ul CODIFICA termenul. Pana la FBS-2 se interpola brut, ceea ce rupea orice
    termen cu spatiu sau diacritice — adica majoritatea termenilor romanesti reali.
  · filtrul local de varsta se aplica pe TOATE treptele care intorc anunturi (FBS-14).
    Motivele difera insa, si de-aia si codul si verdictul difera: pe SSR recenta s-a
    cerut SI serverului, deci filtrul doar strange fereastra lui (~38 h) si un gol de
    acolo e `zero_confirmat`; pe GraphQL nu s-a cerut nimanui nimic (anunturile masurate
    ajungeau la 3581 h), filtrul e singura garantie, iar un gol produs de el NU e
    `zero_confirmat` — serverul n-a confirmat nimic, noi am taiat.
"""
import copy
import json
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


@pytest.fixture
def warns(monkeypatch):
    """Captureaza emit-urile. NEautouse deliberat: doar testele FBS-14 au nevoie de
    ele, iar restul fisierului ramane exact cum era."""
    from app.services.log_manager import log_manager
    mesaje = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: mesaje.append((nivel, mesaj)))
    return mesaje


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


def test_filtrul_se_aplica_SI_pe_calea_graphql():
    """FBS-14 a INVERSAT proprietatea pe care o fixa testul asta.

    Pana aici se numea `test_filtrul_NU_se_aplica_pe_calea_graphql` si sustinea ca „pe
    GraphQL n-am cerut nicio fereastra, deci nu filtram" — adevarat ca descriere a
    codului, dar consecinta era ca o degradare la treapta 2 intorcea anunturi de ORICE
    varsta (fixture-ul real are 182-4361 h), care in aval aratau ca oricare altele.
    Garantia e acum uniforma: nimic DATAT peste prag nu iese din nucleu, indiferent de
    treapta. Testul se rescrie, nu se sterge — el e chiar locul unde se vede schimbarea.
    """
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    # Toate cele 24 din fixture sunt peste pragul implicit -> nu iese niciunul.
    assert canonice == []
    assert stare.trepte_incercate == 2, "s-a ajuns chiar pe treapta degradata"
    # D3 — gol PRODUS DE FILTRU, nu confirmat de server.
    assert stare.eticheta == "gol" and stare.zero_confirmat is False


def test_pe_graphql_cu_pragul_ridicat_anunturile_vechi_trec(monkeypatch):
    """Contra-proba: filtrul e ce le taie, nu altceva de pe drum. Si dovada ca pragul
    degradat citeste ACEEASI sursa de mediu ca cel de la treapta 1."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert len(canonice) == 24 and stare.eticheta == "ok"


# ── FBS-14: taierea de varsta pe treptele degradate, cu contoare ─────────────
def _graphql_cu_varste(varste_ore):
    """Raspuns GraphQL sintetic. `None` intr-o pozitie = anunt FARA `creation_time`.

    Se construieste peste forma REALA din fixture (nu una inventata de la zero), ca sa
    treaca prin acelasi `extrage_anunturi` ca in productie.
    """
    from app.scrapers.facebook.graphql import extrage_anunturi

    sablon = extrage_anunturi(json.loads(_fix("fb_graphql_ok.json")))[0]
    acum = datetime.now(timezone.utc)
    noduri = []
    for i, ore in enumerate(varste_ore):
        nod = copy.deepcopy(sablon)
        nod["id"] = f"fbs14-{i}"
        if ore is None:
            nod.pop("creation_time", None)
            nod.pop("if_gk_just_listed_tag_on_search_feed", None)
        else:
            moment = int((acum - timedelta(hours=ore)).timestamp())
            nod["creation_time"] = moment
            if isinstance(nod.get("if_gk_just_listed_tag_on_search_feed"), dict):
                nod["if_gk_just_listed_tag_on_search_feed"]["creation_time"] = moment
        noduri.append({"node": nod})
    return json.dumps({"data": {"a": {"edges": noduri}}})


def _pe_graphql(monkeypatch, varste_ore, prag="48"):
    """Duce scara pe treapta 2 (fara `city_page_id`) cu feedul sintetic dat."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", prag)
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_graphql_cu_varste(varste_ore), 200)])
    return search_cu_stare("canapea", 44.43, 26.10, client=cl)


def test_treapta_2_taie_vechile_pastreaza_proaspetele_si_nedatatele(monkeypatch, warns):
    """D1 + D2 intr-un singur feed: proaspete, peste prag, si nedatate."""
    canonice, stare = _pe_graphql(monkeypatch, [1.0, 5.0, 100.0, 500.0, None])

    assert len(canonice) == 3, "doua proaspete + una nedatata"
    assert sum(1 for c in canonice if c["listed_at"] is None) == 1
    assert stare.eticheta == "ok" and stare.trepte_incercate == 2

    info = [m for niv, m in warns if niv == "INFO" and "treapta 2" in m]
    assert len(info) == 1, f"UN emit per apel, nu {len(info)}"
    assert "2 din 5 anunturi peste pragul de 48 h" in info[0], info
    assert "1 fara data pastrate" in info[0], info


def test_treapta_2_integral_peste_prag_da_gol_fara_zero_confirmat(monkeypatch):
    """D3 — golul PRODUS DE FILTRU nu e un zero confirmat de server. Distinctia conteaza:
    `zero_confirmat` hraneste detectorul de anomalie din FBS-1b, iar un gol al nostru
    n-are voie sa treaca drept liniste a pietei."""
    canonice, stare = _pe_graphql(monkeypatch, [100.0, 200.0, 3000.0])

    assert canonice == []
    assert stare.eticheta == "gol"
    assert stare.zero_confirmat is False
    assert stare.trepte_incercate == 2


def test_treapta_2_integral_nedatat_trece_tot(monkeypatch, warns):
    """LIMITA CUNOSCUTA a variantei A, documentata ca test: `filtreaza_dupa_varsta`
    pastreaza nedatatele („nu stiu varsta" nu inseamna „vechi"), iar acoperirea lui
    `listed_at` e masurata 100% doar pe SSR — pe GraphQL e NEMASURATA. Contorul de mai
    jos e instrumentul care va spune, la prima degradare reala, daca filtrul musca sau
    doar exista."""
    canonice, stare = _pe_graphql(monkeypatch, [None, None, None])

    assert len(canonice) == 3 and stare.eticheta == "ok"
    info = [m for niv, m in warns if niv == "INFO" and "treapta 2" in m]
    assert len(info) == 1
    assert "0 din 3" in info[0] and "3 fara data pastrate" in info[0], info


def test_treapta_2_feed_integral_proaspat_nu_emite_nimic(monkeypatch, warns):
    """Emit-ul apare doar cand are ce raporta — altfel jurnalul s-ar umple de linii
    care spun „n-am facut nimic"."""
    canonice, _ = _pe_graphql(monkeypatch, [1.0, 2.0, 3.0])

    assert len(canonice) == 3
    assert not [m for niv, m in warns if niv == "INFO" and "treapta 2" in m]


def test_pragul_degradat_vine_din_mediu(monkeypatch):
    """Filtrul degradat si cel de la treapta 1 citesc ACEEASI sursa: acelasi anunt cade
    sau trece dupa cum e pragul."""
    proaspete_la_48, _ = _pe_graphql(monkeypatch, [10.0], prag="48")
    assert len(proaspete_la_48) == 1

    proaspete_la_5, stare = _pe_graphql(monkeypatch, [10.0], prag="5")
    assert proaspete_la_5 == [] and stare.zero_confirmat is False


def test_treapta_1_ramane_neatinsa(monkeypatch, warns):
    """D4 — regresie de neutralitate: pe treapta 1 nimic nu se schimba, si mai ales
    filtrarea NU se aplica de doua ori. `zero_confirmat` de acolo ramane True."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice and stare.eticheta == "ok" and stare.trepte_incercate == 1
    assert [m for m, _ in cl.cereri] == ["get"], "nu s-a coborat pe scara"
    # Emit-ul de treapta degradata nu are ce cauta pe calea SSR.
    assert not [m for niv, m in warns if "treapta 2" in m or "treapta 3" in m]


def test_treapta_1_goala_de_filtru_ramane_zero_confirmat(monkeypatch):
    """Contrastul explicit dintre cele doua goluri: pe treapta 1 transportul a REUSIT si
    avem dovada pozitiva a ce a venit, deci golul e `zero_confirmat`; pe 2-3 nu."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "0.0001")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice, stare = search_cu_stare("canapea", 46.77, 23.62,
                                      city_page_id=_ID_CLUJ, client=cl)

    assert canonice == [] and stare.eticheta == "gol"
    assert stare.zero_confirmat is True


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


# ── 14-19. FBS-6: pragul de pret, trimis server-side pe treapta 1 ────────────
def test_absenta_pragului_lasa_urlul_byte_identic():
    """Garda cea mai importanta a rundei. Daca adaugarea parametrului ar schimba
    URL-ul si cand nu e cerut, toate fixture-urile SSR si toate testele de URL de
    mai sus ar deveni invalide TACIT — exact modul de esec pe care FBS-2 l-a platit
    o data cu interpolarea bruta a termenului."""
    assert (construieste_url(_ID_CLUJ, "canapea")
            == construieste_url(_ID_CLUJ, "canapea", pret_min=None))


def test_pragul_ajunge_in_url_langa_recenta():
    u = construieste_url(_ID_CLUJ, "iphone 15 pro max", pret_min=1500)

    assert "minPrice=1500" in u
    assert "sortBy=creation_time_descend" in u
    assert "daysSinceListed=1" in u
    assert " " not in u, f"termenul ramane codificat: {u}"


@pytest.mark.parametrize("prag", [0, -5])
def test_pragul_zero_sau_negativ_nu_ajunge_in_url(prag):
    """Aceeasi conventie ca in `_build_search_url`: doar strict pozitiv inseamna
    prag. Un `minPrice=0` trimis degeaba ar fi si zgomot, si o a doua semantica."""
    u = construieste_url(_ID_CLUJ, "canapea", pret_min=prag)

    assert "minPrice" not in u
    assert u == construieste_url(_ID_CLUJ, "canapea")


def test_pragul_se_propaga_pe_scara_pana_la_treapta_1(monkeypatch):
    """Contra-proba de capat: pragul dat lui `search` chiar ajunge in GET-ul SSR."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice = search("canapea", 46.77, 23.62, city_page_id=_ID_CLUJ,
                      client=cl, pret_min=3000)

    assert canonice
    assert [m for m, _ in cl.cereri] == ["get"], "treapta 1, fara cadere la GraphQL"
    assert "minPrice=3000" in cl.cereri[0][1]


def _captureaza_nucleul(monkeypatch):
    """Dublu peste `nucleu_search` care retine kwargs-urile primite."""
    from app.services.radar import facebook_scraper as fb

    captat = {}

    def fals(query, lat, lon, **kw):
        captat.update(kw)
        return []

    monkeypatch.delenv("FB_RADAR_ANCORA", raising=False)
    monkeypatch.setattr(fb, "nucleu_search", fals)
    monkeypatch.setattr(fb.log_manager, "emit", lambda *a, **k: None)
    return fb, captat


def test_radarul_trunchiaza_pragul_ca_build_search_url(monkeypatch):
    """`2999.9 -> 2999`, prin `int`, exact ca pe calea de sesiune. Daca cele doua cai
    ar rotunji diferit, acelasi keyword ar cere praguri diferite dupa `FB_MOD`."""
    fb, captat = _captureaza_nucleul(monkeypatch)

    fb._search_logout("iphone", None, None, 2999.9, None)

    assert captat["pret_min"] == 2999


@pytest.mark.parametrize("min_price", [None, 0])
def test_radarul_fara_prag_nu_trimite_niciun_prag(monkeypatch, min_price):
    fb, captat = _captureaza_nucleul(monkeypatch)

    fb._search_logout("iphone", None, None, min_price, None)

    assert captat["pret_min"] is None


# ── 20-26. FBS-10: plafonul de pret, simetricul pragului ─────────────────────
def test_absenta_plafonului_lasa_urlul_byte_identic():
    """Aceeasi garda ca la FBS-6, acum pe a doua margine — si inca o data PESTE prag:
    un URL care avea deja `minPrice` nu are voie sa se schimbe cand plafonul lipseste,
    altfel fixture-urile si testele scrise dupa FBS-6 ar deveni invalide TACIT."""
    assert (construieste_url(_ID_CLUJ, "canapea")
            == construieste_url(_ID_CLUJ, "canapea", pret_max=None))
    assert (construieste_url(_ID_CLUJ, "canapea", pret_min=1500)
            == construieste_url(_ID_CLUJ, "canapea", pret_min=1500, pret_max=None))


def test_plafonul_ajunge_in_url_langa_recenta():
    u = construieste_url(_ID_CLUJ, "iphone 15 pro max", pret_max=1500)

    assert "maxPrice=1500" in u
    assert "sortBy=creation_time_descend" in u
    assert "daysSinceListed=1" in u
    assert " " not in u, f"termenul ramane codificat: {u}"


def test_ordinea_marginilor_e_cea_masurata_la_v3():
    """`minPrice` INAINTEA lui `maxPrice`. Ordinea nu e cosmetica: forma asta e cea pe
    care sonda FBS-V3 a masurat-o ca respectata, si tot ea pastreaza URL-ul cu prag dar
    fara plafon byte-identic cu forma post-FBS-6."""
    u = construieste_url(_ID_CLUJ, "iphone 15 pro max", pret_min=1245, pret_max=1588)

    assert "minPrice=1245" in u and "maxPrice=1588" in u
    assert u.index("minPrice") < u.index("maxPrice")


@pytest.mark.parametrize("plafon", [0, -5])
def test_plafonul_zero_sau_negativ_nu_ajunge_in_url(plafon):
    """Aceeasi conventie ca pentru prag si ca in `_build_search_url`: doar strict
    pozitiv inseamna plafon."""
    u = construieste_url(_ID_CLUJ, "canapea", pret_max=plafon)

    assert "maxPrice" not in u
    assert u == construieste_url(_ID_CLUJ, "canapea")


def test_plafonul_se_propaga_pe_scara_pana_la_treapta_1(monkeypatch):
    """Contra-proba de capat: plafonul dat lui `search` chiar ajunge in GET-ul SSR,
    si NU se cade la GraphQL — treapta 2 nu poarta marginile de pret (D3)."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    canonice = search("canapea", 46.77, 23.62, city_page_id=_ID_CLUJ,
                      client=cl, pret_max=1200)

    assert canonice
    assert [m for m, _ in cl.cereri] == ["get"], "treapta 1, fara cadere la GraphQL"
    assert "maxPrice=1200" in cl.cereri[0][1]


def test_ambele_margini_se_propaga_impreuna(monkeypatch):
    """Forma pe care o trimite productia dupa FBS-10, si cea masurata la FBS-V3."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={f"/marketplace/{_ID_CLUJ}/search":
                          (_fix("fb_ssr_search.html"), 200)})

    search("canapea", 46.77, 23.62, city_page_id=_ID_CLUJ, client=cl,
           pret_min=1245, pret_max=1588)

    url = cl.cereri[0][1]
    assert "minPrice=1245" in url and "maxPrice=1588" in url


def test_radarul_trunchiaza_plafonul_ca_build_search_url(monkeypatch):
    """`2999.9 -> 2999`, prin `int`, EXACT ca pragul si ca pe calea de sesiune."""
    fb, captat = _captureaza_nucleul(monkeypatch)

    fb._search_logout("iphone", 2999.9, None, None, None)

    assert captat["pret_max"] == 2999


@pytest.mark.parametrize("max_price", [None, 0])
def test_radarul_fara_plafon_nu_trimite_niciun_plafon(monkeypatch, max_price):
    fb, captat = _captureaza_nucleul(monkeypatch)

    fb._search_logout("iphone", max_price, None, None, None)

    assert captat["pret_max"] is None


def test_radarul_trimite_ambele_margini_deodata(monkeypatch):
    fb, captat = _captureaza_nucleul(monkeypatch)

    fb._search_logout("iphone", 6000.0, None, 1500.0, None)

    assert (captat["pret_min"], captat["pret_max"]) == (1500, 6000)
