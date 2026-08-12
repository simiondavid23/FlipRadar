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
import time
from datetime import datetime, timezone

from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.services.log_manager import set_log_user
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
    per-user ca tot restul — deci luam PRIMUL rand, pe acelasi argument care face
    deal-urile globale: aplicatia se distribuie ca instanta locala single-user.
    """
    return db.query(RadarSettings).first()


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


def _evalueaza(pret: float, compare_at, min_price_vechi, prag: float):
    """(discount_pct, reason) sau (None, None) daca produsul nu califica.

    R1 si R2 se evalueaza independent; cand trec amandoua, `discount_pct` e
    MAXIMUL lor, iar reason devine "ambele".
    """
    r1 = None
    if compare_at is not None and compare_at > pret > 0:
        procent = (compare_at - pret) / compare_at * 100
        if procent >= prag:
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


def _scaneaza_magazin(db, domain: str, settings, prag: float) -> dict:
    """Scaneaza un magazin. Ridica exceptie doar pe esec de enumerare — apelantul o
    prinde si o scrie in ShopScanState, ca un magazin picat sa nu opreasca restul."""
    from app.services.discord_service import send_deal_notification

    moneda = (SHOP_REGISTRY.get(domain) or {}).get("currency")
    acum = datetime.now(timezone.utc)
    vazute: set[str] = set()
    produse_vazute = 0
    alerte = 0

    for pagina in _pagini(domain):
        for produs in pagina:
            if not isinstance(produs, dict) or produs.get("id") is None:
                continue
            citit = _citeste_produs(produs)
            if citit is None:
                continue  # epuizat: nici deal, nici memorie
            pret, compare_at, marimi = citit
            produse_vazute += 1
            external_id = str(produs["id"])
            vazute.add(external_id)

            # --- memoria R2: se citeste minimul VECHI inainte de a-l actualiza ---
            memorie = (db.query(ShopPriceMemory)
                       .filter(ShopPriceMemory.shop_domain == domain,
                               ShopPriceMemory.external_id == external_id)
                       .first())
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

            deal = (db.query(Deal)
                    .filter(Deal.shop_domain == domain,
                            Deal.external_id == external_id)
                    .first())
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
                    first_seen_at=acum, last_seen_at=acum)
                db.add(deal)
                db.flush()
                if send_deal_notification(deal, settings):
                    alerte += 1
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

    # --- deal-urile care n-au mai aparut in scanul curent se INCHEIE, nu se sterg ---
    active = (db.query(Deal)
              .filter(Deal.shop_domain == domain, Deal.ended_at.is_(None))
              .all())
    for deal in active:
        if deal.external_id not in vazute:
            deal.ended_at = acum

    ramase = sum(1 for d in active if d.external_id in vazute)
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

    settings = _settings(db)
    if settings is not None and not getattr(settings, "deal_scan_enabled", True):
        return {"skipped": "deal_scan_enabled=False", "magazine": 0}

    dezactivate = set(getattr(settings, "deal_shops_disabled", None) or []) if settings else set()
    domenii = sorted(shopify_domains() - dezactivate)
    prag = _prag(settings)

    rezumat = {"magazine": 0, "produse": 0, "alerte": 0, "erori": 0}
    for domain in domenii:
        try:
            rezultat = _scaneaza_magazin(db, domain, settings, prag)
        except Exception as exc:                        # noqa: BLE001
            # Un magazin picat (tema schimbata, blocaj, retea) NU opreste restul:
            # starea lui se vede in panoul de sanatate, ceilalti isi vad de treaba.
            db.rollback()
            _scrie_stare(db, domain, "error", eroare=f"{type(exc).__name__}: {exc}"[:500])
            rezumat["erori"] += 1
            continue
        _scrie_stare(db, domain, "ok", produse=rezultat["produse"],
                     deals_active=rezultat["deals_active"])
        rezumat["magazine"] += 1
        rezumat["produse"] += rezultat["produse"]
        rezumat["alerte"] += rezultat["alerte"]
    return rezumat
