"""SHOP-2a — scannerul de deal-uri pe magazinele Shopify din registru.

Un deal e o OBSERVATIE a aplicatiei, nu o decizie a userului: enumeram catalogul
fiecarui magazin si retinem produsele al caror pret curent e "bun" fata de una din
doua referinte (D5):

  R1 — `compare_at_price` al magazinului: discount >= prag;
  R2 — minimul istoric PROPRIU: pretul scade sub minimul vazut vreodata cu >= prag.

R2 cere memorie pentru TOT catalogul scanat, nu doar pentru deal-uri — altfel n-are
fata de ce compara. De aici `shop_price_memory`, un rand compact per produs vazut.

ATENTIE la formatul pretului: endpoint-ul de ENUMERARE (/products.json) da string
zecimal ('249.99'), pe cand endpoint-ul per-produs (/products/<handle>.js, folosit
de extractorul SHOP-1) da int in unitati minore (24861). Sunt doua parsari
DIFERITE; conversia ÷100 NU are ce cauta aici.
"""
import random
import threading
import time
from datetime import datetime, timezone

from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.services.log_manager import log_manager, set_log_user
from app.services.shop_registry import SHOP_REGISTRY, shopify_domains

# D9 — pragul global implicit, cand userul nu si-a pus unul.
DEFAULT_DISCOUNT_THRESHOLD = 20.0

# Capac de paginare, in stilul celorlalte capace din scraper_service: 250 de
# produse pe pagina x 40 de pagini = 10k produse per magazin. Peste atat, o
# interogare scapata de sub control ar bombarda magazinul.
_MAX_PAGES_DEAL = 40
_PAGE_LIMIT = 250

_PAUZA = 1.5          # secunde intre pagini, plus jitter (politetea din sonde)
_TIMEOUT = 25

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

# SHOP-2c — o singura scanare la un moment dat. Acopera DOUA suprapuneri reale:
# jobul de la 6h care porneste peste o scanare manuala inca in curs, si dublu-click-ul
# pe butonul din UI. Doua scanari simultane ar citi aceeasi memorie de pret si si-ar
# suprascrie reciproc minimele, deci ar produce deal-uri fantoma.
_SCAN_LOCK = threading.Lock()


def is_scan_running() -> bool:
    """True cat timp o scanare tine lock-ul. Consultat de endpointul manual ca sa
    raspunda 409 in loc sa porneasca un thread care oricum ar iesi imediat."""
    return _SCAN_LOCK.locked()


def _pret_strict(brut):
    """float dintr-un pret de enumerare Shopify. Formatul ('249.99') e impus de
    Shopify, deci parsarea ramane STRICTA: orice altceva intoarce None si elementul
    se sare, in loc sa fie "reparat" tacut intr-o valoare inventata."""
    if isinstance(brut, bool) or brut is None:
        return None
    if isinstance(brut, (int, float)):
        return float(brut)
    if not isinstance(brut, str):
        return None
    try:
        return float(brut.strip())
    except ValueError:
        return None


def _settings(db):
    """Setarile care guverneaza scanul.

    Deal-urile sunt globale pe instanta (fara user_id), dar RadarSettings ramane
    per-user ca tot restul — deci luam UN rand, pe acelasi argument care face
    deal-urile globale: aplicatia se distribuie ca instanta locala single-user.

    SET-1 — ordonarea e OBLIGATORIE, nu cosmetica. `.first()` fara ORDER BY lasa
    randul castigator la mila planului de query: pe baza de dezvoltare (3 randuri
    `radar_settings`, 9 useri) pragul de 60 salvat de user 1 a fost ignorat la
    scanul de verificare DEAL-2b, care a citit randul userului 13, cu None. In
    produsul impachetat exista un singur rand, deci acolo nimic nu se schimba;
    pe baze multi-user regula devine explicita: guverneaza randul userului cu
    id-ul cel mai mic, adica proprietarul instantei.

    `listing_scanner` mosteneste regula prin import — o singura implementare,
    deci cele doua scannere nu pot ajunge sa citeasca randuri diferite.
    """
    return db.query(RadarSettings).order_by(RadarSettings.user_id.asc()).first()


