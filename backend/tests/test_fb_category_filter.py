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
    monkeypatch.setattr(fauth, "needs_reauth", lambda results, path: False)
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
