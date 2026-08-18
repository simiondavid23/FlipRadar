"""FBS-1 — identitatea autentificata si detectiile din nucleul Facebook.

Totul OFFLINE. Clientul e un dublu cu `get`/`post`; nicio cerere reala nu pleaca.

Fixture-urile si mostrele lor sursa (dump-urile sondelor, gitignored):
  fb_graphql_identitate_invalida.json <- dumps_fbs0/cerere_02_graphql_anonim.json
                                         (raspunsul REAL de 249 octeti; rid/lid anonimizate)
  fb_graphql_santinela.json           <- dumps_fbs0/cerere_08_graphql_ctime_days.json
                                         (subarborele minim, cursorul scurtat)
  fb_ssr_santinela.html               <- dumps_fbs0d/cerere_01_buc_search_fara_query.html
                                         (blocul de script cu santinela, restul paginii taiat)
  fb_sesiune_storage_state.json       <- CONSTRUIT: forma reala, valori sintetice.
                                         Un `xs` real e un jeton viu, nu intra in repo.

Principiul rundei (D9): tot ce s-a adaugat e inactiv pana cand cineva paseaza
explicit o sesiune. Primul test din fisier e chiar dovada asta.
"""
import json
import os

import pytest

from app.scrapers.facebook import bootstrap as fb_bootstrap
from app.scrapers.facebook import client as fb_client
from app.scrapers.facebook.bootstrap import (
    Bootstrap, acelasi_cont, extrage_bootstrap, incarca_sau_bootstrapeaza,
    URL_SEARCH,
)
from app.scrapers.facebook.client import (
    FacebookClient, StareCautare, _injecteaza_sesiune, search_cu_stare,
)
from app.scrapers.facebook.graphql import (
    COD_IDENTITATE_INVALIDA, Identitate, cauta_cu_cod, identitate_din,
)
from app.scrapers.facebook.parse import looks_like_no_results

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fix(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _izolare(monkeypatch, tmp_path):
    """DATA_DIR spre tmp_path si `_memo` golit — la fel ca in test_fb_core."""
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fb_bootstrap._memo = None
    yield
    fb_bootstrap._memo = None


class ClientFals:
    """Dublu care inregistreaza cererile si raspunde din rute/liste."""

    def __init__(self, rute=None, post_rezultate=None, c_user=None,
                 sesiune_invalida=False, santinela_ultima=False):
        self.rute = rute or {}
        self.post_rezultate = list(post_rezultate or [])
        self.cereri = []
        self.corpuri_trimise = []
        self.antete_trimise = []
        self.c_user = c_user
        self.sesiune_invalida = sesiune_invalida
        self.santinela_ultima = santinela_ultima

    def get(self, url):
        self.cereri.append(("get", url))
        for fragment, rezultat in self.rute.items():
            if fragment in url:
                return rezultat
        return "", 404

    def post(self, url, data=None, headers=None):
        self.cereri.append(("post", url))
        self.corpuri_trimise.append(data)
        self.antete_trimise.append(headers)
        return self.post_rezultate.pop(0) if self.post_rezultate else ("", 500)


class _BootFals:
    friendly_name = "CometMarketplaceSearchContentContainerQuery"
    doc_id = "27517490627932547"
    lsd = "AVpXlsd"
    fb_dtsg = None
    c_user = None


# ── 1-3. D9: corpul anonim ramane byte-identic ───────────────────────────────
def test_corpul_ramane_identic_fara_identitate():
    """D9, cerinta centrala a rundei: fara identitate, corpul e EXACT cel de dinainte.

    Nu se compara cu o copie scrisa de mana (aia ar imbatrani odata cu codul), ci cu
    literalul pe care il cere contractul: `av` si `__user` egale cu "0", si NICIUN
    `fb_dtsg`, nici in corp nici in antet.
    """
    cl = ClientFals(post_rezultate=[('{"data":{}}', 200)])
    cauta_cu_cod(cl, _BootFals(), {"x": 1})

    date = cl.corpuri_trimise[0]
    antete = cl.antete_trimise[0]
    assert date["av"] == "0"
    assert date["__user"] == "0"
    assert "fb_dtsg" not in date
    assert "x-fb-dtsg" not in antete
    # setul de chei e cel istoric, nimic adaugat pe tacute
    assert set(date) == {
        "av", "__user", "__a", "__req", "dpr", "__ccg", "server_timestamps",
        "fb_api_caller_class", "fb_api_req_friendly_name", "variables", "doc_id", "lsd",
    }


def test_corpul_autentificat_poarta_identitatea():
    cl = ClientFals(post_rezultate=[('{"data":{}}', 200)])
    ident = Identitate(c_user="100000000000001", fb_dtsg="NAcM-dtsg-sintetic")

    cauta_cu_cod(cl, _BootFals(), {"x": 1}, identitate=ident)

    date, antete = cl.corpuri_trimise[0], cl.antete_trimise[0]
    assert date["av"] == "100000000000001"
    assert date["__user"] == "100000000000001"
    assert date["fb_dtsg"] == "NAcM-dtsg-sintetic"
    assert antete["x-fb-dtsg"] == "NAcM-dtsg-sintetic"


def test_identitatea_e_ambele_sau_niciuna():
    """Un `c_user` fara `fb_dtsg` (sau invers) e chiar reteta pentru 1357004."""
    assert identitate_din(_BootFals()) is None

    doar_dtsg = type("B", (), {"c_user": None, "fb_dtsg": "d"})()
    doar_user = type("B", (), {"c_user": "1", "fb_dtsg": None})()
    assert identitate_din(doar_dtsg) is None
    assert identitate_din(doar_user) is None

    ambele = type("B", (), {"c_user": "1", "fb_dtsg": "d"})()
    assert identitate_din(ambele) == Identitate("1", "d")


# ── 4-6. cele doua canale de eroare ──────────────────────────────────────────
def test_eroarea_de_la_radacina_e_citita():
    """Raspunsul REAL de 249 de octeti: `error` la radacina, nu in `errors[]`."""
    cl = ClientFals(post_rezultate=[(_fix("fb_graphql_identitate_invalida.json"), 200)])

    raspuns, cod = cauta_cu_cod(cl, _BootFals(), {})

    assert raspuns is None
    assert cod == COD_IDENTITATE_INVALIDA == 1357004


def test_errors_continua_sa_fie_citit():
    """Canalul vechi nu s-a pierdut adaugandu-l pe cel nou."""
    corp = json.dumps({"errors": [{"message": "missing_required_variable_value",
                                   "code": 1675012}]})
    cl = ClientFals(post_rezultate=[(corp, 200)])

    raspuns, cod = cauta_cu_cod(cl, _BootFals(), {})

    assert raspuns is None
    assert cod == 1675012


def test_error_zero_nu_e_tratat_ca_eroare():
    """`"error":0` e un marcaj de succes la Facebook, nu un cod."""
    corp = json.dumps({"error": 0, "data": {"marketplace_search": {"edges": []}}})
    cl = ClientFals(post_rezultate=[(corp, 200)])

    raspuns, cod = cauta_cu_cod(cl, _BootFals(), {})

    assert raspuns is not None
    assert cod is None


# ── 7-9. santinela, pe AMBELE cai ────────────────────────────────────────────
def test_santinela_pe_json_de_graphql():
    assert looks_like_no_results(json.loads(_fix("fb_graphql_santinela.json"))) is True


def test_santinela_pe_html_de_ssr():
    assert looks_like_no_results(_fix("fb_ssr_santinela.html")) is True


def test_santinela_absenta_pe_raspunsuri_normale():
    assert looks_like_no_results(_fix("fb_ssr_search.html")) is False
    assert looks_like_no_results(_fix("fb_graphql_ok.json")) is False
    assert looks_like_no_results("") is False
    assert looks_like_no_results(None) is False


# ── 10-12. scara: santinela, identitate, login-wall ──────────────────────────
def _client_real_cu_sesiune(tmp_path, corp_get, corp_post, status_post=200):
    """`FacebookClient` REAL (ca sa treaca prin `_inspecteaza`), cu transportul
    inlocuit. Sesiunea sintetica ii da `c_user`, deci detectiile sunt active."""
    cale = os.path.join(_FIX, "fb_sesiune_storage_state.json")
    cl = FacebookClient(sleep=lambda _s: None, sesiune_path=cale)

    def _cere(metoda, url, **kw):
        corp = corp_post if metoda == "post" else corp_get
        status = status_post if metoda == "post" else 200
        cl._inspecteaza(corp, url)
        cl.cereri.append((metoda, url))
        return corp, status

    cl.cereri = []
    cl._cere = _cere
    return cl


def test_santinela_opreste_urcarea_scarii(tmp_path):
    """Cu santinela, scara se opreste la treapta 1: `gol`, o singura pereche
    bootstrap+POST, fara re-bootstrap si fara SSR."""
    cl = _client_real_cu_sesiune(tmp_path, _fix("fb_ssr_search.html"),
                                 _fix("fb_graphql_santinela.json"))

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, city_page_id=None,
                                      client=cl)

    assert canonice == []
    assert stare.eticheta == "gol"
    assert stare.trepte_incercate == 2   # FBS-2: GraphQL e treapta 2
    assert len([c for c in cl.cereri if c[0] == "post"]) == 1


