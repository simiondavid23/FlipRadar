"""FB-5 — Radar pe nucleul logat-out, sub comutatorul FB_MOD.

Offline: nucleul e inlocuit pe `facebook_scraper.nucleu_search` /
`nucleu_fetch_detail`. Anunturile mock sunt dicturi CANONICE (forma emisa de
`parse.canonic`), nu obiecte brute de Facebook.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.radar import facebook_scraper as fb

CAT_GEACA = "1608022336159396"      # o categorie oarecare, folosita ca "ceruta"
_AWARE = datetime(2026, 8, 15, 6, 30, 0, tzinfo=timezone.utc)


def _canonic(ext_id="111", *, title="Geaca de piele", price=250.0, currency="RON",
             category_id=None, listed_at=_AWARE, location="București",
             image_url="https://x.invalid/1.jpg"):
    return {
        "external_id": ext_id, "title": title, "price": price, "currency": currency,
        "location": location, "image_url": image_url, "listed_at": listed_at,
        "category_id": category_id,
        "source_url": f"https://www.facebook.com/marketplace/item/{ext_id}/",
    }


@pytest.fixture(autouse=True)
def _env_curat(monkeypatch):
    for v in ("FB_MOD", "FB_RADAR_ANCORA", "FB_FERMA"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda modul, nivel, mesaj: capturate.append((nivel, mesaj)))
    return capturate


@pytest.fixture
def nucleu(monkeypatch):
    apeluri, raspuns = [], []

    # `pret_min` adaugat la FBS-6: dublul trebuie sa poarte ACEEASI semnatura ca
    # `nucleu_search`-ul real, altfel calea logout ridica TypeError la fiecare apel.
    def fals(query, lat, lon, *, raza_km=65, city_page_id=None, pret_min=None):
        apeluri.append({"query": query, "lat": lat, "lon": lon, "raza_km": raza_km,
                        "city_page_id": city_page_id, "pret_min": pret_min})
        return list(raspuns)

    monkeypatch.setattr(fb, "nucleu_search", fals)
    fals.apeluri, fals.raspuns = apeluri, raspuns
    return fals


def _warn(logs):
    return [m for niv, m in logs if niv == "WARN"]


# ── 1. dispecerul ────────────────────────────────────────────────────────────
def test_logout_merge_pe_nucleu(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic())

    rez = fb.search_facebook("geaca", max_price=1000)

    assert len(nucleu.apeluri) == 1 and len(rez) == 1


def test_sesiune_nu_atinge_nucleul(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "sesiune")
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)
    monkeypatch.setattr(fb, "report_outcome", lambda *a: True)

    assert fb.search_facebook("geaca", max_price=1000) == []
    assert nucleu.apeluri == []


def test_fb_mod_absent_inseamna_sesiune(monkeypatch, nucleu):
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)
    monkeypatch.setattr(fb, "report_outcome", lambda *a: True)

    assert fb.search_facebook("geaca", max_price=1000) == []
    assert nucleu.apeluri == []


def test_fb_mod_necunoscut_cade_pe_sesiune_cu_warn(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "hibrid")
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)
    monkeypatch.setattr(fb, "report_outcome", lambda *a: True)

    fb.search_facebook("geaca", max_price=1000)

    assert nucleu.apeluri == []
    assert any("hibrid" in m for m in _warn(logs)), _warn(logs)


@pytest.mark.parametrize("mod", ["logout", "sesiune"])
def test_pagina_peste_1_si_keyword_gol_dau_lista_goala(monkeypatch, nucleu, mod):
    monkeypatch.setenv("FB_MOD", mod)
    nucleu.raspuns.append(_canonic())

    assert fb.search_facebook("geaca", max_price=1000, page=2) == []
    assert fb.search_facebook("   ", max_price=1000) == []
    assert nucleu.apeluri == [], "garda e in dispecer, inainte de orice cale"


# ── 2. filtrele pe calea logout ──────────────────────────────────────────────
def test_exclude_words_exclude(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([_canonic("1", title="Geaca piele"),
                           _canonic("2", title="Geaca replica")])

    rez = fb.search_facebook("geaca", max_price=1000, exclude_words=["replica"])

    assert {r["external_id"] for r in rez} == {"fb_1"}


def test_marginile_de_pret(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    # Titluri DISTINCTE, deliberat (FBS-9b): cinci anunturi cu acelasi titlu postate in
    # aceeasi clipa sunt o amprenta de ferma si s-ar arunca INAINTEA filtrului de pret,
    # care e chiar variabila masurata aici. Doar datele s-au schimbat, nu asertiunea.
    nucleu.raspuns.extend([_canonic("1", price=50.0, title="Geaca piele neagra"),
                           _canonic("2", price=250.0, title="Geaca piele maro"),
                           _canonic("3", price=900.0, title="Geaca piele vintage"),
                           _canonic("4", price=None, title="Geaca fara pret"),
                           _canonic("5", price=0.0, title="Geaca cu pret zero")])

    rez = fb.search_facebook("geaca", max_price=500, min_price=100)

    assert {r["external_id"] for r in rez} == {"fb_2"}


@pytest.mark.parametrize("cat_anunt,ceruta,ramane", [
    (CAT_GEACA, CAT_GEACA, True),      # aceeasi categorie
    ("999999999", CAT_GEACA, False),   # cunoscuta si diferita -> exclus
    (None, CAT_GEACA, True),           # absenta -> pastrat (A6/A7 fail-open)
    ("777", None, True),               # neceruta -> nu se filtreaza nimic
])
def test_regula_de_categorie_a6_a7(monkeypatch, nucleu, cat_anunt, ceruta, ramane):
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setattr(fb, "_known_facebook_category_ids",
                        lambda: {CAT_GEACA, "999999999"})
    nucleu.raspuns.append(_canonic("1", category_id=cat_anunt))

    rez = fb.search_facebook("geaca", max_price=1000, category=ceruta)

    assert bool(rez) is ramane


def test_categoria_necunoscuta_se_logheaza_dar_regula_ramane_cea_de_diferenta(
        monkeypatch, nucleu, logs):
    """A6/A7, exact ca pe sesiune: „necunoscut" NU e el insusi motiv de excludere (de-aia
    doar se logheaza), dar un id PREZENT si DIFERIT tot exclude — chiar daca e necunoscut.
    Un id necunoscut care COINCIDE cu categoria ceruta ramane."""
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setattr(fb, "_known_facebook_category_ids", lambda: {CAT_GEACA})
    nucleu.raspuns.append(_canonic("1", category_id="123-necunoscuta"))

    rez = fb.search_facebook("geaca", max_price=1000, category=CAT_GEACA)

    assert rez == [], "prezent + diferit = exclus, indiferent daca e cunoscut"
    assert any("necunoscut" in m for niv, m in logs if niv == "INFO")

    # acelasi id necunoscut, dar CERUT explicit -> ramane
    nucleu.raspuns.clear()
    nucleu.raspuns.append(_canonic("2", category_id="123-necunoscuta"))
    assert len(fb.search_facebook("geaca", max_price=1000,
                                  category="123-necunoscuta")) == 1


def test_anunturile_fara_categorie_se_numara(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setattr(fb, "_known_facebook_category_ids", lambda: {CAT_GEACA})
    nucleu.raspuns.extend([_canonic("1", category_id=None), _canonic("2", category_id=None)])

    fb.search_facebook("geaca", max_price=1000, category=CAT_GEACA)

    assert any("2 anunturi pastrate fara categorie" in m for niv, m in logs if niv == "INFO")


# ── 2b. FBS-8: cifrele keyword-ului trebuie sa apara in titlu ────────────────
def test_cifrele_keywordului_taie_modelul_gresit(monkeypatch, nucleu, logs):
    """Cautarea FB e FUZZY pe model (masurat la FBS-V2: „iphone 15 pro max" intoarce
    14 si 17 Pro Max, relevanta 0%). Poarta noua taie ce nu poarta grupul cerut."""
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([
        _canonic("1", title="iPhone15 Pro Max GB"),        # lipit de litere -> ramane
        _canonic("2", title="Iphone 17 Pro max nou"),      # alt model -> cade
        _canonic("3", title="iphone 1500 lei super"),      # 15 inghitit de 1500 -> cade
    ])

    rez = fb.search_facebook("iphone 15 pro max", max_price=100000)

    assert {r["external_id"] for r in rez} == {"fb_1"}
    assert any("2 anunturi sarite" in m and "iphone 15 pro max" in m
               for niv, m in logs if niv == "INFO"), [m for _, m in logs]


def test_keyword_fara_cifre_lasa_totul_neatins(monkeypatch, nucleu, logs):
    """No-op complet: pe termeni fara cifre comportamentul e identic cu cel de dinainte
    de FBS-8, inclusiv absenta liniei de jurnal."""
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([_canonic("1", title="Geaca de piele"),
                           _canonic("2", title="Iphone 17 Pro max nou"),
                           _canonic("3", title="canapea 1500 lei")])

    rez = fb.search_facebook("geaca", max_price=100000)

    assert {r["external_id"] for r in rez} == {"fb_1", "fb_2", "fb_3"}
    assert not [m for niv, m in logs if niv == "INFO" and "sarite" in m]


# ── 2c. FBS-9b: amprenta de ferma, cablata in `_search_logout` ───────────────
def _feed_cu_ferma():
    """Trei anunturi cu titlu identic intr-o rafala de 4 minute (agravant: rafala) plus
    doua genuine distincte. Forma e cea masurata la FBS-V2 pe clusterul B: titlu
    IDENTIC, fara decoratie, postate una dupa alta."""
    rafala = [_canonic(str(i), title="iPhone15 Pro Max GB", price=300.0,
                       listed_at=_AWARE + timedelta(minutes=2 * i)) for i in (1, 2, 3)]
    genuine = [_canonic("10", title="iPhone 15 Pro Max 256GB impecabil", price=4800.0,
                        listed_at=_AWARE - timedelta(hours=5)),
               _canonic("11", title="iPhone 15 Pro Max sigilat garantie", price=5200.0,
                        listed_at=_AWARE - timedelta(hours=9))]
    return rafala + genuine


def test_ferma_e_aruncata_raman_doar_genuinele(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend(_feed_cu_ferma())

    rez = fb.search_facebook("iphone 15 pro max", max_price=100000)

    assert {r["external_id"] for r in rez} == {"fb_10", "fb_11"}


def test_garda_fb_ferma_zero_opreste_detectorul(monkeypatch, nucleu):
    """Intrerupatorul de avarie (D3): rollback fara cod si fara commit."""
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setenv("FB_FERMA", "0")
    nucleu.raspuns.extend(_feed_cu_ferma())

    rez = fb.search_facebook("iphone 15 pro max", max_price=100000)

    assert len(rez) == 5, "cu garda stinsa trec toate, inclusiv rafala"


@pytest.mark.parametrize("valoare", ["1", "", "  ", "fals", "off"])
def test_garda_stinge_doar_pe_zero(monkeypatch, nucleu, valoare):
    """Orice ALTCEVA decat `0` lasa apararea PORNITA: o valoare gresit scrisa nu are
    voie sa stinga tacut filtrul."""
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setenv("FB_FERMA", valoare)
    nucleu.raspuns.extend(_feed_cu_ferma())

    assert len(fb.search_facebook("iphone 15 pro max", max_price=100000)) == 2


def test_clusterul_singur_nu_condamna_pe_calea_reala(monkeypatch, nucleu):
    """Regula in doua jumatati, verificata cap-coada: trei titluri identice DAR la ore
    distanta, fara decoratie si la pret normal, nu sunt o ferma."""
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([
        _canonic(str(i), title="Canapea extensibila bej", price=1000.0,
                 listed_at=_AWARE - timedelta(hours=5 * i)) for i in (1, 2, 3)])

    rez = fb.search_facebook("canapea", max_price=100000)

    assert len(rez) == 3


def test_jurnalul_de_ferma_da_cheia_numarul_motivele_si_intervalul(monkeypatch, nucleu, logs):
    """D2 — aruncam anunturi, deci trebuie sa ramana urma din care se reconstituie CE
    s-a aruncat si DE CE. Un contor singur n-ar fi de ajuns."""
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend(_feed_cu_ferma())

    fb.search_facebook("iphone 15 pro max", max_price=100000)

    linii = [m for niv, m in logs if niv == "INFO" and "amprenta de ferma" in m]
    assert len(linii) == 1, f"un singur emit de sinteza per apel, nu {len(linii)}"
    linie = linii[0]
    assert "3 anunturi aruncate" in linie
    assert '"iphone15 pro max gb" x3' in linie
    assert "cluster+rafala" in linie
    assert "300-300" in linie, "intervalul de pret al clusterului"

    # Contorul intra in sinteza existenta, o singura data — nu o a doua linie.
    assert any("2 rezultate" in m and "3 sarite ca ferma" in m
               for niv, m in logs if niv == "OK"), [m for _n, m in logs]


def test_fara_ferme_jurnalul_tace(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("1", title="Geaca de piele"))

    fb.search_facebook("geaca", max_price=1000)

    assert not [m for _n, m in logs if "amprenta de ferma" in m]
    assert not [m for _n, m in logs if "sarite ca ferma" in m]


def test_din_canonice_taie_exact_idurile_din_ferme_si_doar_pe_ele():
    """`_din_canonice` direct: `ferme` e o lista de condamnari, nu o euristica pe care
    functia s-o reevalueze."""
    canonice = [_canonic("1", title="Acelasi titlu"), _canonic("2", title="Acelasi titlu"),
                _canonic("3", title="Alt titlu")]

    rez = fb._din_canonice(canonice, "geaca", None, [], None, None,
                           ferme={"2": ["cluster+rafala"]})

    assert [r["external_id"] for r in rez] == ["fb_1", "fb_3"]


def test_din_canonice_cu_ferme_none_e_identic_cu_azi():
    """Garantia pentru bazin: fara `ferme`, acelasi input da acelasi output — inclusiv
    pe un feed care ESTE o ferma. `_search_bazin` nu paseaza nimic, deci trece pe aici."""
    canonice = _feed_cu_ferma()

    implicit = fb._din_canonice(canonice, "iphone 15 pro max", None, [], None, None)
    explicit = fb._din_canonice(canonice, "iphone 15 pro max", None, [], None, None,
                                ferme=None)

    assert implicit == explicit
    assert len(implicit) == 5, "fara `ferme`, nimic nu se arunca — nici macar rafala"


def test_bazinul_nu_paseaza_ferme(monkeypatch, nucleu):
    """Cablarea e in `_search_logout`, nu in `_din_canonice`: calea de bazin trebuie sa
    ajunga la formator FARA verdict de ferma, fiindca domeniul ei (acumulare peste
    tick-uri) nu e un feed."""
    apeluri = []
    monkeypatch.setenv("FB_MOD", "bazin")
    monkeypatch.setattr(fb, "_din_canonice", lambda *a, **k: apeluri.append(k) or [])

    fb.search_facebook("iphone 15 pro max", max_price=0, keyword_id=1234)

    # AMBELE asertiuni sunt necesare. Fara prima, testul ar trece si daca formatorul
    # n-ar fi chemat deloc — „niciun kwarg" si „niciun apel" arata identic altfel.
    assert len(apeluri) == 1, "calea de bazin trebuie sa ajunga la formator"
    assert "ferme" not in apeluri[0], apeluri


def test_dedup_pe_external_id(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    # Al treilea anunt e distantat in timp (FBS-9b): trei titluri identice in aceeasi
    # clipa ar fi o rafala si s-ar arunca, iar variabila masurata aici e dedup-ul pe id.
    # Duplicatul lui „7" ramane la aceeasi clipa — el CHIAR e acelasi anunt de doua ori.
    nucleu.raspuns.extend([_canonic("7"), _canonic("7"),
                           _canonic("8", listed_at=_AWARE + timedelta(hours=3))])

    rez = fb.search_facebook("geaca", max_price=1000)

    assert [r["external_id"] for r in rez] == ["fb_7", "fb_8"]


# ── 3. maparea ───────────────────────────────────────────────────────────────
def test_maparea_are_aceleasi_chei_ca_pe_sesiune(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("42", title="Geaca piele", price=300.0,
                                   currency="EUR", location="Cluj-Napoca"))

    r = fb.search_facebook("geaca", max_price=1000)[0]

    assert set(r) == {"external_id", "platform", "title", "price", "currency",
                      "condition", "location", "url", "images", "description",
                      "seller_name", "seller_id", "listed_at"}
    assert r["external_id"] == "fb_42"
    assert r["platform"] == "facebook"
    assert r["price"] == 300.0 and r["currency"] == "EUR"
    assert r["location"] == "Cluj-Napoca"
    assert r["url"] == "https://www.facebook.com/marketplace/item/42/"
    assert r["images"] == ["https://x.invalid/1.jpg"]
    assert r["condition"] is None and r["description"] is None
    # vanzatorul NU exista logat-out (masurat) — lipsa la sursa, nu esec de parsare
    assert r["seller_name"] is None and r["seller_id"] is None


def test_images_e_lista_goala_fara_poza(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("1", image_url=None))

    assert fb.search_facebook("geaca", max_price=1000)[0]["images"] == []


# ── 4. listed_at: naiv local, compatibil cu _too_old ─────────────────────────
def test_listed_at_devine_naiv_local_pastrand_momentul(monkeypatch, nucleu):
    """Nu hardcodam ora (testul trebuie sa treaca in orice fus): verificam
    PROPRIETATEA — varsta calculata in conventia naiv-locala e aceeasi cu varsta
    calculata in UTC."""
    monkeypatch.setenv("FB_MOD", "logout")
    aware = datetime.now(timezone.utc) - timedelta(hours=3)
    nucleu.raspuns.append(_canonic("1", listed_at=aware))

    r = fb.search_facebook("geaca", max_price=1000)[0]

    assert r["listed_at"].tzinfo is None, "conventia Radar/Auto e naiv LOCAL"
    varsta_naiva = datetime.now() - r["listed_at"]
    varsta_utc = datetime.now(timezone.utc) - aware
    assert abs((varsta_naiva - varsta_utc).total_seconds()) < 5


def test_listed_at_lipsa_ramane_none(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("1", listed_at=None))

    assert fb.search_facebook("geaca", max_price=1000)[0]["listed_at"] is None


def test_too_old_din_scanner_digera_rezultatul(monkeypatch, nucleu):
    """Compatibilitatea cu consumatorul REAL: `_too_old` face `datetime.now() - listed_at`
    cu now naiv — un datetime aware ar arunca TypeError acolo."""
    from app.utils.radar_scanner import _too_old

    monkeypatch.setenv("FB_MOD", "logout")
    vechi = datetime.now(timezone.utc) - timedelta(days=10)
    nucleu.raspuns.extend([_canonic("1", listed_at=vechi),
                           _canonic("2", listed_at=datetime.now(timezone.utc))])

    rez = fb.search_facebook("geaca", max_price=1000)

    assert _too_old(rez[0]["listed_at"], 7) is True
    assert _too_old(rez[1]["listed_at"], 7) is False


# ── ancora ───────────────────────────────────────────────────────────────────
def test_ancora_implicita_si_configurabila(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "logout")
    fb.search_facebook("geaca", max_price=1000)
    a = nucleu.apeluri[0]
    assert (a["lat"], a["lon"], a["city_page_id"]) == (44.4325, 26.1025, "114304211920174")

    monkeypatch.setenv("FB_RADAR_ANCORA", "iasi")
    fb.search_facebook("geaca", max_price=1000)
    b = nucleu.apeluri[1]
    assert (b["lat"], b["lon"]) == (47.1585, 27.6014) and b["city_page_id"] == "101882609853782"

    monkeypatch.setenv("FB_RADAR_ANCORA", "atlantida")
    fb.search_facebook("geaca", max_price=1000)
    assert (nucleu.apeluri[2]["lat"], nucleu.apeluri[2]["lon"]) == (44.4325, 26.1025)
    assert any("atlantida" in m for m in _warn(logs))


# ── 5. dispecerul de detaliu ─────────────────────────────────────────────────
def test_detaliul_pe_logout_merge_prin_nucleu_si_ignora_sesiunea(monkeypatch):
    primite = []
    monkeypatch.setenv("FB_MOD", "logout")
    monkeypatch.setattr(fb, "nucleu_fetch_detail",
                        lambda url: primite.append(url) or {"description": "d", "images": ["i"]})
    monkeypatch.setattr(fb, "is_facebook_session_valid",
                        lambda p: pytest.fail("calea logout nu are voie sa verifice sesiunea"))

    rez = fb.fetch_facebook_listing_detail("https://www.facebook.com/marketplace/item/1/",
                                           "sesiune-inexistenta.json")

    assert rez == {"description": "d", "images": ["i"]}
    assert primite == ["https://www.facebook.com/marketplace/item/1/"]


def test_detaliul_pe_sesiune_ramane_pe_corpul_vechi(monkeypatch):
    monkeypatch.setattr(fb, "nucleu_fetch_detail",
                        lambda url: pytest.fail("calea de sesiune nu are voie sa cheme nucleul"))
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)

    assert fb.fetch_facebook_listing_detail("https://x.invalid/1", "s.json") == {
        "description": None, "images": None}
