"""FB-6a — executorul, bazinul fb_pool si search-ul cu stare.

Totul OFFLINE: nucleul e inlocuit pe `executor.search_cu_stare`, iar clientul GraphQL
prin dubluri cu get/post. Nicio cerere reala.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.database import SessionLocal
from app.models.auto_keyword import AutoKeyword
from app.models.fb_pool import FbPoolListing
from app.models.fb_scan_state import FbScanState
from app.models.radar_keyword import RadarKeyword
from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword
from app.services.log_manager import log_manager
from app.scrapers.facebook import client as fb_client
from app.scrapers.facebook import executor as ex
from app.scrapers.facebook.client import StareCautare, search, search_cu_stare
from app.scrapers.facebook.graphql import cauta, cauta_cu_cod
from app.scrapers.facebook.planner import (
    FUS_LOCAL, ConfigPlanificator, Planificator, _FORMA_ORARA_IMPLICITA, _ca_utc,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _ceas_diurn() -> datetime:
    """Un moment cu multiplicator orar 1.00, ca bugetele sa fie deterministe.

    DE CE EXISTA: forma orara din `planner.py` taie bugetul in afara intervalului
    08:00-21:59 Europe/Bucharest. Asertiunile de buget din fisierul asta sunt scrise
    pentru multiplicatorul PLIN, deci fara fixare aceleasi teste treceau ziua si picau
    dupa ora 22 — o suita care depinde de cand e rulata. (Asa s-a si descoperit
    dublarea formei orare din frana, la FBS-9b.)

    NU e o constanta, si asta e deliberat: momentul ales e primul instant diurn de la
    `now()` INCOLO, deci ramane mereu la sau dupa ceasul real. Un ceas fixat in trecut
    ar face randurile programate cu `datetime.now()` de catre teste (vezi
    `test_anunturile_noi_numara_doar_inserturile`) sa para viitoare si le-ar scoate
    din selectia perechilor scadente, care merge pe `_acum()`-ul planificatorului.

    Ora se cauta prin CHIAR tabelul de forma orara al planificatorului, nu printr-un
    interval copiat aici: daca dimensionarea se schimba, ceasul testelor o urmeaza.
    """
    t = datetime.now(timezone.utc)
    for _ in range(24):
        ora = t.astimezone(ZoneInfo(FUS_LOCAL)).hour
        if _FORMA_ORARA_IMPLICITA.get(ora, 1.0) == 1.0:
            return t
        t += timedelta(hours=1)
    raise AssertionError("forma orara nu are nicio ora cu multiplicator 1.00")


def _fix(nume):
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def uid(db):
    """Keyword-urile au FK pe users.id, iar `clean_db` goleste tot inainte de test."""
    from app.models.user import User
    u = User(email="fb6a@example.com", username="fb6a", hashed_password="x",
             is_active=True)
    db.add(u)
    db.commit()
    return u.id


@pytest.fixture(autouse=True)
def _izolare(monkeypatch, tmp_path):
    """DATA_DIR spre tmp_path (cache de bootstrap) si starea de modul a executorului
    resetata intre teste — `_planificator` si `_ultimul_tick` sunt globale."""
    from app import config
    from app.scrapers.facebook import bootstrap as fb_bootstrap
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fb_bootstrap._memo = None
    ex._planificator = None
    ex._ultimul_tick = None
    ex._tickuri_fara_ok = 0
    ex._reseteaza_cooldown()
    for v in ("FB_POOL_TTL_ORE", "FB_BUGET_PER_TICK", "FB_FRANA",
              "FB_SESIUNE_PATH", "FB_COOLDOWN_ORE"):
        monkeypatch.delenv(v, raising=False)
    yield
    ex._planificator = None
    ex._ultimul_tick = None
    ex._tickuri_fara_ok = 0
    ex._reseteaza_cooldown()


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: capturate.append((nivel, mesaj)))
    return capturate


def _canonic(ext, *, price=100.0, title="Anunt", category_id=None, listed_at=None):
    return {"external_id": str(ext), "title": title, "price": price, "currency": "RON",
            "location": "București", "image_url": "https://x.invalid/1.jpg",
            "listed_at": listed_at, "category_id": category_id,
            "source_url": f"https://www.facebook.com/marketplace/item/{ext}/"}


class ClientFals:
    """Dublu de transport pentru scara din client.py."""

    def __init__(self, rute=None, post_rezultate=None, blocat=False):
        self.rute = rute or {}
        self.post_rezultate = list(post_rezultate or [])
        self.blocat = blocat
        self.cereri = []

    def get(self, url):
        self.cereri.append(("get", url))
        for fragment, rezultat in self.rute.items():
            if fragment in url:
                return rezultat
        return "", 404

    def post(self, url, data=None, headers=None):
        self.cereri.append(("post", url))
        return self.post_rezultate.pop(0) if self.post_rezultate else ("", 500)


# ── 1-2. graphql: propagarea codului ─────────────────────────────────────────
def test_cauta_cu_cod_propaga_codul_de_resolver():
    corp = json.dumps({"errors": [{"message": "Rate limit exceeded",
                                   "severity": "CRITICAL", "code": 1675004}]})
    cl = ClientFals(post_rezultate=[(corp, 200)])
    boot = type("B", (), {"friendly_name": "Q", "doc_id": "1", "lsd": "l"})()

    raspuns, cod = cauta_cu_cod(cl, boot, {})

    assert raspuns is None
    assert cod == 1675004


def test_cauta_invelisul_ramane_neschimbat():
    """Treapta 2 din client depinde de `cauta` intorcand None — nu se schimba."""
    corp = _fix("fb_graphql_eroare.json")      # codul real din fixture: 1675012
    cl = ClientFals(post_rezultate=[(corp, 200)])
    boot = type("B", (), {"friendly_name": "Q", "doc_id": "1", "lsd": "l"})()

    assert cauta(cl, boot, {}) is None

    cl2 = ClientFals(post_rezultate=[(corp, 200)])
    assert cauta_cu_cod(cl2, boot, {})[1] == 1675012


# ── 3-6. client: search_cu_stare ─────────────────────────────────────────────
def _client_cu_bootstrap(post_rezultate):
    from app.scrapers.facebook.bootstrap import URL_SEARCH
    return ClientFals(rute={URL_SEARCH: (_fix("fb_ssr_search.html"), 200)},
                      post_rezultate=post_rezultate)


def test_stare_ok_pe_raspuns_valid():
    cl = _client_cu_bootstrap([(_fix("fb_graphql_ok.json"), 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert len(canonice) == 24
    assert stare.eticheta == "ok" and stare.cod is None
    # FBS-2: GraphQL e treapta 2, fiindca ancora asta n-are `city_page_id`
    assert stare.trepte_incercate == 2


def test_stare_gol_pe_raspuns_valid_fara_anunturi():
    """`edges: []` = locul chiar e gol; NU e esec, deci scara nu coboara."""
    cl = _client_cu_bootstrap([(_fix("fb_graphql_pagina2.json"), 200)])

    canonice, stare = search_cu_stare("cevacenuexista", 44.43, 26.10, client=cl)

    assert canonice == []
    assert stare.eticheta == "gol" and stare.trepte_incercate == 2


def test_stare_blocat_pe_403(monkeypatch):
    """Zavorul de 403/429 e dovada dura de refuz."""
    from app.scrapers.facebook.client import FacebookClient

    class Sesiune403:
        class _C:
            def clear(self):
                pass
        cookies = _C()

        def get(self, url, **kw):
            return type("R", (), {"status_code": 403, "text": "blocat"})()
        post = get

    monkeypatch.setattr(fb_client, "report_outcome", lambda *a: True)
    cl = FacebookClient(sleep=lambda s: None)
    cl._sesiune = Sesiune403()

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert canonice == []
    assert stare.eticheta == "blocat"
    assert cl.blocat is True


def test_stare_blocat_pe_codul_de_refuz_acces():
    corp = json.dumps({"errors": [{"message": "Rate limit exceeded", "code": 1675004}]})
    cl = _client_cu_bootstrap([(corp, 200), (corp, 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert stare.eticheta == "blocat" and stare.cod == 1675004


def test_stare_esec_si_paritatea_invelisului(monkeypatch):
    """Toate treptele pica FARA dovada de blocaj (sablon invechit). `search` clasic
    intoarce lista goala pe acelasi dublu — invelisul nu schimba nimic."""
    monkeypatch.setattr(fb_client, "report_outcome", lambda *a: True)
    corp = _fix("fb_graphql_eroare.json")      # 1675012 = sablon invechit
    cl = _client_cu_bootstrap([(corp, 200), (corp, 200)])

    canonice, stare = search_cu_stare("canapea", 44.43, 26.10, client=cl)

    assert canonice == []
    assert stare.eticheta == "esec" and stare.trepte_incercate == 4
    assert stare.cod == 1675012

    cl2 = _client_cu_bootstrap([(corp, 200), (corp, 200)])
    assert search("canapea", 44.43, 26.10, client=cl2) == []


# ── 7-9. bazinul ─────────────────────────────────────────────────────────────
def test_bazinul_insereaza_cu_metadate(db):
    acum = datetime.now(timezone.utc)
    noi = ex._scrie_in_bazin(db, "radar", 1, "cluj-napoca",
                             [_canonic("100", listed_at=acum)])

    assert noi == 1
    r = db.query(FbPoolListing).one()
    assert (r.modul, r.keyword_id, r.external_id, r.ancora) == \
        ("radar", 1, "100", "cluj-napoca")
    assert r.prima_vedere_at is not None and r.ultima_vedere_at is not None
    assert r.listed_at == acum.isoformat(), "ISO cu offset, nu datetime"


def test_revederea_actualizeaza_fara_sa_dubleze(db):
    ex._scrie_in_bazin(db, "radar", 1, "bucuresti", [_canonic("100", price=100.0)])
    prima = db.query(FbPoolListing).one().prima_vedere_at

    noi = ex._scrie_in_bazin(db, "radar", 1, "cluj-napoca", [_canonic("100", price=90.0)])

    assert noi == 0, "re-vederea nu e un anunt nou"
    randuri = db.query(FbPoolListing).all()
    assert len(randuri) == 1, "constrangerea unica tine"
    assert randuri[0].price == 90.0, "pretul se poate misca"
    assert randuri[0].prima_vedere_at == prima
    assert randuri[0].ancora == "bucuresti", "ancora primei vederi nu se rescrie"


def test_curatenia_ttl_sterge_doar_expiratele(db, monkeypatch):
    monkeypatch.setenv("FB_POOL_TTL_ORE", "48")
    vechi = datetime.now(timezone.utc) - timedelta(hours=72)
    proaspat = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(FbPoolListing(modul="radar", keyword_id=1, external_id="vechi",
                         ancora="bucuresti", prima_vedere_at=vechi, ultima_vedere_at=vechi))
    db.add(FbPoolListing(modul="radar", keyword_id=1, external_id="nou",
                         ancora="bucuresti", prima_vedere_at=proaspat,
                         ultima_vedere_at=proaspat))
    db.commit()

    sterse = ex._curata_bazinul(db)

    assert sterse == 1
    assert [r.external_id for r in db.query(FbPoolListing)] == ["nou"]


# ── 10-15. executorul ────────────────────────────────────────────────────────
def _mock_nucleu(monkeypatch, per_termen=None, implicit=None, blocat_la=None):
    """Inlocuieste `search_cu_stare` in executor. `blocat_la` = termenul care da blocat.

    FBS-7: dublul poarta si `pret_min`, FBS-10 si `pret_max`, ca semnatura reala.
    Marginile se strang in `praguri` si `plafoane`, liste PARALELE cu `apeluri`
    (acelasi indice = acelasi apel), nu in `apeluri` sub forma de tupluri: asa
    asserturile existente pe `apeluri` raman neatinse, iar marginile raman
    verificabile.
    """
    apeluri = []
    praguri = []
    plafoane = []

    def fals(termen, lat, lon, *, raza_km=65, city_page_id=None, pret_min=None,
             pret_max=None):
        apeluri.append(termen)
        praguri.append(pret_min)
        plafoane.append(pret_max)
        if blocat_la is not None and termen == blocat_la:
            return [], StareCautare("blocat", 1675004, 1)
        canonice = (per_termen or {}).get(termen, implicit or [])
        return list(canonice), StareCautare("ok" if canonice else "gol", None, 1)

    monkeypatch.setattr(ex, "search_cu_stare", fals)
    fals.apeluri = apeluri
    fals.praguri = praguri
    fals.plafoane = plafoane
    return fals


def _keyword_radar(db, uid, nume="geaca", platform="facebook", platforms=None,
                   activ=True, min_price=None, max_price=1000.0):
    # `max_price` a devenit parametru la FBS-10 (era fixat la 1000.0): coloana e
    # `nullable=False`, deci trebuie sa aiba mereu o valoare, dar acum plafonul chiar
    # pleaca server-side si testele au nevoie sa-l poata varia. Implicitul e cel de
    # dinainte, deci toate apelurile existente raman neschimbate.
    kw = RadarKeyword(name=nume, user_id=uid, is_active=activ, platform=platform,
                      platforms=platforms or '["olx"]',
                      max_price=max_price, resale_price=1500.0, min_price=min_price)
    db.add(kw)
    db.commit()
    return kw


def _pregateste(db, keywords, buget, scadente):
    """Creeaza perechile ca tick-ul (scope `national`) si lasa SCADENTE doar cele cerute.

    `tick` sincronizeaza singur cu scope `national`, deci fiecare keyword primeste 51
    de perechi. Fara controlul asta, ce anume e scadent ar depinde de ordinea din
    registru — testele trebuie sa fie deterministe, nu norocoase.
    `scadente` = lista de (modul, keyword_id) in ORDINEA dorita de executie.
    """
    # Ceas FIXAT (vezi `_ceas_diurn`): selectia perechilor scadente si forma orara
    # merg amandoua pe `_acum()`-ul planificatorului, deci si scadentele de mai jos se
    # ancoreaza in ACELASI moment — altfel ar fi doua ceasuri intr-un singur test.
    acum = _ceas_diurn()
    p = Planificator(db, ConfigPlanificator(buget_per_tick=buget), acum=lambda: acum)
    for modul, kid in keywords:
        p.asigura_perechi(modul, kid, "national")

    viitor = acum + timedelta(days=1)
    db.query(FbScanState).update({FbScanState.next_due_at: viitor},
                                 synchronize_session=False)
    db.commit()

    alese = []
    for i, (modul, kid) in enumerate(scadente):
        r = (db.query(FbScanState)
             .filter(FbScanState.modul == modul, FbScanState.keyword_id == kid)
             .order_by(FbScanState.id).first())
        # intarziere descrescatoare -> ordinea din `scadente` e ordinea de executie
        r.next_due_at = acum - timedelta(minutes=100 - i)
        alese.append(r)
    db.commit()
    ex._planificator = p
    return p, alese


def _keyword_auto(db, uid, **kw):
    kw.setdefault("name", "auto-kw")
    obj = AutoKeyword(user_id=uid, **kw)
    db.add(obj)
    return obj


def _keyword_re(db, uid, **kw):
    kw.setdefault("name", "re-kw")
    obj = RealEstateMonitorKeyword(user_id=uid, **kw)
    db.add(obj)
    return obj


def test_sincronizarea_prinde_doar_keywordurile_de_facebook(db, uid, monkeypatch):
    _mock_nucleu(monkeypatch, implicit=[])
    _keyword_radar(db, uid, "cu-platform", platform="facebook")
    _keyword_radar(db, uid, "cu-platforms", platform=None, platforms='["olx","facebook"]')
    _keyword_radar(db, uid, "alta-platforma", platform="olx")
    _keyword_radar(db, uid, "inactiv", platform="facebook", activ=False)
    _keyword_auto(db, uid, platform="facebook_auto", make="BMW", model="320d", is_active=True)
    _keyword_auto(db, uid, platform="autovit", make="Audi", is_active=True)
    _keyword_re(db, uid, platform="facebook_marketplace", query="", is_active=True)
    _keyword_re(db, uid, platform="olx", query="x", is_active=True)
    db.commit()

    intrari = ex._keywords_facebook(db)

    module = sorted((i["modul"], len(i["termeni"])) for i in intrari)
    assert module == [("auto", 1), ("radar", 1), ("radar", 1), ("real_estate", 8)], intrari
    auto = next(i for i in intrari if i["modul"] == "auto")
    assert auto["termeni"] == ["BMW 320d"], "termenul se construieste ca in scanner"


def test_bugetul_se_numara_in_cereri_nu_in_perechi(db, uid, monkeypatch):
    """O pereche imobiliara goala costa 8 cereri. Cu buget 12: 8 + 4 x 1, apoi stop."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    re_kw = _keyword_re(db, uid, platform="facebook_marketplace", query="", is_active=True)
    radare = [_keyword_radar(db, uid, f"kw{i}", platform="facebook") for i in range(10)]
    db.commit()

    _pregateste(db, [("real_estate", re_kw.id)] + [("radar", k.id) for k in radare],
                buget=12,
                scadente=[("real_estate", re_kw.id)] + [("radar", k.id) for k in radare])
    sumar = ex.tick(db)

    assert sumar["cereri"] == 12, sumar
    assert len(nucleu.apeluri) == 12
    assert sumar["executate"] == 5, "perechea de 8 termeni + patru de cate 1"