def _prag(settings) -> float:
    valoare = getattr(settings, "deal_discount_threshold", None) if settings else None
    try:
        valoare = float(valoare)
    except (TypeError, ValueError):
        return DEFAULT_DISCOUNT_THRESHOLD
    return valoare if valoare > 0 else DEFAULT_DISCOUNT_THRESHOLD


def _pauza():
    time.sleep(_PAUZA + random.uniform(0, 0.6))


def _pagini(domain: str):
    """Genereaza paginile de enumerare, pana la pagina goala sau la capac."""
    from app.services.scraper_service import _fetch_shop_url_guarded

    for pagina in range(1, _MAX_PAGES_DEAL + 1):
        if pagina > 1:
            _pauza()
        url = f"https://{domain}/products.json?limit={_PAGE_LIMIT}&page={pagina}"
        raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS, timeout=_TIMEOUT)
        if raspuns is None or raspuns.status_code != 200:
            raise RuntimeError(
                f"enumerare esuata la pagina {pagina} "
                f"(status: {getattr(raspuns, 'status_code', None)})")
        try:
            produse = (raspuns.json() or {}).get("products")
        except Exception:
            raise RuntimeError(f"pagina {pagina} nu e JSON valid")
        if not produse:
            return
        yield produse


def _citeste_produs(produs: dict):
    """(pret, compare_at, marimi_in_stoc) pentru un produs de enumerare.

    Intoarce None cand produsul nu e evaluabil: fara nicio varianta DISPONIBILA cu
    pret valid. Un produs epuizat nu e un chilipir cumparabil, deci se sare complet
    — inclusiv din memoria de pret, ca sa nu contaminam minimul istoric cu preturi
    necumparabile.
    """
    disponibile, compare_at_uri, marimi = [], [], []
    for varianta in produs.get("variants") or []:
        if not isinstance(varianta, dict) or not varianta.get("available"):
            continue
        pret = _pret_strict(varianta.get("price"))
        if pret is None or pret <= 0:
            continue
        disponibile.append(pret)
        eticheta = varianta.get("title") or varianta.get("option1")
        if eticheta:
            marimi.append(str(eticheta))
        compara = _pret_strict(varianta.get("compare_at_price"))
        if compara is not None and compara > 0:
            compare_at_uri.append(compara)

    if not disponibile:
        return None
    return min(disponibile), (min(compare_at_uri) if compare_at_uri else None), marimi


def _evalueaza(pret: float, compare_at, min_price_vechi, prag: float, prag_r1=None):
    """(discount_pct, reason) sau (None, None) daca produsul nu califica.

    R1 si R2 se evalueaza independent; cand trec amandoua, `discount_pct` e
    MAXIMUL lor, iar reason devine "ambele".

    DEAL-2b — `prag_r1` da lui R1 un prag PROPRIU, fiindca referinta lui nu
    inseamna acelasi lucru pe toate caile: la Shopify `compare_at_price` e pretul
    unui comerciant activ, dar pe listarile de outlet pretul taiat e un PRP
    permanent, fata de care tot catalogul pare redus. `None` inseamna "acelasi
    prag ca R2", deci apelantii care nu-l dau se comporta EXACT ca inainte —
    o singura implementare, fara copie divergenta.

    Finete: la `reason="ambele"`, fiecare regula se compara cu pragul EI.
    """
    prag_r1 = prag if prag_r1 is None else prag_r1

    r1 = None
    if compare_at is not None and compare_at > pret > 0:
        procent = (compare_at - pret) / compare_at * 100
        if procent >= prag_r1:
            r1 = procent

    r2 = None
    if min_price_vechi is not None and min_price_vechi > pret > 0:
        procent = (min_price_vechi - pret) / min_price_vechi * 100
        if procent >= prag:
            r2 = procent

    if r1 is not None and r2 is not None:
        return max(r1, r2), "ambele"
    if r1 is not None:
        return r1, "compare_at"
    if r2 is not None:
        return r2, "istoric"
    return None, None


