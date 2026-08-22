"""VAL D / RUNDA 3 — `api_enum`, scannerul API de catalog VTEX (primul domeniu: f64.ro).

Toate testele sunt OFFLINE: fetch-ul e monkeypatch-uit peste tot, ZERO retea
(doctrina BNR-1c). Fixture-urile NU sunt inventate — sunt raspunsuri REALE,
copiate verbatim din sondele VTX:

  f64.ro_fereastra50.json     dumps_vtx3/C2_fereastra_contra.json  (206, 50 produse,
                              `resources: 2450-2499/52542` — o fereastra PLINA)
  f64.ro_segment.json         dumps_vtx1c/f64.ro_api_fq.json       (206, 10 produse,
                              segment `fq=C:1000003`, `resources: 0-9/1164`)
  f64.ro_gol.json             dumps_vtx3/C3_nivel3.json            (200 + `[]` —
                              dovada ca 2xx include si 200, nu doar 206)
  f64.ro_eroare_fereastra.json dumps_vtx3/C1_fereastra_dif50.json  (400, corpul
                              "Parameter _to can't be greater than 50.")
  f64.ro_tree.json            dumps_vtx1c/f64.ro_tree.json         (arborele intreg:
                              41 noduri de nivel 1, 179 de nivel 2, 329 de nivel 3)
"""
import io
import json
import os
import uuid

import pytest

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.models.user import User
from app.services import api_scanner
from app.services.deal_scanner import _evalueaza
from app.services.api_scanner import (
    _e_2xx, _extrage_produse, _external_id, _fereastra, _parse_resources,
)
from app.services.shop_registry import catalog_api_descriptor, catalog_api_domains

FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "api")

DOM = "f64.ro"


