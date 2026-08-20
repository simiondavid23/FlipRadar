"""FB-1 — nucleul Facebook logat-out: bootstrap dinamic, GraphQL, scara de robustete.

Totul OFFLINE, pe fixture-uri derivate din mostrele REALE ale sondelor
(scripts/diagnostics/*/), anonimizate. Clientul e un dublu cu `get`/`post`; nicio
cerere reala nu pleaca din suita asta.

Fixture-urile si mostrele lor sursa:
  fb_ssr_search.html        <- fb_probe_out/cold_search_bucharest.html
  fb_ssr_categorie.html     <- fb_probe_out/categorie_marketplace_category_propertyrentals_.html
  fb_ssr_fara_preloader.html<- aceeasi ca prima, cu dicturile de preloader scoase chirurgical
  fb_graphql_ok.json        <- out_fb0/ok_graphql_count24.json (rularea reala a lui FB-0)
  fb_graphql_eroare.json    <- prefixul real din fb_probe3_out/raport3.json
  fb_graphql_pagina2.json   <- forma reala din fb_probe4_out/raport4.json
  fb_detaliu.html           <- fb_probe_out/detaliu.html
  fb_login_wall.html        <- CONSTRUIT (nicio mostra reala de login-wall pe disc)
"""
import copy
import json
import os

import pytest

from app.services.log_manager import log_manager
from app.scrapers.facebook import bootstrap as fb_bootstrap
from app.scrapers.facebook import client as fb_client
from app.scrapers.facebook.bootstrap import (
    Bootstrap, extrage_bootstrap, incarca_sau_bootstrapeaza, invalideaza,
    obiect_echilibrat, URL_SEARCH, URL_CATEGORIE,
)
from app.scrapers.facebook.client import FacebookClient, search
from app.scrapers.facebook.detail import fetch_detail
from app.scrapers.facebook.graphql import URL_GRAPHQL, extrage_anunturi, muta
from app.scrapers.facebook.parse import canonic, iter_listing_objects

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fix(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


def _fix_json(nume: str):
    return json.loads(_fix(nume))


# ── infrastructura ───────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _izolare(monkeypatch, tmp_path):
    """DATA_DIR spre tmp_path si cache-ul de bootstrap golit INTRE teste.

    `_memo` e global de modul: fara resetare, testul 14 ar trece din greseala
    fiindca un test anterior a lasat un bootstrap in memorie.
    """
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fb_bootstrap._memo = None
    yield
    fb_bootstrap._memo = None


@pytest.fixture(autouse=True)
def warns(monkeypatch):
    mesaje = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: mesaje.append((modul, nivel, mesaj)))
    return mesaje


@pytest.fixture(autouse=True)
def blocari(monkeypatch):
    apeluri = []

    def fals(platform, outcome):
        apeluri.append((platform, outcome))
        return True

    monkeypatch.setattr(fb_client, "report_outcome", fals)
    monkeypatch.setattr(fb_bootstrap, "report_outcome", fals)
    return apeluri


class ClientFals:
    """Dublu de client: rute (fragment de URL -> (corp, status)) si jurnal de cereri."""

    def __init__(self, rute=None, post_rezultate=None):
        self.rute = rute or {}
        self.post_rezultate = list(post_rezultate or [])
        self.cereri = []

    def get(self, url):
        self.cereri.append(("get", url))
        for fragment, rezultat in self.rute.items():
            if fragment in url:
                return rezultat
        return "", 404

    def post(self, url, data=None, headers=None):
        self.cereri.append(("post", url))
        if self.post_rezultate:
            return self.post_rezultate.pop(0)
        return "", 500


def _boot_din_fixture() -> Bootstrap:
    b = extrage_bootstrap(_fix("fb_ssr_search.html"), "search")
    assert b is not None
    return b


def _warn_uri(mesaje):
    return [m for modul, nivel, m in mesaje if nivel == "WARN"]


