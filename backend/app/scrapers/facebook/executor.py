"""FB-6a — executorul: consuma planificatorul si umple bazinul.

Cablat la APScheduler sub garda `FB_EXECUTOR` (implicit OPRIT). La FB-6a doar
UMPLE `fb_pool`; citirea din bazin si comutarea consumatorilor pe logout vin la FB-6b.

DE CE UN SINGUR PLANIFICATOR VIU: frana (§6.4) e stare IN MEMORIE — bugetul redus si
momentul ultimului incident traiesc pe instanta. Daca am construi un Planificator nou
la fiecare tick, frana s-ar reseta la fiecare 5 minute si n-ar apara nimic. Dar
sesiunea SQLAlchemy nu are voie sa stea deschisa intre tick-uri (conexiune tinuta
degeaba, obiecte invechite). Solutia: UN SINGUR obiect Planificator la nivel de modul,
caruia i se schimba `sesiune` la inceputul fiecarui tick. Alegerea e deliberata si e
singurul loc din nucleu cu stare globala.

BUGETUL SE NUMARA IN CERERI, NU IN PERECHI: un keyword imobiliar GOL se expandeaza in
8 termeni (designul Q din FB-4), deci o singura pereche poate costa 8 cereri. Daca am
numara perechi, un tick de 12 ar trimite pana la 96 de cereri.
"""
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.models.fb_pool import FbPoolListing
from app.models.fb_scan_state import FbScanState
from app.services.log_manager import log_manager

from .anchors import dupa_slug
from .client import search_cu_stare
from .planner import Planificator, config_din_env

_TTL_IMPLICIT_ORE = 48
_PRAG_ESEC_TOTAL = 3        # tick-uri consecutive numai cu esec -> WARN zgomotos

_lock = threading.Lock()
_planificator = None
_ultimul_tick = None
_tickuri_numai_esec = 0


def _acum():
    return datetime.now(timezone.utc)


def _ttl_ore() -> float:
    try:
        return float(os.getenv("FB_POOL_TTL_ORE") or _TTL_IMPLICIT_ORE)
    except (TypeError, ValueError):
        return _TTL_IMPLICIT_ORE


def _obtine_planificator(db):
    """Planificatorul viu, cu sesiunea schimbata pe cea a tick-ului curent."""
    global _planificator
    if _planificator is None:
        _planificator = Planificator(db, config_din_env())
    else:
        _planificator.sesiune = db
    return _planificator


def _in_ore_active(kw) -> bool:
    """Fereastra orara a keyword-ului (suporta intervalul peste miezul noptii).

    Foloseste helperul EXISTENT din radar_scanner. Import lenes: `radar_scanner` e un
    modul greu care importa la randul lui scraperele, iar executorul trebuie sa ramana
    importabil singur (in teste, fara aplicatie). Logica e duplicata identic in cele
    trei scannere; nu exista un helper comun de nivel util.
    """
    try:
        from app.utils.radar_scanner import _is_within_active_hours
        return bool(_is_within_active_hours(kw))
    except Exception:
        s = getattr(kw, "active_hours_start", None)
        e = getattr(kw, "active_hours_end", None)
        if s is None or e is None:
            return True
        h = datetime.now().hour
        return (s <= h < e) if s <= e else (h >= s or h < e)


def _platforme_radar(kw) -> list:
    """Setul de platforme al unui keyword Radar, derivat ca in radar_scanner:
    `platform` are prioritate; altfel se parseaza JSON-ul `platforms`."""
    if getattr(kw, "platform", None):
        return [kw.platform]
    import json
    try:
        return list(json.loads(kw.platforms or "[]"))
    except Exception:
        return []


