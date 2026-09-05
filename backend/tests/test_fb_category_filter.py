"""A6/A7 (audit FB) — filtrul de categorie, aliniat pe conventia fail-open.

Cele doua scrapere Facebook tratau DIFERIT un card fara categorie:
  Radar:  `if cat_id != str(category): continue`      -> None difera de orice => EXCLUS
  Auto:   `if cat_id is not None and ...: continue`   -> None => PASTRAT

Facebook nu pune `marketplace_listing_category_id` pe toate cardurile, deci varianta
stricta stergea tacut anunturi reale de indata ce userul alegea o categorie. Conventia
dominanta a proiectului e fail-open (un criteriu care nu se poate verifica NU respinge):
_matches_re_keyword la Imobiliare, plasa year/km din Auto, _is_active, post-filtrul de
subcategorie OLX. Radar s-a aliniat la Auto.

Fisierul acopera AMBELE scrapere, fiindca invarianta de paritate e miezul deciziei.
"""
import pytest

from app.services.radar import facebook_scraper as fb


_VEH = None    # id-ul categoriei vehicule (Auto), rezolvat lenes in _auto_obj


# ── infrastructura: Radar ────────────────────────────────────────────────────────

def _radar_obj(oid: str, title: str, cat_id=None, amount="1000.00") -> dict:
    o = {
        "id": oid,
        "marketplace_listing_title": title,
        "listing_price": {"amount": amount, "formatted_amount": f"RON{amount}"},
    }
    if cat_id is not None:
        o["marketplace_listing_category_id"] = cat_id
    return o


def _radar(monkeypatch, obiecte: list, category=None, logs=None) -> list:
    """search_facebook REAL, cu sesiunea/fetch-ul/iterarea JSON stubuite."""
    import app.services.facebook_auth as fauth

    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fb, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fb, "_fetch", lambda url, cookies: ("<html></html>", "https://www.facebook.com/marketplace/search/"))
    monkeypatch.setattr(fb, "_iter_listing_objects", lambda h: list(obiecte))
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)) if logs is not None else None)
    monkeypatch.setattr(fauth, "session_probably_expired", lambda results, path: False)
    return fb.search_facebook(keyword="geaca", max_price=5000, category=category,
                              session_path="sesiune.json")


# ── infrastructura: Auto (oglinda) ───────────────────────────────────────────────

def _auto_obj(oid: str, title: str, cat_id="__VEH__", amount="10000.00") -> dict:
    from app.scrapers.auto.listings import facebook_auto_scraper as fa
    o = {
        "id": oid,
        "marketplace_listing_title": title,
        "listing_price": {"amount": amount, "formatted_amount": f"RON{amount}"},
    }
    if cat_id == "__VEH__":
        o["marketplace_listing_category_id"] = fa._vehicles_category_id()
    elif cat_id is not None:
        o["marketplace_listing_category_id"] = cat_id
    return o


def _auto(monkeypatch, obiecte: list) -> list:
    from app.scrapers.auto.listings import facebook_auto_scraper as fa

    monkeypatch.setattr(fa, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fa, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fa, "_fetch", lambda url, cookies: ("<html></html>", "https://www.facebook.com/marketplace/search/"))
    monkeypatch.setattr(fa, "_iter_listing_objects", lambda h: list(obiecte))
    monkeypatch.setattr(fa.log_manager, "emit", lambda *a, **k: None)
    return fa.search_facebook_auto(query="bmw", filters={}, session_path="sesiune.json")


# ── Radar: filtrul de categorie ──────────────────────────────────────────────────

def test_anunt_fara_categorie_ramane_desi_userul_a_cerut_o_categorie(monkeypatch):
    """TINTA A6/A7: inainte, `cat_id != str(category)` era adevarat si pentru None,
    deci anuntul disparea tacut."""
    out = _radar(monkeypatch, [_radar_obj("1", "Geaca de piele", cat_id=None)],
                 category="1234")
    assert [r["title"] for r in out] == ["Geaca de piele"]


def test_anunt_cu_alta_categorie_e_exclus(monkeypatch):
    # Regresie: filtrul chiar filtreaza cand ARE ce verifica.
    out = _radar(monkeypatch, [_radar_obj("1", "Geaca de piele", cat_id="9999")],
                 category="1234")
    assert out == []


