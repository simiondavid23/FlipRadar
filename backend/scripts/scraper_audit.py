"""SA-1 — auditul de sanatate al scraperelor: chiar mai raspunde fiecare?

Apeleaza fiecare scraper VIU cu un query generic si raporteaza, per platforma, numarul
de rezultate, tipul erorii si durata. Nu repara nimic — masoara.

CE NU FACE: nu scrie in baza de date, nu trimite notificari, nu salveaza sesiuni, nu
reincearca la eroare. Singurul efect: cate o cerere pe fiecare site. De aceea poate fi
rulat oricand, inclusiv pe productie cu serviciul pornit.

ISTORIC: instrumentul asta a trait pana la SA-1 ca `scripts/diagnostics/
platform_health_probe.py` (IMP-1b) — gitignored, deci nu ajungea pe productie si n-avea
teste, iar listele lui de platforme au ramas in urma codului: dupa MKT-DEAD grupul
`marketplace` nu se mai importa, iar dupa RC-1 grupul `radar` cadea la import pe
`autovit_scraper`/`mobilede_scraper`. Sarea, pe deasupra, doua scrapere VII: `vinted`
din Radar (confundat cu varianta veche care cerea cookie — cel din Radar merge pe
libraria `vinted-scraper`, fara cookie) si `mobile_de` din Auto. Acum e comis, iar
`tests/test_scraper_audit.py` tine listele de aici sincronizate cu cele ale
scannerelor: daca cineva adauga sau scoate o platforma dintr-un scanner fara sa treaca
si pe aici, suita cade.

DE CE TREBUIE RULAT SI PE MASINA DE PRODUCTIE: platformele din
`MODEM_ROUTED_PLATFORMS` ies prin modem (alt IP, alt ASN, cu rotatie) doar acolo unde
modemul e configurat. O platforma poate fi blocata pe un drum si sanatoasa pe celalalt
— rezultatele de pe dezvoltare si de pe productie NU sunt interschimbabile.

RULARE (Windows, din backend/):
  venv\\Scripts\\python.exe scripts\\scraper_audit.py
  venv\\Scripts\\python.exe scripts\\scraper_audit.py --group radar
  venv\\Scripts\\python.exe scripts\\scraper_audit.py --only olx,vinted --no-json
  venv\\Scripts\\python.exe scripts\\scraper_audit.py --keyword bmw --max-price 20000

  Pe productie, din E:\\flipradar-prod\\backend, cu acelasi venv al instalarii:
  venv\\Scripts\\python.exe scripts\\scraper_audit.py > scripts\\audit_out\\audit.txt 2>&1

VERDICTE:
  OK      - a intors rezultate
  GOL     - a raspuns fara eroare, dar 0 rezultate (selectoare rupte / query fara acoperire)
  BLOCAT  - 403/429/captcha/timeout sau exceptie de retea
  SARIT   - cere sesiune/cookie care lipseste, sau nu se testeaza aici (motivul e afisat)

ATENTIE la `--timeout`: e INFORMATIV, mostenit ca atare de la sonda. Nu se aplica
niciunui apel — scraperele isi au propriile timeout-uri, iar un plafon impus din afara
ar cere fie thread-uri, fie un event loop propriu pentru cele sincrone. Ramane in
raport ca sa se vada cu ce intentie s-a rulat.

FACEBOOK nu face nicio cerere aici: se raporteaza doar modul efectiv (`FB_MOD`) si,
pe calea de sesiune, validitatea fisierelor de sesiune de pe disc.
"""
import argparse
import asyncio
import contextlib
import glob
import io
import json
import os
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_BACKEND, ".env"))
except Exception:
    pass

OK, GOL, BLOCAT, SARIT = "OK", "GOL", "BLOCAT", "SARIT"

# ── Platformele, pe module ───────────────────────────────────────────────────────
# Sursa de adevar raman listele scannerelor (RADAR_PLATFORMS / AUTO_PLATFORMS /
# RE_PLATFORMS). Aici sunt IMPARTITE dupa cum se testeaza:
#   GRUPURI_LIVE = se apeleaza chiar, cu o cerere reala
#   FACEBOOK     = se raporteaza fara cerere (sesiune / nucleu / bazin)
#   EXCLUSE      = nu sunt scraping deloc
# `tests/test_scraper_audit.py` verifica reuniunea celor trei contra scannerului.
GRUPURI_LIVE = {
    "radar": ["olx", "vinted", "okazii", "lajumate", "publi24"],
    "auto":  ["autovit", "olx_auto", "mobile_de", "autoscout24", "kleinanzeigen_auto"],
    "imob":  ["olx", "storia", "imobiliare_ro"],
}
FACEBOOK = {"radar": "facebook", "auto": "facebook_auto", "imob": "facebook_marketplace"}
EXCLUSE = {"imob": ["facebook_groups"]}   # ingest din DB (postari salvate), nu scraping

