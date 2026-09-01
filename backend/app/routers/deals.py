"""SHOP-2a — API-ul deal-urilor descoperite de scannerul Shopify.

Deal-urile sunt globale pe instanta (fara user_id, vezi models/deal.py), dar
endpoint-urile raman autentificate ca tot restul aplicatiei: promovarea creeaza
produse PE USERUL curent, deci are nevoie de el oricum.
"""
import threading
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.deal import Deal
from app.models.radar_settings import RadarSettings
from app.models.shop_scan_state import ShopScanState
from app.models.tracked_product import TrackedProduct
from app.models.user import User
from app.services.currency_service import convert, get_all_rates
from app.services.shop_registry import SHOP_REGISTRY, listing_domains, shopify_domains
from app.utils.auth import get_current_user

# Prefixul /api/deals e aplicat la include_router in main.py.
router = APIRouter(tags=["Deals"])

# D7 — starile pe care le poate seta USERUL. `nou` e pusa de scanner, iar
# `promovat` doar de endpointul de promovare: amandoua ar fi minciuni daca ar
# putea fi scrise direct din UI.
_STARI_MANUALE = {"vazut", "ignorat"}

# DEAL-2b — cele trei surse ale feed-ului. Lista e inchisa si validata la intrare,
# ca o valoare gresita sa dea 422 explicit, nu o lista goala derutanta.
_SURSE = {"shopify_enum", "refresh_diff", "listing_scan", "api_enum"}

# DEAL-3 — multimile inchise pentru parametrii noi. `_STARI` e mai larga decat
# `_STARI_MANUALE`: `exclude_state` doar CITESTE starea, deci are voie sa numeasca
# si starile pe care userul nu le poate scrie.
_STARI = {"nou", "vazut", "ignorat", "promovat"}
_SORTARI = {"discount", "recent", "price"}

# Plafonul paginii. 60 acopera un ecran de carduri cu rezerva, iar 500 e taria
# maxima pe care o acceptam de la un client: peste atat, costul redevine cel pe
# care DEAL-3 tocmai l-a eliminat (ORM + JSON + DOM pe zeci de mii de randuri).
_LIMITA_IMPLICITA = 60
_LIMITA_MAXIMA = 500


class DealStateUpdate(BaseModel):
    state: str


def _in_ron(valoare, moneda):
    """Valoarea in RON, DOAR pentru afisare. Sortarea ramane pe discount_pct, care
    e agnostic de moneda — o sortare pe pret convertit ar depinde de cursul zilei."""
    if valoare is None:
        return None
    if (moneda or "RON").upper() == "RON":
        return valoare          # trecere directa: fara apel de conversie
    return convert(valoare, moneda, "RON")


def _serialize(deal: Deal) -> dict:
    return {
        "id": deal.id,
        "shop_domain": deal.shop_domain,
        "external_id": deal.external_id,
        "handle": deal.handle,
        "title": deal.title,
        "url": deal.url,
        "image_url": deal.image_url,
        "currency": deal.currency,
        "price": deal.price,
        "compare_at_price": deal.compare_at_price,
        "discount_pct": deal.discount_pct,
        "reason": deal.reason,
        # DEAL-2b — proveniența pleaca spre UI: cele trei surse au semantici
        # diferite ale pretului taiat, deci utilizatorul trebuie sa le poata separa.
        "deal_source": deal.deal_source,
        "sizes_available": deal.sizes_available or [],
        "min_price_seen": deal.min_price_seen,
        "state": deal.state,
        "first_seen_at": deal.first_seen_at,
        "last_seen_at": deal.last_seen_at,
        "ended_at": deal.ended_at,
        "promoted_product_id": deal.promoted_product_id,
    }


def _valideaza(source, exclude_state, sort):
    """Validarile comune. Fiecare parametru inchis intr-o multime da 422 explicit,
    nu o lista goala derutanta — aceeasi regula ca `source` de la DEAL-2b."""
    if source is not None and source not in _SURSE:
        raise HTTPException(
            status_code=422,
            detail=f"Sursă invalidă. Valori acceptate: {', '.join(sorted(_SURSE))}.")
    if exclude_state is not None and exclude_state not in _STARI:
        raise HTTPException(
            status_code=422,
            detail=f"Stare invalidă. Valori acceptate: {', '.join(sorted(_STARI))}.")
    if sort is not None and sort not in _SORTARI:
        raise HTTPException(
            status_code=422,
            detail=f"Sortare invalidă. Valori acceptate: {', '.join(sorted(_SORTARI))}.")