def _fixture(nume: str) -> str:
    with io.open(os.path.join(FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


def _json(nume: str):
    return json.loads(_fixture(nume))


class _Raspuns:
    def __init__(self, corp, status=206, resources=None):
        self.status_code = status
        self.text = corp
        self.headers = {"resources": resources} if resources else {}


def _seteaza(db, **campuri):
    email = f"api_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x",
             is_active=True)
    db.add(u)
    db.flush()
    s = RadarSettings(user_id=u.id, **campuri)
    db.add(s)
    db.commit()
    return s


# ── 1. Fereastra: EXACT 50 de elemente ───────────────────────────────────────

@pytest.mark.parametrize("de_la,pana_la", [(0, 49), (50, 99), (2450, 2499), (2500, 2549)])
def test_fereastra_are_exact_50_de_elemente(de_la, pana_la):
    """VTX-3 a masurat granita: `_from=2450&_to=2500` (51 elemente) da 400 cu
    „Parameter _to can't be greater than 50.", iar `_to=2499` (50 elemente) da 206
    cu fix 50 de produse. Deci plafonul e pe NUMARUL DE ELEMENTE, nu pe valoarea
    lui `_to` — un `_to` de 2499 a trecut."""
    assert _fereastra(de_la) == pana_la
    assert pana_la - de_la + 1 == 50


def test_corpul_de_eroare_al_ferestrei_e_cel_masurat():
    """Pinuieste mesajul pe care se sprijina interpretarea de mai sus."""
    assert _fixture("f64.ro_eroare_fereastra.json").strip() == (
        '"Parameter _to can\'t be greater than 50."')


# ── 2. 2xx include 206 SI 200 ────────────────────────────────────────────────

@pytest.mark.parametrize("status,ok", [(200, True), (206, True), (204, True),
                                       (400, False), (403, False), (500, False),
                                       (301, False)])
def test_2xx_include_206_si_200(status, ok):
    """Greseala primei treceri VTX a fost o garda pe `== 200`; a doua ar fi una pe
    `== 206`. VTX-3 le-a infirmat pe amandoua: segmentul PLIN da 206, cel GOL da
    200 (dump C3, `resources: 0-9/0`, corp `[]`)."""
    assert _e_2xx(status) is ok


def test_segmentul_gol_e_200_nu_206():
    """Fixture-ul real care a decis garda."""
    assert _fixture("f64.ro_gol.json").strip() == "[]"
    assert _json("f64.ro_gol.json") == []


# ── 3. Headerul `resources` ──────────────────────────────────────────────────

@pytest.mark.parametrize("brut,asteptat", [
    ("2450-2499/52542", (2450, 2499, 52542)),   # C2, fereastra plina
    ("0-9/1164", (0, 9, 1164)),                 # vtx1c, segment fq=C:1000003
    ("0-9/0", (0, 9, 0)),                       # C3, segment gol
    ("0-0/15057", (0, 0, 15057)),               # C5, recensamant
])
def test_parse_resources_pe_valori_masurate(brut, asteptat):
    assert _parse_resources(brut) == asteptat


@pytest.mark.parametrize("brut", [None, "", "aiurea", "1-2", "a-b/c", "0-9/"])
def test_parse_resources_pe_gunoi_da_none(brut):
    """Totalul e ORIENTATIV, deci un header stricat nu are voie sa rupa scanul."""
    assert _parse_resources(brut) is None


# ── 4. Extractia produselor din raspunsuri REALE ─────────────────────────────

def test_extrage_produse_din_fereastra_plina():
    """Fereastra plina masurata: 50 de produse, toate cu pret."""
    produse = _extrage_produse(_json("f64.ro_fereastra50.json"), DOM)

    assert len(produse) == 50
    assert all(p["price"] > 0 for p in produse)
    assert all(p["external_id"].startswith("api:") for p in produse)


def test_extrage_produse_din_segment_filtrat():
    """Segmentul `fq=C:1000003`, primul produs VERBATIM din dump."""
    produse = _extrage_produse(_json("f64.ro_segment.json"), DOM)

    assert len(produse) == 10
    primul = produse[0]
    assert primul["external_id"] == "api:139021"
    assert primul["title"] == "F64 Mini Retro Coolmera Camera Mystery Box"
    assert primul["price"] == 149.99
    assert primul["url"] == "https://www.f64.ro/f64-mini-retro-camera-mystery-box/p"
    # Price == ListPrice (149.99) -> NU e referinta, deci compare_at ramane None.
    assert primul["compare_at"] is None


def test_listprice_devine_referinta_doar_cand_e_peste_pret():
    """`ListPrice` e PRP-ul VTEX. Cand e egal cu `Price` (majoritatea catalogului)
    nu spune nimic, deci nu se scrie ca referinta — altfel R1 ar vedea o reducere
    de 0% pe tot catalogul. Valorile de mai jos sunt din fereastra reala."""
    produse = {p["external_id"]: p
               for p in _extrage_produse(_json("f64.ro_fereastra50.json"), DOM)}
    cu_referinta = [p for p in produse.values() if p["compare_at"] is not None]

    assert cu_referinta, "fereastra 2450-2499 e plina de resigilate cu PRP"
    assert all(p["compare_at"] > p["price"] for p in cu_referinta)
    assert all(p["compare_at"] is None or p["compare_at"] > p["price"]
               for p in produse.values())


def test_produsul_indisponibil_e_sarit():
    """DECIZIA RUNDEI, reversibila: `IsAvailable=False` -> produsul nu intra nici in
    deal-uri, nici in memoria de pret, ca minimul istoric sa nu fie poluat cu
    preturi necumparabile (acelasi rationament ca `_in_stoc` la DEAL-2).

    NOTA DE ONESTITATE: in dump-urile VTX nu exista NICIUN produs cu
    `IsAvailable=False` — toate cele 90 masurate sunt disponibile. Testul ia deci
    un produs REAL si ii comuta flagul, ca sa exercite ramura; forma de raspuns
    ramane cea masurata.
    """
    brut = _json("f64.ro_segment.json")
    brut[0]["items"][0]["sellers"][0]["commertialOffer"]["IsAvailable"] = False

    produse = _extrage_produse(brut, DOM)

    assert len(produse) == 9
    assert "api:139021" not in {p["external_id"] for p in produse}


def test_external_id_e_api_plus_productid():
    assert _external_id("139021") == "api:139021"
    assert _external_id(139021) == "api:139021"


def test_raspunsul_gol_da_zero_produse():
    assert _extrage_produse(_json("f64.ro_gol.json"), DOM) == []


# ── 5. Arborele si descenderea ───────────────────────────────────────────────

def test_excluderile_taie_exact_cele_sase_categorii():
    """SASE, de la runda 3e: EOL a iesit din lista pe masuratoarea VTX-3d, deci
    ramane in arborele util si se scaneaza ca orice alt segment."""
    arbore = _json("f64.ro_tree.json")
    descriptor = catalog_api_descriptor(DOM)

    ramase = api_scanner._radacini_utile(arbore, descriptor["exclude_categories"])

    assert len(arbore) == 41
    assert len(ramase) == 35
    nume = {c["name"] for c in ramase}
    assert "EOL" in nume, "EOL poarta 20.779 de produse (VTX-3d)"
    for exclus in ("Advanced Payment Products", "SH-uri de postat",
                   "frontend", "NoDepartment", "Insurance", "Card Cadou F64"):
        assert exclus not in nume


def test_descenderea_alege_liniar_sub_prag_si_copii_peste():
    """Totalurile sunt cele MASURATE la VTX-1c/VTX-3:
    Aparate foto 1.164 (liniar), Obiective foto 2.855 (descindere),
    Accesorii foto 15.057 (descindere), PC si editare 1.228 (liniar)."""
    arbore = _json("f64.ro_tree.json")
    dupa_id = {c["id"]: c for c in arbore}

    assert api_scanner._are_nevoie_de_descindere(1164) is False
    assert api_scanner._are_nevoie_de_descindere(2855) is True
    assert api_scanner._are_nevoie_de_descindere(15057) is True
    assert api_scanner._are_nevoie_de_descindere(1228) is False
    # granita exacta: 2500 inclusiv e inca liniar
    assert api_scanner._are_nevoie_de_descindere(2500) is False
    assert api_scanner._are_nevoie_de_descindere(2501) is True
    # nodurile masurate chiar au copiii pe care descenderea i-ar folosi
    assert len(dupa_id[1000017]["children"]) == 5     # Obiective foto
    assert len(dupa_id[1000000]["children"]) == 31    # Accesorii foto


def test_benzile_de_pret_se_taie_binar_si_sunt_plafonate():
    """Frunza peste plafon fara copii -> benzi `fq=P:[a TO b]`, taiate binar,
    maxim 8 per frunza. Aici totalul e simulat printr-un recensamant fals."""
    cerute = []

    def recensamant_fals(a, b):
        cerute.append((a, b))
        # densitate concentrata jos: doar banda de sub 1000 e supraincarcata
        return 9000 if a < 1000 else 100

    benzi = api_scanner._benzi_de_pret(recensamant_fals, maxim=8)

    assert len(benzi) <= 8
    assert benzi, "trebuie sa iasa macar o banda"
    # benzile acopera intervalul fara gauri si fara suprapuneri de capete
    benzi_sortate = sorted(benzi)
    assert benzi_sortate[0][0] == 0
    for (_, sfarsit), (inceput_urm, _) in zip(benzi_sortate, benzi_sortate[1:]):
        assert inceput_urm > sfarsit, "benzile nu se suprapun"


# ── 6. Registrul ─────────────────────────────────────────────────────────────

def test_catalog_api_domains_contine_doar_f64():
    assert catalog_api_domains() == {DOM}


def test_descriptorul_de_api_are_cheile_obligatorii():
    d = catalog_api_descriptor(DOM)
    for cheie in ("endpoint", "tree", "currency", "reference_kind",
                  "exclude_categories"):
        assert d.get(cheie), f"lipseste `{cheie}`"
    assert d["endpoint"] == "/api/catalog_system/pub/products/search"
    assert d["tree"] == "/api/catalog_system/pub/category/tree/2"
    assert d["currency"] == "RON"
    assert d["reference_kind"] == "prp"
    assert len(d["exclude_categories"]) == 6      # 3e: EOL a iesit


def test_descriptorul_e_copie_nu_referinta():
    d = catalog_api_descriptor(DOM)
    d["currency"] = "MUTAT"
    assert catalog_api_descriptor(DOM)["currency"] == "RON"


# ── 7. Scanul: oprire, dedup, plafon global ──────────────────────────────────

@pytest.fixture
def scan(monkeypatch):
    """Runner: serveste raspunsuri dupa ORDINEA cererii si ruleaza scanul."""
    cutie = {"raspunsuri": []}
    cereri = []

    def fals(url, *, headers=None, timeout=None, max_hops=3):
        cereri.append(url)
        r = cutie["raspunsuri"]
        # RUNDA 3f — raspunsurile pot fi si o FUNCTIE de URL, nu doar o lista
        # servita in ordine: testele de benzi au nevoie sa raspunda dupa
        # intervalul cerut, fiindca ordinea taieturilor e chiar ce se testeaza.
        if callable(r):
            return r(url)
        i = len(cereri) - 1
        return r[i] if i < len(r) else _Raspuns("[]", 200, "0-49/0")

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fals)
    monkeypatch.setattr(api_scanner, "catalog_api_domains", lambda: {DOM})
    monkeypatch.setattr(api_scanner, "_pauza", lambda: None)

    def ruleaza(raspunsuri, **setari):
        cereri.clear()
        cutie["raspunsuri"] = raspunsuri
        db = SessionLocal()
        try:
            if db.query(RadarSettings).first() is None:
                _seteaza(db, **setari)
            return api_scanner.run_api_scan(db)
        finally:
            db.close()

    ruleaza.cereri = cereri
    return ruleaza


