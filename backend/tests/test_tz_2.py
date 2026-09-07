"""TZ-2 — restul coloanelor de timp trec pe ora locala a sistemului.

TZ-1 mutase pe `acum_local()` doar coloanele afisate in feed-uri (`found_at` x3,
`log_entries.created_at`). Inventarul de atunci clasase restul drept „neafisate" cautand
doar in componentele de feed — dar pagina Deals randeaza `first_seen_at` ca `found_at`,
iar Sales / Inventory / Products / Alerts afiseaza si ele date. Runda asta uniformizeaza
TOT: in baza, orice datetime e naiv, in ora sistemului.

Doua familii de exceptii, ambele documentate in `utils/listing_dates.py`:
  A. contract EXTERN (JWT `exp`, licenta, sesiunea Facebook, /health);
  B. contract INTERN — subsistemul Facebook, unde `_acum()` ramane UTC aware si forma
     orara a traficului se citeste in `FUS_LOCAL` FIXAT (planner.py:51-52).

Si o consecinta care trebuia sa intre in ACELASI commit: `schemas/_types.py` stampila `Z`
pe exact coloanele convertite. O coloana locala servita mai departe cu `Z` ar fi fost
deplasata inca o data de browser — deci serializatorul a disparut (T7).

Totul offline: baza de test + SQLite in memorie. Zero retea.
"""
import io
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# Momentul fix folosit peste tot mai jos. Ales deliberat NEROTUND si vara, ca o
# conversie accidentala UTC->local (+3 h) sa nu poata trece drept egalitate.
_FIX = datetime(2026, 7, 15, 14, 23, 45)


def _sursa(*cale) -> str:
    with io.open(os.path.join(_APP, *cale), encoding="utf-8") as f:
        return f.read()


# ── T1 — garda statica pe modele ────────────────────────────────────────────────

# Modelele care NU au voie sa mai contina un ceas UTC. Lista e pinuita: un model nou
# adaugat cu `utcnow` nu e prins de test, dar unul dintre astea readus la UTC e.
_MODELE_CONVERTITE = [
    "alert.py", "auto_keyword.py", "auto_listing.py", "auto_lot.py",
    "auto_lot_keyword.py", "deal.py", "discord_queue_db.py",
    "facebook_group_config.py", "facebook_group_post.py", "inventory.py",
    "price_history.py", "product.py", "product_source.py",
    "product_source_suggestion.py", "push_subscription.py", "radar_keyword.py",
    "radar_message_template.py", "radar_seen_id.py", "radar_settings.py",
    "real_estate_listing.py", "real_estate_monitor_keyword.py",
    "resale_fee_profile.py", "resale_reference.py", "sale.py",
    "tracked_product.py", "user.py", "vinted_catalog.py",
]


@pytest.mark.parametrize("model", _MODELE_CONVERTITE)
def test_t1_niciun_ceas_utc_in_modelele_convertite(model):
    s = _sursa("models", model)
    assert "utcnow" not in s, f"{model}: default pe utcnow"
    assert "datetime.now(timezone.utc)" not in s, f"{model}: default pe now(timezone.utc)"
    assert "server_default=func.now()" not in s, (
        f"{model}: server_default=func.now() e CURRENT_TIMESTAMP, adica UTC pe SQLite")
    assert "acum_local" in s, f"{model}: nu foloseste ceasul local"


def test_t1b_coloanele_tz1_si_subsistemul_fb_raman_neatinse():
    """Garda in cealalta directie: TZ-1 isi pastreaza plasa, FB isi pastreaza UTC-ul."""
    # TZ-1 — `server_default=func.now()` ramane DELIBERAT ca plasa pentru INSERT-uri
    # din afara ORM-ului; default-ul Python e cel care conteaza.
    for m in ("auto_feed_listing.py", "real_estate_monitor_listing.py"):
        s = _sursa("models", m)
        assert "default=lambda: acum_local()" in s and "server_default=func.now()" in s
    # Subsistemul FB nu are default-uri de ceas deloc (se scriu explicit, cu `_acum()`).
    for m in ("fb_pool.py", "fb_scan_state.py"):
        s = _sursa("models", m)
        assert "acum_local" not in s, f"{m}: subsistemul FB nu se converteste (TZ-2 B)"