def test_bugetul_nu_se_depaseste_cand_perechea_scumpa_vine_la_final(db, uid, monkeypatch):
    """Proprietatea care CHIAR apara bugetul: o pereche de 8 termeni intalnita dupa ce
    s-au consumat deja 5 cereri NU se porneste, fiindca 5+8 > 12. Daca s-ar contoriza
    perechi (cost 1), executorul ar porni-o si ar trimite 13 cereri — adica ar depasi
    tacut bugetul, exact ce frana incearca sa previna."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    radare = [_keyword_radar(db, uid, f"r{i}", platform="facebook") for i in range(5)]
    re_kw = _keyword_re(db, uid, platform="facebook_marketplace", query="", is_active=True)
    db.commit()

    perechi = [("radar", k.id) for k in radare] + [("real_estate", re_kw.id)]
    _pregateste(db, perechi, buget=12, scadente=perechi)
    sumar = ex.tick(db)

    assert sumar["cereri"] <= 12, f"buget depasit: {sumar}"
    assert sumar["cereri"] == 5, sumar
    assert sumar["executate"] == 5, "perechea scumpa ramane pentru tick-ul urmator"
    assert len(nucleu.apeluri) == 5


def test_prima_pereche_se_executa_chiar_daca_depaseste_bugetul(db, uid, monkeypatch):
    """Altfel un buget taiat de frana la 1 ar infometa pe veci keyword-ul gol."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    re_kw = _keyword_re(db, uid, platform="facebook_marketplace", query="", is_active=True)
    db.commit()

    _pregateste(db, [("real_estate", re_kw.id)], buget=1,
                scadente=[("real_estate", re_kw.id)])
    sumar = ex.tick(db)

    assert sumar["executate"] == 1
    assert sumar["cereri"] == 8, "toti cei 8 termeni ai perechii"


