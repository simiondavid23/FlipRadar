"""TZ-3c — coloanele de PIATA respecta ceasul PIETEI, pe tot lantul.

REGULA rundei (scrisa si in handover-ul din `utils/listing_dates.py`): o valoare se
masoara pe ceasul EI. O comparatie sau o scadere cere ambele parti pe acelasi ceas; cand
difera, se aduce ceasul SISTEMULUI pe ceasul PIETEI la momentul comparatiei, niciodata
invers. Producatorii nu se muta pe `la_ora_sistemului` — aia ar strica afisarea, care e
tot rostul ceasului pietei.

CE A PORNIT RUNDA. Auditul de dupa TZ-3b a gasit sase cauze, toate in AFARA registrului
`_CEAS_PIETEI_PERMIS` — care era curat. Garda de atunci verifica cine CHEAMA convertorul,
nu cine ar TREBUI sa-l cheme, deci era oarba exact la scriitorii care nu-l chemau deloc:
  1. Copart — `parse_epoch_ms` emitea ISO FARA offset, iar `to_naive_bucuresti` lasa
     neatins un moment fara offset (contractul lui), deci ora UTC ajungea in
     `auction_date` ca si cum ar fi fost ora Bucurestiului. Singura dintre cele sase care
     gresea DEJA pe masina de productie: licitatia de la 15:00 RO se stoca 12:00.
  2. Vinted / Facebook Auto / Publi24 — `datetime.fromtimestamp()` gol, respectiv „azi"
     ancorat pe `datetime.now()`: ceasul masinii, in coloana pietei.
  3. `_too_old` si stop-criteriul grupurilor FB — scadeau o valoare de piata dintr-un ceas
     de sistem. Fereastra de dezacord e exact offsetul (2 h iarna, 3 h vara).
  4. `listed_at` primea, ca rezerva, `created_at`-ul postarii FB = momentul INSERT-ului.

CUM SE CITESC TESTELE. Cele mai multe sunt PROPRIETATI (doi producatori ai aceleiasi
coloane trebuie sa dea aceeasi ora pentru acelasi instant), deci trec sub orice fus si cad
cand un capat se muta pe alt ceas. Pe o masina din Romania trec si stricate — acolo cele
doua ceasuri sunt acelasi ceas. Proba tare se da rulandu-le sub `TZ=UTC`:

    TZ=UTC pytest tests/test_tz_3c.py
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.listing_dates import FUS_ANUNTURI, acum_local, to_naive_bucuresti


def _acum_piata() -> datetime:
    """Acum, pe ceasul PIETEI — referinta independenta de fusul masinii."""
    return to_naive_bucuresti(datetime.now(timezone.utc))


# Instant fix, ales vara si nerotund, ca o conversie ratata sa nu poata trece drept
# egalitate: 2026-09-10 12:00:00 UTC = 15:00 la Bucuresti.
_EPOCH = 1789041600
_LA_BUCURESTI = datetime(2026, 9, 10, 15, 0, 0)


# ── 1. Copart: `auction_date` e ora Bucurestiului acelui instant ───────────────

def test_1_parse_epoch_ms_emite_offset():
    """Fara offset, `to_naive_bucuresti` n-are ce converti — asta era bug-ul."""
    from app.scrapers.auto.lots._common import parse_epoch_ms

    iso = parse_epoch_ms(_EPOCH * 1000)
    assert iso.endswith("+00:00"), iso
    assert datetime.fromisoformat(iso) == datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def test_1b_auction_date_ajunge_ora_bucurestiului():
    """Lantul intreg, cum il parcurge scanerul: epoch Copart -> coloana."""
    from app.scrapers.auto.lots._common import parse_epoch_ms

    assert to_naive_bucuresti(parse_epoch_ms(_EPOCH * 1000)) == _LA_BUCURESTI


def test_1c_epoch_in_secunde_si_in_milisecunde_dau_acelasi_moment():
    from app.scrapers.auto.lots._common import parse_epoch_ms

    assert parse_epoch_ms(_EPOCH) == parse_epoch_ms(_EPOCH * 1000)


def test_1d_o_singura_implementare_de_parsare():
    """Duplicatul din `auto_lot_scanner` a disparut: doua parsari inseamna doua ceasuri.

    Garda e pe SURSA, nu pe comportament: o a doua copie ar putea fi corecta azi si sa
    divergheze la prima atingere — exact istoria coloanei asteia.
    """
    import inspect

    from app.services import auto_lot_scanner

    sursa = inspect.getsource(auto_lot_scanner)
    assert "def _parse_auction_date" not in sursa, "duplicatul a revenit"
    assert "to_naive_bucuresti(raw.get(\"auction_date\"))" in sursa


def test_1e_ruta_manuala_si_scanerul_scriu_aceeasi_ora():
    """Cele doua cai catre `auto_lots.auction_date` nu au voie sa divergheze."""
    from app.routers.auto import _parse_auction_date
    from app.scrapers.auto.lots._common import parse_epoch_ms

    iso = parse_epoch_ms(_EPOCH * 1000)
    assert _parse_auction_date(iso) == to_naive_bucuresti(iso) == _LA_BUCURESTI


# ── 2. Producatori care scriau ceasul masinii in `listed_at` ──────────────────

def test_2_vinted_poza_da_ora_pietei():
    """Proprietatea: acelasi instant, acelasi rezultat ca la OLX/Facebook.

    `radar_listings.listed_at` primeste de la OLX ora Bucurestiului si primea de la Vinted
    ora masinii — sub `TZ=UTC`, doua anunturi postate in aceeasi clipa aratau 12:00 si
    15:00 in acelasi feed.
    """
    from app.services.radar.vinted_scraper import _listed_at_din_poza

    assert _listed_at_din_poza({"high_resolution": {"timestamp": _EPOCH}}) == _LA_BUCURESTI
    assert _listed_at_din_poza(
        {"high_resolution": {"timestamp": _EPOCH}}) == to_naive_bucuresti(_EPOCH)


def test_2b_vinted_degradare_neschimbata():
    from app.services.radar.vinted_scraper import _listed_at_din_poza

    for rau in (None, {}, {"high_resolution": {}}, {"high_resolution": {"timestamp": 0}}):
        assert _listed_at_din_poza(rau) is None, rau


def test_2c_facebook_auto_nu_mai_are_niciun_fromtimestamp_gol():
    """Calea cu SESIUNE citea `creation_time` cu `datetime.fromtimestamp()` gol.

    Garda e structurala, nu de comportament, si deliberat: conversia traieste inline in
    `_search_sesiune`, o corutina de retea de 130 de linii, fara nicio cusatura pura de
    apucat. Calea logat-out (`_din_canonice_auto`) e acoperita comportamental de
    `test_fb_auto_adapter.py::test_listed_at_naiv_local`, reparata la TZ-3.

    `fromtimestamp` FARA `tz=` e ceasul masinii — exact ce n-are voie sa intre intr-o
    coloana de piata. Cu `tz=` ar fi legitim, deci garda cere argumentul, nu numele.
    """
    import ast
    import inspect

    from app.scrapers.auto.listings import facebook_auto_scraper as fa

    goale = [n.lineno for n in ast.walk(ast.parse(inspect.getsource(fa)))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "fromtimestamp" and not n.keywords]
    assert not goale, f"fromtimestamp fara fus, linia {goale}"
    assert "to_naive_bucuresti(ct)" in inspect.getsource(fa)


def test_2d_publi24_azi_e_ziua_pietei():
    """„azi"/„ieri" se judeca in ZIUA PIETEI, nu a masinii — specia bug-ului Kleinanzeigen.

    La 00:30 Bucuresti, o masina in UTC e inca in ziua precedenta: „azi" primea ieri.
    """
    from app.services.radar import publi24_scraper as p24

    acum_ro = datetime(2026, 9, 7, 0, 30, 0)          # ora PIETEI
    assert p24._parse_date("azi", now=acum_ro) == datetime(2026, 9, 7, 0, 0)
    assert p24._parse_date("ieri", now=acum_ro) == datetime(2026, 9, 6, 0, 0)


def test_2e_publi24_fara_an_se_ancoreaza_tot_pe_piata():
    """Anul lipsa se deduce din ANUL PIETEI, si data din viitor cade in anul trecut."""
    from app.services.radar import publi24_scraper as p24

    acum_ro = datetime(2026, 1, 1, 0, 30, 0)
    assert p24._parse_date("31 decembrie", now=acum_ro) == datetime(2025, 12, 31)


def test_2f_publi24_ancora_implicita_e_ceasul_pietei():
    """Fara `now`, functia nu are voie sa cada inapoi pe ceasul masinii."""
    from app.services.radar import publi24_scraper as p24

    azi_piata = _acum_piata().replace(hour=0, minute=0, second=0, microsecond=0)
    assert p24._parse_date("azi") == azi_piata


# ── 3. Comparatii intre ceasuri ───────────────────────────────────────────────

def test_3_too_old_masoara_pe_ceasul_pietei():
    """Anunt de 25 h cu prag de 1 zi = prea vechi, in ORICE fus.

    Masurat inainte de reparatie, sub `TZ=UTC`: fereastra 24-27 h iesea „proaspat",
    fiindca `datetime.now()` (sistem) e cu 3 h in urma ceasului pietei. Pe un server
    INAINTEA Bucurestiului semnul se inverseaza si se aruncau anunturi proaspete.
    """
    from app.utils.radar_scanner import _too_old

    assert _too_old(_acum_piata() - timedelta(hours=25), 1) is True
    assert _too_old(_acum_piata() - timedelta(hours=23), 1) is False


@pytest.mark.parametrize("ore,asteptat", [(25, True), (26, True), (28, True),
                                          (23, False), (1, False)])
def test_3b_toata_fereastra_de_dezacord(ore, asteptat):
    """Exact orele care divergeau: intre prag si prag+offset."""
    from app.utils.radar_scanner import _too_old

    assert _too_old(_acum_piata() - timedelta(hours=ore), 1) is asteptat


def test_3c_too_old_degradare_neschimbata():
    from app.utils.radar_scanner import _too_old

    assert _too_old(None, 1) is False
    assert _too_old(_acum_piata() - timedelta(days=99), None) is False
    assert _too_old("nu e data", 1) is False


def test_3d_grupuri_fb_postarea_dinainte_de_ultima_rulare_e_veche():
    """`posted_at` (piata) vs `last_run_at` (sistem): pragul se aduce pe ceasul pietei.

    Sub `TZ=UTC`, `posted_at` e cu 3 h INAINTEA lui `last_run_at`, deci criteriul de
    oprire nu se declansa niciodata si scraperul reciteste la nesfarsit postari vechi.
    Pe un server inaintea Bucurestiului s-ar fi oprit prea devreme, sarind postari noi.
    """
    from app.scrapers.facebook_group_scraper import _e_mai_veche_decat_rularea

    ultima_rulare = acum_local()                      # ceasul NOSTRU, ca in DB
    veche = _acum_piata() - timedelta(minutes=1)
    noua = _acum_piata() + timedelta(minutes=1)

    assert _e_mai_veche_decat_rularea(veche, ultima_rulare) is True
    assert _e_mai_veche_decat_rularea(noua, ultima_rulare) is False


def test_3e_grupuri_fb_degradare():
    from app.scrapers.facebook_group_scraper import _e_mai_veche_decat_rularea

    assert _e_mai_veche_decat_rularea(None, acum_local()) is False
    assert _e_mai_veche_decat_rularea(_acum_piata(), None) is False


# ── 4. Rezerva `created_at` -> `listed_at` a disparut ─────────────────────────

def test_4_postare_fb_fara_posted_at_lasa_listed_at_null():
    """O data inventata pe ceasul gresit e mai rea decat lipsa datei.

    `created_at` e momentul INSERT-ului nostru (ceasul sistemului), nu cand a fost
    publicata postarea. Ca rezerva pentru `listed_at` spunea o minciuna dubla: alta
    valoare si alt ceas.
    """
    import inspect

    from app.services import real_estate_scanner

    sursa = inspect.getsource(real_estate_scanner._save_fb_group_post)
    assert 'post.get("created_at")' not in sursa, "rezerva a revenit"
    assert 'to_naive_bucuresti(post.get("posted_at"))' in sursa


def _user_re(db):
    import uuid as _uuid

    from app.models.user import User

    email = f"tz3c_{_uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0],
             hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _kw_re(db, user_id):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    kw = RealEstateMonitorKeyword(user_id=user_id, name="TZ-3c", platform="facebook_groups",
                                  city="Bucuresti", is_active=True, tip_anunt="vanzare")
    db.add(kw)
    db.flush()
    return kw


def _post_fb(**over):
    base = dict(id=1, post_id="tz3c1", group_url="https://facebook.com/groups/imob",
                post_url=None, text="Vand apartament 3 camere, 70 mp, Titan",
                pret=120000, moneda="EUR", tip_anunt="vanzare",
                tip_proprietate="3 camere", suprafata_mp=None, etaj=None, zona=None,
                termen=None, facilitati=None, posted_at=None,
                created_at=datetime(2026, 8, 1, 10, 0, 0))
    base.update(over)
    return base


def test_4b_fara_posted_at_listed_at_ramane_null_dar_anuntul_intra_in_feed():
    """Comportamental: data lipseste, anuntul NU. `found_at` ramane, deci feed-ul il vede.

    Serverul ordoneaza feed-ul dupa `found_at.desc()`, nu dupa `listed_at`, deci un NULL
    nu scoate randul din lista; sortarea „cele mai noi postate" din client cade tot pe
    `found_at` (`sortByDateDesc("listed_at", "found_at")`).
    """
    from app.database import SessionLocal
    from app.services.real_estate_scanner import _save_fb_group_post

    db = SessionLocal()
    try:
        kw = _kw_re(db, _user_re(db).id)
        salvat = _save_fb_group_post(db, _post_fb(), kw, None, {}, eur_ron=5.0)
        assert salvat is not None, "postarea trebuie sa intre in feed"
        assert salvat.listed_at is None, "fara posted_at nu inventam o data"
        assert salvat.found_at is not None, "ceasul nostru ramane — pe el se sorteaza"
    finally:
        db.close()


def test_4c_cu_posted_at_data_e_ora_pietei():
    """Contrapartea: cand Facebook spune cand, valoarea e ora Bucurestiului acelui instant."""
    from app.database import SessionLocal
    from app.services.real_estate_scanner import _save_fb_group_post

    db = SessionLocal()
    try:
        kw = _kw_re(db, _user_re(db).id)
        postat = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        salvat = _save_fb_group_post(db, _post_fb(post_id="tz3c2", posted_at=postat),
                                     kw, None, {}, eur_ron=5.0)
        assert salvat is not None
        assert salvat.listed_at == _LA_BUCURESTI
    finally:
        db.close()
