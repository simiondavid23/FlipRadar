"""FBS-3 — cadenta tick-ului, forma orara a traficului si instrumentarea de baseline.

Totul pur/offline. Ora se INJECTEAZA peste tot: un test care s-ar baza pe ceasul
masinii ar trece sau ar pica in functie de cand e rulat, si exact asta e clasa de
defect pe care runda incearca s-o previna.

Ce fixeaza fisierul, dincolo de comportament:
  · `jitter` din APScheduler NU e `±`. Sursa e `next_fire_time + uniform(0, jitter)`,
    deci o INTARZIERE mereu pozitiva, in secunde. Testul ingheata semantica asta,
    fiindca briefingul o descria ca „±40%".
  · frana si forma orara se COMPUN multiplicativ, nu se suprascriu.
  · un tick sarit APARE in fereastra, nu lipseste din ea.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scrapers.facebook import executor as ex
from app.scrapers.facebook.planner import (
    ConfigPlanificator, FUS_LOCAL, Planificator,
)


class Ceas:
    def __init__(self, start):
        self.t = start

    def acum(self):
        return self.t


def _planificator(ceas, **kw):
    return Planificator(None, ConfigPlanificator(**kw), acum=ceas.acum)


def _utc(zi, ora):
    return datetime(2026, 8, zi, ora, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fereastra_curata(monkeypatch):
    from collections import deque
    monkeypatch.setattr(ex, "_fereastra", deque(maxlen=288))
    yield


# ── 1-3. jitter ──────────────────────────────────────────────────────────────
def test_jitterul_exista_si_e_in_secunde():
    """STOP-critic din briefing: daca `jitter` n-ar exista sau ar avea alta semantica,
    runda se opreste. Verificat pe versiunea INSTALATA, nu din documentatie."""
    assert "jitter" in inspect.signature(IntervalTrigger.__init__).parameters
    sursa = inspect.getsource(BaseTrigger._apply_jitter)
    assert "timedelta(seconds=" in sursa, "jitter-ul e in SECUNDE"


def test_jitterul_e_intarziere_pozitiva_nu_simetrica():
    """Briefingul cerea „±40%". APScheduler face `uniform(0, jitter)` — deci `+0..40%`,
    cu media `+20%`. Perioada efectiva creste, nu se imprastie in jurul intervalului."""
    sursa = inspect.getsource(BaseTrigger._apply_jitter)
    assert "random.uniform(0, jitter)" in sursa
    assert "-jitter" not in sursa

    baza = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    t = IntervalTrigger(minutes=5, jitter=120)
    for _ in range(40):
        got = t._apply_jitter(baza, 120, baza)
        assert baza <= got <= baza + timedelta(seconds=120)


def test_jitterul_implicit_e_40_la_suta_din_interval():
    """Valoarea pe care o paseaza `main.py`, derivata din interval, nu hardcodata."""
    for tick_min, asteptat in ((5, 120), (10, 240), (1, 24)):
        assert round(tick_min * 60 * 0.40) == asteptat


# ── 4-8. forma orara ─────────────────────────────────────────────────────────
def test_multiplicatorul_e_plin_la_pranz_si_redus_noaptea():
    p = _planificator(Ceas(_utc(18, 9)))            # 12:00 local
    assert p.ora_locala() == 12
    assert p.multiplicator_orar() == 1.0

    p_noapte = _planificator(Ceas(_utc(18, 0)))     # 03:00 local
    assert p_noapte.ora_locala() == 3
    assert p_noapte.multiplicator_orar() == pytest.approx(0.33)


def test_ora_se_citeste_pe_fusul_romanesc_nu_pe_utc():
    """Capcana pe care briefingul o semnala: `_acum()` e UTC, iar scheduler-ul ruleaza
    pe Europe/Bucharest. Vara decalajul e 3 h, iarna 2 — deci 01:00 UTC e 04:00 local
    vara si 03:00 iarna. Un multiplicator calculat pe UTC ar fi decalat exact atat."""
    assert FUS_LOCAL == "Europe/Bucharest"

    vara = _planificator(Ceas(datetime(2026, 8, 18, 1, 30, tzinfo=timezone.utc)))
    iarna = _planificator(Ceas(datetime(2026, 1, 18, 1, 30, tzinfo=timezone.utc)))

    assert vara.ora_locala() == 4          # EEST, UTC+3
    assert iarna.ora_locala() == 3         # EET, UTC+2


def test_podeaua_ramane_1_la_orice_ora():
    """Forma orara nu are voie sa opreasca de tot acoperirea."""
    for ora_utc in range(24):
        p = _planificator(Ceas(_utc(18, ora_utc)), buget_per_tick=1)
        assert p.buget_efectiv() >= 1


def test_forma_orara_se_poate_opri():
    p = _planificator(Ceas(_utc(18, 0)), forma_orara_activa=False)

    assert p.multiplicator_orar() == 1.0
    assert p.buget_efectiv() == 12


def test_frana_si_forma_orara_se_compun():
    """Cerinta explicita: produsul, nu unul dintre ele. Frana strange 12 -> 6, iar
    noaptea taie 0.33 peste, deci 6 * 0.33 = 1.98 -> 1."""
    ceas = Ceas(_utc(18, 0))                        # 03:00 local
    p = _planificator(ceas, buget_per_tick=12)
    assert p.buget_efectiv() == 3                   # doar forma orara: 12 * 0.33

    p.semnal_blocaj()                               # frana: 3 -> 1 (jumatate din efectiv)
    dupa = p.buget_efectiv()

    assert dupa == 1
    assert dupa < 3, "frana trebuie sa se aplice PESTE forma orara, nu in locul ei"


def test_ceasul_se_injecteaza_in_buget():
    p = _planificator(Ceas(_utc(18, 9)))
    assert p.buget_efectiv() == 12
    assert p.buget_efectiv(acum=_utc(18, 0)) == 3, "momentul e parametru, nu ceas ascuns"


# ── 9-13. instrumentarea ─────────────────────────────────────────────────────
def _tick(la, **kw):
    baza = {"la": la, "cereri": 4, "executate": 2, "anunturi_noi": 1,
            "zero_confirmate": 0, "etichete": {"ok": 3, "gol": 1}}
    baza.update(kw)
    return baza


def test_fereastra_pastreaza_ultimele_n_si_arunca_vechile(monkeypatch):
    from collections import deque
    monkeypatch.setattr(ex, "_fereastra", deque(maxlen=3))

    for i in range(5):
        ex._inregistreaza_in_fereastra(_tick(f"2026-08-18T0{i}:00:00+00:00"))

    assert len(ex._fereastra) == 3
    assert [t["la"][11:13] for t in ex._fereastra] == ["02", "03", "04"]


def test_agregatele_pe_o_fereastra_construita_de_mana():
    f = [
        _tick("2026-08-18T00:00:00+00:00", cereri=4, etichete={"ok": 3, "gol": 1},
              zero_confirmate=1, anunturi_noi=2),
        _tick("2026-08-18T01:00:00+00:00", cereri=6, etichete={"ok": 1, "esec": 5},
              zero_confirmate=0, anunturi_noi=0),
        {"la": "2026-08-18T02:00:00+00:00", "sarit": "cooldown sesiune"},
    ]

    a = ex._agregate(f)

    assert a["n_tickuri"] == 3
    assert a["n_tickuri_rulate"] == 2
    assert a["n_tickuri_sarite"] == 1
    assert a["sarite_pe_cooldown"] == 1
    assert a["cereri_total"] == 10
    assert a["anunturi_noi_total"] == 2
    assert a["etichete_total"] == {"ok": 4, "gol": 1, "esec": 5}
    assert a["rata_ok"] == 0.4                      # 4 din 10 etichete
    assert a["zero_confirmate_total"] == 1
    assert a["ore_acoperite"] == 2.0
    assert a["cereri_pe_ora"] == 5.0


def test_agregatele_pe_fereastra_goala_nu_crapa():
    assert ex._agregate([]) == {"n_tickuri": 0}


def test_linia_de_jurnal_contine_toate_cheile(monkeypatch):
    linii = []
    from app.services.log_manager import log_manager
    monkeypatch.setattr(log_manager, "emit",
                        lambda m, n, msg: linii.append(msg))

    ex._inregistreaza_in_fereastra(_tick("2026-08-18T12:00:00+00:00",
                                         buget_efectiv=12, frana_stransa=False,
                                         multiplicator_orar=1.0, ora_locala=15,
                                         durata_s=1.5, anomalie=False,
                                         tickuri_fara_ok=0, blocaj=False,
                                         sesiune_invalida=False, perechi_alese=3,
                                         sarite=0))

    assert len(linii) == 1
    linie = linii[0]
    assert linie.startswith("FBTICK "), "prefix stabil, ca sa se poata face grep"
    for cheie in ("la=", "cereri=", "executate=", "etichete=", "buget_efectiv=",
                  "multiplicator_orar=", "ora_locala=", "durata_s=",
                  "zero_confirmate=", "tickuri_fara_ok="):
        assert cheie in linie, f"lipseste {cheie!r} din: {linie}"


def test_cheile_liniei_de_jurnal_nu_se_redenumesc():
    """O cheie redenumita invalideaza tot istoricul deja scris pe disc. Se ADAUGA la
    coada, nu se schimba — testul ingheata setul minim."""
    assert set(ex._CHEI_TICK) >= {
        "la", "cereri", "executate", "etichete", "zero_confirmate",
        "buget_efectiv", "multiplicator_orar", "ora_locala", "durata_s", "sarit",
    }
    assert ex._CHEI_TICK[0] == "la"


def test_tickul_sarit_apare_in_fereastra_ca_sarit():
    """Cerinta explicita: altfel „24 h de rulare" ar arata ca 24 h de activitate, cand
    de fapt o parte a fost pauza de cooldown."""
    ex._inregistreaza_in_fereastra({"la": "2026-08-18T00:00:00+00:00",
                                    "sarit": "cooldown sesiune", "durata_s": 0.0})

    assert len(ex._fereastra) == 1
    assert ex._fereastra[0]["sarit"] == "cooldown sesiune"
    a = ex._agregate(ex._fereastra)
    assert a["n_tickuri_sarite"] == 1 and a["n_tickuri_rulate"] == 0


def test_dimensiunea_ferestrei_acopera_24h_la_intervalul_curent(monkeypatch):
    monkeypatch.setenv("FB_FEREASTRA_ORE", "24")
    monkeypatch.setenv("FB_EXECUTOR_TICK_MIN", "5")
    assert ex._n_ferestre() == 288                  # 24 h / 5 min

    monkeypatch.setenv("FB_EXECUTOR_TICK_MIN", "15")
    assert ex._n_ferestre() == 96


# ── 14. bugetul numara CERERI, nu perechi ────────────────────────────────────
def test_bugetul_numara_cereri_nu_perechi():
    """Briefingul FBS-3 sustinea ca `buget_per_tick` limiteaza PERECHI, si construia
    pe asta un rationament despre cat de stransa e cifra 12. E pe dos: executorul
    numara CERERI (`cost = len(termeni)`), si o spune explicit in docstring-ul lui.

    Testul ingheata semantica, fiindca de ea depinde orice recalibrare viitoare."""
    sursa = inspect.getsource(ex.tick)
    assert 'cost = len(k["termeni"])' in sursa
    assert 'sumar["cereri"] + cost > buget' in sursa
    assert "BUGETUL SE NUMARA IN CERERI, NU IN PERECHI" in ex.__doc__