def test_blocajul_opreste_tickul_si_trage_frana(db, uid, monkeypatch):
    k1 = _keyword_radar(db, uid, "unu", platform="facebook")
    k2 = _keyword_radar(db, uid, "doi", platform="facebook")
    k3 = _keyword_radar(db, uid, "trei", platform="facebook")
    nucleu = _mock_nucleu(monkeypatch, implicit=[], blocat_la="unu")

    p, alese = _pregateste(db, [("radar", k.id) for k in (k1, k2, k3)], buget=12,
                           scadente=[("radar", k.id) for k in (k1, k2, k3)])
    inainte = p.buget_efectiv()
    sumar = ex.tick(db)

    assert sumar["blocaj"] is True
    assert sumar["executate"] == 1, "perechile ramase nu se mai executa"
    assert nucleu.apeluri == ["unu"]
    assert p.stare_frana()["buget_efectiv"] == inainte // 2
    db.refresh(alese[0])
    assert alese[0].last_run_at is not None, "perechea blocata are rezultat inregistrat"


# ── FB-FRANA-1: frana taie BRUT, forma orara se aplica o singura data ────────
# Testele astea stau langa cele de executor fiindca aici e si ceasul fixat, si tot
# aici a iesit la iveala defectul (doua picari dependente de ora, la FBS-9b).
def _ceas_la_ora_locala(ora: int) -> datetime:
    """Moment UTC care cade la `ora` pe fusul romanesc. Data e fixa, deci si DST-ul."""
    return datetime(2026, 8, 20, ora, 0,
                    tzinfo=ZoneInfo(FUS_LOCAL)).astimezone(timezone.utc)


