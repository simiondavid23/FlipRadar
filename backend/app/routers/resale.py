"""FASHION-3a — profiluri de taxe + referinte de revanzare (manual-first).

Toate rutele filtreaza dupa proprietar: profilurile pe `user_id`, referintele
prin join la produs. Un ID strain intoarce 404, ca peste tot in aplicatie
(vezi suita AN-1).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.resale_fee_profile import ResaleFeeProfile
from app.models.resale_reference import ResaleReference
from app.models.user import User
from app.schemas.resale import (
    FeeProfileCreate,
    FeeProfileResponse,
    FeeProfileUpdate,
    NetPreviewRequest,
    NetPreviewResponse,
    ResaleReferenceCreate,
    ResaleReferenceResponse,
    ResaleReferenceUpdate,
)
from app.services.resale_service import (
    compute_net_ron,
    net_in,
    refresh_product_resale_price,
)
from app.utils.auth import get_current_user

# Fara prefix: routerul serveste si /api/resale/..., si rutele imbricate sub
# /api/products/{id}/resale-references.
router = APIRouter(tags=["Resale"])


# Procentele de mai jos sunt VERIFICATE MANUAL pe paginile oficiale la data din
# _SEED_VERIFIED_AT. Nu se scrapeaza si nu se actualizeaza automat: o taxa citita
# gresit ar falsifica tacit fiecare estimare de profit. Fixele si transportul
# raman 0 tocmai fiindca depind de contul fiecaruia.
_SEED_VERIFIED_AT = "2026-07-26"
_SEED_NOTE = (
    "Procentele sunt cele publicate oficial la data verificarii. Taxele fixe si "
    "transportul sunt 0 — completeaza-le cu valorile contului tau (nivelul de "
    "vanzator, tara si metoda de plata le schimba). Surse: "
    "stockx.com/about/selling si goat.com pagina de fees."
)
_SEED_PROFILES = (
    {"platform": "stockx", "label": "StockX", "commission_pct": 9.5,
     "processing_pct": 3.0, "extra_pct": 0.0, "currency": "EUR"},
    {"platform": "goat", "label": "GOAT", "commission_pct": 9.5,
     "processing_pct": 0.0, "extra_pct": 2.9, "currency": "USD"},
)


def _seed_fee_profiles(db: Session, user_id: int) -> None:
    """Creeaza profilurile implicite lipsa. Idempotent: se uita la (user, platform),
    deci un profil sters intentionat NU se recreeaza decat daca lipseste complet
    la un GET ulterior — compromisul acceptat ca lista sa nu fie goala la primul
    contact cu functionalitatea."""
    existing = {
        p.platform for p in db.query(ResaleFeeProfile)
        .filter(ResaleFeeProfile.user_id == user_id).all()
    }
    created = False
    for seed in _SEED_PROFILES:
        if seed["platform"] in existing:
            continue
        db.add(ResaleFeeProfile(
            user_id=user_id, fixed_fee=0.0, shipping_cost=0.0,
            verified_at=_SEED_VERIFIED_AT, note=_SEED_NOTE, **seed,
        ))
        created = True
    if created:
        db.commit()


def _owned_product(db: Session, product_id: int, user: User) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == user.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")
    return product


def _owned_reference(db: Session, ref_id: int, user: User) -> ResaleReference:
    """Ownership prin produs: referintele n-au user_id propriu."""
    ref = (
        db.query(ResaleReference)
        .join(Product, ResaleReference.product_id == Product.id)
        .filter(ResaleReference.id == ref_id, Product.user_id == user.id)
        .first()
    )
    if not ref:
        raise HTTPException(status_code=404, detail="Referinta nu a fost gasita")
    return ref


def _profile_for(db: Session, user_id: int, platform: str):
    return (
        db.query(ResaleFeeProfile)
        .filter(ResaleFeeProfile.user_id == user_id,
                ResaleFeeProfile.platform == platform)
        .first()
    )


def _reference_response(db: Session, ref: ResaleReference, user_id: int) -> dict:
    """Referinta + netul calculat LIVE, in moneda referintei."""
    profile = _profile_for(db, user_id, ref.platform)
    try:
        net = net_in(compute_net_ron(ref.ref_price, ref.ref_currency, profile),
                     ref.ref_currency)
    except ValueError:
        net = None  # moneda fara curs: referinta ramane vizibila, netul nu
    return {
        "id": ref.id, "product_id": ref.product_id, "platform": ref.platform,
        "variant": ref.variant, "ref_price": ref.ref_price,
        "ref_currency": ref.ref_currency, "source_url": ref.source_url,
        "mode": ref.mode, "fetched_at": ref.fetched_at, "is_primary": ref.is_primary,
        "net": net, "net_currency": ref.ref_currency if net is not None else None,
    }


# ── profiluri de taxe ─────────────────────────────────────────────────────────

@router.get("/api/resale/fee-profiles", response_model=List[FeeProfileResponse])
def list_fee_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Profilurile userului, cu seed idempotent la primul contact."""
    _seed_fee_profiles(db, current_user.id)
    return (
        db.query(ResaleFeeProfile)
        .filter(ResaleFeeProfile.user_id == current_user.id)
        .order_by(ResaleFeeProfile.id)
        .all()
    )


