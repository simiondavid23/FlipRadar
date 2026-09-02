"""NET-5.3 — politica de declansare a rotatiei + resetarea starii de reputatie.

Rotator FALSIFICAT: zero atingere de modem, zero retea. Nicio functie `time.sleep` sub
`patch("time.sleep")` global — se inlocuieste doar atributul, in teste single-threaded.
"""
import pytest

from app.services.network import triggers
from app.services.network.rotator import RotationResult
from app.services.radar import health_watchdog as hw
from app.services.radar import vinted_html as vh
from app.services.radar.base_scraper import Outcome


class _FakeRotator:
    def __init__(self, ok=True, changed=True, boom=False, skipped="auto"):
        self.ok, self.changed, self.boom = ok, changed, boom
        # „auto": esecul implicit e un REFUZ (cooldown). `skipped=None` cu `ok=False`
        # inseamna rotatie chiar incercata si esuata — alt caz, vezi tabelul din 5.3a.
        if skipped == "auto":
            skipped = None if ok else "cooldown activ, mai sunt 480s"
        self.skipped = skipped
        self.rotations = 0
        self.available_calls = 0

    def rotate(self, force=False):
        self.rotations += 1
        if self.boom:
            raise RuntimeError("modem plecat")
        return RotationResult(ok=self.ok, changed=self.changed,
                              skipped_reason=self.skipped)

    def available(self):
        self.available_calls += 1
        return True


def _clear_vinted_state():
    for d in (vh._breaker, vh._daily, vh._daily_cap_warned,
              vh._daily_global, vh._daily_global_warned, vh._domain_next_ts):
        d.clear()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "mobilede,vinted")
    monkeypatch.setattr(vh.log_manager, "emit", lambda *a, **k: None)
    hw._reset_state()
    _clear_vinted_state()
    yield
    hw._reset_state()
    _clear_vinted_state()


def _use(monkeypatch, **kw):
    rot = _FakeRotator(**kw)
    monkeypatch.setattr(triggers, "get_rotator", lambda: rot)
    return rot


# ── politica ─────────────────────────────────────────────────────────────────────

def test_blocked_roteste(monkeypatch):
    rot = _use(monkeypatch)
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is True
    assert rot.rotations == 1


def test_celelalte_rezultate_nu_rotesc(monkeypatch):
    rot = _use(monkeypatch)
    for outcome in (Outcome.RATE_LIMITED, Outcome.SITE_CHANGED,
                    Outcome.NOT_FOUND, Outcome.OK):
        assert triggers.rotate_for("mobilede", outcome) is False
    assert rot.rotations == 0


def test_transient_nu_roteste_niciodata(monkeypatch):
    # CRITIC: rotatia insasi taie conexiunea ~34s, deci requesturile prinse in zbor cad
    # cu eroare de retea. Daca aia ar roti, o rotatie ar declansa-o pe urmatoarea, in
    # cascada, pana la epuizarea bugetului orar.
    rot = _use(monkeypatch)
    assert triggers.rotate_for("mobilede", Outcome.TRANSIENT) is False
    assert rot.rotations == 0


def test_rotatie_dezactivata_nu_se_nici_contorizeaza(monkeypatch):
    """Criteriul de acceptare „cu MODEM_ROTATION_ENABLED=false, comportament identic".

    `rotate()` ar intoarce oricum `ok=False`, dar `note_rotation` ar fi rulat deja si
    alertele ar spune „dupa N rotatii de IP" fara sa se fi rotit nimic — pe orice
    instalare fara modem, fiindca `.env.example` livreaza ENABLED=false cu
    ROUTED_PLATFORMS nevid.
    """
    from app.services.network.rotator import reset_rotator
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "false")
    reset_rotator()
    try:
        assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False
        assert hw._rotations_since_alive == {}
    finally:
        reset_rotator()


def test_platforma_nelegata_nu_roteste(monkeypatch):
    # Un 403 pe OLX ar consuma cooldown-ul si ar taia 34s platformele chiar legate.
    rot = _use(monkeypatch)
    assert triggers.rotate_for("olx", Outcome.BLOCKED) is False
    assert rot.rotations == 0