def test_identitatea_invalida_reincearca_exact_o_data(tmp_path):
    """1357004 se comporta ca un sablon invechit — o data. A doua oara e sesiune moarta."""
    cl = _client_real_cu_sesiune(tmp_path, _fix("fb_ssr_search.html"),
                                 _fix("fb_graphql_identitate_invalida.json"))

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, city_page_id=None,
                                      client=cl)

    assert canonice == []
    assert stare.eticheta == "sesiune_invalida"
    assert stare.cod == COD_IDENTITATE_INVALIDA
    assert stare.trepte_incercate == 3          # FBS-2: cele doua trepte GraphQL
    assert len([c for c in cl.cereri if c[0] == "post"]) == 2   # exact o reincercare


def test_login_wall_cu_sesiune_da_sesiune_invalida(tmp_path):
    cl = _client_real_cu_sesiune(tmp_path, _fix("fb_login_wall.html"), "")

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, city_page_id=None,
                                      client=cl)

    assert canonice == []
    assert stare.eticheta == "sesiune_invalida"
    assert stare.eticheta != "esec"


def test_login_wall_fara_sesiune_nu_schimba_nimic(tmp_path):
    """D9: pe calea logat-out, un login-wall ramane exact ce era — `esec`/`blocat`,
    nu `sesiune_invalida`. Facebook serveste frecvent formularul de login logat-out,
    si comportamentul de acolo nu are voie sa se schimbe."""
    cl = FacebookClient(sleep=lambda _s: None)          # FARA sesiune
    perete = _fix("fb_login_wall.html")

    def _cere(metoda, url, **kw):
        cl._inspecteaza(perete, url)
        return perete, 200

    cl._cere = _cere

    _canonice, stare = search_cu_stare("canapea", 44.43, 26.10, city_page_id=None,
                                       client=cl)

    assert cl.sesiune_invalida is False
    assert stare.eticheta in ("esec", "blocat")