def preincarca_pagina(db, domain: str, ids: list[str]) -> tuple[dict, dict]:
    """(memorie_dupa_id, deal_dupa_id) pentru o pagina. Doua SELECT-uri cu `IN`, nu
    doua per produs.

    D10 — pe scanul Shopify sunt 56.768 de produse, deci ~113.000 de interogari per
    rulare (16 minute). Preincarcarea le aduce la doua pe pagina: ~460 in total.

    E SIGUR fiindca `vazute` garanteaza deja ca un `external_id` e tratat o singura
    data per scan (SCAN-1), deci un rand adaugat in cursul paginii nu trebuie sa fie
    vizibil unei cautari ulterioare din aceeasi pagina — si nici nu era, `SessionLocal`
    ruland cu `autoflush=False`. Preincarcarea nu schimba deci nimic din ce vedea codul
    inainte; doar il vede o data, nu de N ori.

    Constrangerea unica `(shop_domain, external_id)` exista pe amandoua tabelele, deci
    dictionarele nu pot pierde randuri prin suprascriere: cel mult unul per cheie.

    Pe PAGINA, nu pe tot domeniul, din doua motive: memoria (un domeniu ca
    footdistrict are 8.000+ de produse, deci tot atatea obiecte ORM tinute degeaba) si
    lungimea listei `IN` — 250 de id-uri la Shopify, 20-76 la listari, comod sub limita
    SQLite de 32.766 de parametri, pe cand un domeniu intreg ar fi trecut-o.
    """
    if not ids:
        return {}, {}
    memorii = (db.query(ShopPriceMemory)
               .filter(ShopPriceMemory.shop_domain == domain,
                       ShopPriceMemory.external_id.in_(ids))
               .all())
    dealuri = (db.query(Deal)
               .filter(Deal.shop_domain == domain,
                       Deal.external_id.in_(ids))
               .all())
    return ({m.external_id: m for m in memorii},
            {d.external_id: d for d in dealuri})


