"""FBS-4 — atingerea programata a sesiunii.

Playwright NU se ruleaza aici. Interfata cu browserul e izolata in
`navigator_playwright`, iar testele o inlocuiesc cu o functie injectata — de-aia
`atinge(navigator=...)` exista ca parametru.

Ce fixeaza fisierul, dincolo de comportament:
  · o atingere ratata NU are voie sa suprascrie o sesiune buna. E acelasi mod de esec
    cu bug-ul documentat in `facebook_auth.py`, dar mai periculos: ruleaza AUTOMAT.
  · valorile cookie-urilor nu ajung NICIODATA in jurnal. Un `xs` scris intr-un fisier
    de loguri e un jeton de sesiune scurs.
"""
import json
import os
from pathlib import Path

import pytest

from app.services.log_manager import log_manager
from app.scrapers.facebook import atingere as at
from app.scrapers.facebook.executor import zavor_executor

# Valori RECOGNOSCIBILE: daca vreuna apare in jurnal, testul o vede.
_XS_VECHI = "SINTETIC-xs-VECHI-recognoscibil-0001"
_XS_NOU = "SINTETIC-xs-NOU-recognoscibil-0002"
_C_USER = "100000000000001"


def _storage(*, xs=_XS_VECHI, c_user=_C_USER, extra=None, fara=()):
    cookies = [
        {"name": "c_user", "value": c_user, "domain": ".facebook.com", "path": "/",
         "expires": 4102444800},
        {"name": "xs", "value": xs, "domain": ".facebook.com", "path": "/",
         "expires": 4102444800},
        {"name": "datr", "value": "SINTETIC-datr-0001", "domain": ".facebook.com",
         "path": "/", "expires": 4102444800},
    ]
    cookies = [c for c in cookies if c["name"] not in fara]
    if extra:
        cookies.extend(extra)
    return {"cookies": cookies, "origins": []}


@pytest.fixture
def sesiune(tmp_path, monkeypatch):
    cale = tmp_path / "facebook_session_13.json"
    cale.write_text(json.dumps(_storage()), encoding="utf-8")
    monkeypatch.setenv("FB_SESIUNE_PATH", str(cale))
    at._ultima = None
    return cale


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: capturate.append((nivel, mesaj)))
    return capturate


def _nav(rezultat, esec=None):
    def f(cale, *, durata_s=None, **kw):
        f.apelat = True
        return rezultat, esec
    f.apelat = False
    return f


# ── 1-2. fara sesiune, nu se face nimic ──────────────────────────────────────
def test_fara_cale_de_sesiune_nu_lanseaza_nimic(monkeypatch, tmp_path):
    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)
    at._ultima = None
    nav = _nav(_storage())

    r = at.atinge(navigator=nav)

    assert r["reusit"] is False
    assert nav.apelat is False, "browserul nu are voie sa porneasca fara sesiune"


def test_fisier_inexistent_nu_lanseaza_nimic(monkeypatch, tmp_path):
    monkeypatch.setenv("FB_SESIUNE_PATH", str(tmp_path / "nu_exista.json"))
    at._ultima = None
    nav = _nav(_storage())

    r = at.atinge(navigator=nav)

    assert r["reusit"] is False and nav.apelat is False


# ── 3-5. esecuri care NU au voie sa scrie ────────────────────────────────────
def test_aterizare_pe_login_nu_scrie_nimic(sesiune):
    inainte = sesiune.read_bytes()

    r = at.atinge(navigator=_nav(None, "aterizare pe login/checkpoint (.../login)"))

    assert r["reusit"] is False
    assert "login" in r["motiv"]
    assert sesiune.read_bytes() == inainte, "sesiunea buna trebuie sa ramana neatinsa"
    assert not list(sesiune.parent.glob("*.bak-*")), "nici copie nu se face degeaba"


def test_c_user_diferit_abandoneaza(sesiune):
    inainte = sesiune.read_bytes()

    r = at.atinge(navigator=_nav(_storage(c_user="999999999999999")))

    assert r["reusit"] is False
    assert "ALT CONT" in r["motiv"]
    assert sesiune.read_bytes() == inainte


def test_stare_fara_xs_abandoneaza(sesiune):
    inainte = sesiune.read_bytes()

    r = at.atinge(navigator=_nav(_storage(fara=("xs",))))

    assert r["reusit"] is False
    assert "xs" in r["motiv"]
    assert sesiune.read_bytes() == inainte


def test_navigator_care_arunca_nu_propaga_si_nu_scrie(sesiune):
    inainte = sesiune.read_bytes()

    def _crapa(cale, *, durata_s=None, **kw):
        raise RuntimeError("browser picat")

    r = at.atinge(navigator=_crapa)          # nu trebuie sa arunce

    assert r["reusit"] is False and "RuntimeError" in r["motiv"]
    assert sesiune.read_bytes() == inainte


# ── 6-8. scrierea cu plasa ───────────────────────────────────────────────────
def test_stare_valida_se_scrie_cu_copie_de_siguranta(sesiune):
    r = at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    assert r["reusit"] is True
    scris = json.loads(sesiune.read_text(encoding="utf-8"))
    assert any(c["name"] == "xs" and c["value"] == _XS_NOU for c in scris["cookies"])
    copii = list(sesiune.parent.glob(f"{sesiune.name}.bak-*"))
    assert len(copii) == 1, "originalul trebuie pastrat inainte de rescriere"
    vechi = json.loads(copii[0].read_text(encoding="utf-8"))
    assert any(c["value"] == _XS_VECHI for c in vechi["cookies"])


