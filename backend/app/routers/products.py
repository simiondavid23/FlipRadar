import random
import time
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from app.database import SessionLocal, get_db
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.product_source_suggestion import ProductSourceSuggestion
from app.models.price_history import PriceHistory
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductSaveResponse,
    ProductDetailResponse,
    RefreshSourceResult,
    RefreshAllSourcesResponse,
)
from app.utils.auth import get_current_user
from app.models.user import User
from app.services.currency_service import convert
from app.services.scraper_service import (
    fetch_ean_from_url,
    refresh_price_from_source,
    find_cross_shop_matches,
)

_SCRAPE_DELAY_RANGE = (0.6, 1.4)


def _recompute_primary_snapshot(product: Product) -> None:
    """Setează product.current_price/currency/source/source_url pe baza sursei
    cu prețul cel mai mic (cu comparație după conversie valutară)."""
    sources_with_price = [s for s in product.sources if s.current_price is not None]
    if not sources_with_price:
        return
    base_currency = product.currency or "EUR"
    def price_in_base(s: ProductSource) -> float:
        if (s.currency or base_currency).upper() == base_currency.upper():
            return float(s.current_price)
        try:
            return float(convert(s.current_price, s.currency, base_currency))
        except Exception:
            return float(s.current_price)
    cheapest = min(sources_with_price, key=price_in_base)
    product.current_price = cheapest.current_price
    product.currency = cheapest.currency or base_currency
    product.source = cheapest.source
    product.source_url = cheapest.source_url