@router.post("/api/resale/fee-profiles", response_model=FeeProfileResponse)
def create_fee_profile(
    payload: FeeProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Profil custom (alta platforma decat cele din seed)."""
    platform = (payload.platform or "").strip()
    if not platform:
        raise HTTPException(status_code=400, detail="Platforma este obligatorie")
    if _profile_for(db, current_user.id, platform) is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Ai deja un profil de taxe pentru „{platform}”.",
        )
    data = payload.model_dump()
    data["platform"] = platform
    profile = ResaleFeeProfile(user_id=current_user.id, **data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/api/resale/fee-profiles/{profile_id}", response_model=FeeProfileResponse)
def update_fee_profile(
    profile_id: int,
    payload: FeeProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Editarea taxelor. Nu atinge niciun net stocat — nu exista: toate netele se
    recalculeaza la citire, deci modificarea se vede imediat peste tot."""
    profile = (
        db.query(ResaleFeeProfile)
        .filter(ResaleFeeProfile.id == profile_id,
                ResaleFeeProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profilul nu a fost gasit")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    # Procentele nu mai sunt cele verificate de noi odata ce userul le-a atins.
    profile.verified_at = None
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/api/resale/net-preview", response_model=NetPreviewResponse)
def net_preview(
    payload: NetPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Netul pentru un pret INCA nesalvat — alimenteaza dialogul din UI.

    Exista ca formula sa NU fie duplicata in JavaScript: o a doua implementare
    ar diverge tacut de compute_net_ron la prima schimbare de reguli, iar userul
    ar vedea in dialog alt numar decat cel salvat. Fara parametru de path, deci
    in afara sweep-ului AN-1 (nu are resursa cu ID de protejat) — ownership-ul e
    implicit: se foloseste DOAR profilul userului curent.
    """
    profile = _profile_for(db, current_user.id, (payload.platform or "").strip())
    currency = (payload.ref_currency or "EUR").upper()
    try:
        net = net_in(compute_net_ron(payload.ref_price, currency, profile), currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"net": net, "net_currency": currency}


# ── referinte de revanzare ────────────────────────────────────────────────────

@router.get("/api/products/{product_id}/resale-references",
            response_model=List[ResaleReferenceResponse])
def list_resale_references(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = _owned_product(db, product_id, current_user)
    refs = (
        db.query(ResaleReference)
        .filter(ResaleReference.product_id == product.id)
        .order_by(ResaleReference.id)
        .all()
    )
    return [_reference_response(db, r, current_user.id) for r in refs]


@router.post("/api/products/{product_id}/resale-references",
             response_model=ResaleReferenceResponse)
def create_resale_reference(
    product_id: int,
    payload: ResaleReferenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = _owned_product(db, product_id, current_user)
    platform = (payload.platform or "").strip()
    if not platform:
        raise HTTPException(status_code=400, detail="Platforma este obligatorie")
    variant = (payload.variant or "").strip()

    existing = (
        db.query(ResaleReference)
        .filter(ResaleReference.product_id == product.id,
                ResaleReference.platform == platform,
                ResaleReference.variant == variant)
        .first()
    )
    if existing is not None:
        marime = f" pe marimea „{variant}”" if variant else ""
        raise HTTPException(
            status_code=400,
            detail=f"Exista deja o referinta „{platform}”{marime} pentru acest produs.",
        )

    # Prima referinta a produsului devine automat primara: altfel ar ramane fara
    # resale_price pana la un set-primary explicit, ceea ce ar parea o eroare.
    is_first = (
        db.query(ResaleReference)
        .filter(ResaleReference.product_id == product.id).count() == 0
    )
    ref = ResaleReference(
        product_id=product.id, platform=platform, variant=variant,
        ref_price=payload.ref_price, ref_currency=(payload.ref_currency or "EUR").upper(),
        source_url=payload.source_url, mode="manual", is_primary=is_first,
    )
    db.add(ref)
    db.flush()
    refresh_product_resale_price(db, product)
    db.commit()
    db.refresh(ref)
    return _reference_response(db, ref, current_user.id)


@router.put("/api/resale/references/{ref_id}", response_model=ResaleReferenceResponse)
def update_resale_reference(
    ref_id: int,
    payload: ResaleReferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ref = _owned_reference(db, ref_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    if "ref_currency" in changes and changes["ref_currency"]:
        changes["ref_currency"] = changes["ref_currency"].upper()
    for key, value in changes.items():
        setattr(ref, key, value)
    db.flush()
    refresh_product_resale_price(db, ref.product)
    db.commit()
    db.refresh(ref)
    return _reference_response(db, ref, current_user.id)


@router.delete("/api/resale/references/{ref_id}")
def delete_resale_reference(
    ref_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ref = _owned_reference(db, ref_id, current_user)
    product = ref.product
    db.delete(ref)
    db.flush()
    # Stergerea primarei lasa produsul fara resale_price (nu promovam automat
    # alta referinta: alegerea e a userului, nu a noastra).
    refresh_product_resale_price(db, product)
    db.commit()
    return {"message": "Referinta a fost stearsa"}


@router.post("/api/resale/references/{ref_id}/set-primary",
             response_model=ResaleReferenceResponse)
def set_primary_resale_reference(
    ref_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Muta flagul de referinta primara si recalculeaza resale_price."""
    ref = _owned_reference(db, ref_id, current_user)
    db.query(ResaleReference).filter(
        ResaleReference.product_id == ref.product_id,
        ResaleReference.id != ref.id,
    ).update({"is_primary": False}, synchronize_session=False)
    ref.is_primary = True
    db.flush()
    refresh_product_resale_price(db, ref.product)
    db.commit()
    db.refresh(ref)
    return _reference_response(db, ref, current_user.id)