# ── T2 — garda statica pe cod ───────────────────────────────────────────────────

_FISIERE_CONVERTITE = [
    ("services", "api_scanner.py"), ("services", "deal_scanner.py"),
    ("services", "deal_retention.py"), ("services", "facebook_group_service.py"),
    ("utils", "radar_scanner.py"), ("services", "real_estate_scanner.py"),
    ("services", "auto_listings_scanner.py"), ("services", "auto_lot_scanner.py"),
    ("services", "radar", "cleanup_service.py"), ("services", "listing_scanner.py"),
    ("utils", "alert_checker.py"), ("services", "discord_service.py"),
    ("routers", "products.py"), ("routers", "radar.py"),
    ("routers", "real_estate_keywords.py"),
    ("services", "radar", "vinted_catalog_service.py"),
]


@pytest.mark.parametrize("cale", _FISIERE_CONVERTITE, ids=lambda c: c[-1])
def test_t2_niciun_ceas_utc_in_fisierele_convertite(cale):
    s = _sursa(*cale)
    for tipar in ("datetime.utcnow()", "datetime.now(timezone.utc)"):
        assert tipar not in s, f"{cale[-1]}: a ramas {tipar}"


# Exceptiile, ENUMERATE: fisierele care AU voie sa foloseasca ceasul UTC, cu motivul.
_EXCEPTII_UTC = {
    ("utils", "auth.py"): "contract extern — `exp` din JWT",
    ("services", "license_service.py"): "contract extern — expirarea licentei",
    ("routers", "health.py"): "contract extern — citit de monitorizare",
    ("routers", "facebook_groups.py"): "contract extern — cookies_saved_at (sesiune FB)",
    ("scrapers", "facebook", "executor.py"): "contract intern FB — `_acum()`",
    ("scrapers", "facebook", "planner.py"): "contract intern FB — cadenta + FUS_LOCAL",
    ("scrapers", "facebook", "bazin.py"): "contract intern FB — retentia bazinului",
    ("scrapers", "facebook", "parse.py"): "contract intern FB — canonicul e UTC aware",
    ("scrapers", "facebook", "bootstrap.py"): "contract extern — prospetimea sesiunii FB",
    ("scrapers", "facebook", "atingere.py"): "contract extern — marcajul sesiunii FB",
    ("services", "radar", "amprenta_ferma.py"): "contract intern FB — citeste canonicul",
}


@pytest.mark.parametrize("cale,motiv", sorted(_EXCEPTII_UTC.items()))
def test_t2b_exceptiile_chiar_folosesc_utc(cale, motiv):
    """Fiecare exceptie e REALA (chiar are un ceas UTC) — altfel lista putrezeste
    tacut si ajunge sa scuze fisiere care s-au convertit deja."""
    s = _sursa(*cale)
    assert ("timezone.utc" in s or "utcnow" in s), f"{cale[-1]}: exceptie moarta ({motiv})"


def test_t2c_documentatia_exceptiilor_exista():
    s = _sursa("utils", "listing_dates.py")
    assert "CONTRACT EXTERN" in s and "CONTRACT INTERN" in s
    assert "planner.py:51-52" in s, "motivul exceptiei FB trebuie citabil, nu doar afirmat"


# ── T3 — default-urile chiar scriu ceasul local ─────────────────────────────────

def _parinti(db):
    """User + Product reali: jumatate din modele au FK catre ei."""
    from app.models.product import Product
    from app.models.user import User

    email = f"tz2_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    p = Product(user_id=u.id, name="Produs TZ-2")
    db.add(p)
    db.flush()
    return u, p


