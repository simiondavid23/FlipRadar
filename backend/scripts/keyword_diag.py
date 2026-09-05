"""TOOL-1 — „de ce nu-mi da keyword-ul asta nimic?", pentru orice platforma Radar.

LA CE RASPUNDE: un keyword e activ, platforma merge in sonda de sanatate, dar feed-ul
ramane gol. Unealta reproduce, cu configuratia REALA din baza de date, tot lantul
keyword -> scanner -> feed si spune LA CE TREAPTA se pierd anunturile.

  Faza A (fara retea) — starea din DB: ce keyword-uri exista pe platforma, daca
    platforma e activata in settings, daca scanul e „due", ce plafon de paginare s-ar
    aplica, cati external_id sunt deja marcati „vazuti", ce listinguri exista, cursul.
  Faza B (cu retea) — apelul REAL al scannerului prin `_run_scraper`, urmat de decizia
    pe care ar lua-o `_scan_user` pentru FIECARE rezultat, in ordinea reala:
    SEEN -> TOO_OLD -> FILTRAT_MARJA -> KEPT, plus histograma.

La final, o linie `VERDICT:` per keyword, care numeste PRIMA treapta la care se pierd
anunturile.

CE NU FACE: nu scrie NIMIC in baza de date — doar SELECT-uri, niciun `add`, niciun
`commit`, niciun `_mark_seen`, nicio notificare. Helper-ele de decizie sunt IMPORTATE
din `app.utils.radar_scanner`, nu reimplementate, iar Faza B trece prin `_run_scraper`,
adica exact dispatch-ul din `_scan_user` — asa unealta nu poate diverge de productie pe
nicio platforma, si nu are nevoie de URL-uri scrise de mana per scraper.

RULARE
  dev:         cd C:\\licenta\\flipRadar\\backend
               venv\\Scripts\\python.exe scripts\\keyword_diag.py --platforma lajumate --fara-retea
               venv\\Scripts\\python.exe scripts\\keyword_diag.py --platforma lajumate
  productie:   cd E:\\flipradar-prod\\backend
               venv\\Scripts\\python.exe scripts\\keyword_diag.py --platforma olx --fara-retea
  (scriptul e in repo, deci ajunge pe productie prin git — spre deosebire de sonda din
   care s-a nascut, care statea in `scripts/diagnostics/`, gitignored.)

ARGUMENTE
  --platforma NUME     OBLIGATORIU, validat contra `RADAR_PLATFORMS`
  --keyword-id N       doar keyword-ul cu acest id
  --max-keywords N     cate keyword-uri se apeleaza in Faza B (implicit 3)
  --fara-retea         doar Faza A (zero cereri catre site-urile scanate)
  --permite-facebook   permite Faza B pe `facebook` (consuma bugetul contului)

ISTORIC: portata din `scripts/diagnostics/sonda_lajumate_keyword.py` (SONDA-LJ2,
2026-09-03), care in trei rulari a diagnosticat trei probleme diferite — filtrul de pret
ignorat de SSR-ul LaJumate, o platforma fara niciun keyword, si `platform_facebook_enabled
= False` in setari. Faza B a sondei era cablata pe LaJumate (`_build_query`, URL construit
de mana); TOOL-1 a inlocuit-o cu `_run_scraper`, deci merge pe orice platforma.
"""
import argparse
import os
import random
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# load_dotenv INAINTE de orice import din `app`: DATABASE_URL e citit la importul
# `app.config`, deci un .env incarcat mai tarziu n-ar mai avea niciun efect.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_BACKEND, ".env"))
except Exception as _exc:  # pragma: no cover — diagnostic
    print(f"[AVERTISMENT] load_dotenv a esuat: {type(_exc).__name__}: {_exc}")

# Platformele pe care se face enrichment de detaliu — `_scan_user` le construieste
# `skip_enrich_ids`. Sursa: radar_scanner.py:2483.
_PLATFORME_CU_ENRICHMENT = ("okazii", "lajumate", "publi24")


def _linie(ch="-", n=78):
    print(ch * n)