# ── interpretarea rezultatului ───────────────────────────────────────────────────

def test_changed_true_reseteaza_si_intoarce_true(monkeypatch):
    _use(monkeypatch, ok=True, changed=True)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 3600,
                                "half_open": False, "warned_skip": True}
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is True
    assert vh._breaker == {}


def test_changed_false_nu_reseteaza(monkeypatch):
    _use(monkeypatch, ok=True, changed=False)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 3600,
                                "half_open": False, "warned_skip": True}
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is False
    assert "vinted.ro" in vh._breaker


def test_changed_none_nu_reseteaza(monkeypatch):
    # Tri-stare: „n-am putut compara WAN-ul" NU e succes.
    _use(monkeypatch, ok=True, changed=None)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 3600,
                                "half_open": False, "warned_skip": True}
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is False
    assert "vinted.ro" in vh._breaker


def test_rotatie_ignorata_de_cooldown_nu_reseteaza(monkeypatch):
    _use(monkeypatch, ok=False, changed=None)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 3600,
                                "half_open": False, "warned_skip": True}
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is False
    assert "vinted.ro" in vh._breaker


def test_rotatorul_care_arunca_nu_propaga(monkeypatch):
    _use(monkeypatch, boom=True)
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False


def test_note_rotation_si_cand_rotatia_arunca(monkeypatch):
    # Altfel contorul ar spune „0 rotatii" fix cand rotatia e stricata.
    _use(monkeypatch, boom=True)
    triggers.rotate_for("mobilede", Outcome.BLOCKED)
    assert hw._rotations_since_alive.get("mobilede") == 1


# ── NET-5.3a — se numara INCERCARILE, nu cererile ────────────────────────────────

def test_rotatie_incercata_si_esuata_se_contorizeaza(monkeypatch):
    # Proprietatea care trebuie PASTRATA: `ok=False` cu `skipped_reason=None` inseamna
    # ca s-a incercat si n-a mers — exact cazul in care contorul conteaza.
    _use(monkeypatch, ok=False, changed=None, skipped=None)
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False
    assert hw._rotations_since_alive.get("mobilede") == 1


def test_cooldown_nu_contorizeaza(monkeypatch):
    # Cu cooldown 600s si 3 incercari in bucla scraperului, un singur scrape blocat
    # produce O rotatie plus DOUA refuzuri. Fara conditia asta, alerta ar raporta 3.
    _use(monkeypatch, ok=False, skipped="cooldown activ, mai sunt 480s")
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False
    assert hw._rotations_since_alive == {}


def test_buget_orar_epuizat_nu_contorizeaza(monkeypatch):
    _use(monkeypatch, ok=False, skipped="buget orar epuizat (5 rotatii/ora)")
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False
    assert hw._rotations_since_alive == {}


def test_rotator_dezactivat_definitiv_nu_contorizeaza(monkeypatch):
    # Lockout de modem / credentiale gresite: `rotate()` propaga `_disabled_reason` ca
    # skipped_reason. Caz pe care verificarea de tip NoopRotator nu-l acoperea.
    _use(monkeypatch, ok=False, skipped="credentiale gresite pentru modem")
    assert triggers.rotate_for("mobilede", Outcome.BLOCKED) is False
    assert hw._rotations_since_alive == {}


# ── starea Vinted ────────────────────────────────────────────────────────────────

def test_breaker_inchis_dupa_rotatie_reusita(monkeypatch):
    # Fara reset, rotesti pe un IP curat si enrichment-ul ramane oprit SASE ORE degeaba.
    _use(monkeypatch, changed=True)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 6 * 3600,
                                "half_open": False, "warned_skip": True}
    assert vh.guard_before_request("vinted.ro")["allowed"] is False
    triggers.rotate_for("vinted", Outcome.BLOCKED)
    assert vh.guard_before_request("vinted.ro")["allowed"] is True


def test_breaker_ramane_deschis_cand_changed_false(monkeypatch):
    _use(monkeypatch, changed=False)
    vh._breaker["vinted.ro"] = {"consec": 2, "open_until": vh._now() + 6 * 3600,
                                "half_open": False, "warned_skip": True}
    triggers.rotate_for("vinted", Outcome.BLOCKED)
    assert vh.guard_before_request("vinted.ro")["allowed"] is False


