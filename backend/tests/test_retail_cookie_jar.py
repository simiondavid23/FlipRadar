"""AMZ-1 C1 — cookie jar si bootstrap de sesiune per domeniu, in poarta retail.

Unele magazine nu servesc nimic unei sesiuni RECI. Masurat pe amazon.de (AMZ-0/0c):
primele 20 de cereri fara cookie-uri au fost blocate 20/20, pe patru rute si cu trei
mecanisme diferite; ruta de bootstrap raspunde insa 200 pe aceeasi sesiune rece si
emite cookie-urile, dupa care 90/90 de cereri OK.

Mecanismul e OPT-IN prin registru. Cel mai important test de aici e primul: cele 88
de magazine FARA `cookie_jar` nu au voie sa vada nicio diferenta.

Fara retea (`curl_requests.get` stubuit) si fara sa atinga directorul real de date:
`_cale_jar` e redirectionat pe `tmp_path`. NICIO VALOARE DE COOKIE reala nu apare in
fisierul asta — cele folosite sunt inventate pentru test.
"""
import json
import time

import pytest

from app.services import scraper_service as ss

DOM_CU_JAR = "cujar.example"
DOM_FARA_JAR = "farajar.example"
URL_UTIL = f"https://{DOM_CU_JAR}/p/1"
URL_BOOTSTRAP = f"https://{DOM_CU_JAR}/bootstrap"
URL_FARA = f"https://{DOM_FARA_JAR}/p/1"

_PAGINA = ('<html><head><title>P</title></head><body>'
           '<div itemscope itemtype="http://schema.org/Product">'
           '<span itemprop="name">P</span><span itemprop="price">10.00</span>'
           '</div></body></html>')
# Marker GENERIC din BLOCK_MARKERS, nu `validatecaptcha`: acela e per-domeniu si
# fara cheia `block_markers` in registru pagina ar trece drept buna (capcana pinuita
# la AMZ-1a de test_01b). Aici ne trebuie un zid pe orice domeniu de test.
_ZID = "<html>captcha-delivery</html>"