def _scaneaza_magazin(db, domain: str, settings, prag: float) -> dict:
    """Scaneaza un magazin. Ridica exceptie doar pe esec de enumerare — apelantul o
    prinde si o scrie in ShopScanState, ca un magazin picat sa nu opreasca restul."""
    from app.services.discord_service import send_deal_notification

    moneda = (SHOP_REGISTRY.get(domain) or {}).get("currency")
    acum = datetime.now(timezone.utc)
    vazute: set[str] = set()
    # DEAL-2b — `calificate` != `vazute`: primul e "am citit produsul", al doilea
    # "produsul CHIAR e un deal acum". Inchiderea se face pe al doilea, vezi jos.
    calificate: set[str] = set()
    produse_vazute = 0
    alerte = 0
    # D7 — notificarile se strang aici si pleaca DUPA commit-ul paginii, ca un
    # timeout de retea catre Discord sa nu mai prelungeasca tranzactia.
    de_notificat: list[Deal] = []

    for pagina in _pagini(domain):
        # D10 — o singura trecere prin pagina ca sa strangem cheile, apoi doua
        # interogari. Cele deja in `vazute` se sar: pentru ele bucla oricum face
        # `continue` inainte de a citi ceva din dictionare.
        ids_pagina = [str(p["id"]) for p in pagina
                      if isinstance(p, dict) and p.get("id") is not None
                      and str(p["id"]) not in vazute]
        memorii, dealuri = preincarca_pagina(db, domain, ids_pagina)

        for produs in pagina:
            if not isinstance(produs, dict) or produs.get("id") is None:
                continue
            citit = _citeste_produs(produs)
            if citit is None:
                continue  # epuizat: nici deal, nici memorie
            pret, compare_at, marimi = citit
            external_id = str(produs["id"])
            # SCAN-1, simetric cu listing_scanner: acelasi produs vazut de doua ori
            # in ACELASI scan se sare de tot. Enumerarea Shopify e paginata, deci un
            # produs poate reaparea daca magazinul se modifica intre cereri; a doua
            # aparitie ar reintra in blocul de memorie, iar cu `autoflush=False`
            # randul adaugat la prima nu e inca vizibil interogarii — s-ar adauga al
            # doilea si commit-ul ar cadea pe cheia unica. Fixul e aici desi caderea
            # a fost reprodusa pe calea de listari: tiparul e identic, iar imunitatea
            # de pana acum e empirica, nu structurala.
            if external_id in vazute:
                continue
            produse_vazute += 1
            vazute.add(external_id)

            # --- memoria R2: se citeste minimul VECHI inainte de a-l actualiza ---
            memorie = memorii.get(external_id)
            if memorie is None:
                # Prima vedere n-are istoric, deci R2 nu se poate evalua.
                min_price_vechi = None
                db.add(ShopPriceMemory(
                    shop_domain=domain, external_id=external_id,
                    min_price=pret, last_price=pret, last_seen_at=acum))
            else:
                min_price_vechi = memorie.min_price
                memorie.min_price = min(memorie.min_price, pret)
                memorie.last_price = pret
                memorie.last_seen_at = acum

            discount_pct, reason = _evalueaza(pret, compare_at, min_price_vechi, prag)
            if discount_pct is None:
                continue
            calificate.add(external_id)

            deal = dealuri.get(external_id)
            handle = produs.get("handle")
            url = f"https://{domain}/products/{handle}" if handle else f"https://{domain}"
            imagini = produs.get("images") or []
            image_url = (imagini[0] or {}).get("src") if imagini else None

            if deal is None:
                deal = Deal(
                    shop_domain=domain, external_id=external_id, handle=handle,
                    title=str(produs.get("title") or "")[:500], url=url,
                    image_url=image_url, currency=moneda, price=pret,
                    compare_at_price=compare_at, discount_pct=discount_pct,
                    reason=reason, sizes_available=marimi,
                    min_price_seen=min_price_vechi, state="nou",
                    # DEAL-1 — explicit, nu pe default: proveniența se citeste la
                    # locul crearii.
                    deal_source="shopify_enum",
                    first_seen_at=acum, last_seen_at=acum)
                db.add(deal)
                db.flush()
                de_notificat.append(deal)
            else:
                # D7: starea e a USERULUI, deci ramane neatinsa — `ignorat` ramane
                # `ignorat`, `vazut` ramane `vazut`. Fara alerta la reaparitie.
                deal.title = str(produs.get("title") or "")[:500]
                deal.url = url
                deal.image_url = image_url
                deal.handle = handle
                deal.price = pret
                deal.compare_at_price = compare_at
                deal.discount_pct = discount_pct
                deal.reason = reason
                deal.sizes_available = marimi
                deal.min_price_seen = min_price_vechi
                deal.last_seen_at = acum
                deal.ended_at = None

        # D6 — commit dupa FIECARE pagina, nu o data la finalul magazinului.
        # Motivul e lock-ul de scriere SQLite: cu un singur commit la final,
        # tranzactia traversa si `_pauza()`-ul si fetch-ul HTTP al paginii
        # urmatoare, deci pe un magazin de 8000+ produse lock-ul de scriere se
        # tinea ~100s. busy_timeout-ul celorlalti scriitori (30s) expira si
        # cadeau in lant cu "database is locked". Comitand per pagina, lock-ul
        # se tine sub o secunda la fiecare ~1.5s de pauza, deci restul
        # aplicatiei apuca sa scrie intre pagini.
        #
        # Consecinta asumata: `db.rollback()`-ul din `run_deal_scan` anuleaza
        # acum doar pagina curenta, nu tot magazinul — paginile deja comise
        # raman. E acceptabil: blocul de inchidere pe `calificate` ruleaza doar
        # la final, deci un magazin picat la jumatate nu inchide nimic gresit,
        # iar scanul urmator recalculeaza si corecteaza.
        db.commit()
        # Notificarea pleaca DOAR pentru randuri deja comise: altfel am putea
        # anunta un deal pe care un rollback ulterior l-ar face sa nu fi existat.
        for deal in de_notificat:
            if send_deal_notification(deal, settings):
                alerte += 1
        de_notificat.clear()

    # --- deal-urile care nu mai CALIFICA se INCHEIE, nu se sterg ---
    # DEAL-2b: pana acum criteriul era `not in vazute`, deci se inchideau doar
    # produsele DISPARUTE. Un produs inca prezent dar care nu mai trece pragul
    # (pretul a urcat, sau pragul a fost marit din UI) trecea prin `continue` la
    # evaluare si ramanea "activ" cu date vechi pentru totdeauna. Pe `calificate`,
    # primul scan de dupa o schimbare de prag isi face singur curatenia — fara SQL
    # manual si fara migratie de date.
    #
    # Filtrul pe `deal_source` e EXPLICIT, nu accidental: randurile `refresh_diff`
    # pot sta pe acelasi domeniu (un produs urmarit prin link) si scanul asta nu
    # spune nimic despre ele. Pana acum scapau doar fiindca `external_id`-ul lor
    # (`src:<id>`) nu se ciocnea cu product_id-urile Shopify.
    active = (db.query(Deal)
              .filter(Deal.shop_domain == domain,
                      Deal.ended_at.is_(None),
                      Deal.deal_source == "shopify_enum")
              .all())
    for deal in active:
        if deal.external_id not in calificate:
            deal.ended_at = acum

    ramase = sum(1 for d in active if d.external_id in calificate)
    db.commit()
    return {"produse": produse_vazute, "deals_active": ramase, "alerte": alerte}