_CAZURI_T3 = [
    ("app.models.deal", "Deal", "first_seen_at", lambda u, p: dict(
        shop_domain="x.ro", external_id=f"e{uuid.uuid4().hex[:8]}", title="t",
        url="https://x.ro/p", price=1.0, currency="RON", discount_pct=10.0,
        reason="compare_at")),
    ("app.models.radar_seen_id", "RadarSeenId", "seen_at", lambda u, p: dict(
        user_id=u.id, platform="vinted", external_id=f"e{uuid.uuid4().hex[:8]}")),
    ("app.models.user", "User", "created_at", lambda u, p: dict(
        email=f"b_{uuid.uuid4().hex[:10]}@x.ro", username=uuid.uuid4().hex[:10],
        hashed_password="x")),
    ("app.models.product", "Product", "created_at", lambda u, p: dict(
        user_id=u.id, name="p2")),
    ("app.models.price_history", "PriceHistory", "recorded_at", lambda u, p: dict(
        product_id=p.id, price=1.0)),
    ("app.models.tracked_product", "TrackedProduct", "added_at", lambda u, p: dict(
        user_id=u.id, product_id=p.id)),
    ("app.models.vinted_catalog", "VintedCatalog", "updated_at", lambda u, p: dict(
        id=1, title="t", path="a > b", depth=1)),
    ("app.models.radar_keyword", "RadarKeyword", "created_at", lambda u, p: dict(
        user_id=u.id, name="kw", max_price=100.0, resale_price=200.0)),
    ("app.models.alert", "Alert", "created_at", lambda u, p: dict(
        user_id=u.id, product_id=p.id, target_price=10.0)),
    ("app.models.sale", "Sale", "created_at", lambda u, p: dict(
        user_id=u.id, product_name="x", sale_price=5.0)),
    ("app.models.inventory", "InventoryItem", "created_at", lambda u, p: dict(
        user_id=u.id, name="x", purchase_price=5.0)),
    ("app.models.discord_queue_db", "DiscordQueueItem", "created_at", lambda u, p: dict(
        webhook_url="https://discord/x", embed="{}", listing_id=1, module="radar")),
]


@pytest.mark.parametrize("modul,clasa,coloana,campuri", _CAZURI_T3,
                         ids=[c[2] + "@" + c[1] for c in _CAZURI_T3])