def test_anunt_cu_aceeasi_categorie_ramane(monkeypatch):
    out = _radar(monkeypatch, [_radar_obj("1", "Geaca de piele", cat_id="1234")],
                 category="1234")
    assert len(out) == 1


def test_anunt_cu_categorie_numerica_se_compara_ca_text(monkeypatch):
    # cat_id vine int din JSON; comparatia se face pe str, ca inainte.
    out = _radar(monkeypatch, [_radar_obj("1", "Geaca", cat_id=1234)], category="1234")
    assert len(out) == 1


def test_fara_categorie_ceruta_nu_se_filtreaza_nimic(monkeypatch):
    out = _radar(monkeypatch, [_radar_obj("1", "Geaca", cat_id=None),
                               _radar_obj("2", "Rochie", cat_id="9999")],
                 category=None)
    assert len(out) == 2


def test_amestec_pastreaza_potrivirea_si_necunoscutul_dar_taie_diferitul(monkeypatch):
    logs = []
    out = _radar(monkeypatch, [_radar_obj("1", "Potrivit", cat_id="1234"),
                               _radar_obj("2", "Fara categorie", cat_id=None),
                               _radar_obj("3", "Alta categorie", cat_id="9999")],
                 category="1234", logs=logs)
    assert sorted(r["title"] for r in out) == ["Fara categorie", "Potrivit"]
    # Vizibilitate: userul vede in jurnal de ce a primit si un anunt fara categorie.
    info = [m for lvl, m in logs if lvl == "INFO" and "fara categorie" in m]
    assert len(info) == 1 and "1 anunturi" in info[0]


# ── paritate Radar <-> Auto pe acelasi scenariu ──────────────────────────────────

def test_paritate_cardul_fara_categorie_e_pastrat_de_ambele_scrapere(monkeypatch):
    """Invarianta deciziei: acelasi card (fara categorie), acelasi verdict in ambele
    module. Auto era deja tolerant; Radar s-a aliniat."""
    radar_out = _radar(monkeypatch, [_radar_obj("1", "Fara categorie", cat_id=None)],
                       category="1234")
    auto_out = _auto(monkeypatch, [_auto_obj("1", "BMW fara categorie", cat_id=None)])
    assert len(radar_out) == 1 and len(auto_out) == 1


def test_paritate_cardul_cu_alta_categorie_e_exclus_de_ambele(monkeypatch):
    radar_out = _radar(monkeypatch, [_radar_obj("1", "Alta categorie", cat_id="9999")],
                       category="1234")
    auto_out = _auto(monkeypatch, [_auto_obj("1", "Jante BMW", cat_id="9999")])
    assert radar_out == [] and auto_out == []


# ── FBS-11/12: ramurile de moneda pe calea de SESIUNE ────────────────────────────
# Golul raportat la FBS-11: filtrele de pret devenisera constiente de moneda pe AMBELE
# cai, dar doar calea de nucleu avea teste — harness-ul care conduce calea de sesiune
# cap-coada e chiar `_radar` de mai sus. FBS-12 il foloseste, ca ramurile sa nu mai fie
# acoperite doar prin citire.

@pytest.fixture
def curs(monkeypatch):
    """Cursuri PINUITE. Fisierul n-are autouse-ul din test_fb_radar_adapter.py, iar fara
    fixare un anunt in EUR/USD ar chema cursul real, al carui lant incepe cu un fetch."""
    from app.services import bnr_exchange
    monkeypatch.setattr(bnr_exchange, "get_eur_ron", lambda: 5.0)
    monkeypatch.setattr(bnr_exchange, "get_usd_ron", lambda: 4.5)
    # CUR-1: de cand `pret_comparabil_ron` cauta codurile din afara EUR/USD in
    # catalogul BNR, si acel lant incepe cu un FETCH — deci se pinuieste la fel.
    # Catalog gol = orice cod non-EUR/USD ramane „necunoscut", ca inainte de CUR-1.
    from app.services import currency_service
    monkeypatch.setattr(currency_service, "_fetch_cu_backoff", lambda now: None)
    monkeypatch.setattr(currency_service, "_disk_rates", lambda: {})
    currency_service._CACHE.clear()
    currency_service._CACHE_TIMESTAMP.clear()