def _scrie_stare(db, domain: str, status: str, produse: int = 0,
                 deals_active: int = 0, eroare: str | None = None) -> None:
    stare = (db.query(ShopScanState)
             .filter(ShopScanState.shop_domain == domain).first())
    if stare is None:
        stare = ShopScanState(shop_domain=domain)
        db.add(stare)
    stare.last_scan_at = datetime.now(timezone.utc)
    stare.last_status = status
    stare.products_seen = produse
    stare.deals_active = deals_active
    stare.error_message = eroare
    db.commit()


def run_deal_scan(db) -> dict:
    """Intrarea de job (APScheduler, la 6h). Intoarce un rezumat pentru logging."""
    # MON-4 — reset defensiv: joburile ruleaza pe thread-uri de pool, iar un
    # user_id ramas de la o rulare anterioara ar eticheta gresit log-urile.
    set_log_user(None)

    # Non-blocant DELIBERAT: o scanare care asteapta la coada ar porni imediat dupa
    # cea curenta si ar reface aceeasi munca. Mai bine iese si o reia jobul urmator.
    if not _SCAN_LOCK.acquire(blocking=False):
        print("[DealScan] scanare deja in curs — cererea a fost ignorata")
        log_manager.emit("catalog", "WARN",
                         "Deal scan Shopify: sarit — scanare deja in curs")
        return {"skipped": "scan deja in curs", "magazine": 0}

    try:
        settings = _settings(db)
        if settings is not None and not getattr(settings, "deal_scan_enabled", True):
            return {"skipped": "deal_scan_enabled=False", "magazine": 0}

        dezactivate = set(getattr(settings, "deal_shops_disabled", None) or []) if settings else set()
        domenii = sorted(shopify_domains() - dezactivate)
        prag = _prag(settings)
        log_manager.emit("catalog", "SCAN",
                         f"Deal scan Shopify: start, {len(domenii)} magazine")

        rezumat = {"magazine": 0, "produse": 0, "alerte": 0, "erori": 0}
        for domain in domenii:
            try:
                rezultat = _scaneaza_magazin(db, domain, settings, prag)
            except Exception as exc:                    # noqa: BLE001
                # Un magazin picat (tema schimbata, blocaj, retea) NU opreste restul:
                # starea lui se vede in panoul de sanatate, ceilalti isi vad de treaba.
                db.rollback()
                _scrie_stare(db, domain, "error", eroare=f"{type(exc).__name__}: {exc}"[:500])
                rezumat["erori"] += 1
                log_manager.emit(
                    "catalog", "WARN",
                    f"Deal scan {domain}: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            _scrie_stare(db, domain, "ok", produse=rezultat["produse"],
                         deals_active=rezultat["deals_active"])
            rezumat["magazine"] += 1
            rezumat["produse"] += rezultat["produse"]
            rezumat["alerte"] += rezultat["alerte"]
        log_manager.emit(
            "catalog", "OK",
            f"Deal scan Shopify: gata — {rezumat['magazine']} magazine ok, "
            f"{rezumat['erori']} erori, {rezumat['produse']} produse, "
            f"{rezumat['alerte']} alerte")
        return rezumat
    finally:
        _SCAN_LOCK.release()


