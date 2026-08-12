"""SHOP-2a — API-ul deal-urilor descoperite de scannerul Shopify.

Deal-urile sunt globale pe instanta (fara user_id, vezi models/deal.py), dar
endpoint-urile raman autentificate ca tot restul aplicatiei: promovarea creeaza
produse PE USERUL curent, deci are nevoie de el oricum.
"""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.deal import Deal
from app.models.tracked_product import TrackedProduct
from app.models.user import User
from app.utils.auth import get_current_user

# Prefixul /api/deals e aplicat la include_router in main.py.
router = APIRouter(tags=["Deals"])

# D7 — starile pe care le poate seta USERUL. `nou` e pusa de scanner, iar
# `promovat` doar de endpointul de promovare: amandoua ar fi minciuni daca ar
# putea fi scrise direct din UI.
_STARI_MANUALE = {"vazut", "ignorat"}


class DealStateUpdate(BaseModel):
    state: str


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
        "sizes_available": deal.sizes_available or [],
        "min_price_seen": deal.min_price_seen,
        "state": deal.state,
        "first_seen_at": deal.first_seen_at,
        "last_seen_at": deal.last_seen_at,
        "ended_at": deal.ended_at,
        "promoted_product_id": deal.promoted_product_id,
    }


@router.get("/")
def list_deals(
    state: Optional[str] = None,
    shop_domain: Optional[str] = None,
    active: Optional[bool] = None,
    min_discount: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """Deal-urile, filtrabile. Conversia valutara pentru afisare ramane in
    frontend (SHOP-2b), prin endpointul de rate existent — aici pretul si moneda
    pleaca exact cum le-a masurat scannerul."""
    q = db.query(Deal)
    if state:
        q = q.filter(Deal.state == state)
    if shop_domain:
        q = q.filter(Deal.shop_domain == shop_domain)
    if active is not None:
        q = q.filter(Deal.ended_at.is_(None) if active else Deal.ended_at.isnot(None))
    if min_discount is not None:
        q = q.filter(Deal.discount_pct >= min_discount)
    return [_serialize(d) for d in q.order_by(Deal.discount_pct.desc()).all()]


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