def test_t3_defaultul_scrie_exact_ceasul_local(monkeypatch, modul, clasa, coloana, campuri):
    """Default-ul e `lambda: acum_local()`, nu `acum_local` gol — legare TARZIE.

    Diferenta nu e cosmetica: un callable legat la definirea clasei nu mai poate fi
    mock-uit, deci nici testat. Acelasi tipar pe care TZ-1 il folosea deja pentru
    `found_at`.
    """
    import importlib

    from app.database import SessionLocal

    m = importlib.import_module(modul)
    monkeypatch.setattr(m, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        u, p = _parinti(db)
        rand = getattr(m, clasa)(**campuri(u, p))
        db.add(rand)
        db.commit()
        db.refresh(rand)
        assert getattr(rand, coloana) == _FIX
        assert getattr(rand, coloana).tzinfo is None, "in baza tinem NAIV"
    finally:
        db.close()


# ── T4 — comparatiile de prag, pe ceasul mock-uit ───────────────────────────────

def test_t4_platform_scan_due_nu_mai_citeste_naivul_ca_utc():
    """radar_scanner — cazul care ar fi facut ORICE keyword scadent 3 h dupa deploy.

    `last_scan_at` e acum ora locala; coercitia veche (`tzinfo=utc`) l-ar fi impins cu
    offsetul in trecut, deci pragul de 5 min ar fi parut mereu depasit.
    """
    from datetime import timedelta

    from app.utils import radar_scanner as rs

    class KW:
        platform_last_scan = None
        poll_interval_minutes = 5
        last_scan_at = _FIX - timedelta(minutes=4)

    assert rs._platform_scan_due(KW(), "vinted", now=_FIX) is False   # 4 min < 5
    KW.last_scan_at = _FIX - timedelta(minutes=6)
    assert rs._platform_scan_due(KW(), "vinted", now=_FIX) is True    # 6 min > 5
    # o stampila VECHE, cu offset, ramane corecta (nu cere backfill)
    KW.last_scan_at = None
    KW.platform_last_scan = '{"vinted": "%s"}' % (
        _FIX.astimezone().isoformat())
    assert rs._platform_scan_due(KW(), "vinted", now=_FIX) is False


def test_t4b_mark_platform_scanned_emite_offsetul_local():
    """Stringul din JSON e auto-descriptiv: ora locala CU offset, nu naiv si nu `Z`."""
    import json

    from app.utils import radar_scanner as rs

    class KW:
        platform_last_scan = None
        last_scan_at = None

    kw = KW()
    rs._mark_platform_scanned(kw, "vinted", now=_FIX)
    ts = json.loads(kw.platform_last_scan)["vinted"]
    assert not ts.endswith("Z") and "+00:00" not in ts, f"nu mai emitem UTC: {ts}"
    assert datetime.fromisoformat(ts).replace(tzinfo=None) == _FIX
    assert kw.last_scan_at == _FIX


def test_t4c_polling_due_imobiliare_pe_acelasi_ceas():
    from datetime import timedelta

    from app.services import real_estate_scanner as rs

    class KW:
        last_scan_at = _FIX - timedelta(minutes=29)
        polling_interval_minutes = 30

    assert rs._polling_due(KW(), _FIX) is False
    KW.last_scan_at = _FIX - timedelta(minutes=31)
    assert rs._polling_due(KW(), _FIX) is True


def test_t4d_retentia_de_dealuri_masoara_pe_ceasul_local(monkeypatch):
    """deal_retention — pragul de vechime se ia de la `acum_local`, ca `last_seen_at`."""
    from app.services import deal_retention as dr

    monkeypatch.setattr(dr, "acum_local", lambda: _FIX)
    assert "acum_local()" in _sursa("services", "deal_retention.py")


def test_t4e_cleanup_service_compara_doua_coloane_pe_acelasi_ceas():
    """`found_at` (TZ-1) si `last_checked_at` (TZ-2) sunt acum acelasi ceas — inainte
    randul avea doua conventii, la 3 h distanta."""
    s = _sursa("services", "radar", "cleanup_service.py")
    assert "cutoff = acum_local()" in s
    assert "last_checked_at = acum_local()" in s


# ── T5 — migrarea ───────────────────────────────────────────────────────────────

def _baza_sintetica(cale, n_deals=5):
    """SQLite pe disc cu cate un rand de VARA si unul de IARNA in fiecare coloana."""
    c = sqlite3.connect(cale)
    c.execute("CREATE TABLE schema_migrations (migration_name VARCHAR(200) UNIQUE NOT NULL, "
              "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE deals (id INTEGER PRIMARY KEY, first_seen_at TIMESTAMP, "
              "last_seen_at TIMESTAMP, ended_at TIMESTAMP)")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, created_at TIMESTAMP, "
              "updated_at TIMESTAMP)")
    # coloane care NU au voie sa fie atinse
    c.execute("CREATE TABLE radar_listings (id INTEGER PRIMARY KEY, found_at TIMESTAMP, "
              "last_checked_at TIMESTAMP)")
    c.execute("CREATE TABLE fb_scan_state (id INTEGER PRIMARY KEY, next_due_at TIMESTAMP)")
    c.execute("CREATE TABLE facebook_group_configs (id INTEGER PRIMARY KEY, "
              "created_at TIMESTAMP, last_run_at TIMESTAMP, cookies_saved_at TIMESTAMP)")
    iarna = "2026-01-15 10:00:00"     # UTC+2
    vara = "2026-07-15 10:00:00"      # UTC+3
    for i in range(n_deals):
        val = iarna if i % 2 else vara
        c.execute("INSERT INTO deals (id, first_seen_at, last_seen_at, ended_at) "
                  "VALUES (?,?,?,NULL)", (i + 1, val, val))
    c.execute("INSERT INTO users (id, created_at, updated_at) VALUES (1,?,?)", (iarna, vara))
    c.execute("INSERT INTO radar_listings (id, found_at, last_checked_at) VALUES (1,?,?)",
              (vara, vara))
    c.execute("INSERT INTO fb_scan_state (id, next_due_at) VALUES (1,?)", (vara,))
    c.execute("INSERT INTO facebook_group_configs (id, created_at, last_run_at, "
              "cookies_saved_at) VALUES (1,?,?,?)", (vara, vara, vara))
    c.commit()
    c.close()