# ── DEAL-1: a doua sursa a feed-ului — scaderile prinse de refresh ───────────

def record_refresh_diff_deal(db, *, product, ps, old_price, new_price, min30):
    """Persista ca Deal o scadere de pret vazuta la refresh-ul unei surse urmarite.

    A doua sursa a feed-ului, dupa scannerul Shopify. Mecanismul de detectie exista
    deja in bucla de refresh (flash-deal); ce lipsea era RANDUL — scaderea se anunta
    si se pierdea. Toata logica de feed sta AICI, ca alert_checker doar sa cheme.

    Criteriul e scaderea fata de pretul anterior al sursei, nu fata de o referinta
    de magazin: la un produs urmarit, `old_price` chiar e pretul pe care l-ai fi
    platit ieri, deci e referinta cinstita. `min30` intra doar informativ.

    Fara Discord aici, DELIBERAT: momentul e deja acoperit de flash-deal, pe canalul
    lui si cu pragul lui (`flash_deal_threshold`). Un al doilea mesaj pentru acelasi
    eveniment ar fi zgomot. Livrabilul acestei cai e randul din feed.

    Intoarce Deal-ul scris/actualizat, sau None cand scaderea nu califica.
    """
    settings = _settings(db)
    prag = _prag(settings)
    try:
        vechi, nou = float(old_price), float(new_price)
    except (TypeError, ValueError):
        return None
    if vechi <= 0 or nou <= 0:
        return None

    shop_domain = ps.source
    # Stabil per INSTANTA de sursa (produs + magazin + varianta sunt deja unice pe
    # ProductSource), si mult sub 64 de caractere.
    external_id = f"src:{ps.id}"
    acum = datetime.now(timezone.utc)
    existent = (db.query(Deal)
                .filter(Deal.shop_domain == shop_domain,
                        Deal.external_id == external_id)
                .first())

    discount_pct = (vechi - nou) / vechi * 100.0
    if discount_pct < prag:
        # Pretul a urcat inapoi peste cel al deal-ului activ -> oferta s-a terminat.
        # D7: se scrie `ended_at`, starea userului ramane neatinsa, randul nu se sterge.
        if existent is not None and existent.ended_at is None and nou > (existent.price or 0):
            existent.ended_at = acum
            db.commit()
        return None

    titlu = str(product.name or "")[:500]
    if ps.variant:
        titlu = f"{titlu} — {ps.variant}"[:500]

    if existent is None:
        existent = Deal(
            shop_domain=shop_domain, external_id=external_id, handle=None,
            title=titlu, url=ps.source_url, image_url=getattr(product, "image_url", None),
            currency=ps.currency, price=nou, compare_at_price=None,
            discount_pct=discount_pct, reason="istoric", sizes_available=[],
            min_price_seen=min30, state="nou", deal_source="refresh_diff",
            first_seen_at=acum, last_seen_at=acum)
        db.add(existent)
    else:
        # D7, ca la scanner: starea e a USERULUI si ramane neatinsa.
        existent.title = titlu
        existent.url = ps.source_url
        existent.image_url = getattr(product, "image_url", None)
        existent.currency = ps.currency
        existent.price = nou
        existent.compare_at_price = None
        existent.discount_pct = discount_pct
        existent.reason = "istoric"
        existent.min_price_seen = min30
        existent.last_seen_at = acum
        existent.ended_at = None
    db.commit()
    return existent