def test_checkpoint_nu_da_fals_pozitiv_pe_pagini_sanatoase():
    """Markerul evident, `/checkpoint/`, e GRESIT: apare in tabelele de rute din JS-ul
    unei pagini de marketplace perfect sanatoase. Folosit ca detector, ar fi omorat
    orice scan autentificat la PRIMA cerere. Testul fixeaza masuratoarea."""
    sanatoase = ["fb_ssr_search.html", "fb_ssr_categorie.html", "fb_graphql_ok.json"]

    for nume in sanatoase:
        corp = _fix(nume)
        assert fb_client._are_checkpoint(corp) is False, nume

    # ...si dovada ca respingerea markerului naiv nu e teoretica:
    assert "/checkpoint/" in _fix("fb_ssr_search.html")


def test_checkpoint_prinde_markerii_specifici():
    for marker in ('"checkpoint"', "/checkpoint/?next=1", "checkpoint_flow"):
        assert fb_client._are_checkpoint(f"<html>x{marker}y</html>") is True


def test_pagina_sanatoasa_cu_sesiune_nu_invalideaza_sesiunea():
    """Consecinta directa a testului de mai sus, dar pe client: o pagina normala nu
    are voie sa marcheze sesiunea drept moarta."""
    cl = FacebookClient(sleep=lambda _s: None,
                        sesiune_path=os.path.join(_FIX, "fb_sesiune_storage_state.json"))
    cl._inspecteaza(_fix("fb_ssr_search.html"), "https://www.facebook.com/marketplace/")

    assert cl.sesiune_invalida is False


# ── 13-16. jar-ul de cookie-uri ──────────────────────────────────────────────
def test_jar_gol_fara_cale():
    cl = FacebookClient(sleep=lambda _s: None)
    assert cl.c_user is None
    assert dict(cl._sesiune.cookies.get_dict()) == {}


def test_jar_primeste_doar_facebook_neexpirate():
    cl = FacebookClient(sleep=lambda _s: None,
                        sesiune_path=os.path.join(_FIX, "fb_sesiune_storage_state.json"))

    nume = set(cl._sesiune.cookies.get_dict().keys())
    assert {"datr", "sb", "c_user", "xs"} <= nume
    assert "wd" not in nume                # expirat
    assert "_GRECAPTCHA" not in nume       # alt domeniu
    assert cl.c_user == "100000000000001"


def test_sesiune_lipsa_degradeaza_nu_arunca(tmp_path):
    cl = FacebookClient(sleep=lambda _s: None,
                        sesiune_path=str(tmp_path / "nu_exista.json"))
    assert cl.c_user is None
    assert dict(cl._sesiune.cookies.get_dict()) == {}


def test_sesiune_corupta_degradeaza_nu_arunca(tmp_path):
    stricat = tmp_path / "stricat.json"
    stricat.write_text("{ nu e json", encoding="utf-8")

    cl = FacebookClient(sleep=lambda _s: None, sesiune_path=str(stricat))

    assert cl.c_user is None
    assert dict(cl._sesiune.cookies.get_dict()) == {}