def _arbore_mic():
    """Un arbore de UN nod util, ca testele de scan sa nu plimbe 34 de categorii."""
    return json.dumps([{"id": 1000003, "name": "Aparate foto", "hasChildren": False,
                        "children": []}])


def test_segmentul_se_opreste_pe_fereastra_goala(scan):
    """Oprirea NU e pe egalitate cu totalul din `resources` (drift masurat -388 in
    4 zile, plus CloudFront cu s-maxage=300), ci pe fereastra goala."""
    rezumat = scan([
        _Raspuns(_arbore_mic(), 200),                                    # tree
        _Raspuns("[]", 200, "0-0/2"),                                    # recensamant
        _Raspuns(_fixture("f64.ro_segment.json"), 206, "0-49/2"),        # fereastra 1
        _Raspuns("[]", 200, "50-99/2"),                                  # fereastra 2 GOALA
    ])

    assert rezumat["erori"] == 0
    assert rezumat["produse"] == 10
    assert len(scan.cereri) == 4, "dupa fereastra goala nu se mai cere nimic"


def test_dedup_in_acelasi_scan(scan):
    """Tiparul SCAN-1. Aici conteaza dublu: benzile `[a TO b]` se pot suprapune la
    capete, iar acelasi produs poate aparea in doua segmente."""
    segment = _fixture("f64.ro_segment.json")
    rezumat = scan([
        _Raspuns(_arbore_mic(), 200),
        _Raspuns("[]", 200, "0-0/2"),
        _Raspuns(segment, 206, "0-49/2"),
        _Raspuns(segment, 206, "50-99/2"),      # ACELEASI 10 produse
        _Raspuns("[]", 200, "100-149/2"),
    ])

    assert rezumat["produse"] == 10, "a doua fereastra nu adauga produse noi"
    db = SessionLocal()
    try:
        assert db.query(ShopPriceMemory).count() == 10
    finally:
        db.close()


def test_statusul_neasteptat_opreste_segmentul_nu_scanul(scan):
    """Un 400 pe o fereastra e o masuratoare, nu o catastrofa: segmentul se inchide
    si scanul continua ordonat."""
    rezumat = scan([
        _Raspuns(_arbore_mic(), 200),
        _Raspuns("[]", 200, "0-0/2"),
        _Raspuns(_fixture("f64.ro_eroare_fereastra.json"), 400),
    ])

    assert rezumat["magazine"] == 1, "scanul se incheie ca succes, nu ca eroare"


def test_plafonul_global_de_cereri(scan, monkeypatch):
    """Plasa: 1600 de cereri HTTP per scan. Atinsa -> stare `error` + log, dar
    scanul se incheie ORDONAT (nu exceptie, nu bucla)."""
    monkeypatch.setattr(api_scanner, "_MAX_CERERI", 5)
    segment = _fixture("f64.ro_segment.json")
    scan([_Raspuns(_arbore_mic(), 200)]
         + [_Raspuns(segment, 206, "0-49/99999") for _ in range(20)])

    assert len(scan.cereri) <= 5
    db = SessionLocal()
    try:
        stare = db.query(ShopScanState).filter(
            ShopScanState.shop_domain == DOM).first()
        assert stare is not None and stare.last_status == "error"
    finally:
        db.close()


def test_plafonul_de_productie_este_1600():
    assert api_scanner._MAX_CERERI == 1600


# ── 8. Deal-uri, sursa, anti-avalansa ────────────────────────────────────────

def test_deal_source_este_api_enum(scan, monkeypatch):
    """R1 pe `ListPrice`, cu pragul PROPRIU al listarilor (PRP, nu pretul unui
    comerciant activ). Pragul se coboara aici ca fereastra reala sa califice."""
    monkeypatch.setattr(api_scanner, "_prag_r1", lambda _s: 5.0)
    scan([
        _Raspuns(_arbore_mic(), 200),
        _Raspuns("[]", 200, "0-0/2"),
        _Raspuns(_fixture("f64.ro_fereastra50.json"), 206, "0-49/2"),
        _Raspuns("[]", 200, "50-99/2"),
    ])

    db = SessionLocal()
    try:
        deals = db.query(Deal).all()
    finally:
        db.close()
    assert deals, "fereastra 2450-2499 e plina de resigilate cu PRP"
    assert all(d.deal_source == "api_enum" for d in deals)
    assert all(d.currency == "RON" for d in deals)
    assert all(d.reason == "compare_at" for d in deals)


def test_primul_scan_nu_notifica(scan, monkeypatch):
    """Anti-avalansa, integral ca la DEAL-2: primul scan reusit al unui domeniu e
    linie de baza TACUTA. Pe un catalog de 52.000 de produse, altfel ar fi potop."""
    trimise = []
    monkeypatch.setattr("app.services.discord_service.send_deal_notification",
                        lambda d, s: trimise.append(d) or True)
    monkeypatch.setattr(api_scanner, "_prag_r1", lambda _s: 5.0)
    scan([
        _Raspuns(_arbore_mic(), 200),
        _Raspuns("[]", 200, "0-0/2"),
        _Raspuns(_fixture("f64.ro_fereastra50.json"), 206, "0-49/2"),
        _Raspuns("[]", 200, "50-99/2"),
    ])

    assert trimise == []


def test_plafonul_de_alerte_este_zece():
    assert api_scanner._MAX_ALERTE == 10


# ── 9. Cablarea ──────────────────────────────────────────────────────────────

def test_api_enum_e_sursa_acceptata_de_feed():
    """Fara asta, filtrul din UI ar primi 422 pe propria lui optiune."""
    from app.routers.deals import _SURSE

    assert "api_enum" in _SURSE
    assert _SURSE == {"shopify_enum", "refresh_diff", "listing_scan", "api_enum"}