def _keywords_facebook(db) -> list:
    """Keyword-urile ACTIVE care au Facebook ca platforma, din toate trei modulele.

    Intoarce dicturi: modul, keyword_id, termeni, in_ore_active.
    """
    from app.models.auto_keyword import AutoKeyword
    from app.models.radar_keyword import RadarKeyword
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    out = []

    for kw in db.query(RadarKeyword).filter(RadarKeyword.is_active.is_(True)).all():
        if "facebook" not in _platforme_radar(kw):
            continue
        termen = (kw.name or "").strip()
        if not termen:
            continue
        out.append({"modul": "radar", "keyword_id": kw.id, "termeni": [termen],
                    "in_ore_active": _in_ore_active(kw)})

    for kw in db.query(AutoKeyword).filter(AutoKeyword.is_active.is_(True)).all():
        if (kw.platform or "") != "facebook_auto":
            continue
        # Acelasi termen ca in auto_listings_scanner: make + model + query, fara goluri.
        termen = " ".join(x for x in [kw.make, kw.model, kw.query] if x).strip()
        if not termen:
            # Un termen gol la Auto nu are semantica de expandare (aia e doar la
            # Imobiliare, designul Q) — keyword-ul se sare.
            continue
        out.append({"modul": "auto", "keyword_id": kw.id, "termeni": [termen],
                    "in_ore_active": _in_ore_active(kw)})

    for kw in db.query(RealEstateMonitorKeyword).filter(
            RealEstateMonitorKeyword.is_active.is_(True)).all():
        if (kw.platform or "") != "facebook_marketplace":
            continue
        q = (kw.query or "").strip()
        if q:
            termeni = [q]
        else:
            from app.scrapers.real_estate.facebook_real_estate import _termeni_gol
            termeni = _termeni_gol()
        out.append({"modul": "real_estate", "keyword_id": kw.id, "termeni": termeni,
                    "in_ore_active": _in_ore_active(kw)})

    return out


def _scrie_in_bazin(db, modul: str, keyword_id: int, ancora_slug: str,
                    canonice: list) -> int:
    """Insereaza sau reimprospateaza anunturile. Intoarce cate sunt NOI."""
    acum = _acum()
    noi = 0
    for c in canonice:
        ext = str(c.get("external_id") or "")
        if not ext:
            continue
        rand = db.query(FbPoolListing).filter(
            FbPoolListing.modul == modul,
            FbPoolListing.keyword_id == keyword_id,
            FbPoolListing.external_id == ext).first()
        if rand is None:
            listed = c.get("listed_at")
            db.add(FbPoolListing(
                modul=modul, keyword_id=keyword_id, external_id=ext,
                ancora=ancora_slug, title=c.get("title"), price=c.get("price"),
                currency=c.get("currency"), location=c.get("location"),
                source_url=c.get("source_url"), image_url=c.get("image_url"),
                category_id=(str(c["category_id"]) if c.get("category_id") else None),
                listed_at=(listed.isoformat() if hasattr(listed, "isoformat") else listed),
                prima_vedere_at=acum, ultima_vedere_at=acum))
            noi += 1
        else:
            rand.ultima_vedere_at = acum
            rand.price = c.get("price")      # pretul se poate misca
    db.commit()
    return noi


def _curata_bazinul(db) -> int:
    """Sterge randurile nevazute de mai mult de FB_POOL_TTL_ORE. O singura cerere."""
    limita = _acum() - timedelta(hours=_ttl_ore())
    sterse = db.query(FbPoolListing).filter(
        FbPoolListing.ultima_vedere_at < limita).delete(synchronize_session=False)
    db.commit()
    return int(sterse or 0)