def _ruleaza_migrarea(cale):
    import app.utils.db_migrate as dm

    eng = create_engine("sqlite:///" + cale.replace("\\", "/"))
    insp = inspect(eng)
    with eng.connect() as conn:
        for nume in dm._TZ2_GRUPURI:
            dm._tz2_backfill_grup(conn, insp, nume)
    eng.dispose()


def _val(cale, tabel, coloana, rid=1):
    c = sqlite3.connect(cale)
    try:
        return c.execute(f"SELECT {coloana} FROM {tabel} WHERE rowid = ?", (rid,)).fetchone()[0]
    finally:
        c.close()


def test_t5_migrarea_converteste_per_rand_cu_dst(tmp_path):
    cale = str(tmp_path / "tz2.db")
    _baza_sintetica(cale)
    _ruleaza_migrarea(cale)

    # rowid 1 = vara (+3), rowid 2 = iarna (+2) — offsetul se aplica PER RAND
    assert str(_val(cale, "deals", "first_seen_at", 1)).startswith("2026-07-15 13:00")
    assert str(_val(cale, "deals", "first_seen_at", 2)).startswith("2026-01-15 12:00")
    assert str(_val(cale, "users", "created_at")).startswith("2026-01-15 12:00")
    assert str(_val(cale, "users", "updated_at")).startswith("2026-07-15 13:00")
    # NULL-urile raman NULL
    assert _val(cale, "deals", "ended_at", 1) is None


def test_t5b_coloanele_interzise_raman_neatinse(tmp_path):
    cale = str(tmp_path / "tz2b.db")
    _baza_sintetica(cale)
    inainte = {
        ("radar_listings", "found_at"): _val(cale, "radar_listings", "found_at"),
        ("fb_scan_state", "next_due_at"): _val(cale, "fb_scan_state", "next_due_at"),
        ("facebook_group_configs", "cookies_saved_at"):
            _val(cale, "facebook_group_configs", "cookies_saved_at"),
    }
    _ruleaza_migrarea(cale)
    for (tabel, coloana), vechi in inainte.items():
        assert _val(cale, tabel, coloana) == vechi, f"{tabel}.{coloana} nu avea voie sa se schimbe"
    # dar vecinele lor din acelasi tabel S-AU convertit
    assert str(_val(cale, "radar_listings", "last_checked_at")).startswith("2026-07-15 13:00")
    assert str(_val(cale, "facebook_group_configs", "created_at")).startswith("2026-07-15 13:00")


def test_t5c_a_doua_rulare_nu_schimba_nimic(tmp_path):
    cale = str(tmp_path / "tz2c.db")
    _baza_sintetica(cale)
    _ruleaza_migrarea(cale)
    dupa_una = [_val(cale, "deals", "first_seen_at", i) for i in (1, 2, 3)]
    _ruleaza_migrarea(cale)
    assert [_val(cale, "deals", "first_seen_at", i) for i in (1, 2, 3)] == dupa_una


def test_t5d_batch_urile_acopera_un_tabel_mai_mare_decat_un_batch(tmp_path):
    """> 5.000 de randuri: TOATE convertite, NICIUNUL de doua ori."""
    import app.utils.db_migrate as dm

    cale = str(tmp_path / "tz2d.db")
    _baza_sintetica(cale, n_deals=12_001)      # 3 batch-uri de 5.000 + rest
    assert dm._TZ2_BATCH == 5000
    _ruleaza_migrarea(cale)

    c = sqlite3.connect(cale)
    try:
        vara = c.execute("SELECT COUNT(*) FROM deals WHERE first_seen_at "
                         "LIKE '2026-07-15 13:00%'").fetchone()[0]
        iarna = c.execute("SELECT COUNT(*) FROM deals WHERE first_seen_at "
                          "LIKE '2026-01-15 12:00%'").fetchone()[0]
        assert vara + iarna == 12_001, "randuri neconvertite (batch sarit)"
        # o a doua conversie ar da 16:00 / 14:00 — niciun rand nu trebuie sa fie acolo
        dublu = c.execute("SELECT COUNT(*) FROM deals WHERE first_seen_at "
                          "LIKE '2026-07-15 16:00%' OR first_seen_at "
                          "LIKE '2026-01-15 14:00%'").fetchone()[0]
        assert dublu == 0, "randuri convertite de DOUA ori"
        ramase = c.execute("SELECT COUNT(*) FROM schema_migrations WHERE "
                           "migration_name LIKE 'tz2p:%'").fetchone()[0]
        assert ramase == 0, "marcajele de progres trebuie curatate la final"
        for nume in dm._TZ2_GRUPURI:
            assert c.execute("SELECT 1 FROM schema_migrations WHERE migration_name = ?",
                             (nume,)).fetchone(), f"{nume} neinregistrat"
    finally:
        c.close()