def _titlu(text):
    print()
    _linie("=")
    print(text)
    _linie("=")


def _naiv_utc(dt):
    """Datetime comparabil cu `datetime.utcnow()`: aware -> UTC naiv, naiv -> neschimbat."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _fmt(v, lipsa="-"):
    return lipsa if v is None else v


def platforme_valide() -> list:
    """Lista de platforme acceptate = exact `RADAR_PLATFORMS`. Importul e LOCAL ca
    modulul sa poata fi importat fara sa atinga `app` (si deci baza de date)."""
    from app.utils.radar_scanner import RADAR_PLATFORMS
    return list(RADAR_PLATFORMS)


def _incarca_modelele():
    """Registrul de mappere SQLAlchemy trebuie sa fie COMPLET inainte de prima
    interogare: `User` are relationship-uri catre modele pe care unealta nu le-ar
    importa niciodata singura, iar configurarea mapperelor crapa cu InvalidRequestError
    la primul `db.query`. In productie le importa `app.main` una cate una; aici mergem
    pe pachet, ca lista sa nu poata diverge. Intoarce lista de esecuri."""
    import importlib
    import pkgutil
    import app.models as _modele
    esecuri = []
    for m in pkgutil.iter_modules(_modele.__path__):
        try:
            importlib.import_module(f"app.models.{m.name}")
        except Exception as exc:
            esecuri.append(f"{m.name}: {type(exc).__name__}: {str(exc)[:120]}")
    return esecuri


# ── decizia per anunt, PURA ─────────────────────────────────────────────────────
def decide(listing: dict, kw, seen: bool, eur_ron, usd_ron=None, cursuri=None) -> str:
    """Ce ar face `_scan_user` cu acest anunt, ca text care INCEPE cu verdictul.

    Ordinea e cea din scanner si CONTEAZA: un anunt si vazut, si vechi iese `SEEN`,
    fiindca `_already_seen` se verifica INAINTEA lui `_too_old` (radar_scanner.py:2571
    vs. filtrul de vechime de dupa). Inversarea ar da alt verdict pe aceleasi date.

    Pura: nu atinge baza (`seen` se paseaza gata calculat) si nu atinge reteaua
    (cursurile se paseaza). Importurile sunt locale din acelasi motiv ca la
    `platforme_valide`.
    """
    from app.services.radar.scorer import calculate_score
    from app.utils import radar_scanner as RS

    if not listing.get("external_id"):
        return "FARA_EXTERNAL_ID"
    if seen:
        return "SEEN"
    if RS._too_old(listing.get("listed_at"), getattr(kw, "max_age_days", None)):
        return f"TOO_OLD (max_age_days={getattr(kw, 'max_age_days', None)})"

    pret_ron = RS._price_to_ron(listing.get("price"), listing.get("currency"),
                               eur_ron, usd_ron, cursuri=cursuri)
    sd = calculate_score(
        listing_price=pret_ron or 0,
        resale_price=kw.resale_price,
        min_margin_pct=kw.min_margin_pct or 10.0,
        grade_a_min=kw.grade_a_min,
        grade_b_min=kw.grade_b_min,
        grade_c_min=kw.grade_c_min,
    )
    marja = sd.get("margin_pct")
    marja_s = f"{marja:.1f}%" if isinstance(marja, (int, float)) else str(marja)
    if sd["filtered"] and sd["score"] is None:
        return (f"FILTRAT_MARJA (marja {marja_s}, pret_ron={pret_ron}, "
                f"resale={kw.resale_price})")
    return (f"KEPT grad {sd['score']} marja {marja_s} "
            f"(pret_ron={pret_ron}, filtered={sd['filtered']})")


# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="keyword_diag.py",
        description="TOOL-1 — de ce nu da nimic un keyword Radar, pe orice platforma")
    ap.add_argument("--platforma", required=True, help="platforma diagnosticata")
    ap.add_argument("--keyword-id", type=int, default=None, help="doar keyword-ul cu acest id")
    ap.add_argument("--max-keywords", type=int, default=3,
                    help="cate keyword-uri se apeleaza in Faza B (implicit 3)")
    ap.add_argument("--fara-retea", action="store_true", help="doar Faza A")
    ap.add_argument("--permite-facebook", action="store_true",
                    help="permite Faza B pe facebook (consuma bugetul contului)")
    args = ap.parse_args(argv)
    platforma = (args.platforma or "").strip().lower()

    valide = platforme_valide()
    if platforma not in valide:
        print(f"EROARE: platforma {args.platforma!r} nu e o platforma Radar.")
        print(f"        Platforme valide (RADAR_PLATFORMS): {', '.join(valide)}")
        print("        Daca platforma exista in alt modul (Auto, Imobiliare), unealta asta")
        print("        nu o acopera — ea merge pe lantul Radar Piata.")
        return 2

    print(f"TOOL-1 keyword_diag · platforma={platforma} · fara_retea={args.fara_retea} · "
          f"max_keywords={args.max_keywords} · keyword_id={_fmt(args.keyword_id, '(toate)')}")
    print(f"pornita la {datetime.now().isoformat(timespec='seconds')} (local) / "
          f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} (UTC)")
    print(f"backend pe sys.path: {_BACKEND}")

    # -- A1 — baza de date ----------------------------------------------------
    _titlu("FAZA A · 1 — BAZA DE DATE")
    from app.config import DATABASE_URL, DATA_DIR
    print(f"DATA_DIR      = {DATA_DIR}")
    print(f"DATABASE_URL  = {DATABASE_URL}")
    print(f"env DATABASE_URL       = {_fmt(os.getenv('DATABASE_URL'), '(nesetat)')}")
    print(f"env FLIPRADAR_DATA_DIR = {_fmt(os.getenv('FLIPRADAR_DATA_DIR'), '(nesetat)')}")

    if DATABASE_URL.startswith("sqlite"):
        cale = DATABASE_URL.split("///", 1)[-1] if "///" in DATABASE_URL else ""
        cale_abs = os.path.abspath(cale) if cale else ""
        exista = os.path.isfile(cale_abs) if cale_abs else False
        print(f"fisier SQLite = {cale_abs}")
        print(f"exista        = {exista}")
        if not exista:
            print()
            print("STOP: fisierul bazei de date NU exista la calea de mai sus.")
            print("      Rulezi din directorul gresit (sau .env-ul de productie nu e citit).")
            print("      Nimic din ce urmeaza n-ar masura baza reala — ies acum.")
            return 2
        dim = os.path.getsize(cale_abs)
        print(f"dimensiune    = {dim} octeti ({dim / 1048576.0:.2f} MiB)")
        print(f"modificat     = "
              f"{datetime.fromtimestamp(os.path.getmtime(cale_abs)).isoformat(timespec='seconds')} (local)")
    else:
        print("dialect non-SQLite — sar peste verificarea fisierului")

    esecuri = _incarca_modelele()
    if esecuri:
        print("[AVERTISMENT] module din app.models care nu s-au importat:")
        for e in esecuri:
            print(f"  {e}")

    from app.database import SessionLocal
    from app.models.log_entry import LogEntry
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_listing import RadarListing
    from app.models.radar_seen_id import RadarSeenId
    from app.models.radar_settings import RadarSettings
    from app.services import bnr_exchange, currency_service
    from app.utils import radar_scanner as RS

    db = SessionLocal()
    cod_iesire = 0
    verdicte = {}
    try:
        toate = db.query(RadarKeyword).filter(RadarKeyword.is_active == True).all()  # noqa: E712

        def _platformele(kw):
            if kw.platform:
                return [(kw.platform or "").lower()]
            return [(p or "").lower() for p in RS._parse_json_list(kw.platforms)]

        kws = [k for k in toate if platforma in _platformele(k)]
        if args.keyword_id is not None:
            kws = [k for k in kws if k.id == args.keyword_id]

        # -- A2 — loguri ------------------------------------------------------
        _titlu("FAZA A · 2 — LOGURI (log_entries, module='radar')")
        log_pers_raw = os.getenv("LOG_DB_PERSISTENCE", "false")
        print(f"LOG_DB_PERSISTENCE = {log_pers_raw!r}")
        if log_pers_raw.lower() == "true":
            from sqlalchemy import func as sqlfunc, or_
            nevoi = [f"%{platforma}%"] + [f'%keyword "{(k.name or "").lower()}"%' for k in kws]
            randuri = (
                db.query(LogEntry)
                .filter(LogEntry.module == "radar")
                .filter(or_(*[sqlfunc.lower(LogEntry.message).like(n) for n in nevoi]))
                .order_by(LogEntry.created_at.desc()).limit(40).all()
            )
            print(f"tipare cautate: {nevoi}")
            print(f"{len(randuri)} randuri (ultimele 40, desc dupa created_at)")
            _linie()
            for r in randuri:
                ts = r.created_at.isoformat(timespec="seconds") if r.created_at else "-"
                print(f"{ts} | {r.level:<5} | {r.message}")
            if not randuri:
                print("(niciun rand care sa se potriveasca)")
        else:
            print("loguri nepersistate — se citesc din UI Live Logs")

        # -- A3 — keyword-urile -----------------------------------------------
        _titlu(f"FAZA A · 3 — KEYWORD-URI ACTIVE PE '{platforma}'")
        print(f"RadarKeyword is_active=True, total: {len(toate)}")
        if not kws:
            print()
            print(f"!!! NICIUN KEYWORD ACTIV PE PLATFORMA '{platforma.upper()}' !!!")
            print(f"    E DEJA UN VERDICT: jobul radar_scan_{platforma} n-are ce scana.")
            print("    (nici `platform`, nici lista JSON `platforms` nu contin platforma)")
            print()
            print("    Keyword-urile active si platformele lor, pentru context:")
            for k in toate:
                print(f"      id={k.id} user={k.user_id} name={k.name!r} "
                      f"platform={k.platform!r} platforms={k.platforms!r}")
        else:
            print(f"potrivite pe '{platforma}': {len(kws)}")
        for k in kws:
            _linie()
            print(f"id                        = {k.id}")
            print(f"user_id                   = {k.user_id}")
            print(f"name                      = {k.name!r}")
            print(f"platform                  = {k.platform!r}")
            print(f"platforms                 = {k.platforms!r}")
            print(f"max_price                 = {k.max_price}")
            print(f"min_price                 = {k.min_price}")
            print(f"resale_price              = {k.resale_price}")
            print(f"min_margin_pct            = {k.min_margin_pct}")
            print(f"grade_a_min/b/c           = {k.grade_a_min} / {k.grade_b_min} / {k.grade_c_min}")
            print(f"category                  = {k.category!r}")
            print(f"condition                 = {k.condition!r}")
            print(f"judet                     = {k.judet!r}")
            print(f"oras                      = {k.oras!r}")
            print(f"poll_interval_minutes     = {k.poll_interval_minutes}")
            print(f"max_age_days              = {k.max_age_days}")
            print(f"active_hours_start/end    = {k.active_hours_start} / {k.active_hours_end}")
            print(f"exclude_words             = {k.exclude_words!r}")
            print(f"exclude_matching_mode     = {getattr(k, 'exclude_matching_mode', None)!r}")
            print(f"exclude_description_words = {getattr(k, 'exclude_description_words', None)!r}")
            print(f"platform_last_scan (brut) = {k.platform_last_scan!r}")
            print(f"last_scan_at              = {k.last_scan_at}")

        # -- A4 — settings per user -------------------------------------------
        _titlu("FAZA A · 4 — SETTINGS (platforma activata?)")
        settings_per_user = {}
        for uid in sorted({k.user_id for k in kws}):
            s = db.query(RadarSettings).filter(RadarSettings.user_id == uid).first()
            settings_per_user[uid] = s
            _linie()
            print(f"user_id = {uid}")
            if s is None:
                print("  RadarSettings: NU EXISTA RAND (in productie l-ar crea "
                      "_get_or_create_settings cu valorile implicite; unealta NU scrie)")
                continue
            atr = f"platform_{platforma}_enabled"
            print(f"  {atr} (brut) = {getattr(s, atr, '<atribut inexistent>')!r}")
            print(f"  _platform_enabled_in_settings({platforma!r}) = "
                  f"{RS._platform_enabled_in_settings(platforma, s)}")

        # -- A5 — decizia de scan ---------------------------------------------
        _titlu("FAZA A · 5 — DECIZIA DE SCAN (helperele reale)")
        blocaje_per_kw = {}
        for k in kws:
            _linie()
            print(f"keyword id={k.id} {k.name!r}")
            ore = RS._is_within_active_hours(k)
            due = RS._platform_scan_due(k, platforma)
            stamps = RS._parse_platform_last_scan(k)
            first_scan = platforma not in stamps and (k.last_scan_at is None or bool(stamps))
            page_cap = RS._page_cap_for(platforma, first_scan)
            fast = (k.poll_interval_minutes or 5) < 5
            cap_fast = (1 if page_cap is None else min(page_cap, 1)) if fast else page_cap
            s = settings_per_user.get(k.user_id)
            enabled = RS._platform_enabled_in_settings(platforma, s) if s is not None else None
            for eticheta, valoare in (
                ("_is_within_active_hours(kw)", ore),
                (f"_platform_scan_due(kw, {platforma!r})", due),
                ("_parse_platform_last_scan(kw)", repr(stamps)),
                ("_first_scan (formula din _scan_user)", first_scan),
                (f"_page_cap_for({platforma!r}, {first_scan})", page_cap),
                (f"plafon FAST-1 (interval < 5 min = {fast})", cap_fast),
                ("platforma activata in settings", enabled),
            ):
                print(f"  {eticheta:<44} = {valoare}")
            blocaje = []
            if enabled is False:
                blocaje.append("platforma dezactivata in settings")
            if not ore:
                blocaje.append("interval orar inactiv")
            if not due:
                blocaje.append("scan nu e due (poll_interval neexpirat)")
            blocaje_per_kw[k.id] = blocaje
            print(f"  >>> {'AR SCANA ACUM' if not blocaje else 'NU AR SCANA: ' + ' · '.join(blocaje)}")

        # -- A6 — contoare din DB ---------------------------------------------
        _titlu("FAZA A · 6 — CONTOARE DIN DB (per user + platforma)")
        acum_naiv = datetime.now(timezone.utc).replace(tzinfo=None)
        c24, c7z = acum_naiv - timedelta(hours=24), acum_naiv - timedelta(days=7)
        print(f"referinta 'acum' (UTC naiv) = {acum_naiv.isoformat(timespec='seconds')}")
        for uid in sorted({k.user_id for k in kws}):
            _linie()
            print(f"user_id = {uid} · platforma = {platforma}")
            seen_n = [_naiv_utc(t) for (t,) in db.query(RadarSeenId.seen_at).filter(
                RadarSeenId.user_id == uid, RadarSeenId.platform == platforma).all()]
            print(f"  RadarSeenId  total = {len(seen_n)} · "
                  f"ultimele 24h = {sum(1 for t in seen_n if t and t >= c24)} · "
                  f"ultimele 7 zile = {sum(1 for t in seen_n if t and t >= c7z)}")
            val = [t for t in seen_n if t]
            if val:
                print(f"               cel mai vechi = {min(val).isoformat(timespec='seconds')} · "
                      f"cel mai nou = {max(val).isoformat(timespec='seconds')}")

            fa = [(_naiv_utc(f), sc) for (f, sc) in db.query(
                RadarListing.found_at, RadarListing.score).filter(
                RadarListing.user_id == uid, RadarListing.platform == platforma).all()]
            print(f"  RadarListing total = {len(fa)} · "
                  f"ultimele 24h = {sum(1 for f, _ in fa if f and f >= c24)} · "
                  f"ultimele 7 zile = {sum(1 for f, _ in fa if f and f >= c7z)}")
            dist = {}
            for _, sc in fa:
                cheie = sc if sc is not None else "None"
                dist[cheie] = dist.get(cheie, 0) + 1
            print("  distributie scor: " + (
                " · ".join(f"{g}={dist.get(g, 0)}" for g in ("A", "B", "C", "D", "None"))
                if fa else "(niciun rand)"))
            ultime = (db.query(RadarListing)
                      .filter(RadarListing.user_id == uid, RadarListing.platform == platforma)
                      .order_by(RadarListing.found_at.desc()).limit(5).all())
            print("  ultimele 5 randuri (found_at | keyword_id | score | price | title[:60]):")
            for r in ultime:
                f = r.found_at.isoformat(timespec="seconds") if r.found_at else "-"
                print(f"    {f} | kw={r.keyword_id} | {_fmt(r.score)} | "
                      f"{r.price} {r.currency} | {(r.title or '')[:60]}")
            if not ultime:
                print("    (niciun rand)")

        # -- A7 — cursurile ----------------------------------------------------
        _titlu("FAZA A · 7 — CURS BNR")
        print("(singurul apel din Faza A care poate atinge reteaua: curs.bnr.ro. Zero cereri")
        print(" catre site-urile scanate, deci `--fara-retea` ramane valabil pentru masuratoare.)")
        eur_ron = usd_ron = None
        cursuri = {}
        try:
            eur_ron = bnr_exchange.get_eur_ron()
            print(f"get_eur_ron() = {eur_ron}")
        except Exception as exc:
            print(f"get_eur_ron() A CRAPAT: {type(exc).__name__}: {str(exc)[:200]}")
        try:
            usd_ron = bnr_exchange.get_usd_ron()
            print(f"get_usd_ron() = {usd_ron}")
        except Exception as exc:
            print(f"get_usd_ron() A CRAPAT: {type(exc).__name__}: {str(exc)[:200]}")
        try:
            cursuri = currency_service.catalog_ron()
            print(f"len(catalog_ron()) = {len(cursuri)} coduri (CUR-1)")
        except Exception as exc:
            print(f"catalog_ron() A CRAPAT: {type(exc).__name__}: {str(exc)[:200]}")

        # =====================================================================
        # Ordinea garzilor: `--fara-retea` (userul a cerut explicit doar Faza A), apoi
        # Facebook (poarta de POLITICA — se aplica indiferent ce e in baza, ca mesajul
        # despre buget sa apara si cand n-ai niciun keyword), apoi lipsa keyword-urilor.
        sarita = None
        if args.fara_retea:
            sarita = "--fara-retea"
        elif platforma == "facebook" and not args.permite_facebook:
            sarita = ("calea de sesiune — ruleaza cu --permite-facebook daca accepti "
                      "o cautare pe contul tau")
        elif not kws:
            sarita = "niciun keyword pe platforma"
        if sarita:
            _titlu(f"FAZA B — SARITA ({sarita})")
        else:
            _titlu(f"FAZA B — APELUL REAL AL SCANNERULUI ({platforma})")
            print("Apelul trece prin `_run_scraper`, adica exact dispatch-ul din `_scan_user`")
            print("(radar_scanner.py:2495) — deci nu poate diverge de productie.")

            for nr, k in enumerate(kws[:args.max_keywords]):
                if nr > 0:
                    pauza = random.uniform(3, 5)
                    print(f"\n(pauza {pauza:.1f}s)")
                    time.sleep(pauza)
                _linie("=")
                print(f"KEYWORD id={k.id} user={k.user_id} name={k.name!r}")
                _linie("=")

                settings = settings_per_user.get(k.user_id)
                if settings is None:
                    print("SARIT: userul n-are rand in RadarSettings. In productie l-ar crea")
                    print("       `_get_or_create_settings`; unealta NU scrie in baza.")
                    verdicte[k.id] = "userul n-are rand in RadarSettings"
                    continue

                # exclude_words exact ca in _scan_user (radar_scanner.py:2440 si :2443).
                # ATENTIE: in modul `advanced` NU se goleste aici — `_run_scraper` o face
                # singur (radar_scanner.py:1895), iar apelantul paseaza lista intreaga.
                exclude_words = RS._parse_json_list(k.exclude_words)
                adv = (getattr(k, "exclude_matching_mode", "simple") or "simple") == "advanced"
                print(f"exclude_words (radar_scanner.py:2440) = {exclude_words!r}")
                print(f"advanced      (radar_scanner.py:2443) = {adv}")

                # _skip_enrich exact ca in _scan_user (radar_scanner.py:2482-2489)
                skip_enrich = None
                if platforma in _PLATFORME_CU_ENRICHMENT:
                    skip_enrich = {
                        ext for (ext,) in db.query(RadarSeenId.external_id)
                        .filter(RadarSeenId.user_id == k.user_id,
                                RadarSeenId.platform == platforma).all()
                    }
                print(f"skip_enrich_ids (radar_scanner.py:2482) = "
                      f"{len(skip_enrich) if skip_enrich is not None else None} id-uri")

                t0 = time.time()
                try:
                    rezultate = RS._run_scraper(platforma, k, settings, exclude_words,
                                                page=1, advanced=adv, db=db,
                                                skip_enrich_ids=skip_enrich)
                except Exception as exc:
                    # o eroare E un rezultat: se raporteaza, nu se reincearca
                    print(f"EROARE: {type(exc).__name__}: {str(exc)[:200]}")
                    traceback.print_exc()
                    verdicte[k.id] = f"_run_scraper a ridicat {type(exc).__name__}"
                    cod_iesire = 1
                    continue
                dt = time.time() - t0
                print(f"len(rezultate) = {len(rezultate)}  ({dt:.1f}s)")

                hist = {"SEEN": 0, "TOO_OLD": 0, "FILTRAT_MARJA": 0, "KEPT": 0,
                        "FARA_EXTERNAL_ID": 0}
                for r in rezultate:
                    ext = r.get("external_id")
                    seen = bool(ext) and RS._already_seen(db, k.user_id, platforma, ext)
                    verdict = decide(r, k, seen, eur_ron, usd_ron, cursuri)
                    hist[verdict.split()[0].split("(")[0]] += 1
                    print(f"  {str(ext)[:22]:<22} | {r.get('price')} {r.get('currency')} | "
                          f"{r.get('listed_at')} | {(r.get('title') or '')[:50]}")
                    print(f"      -> {verdict}")
                print(f"HISTOGRAMA kw={k.id} {k.name!r}: brute {len(rezultate)} -> " +
                      " · ".join(f"{n.lower()} {c}" for n, c in hist.items()))

                if blocaje_per_kw.get(k.id):
                    verdicte[k.id] = blocaje_per_kw[k.id][0]
                elif not rezultate:
                    verdicte[k.id] = "scraperul a intors 0 rezultate BRUTE"
                elif hist["KEPT"]:
                    verdicte[k.id] = f"OK — {hist['KEPT']} anunturi ar intra in feed"
                elif hist["SEEN"] == len(rezultate):
                    verdicte[k.id] = "toate anunturile sunt deja marcate SEEN"
                elif hist["TOO_OLD"] == len(rezultate):
                    verdicte[k.id] = f"toate anunturile sunt TOO_OLD (max_age_days={k.max_age_days})"
                elif hist["FILTRAT_MARJA"] == len(rezultate):
                    verdicte[k.id] = f"toate anunturile cad pe marja (resale_price={k.resale_price})"
                else:
                    verdicte[k.id] = ("niciun anunt nu trece — amestec de "
                                      f"seen/too_old/marja: {hist}")

        # -- VERDICT ----------------------------------------------------------
        _titlu("VERDICT")
        if not kws:
            print(f"VERDICT: niciun keyword activ pe platforma '{platforma}' — "
                  f"jobul radar_scan_{platforma} n-are ce scana")
        else:
            for k in kws:
                motiv = verdicte.get(k.id)
                if motiv is None:
                    blocaje = blocaje_per_kw.get(k.id) or []
                    motiv = (blocaje[0] if blocaje
                             else "Faza B nu a rulat — nu se poate numi treapta care pierde anunturi")
                print(f"VERDICT: kw={k.id} {k.name!r} -> {motiv}")
        return cod_iesire
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