def _filtre(q, state, shop_domain, source, active, min_discount,
            exclude_state, category):
    """Filtrele, intr-un singur loc, fiindca sunt folosite de DOUA endpointuri:
    lista si numaratoarea. Daca ar fi scrise de doua ori, ar putea devia, iar un
    total care nu se potriveste cu randurile afisate e mai rau decat lipsa lui."""
    if state:
        q = q.filter(Deal.state == state)
    if exclude_state:
        q = q.filter(Deal.state != exclude_state)
    if source:
        q = q.filter(Deal.deal_source == source)
    if shop_domain:
        q = q.filter(Deal.shop_domain == shop_domain)
    if active is not None:
        q = q.filter(Deal.ended_at.is_(None) if active else Deal.ended_at.isnot(None))
    if min_discount is not None:
        q = q.filter(Deal.discount_pct >= min_discount)
    if category:
        # Categoria e o proprietate a MAGAZINULUI (SHOP_REGISTRY), nu a randului,
        # deci se traduce intr-un IN pe domenii. O multime goala filtreaza la ZERO
        # rezultate, nu se ignora: o categorie inexistenta trebuie sa arate gol,
        # altfel userul ar primi tot feed-ul si ar crede ca filtrul a functionat.
        domenii = [d for d, meta in SHOP_REGISTRY.items()
                   if (meta or {}).get("category") == category]
        q = q.filter(Deal.shop_domain.in_(domenii))
    return q


def _ordine(sort):
    """Expresia de ORDER BY, cu tie-break pe id ca paginarea sa fie STABILA: la
    valori egale de discount, doua cereri consecutive fara tie-break pot intoarce
    aceleasi randuri pe pagini diferite, deci userul ar vedea duplicate si goluri.

    `price` compara in RON, altfel un pret in EUR ar parea mai mic decat unul in
    RON. Cursul vine din `get_all_rates()`; daca lipseste, cadem pe pretul brut —
    o sortare aproximativa e mai buna decat un 500 pe o pagina de feed.
    """
    if sort == "recent":
        return [Deal.first_seen_at.desc(), Deal.id.desc()]
    if sort == "price":
        try:
            rate = get_all_rates() or {}
        except Exception:
            rate = {}
        # Cheile sunt "EUR_RON"/"USD_RON", nu coduri simple de moneda.
        perechi = [(cheie.split("_")[0], factor)
                   for cheie, factor in rate.items() if factor]
        if not perechi:
            return [Deal.price.asc(), Deal.id.asc()]
        # RON si orice moneda necunoscuta cad pe `else_`, adica factor 1.
        expr = case(*[(Deal.currency == cod, Deal.price * factor)
                      for cod, factor in perechi], else_=Deal.price)
        return [expr.asc(), Deal.id.asc()]
    return [Deal.discount_pct.desc(), Deal.id.desc()]


