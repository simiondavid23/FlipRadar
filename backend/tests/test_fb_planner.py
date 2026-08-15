"""FB-3 — planificatorul pe perechi (keyword x ancora): buget, interval, frana.

Totul izolat: planificatorul nu apeleaza nucleul, nu face cereri, nu doarme. Ceasul
e injectat, deci testele sunt deterministe si nu asteapta niciun timp real.

Tabelul `fb_scan_state` e creat de fixture-ul `_schema` din conftest (care importa
app.main -> Base.metadata.create_all), la fel ca `shop_scan_state`.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models.fb_scan_state import FbScanState
from app.services.log_manager import log_manager
from app.scrapers.facebook.anchors import ANCORE, selecteaza
from app.scrapers.facebook.planner import (
    ConfigPlanificator, Planificator, _ca_utc, config_din_env,
)


class Ceas:
    """Ceas controlabil, UTC aware."""

    def __init__(self, start=None):
        self.t = start or datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    def acum(self):
        return self.t

    def avanseaza(self, minute=0):
        self.t += timedelta(minutes=minute)
        return self.t


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def ceas():
    return Ceas()


@pytest.fixture
def warns(monkeypatch):
    mesaje = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: mesaje.append((modul, nivel, mesaj)))
    return mesaje


def _planificator(db, ceas, **kw):
    return Planificator(db, ConfigPlanificator(**kw), acum=ceas.acum)


def _pereche(db, ancora, *, scadenta, modul="radar", keyword_id=1, interval=30):
    r = FbScanState(modul=modul, keyword_id=keyword_id, ancora=ancora,
                    interval_min=interval, next_due_at=scadenta, cicluri_goale=0,
                    stare="activ")
    db.add(r)
    db.commit()
    return r


# ── 14. bugetul e respectat ──────────────────────────────────────────────────
def test_bugetul_limiteaza_numarul_de_perechi_alese(db, ceas):
    trecut = ceas.acum() - timedelta(hours=1)
    for kw in (1, 2):
        for a in ANCORE[:50]:
            _pereche(db, a.slug, scadenta=trecut, keyword_id=kw)
    assert db.query(FbScanState).count() == 100

    p = _planificator(db, ceas, buget_per_tick=12)
    alese = p.alege_scadente()

    assert len(alese) == 12


def test_perechile_nescadente_nu_sunt_alese(db, ceas):
    _pereche(db, "bucuresti", scadenta=ceas.acum() - timedelta(minutes=1))
    _pereche(db, "cluj-napoca", scadenta=ceas.acum() + timedelta(minutes=1))

    alese = _planificator(db, ceas).alege_scadente()

    assert [r.ancora for r in alese] == ["bucuresti"]


# ── 15. ordinea: intarziere descrescator, apoi tier crescator ────────────────
def test_ordinea_dupa_intarziere_descrescator(db, ceas):
    acum = ceas.acum()
    _pereche(db, "cluj-napoca", scadenta=acum - timedelta(minutes=5))
    _pereche(db, "iasi", scadenta=acum - timedelta(minutes=90))
    _pereche(db, "arad", scadenta=acum - timedelta(minutes=30))

    alese = _planificator(db, ceas).alege_scadente()

    assert [r.ancora for r in alese] == ["iasi", "arad", "cluj-napoca"]


def test_la_intarziere_egala_tierul_mic_are_prioritate(db, ceas):
    aceeasi = ceas.acum() - timedelta(minutes=20)
    # inserate in ordine inversa fata de cea asteptata, ca sortarea sa fie dovedita
    _pereche(db, "calafat", scadenta=aceeasi)          # tier 3
    _pereche(db, "targu-mures", scadenta=aceeasi)      # tier 2
    _pereche(db, "bucuresti", scadenta=aceeasi)        # tier 1

    alese = _planificator(db, ceas).alege_scadente()

    assert [r.ancora for r in alese] == ["bucuresti", "targu-mures", "calafat"]


# ── 16. interval adaptiv ─────────────────────────────────────────────────────
@pytest.mark.parametrize("intoarse,noi,interval,asteptat", [
    (10, 8, 60, 30),        # rata 0.8 >= 0.75 -> injumatatire
    (10, 0, 60, 90),        # rata 0.0 <= 0.05 -> x1.5
    (10, 4, 60, 60),        # rata 0.4 -> neschimbat
    (10, 9, 10, 10),        # podeaua: nu coboara sub interval_min_min
    (10, 0, 1440, 1440),    # tavanul: nu urca peste interval_max_min
])
def test_intervalul_se_adapteaza_dupa_rata(db, ceas, intoarse, noi, interval, asteptat):
    r = _pereche(db, "bucuresti", scadenta=ceas.acum(), interval=interval)
    p = _planificator(db, ceas)

    p.inregistreaza_rezultat(r, intoarse, noi)

    assert r.interval_min == asteptat
    assert r.ultima_rata_noi == pytest.approx(noi / max(intoarse, 1))
    # `_ca_utc` nu e cosmetica: dupa commit, SQLite intoarce datetime-urile NAIVE,
    # iar comparatia directa cu ceasul (aware) arunca TypeError. Exact capcana
    # documentata in modelul fb_scan_state.
    assert _ca_utc(r.last_run_at) == ceas.acum()
    assert _ca_utc(r.next_due_at) == ceas.acum() + timedelta(minutes=asteptat)


def test_ciclurile_goale_cresc_si_se_reseteaza(db, ceas):
    r = _pereche(db, "bucuresti", scadenta=ceas.acum(), interval=60)
    p = _planificator(db, ceas)

    p.inregistreaza_rezultat(r, 0, 0)
    assert r.cicluri_goale == 1
    p.inregistreaza_rezultat(r, 0, 0)
    assert r.cicluri_goale == 2

    p.inregistreaza_rezultat(r, 5, 1)
    assert r.cicluri_goale == 0


def test_starea_se_deriva_din_interval_si_cicluri(db, ceas):
    r = _pereche(db, "bucuresti", scadenta=ceas.acum(), interval=60)
    p = _planificator(db, ceas)

    p.inregistreaza_rezultat(r, 10, 8)          # productiv
    assert r.stare == "activ"

    p.inregistreaza_rezultat(r, 0, 0)           # ciclu gol
    assert r.stare == "degradat"

    r.interval_min = 1440
    p.inregistreaza_rezultat(r, 0, 0)           # deja la plafon
    assert r.stare == "retrogradat"


# ── 17. frana adaptiva ───────────────────────────────────────────────────────
def test_frana_injumatateste_bugetul_cu_podea_1(db, ceas):
    p = _planificator(db, ceas, buget_per_tick=12)
    assert p.buget_efectiv() == 12

    assert p.semnal_blocaj() == 6
    assert p.semnal_blocaj() == 3
    assert p.semnal_blocaj() == 1
    assert p.semnal_blocaj() == 1          # podeaua
    assert p.buget_efectiv() == 1


def test_frana_revine_o_treapta_pe_fereastra(db, ceas):
    p = _planificator(db, ceas, buget_per_tick=12, frana_revenire_min=30)
    for _ in range(3):
        p.semnal_blocaj()                  # 12 -> 6 -> 3 -> 1
    assert p.buget_efectiv() == 1

    ceas.avanseaza(minute=29)
    assert p.buget_efectiv() == 1, "sub o fereastra completa nu se revine"

    ceas.avanseaza(minute=1)               # 30 total
    assert p.buget_efectiv() == 2

    ceas.avanseaza(minute=60)              # 90 total -> 3 trepte
    assert p.buget_efectiv() == 4

    ceas.avanseaza(minute=10_000)          # plafonat la bugetul configurat
    assert p.buget_efectiv() == 12


def test_un_blocaj_nou_reporneste_ceasul_de_revenire(db, ceas):
    p = _planificator(db, ceas, buget_per_tick=12, frana_revenire_min=30)
    p.semnal_blocaj()                      # 6
    ceas.avanseaza(minute=60)
    assert p.buget_efectiv() == 8          # 6 + 2 trepte

    p.semnal_blocaj()                      # din 8 -> 4, ceasul repornit
    assert p.buget_efectiv() == 4
    ceas.avanseaza(minute=29)
    assert p.buget_efectiv() == 4


def test_stare_frana_reflecta_contoarele(db, ceas):
    p = _planificator(db, ceas, buget_per_tick=12)
    assert p.stare_frana() == {"buget_configurat": 12, "buget_efectiv": 12,
                               "ultimul_incident_at": None, "incidente_total": 0}

    p.semnal_blocaj()
    p.semnal_blocaj()
    st = p.stare_frana()

    assert st["incidente_total"] == 2
    assert st["buget_efectiv"] == 3
    assert st["ultimul_incident_at"] == ceas.acum()


def test_blocajul_taie_bugetul_dar_nu_atinge_intervalul(db, ceas, warns):
    r = _pereche(db, "bucuresti", scadenta=ceas.acum(), interval=60)
    p = _planificator(db, ceas, buget_per_tick=12)

    p.inregistreaza_rezultat(r, 0, 0, blocaj=True)

    assert r.interval_min == 60, "un blocaj nu spune nimic despre productivitatea ancorei"
    assert p.buget_efectiv() == 6
    assert any("blocaj" in m for _, niv, m in warns if niv == "WARN")


def test_bugetul_redus_limiteaza_selectia(db, ceas):
    trecut = ceas.acum() - timedelta(hours=1)
    for a in ANCORE[:20]:
        _pereche(db, a.slug, scadenta=trecut)
    p = _planificator(db, ceas, buget_per_tick=12)

    assert len(p.alege_scadente()) == 12
    p.semnal_blocaj()
    assert len(p.alege_scadente()) == 6


# ── 18. CONTROL NEGATIV: frana oprita ────────────────────────────────────────
def test_cu_frana_oprita_semnalul_nu_schimba_bugetul(db, ceas):
    """Inversul testului 17: cu `frana_activa=False` bugetul ramane cel configurat,
    oricate semnale ar veni. Daca implementarea ar ignora starea franei (riscul
    'frana decorativa'), testul 17 ar pica, nu acesta."""
    p = _planificator(db, ceas, buget_per_tick=12, frana_activa=False)

    p.semnal_blocaj()
    p.semnal_blocaj()

    assert p.buget_efectiv() == 12
    assert p.stare_frana()["incidente_total"] == 2, "incidentele tot se contorizeaza"


# ── 19. asigura_perechi ──────────────────────────────────────────────────────
def test_asigura_perechi_e_idempotent(db, ceas):
    p = _planificator(db, ceas)

    create1 = p.asigura_perechi("radar", 7, "national")
    total1 = db.query(FbScanState).count()
    create2 = p.asigura_perechi("radar", 7, "national")
    total2 = db.query(FbScanState).count()

    assert create1 == 51 and total1 == 51
    assert create2 == 0 and total2 == 51


def test_asigura_perechi_nu_reseteaza_randurile_existente(db, ceas):
    p = _planificator(db, ceas)
    p.asigura_perechi("radar", 7, "ancore:bucuresti")
    r = db.query(FbScanState).one()
    r.interval_min = 999
    viitor = ceas.acum() + timedelta(hours=5)
    r.next_due_at = viitor
    db.commit()

    p.asigura_perechi("radar", 7, "ancore:bucuresti")

    assert r.interval_min == 999, "invatarea nu se pierde la repornire"


def test_asigura_perechi_respecta_scope_ul(db, ceas):
    p = _planificator(db, ceas)

    p.asigura_perechi("radar", 7, "judet:CJ")

    asteptate = {a.slug for a in selecteaza("judet:CJ")}
    assert {r.ancora for r in db.query(FbScanState)} == asteptate


def test_asigura_perechi_exclude_ancorele_dezactivate(db, ceas):
    p = _planificator(db, ceas, ancore_dezactivate=("bucuresti", "iasi"))

    p.asigura_perechi("radar", 7, "national")

    sluguri = {r.ancora for r in db.query(FbScanState)}
    assert len(sluguri) == 49
    assert "bucuresti" not in sluguri and "iasi" not in sluguri


def test_ancorele_dezactivate_nu_se_planifica_nici_daca_randul_exista(db, ceas):
    """Dezactivarea trebuie sa aiba efect si pe randuri create INAINTE de ea —
    altfel comutatorul de urgenta nu opreste nimic din ce e deja in tabel."""
    trecut = ceas.acum() - timedelta(hours=1)
    _pereche(db, "bucuresti", scadenta=trecut)
    _pereche(db, "cluj-napoca", scadenta=trecut)

    p = _planificator(db, ceas, ancore_dezactivate=("bucuresti",))

    assert [r.ancora for r in p.alege_scadente()] == ["cluj-napoca"]


def test_ancora_disparuta_din_registru_e_ignorata_cu_warn(db, ceas, warns):
    _pereche(db, "oras-desfiintat", scadenta=ceas.acum() - timedelta(hours=1))
    _pereche(db, "bucuresti", scadenta=ceas.acum() - timedelta(hours=1))

    alese = _planificator(db, ceas).alege_scadente()

    assert [r.ancora for r in alese] == ["bucuresti"]
    assert any("oras-desfiintat" in m for _, niv, m in warns if niv == "WARN")


def test_perechile_sunt_separate_pe_modul_si_keyword(db, ceas):
    p = _planificator(db, ceas)

    p.asigura_perechi("radar", 1, "ancore:bucuresti")
    p.asigura_perechi("auto", 1, "ancore:bucuresti")
    p.asigura_perechi("radar", 2, "ancore:bucuresti")

    assert db.query(FbScanState).count() == 3


# ── 20. config_din_env ───────────────────────────────────────────────────────
_FB_VARS = ("FB_BUGET_PER_TICK", "FB_INTERVAL_MIN", "FB_INTERVAL_MAX", "FB_FRANA",
            "FB_FRANA_REVENIRE_MIN", "FB_ANCORE_DEZACTIVATE")


def test_config_din_env_gol_da_defaulturile(monkeypatch):
    for v in _FB_VARS:
        monkeypatch.delenv(v, raising=False)

    c = config_din_env()

    assert c.buget_per_tick == 12
    assert c.interval_min_min == 10
    assert c.interval_max_min == 1440
    assert c.frana_activa is True
    assert c.frana_revenire_min == 30
    assert c.ancore_dezactivate == ()
    assert c.interval_start_tier == {1: 30, 2: 180, 3: 480}


def test_config_din_env_citeste_variabilele(monkeypatch):
    for v in _FB_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FB_BUGET_PER_TICK", "3")
    monkeypatch.setenv("FB_FRANA", "0")
    monkeypatch.setenv("FB_ANCORE_DEZACTIVATE", "iasi, arad ")

    c = config_din_env()

    assert c.buget_per_tick == 3
    assert c.frana_activa is False
    assert c.ancore_dezactivate == ("iasi", "arad")


def test_config_din_env_ignora_valorile_stricate(monkeypatch):
    for v in _FB_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FB_BUGET_PER_TICK", "nu-e-numar")

    assert config_din_env().buget_per_tick == 12


def test_configuratiile_nu_impart_acelasi_dict_de_tier():
    """`interval_start_tier` e mutabil: fara default_factory, doua configuratii ar
    imparti acelasi dict si modificarea uneia ar sari in cealalta."""
    a, b = ConfigPlanificator(), ConfigPlanificator()
    a.interval_start_tier[1] = 999
    assert b.interval_start_tier[1] == 30