def test_t5e_reluarea_continua_de_unde_a_ramas(tmp_path):
    """Marcajul de progres e contractul de reluabilitate: un grup intrerupt dupa
    batch-ul 1 nu reconverteste batch-ul 1 la repornire."""
    import app.utils.db_migrate as dm

    cale = str(tmp_path / "tz2e.db")
    _baza_sintetica(cale, n_deals=7_000)
    eng = create_engine("sqlite:///" + cale.replace("\\", "/"))
    insp = inspect(eng)
    # rulare "intrerupta": doar coloana deals.first_seen_at, un singur grup, apoi cadere
    with eng.connect() as conn:
        original = dm._TZ2_GRUPURI["tz2a_feed"]
        dm._TZ2_GRUPURI["tz2a_feed"] = [("deals", "first_seen_at")]
        try:
            dm._tz2_backfill_grup(conn, insp, "tz2a_feed")
        finally:
            dm._TZ2_GRUPURI["tz2a_feed"] = original
    eng.dispose()
    primul = _val(cale, "deals", "first_seen_at", 1)
    assert str(primul).startswith("2026-07-15 13:00")
    # grupul e marcat aplicat -> a doua trecere il sare complet
    _ruleaza_migrarea(cale)
    assert _val(cale, "deals", "first_seen_at", 1) == primul


# ── T6 — Deals: `first_seen_at` afisat ca `found_at` ────────────────────────────