# Numele de log ale modulelor, pentru WARN-ul din `mod_fb`.
_MODUL_LOG = {"radar": "radar", "auto": "auto_listings", "imob": "real_estate"}

_BLOCK_MARKERS = ("403", "429", "captcha", "blocat", "forbidden", "timeout",
                  "timed out", "cloudflare", "imperva", "datadome")


def _clasifica(n: int, err: str, zgomot: str = "") -> str:
    """Verdictul. `zgomot` = ce a printat scraperul: multe scrapere inghit un 403 si
    intorc [], deci fara textul lor un blocaj ar arata identic cu "selectoare rupte"."""
    if err:
        return BLOCAT
    if n:
        return OK
    return BLOCAT if any(m in (zgomot or "").lower() for m in _BLOCK_MARKERS) else GOL


def nume_ambigue() -> set:
    """Numele care apar in mai mult de un modul (azi: `olx`, in radar si imob).
    Doar ele se prefixeaza in tabel, ca sa nu ingrosam degeaba restul randurilor."""
    vazute, ambigue = set(), set()
    for nume in GRUPURI_LIVE.values():
        for n in nume:
            if n in vazute:
                ambigue.add(n)
            vazute.add(n)
    return ambigue


def eticheta(grup: str, nume: str) -> str:
    return f"{grup}/{nume}" if nume in nume_ambigue() else nume


# ── Constructorii de probe ───────────────────────────────────────────────────────
# Fiecare intoarce [(grup, nume, callable -> lista)]. Importurile sunt LAZY (in corp),
# ca modulul sa fie importabil din teste fara sa traga tot lantul de scrapere.

def probe_radar(kw: str, max_price: float) -> list:
    from app.services.radar.lajumate_scraper import search_lajumate
    from app.services.radar.okazii_scraper import search_okazii
    from app.services.radar.olx_scraper import search_olx
    from app.services.radar.publi24_scraper import search_publi24
    from app.services.radar.vinted_scraper import search_vinted

    # Fara `skip_enrich_ids`: la un keyword NOU, olx/okazii/publi24 imbogatesc fiecare
    # rezultat cu un fetch de pagina, deci pentru ele proba masoara si calea aia, nu doar
    # cautarea. LaJumate NU mai are enrichment (LJ-2): lista API aduce deja descrierea si
    # imaginile complete, deci acolo se masoara doar cererea de lista.
    return [
        ("radar", "olx", lambda: search_olx(kw, max_price=max_price, judet=None, oras=None,
                                            condition="all", exclude_words=[], min_price=None,
                                            category=None)),
        ("radar", "vinted", lambda: search_vinted(kw, max_price=max_price, condition="all",
                                                  exclude_words=[], min_price=None,
                                                  category=None)),
        ("radar", "okazii", lambda: search_okazii(keyword=kw, page=1, max_price=max_price,
                                                  condition="all", exclude_words=[])),
        ("radar", "lajumate", lambda: search_lajumate(keyword=kw, max_price=max_price,
                                                      exclude_words=[], min_price=None,
                                                      category=None)),
        ("radar", "publi24", lambda: search_publi24(keyword=kw, max_price=max_price,
                                                    exclude_words=[], category=None)),
    ]


def probe_auto() -> list:
    from app.scrapers.auto.listings.autoscout24_scraper import search_autoscout24
    from app.scrapers.auto.listings.autovit_scraper import search_autovit
    from app.scrapers.auto.listings.kleinanzeigen_auto import search_kleinanzeigen_auto
    from app.scrapers.auto.listings.mobile_de_scraper import search_mobile_de
    from app.scrapers.auto.listings.olx_auto import search_olx_auto

    # `make_id` accepta si NUMELE marcii, nu doar id-ul numeric: scraperul il rezolva
    # prin `_resolve_make` cand nu e format din cifre.
    return [
        ("auto", "autovit", lambda: asyncio.run(search_autovit(make="bmw", filters={}))),
        ("auto", "olx_auto", lambda: asyncio.run(search_olx_auto(query="bmw", filters={}))),
        ("auto", "mobile_de", lambda: asyncio.run(search_mobile_de(make_id="bmw", filters={}))),
        ("auto", "autoscout24", lambda: asyncio.run(search_autoscout24(make="bmw", filters={}))),
        ("auto", "kleinanzeigen_auto", lambda: asyncio.run(
            search_kleinanzeigen_auto(query="bmw", make="bmw"))),
    ]