def test_jobul_e_implicit_OPRIT():
    """Garda de mediu, tiparul FB_EXECUTOR: un scan complet inseamna ~1.100-1.300
    de cereri si 33-48 de minute, deci pornirea lui e o DECIZIE, nu un efect al
    unui deploy. Testul pinuieste ca variabila lipsa inseamna OPRIT."""
    import os
    import re

    cale = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
    with open(cale, encoding="utf-8") as f:
        sursa = f.read()
    m = re.search(r'if \(os\.getenv\("API_ENUM_SCAN"\)[^\n]*\n', sursa)
    assert m, "garda API_ENUM_SCAN a disparut din main.py"
    assert 'or ""' in m.group(0), 'fara `or ""` variabila lipsa ar arunca'
    assert 'in ("1", "true")' in m.group(0), "lista alba => implicit OPRIT"


# ── 10. RUNDA 3b — descenderea pe CAI de categorie (VTX-4) ───────────────────
#
# Runda 3 a esuat live pe o singura presupunere: ca `fq=C:<id>` prinde produse la
# orice nivel. VTX-4 a masurat contrariul si a dat forma corecta:
#
#   fq=C:1000027                  -> total 0      (id GOL, runda 3, toti cei 56)
#   fq=C:1000000/1000027          -> total 2217   (CALE, VTX-4 P1)
#   fq=C:1000017/1000114/1000297  -> total 229    (nivel 3 pe cale, VTX-4 P3)
#
# Forma canonica e publicata chiar de API in fiecare produs, si era in dump-urile
# rundei 3 de la bun inceput:
#   categoriesIds: ["/1000003/1000067/1000228/", "/1000003/1000067/", "/1000003/"]

def _arbore_cu_copil():
    """Parinte peste plafon, cu un copil — exact forma pe care runda 3 o pierdea."""
    return json.dumps([{
        "id": 1000000, "name": "Accesorii foto", "hasChildren": True,
        "children": [{"id": 1000027, "name": "Filtre foto",
                      "hasChildren": False, "children": []}],
    }])


def _arbore_cu_nepot():
    """Trei niveluri: 1000017 > 1000114 > 1000297, calea masurata la VTX-4 P3."""
    return json.dumps([{
        "id": 1000017, "name": "Obiective foto", "hasChildren": True,
        "children": [{
            "id": 1000114, "name": "Accesorii obiective foto", "hasChildren": True,
            "children": [{"id": 1000297, "name": "Capace obiective foto",
                          "hasChildren": False, "children": []}],
        }],
    }])


def test_descenderea_cere_copilul_pe_CALE_nu_pe_id_gol(scan):
    """Reparatia rundei 3b. Cu id-ul gol, cei 31 de copii ai lui „Accesorii foto"
    (15.057 de produse) au dat 0 si s-au pierdut toti."""
    scan([
        _Raspuns(_arbore_cu_copil(), 200),                              # tree
        _Raspuns("[]", 200, "0-0/15057"),                               # parinte: peste prag
        _Raspuns("[]", 200, "0-0/2217"),                                # copil, pe CALE
        _Raspuns(_fixture("f64.ro_cale_nivel2.json"), 206, "0-49/2217"),
        _Raspuns("[]", 200, "50-99/2217"),
    ])

    cerute = " ".join(scan.cereri)
    assert "fq=C:1000000/1000027" in cerute, \
        "copilul trebuie cerut pe CALE (slash-ul NU are voie sa fie procent-codat)"
    assert "fq=C:1000027&" not in cerute, "id-ul gol e exact ce a esuat la runda 3"


def test_descenderea_merge_pana_la_nivelul_3_pe_cale(scan):
    """VTX-4 P3: `fq=C:1000017/1000114/1000297` -> 206, total 229. Deci frunza NU
    era goala la VTX-3; sintaxa era gresita."""
    scan([
        _Raspuns(_arbore_cu_nepot(), 200),
        _Raspuns("[]", 200, "0-0/2829"),                                # nivel 1: peste prag
        _Raspuns("[]", 200, "0-0/2600"),                                # nivel 2: tot peste
        _Raspuns("[]", 200, "0-0/229"),                                 # nivel 3, pe cale
        _Raspuns(_fixture("f64.ro_cale_nivel3.json"), 206, "0-49/229"),
        _Raspuns("[]", 200, "50-99/229"),
    ])

    cerute = " ".join(scan.cereri)
    assert "fq=C:1000017/1000114" in cerute, "nivelul 2 se cere pe cale"
    assert "fq=C:1000017/1000114/1000297" in cerute, "nivelul 3 se cere pe cale"


def test_baza_e_www_ca_sa_nu_depinda_de_redirect(scan):
    """Runda 3 a masurat 335 din 335 de cereri redirectate `f64.ro` ->
    `www.f64.ro:443`. Hopul se evita din start, nu se plateste de 1.200 de ori."""
    scan([_Raspuns(_arbore_cu_copil(), 200), _Raspuns("[]", 200, "0-0/10"),
          _Raspuns("[]", 200, "0-49/10")])

    assert scan.cereri, "trebuie sa fi plecat macar cererea de arbore"
    assert all(u.startswith("https://www.f64.ro/") for u in scan.cereri), \
        "toate cererile pleaca direct pe www"


def test_5xx_se_reincearca_o_data_si_apoi_reuseste(scan):
    """AMENDAMENT 3b. f64 da 5xx sporadic: runda 3 a vazut 4 pe cereri OBISNUITE,
    iar VTX-4 P5 unul pe combinatia C+P (`"Erro ao realizar uma busca:"`, cu
    `x-cache: Error from cloudfront`). O reincercare absoarbe tranzitoriul."""
    scan([
        _Raspuns(_arbore_cu_copil(), 200),
        _Raspuns(_fixture("f64.ro_eroare_500.json"), 500),   # recensamant: pica
        _Raspuns("[]", 200, "0-0/10"),                       # RETRY: reuseste
        _Raspuns(_fixture("f64.ro_segment.json"), 206, "0-49/10"),
        _Raspuns("[]", 200, "50-99/10"),
    ])

    db = SessionLocal()
    try:
        assert db.query(ShopPriceMemory).count() == 10, \
            "dupa retry, segmentul se citeste normal"
    finally:
        db.close()


def test_5xx_de_doua_ori_degradeaza_local_si_scanul_continua(scan):
    """A doua oara nu se mai insista: cererea se abandoneaza, segmentul se
    degradeaza (recensamant necunoscut -> enumerare liniara), iar SCANUL CONTINUA.
    Un 5xx nu are voie sa fie eroare de scan."""
    err = _fixture("f64.ro_eroare_500.json")
    rezumat = scan([
        _Raspuns(_arbore_cu_copil(), 200),
        _Raspuns(err, 500),                                  # recensamant
        _Raspuns(err, 500),                                  # RETRY: tot pica
        _Raspuns(_fixture("f64.ro_segment.json"), 206, "0-49/10"),
        _Raspuns("[]", 200, "50-99/10"),
    ])

    assert rezumat["erori"] == 0, "5xx repetat nu e eroare de scan"
    assert rezumat["magazine"] == 1
    assert rezumat["produse"] == 10, "segmentul se enumereaza si fara recensamant"