def _planificator_la(ora_locala: int, buget: int = 12):
    """Planificator cu ceas fixat la o ora LOCALA data. Fara DB: nimic de aici nu
    atinge perechile, doar aritmetica franei. Intoarce si ceasul, ca sa poata fi mutat."""
    ceas = [_ceas_la_ora_locala(ora_locala)]
    p = Planificator(None, ConfigPlanificator(buget_per_tick=buget),
                     acum=lambda: ceas[0])
    return p, ceas


def test_frana_injumatateste_brutul_nu_valoarea_modelata_orar():
    """Regresia rundei. La 22:00 local multiplicatorul e 0.75, deci brutul 12 devine 6
    si abia apoi se modeleaza: int(6 x 0.75) = 4.

    Varianta veche injumatatea EFECTIVUL (int(12 x 0.75) = 9 -> 4), depozita 4 ca si
    cum ar fi brut si-l modela A DOUA oara la citire: int(4 x 0.75) = 3. Sub jumatate,
    si invizibil ziua, cand multiplicatorul e 1.00."""
    p, _ = _planificator_la(22)
    assert p.multiplicator_orar() == pytest.approx(0.75)
    assert p.buget_efectiv() == 9, "doar forma orara, inainte de orice semnal"

    assert p.semnal_blocaj() == 6, "jumatate din BRUT, nu din efectiv"

    assert p.buget_efectiv() == 4, "int(6 x 0.75) — forma orara aplicata O SINGURA data"


