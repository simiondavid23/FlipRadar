import random
import re
import time
import urllib.parse
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
    ProductFromUrlRequest,
    ProductFromUrlResponse,
    ExtractUrlRequest,
    ExtractPreviewResponse,
    RefreshSourceResult,
    RefreshAllSourcesResponse,
)
from app.utils.auth import get_current_user, require_feature
from app.utils.category_mapper import infer_category_from_name
from app.models.user import User
from app.services.currency_service import convert
from app.services.scraper_service import (
    fetch_ean_from_url,
    refresh_source,
    find_cross_shop_matches,
)
# Fara risc de ciclu de import: extractorul importa scraper_service DOAR lenes,
# in corpul lui extract_product (vezi comentariul de acolo).
from app.services.product_page_extractor import (
    extract_product,
    ProductExtractionError,
    VALIDATED_DOMAINS,
)
# LOT1 — politica de identitate a URL-ului per magazin (vezi create_product_from_url).
from app.services.shop_registry import url_identity_of

_SCRAPE_DELAY_RANGE = (0.6, 1.4)


def _recompute_primary_snapshot(product: Product) -> None:
    """Setează product.current_price/currency/source/source_url pe baza sursei
    cu prețul cel mai mic (cu comparație după conversie valutară). Minimul se ia
    peste toate sursele ȘI variantele produsului."""
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
    variant: str = "",
) -> None:
    """Creează sau actualizează un ProductSource pe produs + PriceHistory, apoi
    recalculează snapshot-ul primar (current_price = minimul dintre surse) și face
    commit. Reutilizabilă din create_product și din task-ul de cross-shop matching.

    `name` e acceptat pentru compatibilitate de semnătură (ProductSource nu are
    coloană de nume — numele produsului e pe Product).

    `variant` (mărimea) face parte din identitatea sursei: aceeași sursă cu mărimi
    diferite sunt rânduri distincte. `""` = fără variantă (rând la nivel de produs).
    """
    if not source:
        return
    # RETAIL-AUDIT (5.3e): un pret 0 venit dintr-o parsare esuata (ex. card de
    # cautare fara pret) NU e un pret — atasat, devenea snapshot 0 si "0 <= tinta"
    # declansa alerta de pret la fiecare ciclu. Sursa se ataseaza, pretul nu.
    if price is not None and not (isinstance(price, (int, float)) and float(price) > 0):
        price = None
    ps = next((s for s in product.sources
               if s.source == source and (s.variant or "") == variant), None)
    if ps is None and source_url:
        ps = ProductSource(
            product_id=product.id,
            source=source,
            source_url=source_url,
            current_price=price,
            currency=currency or "EUR",
            variant=variant,
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
            variant=variant,
        ))

    _recompute_primary_snapshot(product)
    db.commit()
    db.refresh(product)


router = APIRouter(prefix="/api/products", tags=["Products"])

# Adaugarea prin link face fetch server-side pe un URL dat de user — aceeasi
# suprafata de scraping ca routerul /api/scraping, deci acelasi gard de feature.
_scraping_user = require_feature("can_use_scraping")


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