def test_combinatia_C_si_P_pastreaza_calea(scan):
    """Cand o frunza peste plafon ajunge la benzi, `fq=C` trebuie sa poarte tot
    CALEA. VTX-4 P4 a masurat perechea pe nivel 1 (206, total 1018)."""
    scan([
        _Raspuns(_arbore_cu_copil(), 200),
        _Raspuns("[]", 200, "0-0/15057"),                    # parinte peste prag
        _Raspuns("[]", 200, "0-0/9000"),                      # copilul, pe cale, TOT peste
        _Raspuns(_fixture("f64.ro_combinatie.json"), 206, "0-0/1018"),
    ] + [_Raspuns("[]", 200, "0-0/100") for _ in range(30)])

    combinate = [u for u in scan.cereri if u.count("fq=") >= 2]
    assert combinate, "frunza peste plafon trebuie sa ajunga la benzi"
    assert all("fq=C:1000000/1000027" in u for u in combinate), \
        "banda pastreaza CALEA, nu id-ul gol"
    assert all("fq=P:" in u for u in combinate)


# ── 11. RUNDA 3e — amendamentele EOL (VTX-3d) ────────────────────────────────
#
# VTX-3d a masurat compozitia celor 7 radacini excluse si a inchis G1:
#   EOL (1000013)              20779   99,96% din gaura de 20.788
#   Insurance / frontend / Card Cadou      6 / 1 / 1
#   Advanced Payment Products / SH-uri de postat / NoDepartment    0 / 0 / 0
#
# Iar EOL NU e zgomot: pe fereastra E8 (fixture `f64.ro_eol.json`), 10 din 11
# oferte sunt `IsAvailable=True`, toate cu pret real, 6 din 10 cu
# `ListPrice > Price`, si `categoriesIds: ["/1000013/"]` — deci exclusiv acolo,
# ceea ce explica de ce scanul nu le vazuse niciodata.

def test_EOL_nu_mai_e_exclusa_dar_celelalte_sase_raman():
    """T1 — amendamentul de lista. Cele sase masurate ca goale sau neglijabile
    raman afara; EOL intra, fiindca poarta 20.779 de produse."""
    excluse = catalog_api_descriptor(DOM)["exclude_categories"]

    assert "EOL" not in excluse, "EOL poarta 99,96% din gaura masurata la VTX-3d"
    for ramane in ("Advanced Payment Products", "SH-uri de postat", "frontend",
                   "NoDepartment", "Insurance", "Card Cadou F64"):
        assert ramane in excluse, f"{ramane} ramane exclusa"
    assert len(excluse) == 6


def test_EOL_e_tratata_ca_segment_si_ajunge_la_benzi(scan):
    """T1b — EOL n-are copii in arbore si are 20.779 > 2.500, deci singura cale
    de segmentare care ii ramane sunt benzile de pret `fq=P`."""
    arbore = json.dumps([{"id": 1000013, "name": "EOL", "hasChildren": False,
                          "children": []}])
    scan([_Raspuns(arbore, 200), _Raspuns("[]", 200, "0-0/20779")]
         + [_Raspuns("[]", 200, "0-0/100") for _ in range(60)])

    cerute = " ".join(scan.cereri)
    assert "fq=C:1000013" in cerute, "EOL nu mai e sarita"
    combinate = [u for u in scan.cereri if u.count("fq=") >= 2]
    assert combinate, "frunza de 20.779 fara copii TREBUIE sa ajunga la benzi"
    assert all("fq=C:1000013" in u and "fq=P:" in u for u in combinate)


def test_plafonul_de_benzi_este_16():
    """T2 — aritmetica: 8 benzi x 2.500 = 20.000 < 20.779, deci plafonul vechi
    n-ar fi acoperit EOL nici in cazul ideal al unei impartiri perfecte."""
    assert api_scanner._MAX_BENZI == 16
    assert 8 * api_scanner._PRAG_SEGMENT < 20779, "de-asta nu ajungeau 8 benzi"
    assert 16 * api_scanner._PRAG_SEGMENT > 20779, "16 acopera, cu marja"


def test_benzile_se_subimpart_pana_la_plafonul_de_16():
    """T2b — o frunza cu densitate concentrata jos se taie pana la 16 benzi, si
    abia ce ramane peste plafon se enumereaza partial."""
    cerute = []

    def recensamant_fals(a, b):
        cerute.append((a, b))
        return 9000 if a < 1000 else 100

    benzi = api_scanner._benzi_de_pret(recensamant_fals)

    assert len(benzi) <= 16
    assert len(benzi) > 8, "cu plafonul nou trebuie sa se taie mai fin decat 8"
    sortate = sorted(benzi)
    assert sortate[0][0] == 0
    for (_, sfarsit), (inceput, _) in zip(sortate, sortate[1:]):
        assert inceput > sfarsit, "benzile nu se suprapun"


def test_EOL_fixture_real_articolul_taxa_intra_dar_nu_califica():
    """T3 — DECIZIA D2: articolele-taxa NU se filtreaza. Sunt inerte pentru feed
    (`Price == ListPrice`, pret stabil), deci nu produc deal-uri; un filtru pe
    nume ar fi o regula inventata, nu masurata."""
    produse = _extrage_produse(_json("f64.ro_eol.json"), DOM)

    assert len(produse) == 10, "toate cele 10 produse EOL se extrag"
    taxa = [p for p in produse if p["external_id"] == "api:129150"]
    assert taxa, "articolul-taxa se ingereaza normal, nu se filtreaza"
    assert taxa[0]["price"] == 49.99
    assert taxa[0]["compare_at"] is None, \
        "Price == ListPrice -> nicio referinta, deci R1 nu are pe ce califica"

    discount, motiv = _evalueaza(taxa[0]["price"], taxa[0]["compare_at"],
                                 None, 20.0, prag_r1=40.0)
    assert discount is None and motiv is None


