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
# Tick-uri consecutive fara NICIUN `ok` -> WARN zgomotos SI frana pe anomalie.
# Acelasi prag pentru amandoua, deliberat: avertismentul explica, frana actioneaza.
_PRAG_ESEC_TOTAL = 3
_COOLDOWN_ORE_IMPLICIT = 6.0

_lock = threading.Lock()
_planificator = None
_ultimul_tick = None
# Numara tick-urile in care NIMIC n-a reusit, nu doar cele „numai cu esec": o sesiune
# moarta produce `sesiune_invalida`, nu `esec`, si ar fi trecut in tacere (gaura
# gasita la finalul FBS-1).
_tickuri_fara_ok = 0
_cooldown_pana_la = None
_cooldown_amprenta = None       # amprenta sesiunii la momentul intrarii in cooldown


def _cooldown_ore() -> float:
    try:
        return float(os.getenv("FB_COOLDOWN_ORE") or _COOLDOWN_ORE_IMPLICIT)
    except (TypeError, ValueError):
        return _COOLDOWN_ORE_IMPLICIT


def _amprenta_sesiune():
    """Ce anume identifica sesiunea curenta, pentru ridicarea cooldown-ului.

    Calea PLUS mtime si marime: o reconectare din UI rescrie fisierul la aceeasi
    cale, deci o amprenta doar pe cale n-ar observa nimic si utilizatorul ar astepta
    ore fara sa inteleaga de ce.
    """
    cale = (os.getenv("FB_SESIUNE_PATH") or "").strip() or None
    if not cale:
        return None
    try:
        st = os.stat(cale)
        return (cale, st.st_mtime_ns, st.st_size)
    except OSError:
        return (cale, None, None)


def _intra_in_cooldown(db=None) -> None:
    global _cooldown_pana_la, _cooldown_amprenta
    ore = _cooldown_ore()
    _cooldown_pana_la = _acum() + timedelta(hours=ore)
    _cooldown_amprenta = _amprenta_sesiune()
    _alerteaza(db,
        f"Facebook executor: sesiune invalida — pauza {ore:g} h, pana la "
        f"{_cooldown_pana_la.isoformat()}. O sesiune moarta nu se repara insistand; "
        f"reconecteaza contul, iar pauza cade singura la rescrierea fisierului.")


def _reseteaza_cooldown() -> None:
    global _cooldown_pana_la, _cooldown_amprenta
    _cooldown_pana_la = None
    _cooldown_amprenta = None


def _cooldown_activ() -> dict:
    """`{}` daca se poate rula. Altfel motivul saririi. Ridica singur pauza expirata
    sau invalidata de o sesiune noua."""
    if _cooldown_pana_la is None:
        return {}
    if _amprenta_sesiune() != _cooldown_amprenta:
        log_manager.emit("radar", "INFO",
            "Facebook executor: sesiunea s-a schimbat — pauza de cooldown cade")
        _reseteaza_cooldown()
        return {}
    if _acum() >= _cooldown_pana_la:
        log_manager.emit("radar", "INFO",
            "Facebook executor: pauza de cooldown a expirat, se reia")
        _reseteaza_cooldown()
        return {}
    return {"sarit": "cooldown sesiune", "pana_la": _cooldown_pana_la.isoformat()}