def test_reset_sterge_daily_dar_nu_daily_global(monkeypatch):
    today = vh._today_str()
    vh._daily["vinted.ro"] = (today, 250)
    vh._daily_global["vinted.ro"] = (today, 300)
    _use(monkeypatch, changed=True)
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is True
    assert "vinted.ro" not in vh._daily
    assert vh._daily_global["vinted.ro"] == (today, 300)


def test_plafonul_global_refuza_chiar_si_dupa_rotatie(monkeypatch):
    # Plasa care impiedica bucla „250 -> blocaj -> rotatie -> inca 250" sa ajunga la
    # ~1250/ora, exact cadenta care a produs incidentul RP-1.1.
    today = vh._today_str()
    vh._daily["vinted.ro"] = (today, 250)
    vh._daily_global["vinted.ro"] = (today, 750)
    _use(monkeypatch, changed=True)
    assert triggers.rotate_for("vinted", Outcome.BLOCKED) is True
    decision = vh.guard_before_request("vinted.ro")
    assert decision["allowed"] is False
    assert decision["reason"] == "daily_global_cap"


# ── watchdog ─────────────────────────────────────────────────────────────────────

def _blocked_cycle(platform, results=0):
    hw.open_cycle(platform)
    hw.note_results(platform, results)
    if not results:
        hw.note_blocked(platform)
    hw.close_cycle(None, platform)


def test_contorul_se_reseteaza_doar_la_recovery():
    hw.note_rotation("mobilede")
    hw.note_rotation("mobilede")
    assert hw._rotations_since_alive["mobilede"] == 2
    _blocked_cycle("mobilede")                      # ciclu blocat: NU reseteaza
    assert hw._rotations_since_alive["mobilede"] == 2
    _blocked_cycle("mobilede", results=5)           # recovery real: reseteaza
    assert hw._rotations_since_alive["mobilede"] == 0


def test_alerta_pleaca_chiar_daca_rotim_intre_cicluri(monkeypatch):
    """Scenariu: blocat -> rotim -> tot blocat. Daca rotatia ar reseta streak-urile,
    pragul nu s-ar atinge NICIODATA si n-ar pleca nicio alerta: am roti in gol pana la
    epuizarea bugetului orar, fara ca nimeni sa afle. Rotatiile trec prin `rotate_for`,
    nu prin `note_rotation` direct — altfel testul nu atinge calea reala."""
    alerts = []
    monkeypatch.setattr(hw, "_dispatch_alert",
                        lambda db, text, level: alerts.append(text))
    _use(monkeypatch, changed=True)
    for _ in range(2):
        hw.open_cycle("mobilede")
        hw.note_results("mobilede", 0)
        hw.note_blocked("mobilede")
        triggers.rotate_for("mobilede", Outcome.BLOCKED)
        hw.close_cycle(None, "mobilede")
    assert len(alerts) == 1
    assert "după 2 rotații de IP" in alerts[0]


def test_textul_alertei_fara_rotatii_nu_are_sufix(monkeypatch):
    alerts = []
    monkeypatch.setattr(hw, "_dispatch_alert",
                        lambda db, text, level: alerts.append(text))
    for _ in range(2):
        _blocked_cycle("mobilede")
    assert len(alerts) == 1 and "rotații" not in alerts[0]


# ── §7 — recuperarea datelor la boot ─────────────────────────────────────────────

def test_link_jos_nu_cheama_available(monkeypatch):
    # available() ar dura ~30s cu modemul absent si ar intarzia pornirea uvicorn.
    rot = _use(monkeypatch)
    monkeypatch.setattr(triggers.binding, "modem_link_up", lambda *a: False)
    assert triggers.recover_data_if_link_up() is False
    assert rot.available_calls == 0


def test_link_sus_cheama_available_o_data(monkeypatch):
    rot = _use(monkeypatch)
    monkeypatch.setattr(triggers.binding, "modem_link_up", lambda *a: True)
    assert triggers.recover_data_if_link_up() is True
    assert rot.available_calls == 1