def test_storage_state_fara_cheia_cookies_degradeaza(tmp_path):
    fara = tmp_path / "fara.json"
    fara.write_text(json.dumps({"origins": []}), encoding="utf-8")

    assert _injecteaza_sesiune(FacebookClient(sleep=lambda _s: None)._sesiune,
                               str(fara)) is None


# ── 17-19. cache-ul cuplat cu contul ─────────────────────────────────────────
def test_acelasi_cont_distinge_none_de_cont():
    assert acelasi_cont(None, None) is True
    assert acelasi_cont("1", "1") is True
    assert acelasi_cont(None, "1") is False
    assert acelasi_cont("1", None) is False
    assert acelasi_cont("1", "2") is False


def test_cache_cu_alt_c_user_se_ignora():
    """Un `fb_dtsg` de la alt cont produce exact 1357004 — deci cache-ul se arunca."""
    html = _fix("fb_ssr_search.html")
    boot_strain = extrage_bootstrap(html, "search")
    fb_bootstrap._scrie_cache(
        Bootstrap(**{**boot_strain.__dict__, "c_user": "999999999999999"}))

    cl = ClientFals(rute={"marketplace": (html, 200)}, c_user="100000000000001")
    boot = incarca_sau_bootstrapeaza(cl)

    assert boot is not None
    assert boot.c_user == "100000000000001"
    assert cl.cereri, "cache-ul strain trebuia ignorat, deci se re-bootstrapeaza"


def test_cache_al_aceluiasi_cont_se_refoloseste():
    html = _fix("fb_ssr_search.html")
    boot = extrage_bootstrap(html, "search")
    fb_bootstrap._scrie_cache(Bootstrap(**{**boot.__dict__, "c_user": "100000000000001"}))

    cl = ClientFals(rute={"marketplace": (html, 200)}, c_user="100000000000001")
    din_cache = incarca_sau_bootstrapeaza(cl)

    assert din_cache is not None
    assert din_cache.c_user == "100000000000001"
    assert cl.cereri == [], "cache-ul propriu trebuia refolosit, fara cereri"


def test_cache_logat_out_nu_se_refoloseste_logat_in():
    """Bootstrap-ul logat-out n-are `c_user`; refolosit logat-in ar trimite un corp
    fara identitate peste un jar autentificat — chiar cazul masurat la FBS-0."""
    html = _fix("fb_ssr_search.html")
    fb_bootstrap._scrie_cache(extrage_bootstrap(html, "search"))

    cl = ClientFals(rute={"marketplace": (html, 200)}, c_user="100000000000001")
    incarca_sau_bootstrapeaza(cl)

    assert cl.cereri, "cache-ul logat-out nu are voie sa fie refolosit logat-in"


# ── 20-21. bootstrap: fb_dtsg si c_user ──────────────────────────────────────
def test_fb_dtsg_se_extrage_din_pagina():
    boot = extrage_bootstrap(_fix("fb_ssr_search.html"), "search")
    assert boot is not None
    assert boot.fb_dtsg, "pagina contine DTSGInitialData, deci jetonul trebuie extras"
    assert boot.c_user is None, "c_user vine din jar, nu din pagina"


def test_bootstrap_logat_out_ramane_fara_identitate():
    """Chiar daca pagina are `fb_dtsg`, fara `c_user` corpul ramane cel anonim."""
    boot = extrage_bootstrap(_fix("fb_ssr_search.html"), "search")
    assert identitate_din(boot) is None


# ── 22. executorul nu se rupe la o eticheta noua ─────────────────────────────
def test_eticheta_necunoscuta_nu_rupe_sumarul_executorului():
    """E7: `sumar["etichete"]` se incrementeaza cu `.get(..., 0) + 1`. Testul trece
    chiar `sesiune_invalida` prin tiparul folosit de executor."""
    sumar = {"etichete": {"ok": 0, "gol": 0, "blocat": 0, "esec": 0}}
    for eticheta in ("ok", "sesiune_invalida", "sesiune_invalida", "inventata"):
        sumar["etichete"][eticheta] = sumar["etichete"].get(eticheta, 0) + 1

    assert sumar["etichete"]["sesiune_invalida"] == 2
    assert sumar["etichete"]["inventata"] == 1
    assert sumar["etichete"]["ok"] == 1
    assert StareCautare("sesiune_invalida").eticheta == "sesiune_invalida"


# ── 23. 1357004 nu e blocaj ──────────────────────────────────────────────────
def test_identitatea_invalida_nu_e_blocaj():
    """`_pare_blocat` ramane despre refuz de ACCES. 1357004 e identitate gresita,
    si cere alta reactie la FBS-1b decat un 403."""
    cl = ClientFals()
    assert fb_client._pare_blocat(cl, COD_IDENTITATE_INVALIDA) is False
    assert fb_client._pare_blocat(cl, fb_client.COD_REFUZ_ACCES) is True