def _alerteaza(db, text: str) -> None:
    """WARN in jurnal si, daca avem `db`, alerta Discord pe tiparul EXISTENT.

    Nu se inventeaza o ruta noua: `health_watchdog._dispatch_alert` e deja exact
    „job global care alerteaza fara context de utilizator" — aduna webhook-urile
    userilor activi si trimite best-effort. Importul e lenes ca sa nu legam
    executorul de watchdog la nivel de modul.
    """
    if db is None:
        log_manager.emit("radar", "WARN", text)
        return
    try:
        # `_dispatch_alert` logheaza SI trimite — de-aia nu logam si noi inainte.
        from app.services.radar.health_watchdog import _dispatch_alert
        _dispatch_alert(db, text, "WARN")
    except Exception as exc:      # telemetria nu are voie sa opreasca un tick
        log_manager.emit("radar", "WARN", text)
        log_manager.emit("radar", "WARN",
            f"Facebook executor: alerta Discord a esuat ({type(exc).__name__})")


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
    global _ultimul_tick, _tickuri_fara_ok

    # PRIMUL lucru, inaintea zavorului si a planificatorului: o pauza de cooldown nu
    # are voie sa consume nici macar o interogare de DB.
    sarit = _cooldown_activ()
    if sarit:
        return sarit

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
                 "zero_confirmate": 0, "sesiune_invalida": False,
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
                    city_page_id=ancora.city_page_id)
                sumar["cereri"] += 1
                sumar["etichete"][stare.eticheta] = \
                    sumar["etichete"].get(stare.eticheta, 0) + 1
                if getattr(stare, "zero_confirmat", False):
                    sumar["zero_confirmate"] += 1
                intoarse += len(canonice)
                canonice_toate.extend(canonice)
                if stare.eticheta == "blocat":
                    blocaj = True
                    break      # abandonam si termenii ramasi ai perechii
                if stare.eticheta == "sesiune_invalida":
                    # Ca la `blocat`: se rupe tick-ul. Diferenta e reactia — un 403
                    # trece, o sesiune moarta nu trece de la sine, deci urmeaza pauza.
                    sumar["sesiune_invalida"] = True
                    blocaj = True
                    break

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
        cereri = sumar["cereri"]

        # Criteriul e „niciuna n-a REUSIT", nu „toate au ESUAT". Vechea forma numara
        # doar eticheta `esec`, deci o sesiune moarta (care da `sesiune_invalida`) sau
        # un sir de `blocat` treceau in tacere — exact gaura gasita la finalul FBS-1.
        fara_ok = executate > 0 and cereri > 0 and sumar["etichete"].get("ok", 0) == 0

        # ...dar un tick in care Facebook a CONFIRMAT zero pe fiecare cerere e sanatos,
        # nu suspect. De cand exista santinela (FBS-1), un zero confirmat iese tot
        # `gol`; fara distinctia asta, o noapte linistita ar declansa frana.
        toate_confirmate = fara_ok and sumar["zero_confirmate"] == cereri
        anomalie = fara_ok and not toate_confirmate
        sumar["anomalie"] = anomalie

        _tickuri_fara_ok = _tickuri_fara_ok + 1 if anomalie else 0
        sumar["tickuri_fara_ok"] = _tickuri_fara_ok

        if _tickuri_fara_ok >= _PRAG_ESEC_TOTAL:
            log_manager.emit("radar", "WARN",
                f"Facebook executor: {_tickuri_fara_ok} tick-uri consecutive fara "
                f"NICIUN rezultat reusit (etichete {sumar['etichete']}) — acoperirea e "
                f"cazuta. Verifica sesiunea si bootstrap-ul (sablonul din pagina) "
                f"inainte sa te bazezi pe bazin.")
            # Frana pe ANOMALIE SUSTINUTA — aparare in adancime, nu certitudine.
            # Motivul e direct din FBS-1: lista de markeri de checkpoint e validata
            # doar NEGATIV (zero fals-pozitive pe cunoscut-bun), fara nicio mostra
            # reala de checkpoint. Un fals negativ e plauzibil, si costul lui ar fi sa
            # ciocanim mai departe un cont deja provocat. Raspunsul e proportionat:
            # bugetul se injumatateste, revenirea e cea existenta. La fiecare alt
            # multiplu al pragului se mai coboara o treapta, cu podeaua de 1 din
            # `semnal_blocaj`.
            if _tickuri_fara_ok % _PRAG_ESEC_TOTAL == 0 and _planificator is not None:
                _planificator.semnal_blocaj()
                _alerteaza(db,
                    f"Facebook executor: {_tickuri_fara_ok} tick-uri consecutive fara "
                    f"niciun rezultat — se strange frana (buget injumatatit). Nu e o "
                    f"dovada de blocaj, e o anomalie sustinuta.")

        if sumar["sesiune_invalida"]:
            _intra_in_cooldown(db)

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

    # Regimul se raporteaza din configuratie, nu din ultimul client construit:
    # endpointul poate fi interogat inainte de primul tick.
    from .client import _cale_sesiune
    from app.services.radar.facebook_scraper import is_facebook_session_valid
    cale = _cale_sesiune()
    try:
        sesiune_valida = bool(cale) and is_facebook_session_valid(cale)
    except Exception:
        sesiune_valida = False

    return {
        "frana": (_planificator.stare_frana() if _planificator is not None else {}),
        "activ": _planificator is not None,
        "perechi": {str(k): int(v) for k, v in perechi.items()},
        "bazin": {"total": int(total_bazin),
                  "cea_mai_recenta_prima_vedere": (cea_mai_recenta.isoformat()
                                                   if cea_mai_recenta else None)},
        "ultimul_tick": _ultimul_tick,
        "sesiune": {
            "regim": "autentificat" if cale else "logat-out",
            "cale": cale,
            "valida": sesiune_valida,
        },
        "cooldown": {
            "activ": _cooldown_pana_la is not None,
            "pana_la": (_cooldown_pana_la.isoformat()
                        if _cooldown_pana_la is not None else None),
        },
        "tickuri_fara_ok": _tickuri_fara_ok,
    }