def test_semnalele_succesive_se_compun_in_spatiul_brut():
    """Compunerea ramane cea documentata: brut 12, doua semnale, 6 apoi 3."""
    p, _ = _planificator_la(22)

    assert [p.semnal_blocaj(), p.semnal_blocaj()] == [6, 3]
    assert p.buget_efectiv() == 2, "int(3 x 0.75)"


def test_revenirea_pe_trepte_lucreaza_tot_in_brut():
    """Treptele se aduna peste `_buget_redus` INAINTE de modelare, consecvent cu el.

    Ora aleasa e 03:00 local (x0.33), iar avansul de 60 min ramane in acelasi interval
    (00:00-05:59), deci multiplicatorul NU se schimba si diferenta masurata e strict a
    treptelor — nu a trecerii dintr-o treapta orara in alta."""
    p, ceas = _planificator_la(3)
    assert p.semnal_blocaj() == 6
    assert p.buget_efectiv() == 1, "int(6 x 0.33) = 1"

    ceas[0] += timedelta(minutes=60)          # doua ferestre de revenire a 30 min

    assert p.multiplicator_orar() == pytest.approx(0.33), "acelasi interval orar"
    assert p._baza_bruta() == 8, "6 + 2 trepte, in BRUT"
    assert p.buget_efectiv() == 2, "int(8 x 0.33), o singura modelare"