@router.get("/stats")
def get_products_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Statistici de profitabilitate din catalogul utilizatorului (folosește resale_price).

    profit_estimat_total e in EUR (convertit per produs din moneda produsului).
    """
    rows = (
        db.query(Product.current_price, Product.resale_price, Product.currency)
        .filter(Product.user_id == current_user.id)
        .all()
    )
    profit_estimat_total = 0.0
    roi_values: list[float] = []
    produse_profitabile = 0
    produse_fara_pret_revanzare = 0
    total = len(rows)

    for current_price, resale_price, currency in rows:
        if resale_price is None:
            produse_fara_pret_revanzare += 1
            continue
        if current_price is None or current_price <= 0:
            continue
        diff = float(resale_price) - float(current_price)
        if diff > 0:
            # DASH-1: diferenta e in moneda produsului — convertim per produs
            # ca totalul sa fie EUR (scraperele Catalog scriu RON, default EUR).
            profit_estimat_total += convert(diff, currency or "EUR", "EUR")
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
            variant=product_data.variant,
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

    # `variant` e camp de SURSA, nu de produs: Product nu are coloana, deci ar pica
    # cu TypeError daca l-am trece prin **model_dump().
    new_product = Product(**product_data.model_dump(exclude={"variant"}), user_id=current_user.id)
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
            variant=product_data.variant,
            last_checked_at=datetime.now(timezone.utc),
        ))

    if new_product.current_price:
        db.add(PriceHistory(
            product_id=new_product.id,
            price=new_product.current_price,
            currency=new_product.currency,
            source=new_product.source,
            variant=product_data.variant,
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


def _host_key(url: str) -> str:
    """Hostname lowercase fara "www." — aceeasi cheie de domeniu ca extractorul."""
    try:
        host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _normalize_source_path(u: str) -> str:
    """Colapseaza secventele de `/` din CALEA unui URL, restul neatins.

    Doar calea: schema (`https://`) ramane intacta, la fel query-ul si fragmentul.
    Masurat la LOT3b pe spartoo.ro, care serveste identic `/Nike-x.php` si
    `//Nike-x.php` fara redirect si fara canonical care sa normalizeze — deci doua
    forme ale aceluiasi produs ar trece amandoua de dedup si ar deveni doua surse.
    """
    if not u:
        return u
    try:
        parts = urllib.parse.urlsplit(u)
    except Exception:
        return u
    cale = re.sub(r"/{2,}", "/", parts.path)
    if cale == parts.path:
        return u
    return urllib.parse.urlunsplit(parts._replace(path=cale))


def _from_url_http_error(exc: ProductExtractionError, url: str) -> HTTPException:
    """ProductExtractionError.reason -> status + mesaj pentru UI."""
    if exc.reason == "domain_not_allowed":
        host = _host_key(url) or (url or "")[:80]
        return HTTPException(
            status_code=400,
            detail=f"Domeniul „{host}” nu este pe lista magazinelor suportate.",
        )
    if exc.reason in ("no_product_data", "invalid_price"):
        return HTTPException(
            status_code=422,
            detail="Nu am putut extrage datele produsului din această pagină.",
        )
    # fetch_failed / challenge (si orice motiv viitor): problema e la magazin.
    return HTTPException(
        status_code=502,
        detail="Magazinul nu a răspuns sau a blocat cererea. Încearcă din nou mai târziu.",
    )


@router.post("/extract-url", response_model=ExtractPreviewResponse)
def extract_url_preview(
    payload: ExtractUrlRequest,
    current_user: User = Depends(_scraping_user),
):
    """Perechea READ-ONLY a lui /from-url: citeste pagina si intoarce ce a gasit,
    FARA sa scrie nimic in baza.

    Exista pentru wizardul de adaugare prin link (FASHION-1d): pana acum el crea
    produsul la deschidere, ca sa aiba ce previzualiza, iar cu marimi asta ar fi
    lasat in urma randuri agregate parazite pentru fiecare link deschis si
    abandonat. Acum crearea se face la Finalizeaza, dupa alegerea marimii.

    Aceleasi garduri (auth + can_use_scraping) si EXACT aceeasi mapare de erori
    ca from-url — deliberat, ca preview-ul si salvarea sa esueze la fel.
    """
    url = (payload.url or "").strip()
    try:
        res = extract_product(url)
    except ProductExtractionError as exc:
        raise _from_url_http_error(exc, url)

    return {
        "name": res["name"],
        "price": res["price"],
        "currency": res["currency"],
        "in_stock": res["in_stock"],
        "image_url": res["image_url"],
        "is_aggregate": res["is_aggregate"],
        "domain_validated": res["domain"] in VALIDATED_DOMAINS,
        "variants": res.get("variants"),
    }


@router.post("/from-url", response_model=ProductFromUrlResponse)
def create_product_from_url(
    payload: ProductFromUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_scraping_user),
):
    """Adauga un produs pornind DOAR de la link-ul paginii de magazin.

    Extrage datele cu extractorul generic, apoi deleaga integral salvarea catre
    create_product: dedup-ul per user, snapshot-ul initial de pret si task-urile
    de fundal (backfill EAN + cross-shop) sunt deja acolo si raman singura
    implementare. Aici se adauga doar ce e specific link-ului: stocul pe sursa
    si meta de extractie in raspuns.
    """
    url = (payload.url or "").strip()
    try:
        res = extract_product(url)
    except ProductExtractionError as exc:
        raise _from_url_http_error(exc, url)

    # LOT1 — pe magazinele marcate `url_identity: "exact"` in registru, QUERY-ul e
    # parte din identitatea sursei, deci pastram URL-ul lipit de user (fara
    # fragment, care e stare de UI) si IGNORAM canonicalul. Pe flip.ro `?shape=`
    # alege starea produsului si odata cu ea pretul — masurat 2999.99 cu
    # `?shape=Excelent` vs 2849.99 fara — deci un canonical curatat de parametri ar
    # urmari alt pret decat cel vazut de user.
    #
    # Altfel: canonical-ul e preferat (taie parametrii de sesiune/tracking), dar
    # DOAR daca ramane pe acelasi magazin — un canonical catre alt domeniu ar muta sursa.
    canonical = res.get("canonical_url") or ""
    if url_identity_of(res["domain"]) == "exact":
        source_url = urllib.parse.urldefrag(url)[0] or url
    else:
        source_url = canonical if canonical and _host_key(canonical) == res["domain"] else (
            urllib.parse.urldefrag(url)[0] or url
        )
    # LOT3b — spartoo.ro serveste IDENTIC cu si fara dublu slash in cale, fara sa
    # redirecteze si fara sa normalizeze. Doua forme ale aceluiasi URL ar ocoli
    # dedup-ul si ar crea doua surse pentru acelasi produs, deci colapsam `//` in
    # CALE. Se aplica pe rezultatul FINAL, indiferent de ramura care l-a ales.
    source_url = _normalize_source_path(source_url)

    # FASHION-1c — cand userul cere o marime anume, ea devine sursa de adevar
    # pentru pret si stoc: agregatul "de la" al grupului ar fi pretul ALTEI marimi.
    # Spatiile din jur se taie (vin din formular), dar potrivirea ramane EXACTA —
    # etichetele sunt string liber ('40_5', '28_32'), fara semantica de normalizat.
    wanted = (payload.variant or "").strip()
    variants = res.get("variants")
    entry = None
    if wanted:
        if not variants:
            raise HTTPException(
                status_code=422,
                detail="Pagina nu publică oferte per mărime, deci nu putem urmări o mărime anume.",
            )
        entry = next((v for v in variants if v.get("variant") == wanted), None)
        if entry is None:
            disponibile = ", ".join(str(v.get("variant")) for v in variants if v.get("variant"))
            raise HTTPException(
                status_code=422,
                detail=f"Mărimea „{wanted}” nu este publicată pe această pagină. "
                       f"Mărimi disponibile: {disponibile}.",
            )

    # KEYWORD_MAP e cheiat pe slug-ul magazinului ("emag"), nu pe domeniu — acelasi
    # apel ca in scraperele de cautare, care intoarce (categorie, subcategorie).
    main_cat, sub_cat = infer_category_from_name(res["name"], res["domain"].split(".")[0])

    save = create_product(
        product_data=ProductCreate(
            name=res["name"],
            image_url=res["image_url"],
            source=res["domain"],
            source_url=source_url,
            current_price=entry["price"] if entry else res["price"],
            currency=res["currency"],
            category=main_cat,
            subcategory=sub_cat,
            variant=wanted,
        ),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )

    # Stocul e singurul camp pe care create_product nu-l cunoaste (ProductCreate e
    # la nivel de produs, nu de sursa) -> se scrie dupa salvare, pe sursa creata.
    # Filtrul pe varianta tine randul TINTA: acelasi magazin poate avea acum si
    # randuri pe marimi, iar un `.first()` nefiltrat ar fi nedeterminist.
    source_row = (
        db.query(ProductSource)
        .filter(ProductSource.product_id == save["id"],
                ProductSource.source == res["domain"],
                ProductSource.variant == wanted)
        .first()
    )
    if source_row is not None:
        source_row.in_stock = entry["in_stock"] if entry else res["in_stock"]
        db.commit()

    product = db.query(Product).filter(Product.id == save["id"]).first()
    return {
        **_build_detail_response(db, product),
        "is_new": save["is_new"],
        "previous_price": save["previous_price"],
        "price_changed": save["price_changed"],
        "domain_validated": res["domain"] in VALIDATED_DOMAINS,
        "extraction": {
            "method": res["method"],
            "override_applied": res["override_applied"],
            "in_stock": res["in_stock"],
            "is_aggregate": res["is_aggregate"],
        },
        # Marimile paginii, ca UI-ul sa poata propune alegerea (FASHION-1d).
        "variants": variants,
    }


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
            variant="",
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
            res = refresh_source(
                source=ps.source,
                source_url=ps.source_url,
                product_name=product.name,
                sku=product.sku,
                variant=ps.variant,
            )
        except Exception as e:
            results.append(RefreshSourceResult(
                source=ps.source, source_url=ps.source_url,
                old_price=old_price, new_price=None, currency=ps.currency,
                changed=False, success=False, error=str(e),
            ))
            continue
        new_price = res["price"] if res else None
        ps.last_checked_at = now
        # Stocul vine doar de pe calea "url"; None = necunoscut, deci nu suprascrie
        # o stare deja cunoscuta (aceeasi regula ca in alert_checker).
        if res and res.get("in_stock") is not None:
            ps.in_stock = res["in_stock"]
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
                variant=ps.variant or "",
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