def test_EOL_resigilatul_real_intra_cu_referinta_dar_sub_pragul_R1():
    """T4 — granita semantica, pe valori MASURATE (productId 137977):
    3999.2 fata de 4999.0 = -20%, real, dar sub `listing_r1_threshold` = 40%.
    Deci EOL aduce marfa reala in memorie (temelia lui R2) fara sa inunde R1."""
    produse = {p["external_id"]: p
               for p in _extrage_produse(_json("f64.ro_eol.json"), DOM)}
    resigilat = produse["api:137977"]

    assert resigilat["price"] == 3999.2
    assert resigilat["compare_at"] == 4999.0
    procent = (1 - resigilat["price"] / resigilat["compare_at"]) * 100
    assert 19.5 < procent < 20.5

    sub_prag, _ = _evalueaza(resigilat["price"], resigilat["compare_at"],
                             None, 20.0, prag_r1=40.0)
    assert sub_prag is None, "-20% nu trece pragul de listare de 40%"

    peste_prag, motiv = _evalueaza(resigilat["price"], resigilat["compare_at"],
                                   None, 20.0, prag_r1=15.0)
    assert peste_prag is not None and motiv == "compare_at"


# ── 12. RUNDA 3f — garda de banda reparata (D6) + benzi goale (D7) ──────────
#
# Runda 3e a masurat live ca vechea garda „total banda == total parinte =>
# filtru ignorat" DA RATEU. Cererile reale, verbatim din dumps_vtx3e:
#
#   206  resources=0-0/20779  ...&fq=C:1000013&fq=P:[0 TO 100000]
#   206  resources=0-0/20779  ...&fq=C:1000013&fq=P:[0 TO 50000]
#
# Tot EOL-ul e sub 50.000 RON, deci banda [0 TO 50000] chiar ii contine pe toti
# cei 20.779. O banda care acopera CINSTIT totul e indistinctibila de un filtru
# ignorat prin testul ala — si asa s-a declansat fallback-ul liniar, plafonat la
# 2.550, lasand 18.231 de produse necitite (34,7% din catalog).
#
# D6: dovada de filtru mort e cand AMBELE jumatati ale unei taieturi intorc
#     totalul parintelui. Una plina si una goala inseamna filtru VIU.
# D7: o banda GOALA nu consuma din bugetul de 16 — altfel jumatatile moarte ale
#     unui catalog inghesuit mananca plafonul si frunza ramane neacoperita.

def _raspuns_banda(total):
    """Raspuns de recensamant cu un `resources` de totalul cerut."""
    return _Raspuns("[]", 200, "0-0/%d" % total)


def _responder_eol(distributie, total_parinte=20779):
    """Mock pe URL: `distributie(a, b)` da totalul benzii [a,b]."""
    import re as _re

    def raspunde(url):
        if "category/tree" in url:
            return _Raspuns(json.dumps([{"id": 1000013, "name": "EOL",
                                         "hasChildren": False, "children": []}]), 200)
        m = _re.search(r"fq=P:\[(\d+)(?:%20| )TO(?:%20| )(\d+)\]", url)
        if m is None:
            return _raspuns_banda(total_parinte)          # recensamantul frunzei
        a, b = int(m.group(1)), int(m.group(2))
        total = distributie(a, b)
        if url.endswith("_to=0") or "_to=0&" in url:
            return _raspuns_banda(total)                  # recensamant de banda
        return _Raspuns("[]", 200, "0-49/%d" % total)     # fereastra (goala)

    return raspunde


def test_D6_banda_mama_plina_cu_sora_goala_NU_e_filtru_mort(scan):
    """T1 — cazul EOL REAL. Toata marfa sub 50.000: [0,50000]=20779 si
    [50001,100000]=0. Una plina + una goala => filtrul e VIU, taierea continua,
    NICIUN fallback. Pe codul de la 3e asta declansa fallback-ul."""
    rezumat = scan(_responder_eol(lambda a, b: 20779 if a < 50000 else 0))

    assert rezumat["erori"] == 0
    jur = rezumat.get("jurnal") or {}
    combinate = [u for u in scan.cereri if u.count("fq=") >= 2]
    assert combinate, "trebuie sa se ceara benzi"
    assert len(combinate) > 2, \
        "pe codul vechi se opreau la 2 cereri combinate si cadea pe fallback"


def test_D6_ambele_jumatati_egale_cu_parintele_INSEAMNA_filtru_mort(scan):
    """T2 — comportamentul vechi, dar pe conditia CORECTA: daca al doilea `fq` e
    ignorat cu adevarat, ORICE banda da totalul parintelui, deci si ambele
    jumatati ale unei taieturi. Atunci fallback-ul e raspunsul bun."""
    scan(_responder_eol(lambda a, b: 20779))              # filtru complet ignorat

    combinate = [u for u in scan.cereri if u.count("fq=") >= 2]
    simple = [u for u in scan.cereri if u.count("fq=") == 1
              and "category/tree" not in u]
    assert combinate, "se incearca benzi"
    assert len(combinate) <= 4, "se renunta REPEDE cand filtrul e mort"
    assert simple, "dupa renuntare se enumereaza liniar (fallback)"


def test_D7_benzile_goale_nu_consuma_din_plafon():
    """T3 — marfa inghesuita intr-un interval ingust. Jumatatile goale se arunca
    si NU mananca din cele 16, deci taierea poate cobori destul de fin cat sa
    acopere intervalul plin."""
    cerute = []

    def recensamant(a, b):
        # Marfa imprastiata pe [0, 800]; peste, nimic. Proportional cu suprapunerea,
        # fiindca doua benzi DISJUNCTE nu pot contine amandoua acelasi produs —
        # un mock care ar spune altfel ar declansa fals garda D6.
        cerute.append((a, b))
        lo, hi = max(a, 0), min(b, 800)
        return int(20000 * (hi - lo + 1) / 801) if hi >= lo else 0

    benzi = api_scanner._benzi_de_pret(recensamant, total_parinte=20000)

    assert benzi, "trebuie sa iasa benzi"
    assert all(recensamant(a, b) > 0 for a, b in benzi), \
        "nicio banda GOALA nu ramane in rezultat"
    assert len(benzi) <= api_scanner._MAX_BENZI
    cea_mai_mare = max(b - a for a, b in benzi)
    assert cea_mai_mare < 100000, \
        "fara D7, plafonul s-ar fi consumat pe jumatati moarte si banda ar fi ramas larga"