def test_ziua_reparatia_nu_schimba_nimic():
    """Garda de non-regresie: la multiplicator 1.00 brut si efectiv coincid, deci
    comportamentul de dinainte de runda ramane bit cu bit acelasi."""
    p, _ = _planificator_la(12)

    assert p.buget_efectiv() == 12
    assert [p.semnal_blocaj(), p.semnal_blocaj(), p.semnal_blocaj()] == [6, 3, 1]
    assert p.semnal_blocaj() == 1, "podeaua"
    assert p.buget_efectiv() == 1


def test_perechea_fara_keyword_activ_se_reprogrameaza_fara_adaptare(db, uid, monkeypatch):
    _mock_nucleu(monkeypatch, implicit=[])
    kw = _keyword_radar(db, uid, "dispare", platform="facebook")
    _, alese = _pregateste(db, [("radar", kw.id)], buget=12,
                           scadente=[("radar", kw.id)])
    pereche = alese[0]
    interval_initial = pereche.interval_min

    kw.is_active = False          # keyword-ul dispare intre tick-uri
    db.commit()
    sumar = ex.tick(db)

    db.refresh(pereche)
    assert sumar["sarite"] >= 1 and sumar["executate"] == 0
    assert pereche.interval_min == interval_initial, "intervalul NU se adapteaza"
    assert pereche.last_run_at is None, "nu s-a masurat nimic"
    assert _ca_utc(pereche.next_due_at) > datetime.now(timezone.utc)


def test_anunturile_noi_numara_doar_inserturile(db, uid, monkeypatch):
    kw = _keyword_radar(db, uid, "geaca", platform="facebook")
    canonice = [_canonic("1"), _canonic("2")]
    _mock_nucleu(monkeypatch, implicit=canonice)

    _, alese = _pregateste(db, [("radar", kw.id)], buget=1, scadente=[("radar", kw.id)])
    pereche = alese[0]
    s1 = ex.tick(db)
    db.refresh(pereche)
    interval_dupa_primul = pereche.interval_min

    # al doilea tick pe ACELEASI anunturi: zero noi -> rata 0 -> intervalul creste
    pereche.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    s2 = ex.tick(db)
    db.refresh(pereche)

    assert s1["anunturi_noi"] == 2
    assert s2["anunturi_noi"] == 0
    assert pereche.interval_min > interval_dupa_primul, "rata mica -> interval mai mare"
    assert db.query(FbPoolListing).count() == 2