def tick(db) -> dict:
    """Un ciclu al executorului. Intoarce sumarul (si il pastreaza pentru diagnostic)."""
    global _ultimul_tick, _tickuri_numai_esec

    if not _lock.acquire(blocking=False):
        log_manager.emit("radar", "WARN",
            "Facebook executor: tick-ul precedent inca ruleaza — il sar pe acesta "
            "(nu se pune la coada)")
        return {"sarit": "tick suprapus"}

    try:
        planificator = _obtine_planificator(db)
        sumar = {"perechi_alese": 0, "executate": 0, "sarite": 0, "cereri": 0,
                 "anunturi_noi": 0, "blocaj": False,
                 "etichete": {"ok": 0, "gol": 0, "blocat": 0, "esec": 0},
                 "sterse_ttl": 0}

        # ── 1. sincronizarea perechilor ──────────────────────────────────────
        keywords = _keywords_facebook(db)
        index = {(k["modul"], k["keyword_id"]): k for k in keywords}
        create = 0
        for k in keywords:
            # Scope fix `national` la FB-6a; scope per keyword vine cu coloana
            # `fb_scope` la FB-7.
            create += planificator.asigura_perechi(k["modul"], k["keyword_id"], "national")
        if create:
            log_manager.emit("radar", "INFO",
                f"Facebook executor: {create} perechi noi create")

        # ── 2. scadentele ────────────────────────────────────────────────────
        scadente = planificator.alege_scadente()
        sumar["perechi_alese"] = len(scadente)
        buget = planificator.buget_efectiv()

        de_executat = []
        for pereche in scadente:
            k = index.get((pereche.modul, pereche.keyword_id))
            if k is None or not k["in_ore_active"]:
                # Keyword sters, dezactivat, mutat de pe Facebook sau in afara orelor
                # active: se REPROGRAMEAZA fara adaptare. `inregistreaza_rezultat` ar
                # fi gresit — nu s-a masurat nimic, iar intervalul n-are voie sa se
                # adapteze pe un non-eveniment.
                # Aware UTC, ca planificatorul (care scrie tot aware la
                # `inregistreaza_rezultat`) — nu amestecam conventiile in aceeasi coloana.
                pereche.next_due_at = _acum() + timedelta(minutes=int(pereche.interval_min))
                sumar["sarite"] += 1
                continue
            de_executat.append((pereche, k))
        if sumar["sarite"]:
            db.commit()

        # ── 3. executia, in limita bugetului de CERERI ───────────────────────
        for pereche, k in de_executat:
            cost = len(k["termeni"])
            if sumar["executate"] and sumar["cereri"] + cost > buget:
                break      # restul raman scadente pentru tick-ul urmator
            # Prima pereche se executa MEREU, chiar daca singura depaseste bugetul:
            # altfel un buget taiat de frana la 1 ar infometa pe veci keyword-ul
            # imobiliar gol (8 termeni), care n-ar mai fi scanat niciodata.

            ancora = dupa_slug(pereche.ancora)
            if ancora is None:
                sumar["sarite"] += 1
                continue

            intoarse, blocaj = 0, False
            canonice_toate = []
            for termen in k["termeni"]:
                canonice, stare = search_cu_stare(
                    termen, ancora.lat, ancora.lon, raza_km=65.0,
                    fb_slug=ancora.fb_slug)
                sumar["cereri"] += 1
                sumar["etichete"][stare.eticheta] = \
                    sumar["etichete"].get(stare.eticheta, 0) + 1
                intoarse += len(canonice)
                canonice_toate.extend(canonice)
                if stare.eticheta == "blocat":
                    blocaj = True
                    break      # abandonam si termenii ramasi ai perechii

            noi = _scrie_in_bazin(db, pereche.modul, pereche.keyword_id,
                                  pereche.ancora, canonice_toate)
            sumar["anunturi_noi"] += noi
            sumar["executate"] += 1
            planificator.inregistreaza_rezultat(pereche, intoarse, noi, blocaj)

            if blocaj:
                # Frana a fost deja semnalata prin `inregistreaza_rezultat`. Tick-ul
                # se inchide devreme: nu insistam pe un server care tocmai ne-a oprit.
                sumar["blocaj"] = True
                break

        # ── 4. curatenie + sumar ─────────────────────────────────────────────
        sumar["sterse_ttl"] = _curata_bazinul(db)

        executate = sumar["executate"]
        numai_esec = executate > 0 and sumar["etichete"].get("esec", 0) == sumar["cereri"]
        _tickuri_numai_esec = _tickuri_numai_esec + 1 if numai_esec else 0
        if _tickuri_numai_esec >= _PRAG_ESEC_TOTAL:
            log_manager.emit("radar", "WARN",
                f"Facebook executor: {_tickuri_numai_esec} tick-uri consecutive in care "
                f"TOATE cererile au esuat — acoperirea logat-out e cazuta. Verifica "
                f"bootstrap-ul (sablonul din pagina) inainte sa te bazezi pe bazin.")

        log_manager.emit("radar", "INFO",
            f"Facebook executor: {executate}/{sumar['perechi_alese']} perechi, "
            f"{sumar['cereri']} cereri (buget {buget}), {sumar['anunturi_noi']} anunturi noi, "
            f"{sumar['sarite']} sarite, etichete {sumar['etichete']}"
            + (" — BLOCAJ" if sumar["blocaj"] else ""))

        sumar["buget"] = buget
        sumar["la"] = _acum().isoformat()
        _ultimul_tick = sumar
        return sumar
    finally:
        _lock.release()


def stare_executor(db) -> dict:
    """Diagnostic pentru endpointul din routerul Radar."""
    perechi = dict(db.query(FbScanState.stare, func.count(FbScanState.id))
                   .group_by(FbScanState.stare).all())
    total_bazin = db.query(func.count(FbPoolListing.id)).scalar() or 0
    cea_mai_recenta = db.query(func.max(FbPoolListing.prima_vedere_at)).scalar()

    return {
        "frana": (_planificator.stare_frana() if _planificator is not None else {}),
        "activ": _planificator is not None,
        "perechi": {str(k): int(v) for k, v in perechi.items()},
        "bazin": {"total": int(total_bazin),
                  "cea_mai_recenta_prima_vedere": (cea_mai_recenta.isoformat()
                                                   if cea_mai_recenta else None)},
        "ultimul_tick": _ultimul_tick,
    }