def test_D7_frunza_ingusta_se_acopera_INTEGRAL():
    """T4 — benzile finale ajung sub prag si acopera tot intervalul cu marfa."""
    def recensamant(a, b):
        # 24.000 de produse imprastiate uniform pe [0, 2000], nimic peste
        lo, hi = max(a, 0), min(b, 2000)
        return max(0, int(24000 * (hi - lo + 1) / 2001)) if hi >= lo else 0

    benzi = api_scanner._benzi_de_pret(recensamant, total_parinte=24000)

    assert benzi
    sub_prag = [1 for a, b in benzi if recensamant(a, b) <= api_scanner._PRAG_SEGMENT]
    assert len(sub_prag) == len(benzi), \
        "toate benzile finale trebuie sa incapa in enumerarea liniara"
    suma = sum(recensamant(a, b) for a, b in benzi)
    assert suma >= 24000 * 0.95, \
        "benzile acopera aproape tot: suma=%d din 24000" % suma


# ── 13. RUNDA 3g — D8 + integrarea cu clasificarea de blocaje (AMZ-1a) ──────
#
# Runda 3f a masurat live al treilea defect: un 5xx TRANZITORIU pe UN recensamant
# de banda abandona strategia de benzi pe TOT domeniul. Secventa reala, verbatim
# din dumps_vtx3f:
#     206  0-0/20779   P:[0 TO 100000]
#     206  0-0/20779   P:[0 TO 50000]
#     200  0-0/0       P:[50001 TO 100000]     <- D7, banda goala
#     206  0-0/20779   P:[0 TO 25000]
#     500  None        P:[25001 TO 50000]
#     500  None        P:[25001 TO 50000]      <- retry epuizat => fallback pe tot EOL
# Aceeasi rulare a vazut 10 cereri cu 5xx pe 5 URL-uri distincte, patru dintre ele
# ferestre obisnuite FARA `fq=P` — deci hopa de server, nu filtru nesuportat.
#
# AMZ-1a (comis) adauga portii notiunea de „zid". VERBATIM din scraper_service.py:
#     `if _clasifica_raspuns(current_url, response) in _REZULTATE_ZID: return None`
#   „De ce blocajul intoarce None, adica EXACT forma de la eroarea de retea:
#    valoarea de retur n-are camp de motiv, iar apelantii nu se rescriu in runda asta."
# Deci un zid ajunge la `cere()` NEDISTINCTIBIL de o eroare de retea: `None`.
# Consecinta pe codul de la 3f: `_e_5xx(None)` e False, deci zidul NU primeste
# reincercare si degradeaza instant — exact ce nu vrem pentru un transport picat.

def test_D8_banda_picata_nu_omoara_strategia(scan):
    """T1 — reproduce live-ul 3f: banda [25001,50000] da 5xx dublu. ACEA banda se
    marcheaza partiala, taierea CONTINUA pe surori, fallback-ul NU se declanseaza."""
    import re as _re

    def raspunde(url):
        if "category/tree" in url:
            return _Raspuns(json.dumps([{"id": 1000013, "name": "EOL",
                                         "hasChildren": False, "children": []}]), 200)
        m = _re.search(r"fq=P:\[(\d+)(?:%20| )TO(?:%20| )(\d+)\]", url)
        if m is None:
            return _Raspuns("[]", 200, "0-0/20779")
        a, b = int(m.group(1)), int(m.group(2))
        if a == 25001:
            return _Raspuns('"Erro ao realizar uma busca:"', 500)   # banda bolnava
        # Marfa imprastiata pe [0, 20000], PROPORTIONAL cu suprapunerea: doua benzi
        # disjuncte nu pot contine amandoua acelasi produs, iar un mock care ar
        # spune altfel ar declansa fals D6 (pacalit deja o data, la 3f/T3).
        lo, hi = max(a, 0), min(b, 20000)
        total = int(20779 * (hi - lo + 1) / 20001) if hi >= lo else 0
        if url.endswith("_to=0") or "_to=0&" in url:
            return _Raspuns("[]", 200, "0-0/%d" % total)
        return _Raspuns("[]", 200, "0-49/%d" % total)

    rezumat = scan(raspunde)
    jur = rezumat.get("jurnal") or {}

    assert jur.get("benzi_indisponibile") is False, \
        "o banda picata NU e dovada ca fq=C+fq=P nu tine"
    assert jur.get("fallback", 0) == 0, "strategia de benzi NU se abandoneaza"
    assert jur.get("benzi_partiale", 0) >= 1, "banda picata se consemneaza ca partiala"


def test_D8_BenziIndisponibile_ramane_rezervata_verdictului_D6():
    """T2 — transportul (None / 5xx) nu mai are voie sa ridice exceptia. Singura ei
    cauza ramane D6: AMBELE jumatati ale unei taieturi dau totalul parintelui."""
    import inspect

    sursa = inspect.getsource(api_scanner)
    assert "recensamant de banda fara raspuns" not in sursa, \
        "cauza de TRANSPORT a fost scoasa din _BenziIndisponibile"

    # singura ridicare ramasa e cea din _benzi_de_pret, pe conditia D6
    ridicari = [l.strip() for l in sursa.splitlines()
                if "raise _BenziIndisponibile" in l]
    assert len(ridicari) == 1, "o singura cauza: %s" % ridicari
    assert "fq=P ignorat" in sursa


def test_D8_integrare_zid_AMZ1a_e_esec_de_TRANSPORT(scan):
    """T3 — forma REALA a zidului AMZ-1a: poarta intoarce `None` (citat la A1).
    Trebuie tratat ca transport picat — deci reincercat, apoi degradat LOCAL —
    nu ca fereastra goala (care ar inchide segmentul declarandu-l terminat)."""
    apeluri = {"n": 0}

    def raspunde(url):
        if "category/tree" in url:
            return _Raspuns(json.dumps([{"id": 1000003, "name": "Aparate foto",
                                         "hasChildren": False, "children": []}]), 200)
        if url.endswith("_to=0") or "_to=0&" in url:
            return _Raspuns("[]", 200, "0-0/120")
        apeluri["n"] += 1
        if apeluri["n"] == 1:
            return None                    # ZID clasificat AMZ-1a: exact `None`
        return _Raspuns(_fixture("f64.ro_segment.json"), 206, "0-49/120")

    rezumat = scan(raspunde)

    assert rezumat["erori"] == 0, "un zid nu e eroare de scan"
    assert rezumat["produse"] == 10, \
        "dupa reincercare fereastra se citeste; zidul NU inseamna catalog gol"
    jur = rezumat.get("jurnal") or {}
    assert jur.get("retry_transport", 0) >= 1, "zidul intra pe calea de reincercare"