# ── 16. diagnosticul ─────────────────────────────────────────────────────────
def test_endpointul_de_diagnostic(auth_client, db, monkeypatch):
    r = auth_client.get("/api/radar/facebook/planner-status")

    assert r.status_code == 200
    date = r.json()
    assert set(date) >= {"frana", "perechi", "bazin", "ultimul_tick"}
    assert date["bazin"]["total"] == 0
    assert date["ultimul_tick"] is None


def test_stare_executor_dupa_un_tick(db, uid, monkeypatch):
    kw = _keyword_radar(db, uid, "geaca", platform="facebook")
    _mock_nucleu(monkeypatch, implicit=[_canonic("1")])
    _pregateste(db, [("radar", kw.id)], buget=3, scadente=[("radar", kw.id)])
    ex.tick(db)

    stare = ex.stare_executor(db)

    assert stare["activ"] is True
    assert stare["bazin"]["total"] == 1
    assert stare["ultimul_tick"]["executate"] == 1
    assert stare["frana"]["buget_configurat"] == 3


def test_tickurile_suprapuse_se_sar(db):
    ex._lock.acquire()
    try:
        sumar = ex.tick(db)
    finally:
        ex._lock.release()

    assert sumar == {"sarit": "tick suprapus"}


# ── FBS-7: pragul de pret al keyword-ului, pana la treapta 1 ─────────────────
@pytest.mark.parametrize("min_price,asteptat", [
    (3000.0, 3000),      # cazul normal
    (2999.9, 2999),      # trunchiere prin `int`, ca la FBS-6
    (None, None),        # necompletat
    (0, None),           # zero inseamna „fara prag", nu „prag zero"
    (-5, None),          # negativ, la fel
])
def test_pragul_radar_se_normalizeaza_ca_la_fbs6(db, uid, min_price, asteptat):
    _keyword_radar(db, uid, "geaca", platform="facebook", min_price=min_price)
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [i["pret_min"] for i in intrari] == [asteptat]


def test_imobiliarele_nu_trimit_prag_desi_au_price_min(db, uid):
    """D3 — AMANAT pe moneda, si asta e comportament TESTAT, nu doar comentat:
    `price_min` e in EUR pe `price_currency`, iar `minPrice` e RON. O regresie care
    l-ar cabla „ca la Radar" ar taia la ~5x pragul real, tacut."""
    _keyword_re(db, uid, platform="facebook_marketplace", query="apartament",
                is_active=True, price_min=250, price_currency="EUR")
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [i["modul"] for i in intrari] == ["real_estate"]
    assert intrari[0]["pret_min"] is None


def test_autoul_nu_trimite_prag(db, uid):
    """D2 — `AutoKeyword` n-are camp de pret minim; cheia exista si e `None`."""
    _keyword_auto(db, uid, platform="facebook_auto", make="BMW", model="320d",
                  is_active=True)
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [(i["modul"], i["pret_min"]) for i in intrari] == [("auto", None)]


def test_pragul_ajunge_in_apelul_nucleului(db, uid, monkeypatch):
    """Contra-proba de capat: pragul din keyword chiar ajunge la `search_cu_stare`.
    Fara asta, cablarea ar putea fi corecta pana la dictul de keyword si pierduta
    exact in bucla care conteaza."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    k = _keyword_radar(db, uid, "iphone", platform="facebook", min_price=1500.0)
    db.commit()

    _pregateste(db, [("radar", k.id)], buget=1, scadente=[("radar", k.id)])
    ex.tick(db)

    assert nucleu.apeluri == ["iphone"]
    assert nucleu.praguri == [1500]


def test_keywordul_fara_prag_cheama_nucleul_cu_none(db, uid, monkeypatch):
    """Contra-proba: fara prag NU se trimite un prag inventat (0 ar fi ajuns in URL
    daca normalizarea ar fi lipsit)."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    k = _keyword_radar(db, uid, "geaca", platform="facebook", min_price=None)
    db.commit()

    _pregateste(db, [("radar", k.id)], buget=1, scadente=[("radar", k.id)])
    ex.tick(db)

    assert nucleu.apeluri == ["geaca"]
    assert nucleu.praguri == [None]


