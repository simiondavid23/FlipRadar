"""TOOL-1 — `scripts/keyword_diag.py` ramane sincronizat cu scannerul si nu minte.

DE CE EXISTA: unealta raspunde la intrebarea de suport numarul unu („de ce nu-mi da
keyword-ul asta nimic?"), iar raspunsul ei e util DOAR daca reproduce exact decizia din
`_scan_user`. Trei lucruri se pot strica tacut si le prinde fisierul asta:

  * lista de platforme acceptate se desincronizeaza de `RADAR_PLATFORMS`;
  * ordinea treptelor de decizie se schimba (un anunt si vazut, si vechi trebuie sa iasa
    `SEEN`, fiindca `_already_seen` se verifica INAINTEA lui `_too_old`);
  * garda de Facebook cade, si o rulare de diagnostic consuma tacut bugetul contului.

Fara retea si fara baza: `decide` e pura (primeste `seen` si cursurile gata calculate),
iar celelalte teste nu ajung la Faza A.
"""
import importlib.util
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL = os.path.join(_BACKEND, "scripts", "keyword_diag.py")


def _incarca():
    """Importa scriptul ca modul, fara sa-i ruleze `main()` (e sub `__main__`)."""
    spec = importlib.util.spec_from_file_location("keyword_diag", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("keyword_diag", mod)
    spec.loader.exec_module(mod)
    return mod


diag = _incarca()


def _kw(resale_price=1000.0, min_margin_pct=10.0, max_age_days=None):
    """Forma minima de RadarKeyword citita de `decide`."""
    return types.SimpleNamespace(
        resale_price=resale_price, min_margin_pct=min_margin_pct,
        max_age_days=max_age_days, grade_a_min=None, grade_b_min=None, grade_c_min=None,
    )


# ── 1: importul nu are efecte secundare ─────────────────────────────────────────
def test_importul_nu_deschide_baza_si_nu_face_retea():
    """Modulul se importa cu `app` NEATINS: toate importurile din `app` sunt locale,
    in functii. Daca cineva le muta la nivel de fisier, `app.config` se evalueaza la
    import (si cu el DATABASE_URL, engine-ul, lantul de curs) — exact ce nu vrem
    intr-un modul care e si importat de teste, si copiat pe productie."""
    sursa = open(_TOOL, encoding="utf-8").read()
    inainte_de_main = sursa.split("def main(", 1)[0]
    for linie in inainte_de_main.splitlines():
        strip = linie.strip()
        if strip.startswith(("import app", "from app")) and not linie.startswith(" "):
            pytest.fail(f"import din `app` la nivel de modul: {strip!r}")
    # Contra-proba: functiile care CHIAR au nevoie de `app` il importa local.
    assert "from app.utils.radar_scanner import RADAR_PLATFORMS" in sursa


# ── 2: platforma invalida -> cod 2 + lista valida in mesaj ──────────────────────
def test_platforma_invalida_da_cod_2_cu_lista(capsys):
    from app.utils.radar_scanner import RADAR_PLATFORMS

    cod = diag.main(["--platforma", "autovit"])

    assert cod == 2
    iesire = capsys.readouterr().out
    for p in RADAR_PLATFORMS:
        assert p in iesire, iesire
    assert "autovit" in iesire


# ── 3: decizia per anunt, in ordinea din scanner ────────────────────────────────
def test_decide_seen():
    assert diag.decide({"external_id": "x", "price": 100.0, "currency": "RON"},
                       _kw(), seen=True, eur_ron=5.0).startswith("SEEN")


def test_decide_too_old():
    from datetime import datetime, timedelta
    vechi = datetime.utcnow() - timedelta(days=30)
    verdict = diag.decide({"external_id": "x", "price": 100.0, "currency": "RON",
                           "listed_at": vechi},
                          _kw(max_age_days=7), seen=False, eur_ron=5.0)
    assert verdict.startswith("TOO_OLD"), verdict


def test_decide_seen_bate_too_old():
    """Ordinea din `_scan_user`: `_already_seen` INAINTEA lui `_too_old`. Un anunt si
    vazut, si vechi iese `SEEN` — inversarea ar da alt verdict pe aceleasi date."""
    from datetime import datetime, timedelta
    vechi = datetime.utcnow() - timedelta(days=30)
    verdict = diag.decide({"external_id": "x", "price": 100.0, "currency": "RON",
                           "listed_at": vechi},
                          _kw(max_age_days=7), seen=True, eur_ron=5.0)
    assert verdict.startswith("SEEN"), verdict


def test_decide_filtrat_marja():
    """1500 RON fata de 1000 RON revanzare -> marja negativa -> nu intra in feed."""
    verdict = diag.decide({"external_id": "x", "price": 1500.0, "currency": "RON"},
                          _kw(resale_price=1000.0), seen=False, eur_ron=5.0)
    assert verdict.startswith("FILTRAT_MARJA"), verdict


def test_decide_kept_cu_grad():
    """400 RON fata de 1000 -> marja 60% -> grad A."""
    verdict = diag.decide({"external_id": "x", "price": 400.0, "currency": "RON"},
                          _kw(resale_price=1000.0), seen=False, eur_ron=5.0)
    assert verdict.startswith("KEPT grad A"), verdict


def test_decide_foloseste_catalogul_de_monede():
    """CUR-1/TIDY-1: `decide` paseaza `cursuri` mai departe, deci un anunt in GBP se
    scoreaza convertit. Fara catalog, 100 GBP ar fi citit ca 100 RON (grad A fals)."""
    listing = {"external_id": "x", "price": 100.0, "currency": "GBP"}
    cu = diag.decide(listing, _kw(resale_price=1000.0), seen=False,
                     eur_ron=5.0, usd_ron=4.5, cursuri={"GBP": 6.0})
    fara = diag.decide(listing, _kw(resale_price=1000.0), seen=False, eur_ron=5.0)
    assert "pret_ron=600.0" in cu, cu
    assert "pret_ron=100.0" in fara, fara


def test_decide_fara_external_id():
    assert diag.decide({"price": 100.0, "currency": "RON"},
                       _kw(), seen=False, eur_ron=5.0) == "FARA_EXTERNAL_ID"


# ── 4: sincronizare cu scannerul ────────────────────────────────────────────────
def test_platformele_acceptate_sunt_exact_cele_din_scanner():
    from app.utils.radar_scanner import RADAR_PLATFORMS

    assert set(diag.platforme_valide()) == set(RADAR_PLATFORMS), (
        "ai schimbat scannerul — actualizeaza keyword_diag.py")


def test_lista_de_enrichment_e_cea_din_scan_user():
    """`_skip_enrich` se construieste doar pentru platformele cu enrichment de detaliu.
    Daca una intra sau iese din lista in `_scan_user`, unealta trebuie sa urmeze."""
    sursa = open(os.path.join(_BACKEND, "app", "utils", "radar_scanner.py"),
                 encoding="utf-8").read()
    assert 'if platform in ("okazii", "lajumate", "publi24"):' in sursa, (
        "lista de enrichment din _scan_user s-a schimbat — "
        "actualizeaza _PLATFORME_CU_ENRICHMENT din keyword_diag.py")
    assert diag._PLATFORME_CU_ENRICHMENT == ("okazii", "lajumate", "publi24")


# ── 5: Faza B pe facebook e pazita ──────────────────────────────────────────────
def test_faza_b_pe_facebook_nu_ruleaza_fara_flag(auth_client, monkeypatch, capsys):
    """Fara `--permite-facebook`, o rulare de diagnostic nu are voie sa consume bugetul
    contului: `_run_scraper` trebuie sa ramana NEAPELAT.

    Keyword-ul se creeaza ANUME: pe o baza goala garda n-ar fi probata deloc — Faza B
    n-are ce apela oricum, deci testul ar trece si cu garda scoasa.
    """
    from app.database import SessionLocal
    from app.models.radar_settings import RadarSettings
    from app.utils import radar_scanner as RS

    uid = auth_client.get("/api/auth/me").json()["id"]
    r = auth_client.post("/api/radar/keywords", json={
        "name": "geaca de piele", "max_price": 1000.0, "resale_price": 2000.0,
        "platforms": ["facebook"], "notify_email": False, "notify_discord": False,
    })
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        s = db.query(RadarSettings).filter(RadarSettings.user_id == uid).first()
        if s is None:
            s = RadarSettings(user_id=uid)
            db.add(s)
        s.platform_facebook_enabled = True
        db.commit()
    finally:
        db.close()

    apeluri = []
    monkeypatch.setattr(RS, "_run_scraper",
                        lambda *a, **k: apeluri.append(a) or [])

    diag.main(["--platforma", "facebook", "--max-keywords", "1"])

    iesire = capsys.readouterr().out
    assert "keyword-uri active pe 'facebook'" in iesire.lower(), iesire
    assert "potrivite pe 'facebook': 1" in iesire, "keyword-ul de test n-a fost gasit"
    assert apeluri == [], "Faza B a apelat scraperul pe facebook fara flag"
    assert "--permite-facebook" in iesire, iesire