def test_t6_deals_serveste_first_seen_at_in_ora_locala(auth_client, monkeypatch):
    """Pagina Deals randeaza `deal.first_seen_at` sub numele `found_at`
    (`frontend/src/app/dashboard/deals/page.js:407`) si il trece prin `timeAgo`, care
    scade din `Date.now()` al browserului. Cu valoarea in UTC arata „acum 3 h" imediat
    dupa scan — bug-ul viu pe care il inchide TZ-2."""
    from app.database import SessionLocal
    from app.models import deal as deal_mod

    monkeypatch.setattr(deal_mod, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        d = deal_mod.Deal(shop_domain="x.ro", external_id=f"e{uuid.uuid4().hex[:8]}",
                          title="Produs", url="https://x.ro/p", price=10.0,
                          currency="RON", discount_pct=10.0, reason="compare_at")
        db.add(d)
        db.commit()
    finally:
        db.close()

    r = auth_client.get("/api/deals/")
    assert r.status_code == 200, r.text
    items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
    al_nostru = [x for x in items if x.get("title") == "Produs"]
    assert al_nostru, r.json()
    ts = al_nostru[0]["first_seen_at"]
    assert not str(ts).endswith("Z") and "+00:00" not in str(ts), ts
    assert datetime.fromisoformat(str(ts)).replace(tzinfo=None) == _FIX


# ── T7 — UTCDateTime a disparut ─────────────────────────────────────────────────

def test_t7_niciun_serializator_mai_stampileaza_z():
    """Serializatorul si TOATE folosirile lui. Daca ramane pe fie si o singura coloana
    convertita, valoarea locala pleaca etichetata `Z` si browserul o mai deplaseaza o
    data — exact bug-ul pe care runda il elimina."""
    schemas = os.path.join(_APP, "schemas")
    assert not os.path.exists(os.path.join(schemas, "_types.py")), \
        "schemas/_types.py trebuie sters"
    for fn in os.listdir(schemas):
        if not fn.endswith(".py"):
            continue
        s = _sursa("schemas", fn)
        assert "UTCDateTime" not in s, f"schemas/{fn}: UTCDateTime a ramas"
        assert '"Z"' not in s and "replace(\"+00:00\", \"Z\")" not in s, \
            f"schemas/{fn}: mai stampileaza Z"


# ── T8 — subsistemul Facebook e neatins ─────────────────────────────────────────

def test_t8_fb_pastreaza_utc_si_fusul_fixat():
    from app.scrapers.facebook import executor, planner

    acum = executor._acum()
    assert acum.tzinfo is not None, "`_acum()` din executor trebuie sa ramana AWARE"
    assert acum.utcoffset().total_seconds() == 0, "si anume UTC"
    assert planner.FUS_LOCAL == "Europe/Bucharest", \
        "forma orara e ancorata in piata, nu in ceasul masinii (planner.py:51-52)"
    # coercitiile FB isi pastreaza semantica, cu marcajul care o explica
    for fn in ("planner.py", "parse.py", "bootstrap.py"):
        assert "TZ-2 — EXCEPTIE" in _sursa("scrapers", "facebook", fn), fn


def test_t8b_forma_orara_ramane_pe_ora_bucurestiului():
    """Proba concreta: 23:00 UTC e ora 2 la Bucuresti vara, si asa trebuie citita."""
    from app.scrapers.facebook.planner import ConfigPlanificator, Planificator

    p = Planificator(sesiune=None, config=ConfigPlanificator())
    assert p.ora_locala(datetime(2026, 7, 15, 23, 0, tzinfo=timezone.utc)) == 2


# ── T9 — endpoint-urile retail servesc ora locala, fara offset ──────────────────

_SCHEME_RETAIL = [
    ("app.schemas.alert", "AlertResponse", ("created_at", "triggered_at")),
    ("app.schemas.product", "ProductResponse", ("created_at",)),
    ("app.schemas.sale", "SaleResponse", ("created_at",)),
    ("app.schemas.inventory", "InventoryItemResponse", ("created_at",)),
    ("app.schemas.user", "UserResponse", ("created_at",)),
]


@pytest.mark.parametrize("modul,clasa,campuri", _SCHEME_RETAIL, ids=[c[1] for c in _SCHEME_RETAIL])
def test_t9_schemele_retail_emit_fara_offset(modul, clasa, campuri):
    """Serializarea JSON a schemei nu adauga `Z` si nu deplaseaza valoarea.

    Asertia e pe IESIREA serializata, nu pe adnotarea campului: `UTCDateTime` era un
    `Annotated[datetime, PlainSerializer(...)]`, iar Pydantic il rezolva la `datetime`
    simplu — deci o garda pe numele tipului n-ar fi vazut serializatorul ramas pe o
    coloana. Asta e exact ce trebuie sa prinda sabotajul S4.
    """
    import importlib
    import json

    m = importlib.import_module(modul)
    model = getattr(m, clasa)
    for camp in campuri:
        assert camp in model.model_fields, f"{clasa}: campul {camp} a disparut"
    obiect = model.model_construct(**{c_: _FIX for c_ in campuri})
    iesire = json.loads(obiect.model_dump_json())
    for camp in campuri:
        text_ = str(iesire[camp])
        assert not text_.endswith("Z"), f"{clasa}.{camp}: inca stampilat Z ({text_})"
        assert "+00:00" not in text_, f"{clasa}.{camp}: inca emite offset UTC ({text_})"
        assert datetime.fromisoformat(text_).replace(tzinfo=None) == _FIX, (
            f"{clasa}.{camp}: valoarea a fost deplasata ({text_})")


def test_t9b_alerts_serveste_exact_ceasul_local(auth_client, monkeypatch):
    from app.database import SessionLocal
    from app.models import alert as alert_mod

    monkeypatch.setattr(alert_mod, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        u, p = _parinti(db)
        a = alert_mod.Alert(user_id=u.id, product_id=p.id, target_price=10.0,
                            is_active=True)
        db.add(a)
        db.commit()
        db.refresh(a)
        assert a.created_at == _FIX
        # forma serializata: fara `Z`, fara offset, exact valoarea scrisa
        import json
        brut = json.dumps(a.created_at.isoformat())
        assert "Z" not in brut and "+00:00" not in brut, brut
    finally:
        db.close()