@router.get("/")
def list_deals(
    state: Optional[str] = None,
    shop_domain: Optional[str] = None,
    source: Optional[str] = None,
    active: Optional[bool] = None,
    min_discount: Optional[float] = None,
    exclude_state: Optional[str] = None,
    category: Optional[str] = None,
    sort: str = "discount",
    limit: int = Query(_LIMITA_IMPLICITA, ge=1, le=_LIMITA_MAXIMA),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """Deal-urile, filtrabile, sortate si PAGINATE pe server. Conversia valutara
    pentru afisare ramane in frontend (SHOP-2b), prin endpointul de rate existent
    — aici pretul si moneda pleaca exact cum le-a masurat scannerul.

    DEAL-3 — raspunsul ramane o LISTA, nu un obiect `{items, total}`: contractul
    e deja consumat asa, iar schimbarea formei ar fi rupt fara castig fiecare
    apelant. Totalul are endpoint separat (`/count`) tocmai din acest motiv, si
    are si un avantaj: incarcarea incrementala cere numaratoarea O SINGURA DATA,
    la reset, nu la fiecare pagina, deci COUNT-ul nu se plateste de N ori.

    Filtrele si sortarea au coborat toate pe server (D-A/D-E). Inainte, pagina
    aducea toate randurile active — 21k pe productie — si le filtra/sorta in
    browser; costul nu era SQLite (216 ms masurati), ci ORM-ul, JSON-ul si DOM-ul.
    """
    _valideaza(source, exclude_state, sort)

    q = _filtre(db.query(Deal), state, shop_domain, source, active,
                min_discount, exclude_state, category)

    iesire = []
    for d in q.order_by(*_ordine(sort)).offset(offset).limit(limit).all():
        item = _serialize(d)
        item["price_ron"] = _in_ron(d.price, d.currency)
        if d.compare_at_price is not None:
            item["compare_at_price_ron"] = _in_ron(d.compare_at_price, d.currency)
        iesire.append(item)
    return iesire


@router.get("/count")
def deals_count(
    state: Optional[str] = None,
    shop_domain: Optional[str] = None,
    source: Optional[str] = None,
    active: Optional[bool] = None,
    min_discount: Optional[float] = None,
    exclude_state: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DEAL-3 — cate randuri ar intoarce lista cu ACELEASI filtre. Fara limit /
    offset / sort: niciunul nu schimba totalul, iar acceptarea lor ar sugera ca da.

    Trece prin `_filtre`, aceeasi functie ca lista, ca numaratoarea sa nu poata
    devia de la ce se afiseaza. COUNT in SQL, deci nu se materializeaza niciun
    obiect ORM."""
    _valideaza(source, exclude_state, None)

    q = _filtre(db.query(Deal), state, shop_domain, source, active,
                min_discount, exclude_state, category)
    return {"total": q.with_entities(func.count(Deal.id)).scalar() or 0}


@router.get("/stats")
def deals_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cifrele din capul paginii. „Active" = deal-uri pe care scannerul le-a
    revazut la ultima trecere (`ended_at IS NULL`).

    DEAL-3 — totul se calculeaza in SQL, printr-o singura interogare agregata.
    Inainte, `.all()` materializa 21k obiecte ORM ca sa numere trei lucruri;
    COUNT/SUM/AVG dau exact aceleasi cifre fara sa construiasca niciun obiect.
    Cheile si tipurile raspunsului raman neschimbate.
    """
    activ, noi, medie = (db.query(
        func.count(Deal.id),
        func.sum(case((Deal.state == "nou", 1), else_=0)),
        func.avg(Deal.discount_pct),
    ).filter(Deal.ended_at.is_(None)).one())
    ultimul = db.query(func.max(ShopScanState.last_scan_at)).scalar()
    return {
        "active": activ or 0,
        # SUM peste zero randuri da NULL, nu 0 — de aici `or 0`. AVG la fel, dar
        # acolo None e chiar raspunsul corect (nu exista active de mediat).
        "noi": int(noi or 0),
        "avg_discount_active": (round(float(medie), 1) if medie is not None
                                else None),
        "last_scan_at": ultimul,
    }


@router.get("/shops")
def deals_shops(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Universul de deal-uri: magazinele enumerabile Shopify REUNITE cu cele care
    au descriptor de listare (DEAL-2), cu starea ultimului scan atasata acolo unde
    exista.

    Reuniune, nu concatenare: cele doua capabilitati sunt independente, deci un
    domeniu ar putea intr-o zi sa le aiba pe amandoua fara sa apara de doua ori.
    Starile vin oricum din ShopScanState, care e comun ambelor scannere.

    Alimenteaza filtrele, banda de sanatate si checklist-ul din setari. E si
    samanta viitorului endpoint general /shops.
    """
    setari = (db.query(RadarSettings)
              .filter(RadarSettings.user_id == current_user.id).first())
    dezactivate = set(getattr(setari, "deal_shops_disabled", None) or [])
    stari = {s.shop_domain: s for s in db.query(ShopScanState).all()}

    iesire = []
    for domain in sorted(shopify_domains() | listing_domains()):
        meta = SHOP_REGISTRY.get(domain) or {}
        rand = {
            "domain": domain,
            "label": meta.get("label") or domain,
            "category": meta.get("category"),
            # Domeniile de listare n-au `currency` la nivelul intrarii — moneda lor
            # e o proprietate a LISTARII (masurata acolo), nu a extractorului de
            # produs, care la `jsonld` o citeste din pagina. Fara rezerva asta,
            # cele 4 randuri noi ar aparea cu moneda goala in panoul de sanatate.
            "currency": meta.get("currency") or (meta.get("listing") or {}).get("currency"),
            "disabled": domain in dezactivate,
            "last_scan_at": None, "last_status": None,
            "products_seen": None, "deals_active": None,
        }
        stare = stari.get(domain)
        if stare is not None:
            rand.update({
                "last_scan_at": stare.last_scan_at,
                "last_status": stare.last_status,
                "products_seen": stare.products_seen,
                "deals_active": stare.deals_active,
            })
        iesire.append(rand)
    return iesire


@router.post("/scan")
def scan_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Porneste o scanare imediata, fara sa astepte jobul de la 6h.

    Thread daemon cu sesiune proprie, exact ca /radar/scan-now: sesiunea
    request-ului se inchide la return, deci scanul nu poate imprumuta pe-a lui.
    Garda de concurenta e in scanner (lock la nivel de modul); aici o consultam
    doar ca sa raspundem 409 in loc sa pornim un thread care ar iesi imediat.
    """
    from app.services.deal_scanner import is_scan_running, run_deal_scan

    if is_scan_running():
        raise HTTPException(
            status_code=409,
            detail="O scanare de deal-uri este deja în curs. Așteaptă să se termine.")

    def _background_scan():
        from app.database import SessionLocal
        _db = SessionLocal()
        try:
            run_deal_scan(_db)
        except Exception as exc:                        # noqa: BLE001
            print(f"[DealScan manual] eroare: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"started": True}


@router.post("/scan-listings")
def scan_listings_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DEAL-2 — porneste imediat scanarea listarilor HTML, fara jobul de 24h.

    Acelasi tipar ca `/scan`, dar pe lock-ul PROPRIU al scannerului de listari:
    cele doua scaneaza domenii disjuncte, deci pot merge in paralel, iar 409-ul de
    aici raspunde doar pentru o scanare de listari deja in curs.
    """
    from app.services.listing_scanner import is_listing_scan_running, run_listing_scan

    if is_listing_scan_running():
        raise HTTPException(
            status_code=409,
            detail="O scanare de listări este deja în curs. Așteaptă să se termine.")

    def _background_scan():
        from app.database import SessionLocal
        _db = SessionLocal()
        try:
            run_listing_scan(_db)
        except Exception as exc:                        # noqa: BLE001
            print(f"[ListingScan manual] eroare: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"started": True}


@router.post("/scan-api")
def scan_api_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """VAL D — porneste imediat enumerarea prin API de catalog, fara jobul de 24h.

    Acelasi tipar ca `/scan-listings`, pe lock-ul PROPRIU al scannerului de API:
    cele trei surse scaneaza domenii disjuncte, deci pot merge in paralel, iar
    409-ul de aici raspunde doar pentru o enumerare de API deja in curs.
    """
    from app.services.api_scanner import is_api_scan_running, run_api_scan

    if is_api_scan_running():
        raise HTTPException(
            status_code=409,
            detail="O enumerare prin API este deja în curs. Așteaptă să se termine.")

    def _background_scan():
        from app.database import SessionLocal
        _db = SessionLocal()
        try:
            run_api_scan(_db)
        except Exception as exc:                        # noqa: BLE001
            print(f"[ApiScan manual] eroare: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"started": True}


@router.patch("/{deal_id}")
def update_deal_state(
    deal_id: int,
    payload: DealStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal inexistent.")
    if payload.state not in _STARI_MANUALE:
        raise HTTPException(
            status_code=422,
            detail=f"Stare invalidă: „{payload.state}”. Permise: "
                   f"{', '.join(sorted(_STARI_MANUALE))}.")
    deal.state = payload.state
    db.commit()
    db.refresh(deal)
    return _serialize(deal)


@router.post("/{deal_id}/promote")
def promote_deal(
    deal_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promoveaza un deal in produs urmarit.

    Refoloseste INTEGRAL calea add-by-link: `create_product_from_url` e apelat ca
    functie, exact pattern-ul prin care el insusi deleaga la `create_product`. Asa
    vin gratis dedup-ul per user, snapshot-ul de pret, backfill-ul EAN si
    cross-shop — o a doua implementare ar diverge de prima la prima schimbare.

    Daca extractia live esueaza (produs disparut intre timp), eroarea HTTP a caii
    existente se propaga si deal-ul ramane NESCHIMBAT.
    """
    from app.routers.products import create_product_from_url
    from app.schemas.product import ProductFromUrlRequest

    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal inexistent.")

    rezultat = create_product_from_url(
        payload=ProductFromUrlRequest(url=deal.url),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )
    # create_product_from_url intoarce payload-ul de detaliu, cu produsul sub
    # cheia "product" (vezi _build_detail_response) — nu un id la radacina.
    product_id = rezultat["product"].id

    deal.state = "promovat"
    deal.promoted_product_id = product_id

    # Upsert pe TrackedProduct: pragul nu se atinge aici — el e treaba modelului
    # Alert, ca peste tot in aplicatie.
    tracked = (db.query(TrackedProduct)
               .filter(TrackedProduct.user_id == current_user.id,
                       TrackedProduct.product_id == product_id)
               .first())
    if tracked is None:
        tracked = TrackedProduct(user_id=current_user.id, product_id=product_id,
                                 monitoring_active=True)
        db.add(tracked)
    else:
        tracked.monitoring_active = True
    db.commit()
    db.refresh(deal)

    # `product_id` la radacina: raspunsul lui create_product_from_url e deja un
    # obiect imbricat, iar UI-ul are nevoie de id fara sa-i cunoasca forma.
    return {"deal": _serialize(deal), "product_id": product_id,
            "product": rezultat["product"]}