def _cai_scalare(obj, prefix=""):
    """Toate caile scalare dintr-un dict, in forma punctata."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_cai_scalare(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_cai_scalare(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


# ── 1. bootstrap alege preloaderul corect dintre mai multe ───────────────────
def test_bootstrap_alege_preloaderul_de_cautare_dintre_mai_multe():
    html = _fix("fb_ssr_search.html")
    assert html.count("RelayPreloader") > 1, "fixture-ul trebuie sa aiba mai multe preloadere"

    boot = extrage_bootstrap(html, "search")

    assert boot is not None
    assert "buyLocation" in boot.variables
    assert "query" in boot.variables["params"]["bqf"]
    assert boot.doc_id.isdigit()
    assert boot.lsd
    assert boot.friendly_name == "CometMarketplaceSearchContentContainerQuery"
    assert boot.sursa == "search"
    assert boot.sursa_html_len == len(html)


# ── 2. fara preloader: None, nu exceptie ─────────────────────────────────────
def test_bootstrap_fara_preloader_intoarce_none_nu_arunca():
    html = _fix("fb_ssr_fara_preloader.html")
    assert extrage_bootstrap(html, "search") is None
    # anunturile sunt inca acolo: fixture-ul a pierdut DOAR preloaderul
    assert len(iter_listing_objects(html)) > 0


def test_bootstrap_pe_pagina_de_categorie_reala_nu_da_sablon():
    """Constatare FB-1 contra briefingului: pagina de categorie CHIAR are preloadere
    (36), dar niciunul cu forma de cautare — sunt query-uri de browse
    (MarketplaceRealEstateContentQuery: categoryIDArray/radius, fara params.bqf).
    Deci sursa alternativa exista ca mecanism, dar pe Facebook-ul de azi nu produce
    un sablon utilizabil. Testul inghecata realitatea masurata, ca sa se vada daca
    se schimba."""
    html = _fix("fb_ssr_categorie.html")
    assert html.count("RelayPreloader") > 1
    assert extrage_bootstrap(html, "categorie") is None


# ── 3. obiect_echilibrat: acolade in stringuri si escape-uri ─────────────────
def test_obiect_echilibrat_respecta_stringurile_si_escape_urile():
    # acolada INCHISA singura intr-un string: un numarator naiv taie aici si
    # intoarce JSON invalid
    caz1 = {"a": "acolada inchisa } singura", "c": {"d": 1}}
    text1 = "zgomot inainte " + json.dumps(caz1) + " coada }}}"
    assert json.loads(obiect_echilibrat(text1, 0)) == caz1

    # ghilimea ESCAPATA: fara tratarea escape-ului, stringul pare inchis prea devreme
    caz2 = {"a": 'ghilimea " apoi acolada } aici', "b": 2}
    text2 = "x" + json.dumps(caz2) + "y"
    assert json.loads(obiect_echilibrat(text2, 0)) == caz2

    assert obiect_echilibrat("fara acolade", 0) is None
    assert obiect_echilibrat('{"neinchis": 1', 0) is None


def test_obiect_echilibrat_pe_fixture_ul_real():
    html = _fix("fb_ssr_search.html")
    i = html.find("RelayPreloader")
    vi = html.find('"variables"', i)
    brut = obiect_echilibrat(html, vi)
    assert brut is not None
    date = json.loads(brut)          # trebuie sa fie JSON valid, nu un fragment taiat
    assert isinstance(date, dict)


# ── 4. muta schimba exact ce trebuie, count NEATINS ──────────────────────────
def test_muta_schimba_exact_campurile_cerute_si_nu_atinge_count():
    sablon = _boot_din_fixture().variables
    inainte = _cai_scalare(sablon)

    v = muta(sablon, query="canapea", lat=46.7712, lon=23.6236, raza_km=100)

    assert v is not None
    dupa = _cai_scalare(v)
    schimbate = {c for c in set(inainte) | set(dupa) if inainte.get(c) != dupa.get(c)}
    assert schimbate == {
        "savedSearchQuery",
        "params.bqf.query",
        "buyLocation.latitude",
        "buyLocation.longitude",
        "params.browse_request_params.filter_location_latitude",
        "params.browse_request_params.filter_location_longitude",
        "params.browse_request_params.filter_radius_km",
    }
    # A2: count ramane valoarea din sablon (plafonat server-side la 24 oricum)
    assert v["count"] == sablon["count"]
    assert v["params"]["bqf"]["query"] == "canapea"
    assert v["buyLocation"] == {"latitude": 46.7712, "longitude": 23.6236}
    # sablonul original nu e mutat sub picioarele apelantului
    assert sablon["savedSearchQuery"] != "canapea" or inainte == _cai_scalare(sablon)


# ── 5. CONTROL NEGATIV: muta refuza si logheaza cand lipseste o cale ─────────
def test_muta_refuza_si_logheaza_cand_lipseste_o_cale(warns):
    sablon = copy.deepcopy(_boot_din_fixture().variables)
    del sablon["params"]["bqf"]

    v = muta(sablon, query="canapea", lat=44.43, lon=26.10, raza_km=65)

    assert v is None
    assert any("params.bqf.query" in m for m in _warn_uri(warns)), _warn_uri(warns)


# ── 6. acelasi canonic din SSR si din GraphQL ────────────────────────────────
def test_canonic_identic_din_ssr_si_din_graphql():
    brut = extrage_anunturi(_fix_json("fb_graphql_ok.json"))[0]

    # acelasi obiect BRUT, servit prin calea SSR (bloc <script type=application/json>)
    html = ('<html><script type="application/json">'
            + json.dumps({"require": [["x", "y", [{"result": {"data": brut}}]]]})
            + "</script></html>")
    din_ssr = iter_listing_objects(html)
    assert len(din_ssr) == 1

    assert canonic(din_ssr[0]) == canonic(brut)
    c = canonic(brut)
    assert c["external_id"] and c["source_url"].endswith(f"/{c['external_id']}/")


# ── FBS-12: parserul de NUCLEU eticheteaza moneda reala ──────────────────────────
# Pana la FBS-12, `parse_price` eticheta „RON" orice nu recunostea, iar filtrele
# comparau un anunt in GBP cu praguri RON. Pana aici parserul de nucleu n-avea niciun
# test propriu — era acoperit doar transitiv, prin `canonic`.
@pytest.mark.parametrize("formatted,moneda", [
    ("RON800", "RON"),
    ("€800", "EUR"),
    ("$800", "USD"),
    ("800 USD", "USD"),
    ("USD800", "USD"),        # cod lipit de cifra: `\b` l-ar fi ratat
    ("800 GBP", "GBP"),       # regresia masurata la FBS-11
    ("800 CHF", "CHF"),       # idem
    ("1.500 lei", "RON"),     # singurul cod tradus
    ("Pret: 800 RON", "RON"), # cuvintele din jur nu produc coduri false
    ("800", "RON"),           # nicio informatie de moneda
    ("", "RON"),
])
def test_parse_price_eticheteaza_moneda_reala(formatted, moneda):
    from app.scrapers.facebook.parse import parse_price

    obj = {"listing_price": {"amount": "800", "formatted_amount": formatted}}
    assert parse_price(obj) == (800.0, moneda)


def test_moneda_ajunge_neschimbata_in_dictul_canonic():
    """Contra-proba de capat: eticheta nu se pierde intre parser si `canonic`, care e
    ce vad filtrele si ce se stocheaza pe anunt."""
    brut = {"id": "77", "marketplace_listing_title": "Geaca",
            "listing_price": {"amount": "800", "formatted_amount": "800 GBP"},
            "is_live": True}

    assert canonic(brut)["currency"] == "GBP"


# ── 7. scara de robustete ────────────────────────────────────────────────────
def test_scara_incepe_cu_ssr_pe_id(monkeypatch, warns):
    """FBS-2 a INVERSAT scara: cu `city_page_id`, treapta 1 e SSR, nu GraphQL.
    Testul numara cererile — un verdict corect obtinut pe calea gresita n-ar spune
    nimic. Pragul de varsta se ridica, ca testul sa fie despre SCARA, nu despre
    vechimea fixture-ului."""
    monkeypatch.setenv("FB_VARSTA_MAX_ORE", "1000000")
    cl = ClientFals(rute={"/marketplace/109529709065736/search":
                          (_fix("fb_ssr_search.html"), 200)})

    rez = search("canapea", 46.7712, 23.6236,
                 city_page_id="109529709065736", client=cl)

    assert rez, "treapta 1 (SSR pe ID) trebuia sa intoarca anunturi"
    metode = [m for m, _ in cl.cereri]
    assert metode == ["get"], f"o singura cerere, zero GraphQL: {cl.cereri}"
    assert "sortBy=creation_time_descend" in cl.cereri[0][1]


def test_scara_cade_la_graphql_pe_esec_ambiguu_al_ssr(warns):
    """Caderea ramane pentru esecul AMBIGUU — fara anunturi si fara santinela."""
    cl = ClientFals(
        rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200),
              "/marketplace/109529709065736/search": ("<html></html>", 200)},
        post_rezultate=[(_fix("fb_graphql_ok.json"), 200)],
    )

    rez = search("canapea", 46.7712, 23.6236,
                 city_page_id="109529709065736", client=cl)

    assert rez, "GraphQL de pe treapta 2 trebuia sa salveze cautarea"
    metode = [m for m, _ in cl.cereri]
    assert metode == ["get", "get", "post"], cl.cereri
    assert any("treapta 1->2" in m for m in _warn_uri(warns))


def test_scara_fara_id_incepe_de_la_graphql(warns, blocari):
    """Ancorele fara `city_page_id` (33 din 51) se comporta exact ca inainte de FBS-2."""
    eroare = _fix("fb_graphql_eroare.json")
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(eroare, 200), (eroare, 200)])

    rez = search("canapea", 44.4325, 26.1025, client=cl)

    assert rez == []
    assert ("facebook", fb_client.Outcome.BLOCKED) in blocari
    metode = [m for m, _ in cl.cereri]
    assert metode == ["get", "post", "get", "post"], "nicio cerere SSR fara ID"
    w = _warn_uri(warns)
    assert any("treapta 2->3" in m for m in w), w
    assert any("n-are `city_page_id`" in m for m in w), w


def test_scara_treapta_1_reusita_nu_coboara(warns):
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_ok.json"), 200)])

    rez = search("canapea", 44.4325, 26.1025, client=cl)

    assert len(rez) == 24
    assert [m for m, _ in cl.cereri] == ["get", "post"]
    assert not any("treapta" in m for m in _warn_uri(warns))


def test_pagina2_cu_edges_gol_e_rezultat_valid_nu_esec(warns):
    """`edges: []` inseamna zero rezultate, nu forma stricata: scara NU trebuie sa
    coboare (altfel am reincerca la nesfarsit cautari legitim goale)."""
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(_fix("fb_graphql_pagina2.json"), 200)])

    rez = search("cevacenuexista", 44.4325, 26.1025, client=cl)

    assert rez == []
    assert [m for m, _ in cl.cereri] == ["get", "post"]
    assert not any("treapta" in m for m in _warn_uri(warns))


# ── 8. anunturile inactive sunt excluse ──────────────────────────────────────
@pytest.mark.parametrize("cheie,valoare", [
    ("is_sold", True), ("is_pending", True), ("is_hidden", True), ("is_live", False),
])
def test_canonic_exclude_anunturile_inactive(cheie, valoare):
    brut = copy.deepcopy(extrage_anunturi(_fix_json("fb_graphql_ok.json"))[0])
    assert canonic(brut) is not None          # control pozitiv pe acelasi obiect
    brut[cheie] = valoare
    assert canonic(brut) is None


def test_canonic_fara_id_intoarce_none():
    brut = copy.deepcopy(extrage_anunturi(_fix_json("fb_graphql_ok.json"))[0])
    brut.pop("id")
    assert canonic(brut) is None


# ── 9. listed_at din creation_time, inclusiv imbricat ────────────────────────
def test_listed_at_din_creation_time_inclusiv_imbricat():
    from datetime import datetime, timezone

    plat = {"id": "1", "marketplace_listing_title": "x", "creation_time": 1786636940}
    assert canonic(plat)["listed_at"] == datetime(2026, 8, 13, 16, 2, 20, tzinfo=timezone.utc)

    imbricat = {"id": "2", "marketplace_listing_title": "y",
                "if_gk_just_listed_tag_on_search_feed": {"creation_time": 1786636940}}
    assert canonic(imbricat)["listed_at"] == canonic(plat)["listed_at"]

    fara = {"id": "3", "marketplace_listing_title": "z"}
    assert canonic(fara)["listed_at"] is None

    # valoare absurda: mai bine None decat o data falsa
    absurd = {"id": "4", "marketplace_listing_title": "w", "creation_time": 12}
    assert canonic(absurd)["listed_at"] is None


# ── 10. dedup pe external_id ─────────────────────────────────────────────────
def test_dedup_pe_external_id_in_acelasi_apel():
    raspuns = _fix_json("fb_graphql_ok.json")
    anunturi = extrage_anunturi(raspuns)
    dublat = {"data": {"a": {"edges": [{"node": anunturi[0]}, {"node": anunturi[0]},
                                       {"node": anunturi[1]}]}}}
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                    post_rezultate=[(json.dumps(dublat), 200)])

    rez = search("canapea", 44.4325, 26.1025, client=cl)

    assert len(rez) == 2
    assert len({r["external_id"] for r in rez}) == 2


# ── 11. bootstrap DUAL ───────────────────────────────────────────────────────
def test_bootstrap_dual_cade_pe_sursa_alternativa(warns):
    """Mecanismul de sursa alternativa: cand pagina de search nu da sablon, se
    incearca a doua sursa. Ca sa testam MECANISMUL cu date reale (nu cu o pagina
    Facebook inventata), servim pe URL-ul de categorie un HTML real care CHIAR are
    preloader. Realitatea paginii de categorie de azi e prinsa separat, in
    test_bootstrap_pe_pagina_de_categorie_reala_nu_da_sablon."""
    cl = ClientFals(rute={
        URL_SEARCH: (_fix("fb_ssr_fara_preloader.html"), 200),
        URL_CATEGORIE: (_fix("fb_ssr_search.html"), 200),
    })

    boot = incarca_sau_bootstrapeaza(cl)

    assert boot is not None
    assert boot.sursa == "categorie"
    assert [u for _, u in cl.cereri] == [URL_SEARCH, URL_CATEGORIE]
    assert any("sursa alternativa" in m for m in _warn_uri(warns)), _warn_uri(warns)


# ── 12. A3: ambele surse esueaza -> WARN + BLOCKED ───────────────────────────
def test_bootstrap_esuat_pe_ambele_surse_da_warn_si_blocked(warns, blocari):
    cl = ClientFals(rute={
        URL_SEARCH: (_fix("fb_ssr_fara_preloader.html"), 200),
        URL_CATEGORIE: (_fix("fb_ssr_fara_preloader.html"), 200),
    })

    assert incarca_sau_bootstrapeaza(cl) is None

    assert ("facebook", fb_bootstrap.Outcome.BLOCKED) in blocari
    w = _warn_uri(warns)
    assert any("NICIO sursa" in m for m in w), w
    assert sum(1 for m in w if "fara sablon valid" in m) == 2


# ── 13. fara retry pe 403/429 ────────────────────────────────────────────────
class _SesiuneFalsa:
    def __init__(self, status):
        self.status = status
        self.apeluri = 0

    class _Cookies:
        def clear(self):
            pass

    cookies = _Cookies()

    def get(self, url, **kw):
        self.apeluri += 1
        return type("R", (), {"status_code": self.status, "text": "blocat"})()

    post = get


@pytest.mark.parametrize("status", [403, 429])
def test_fara_retry_pe_403_si_429(monkeypatch, blocari, status):
    cl = FacebookClient(sleep=lambda s: None)
    falsa = _SesiuneFalsa(status)
    cl._sesiune = falsa

    corp, st = cl.get("https://www.facebook.com/x")

    assert st == status
    assert falsa.apeluri == 1, "un blocaj nu se reincearca"
    assert ("facebook", fb_client.Outcome.BLOCKED) in blocari

    # zavorul: cererile urmatoare nu mai ating reteaua deloc
    cl.get("https://www.facebook.com/y")
    cl.post("https://www.facebook.com/z", data={})
    assert falsa.apeluri == 1


def test_search_cu_429_face_o_singura_cerere(monkeypatch, blocari):
    cl = FacebookClient(sleep=lambda s: None)
    falsa = _SesiuneFalsa(429)
    cl._sesiune = falsa

    rez = search("canapea", 44.4325, 26.1025,
                 city_page_id="114304211920174", client=cl)

    assert rez == []
    assert falsa.apeluri == 1, "scara nu are voie sa insiste pe un server care ne limiteaza"
    assert ("facebook", fb_client.Outcome.BLOCKED) in blocari


def test_retry_pe_5xx(monkeypatch, blocari):
    class Sesiune5xx(_SesiuneFalsa):
        def get(self, url, **kw):
            self.apeluri += 1
            cod = 500 if self.apeluri < 3 else 200
            return type("R", (), {"status_code": cod, "text": "ok"})()
        post = get

    cl = FacebookClient(sleep=lambda s: None)
    falsa = Sesiune5xx(500)
    cl._sesiune = falsa

    corp, st = cl.get("https://www.facebook.com/x")

    assert st == 200
    assert falsa.apeluri == 3, "doua retry-uri peste incercarea initiala"
    assert blocari == []


# ── 14. cache-ul de bootstrap ────────────────────────────────────────────────
def test_cache_bootstrap_evita_cererea_si_invalidarea_o_reface(tmp_path):
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)})

    b1 = incarca_sau_bootstrapeaza(cl)
    assert b1 is not None and len(cl.cereri) == 1

    b2 = incarca_sau_bootstrapeaza(cl)
    assert b2 is not None and len(cl.cereri) == 1, "al doilea apel nu trebuie sa ceara"

    # cache-ul e si pe disc, nu doar in memorie: golim memoria, tot nu se cere
    assert (tmp_path / "data" / "fb_bootstrap.json").exists()
    fb_bootstrap._memo = None
    b3 = incarca_sau_bootstrapeaza(cl)
    assert b3 is not None and len(cl.cereri) == 1
    assert b3.doc_id == b1.doc_id

    invalideaza()
    assert not (tmp_path / "data" / "fb_bootstrap.json").exists()
    b4 = incarca_sau_bootstrapeaza(cl)
    assert b4 is not None and len(cl.cereri) == 2, "dupa invalidare se cere din nou"


def test_cache_expirat_se_reface(monkeypatch):
    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)})
    assert incarca_sau_bootstrapeaza(cl) is not None
    assert len(cl.cereri) == 1

    fb_bootstrap._memo = None
    monkeypatch.setenv("FB_BOOTSTRAP_TTL_H", "0")
    assert incarca_sau_bootstrapeaza(cl) is not None
    assert len(cl.cereri) == 2, "un cache expirat nu se foloseste"


def test_cache_corupt_nu_arunca(tmp_path):
    cale = tmp_path / "data" / "fb_bootstrap.json"
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text("{ trunchiat", encoding="utf-8")

    cl = ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)})
    assert incarca_sau_bootstrapeaza(cl) is not None
    assert len(cl.cereri) == 1


# ── SSR si detaliu ───────────────────────────────────────────────────────────
def test_ssr_opreste_pe_login_wall(warns):
    from app.scrapers.facebook.ssr import cauta_ssr
    cl = ClientFals(rute={"/marketplace/": (_fix("fb_login_wall.html"), 200)})

    assert cauta_ssr(cl, "bucharest", "canapea") == []
    assert any("login-wall" in m for m in _warn_uri(warns))


def test_fetch_detail_extrage_descrierea_si_pozele():
    cl = ClientFals(rute={"/marketplace/item/": (_fix("fb_detaliu.html"), 200)})

    rez = fetch_detail("https://www.facebook.com/marketplace/item/123/", client=cl)

    assert rez["description"]
    assert isinstance(rez["images"], list) and rez["images"]


def test_fetch_detail_pe_login_wall_da_none(warns):
    cl = ClientFals(rute={"/marketplace/item/": (_fix("fb_login_wall.html"), 200)})
    assert fetch_detail("https://www.facebook.com/marketplace/item/123/",
                        client=cl) == {"description": None, "images": None}


def test_fetch_detail_nu_arunca_la_eroare():
    class Explodeaza:
        def get(self, url):
            raise RuntimeError("retea")

    assert fetch_detail("https://www.facebook.com/marketplace/item/1/",
                        client=Explodeaza()) == {"description": None, "images": None}