def probe_imob() -> list:
    from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro
    from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
    from app.scrapers.real_estate.storia_scraper import search_storia

    # Cheia orasului e `locatie`, NU `oras`: sonda veche trimitea `oras` si cauta la
    # nivel NATIONAL fara sa stie, fiindca scraperele ignora tacut cheile necunoscute.
    f = {"tip_anunt": "inchiriere", "locatie": "Bucuresti"}
    return [
        ("imob", "olx", lambda: asyncio.run(search_olx_real_estate(filters=dict(f)))),
        ("imob", "storia", lambda: asyncio.run(search_storia(filters=dict(f)))),
        ("imob", "imobiliare_ro", lambda: asyncio.run(search_imobiliare_ro(filters=dict(f)))),
    ]


def probe_facebook() -> list:
    """[(grup, nume, motiv)] — ZERO cereri. Raporteaza modul efectiv per modul si,
    pe calea de sesiune, cate fisiere de sesiune sunt valide."""
    from app.scrapers.facebook.mod import mod_fb

    out = []
    for modul, nume in FACEBOOK.items():
        try:
            fb_mod = mod_fb(_MODUL_LOG.get(modul, "radar"))
        except Exception as exc:
            out.append(("facebook", nume, f"nu pot citi FB_MOD: {type(exc).__name__}"))
            continue
        if fb_mod == "nucleu":
            motiv = "FB_MOD=nucleu — calea logat-out, se testeaza prin runda FB-AUDIT"
        elif fb_mod == "bazin":
            motiv = "FB_MOD=bazin — citeste din fb_pool, fara retea"
        else:
            motiv = f"FB_MOD={fb_mod} — {_stare_sesiuni()}"
        out.append(("facebook", nume, motiv))
    return out


def _stare_sesiuni() -> str:
    """Cate fisiere `facebook_session*.json` din DATA_DIR/data sunt valide.

    SA-1b: directorul e DATA_DIR/**data**, nu DATA_DIR. Acolo scrie aplicatia
    sesiunile — `app/routers/radar.py:_default_facebook_session_path` face
    `base_dir = DATA_DIR / "data"`. Sufixul e replicat literal aici, nu importat
    din router: auditul nu are voie sa depinda de routere. Varianta veche cauta
    un nivel mai sus si raporta "niciun fisier de sesiune" chiar dupa un login
    manual reusit — verdictul Facebook era fals-negativ prin constructie (bug
    mostenit din sonda `platform_health_probe.py`).

    Motivul intors poarta MEREU calea absoluta cautata, ca urmatorul fals-negativ
    de acest fel sa se vada din prima citire a raportului. "Directorul nu exista"
    si "niciun fisier in el" sunt stari diferite, cu mesaje diferite.

    Limita asumata: auditul NU deschide baza de date (principiu SA-1), deci vede
    DOAR calea default. Un user care are `RadarSettings.facebook_session_path`
    setat pe alta cale (vezi `app/services/facebook_session.py:
    resolve_facebook_session_path`, care prefera setarea) ii scapa acestei
    functii. Nu se "repara" adaugand aici acces la DB.
    """
    try:
        from pathlib import Path
        from app.paths import get_data_dir
        director = Path(get_data_dir()) / "data"
    except Exception as exc:
        return f"nu pot citi directorul de date: {type(exc).__name__}"
    if not director.is_dir():
        return f"directorul {director} nu exista (niciun login manual pe masina asta)"
    fisiere = sorted(glob.glob(os.path.join(str(director), "facebook_session*.json")))
    if not fisiere:
        return f"niciun fisier de sesiune in {director} (login manual din Setari Radar -> Facebook)"
    try:
        from app.services.radar.facebook_scraper import is_facebook_session_valid
        valide = [f for f in fisiere if is_facebook_session_valid(f)]
    except Exception as exc:
        return f"{len(fisiere)} sesiuni in {director}, validarea a crapat: {type(exc).__name__}"
    if valide:
        return f"{len(valide)}/{len(fisiere)} sesiuni valide in {director}"
    return f"{len(fisiere)} sesiuni in {director}, niciuna valida (expirate)"


# ── Rularea ──────────────────────────────────────────────────────────────────────
def _construieste(kw: str, max_price: float) -> list:
    probe = []
    for builder in (lambda: probe_radar(kw, max_price), probe_auto, probe_imob):
        try:
            probe.extend(builder())
        except Exception as exc:
            print(f"[audit] nu pot construi un grup de probe: {type(exc).__name__}: {exc}")
    return probe