def test_scrierea_e_atomica_si_nu_lasa_original_corupt(sesiune, monkeypatch):
    """`os.replace` esuat inseamna „originalul e intact", nu „fisier pe jumatate"."""
    inainte = sesiune.read_bytes()

    def _replace_stricat(src, dst):
        raise OSError("disc plin")

    monkeypatch.setattr(at.os, "replace", _replace_stricat)

    r = at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    assert r["reusit"] is False
    assert sesiune.read_bytes() == inainte, "originalul trebuie sa ramana valid"
    assert json.loads(sesiune.read_text(encoding="utf-8"))["cookies"]
    assert not list(sesiune.parent.glob("*.tmp")), "temporarul se curata"


def test_se_pastreaza_doar_ultimele_copii(sesiune):
    for i in range(6):
        at.atinge(navigator=_nav(_storage(xs=f"{_XS_NOU}-{i}")))

    copii = list(sesiune.parent.glob(f"{sesiune.name}.bak-*"))
    assert len(copii) <= at._COPII_PASTRATE + 1, f"{len(copii)} copii"


# ── 9-11. comparatia ─────────────────────────────────────────────────────────
def test_comparatia_vede_xs_schimbat():
    d = at.compara(_storage(), _storage(xs=_XS_NOU))

    assert d["xs_schimbat"] is True
    assert d["schimbate"] == ["xs"]
    assert d["ceva_schimbat"] is True


def test_comparatia_vede_xs_neschimbat():
    d = at.compara(_storage(), _storage())

    assert d["xs_schimbat"] is False
    assert d["schimbate"] == []
    assert d["ceva_schimbat"] is False


def test_comparatia_vede_cookie_aparut_si_disparut():
    nou = _storage(fara=("datr",), extra=[
        {"name": "fr", "value": "x", "domain": ".facebook.com", "expires": 1}])

    d = at.compara(_storage(), nou)

    assert d["aparute"] == ["fr"]
    assert d["disparute"] == ["datr"]
    assert d["ceva_schimbat"] is True


def test_comparatia_raporteaza_expirari_noi():
    nou = _storage()
    for c in nou["cookies"]:
        if c["name"] == "xs":
            c["expires"] = 4200000000

    d = at.compara(_storage(), nou)

    assert "xs" in d["expirari_noi"]
    assert d["schimbate"] == [], "doar expirarea s-a schimbat, nu valoarea"
    assert d["ceva_schimbat"] is True


# ── 12. valorile NU ajung in jurnal ──────────────────────────────────────────
def test_valorile_cookieurilor_nu_apar_niciodata_in_jurnal(sesiune, logs):
    at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    tot = " | ".join(m for _n, m in logs)
    assert _XS_VECHI not in tot, "valoarea VECHE a scapat in jurnal"
    assert _XS_NOU not in tot, "valoarea NOUA a scapat in jurnal"
    assert _C_USER not in tot
    # ...dar faptul schimbarii TREBUIE sa fie acolo, altfel runda n-are ce masura
    assert any("FBATINGERE" in m and "xs_schimbat=1" in m for _n, m in logs)


def test_linia_de_jurnal_are_cheile_de_calibrare(sesiune, logs):
    at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    linie = next(m for _n, m in logs if m.startswith("FBATINGERE"))
    for cheie in ("la=", "reusit=", "xs_schimbat=", "datr_schimbat=",
                  "ceva_schimbat=", "schimbate=", "aparute=", "disparute="):
        assert cheie in linie, f"lipseste {cheie!r} din: {linie}"


# ── 13. coordonarea cu executorul ────────────────────────────────────────────
def test_nu_ruleaza_daca_zavorul_e_tinut(sesiune):
    """Doua sesiuni concurente ale aceluiasi cont sunt un declansator de checkpoint
    de sine statator, deci atingerea NU asteapta — sare si reincearca la urmatoarea
    programare."""
    nav = _nav(_storage(xs=_XS_NOU))
    inainte = sesiune.read_bytes()

    with zavor_executor(blocking=False) as obtinut:
        assert obtinut
        r = at.atinge(navigator=nav)

    assert r["reusit"] is False
    assert "executor" in r["motiv"]
    assert nav.apelat is False, "browserul nu porneste cat timp ruleaza un tick"
    assert sesiune.read_bytes() == inainte


def test_zavorul_se_elibereaza_si_atingerea_merge_dupa(sesiune):
    with zavor_executor(blocking=False) as obtinut:
        assert obtinut
    r = at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    assert r["reusit"] is True


# ── 14. vizibilitate ─────────────────────────────────────────────────────────
def test_ultima_atingere_nu_expune_valori(sesiune):
    at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    u = at.ultima_atingere()

    assert u["reusit"] is True
    assert u["schimbari"]["xs_schimbat"] is True
    assert _XS_NOU not in json.dumps(u) and _XS_VECHI not in json.dumps(u)


def test_stare_executor_include_atingerea(sesiune):
    from app.scrapers.facebook.executor import _ultima_atingere
    at.atinge(navigator=_nav(_storage(xs=_XS_NOU)))

    s = _ultima_atingere()

    assert s["reusit"] is True and s["xs_schimbat"] is True
    assert "valoare" not in json.dumps(s).lower()
    assert _XS_NOU not in json.dumps(s)


# ── 15. jobul nu se inregistreaza fara garda ─────────────────────────────────
def test_jobul_e_sub_garda_implicit_oprita():
    sursa = Path("app/main.py").read_text(encoding="utf-8")

    assert 'os.getenv("FB_ATINGERE")' in sursa
    assert 'id="fb_atingere"' in sursa
    # garda are aceeasi forma ca a executorului: doar "1"/"true" o pornesc
    poz = sursa.index('os.getenv("FB_ATINGERE")')
    assert '("1", "true")' in sursa[poz:poz + 200]
    assert "FB_ATINGERE absent" in sursa, "cazul OPRIT trebuie sa fie explicit"