def test_D8_integrare_calea_fericita_ramane_neatinsa(scan):
    """T4 — control negativ: un 2xx normal prin poarta modificata trece identic."""
    rezumat = scan([
        _Raspuns(json.dumps([{"id": 1000003, "name": "Aparate foto",
                              "hasChildren": False, "children": []}]), 200),
        _Raspuns("[]", 200, "0-0/10"),
        _Raspuns(_fixture("f64.ro_segment.json"), 206, "0-49/10"),
        _Raspuns("[]", 200, "50-99/10"),
    ])

    assert rezumat["erori"] == 0
    assert rezumat["produse"] == 10
    jur = rezumat.get("jurnal") or {}
    assert jur.get("retry_transport", 0) == 0, "calea fericita nu reincearca nimic"
    assert jur.get("benzi_partiale", 0) == 0


# ── 14. RUNDA 3h — D9: banda de pret-0 se RECENSEAZA, nu se enumereaza ──────
#
# Runda 3g a masurat descompunerea completa a segmentului EOL pe benzi de pret:
#     P:[0 TO 0]        -> 20766        P:[391 TO 781]   ->  6
#     P:[49 TO 97]      ->     2        P:[782 TO 1562]  ->  2
#     P:[196 TO 390]    ->     2        P:[3126 TO 6250] ->  1
#                               SUMA -> 20779 = EOL exact
#
# Adica 99,94% din EOL are pretul INDEXAT 0. Taierea binara nu-i poate separa —
# impart acelasi punct de pret — deci converge la banda degenerata [0 TO 0], care
# apoi mananca 51 de ferestre si loveste plafonul liniar de 2.550.
#
# D9: pretul 0 nu e o oferta. Recensamantul benzii ALEA e CIFRA care explica
# reziduul, nu o coada de enumerat. Deci se citeste totalul si NU se cer ferestre.

# Distributia MASURATA la 3g, ca puncte de pret: reproduce exact recensamintele
# de mai sus pentru orice interval cerut.
_EOL_PUNCTE = [(0, 20766), (50, 2), (200, 2), (400, 6), (800, 2), (4000, 1)]


def _recensamant_eol(a, b):
    return sum(c for pret, c in _EOL_PUNCTE if a <= pret <= b)


def _responder_eol_masurat(total_pret_zero=20766):
    """Mock pe URL care reproduce descompunerea reala a lui EOL."""
    import re as _re

    puncte = [(p, c) for p, c in _EOL_PUNCTE if p != 0]
    puncte.append((0, total_pret_zero))

    def total_pe(a, b):
        return sum(c for pret, c in puncte if a <= pret <= b)

    def raspunde(url):
        if "category/tree" in url:
            return _Raspuns(json.dumps([{"id": 1000013, "name": "EOL",
                                         "hasChildren": False, "children": []}]), 200)
        m = _re.search(r"fq=P:\[(\d+)(?:%20| )TO(?:%20| )(\d+)\]", url)
        if m is None:
            return _Raspuns("[]", 200, "0-0/%d" % total_pe(0, 10 ** 9))
        a, b = int(m.group(1)), int(m.group(2))
        t = total_pe(a, b)
        if url.endswith("_to=0") or "_to=0&" in url:
            return _Raspuns("[]", 200, "0-0/%d" % t)          # recensamant
        return _Raspuns("[]", 200, "0-49/%d" % t)             # fereastra

    return raspunde


def test_recensamintele_mock_reproduc_masuratoarea_3g():
    """Control: mock-ul chiar da cifrele masurate live, altfel testele de mai jos
    ar valida o fictiune."""
    assert _recensamant_eol(0, 100000) == 20779
    assert _recensamant_eol(0, 50000) == 20779
    assert _recensamant_eol(50001, 100000) == 0
    assert _recensamant_eol(0, 3125) == 20778
    assert _recensamant_eol(3126, 6250) == 1
    assert _recensamant_eol(49, 97) == 2
    assert _recensamant_eol(196, 390) == 2
    assert _recensamant_eol(391, 781) == 6
    assert _recensamant_eol(782, 1562) == 2
    assert _recensamant_eol(0, 0) == 20766


def test_D9_banda_pret_zero_se_recenseaza_dar_NU_se_enumereaza(scan):
    """T1 — banda [0 TO 0] nu primeste nicio fereastra; cifra ei intra in contor;
    celelalte benzi se enumereaza normal."""
    rezumat = scan(_responder_eol_masurat())
    jur = rezumat.get("jurnal") or {}

    # Forma REALA a URL-ului: parantezele drepte raman literale (safe=":[]/"),
    # spatiile devin %20 — verificat pe urmele live de la 3g, ex.
    # . Un tipar cu %5B ar fi trecut VACUU.
    ferestre_pe_zero = [u for u in scan.cereri if "P:[0%20TO%200]" in u]
    ferestre_pe_zero = [u for u in ferestre_pe_zero
                        if not (u.endswith("_to=0") or "_to=0&" in u)]
    assert ferestre_pe_zero == [], \
        "banda de pret-0 NU are voie sa consume ferestre: %s" % ferestre_pe_zero[:2]

    assert jur.get("pret_zero_neenumerat", 0) == 20766, \
        "cifra recensata explica reziduul"
    assert jur.get("partiale", 0) == 0, \
        "fara banda degenerata, nimic nu mai loveste plafonul liniar"

    # celelalte benzi chiar se enumereaza
    alte = [u for u in scan.cereri if "fq=P:" in u.replace("%3A", ":")
            and not (u.endswith("_to=0") or "_to=0&" in u)]
    assert alte, "benzile cu marfa reala se enumereaza"


def test_D9_banda_pret_zero_GOALA_nu_umfla_contorul(scan):
    """T2 — daca la pretul 0 nu sta nimic, banda e pur si simplu goala (D7) si
    contorul ramane zero. Contorul masoara marfa-fantoma, nu existenta benzii."""
    rezumat = scan(_responder_eol_masurat(total_pret_zero=0))
    jur = rezumat.get("jurnal") or {}

    assert jur.get("pret_zero_neenumerat", 0) == 0
    assert jur.get("benzi_indisponibile") is False


def test_D9_pret_zero_e_tratat_LA_FEL_pe_ambele_cai():
    """T3 — garda semantica. Un produs cu `Price=0` ajuns intr-o fereastra
    obisnuita (in afara benzilor) se sare ca `fara_pret`. Deci „pret 0 = non-oferta"
    e aceeasi regula si la nivel de banda (D9), si la nivel de produs."""
    brut = _json("f64.ro_segment.json")
    brut[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 0

    contoare = {}
    produse = _extrage_produse(brut, DOM, contoare)

    assert len(produse) == 9
    assert contoare.get("fara_pret") == 1
    assert "api:139021" not in {p["external_id"] for p in produse}