def _profil() -> str:
    try:
        from app.utils.http_profile import DEFAULT_IMPERSONATE
        from curl_cffi.requests.impersonate import REAL_TARGET_MAP
        return f"{DEFAULT_IMPERSONATE} -> {REAL_TARGET_MAP.get(DEFAULT_IMPERSONATE, DEFAULT_IMPERSONATE)}"
    except Exception:
        return "?"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Auditul de sanatate al scraperelor (live).")
    ap.add_argument("--only", default="", help="lista de nume, separate prin virgula")
    ap.add_argument("--group", default="", help="radar,auto,imob,facebook")
    ap.add_argument("--keyword", default="iphone", help="query generic pentru marketplace-uri")
    ap.add_argument("--max-price", type=float, default=5000.0)
    ap.add_argument("--timeout", type=int, default=90,
                    help="INFORMATIV: nu se aplica niciunui apel (vezi docstring)")
    ap.add_argument("--json", dest="json_path", default="",
                    help="unde se scrie raportul JSON (implicit: scripts/audit_out/audit_<data>.json)")
    ap.add_argument("--no-json", action="store_true", help="nu scrie niciun fisier")
    args = ap.parse_args(argv)

    probe = _construieste(args.keyword, args.max_price)
    doar = {x.strip() for x in args.only.split(",") if x.strip()}
    grupuri = {x.strip() for x in args.group.split(",") if x.strip()}
    if doar:
        probe = [p for p in probe if p[1] in doar]
    if grupuri:
        probe = [p for p in probe if p[0] in grupuri]

    rutate = os.environ.get("MODEM_ROUTED_PLATFORMS", "") or "(gol)"
    profil = _profil()
    print(f"profil de impersonare : {profil}")
    print(f"platforme prin modem  : {rutate}")
    print(f"keyword / pret maxim  : {args.keyword!r} / {args.max_price}")
    print(f"timeout (informativ)  : {args.timeout}s")
    print(f"platforme de sondat   : {len(probe)}")
    print()

    rezultate = []
    for grup, nume, fn in probe:
        t0 = time.monotonic()
        n, err = 0, ""
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                r = fn()
            n = len(r or [])
        except Exception as exc:
            err = f"{type(exc).__name__}: {str(exc)[:90]}"
        dt = time.monotonic() - t0
        zgomot = buf.getvalue().strip()
        verdict = _clasifica(n, err, zgomot)
        detaliu = err or (zgomot.splitlines()[-1][:70] if zgomot else "")
        rezultate.append({"grup": grup, "nume": nume, "rezultate": n,
                          "verdict": verdict, "durata_s": round(dt, 1), "detaliu": detaliu})
        print(f"  {eticheta(grup, nume):<20} {verdict:<7} {n:>4} rezultate  {dt:6.1f}s  {detaliu}")

    if not grupuri or "facebook" in grupuri:
        try:
            fb = probe_facebook()
        except Exception as exc:
            fb = [("facebook", "facebook", f"constructorul a crapat: {type(exc).__name__}")]
        for grup, nume, motiv in fb:
            if doar and nume not in doar:
                continue
            rezultate.append({"grup": grup, "nume": nume, "rezultate": 0,
                              "verdict": SARIT, "durata_s": 0.0, "detaliu": motiv})
            print(f"  {nume:<20} {SARIT:<7}    -             -   {motiv}")

    _tabel(rezultate)

    cale_json = ""
    if not args.no_json:
        cale_json = args.json_path or os.path.join(
            _HERE, "audit_out", f"audit_{datetime.now():%Y-%m-%d_%H%M}.json")
        try:
            os.makedirs(os.path.dirname(cale_json) or ".", exist_ok=True)
            with open(cale_json, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "profil_impersonare": profil,
                    "modem_routed_platforms": rutate,
                    "keyword": args.keyword,
                    "max_price": args.max_price,
                    "probe": rezultate,
                }, f, ensure_ascii=False, indent=2)
            print(f"raport JSON: {cale_json}")
        except Exception as exc:
            print(f"[audit] nu pot scrie JSON-ul: {type(exc).__name__}: {exc}")
    return 0


def _tabel(rezultate: list) -> None:
    print()
    print("=" * 78)
    print(f"{'GRUP':<10} {'PLATFORMA':<22} {'REZULTATE':>9}  {'VERDICT':<8} {'DURATA':>7}")
    print("-" * 78)
    for r in rezultate:
        sarit = r["verdict"] == SARIT
        rez = "-" if sarit else str(r["rezultate"])
        dur = "-" if sarit else f"{r['durata_s']:.1f}s"
        print(f"{r['grup']:<10} {eticheta(r['grup'], r['nume']):<22} {rez:>9}  "
              f"{r['verdict']:<8} {dur:>7}")
    print("-" * 78)
    for v in (OK, GOL, BLOCAT, SARIT):
        nume = [eticheta(r["grup"], r["nume"]) for r in rezultate if r["verdict"] == v]
        if nume:
            print(f"{v:<7} ({len(nume):>2}): {', '.join(nume)}")
    print("=" * 78)


if __name__ == "__main__":
    sys.exit(main())