class _Resp:
    def __init__(self, status=200, text=_PAGINA, cookies=None, headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self.cookies = dict(cookies or {})


@pytest.fixture
def mediu(monkeypatch, tmp_path):
    """Doua domenii permise (unul cu jar, unul fara), disc redirectionat pe tmp."""
    monkeypatch.setattr(ss, "VALIDATED_DOMAINS",
                        set(ss.VALIDATED_DOMAINS) | {DOM_CU_JAR, DOM_FARA_JAR})
    monkeypatch.setitem(ss._COOKIE_JAR_DOMENIU, DOM_CU_JAR, "proba")
    monkeypatch.setitem(ss._BOOTSTRAP_URL_DOMENIU, DOM_CU_JAR, URL_BOOTSTRAP)
    monkeypatch.setattr(ss, "_cale_jar", lambda nume: tmp_path / f"cookies_{nume}.json")

    # Stare de proces curata intre teste — altfel jar-ul incarcat de un test ar face
    # testul urmator sa creada ca are sesiune.
    monkeypatch.setattr(ss, "_JARURI", {})
    monkeypatch.setattr(ss, "_JARURI_INCARCATE", set())
    monkeypatch.setattr(ss, "_ULTIMUL_BOOTSTRAP", {})
    monkeypatch.setattr(ss, "_ULTIMA_CERERE_PE_DOMENIU", {})

    stare = {"cereri": [], "raspunsuri": [], "warn": []}

    def emit(modul, nivel, mesaj):
        if nivel == "WARN":
            stare["warn"].append(str(mesaj))

    monkeypatch.setattr(ss.log_manager, "emit", emit)
    monkeypatch.setattr(ss.time, "sleep", lambda s: None)

    def fake_get(url, **kw):
        stare["cereri"].append({"url": url, "cookies": kw.get("cookies")})
        i = len(stare["cereri"]) - 1
        lst = stare["raspunsuri"]
        return lst[i] if i < len(lst) else (lst[-1] if lst else _Resp())

    monkeypatch.setattr(ss.curl_requests, "get", fake_get)

    stare["seteaza"] = lambda *r: stare["raspunsuri"].extend(r)
    stare["cale"] = lambda nume="proba": tmp_path / f"cookies_{nume}.json"
    return stare


def _poarta(url=URL_UTIL):
    return ss._fetch_shop_url_guarded(url, headers={}, timeout=5)


# ── 1. domeniile fara jar nu vad nicio diferenta ────────────────────────────────
def test_01_domeniu_fara_jar_nu_primeste_cookies_si_nu_scrie_pe_disc(mediu, tmp_path):
    mediu["seteaza"](_Resp())
    raspuns = _poarta(URL_FARA)

    assert raspuns is not None and raspuns.status_code == 200
    assert len(mediu["cereri"]) == 1
    assert mediu["cereri"][0]["cookies"] in (None, {}), "cookies= nu se trimite"
    assert list(tmp_path.glob("cookies_*.json")) == [], "niciun fisier scris"
    assert mediu["warn"] == []


# ── 2. jar lipsa + bootstrap ────────────────────────────────────────────────────
def test_02_jar_lipsa_face_bootstrap_apoi_cererea_utila(mediu):
    mediu["seteaza"](
        _Resp(cookies={"session-id": "s1"}),   # bootstrap
        _Resp(),                               # cererea utila
    )
    raspuns = _poarta()

    assert raspuns is not None
    assert len(mediu["cereri"]) == 2
    assert mediu["cereri"][0]["url"] == URL_BOOTSTRAP
    assert mediu["cereri"][1]["url"] == URL_UTIL
    assert mediu["cereri"][1]["cookies"] == {"session-id": "s1"}, \
        "cererea utila pleaca cu cookie-urile emise de bootstrap"


# ── 3. jar existent pe disc -> niciun bootstrap ─────────────────────────────────
def test_03_jar_existent_nu_declanseaza_bootstrap(mediu):
    mediu["cale"]().write_text(json.dumps({"session-id": "de-pe-disc"}),
                               encoding="utf-8")
    mediu["seteaza"](_Resp())
    raspuns = _poarta()

    assert raspuns is not None
    assert len(mediu["cereri"]) == 1, "fara bootstrap"
    assert mediu["cereri"][0]["cookies"] == {"session-id": "de-pe-disc"}
    assert mediu["warn"] == []


# ── 4 / 5. persistarea ──────────────────────────────────────────────────────────
def test_04_cookie_nou_ajunge_pe_disc(mediu):
    mediu["cale"]().write_text(json.dumps({"session-id": "s1"}), encoding="utf-8")
    mediu["seteaza"](_Resp(cookies={"session-token": "t1"}))
    _poarta()

    pe_disc = json.loads(mediu["cale"]().read_text(encoding="utf-8"))
    assert pe_disc == {"session-id": "s1", "session-token": "t1"}


def test_05_fara_cookie_nou_fisierul_NU_e_rescris(mediu):
    cale = mediu["cale"]()
    cale.write_text(json.dumps({"session-id": "s1"}), encoding="utf-8")
    mtime0 = cale.stat().st_mtime_ns

    # Acelasi cookie, cu aceeasi valoare: nimic de schimbat.
    mediu["seteaza"](_Resp(cookies={"session-id": "s1"}))
    _poarta()

    assert cale.stat().st_mtime_ns == mtime0, \
        "un jar neschimbat nu se rescrie — altfel fiecare produs urmarit ar da un write"


# ── 6 / 7 / 8. recuperarea dupa blocaj ──────────────────────────────────────────
def test_06_blocat_apoi_bootstrap_apoi_reusita(mediu):
    mediu["cale"]().write_text(json.dumps({"session-id": "vechi"}), encoding="utf-8")
    mediu["seteaza"](
        _Resp(text=_ZID),                       # cererea utila -> zid
        _Resp(cookies={"session-id": "nou"}),   # bootstrap
        _Resp(),                                # cererea utila, repetata
    )
    raspuns = _poarta()

    assert raspuns is not None and raspuns.status_code == 200
    assert len(mediu["cereri"]) == 3
    assert [c["url"] for c in mediu["cereri"]] == [URL_UTIL, URL_BOOTSTRAP, URL_UTIL]
    assert mediu["cereri"][2]["cookies"] == {"session-id": "nou"}


def test_07_blocat_dupa_bootstrap_ramane_None_cu_UN_singur_bootstrap(mediu):
    mediu["cale"]().write_text(json.dumps({"session-id": "vechi"}), encoding="utf-8")
    mediu["seteaza"](_Resp(text=_ZID))          # tot ce urmeaza e zid

    raspuns = _poarta()

    assert raspuns is None
    bootstrapuri = [c for c in mediu["cereri"] if c["url"] == URL_BOOTSTRAP]
    assert len(bootstrapuri) == 1, "exact UN bootstrap, fara bucla"
    assert len(mediu["cereri"]) == 3, "utila, bootstrap, utila — si gata"


def test_08_al_doilea_blocaj_in_racire_nu_mai_face_bootstrap(mediu):
    mediu["cale"]().write_text(json.dumps({"session-id": "vechi"}), encoding="utf-8")
    mediu["seteaza"](_Resp(text=_ZID))

    assert _poarta() is None
    dupa_primul = len(mediu["cereri"])

    assert _poarta() is None
    cereri_noi = mediu["cereri"][dupa_primul:]

    assert [c["url"] for c in cereri_noi] == [URL_UTIL], \
        "in racire: doar cererea utila, niciun bootstrap nou"


def test_08b_dupa_racire_bootstrapul_e_permis_din_nou(mediu, monkeypatch):
    mediu["cale"]().write_text(json.dumps({"session-id": "vechi"}), encoding="utf-8")
    mediu["seteaza"](_Resp(text=_ZID))
    assert _poarta() is None

    # Ceasul MONOTON sare peste fereastra de racire.
    real = time.monotonic
    monkeypatch.setattr(ss.time, "monotonic",
                        lambda: real() + ss._RACIRE_BOOTSTRAP_S + 1)
    dupa_primul = len(mediu["cereri"])
    assert _poarta() is None

    urls = [c["url"] for c in mediu["cereri"][dupa_primul:]]
    assert URL_BOOTSTRAP in urls, "peste fereastra, bootstrap-ul redevine permis"


# ── 9. jar fara bootstrap ───────────────────────────────────────────────────────
def test_09_jar_fara_bootstrap_url_pleaca_fara_cookies(mediu, monkeypatch):
    monkeypatch.delitem(ss._BOOTSTRAP_URL_DOMENIU, DOM_CU_JAR)
    mediu["seteaza"](_Resp())

    raspuns = _poarta()

    assert raspuns is not None
    assert len(mediu["cereri"]) == 1, "fara bootstrap, fara eroare"
    assert mediu["cereri"][0]["cookies"] in (None, {})


# ── 10. jurnalul nu scapa valori ────────────────────────────────────────────────
def test_10_warnurile_nu_contin_valori_de_cookie(mediu):
    mediu["seteaza"](
        _Resp(cookies={"session-id": "VALOARE-SECRETA-123"}),
        _Resp(),
    )
    _poarta()

    assert mediu["warn"], "bootstrap-ul emite un WARN"
    intreg = " ".join(mediu["warn"])
    assert DOM_CU_JAR in intreg
    assert "motiv=lipsa" in intreg
    assert "VALOARE-SECRETA-123" not in intreg
    assert "session-id" not in intreg


# ── 11. calea reala a jar-ului e gitignorata ────────────────────────────────────
def test_11_calea_reala_a_jarului_e_gitignorata():
    """Jar-ul poarta cookie-uri de sesiune: daca ar scapa in git, ar scapa definitiv.

    Testul ruleaza `git check-ignore` pe calea REALA (nu pe tmp_path), fiindca doar
    aia ajunge pe disc in productie.
    """
    import subprocess
    from pathlib import Path

    # Import local, ca in `_cale_jar`: DATA_DIR se rezolva la apel.
    from app.config import DATA_DIR

    cale = Path(DATA_DIR) / "data" / "cookies_amazon_de.json"
    repo = Path(__file__).resolve().parents[2]
    try:
        rel = cale.resolve().relative_to(repo)
    except ValueError:
        pytest.skip("DATA_DIR e in afara repo-ului — nimic de ignorat in git")

    p = subprocess.run(["git", "check-ignore", "-v", str(rel).replace("\\", "/")],
                       cwd=str(repo), capture_output=True, text=True)
    assert p.returncode == 0, (
        f"calea jar-ului NU e gitignorata: {rel}\n{p.stdout}{p.stderr}")


# ── 13. sesiunea NU se scurge catre alt domeniu la redirect ────────────────────
def test_13_redirect_catre_alt_domeniu_pleaca_fara_cookies(mediu):
    """Un redirect intre magazine e legitim, dar sesiunea unuia n-are ce cauta la
    celalalt: ar fi o scurgere de date de sesiune catre un tert.

    Simetric cu `_impersonate_for`, care se rezolva tot per hop. Verificam AMBELE
    sensuri: nu trimitem cookie-urile noastre, si nu adoptam cookie-urile lui.
    """
    mediu["cale"]().write_text(json.dumps({"session-id": "al-nostru"}),
                               encoding="utf-8")
    mediu["seteaza"](
        _Resp(status=302, headers={"location": URL_FARA}),
        _Resp(cookies={"cookie-strain": "nu-ne-apartine"}),
    )
    raspuns = _poarta()

    assert raspuns is not None and raspuns.status_code == 200
    assert len(mediu["cereri"]) == 2
    assert mediu["cereri"][0]["cookies"] == {"session-id": "al-nostru"}
    assert mediu["cereri"][1]["cookies"] in (None, {}), \
        "hop-ul catre alt domeniu NU primeste sesiunea noastra"

    pe_disc = json.loads(mediu["cale"]().read_text(encoding="utf-8"))
    assert pe_disc == {"session-id": "al-nostru"}, \
        "cookie-urile domeniului strain NU intra in jar-ul nostru"


# ── 14. 429 nu e motiv de bootstrap ─────────────────────────────────────────────
def test_14_rate_limited_nu_declanseaza_bootstrap_si_nu_goleste_jarul(mediu):
    """`RATE_LIMITED` inseamna „prea multe cereri". Raspunsul corect e mai PUTIN
    trafic — nu inca doua cereri si o sesiune aruncata. Sesiunea nu e vinovata."""
    mediu["cale"]().write_text(json.dumps({"session-id": "s1"}), encoding="utf-8")
    mediu["seteaza"](_Resp(status=429, text="<html>prea des</html>"))

    raspuns = _poarta()

    assert raspuns is None
    assert len(mediu["cereri"]) == 1, "nicio cerere in plus"
    assert [c["url"] for c in mediu["cereri"]] == [URL_UTIL], "niciun bootstrap"
    assert json.loads(mediu["cale"]().read_text(encoding="utf-8")) == \
        {"session-id": "s1"}, "jar-ul NU e golit"


# ── 15. intervalul se respecta si intre bootstrap si cererea utila ─────────────
def test_15_cererea_utila_de_dupa_bootstrap_asteapta_intervalul(mediu, monkeypatch):
    """Bootstrap-ul consuma el insusi o cerere catre domeniu, iar cererea utila vine
    imediat dupa. Fara asteptare, cele doua pleaca spate-in-spate si incalca exact
    `min_fetch_interval_s` al domeniului (pe amazon.de, 10s)."""
    apeluri = []
    real = ss._asteapta_intervalul
    monkeypatch.setattr(ss, "_asteapta_intervalul",
                        lambda u: (apeluri.append(u), real(u))[1])
    monkeypatch.setitem(ss._MIN_FETCH_INTERVALE, DOM_CU_JAR, 10)

    mediu["seteaza"](
        _Resp(cookies={"session-id": "s1"}),   # bootstrap
        _Resp(),                               # cererea utila
    )
    assert _poarta() is not None

    assert apeluri == [URL_UTIL, URL_BOOTSTRAP, URL_UTIL], (
        "trei asteptari: intrarea in poarta, bootstrap-ul (apel recursiv) si "
        "cererea utila de dupa bootstrap")


# ── garda: harta de jar-uri se citeste din registru, nu din cod ─────────────────
def test_12_hartile_vin_din_registru():
    from app.services.shop_registry import option_map

    assert ss._COOKIE_JAR_DOMENIU == option_map("cookie_jar")
    assert ss._BOOTSTRAP_URL_DOMENIU == option_map("bootstrap_url")