def _pret_obj(oid: str, titlu: str, suma: str, formatted: str) -> dict:
    """Card cu `formatted_amount` controlat — de acolo isi ia parserul moneda."""
    return {"id": oid, "marketplace_listing_title": titlu,
            "listing_price": {"amount": suma, "formatted_amount": formatted}}


def test_sesiune_eur_se_compara_convertit(monkeypatch, curs):
    """500 EUR = 2500 RON (sub `max_price` 5000, deci ramane), 1200 EUR = 6000 RON
    (peste, deci cade). Inainte de FBS-11 amandoua treceau, comparate ca numere."""
    out = _radar(monkeypatch, [
        _pret_obj("1", "Geaca ieftina", "500", "€500"),
        _pret_obj("2", "Geaca scumpa", "1200", "€1200"),
    ])

    assert [r["external_id"] for r in out] == ["fb_1"]
    assert out[0]["price"] == 500.0 and out[0]["currency"] == "EUR", \
        "pretul afisat ramane in moneda lui"


def test_sesiune_usd_se_converteste(monkeypatch, curs):
    """FBS-12: 1200 USD = 5400 RON, peste `max_price` 5000 — cade. La FBS-11 ar fi
    trecut permisiv, fiindca USD nu era convertibil."""
    out = _radar(monkeypatch, [
        _pret_obj("1", "Geaca ieftina", "500", "500 USD"),      # 2250 RON, ramane
        _pret_obj("2", "Geaca scumpa", "1200", "1200 USD"),     # 5400 RON, cade
    ])

    assert [r["external_id"] for r in out] == ["fb_1"]


def test_sesiune_moneda_necunoscuta_trece_cu_contor(monkeypatch, curs):
    """D2 pe calea de sesiune, devenita EFECTIVA de cand parserul spune adevarul: pana
    la FBS-12 un „9000 GBP" era etichetat RON si taiat de `max_price`.

    CUR-1: exemplul a trecut de la GBP la „XXX" — GBP e in catalogul BNR si se
    CONVERTESTE acum, deci nu mai exercita poarta permisiva."""
    logs = []
    out = _radar(monkeypatch, [_pret_obj("1", "Geaca", "9000", "9000 XXX")], logs=logs)

    assert [r["external_id"] for r in out] == ["fb_1"]
    assert out[0]["currency"] == "XXX"
    assert any("moneda lor nu se poate aduce in RON" in m
               for niv, m in logs if niv == "INFO"), logs


def test_sesiune_cursul_picat_lasa_sa_treaca_cu_un_singur_warn(monkeypatch):
    """D3 pe calea de sesiune: filtrarea nu pica fiindca BNR-ul tace, iar avertismentul
    e unul per apel, nu unul per anunt."""
    from app.services import bnr_exchange

    def explodeaza():
        raise RuntimeError("BNR indisponibil")

    monkeypatch.setattr(bnr_exchange, "get_eur_ron", explodeaza)
    logs = []
    out = _radar(monkeypatch, [_pret_obj("1", "Geaca A", "9000", "€9000"),
                               _pret_obj("2", "Geaca B", "9500", "€9500")], logs=logs)

    assert {r["external_id"] for r in out} == {"fb_1", "fb_2"}
    warn = [m for niv, m in logs if niv == "WARN" and "cursul BNR indisponibil" in m]
    assert len(warn) == 1, f"UN singur WARN per apel, nu {len(warn)}"


def test_sesiune_ron_ramane_neutru(monkeypatch, curs):
    """Regresie: acolo unde nu exista moneda straina, nimic nu se schimba si jurnalul tace."""
    logs = []
    out = _radar(monkeypatch, [_pret_obj("1", "Geaca A", "1000", "RON1000"),
                               _pret_obj("2", "Geaca B", "9000", "RON9000")], logs=logs)

    assert [r["external_id"] for r in out] == ["fb_1"], "9000 RON e peste max_price 5000"
    assert not [m for _n, m in logs if "fara verificare" in m]
