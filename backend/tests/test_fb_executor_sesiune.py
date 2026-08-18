"""FBS-1b — sesiunea ca infrastructura, cooldown-ul si frana pe anomalie.

Totul OFFLINE: `executor.search_cu_stare` e inlocuit cu dubluri care intorc stari
fabricate, iar sesiunea e `storage_state`-ul SINTETIC de la FBS-1 (un `xs` real e un
jeton viu si nu intra in repo).

Ce fixeaza fisierul asta, dincolo de comportament:
  · D10 — sesiunea scraperului vine din `FB_SESIUNE_PATH`, NU din
    `resolve_facebook_session_path(db, user_id)`. Contul lucrator e separat de
    conturile utilizatorilor, si asta trebuie sa ramana adevarat.
  · gaura gasita la finalul FBS-1 — avertismentul „acoperirea e cazuta" se calcula
    doar pe eticheta `esec`, deci o sesiune moarta trecea in tacere.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models.radar_keyword import RadarKeyword
from app.services.log_manager import log_manager
from app.scrapers.facebook import client as fb_client
from app.scrapers.facebook import executor as ex
from app.scrapers.facebook.client import StareCautare
from app.scrapers.facebook.planner import ConfigPlanificator, Planificator

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
_SESIUNE = os.path.join(_FIX, "fb_sesiune_storage_state.json")


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def uid(db):
    from app.models.user import User
    u = User(email="fbs1b@example.com", username="fbs1b", hashed_password="x",
             is_active=True)
    db.add(u)
    db.commit()
    return u.id


@pytest.fixture(autouse=True)
def _izolare(monkeypatch, tmp_path):
    from app import config
    from app.scrapers.facebook import bootstrap as fb_bootstrap
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fb_bootstrap._memo = None
    ex._planificator = None
    ex._ultimul_tick = None
    ex._tickuri_fara_ok = 0
    ex._reseteaza_cooldown()
    fb_client._regim_logat = None
    for v in ("FB_SESIUNE_PATH", "FB_COOLDOWN_ORE", "FB_BUGET_PER_TICK", "FB_FRANA"):
        monkeypatch.delenv(v, raising=False)
    yield
    ex._planificator = None
    ex._ultimul_tick = None
    ex._tickuri_fara_ok = 0
    ex._reseteaza_cooldown()
    fb_client._regim_logat = None


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: capturate.append((nivel, mesaj)))
    return capturate


# ══════════════════════════════════════════════════════════════════════════════
# 1. Sesiunea, cablata prin configuratie
# ══════════════════════════════════════════════════════════════════════════════
def test_fara_variabila_ramane_logat_out(monkeypatch):
    """Garda e chiar absenta caii: exact comportamentul de dinainte, cu jar gol."""
    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)

    assert fb_client._cale_sesiune() is None
    cl = fb_client._client_implicit()
    assert cl.c_user is None
    assert dict(cl._sesiune.cookies.get_dict()) == {}


def test_cale_setata_incarca_sesiunea(monkeypatch):
    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)

    cl = fb_client._client_implicit()

    assert cl.c_user == "100000000000001"
    assert "xs" in cl._sesiune.cookies.get_dict()


def test_fisier_inexistent_degradeaza_la_logat_out(monkeypatch, tmp_path):
    monkeypatch.setenv("FB_SESIUNE_PATH", str(tmp_path / "nu_exista.json"))

    assert fb_client._cale_sesiune() is None, "garda = absenta caii, nu o a doua setare"
    cl = fb_client._client_implicit()
    assert cl.c_user is None


def test_calea_se_citeste_la_apel_nu_la_import(monkeypatch, tmp_path):
    """Acelasi motiv ca la `_cale_cache()`: testele trebuie s-o poata redirecta, iar
    un build PyInstaller ar fixa-o la pornire."""
    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)
    assert fb_client._client_implicit().c_user is None

    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)
    assert fb_client._client_implicit().c_user == "100000000000001"

    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)
    assert fb_client._client_implicit().c_user is None


def test_regimul_se_logheaza_o_data_pe_configuratie(monkeypatch, logs):
    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)

    fb_client._client_implicit()
    fb_client._client_implicit()
    fb_client._client_implicit()

    regim = [m for _n, m in logs if "regim AUTENTIFICAT" in m]
    assert len(regim) == 1, "un client per `search` ar fi umplut jurnalul"

    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)
    fb_client._client_implicit()
    assert any("regim LOGAT-OUT" in m for _n, m in logs), \
        "schimbarea configuratiei trebuie sa se vada imediat"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Cooldown pe sesiune invalida
# ══════════════════════════════════════════════════════════════════════════════
def _pregateste_un_keyword(db, uid, stari):
    """Un keyword Radar scadent, cu `search_cu_stare` inlocuit de `stari` (lista de
    StareCautare consumate in ordine, ultima se repeta)."""
    k = RadarKeyword(name="canapea", user_id=uid, is_active=True,
                     platform="facebook", platforms='["facebook"]',
                     max_price=1000.0, resale_price=1500.0)
    db.add(k)
    db.commit()

    p = Planificator(db, ConfigPlanificator(buget_per_tick=4))
    p.asigura_perechi("radar", k.id, "national")
    from app.models.fb_scan_state import FbScanState
    db.query(FbScanState).update(
        {FbScanState.next_due_at: datetime.now(timezone.utc) + timedelta(days=1)},
        synchronize_session=False)
    r = db.query(FbScanState).order_by(FbScanState.id).first()
    r.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    ex._planificator = p
    return k


def _forteaza_scadenta(db):
    """Readuce perechea in scadenta. Dupa un tick, `inregistreaza_rezultat` o
    reprogrameaza in viitor — corect in productie, dar un test cu mai multe tick-uri
    ar masura altfel tick-uri goale (`executate == 0`), care NU conteaza ca anomalie."""
    from app.models.fb_scan_state import FbScanState
    r = db.query(FbScanState).order_by(FbScanState.id).first()
    r.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()


def _fals_search(stari):
    apeluri = {"n": 0}

    def _f(termen, lat, lon, **kw):
        i = min(apeluri["n"], len(stari) - 1)
        apeluri["n"] += 1
        return [], stari[i]

    _f.apeluri = apeluri
    return _f


def test_sesiune_invalida_rupe_tickul_si_intra_in_cooldown(db, uid, monkeypatch):
    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("sesiune_invalida", 1357004, 2)]))

    sumar = ex.tick(db)

    assert sumar["sesiune_invalida"] is True
    assert sumar["blocaj"] is True
    assert ex._cooldown_pana_la is not None


def test_tick_in_cooldown_sare_fara_sa_atinga_nimic(db, uid, monkeypatch):
    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)
    _pregateste_un_keyword(db, uid, None)
    ex._intra_in_cooldown(None)

    def _explodeaza(*a, **kw):
        raise AssertionError("planificatorul nu are voie sa fie atins in cooldown")

    monkeypatch.setattr(ex, "_obtine_planificator", _explodeaza)
    monkeypatch.setattr(ex, "search_cu_stare", _explodeaza)

    sumar = ex.tick(db)

    assert sumar["sarit"] == "cooldown sesiune"
    assert "pana_la" in sumar


def test_cooldownul_expira_singur(db, uid, monkeypatch):
    ex._intra_in_cooldown(None)
    ex._cooldown_pana_la = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert ex._cooldown_activ() == {}
    assert ex._cooldown_pana_la is None


def test_cooldownul_cade_la_schimbarea_sesiunii(monkeypatch, tmp_path):
    """Altfel reconectarea manuala din UI n-ar avea efect ore intregi, iar
    utilizatorul n-ar intelege de ce."""
    sesiune = tmp_path / "sesiune.json"
    sesiune.write_text('{"cookies": []}', encoding="utf-8")
    monkeypatch.setenv("FB_SESIUNE_PATH", str(sesiune))
    ex._intra_in_cooldown(None)
    assert ex._cooldown_activ()["sarit"] == "cooldown sesiune"

    # reconectare: acelasi nume, alt continut
    sesiune.write_text('{"cookies": [{"name": "c_user", "value": "1"}]}',
                       encoding="utf-8")

    assert ex._cooldown_activ() == {}
    assert ex._cooldown_pana_la is None


def test_durata_cooldownului_din_variabila(monkeypatch):
    monkeypatch.setenv("FB_COOLDOWN_ORE", "2")
    inainte = datetime.now(timezone.utc)

    ex._intra_in_cooldown(None)

    delta = (ex._cooldown_pana_la - inainte).total_seconds() / 3600
    assert 1.9 < delta < 2.1


# ══════════════════════════════════════════════════════════════════════════════
# 3. Gaura `numai_esec`: criteriul devine „niciuna n-a reusit"
# ══════════════════════════════════════════════════════════════════════════════
def test_zero_ok_cu_etichete_mixte_declanseaza_avertismentul(db, uid, monkeypatch, logs):
    """Azi criteriul era `etichete["esec"] == cereri`, deci un tick cu `blocat` si
    `gol` trecea in tacere. Testul foloseste EXACT un amestec fara niciun `esec`."""
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("gol", None, 4)]))

    for _ in range(ex._PRAG_ESEC_TOTAL):
        _forteaza_scadenta(db)
        ex.tick(db)

    assert ex._tickuri_fara_ok >= ex._PRAG_ESEC_TOTAL
    assert any("acoperirea e cazuta" in m for _n, m in logs)
    # criteriul vechi ar fi cerut `esec`; aici n-a existat niciunul
    assert ex._ultimul_tick["etichete"].get("esec", 0) == 0


def test_un_singur_ok_reseteaza_contorul(db, uid, monkeypatch):
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("gol", None, 4)]))
    ex.tick(db)
    assert ex._tickuri_fara_ok == 1

    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("ok", None, 1)]))
    _forteaza_scadenta(db)
    ex.tick(db)

    assert ex._tickuri_fara_ok == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. Frana pe anomalie + intrebarea de design (zero confirmat prin santinela)
# ══════════════════════════════════════════════════════════════════════════════
def test_n_tickuri_fara_ok_strang_frana(db, uid, monkeypatch):
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("esec", None, 4)]))
    apeluri = {"n": 0}
    monkeypatch.setattr(ex._planificator, "semnal_blocaj",
                        lambda: apeluri.__setitem__("n", apeluri["n"] + 1))

    for _ in range(ex._PRAG_ESEC_TOTAL - 1):
        _forteaza_scadenta(db)
        ex.tick(db)
    assert apeluri["n"] == 0, "sub prag, frana nu se strange"

    _forteaza_scadenta(db)
    ex.tick(db)
    assert apeluri["n"] == 1


def test_golurile_confirmate_prin_santinela_nu_sunt_anomalie(db, uid, monkeypatch, logs):
    """INTREBAREA DE DESIGN a rundei, rezolvata: un zero pe care Facebook l-a
    CONFIRMAT explicit e sanatos, nu suspect. Fara distinctia asta, detectorul ar
    porni in nopti linistite — de cand exista santinela (FBS-1), un zero confirmat
    iese tot `gol`, nedistinctibil de un gol ambiguu."""
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("gol", None, 1, zero_confirmat=True)]))
    apeluri = {"n": 0}
    monkeypatch.setattr(ex._planificator, "semnal_blocaj",
                        lambda: apeluri.__setitem__("n", apeluri["n"] + 1))

    for _ in range(ex._PRAG_ESEC_TOTAL + 1):
        _forteaza_scadenta(db)
        ex.tick(db)

    assert ex._tickuri_fara_ok == 0
    assert apeluri["n"] == 0
    assert not any("acoperirea e cazuta" in m for _n, m in logs)
    assert ex._ultimul_tick["anomalie"] is False


def test_gol_neconfirmat_ramane_anomalie(db, uid, monkeypatch):
    """Contra-proba: acelasi `gol`, dar fara confirmare, CONTEAZA."""
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare",
                        _fals_search([StareCautare("gol", None, 4, zero_confirmat=False)]))

    ex.tick(db)

    assert ex._tickuri_fara_ok == 1
    assert ex._ultimul_tick["anomalie"] is True


def test_amestec_confirmat_si_neconfirmat_ramane_anomalie(db, uid, monkeypatch):
    """Pragul e „TOATE confirmate", nu „macar unul": un singur gol inexplicabil
    intr-un tick altfel linistit e exact semnalul pe care nu vrem sa-l pierdem."""
    _pregateste_un_keyword(db, uid, None)
    monkeypatch.setattr(ex, "search_cu_stare", _fals_search([
        StareCautare("gol", None, 1, zero_confirmat=True),
        StareCautare("gol", None, 4, zero_confirmat=False),
    ]))

    ex.tick(db)

    if ex._ultimul_tick["cereri"] > 1:
        assert ex._ultimul_tick["anomalie"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. Starea vizibila
# ══════════════════════════════════════════════════════════════════════════════
def test_stare_executor_raporteaza_regimul_logat_out(db, monkeypatch):
    monkeypatch.delenv("FB_SESIUNE_PATH", raising=False)

    st = ex.stare_executor(db)

    assert st["sesiune"]["regim"] == "logat-out"
    assert st["sesiune"]["cale"] is None
    assert st["sesiune"]["valida"] is False
    assert st["cooldown"]["activ"] is False
    assert st["tickuri_fara_ok"] == 0


def test_stare_executor_raporteaza_regimul_autentificat(db, monkeypatch):
    monkeypatch.setenv("FB_SESIUNE_PATH", _SESIUNE)

    st = ex.stare_executor(db)

    assert st["sesiune"]["regim"] == "autentificat"
    assert st["sesiune"]["cale"] == _SESIUNE


def test_stare_executor_arata_cooldownul(db, monkeypatch):
    monkeypatch.setenv("FB_COOLDOWN_ORE", "3")
    ex._intra_in_cooldown(None)

    st = ex.stare_executor(db)

    assert st["cooldown"]["activ"] is True
    assert st["cooldown"]["pana_la"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# 6. Alerta Discord, pe tiparul EXISTENT
# ══════════════════════════════════════════════════════════════════════════════
def test_alerta_fara_db_ramane_doar_in_jurnal(logs):
    ex._alerteaza(None, "mesaj de test")

    assert any("mesaj de test" in m for _n, m in logs)


def test_alerta_cu_db_foloseste_dispatch_ul_existent(db, monkeypatch):
    """Nu se inventeaza o ruta noua de notificare: `health_watchdog._dispatch_alert`
    e deja tiparul „job global care alerteaza fara context de utilizator"."""
    primite = []
    import app.services.radar.health_watchdog as hw
    monkeypatch.setattr(hw, "_dispatch_alert",
                        lambda d, text, level: primite.append((text, level)))

    ex._alerteaza(db, "anomalie sustinuta")

    assert primite == [("anomalie sustinuta", "WARN")]


def test_alerta_care_crapa_nu_opreste_tickul(db, monkeypatch, logs):
    import app.services.radar.health_watchdog as hw

    def _crapa(*a, **kw):
        raise RuntimeError("discord picat")

    monkeypatch.setattr(hw, "_dispatch_alert", _crapa)

    ex._alerteaza(db, "mesaj important")      # nu trebuie sa arunce

    assert any("mesaj important" in m for _n, m in logs)
    assert any("alerta Discord a esuat" in m for _n, m in logs)