def attach_source_to_product(
    db: Session,
    product: Product,
    source: Optional[str],
    source_url: Optional[str],
    price: Optional[float] = None,
    currency: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """Creează sau actualizează un ProductSource pe produs + PriceHistory, apoi
    recalculează snapshot-ul primar (current_price = minimul dintre surse) și face
    commit. Reutilizabilă din create_product și din task-ul de cross-shop matching.

    `name` e acceptat pentru compatibilitate de semnătură (ProductSource nu are
    coloană de nume — numele produsului e pe Product).
    """
    if not source:
        return
    ps = next((s for s in product.sources if s.source == source), None)
    if ps is None and source_url:
        ps = ProductSource(
            product_id=product.id,
            source=source,
            source_url=source_url,
            current_price=price,
            currency=currency or "EUR",
            last_checked_at=datetime.now(timezone.utc),
        )
        db.add(ps)
        product.sources.append(ps)
    elif ps is not None:
        if price is not None:
            ps.current_price = price
        if currency:
            ps.currency = currency
        if source_url:
            ps.source_url = source_url
        ps.last_checked_at = datetime.now(timezone.utc)

    if price is not None:
        db.add(PriceHistory(
            product_id=product.id,
            price=price,
            currency=currency or "EUR",
            source=source,
        ))

    _recompute_primary_snapshot(product)
    db.commit()
    db.refresh(product)


router = APIRouter(prefix="/api/products", tags=["Products"])


def _user_products_query(db: Session, user_id: int):
    return db.query(Product).filter(Product.user_id == user_id)


@router.get("/", response_model=List[ProductResponse])
def get_products(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    roi_min: Optional[float] = Query(None),
    roi_max: Optional[float] = Query(None),
    source: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listează produsele utilizatorului curent cu filtre și sortare opționale."""
    query = _user_products_query(db, current_user.id)

    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.ean.ilike(pattern),
                Product.category.ilike(pattern),
            )
        )
    if category:
        query = query.filter(Product.category.ilike(f"%{category.strip()}%"))
    if brand:
        # FlipRadar — cautarea de brand acopera nume, brand si categorie (match larg).
        b = brand.strip()
        query = query.filter(
            or_(
                Product.name.ilike(f"%{b}%"),
                Product.brand.ilike(f"%{b}%"),
                Product.category.ilike(f"%{b}%"),
            )
        )

    # FlipRadar — BUG 6: un singur set de parametri pentru pret (price_min/price_max).
    if price_min is not None:
        query = query.filter(Product.current_price >= price_min)
    if price_max is not None:
        query = query.filter(Product.current_price <= price_max)
    if source:
        query = query.filter(Product.source == source)

    if roi_min is not None:
        # ROI = ((revanzare - curent) / curent) * 100, doar când ambele sunt prezente și curent > 0
        query = query.filter(
            Product.resale_price.isnot(None),
            Product.current_price.isnot(None),
            Product.current_price > 0,
            ((Product.resale_price - Product.current_price) / Product.current_price * 100) >= roi_min,
        )

    if roi_max is not None:
        # ROI = ((revanzare - curent) / curent) * 100 — oglinda lui roi_min, prag superior (<=)
        query = query.filter(
            Product.resale_price.isnot(None),
            Product.current_price.isnot(None),
            Product.current_price > 0,
            ((Product.resale_price - Product.current_price) / Product.current_price * 100) <= roi_max,
        )

    sort_key = (sort_by or "").lower()
    if sort_key == "price_asc":
        query = query.order_by(Product.current_price.asc().nullslast())
    elif sort_key == "price_desc":
        query = query.order_by(Product.current_price.desc().nullslast())
    elif sort_key == "name_asc":
        query = query.order_by(Product.name.asc())
    elif sort_key == "newest":
        query = query.order_by(Product.created_at.desc())
    elif sort_key == "roi_desc":
        # FlipRadar — BUG 4: sorteaza dupa ROI procentual real, nu dupa diferenta absoluta.
        from sqlalchemy import case
        roi_expr = case(
            (Product.current_price > 0,
             (Product.resale_price - Product.current_price) / Product.current_price * 100),
            else_=None
        )
        query = query.order_by(roi_expr.desc().nullslast())

    return query.offset(skip).limit(limit).all()


@router.get("/filter-options")
def get_filter_options(
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """FlipRadar — branduri si categorii distincte din catalogul utilizatorului,
    direct din baza de date. Optional filtrate dupa sursa (magazin) selectata."""
    base = db.query(Product).filter(
        Product.user_id == current_user.id
    )
    if source:
        base = base.filter(Product.source == source)

    brands_q = (
        base.filter(Product.brand.isnot(None))
        .with_entities(Product.brand)
        .distinct()
        .order_by(Product.brand)
        .limit(100)
        .all()
    )
    categories_q = (
        base.filter(Product.category.isnot(None))
        .with_entities(Product.category)
        .distinct()
        .order_by(Product.category)
        .limit(100)
        .all()
    )

    return {
        "brands": [r[0] for r in brands_q if r[0]],
        "categories": [r[0] for r in categories_q if r[0]],
    }


@router.get("/brands")
def get_brands(
    source: Optional[str] = Query(None),
    q: Optional[str] = Query(None, min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """FlipRadar — autocomplete brand: branduri distincte din catalogul
    utilizatorului, filtrate optional dupa sursa si dupa prefixul `q`."""
    query = (
        db.query(Product.brand)
        .filter(Product.user_id == current_user.id, Product.brand.isnot(None))
    )
    if source:
        query = query.filter(Product.source == source)
    if q:
        query = query.filter(Product.brand.ilike(f"{q.strip()}%"))
    rows = query.distinct().order_by(Product.brand).limit(20).all()
    return [r[0] for r in rows if r[0]]


# FlipRadar — taxonomie fixa de categorii per magazin (nu vine din DB).
# Cheile sunt forma scurta a sursei; endpoint-ul accepta si domeniul ("altex.ro").
CATEGORIES_BY_SOURCE = {
    "altex": [
        {"name": "Telefoane", "sub": ["Smartphone", "Accesorii telefoane"]},
        {"name": "Laptopuri", "sub": ["Gaming", "Ultrabook", "Business"]},
        {"name": "TV & Audio", "sub": ["Televizoare", "Sisteme audio", "Casti"]},
        {"name": "Electrocasnice mari", "sub": ["Frigidere", "Masini de spalat", "Aragazuri"]},
        {"name": "Electrocasnice mici", "sub": ["Aspiratoare", "Cafetiere", "Fiare de calcat"]},
    ],
    "emag": [
        {"name": "Telefoane & Tablete", "sub": ["Smartphone", "Tablete", "Accesorii"]},
        {"name": "Laptopuri & PC", "sub": ["Laptopuri", "Desktop PC", "Componente"]},
        {"name": "TV, Audio-Video", "sub": ["Televizoare", "Boxe", "Casti"]},
        {"name": "Electrocasnice", "sub": ["Frigidere", "Masini de spalat", "Aspiratoare"]},
        {"name": "Fashion", "sub": ["Imbracaminte", "Incaltaminte", "Accesorii"]},
    ],
    "pcgarage": [
        {"name": "Componente PC", "sub": ["Procesoare", "Placi video", "RAM", "SSD"]},
        {"name": "Periferice", "sub": ["Mouse", "Tastatura", "Monitor", "Casti gaming"]},
    ],
    "sole": [
        {"name": "Cosmetice", "sub": ["Ingrijire ten", "Machiaj", "Parfumuri"]},
        {"name": "Sanatate", "sub": ["Vitamine", "Suplimente", "Dispozitive medicale"]},
    ],
    "farmaciatei": [
        {"name": "Medicamente OTC", "sub": ["Durere", "Raceala si gripa", "Digestive"]},
        {"name": "Cosmetice", "sub": ["Dermatocosmetice", "Ingrijire corp"]},
    ],
}


@router.get("/categories-by-source")
def get_categories_by_source(
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """FlipRadar — categorii fixe per magazin (taxonomie hardcodata, fara DB).
    Accepta atat forma scurta ('altex') cat si domeniul ('altex.ro')."""
    key = (source or "").lower().replace(".ro", "").strip()
    return CATEGORIES_BY_SOURCE.get(key, [])


@router.get("/source-categories")
def get_source_categories(
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    from app.constants.source_categories import SOURCE_CATEGORIES
    if source and source in SOURCE_CATEGORIES:
        return {"source": source, "categories": SOURCE_CATEGORIES[source]}
    return {"sources": list(SOURCE_CATEGORIES.keys()),
            "all": SOURCE_CATEGORIES}


@router.get("/stats")
def get_products_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Statistici de profitabilitate din catalogul utilizatorului (folosește resale_price)."""
    rows = (
        db.query(Product.current_price, Product.resale_price)
        .filter(Product.user_id == current_user.id)
        .all()
    )
    profit_estimat_total = 0.0
    roi_values: list[float] = []
    produse_profitabile = 0
    produse_fara_pret_revanzare = 0
    total = len(rows)

    for current_price, resale_price in rows:
        if resale_price is None:
            produse_fara_pret_revanzare += 1
            continue
        if current_price is None or current_price <= 0:
            continue
        diff = float(resale_price) - float(current_price)
        if diff > 0:
            profit_estimat_total += diff
            produse_profitabile += 1
        roi_values.append((diff / float(current_price)) * 100.0)

    roi_mediu = round(sum(roi_values) / len(roi_values), 2) if roi_values else 0.0

    return {
        "total_products": total,
        "profit_estimat_total": round(profit_estimat_total, 2),
        "roi_mediu": roi_mediu,
        "produse_profitabile": produse_profitabile,
        "produse_fara_pret_revanzare": produse_fara_pret_revanzare,
        "produse_cu_pret_revanzare": total - produse_fara_pret_revanzare,
    }


def _build_detail_response(db: Session, product: Product) -> dict:
    """Construieste payload-ul ProductDetailResponse (produs + istoric + sugestii +
    agregate de pret). Reutilizat de GET detail si de confirmarea unei sugestii."""
    price_history = (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product.id)
        .order_by(PriceHistory.recorded_at.desc())
        .all()
    )
    prices = [ph.price for ph in price_history]
    return {
        "product": product,
        "price_history": price_history,
        "suggestions": product.suggestions,
        "lowest_price": min(prices) if prices else None,
        "highest_price": max(prices) if prices else None,
        "average_price": round(sum(prices) / len(prices), 2) if prices else None,
    }


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    return _build_detail_response(db, product)


def _normalize_name(name: str) -> str:
    return " ".join((name or "").lower().split())


def _build_save_response(product: Product, is_new: bool, previous_price: Optional[float]) -> dict:
    price_changed = (
        (not is_new)
        and previous_price is not None
        and product.current_price is not None
        and round(float(previous_price), 2) != round(float(product.current_price), 2)
    )
    return {
        "id": product.id,
        "name": product.name,
        "ean": product.ean,
        "sku": product.sku,
        "brand": product.brand,
        "category": product.category,
        "subcategory": product.subcategory,
        "image_url": product.image_url,
        "description": product.description,
        "source": product.source,
        "source_url": product.source_url,
        "current_price": product.current_price,
        "original_price": product.original_price,
        "resale_price": product.resale_price,
        "currency": product.currency,
        "created_at": product.created_at,
        "is_new": is_new,
        "previous_price": previous_price,
        "price_changed": price_changed,
    }


def _backfill_ean(product_id: int, source_url: str) -> None:
    """Preia EAN-ul din pagina de detalii a produsului în background și îl persistă."""
    if not source_url:
        return
    db: Session = SessionLocal()
    try:
        ean = fetch_ean_from_url(source_url)
        if not ean:
            return
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and not product.ean:
            product.ean = ean
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"[EAN backfill] Eroare pentru product_id={product_id}: {e}")
    finally:
        db.close()


