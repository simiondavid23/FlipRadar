"""SA-1 — `scripts/scraper_audit.py` ramane sincronizat cu scannerele.

DE CE EXISTA: predecesorul auditului (`scripts/diagnostics/platform_health_probe.py`,
gitignored) si-a tinut listele de platforme scrise de mana si a ramas in urma codului
de doua ori la rand — dupa MKT-DEAD importa un pachet sters, dupa RC-1 cadea la import
pe scraperele Radar de masini. Testele de aici fac exact ce n-avea sonda: leaga listele
auditului de listele REALE ale scannerelor, ca o platforma adaugata sau scoasa dintr-un
scanner sa nu poata trece neobservata pe langa audit.

Fara retea: nu se apeleaza niciun callable de proba, doar se construiesc.
"""
import importlib.util
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUDIT = os.path.join(_BACKEND, "scripts", "scraper_audit.py")


def _incarca_audit():
    """Importa scriptul ca modul, fara sa-i ruleze `main()` (tot ce face e sub
    `if __name__ == "__main__"`)."""
    spec = importlib.util.spec_from_file_location("scraper_audit", _AUDIT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("scraper_audit", mod)
    spec.loader.exec_module(mod)
    return mod


audit = _incarca_audit()


def _platforme_scanner(modul: str) -> set:
    if modul == "radar":
        from app.utils.radar_scanner import RADAR_PLATFORMS
        return set(RADAR_PLATFORMS)
    if modul == "auto":
        from app.services.auto_listings_scanner import AUTO_PLATFORMS
        return set(AUTO_PLATFORMS)
    from app.services.real_estate_scanner import RE_PLATFORMS
    return set(RE_PLATFORMS)


# ── 1: sincronizarea cu scannerele ───────────────────────────────────────────────
@pytest.mark.parametrize("modul", ["radar", "auto", "imob"])
def test_listele_auditului_acopera_scannerul(modul):
    acoperite = (set(audit.GRUPURI_LIVE[modul])
                 | {audit.FACEBOOK[modul]}
                 | set(audit.EXCLUSE.get(modul, [])))
    reale = _platforme_scanner(modul)
    assert acoperite == reale, (
        f"scraper_audit.py e desincronizat pe modulul '{modul}': "
        f"lipsesc {sorted(reale - acoperite)}, in plus {sorted(acoperite - reale)}. "
        f"Ai adaugat/scos o platforma din scanner — actualizeaza scripts/scraper_audit.py "
        f"(GRUPURI_LIVE / FACEBOOK / EXCLUSE)."
    )


# ── 2: clasificatorul de verdicte ────────────────────────────────────────────────
@pytest.mark.parametrize("n,err,zgomot,asteptat", [
    (0, "", "", "GOL"),                      # a raspuns, dar n-a gasit nimic
    (5, "", "", "OK"),
    (0, "Timeout", "", "BLOCAT"),            # exceptia bate orice
    (0, "", "[x] HTTP 403", "BLOCAT"),       # scraperul a inghitit blocajul si a printat
    (5, "", "HTTP 403", "OK"),               # a intors rezultate: zgomotul nu conteaza
])
def test_clasifica(n, err, zgomot, asteptat):
    assert audit._clasifica(n, err, zgomot) == asteptat


# ── 3: constructorii intorc exact numele declarate ───────────────────────────────
@pytest.mark.parametrize("modul,builder", [
    ("radar", lambda a: a.probe_radar("iphone", 5000.0)),
    ("auto", lambda a: a.probe_auto()),
    ("imob", lambda a: a.probe_imob()),
])
def test_constructorii_intorc_numele_din_grupuri_live(modul, builder):
    probe = builder(audit)
    assert [g for g, _n, _f in probe] == [modul] * len(probe)
    assert [n for _g, n, _f in probe] == audit.GRUPURI_LIVE[modul]
    assert all(callable(f) for _g, _n, f in probe)


# ── 4: etichetele se prefixeaza doar cand numele e ambiguu ───────────────────────
def test_eticheta_prefixeaza_doar_numele_ambigue():
    assert "olx" in audit.nume_ambigue()          # exista si in radar, si in imob
    assert audit.eticheta("radar", "olx") == "radar/olx"
    assert audit.eticheta("imob", "olx") == "imob/olx"
    assert audit.eticheta("radar", "vinted") == "vinted"
    assert audit.eticheta("auto", "mobile_de") == "mobile_de"


# ── 5: main() pe grupul facebook — fara retea, fara disc ─────────────────────────
def test_main_pe_facebook_nu_atinge_reteaua(monkeypatch, capsys):
    monkeypatch.setenv("FB_MOD", "bazin")   # `bazin` citeste din fb_pool, deci nici disc
    assert audit.main(["--group", "facebook", "--no-json"]) == 0
    iesire = capsys.readouterr().out
    assert "FB_MOD=bazin" in iesire
    for nume in audit.FACEBOOK.values():
        assert nume in iesire
    assert "SARIT" in iesire


# ── 6: platformele excluse au un motiv, nu-s uitate ──────────────────────────────
def test_exclusele_nu_sunt_probe_live():
    for modul, nume in audit.EXCLUSE.items():
        for n in nume:
            assert n not in audit.GRUPURI_LIVE[modul]
            assert n != audit.FACEBOOK[modul]