# ── FBS-10: plafonul, simetricul pragului ────────────────────────────────────
# ASIMETRIE REALA fata de prag, de stiut: `RadarKeyword.min_price` e nullable, dar
# `max_price` e `nullable=False` — deci pe Radar plafonul NU poate fi NULL, iar cazul
# „necompletat" se exprima prin 0, nu prin None. Normalizarea trateaza si None (poate
# veni pe alte cai, si garda `kw.max_price and ...` nu are voie sa presupuna), dar acolo
# se testeaza: `test_radarul_fara_plafon_nu_trimite_niciun_plafon` din test_fb_ssr_id.py
# il acopera direct pe `_search_logout`, unde chiar e accesibil.
@pytest.mark.parametrize("max_price,asteptat", [
    (8000.0, 8000),      # normal
    (2999.9, 2999),      # trunchiere prin `int`, ca la prag
    (0, None),           # zero inseamna „fara plafon", nu „plafon zero"
    (-5, None),          # negativ, la fel
])
def test_plafonul_radar_se_normalizeaza_ca_pragul(db, uid, max_price, asteptat):
    _keyword_radar(db, uid, "geaca", platform="facebook", max_price=max_price)
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [i["pret_max"] for i in intrari] == [asteptat]


def test_autoul_nu_trimite_plafon_desi_ARE_price_max(db, uid):
    """D4 — amanare pe MONEDA, si e comportament TESTAT, nu doar comentat.

    Spre deosebire de prag (unde Auto pur si simplu n-are camp), plafonul EXISTA:
    `price_max`. Dar exista si `price_currency`, implicit EUR, iar piata auto chiar se
    listeaza frecvent in EUR. Un `maxPrice` care e RON, alimentat dintr-o valoare EUR,
    ar taia la ~5x sub plafonul real — tacut. De-aia keyword-ul de aici ARE `price_max`
    setat: testul ar trece si daca ramura ar fi goala, dar atunci n-ar dovedi nimic."""
    _keyword_auto(db, uid, platform="facebook_auto", make="BMW", model="320d",
                  is_active=True, price_max=25000, price_currency="EUR")
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [(i["modul"], i["pret_max"]) for i in intrari] == [("auto", None)]


def test_imobiliarele_nu_trimit_plafon(db, uid):
    _keyword_re(db, uid, platform="facebook_marketplace", query="apartament",
                is_active=True, price_max=800, price_currency="EUR")
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert [(i["modul"], i["pret_max"]) for i in intrari] == [("real_estate", None)]


def test_cheia_pret_max_exista_pe_toate_ramurile(db, uid):
    """Forma uniforma de dict: `tick` citeste `k["pret_max"]` DIRECT, fara `get` cu
    implicit. Un modul adaugat mai tarziu si uitat aici trebuie sa crape zgomotos, nu
    sa scaneze tacit fara plafon."""
    _keyword_radar(db, uid, "geaca", platform="facebook")
    _keyword_auto(db, uid, platform="facebook_auto", make="BMW", is_active=True)
    _keyword_re(db, uid, platform="facebook_marketplace", query="apartament",
                is_active=True)
    db.commit()

    intrari = ex._keywords_facebook(db)

    assert len(intrari) == 3
    assert all("pret_max" in i for i in intrari), intrari


def test_plafonul_ajunge_in_apelul_nucleului(db, uid, monkeypatch):
    """Contra-proba de capat, ca la prag: plafonul din keyword chiar ajunge la
    `search_cu_stare`, nu se pierde in bucla care conteaza."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    k = _keyword_radar(db, uid, "iphone", platform="facebook", max_price=6000.0)
    db.commit()

    _pregateste(db, [("radar", k.id)], buget=1, scadente=[("radar", k.id)])
    ex.tick(db)

    assert nucleu.apeluri == ["iphone"]
    assert nucleu.plafoane == [6000]


def test_keywordul_fara_plafon_cheama_nucleul_cu_none(db, uid, monkeypatch):
    """„Fara plafon" pe Radar inseamna 0, nu NULL — coloana e `nullable=False`."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    k = _keyword_radar(db, uid, "geaca", platform="facebook", max_price=0)
    db.commit()

    _pregateste(db, [("radar", k.id)], buget=1, scadente=[("radar", k.id)])
    ex.tick(db)

    assert nucleu.plafoane == [None]


def test_ambele_margini_ajung_impreuna_la_nucleu(db, uid, monkeypatch):
    """Forma completa pe care o trimite productia dupa FBS-10 — cea masurata la FBS-V3."""
    nucleu = _mock_nucleu(monkeypatch, implicit=[])
    k = _keyword_radar(db, uid, "iphone", platform="facebook",
                       min_price=1245.0, max_price=1588.0)
    db.commit()

    _pregateste(db, [("radar", k.id)], buget=1, scadente=[("radar", k.id)])
    ex.tick(db)

    assert (nucleu.praguri, nucleu.plafoane) == ([1245], [1588])