def _cross_shop_match(product_id: int) -> None:
    """Task de fundal: caută același produs pe celelalte magazine. Potrivirile prin
    EAN se atașează automat ca surse; potrivirile pe nume devin sugestii ce așteaptă
    confirmarea utilizatorului (nu intră în calculul current_price)."""
    db: Session = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return
        matches = find_cross_shop_matches(product.name, product.ean, product.source)

        # Potriviri confirmate prin EAN -> atasate automat ca surse.
        for m in matches["ean_matches"]:
            attach_source_to_product(
                db, product,
                m.get("source"), m.get("source_url"),
                m.get("price"), m.get("currency"),
            )

        # Potriviri doar pe nume -> sugestii (nu intra in current_price pana la confirmare).
        for c in matches["name_candidates"]:
            src = c.get("source")
            if not src or not c.get("source_url"):
                continue
            # Sare peste sursele deja atasate (ex. confirmate prin EAN in acelasi run).
            if any(s.source == src for s in product.sources):
                continue
            exists = db.query(ProductSourceSuggestion).filter_by(
                product_id=product.id, source=src).first()
            if not exists:
                db.add(ProductSourceSuggestion(
                    product_id=product.id,
                    source=src,
                    source_url=c.get("source_url"),
                    name=c.get("name"),
                    price=c.get("price"),
                    currency=c.get("currency") or "EUR",
                ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[cross-shop match] Eroare pentru product_id={product_id}: {e}")
    finally:
        db.close()


@router.post("/", response_model=ProductSaveResponse)
def create_product(
    product_data: ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Salvează un produs pentru utilizatorul curent.

    Deduplicarea este per utilizator:
    1. Potrivire EAN/SKU -> dacă aceeași sursă: actualizează ProductSource existent. Dacă
       sursă diferită: adaugă un nou ProductSource la Produsul existent.
    2. Potrivire (name, source) -> actualizează ProductSource existent pe acea sursă.
    3. Altfel -> creează Product nou + primul ProductSource.
    """

    def _add_or_update_source(existing: Product) -> dict:
        old_primary_price = existing.current_price
        # Completeaza campurile lipsa la nivel de produs din datele noi.
        if product_data.ean and not existing.ean:
            existing.ean = product_data.ean
        if product_data.sku and not existing.sku:
            existing.sku = product_data.sku
        if product_data.image_url and not existing.image_url:
            existing.image_url = product_data.image_url

        # Scrierea sursei (ProductSource + PriceHistory + recompute + commit) e
        # extrasa in attach_source_to_product (reutilizata si de cross-shop matching).
        attach_source_to_product(
            db, existing,
            product_data.source, product_data.source_url,
            product_data.current_price, product_data.currency,
        )
        return _build_save_response(existing, is_new=False, previous_price=old_primary_price)

    user_products = _user_products_query(db, current_user.id)

    if product_data.ean:
        existing_ean = user_products.filter(Product.ean == product_data.ean).first()
        if existing_ean:
            return _add_or_update_source(existing_ean)

    if product_data.sku:
        existing_sku = user_products.filter(Product.sku == product_data.sku).first()
        if existing_sku:
            return _add_or_update_source(existing_sku)

    if product_data.source:
        normalized = _normalize_name(product_data.name)
        same_site_match = (
            user_products
            .filter(func.lower(Product.name) == normalized)
            .filter(Product.source == product_data.source)
            .first()
        )
        if same_site_match is not None:
            return _add_or_update_source(same_site_match)

    new_product = Product(**product_data.model_dump(), user_id=current_user.id)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    if new_product.source and new_product.source_url:
        db.add(ProductSource(
            product_id=new_product.id,
            source=new_product.source,
            source_url=new_product.source_url,
            current_price=new_product.current_price,
            currency=new_product.currency or "EUR",
            last_checked_at=datetime.now(timezone.utc),
        ))

    if new_product.current_price:
        db.add(PriceHistory(
            product_id=new_product.id,
            price=new_product.current_price,
            currency=new_product.currency,
            source=new_product.source,
        ))

    db.commit()
    db.refresh(new_product)

    if not new_product.ean and new_product.source_url:
        background_tasks.add_task(_backfill_ean, new_product.id, new_product.source_url)

    # Cross-shop matching DOAR pe ramura de produs nou. BackgroundTasks ruleaza
    # secvential in ordinea adaugarii, deci porneste dupa _backfill_ean si vede
    # EAN-ul proaspat completat daca a fost gasit.
    background_tasks.add_task(_cross_shop_match, new_product.id)

    return _build_save_response(new_product, is_new=True, previous_price=None)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizează câmpurile editabile ale unui produs al utilizatorului. Doar câmpurile trimise se modifică."""
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        new_name = (changes["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Numele produsului nu poate fi gol")
        changes["name"] = new_name

    price_changed = (
        "current_price" in changes
        and changes["current_price"] is not None
        and product.current_price != changes["current_price"]
    )

    for key, value in changes.items():
        setattr(product, key, value)

    if price_changed:
        db.add(PriceHistory(
            product_id=product.id,
            price=product.current_price,
            currency=product.currency or "EUR",
            source=product.source,
        ))

    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/refresh-price", response_model=RefreshAllSourcesResponse)
def refresh_product_price(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-scrapeaza prețul live pentru fiecare sursă a unui produs. Secvențial cu
    delay aleatoriu între cereri pentru a evita blocarea IP-ului."""
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")
    if not product.sources:
        raise HTTPException(status_code=400, detail="Produsul nu are nicio sursa scrapeable.")

    results: List[RefreshSourceResult] = []
    now = datetime.now(timezone.utc)
    for i, ps in enumerate(product.sources):
        if i > 0:
            time.sleep(random.uniform(*_SCRAPE_DELAY_RANGE))
        old_price = ps.current_price
        try:
            new_price = refresh_price_from_source(
                source=ps.source,
                source_url=ps.source_url,
                product_name=product.name,
                sku=product.sku,
            )
        except Exception as e:
            results.append(RefreshSourceResult(
                source=ps.source, source_url=ps.source_url,
                old_price=old_price, new_price=None, currency=ps.currency,
                changed=False, success=False, error=str(e),
            ))
            continue
        ps.last_checked_at = now
        if new_price is None:
            results.append(RefreshSourceResult(
                source=ps.source, source_url=ps.source_url,
                old_price=old_price, new_price=None, currency=ps.currency,
                changed=False, success=False, error="Pretul nu a putut fi preluat de la sursa.",
            ))
            continue
        changed = old_price != new_price
        if changed:
            ps.current_price = new_price
            db.add(PriceHistory(
                product_id=product.id,
                price=new_price,
                currency=ps.currency or "EUR",
                source=ps.source,
            ))
        results.append(RefreshSourceResult(
            source=ps.source, source_url=ps.source_url,
            old_price=old_price, new_price=new_price, currency=ps.currency,
            changed=changed, success=True,
        ))

    _recompute_primary_snapshot(product)
    db.commit()
    db.refresh(product)
    return RefreshAllSourcesResponse(product=product, results=results)


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    db.delete(product)
    db.commit()
    return {"message": "Produsul a fost sters din baza de date"}


@router.post("/{product_id}/suggestions/{suggestion_id}/confirm", response_model=ProductDetailResponse)
def confirm_suggestion(
    product_id: int,
    suggestion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirmă o sugestie: o atașează ca ProductSource (intră în calculul
    current_price) și o șterge din lista de sugestii. Întoarce produsul actualizat."""
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    sug = (
        db.query(ProductSourceSuggestion)
        .filter(
            ProductSourceSuggestion.id == suggestion_id,
            ProductSourceSuggestion.product_id == product_id,
        )
        .first()
    )
    if not sug:
        raise HTTPException(status_code=404, detail="Sugestia nu a fost gasita")

    attach_source_to_product(
        db, product, sug.source, sug.source_url, sug.price, sug.currency, sug.name,
    )
    db.delete(sug)
    db.commit()
    db.refresh(product)
    return _build_detail_response(db, product)


@router.delete("/{product_id}/suggestions/{suggestion_id}")
def delete_suggestion(
    product_id: int,
    suggestion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Respinge (șterge) o sugestie de sursă fără a o atașa produsului."""
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    sug = (
        db.query(ProductSourceSuggestion)
        .filter(
            ProductSourceSuggestion.id == suggestion_id,
            ProductSourceSuggestion.product_id == product_id,
        )
        .first()
    )
    if not sug:
        raise HTTPException(status_code=404, detail="Sugestia nu a fost gasita")

    db.delete(sug)
    db.commit()
    return {"message": "Sugestia a fost respinsa."}
