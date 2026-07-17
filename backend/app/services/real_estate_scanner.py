"""Periodic scanner for real_estate_keywords — 30 min interval.

Modelele noi sunt importate aliasate (RealEstateKeyword / RealEstateListing) catre
clasele distincte RealEstateMonitorKeyword / RealEstateMonitorListing, ca sa nu
existe coliziune cu modelul existent RealEstateListing (tabel real_estate_listing).
"""
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword as RealEstateKeyword
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing
from app.models.user import User
from app.services.real_estate.extractor import extract_all, groq_extract
from app.services.real_estate.scorer import compute_re_score, get_zone_avg_ppm
from app.services.real_estate.zones import normalize_zone, retroactive_normalize
from app.services.log_manager import log_manager, set_log_user


def _within_hours(kw: RealEstateKeyword) -> bool:
    if kw.active_hours_start is None or kw.active_hours_end is None:
        return True
    h = datetime.now().hour
    s, e = kw.active_hours_start, kw.active_hours_end
    return (s <= h < e) if s <= e else (h >= s or h < e)


def _polling_due(kw, now: datetime) -> bool:
    """PURA: True daca intervalul de polling per keyword a expirat de la ultimul scan.

    `now` (aware UTC) e injectat pentru testabilitate. Un last_scan_at naiv (fara tzinfo)
    e considerat UTC — aceeasi conventie ca la Radar.
    Fallback 30 min = default-ul RE (polling_interval_minutes), NU 5 ca la Radar.
    """
    if kw.last_scan_at is None:
        return True
    last = kw.last_scan_at.replace(tzinfo=timezone.utc) if kw.last_scan_at.tzinfo is None else kw.last_scan_at
    elapsed = now - last
    return elapsed >= timedelta(minutes=kw.polling_interval_minutes or 30)


def _due_keywords(keywords: list, now: datetime, force: bool) -> list:
    """PURA: keyword-urile scadente la `now`. force=True (scan manual) -> lista neschimbata."""
    if force:
        return keywords
    return [kw for kw in keywords if _polling_due(kw, now)]


def _is_groq_enabled(db: Session, user_id: int) -> bool:
    try:
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        cfg = getattr(user, "ai_features_config", None) or {}
        return cfg.get("ai_radar_review", True) is not False
    except Exception:
        return True


def _seed_from_raw(raw: dict) -> dict:
    """Mapeaza cheile emise de scrapere intr-un seed canonic (scraper > regex/Groq).

    Scraperele .ro (make_re_listing) emit chei romanesti (titlu/descriere/camere/
    suprafata_mp/etaj/moneda/locatie_oras/tip_proprietate), iar scraperul Facebook emite
    variante englezesti (title/description/price/currency/location). Citim cu fallback, in
    ordinea data, ca sa nu mai pierdem campurile structurate (bug: scannerul citea doar
    cheile EN si re-ghicea camerele/suprafata din regex, iar moneda din raw["currency"]
    inexistent => RON salvat ca EUR). Valorile None/"" raman None. `price` -> float daca se
    poate, altfel None. Returneaza un dict cu exact cheile de mai jos.
    """
    def pick(*keys):
        # primul din chei cu valoare ne-goala (None/"" sar), altfel None
        for k in keys:
            v = raw.get(k)
            if v not in (None, ""):
                return v
        return None

    price = pick("price", "pret")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    # listed_at: string ISO (emis de scraperul OLX) -> datetime; lipsa/invalid -> None.
    listed_at = raw.get("listed_at")
    if listed_at:
        try:
            listed_at = datetime.fromisoformat(str(listed_at))
        except (TypeError, ValueError):
            listed_at = None
    else:
        listed_at = None

    return {
        "title":         pick("title", "titlu"),
        "description":   pick("description", "descriere"),
        "rooms":         pick("camere"),
        "area_sqm":      pick("suprafata_mp"),
        "floor":         pick("etaj"),
        "price":         price,
        "currency":      pick("currency", "moneda"),
        "property_type": pick("property_type", "tip_proprietate"),
        # IMO-1 — `zone` (districtul din enrichment-ul OLX) are prioritate: e mai specific
        # decat "location"/orasul generic de pe card ("București, Sectorul 6").
        "zone_hint":     pick("zone", "location", "locatie_oras"),
        "listed_at":     listed_at,
    }


def _norm_ascii(s: str) -> str:
    """Normalizare partajata: NFKD -> ascii (fara diacritice), lower, strip.

    Folosita atat de _matches_query_local (cautare libera) cat si de _matches_exclusions (IM-6).
    """
    n = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return n.lower().strip()


def _matches_query_local(text: str, query: Optional[str]) -> bool:
    """True daca `text` contine toti termenii din `query` (cautare libera locala).

    Semantica: query gol/None => True. Query se sparge pe virgule in termeni; fiecare termen
    (normalizat cu _norm_ascii) trebuie sa apara ca substring in textul normalizat identic (AND
    intre termeni). Text None tratat ca "". Folosit pentru platformele care NU pot cauta liber la
    sursa (Storia, Imobiliare.ro, Grupuri FB); pe OLX si Facebook Marketplace query-ul merge la
    sursa, deci nu se aplica local.
    """
    if not query or not str(query).strip():
        return True
    hay = _norm_ascii(text)
    for term in str(query).split(","):
        t = _norm_ascii(term)
        if t and t not in hay:
            return False
    return True


def _matches_exclusions(text: str, exclude_words) -> bool:
    """True daca `text` NU contine NICIUN termen exclus (False = respins). IM-6.

    Semantica inversa fata de _matches_query_local: exclude_words None/gol => True (nu respinge);
    text None tratat ca ""; termenii se normalizeaza cu _norm_ascii (termeni goli ignorati); daca
    ORICE termen apare ca substring in textul normalizat => False. Aplicata local pe TOATE
    platformele (sursa nu poate exclude).
    """
    if not exclude_words:
        return True
    hay = _norm_ascii(text)
    for term in exclude_words:
        t = _norm_ascii(term)
        if t and t in hay:
            return False
    return True


# SCHED-2 — platformele Imobiliare, fiecare cu jobul ei (re_scan_).
# facebook_groups = ingest din tabelul facebook_group_posts (fara scraping live).
RE_PLATFORMS = ["olx", "storia", "imobiliare_ro", "facebook_marketplace", "facebook_groups"]


def _olx_query_with_zone(query, zone) -> Optional[str]:
    """IMO-1 — la OLX, zona intra in cautarea full-text q- (OLX cauta si in descrieri
    server-side): pre-ingusteaza rezultatele ca bugetul de enrichment sa se cheltuie
    pe candidati relevanti, nu pe tot orasul. Trade-off asumat: un anunt din zona
    care nu-si mentioneaza cartierul nicaieri nu va aparea. Ambele goale -> None."""
    parts = [str(p).strip() for p in (query, zone) if p and str(p).strip()]
    return " ".join(parts) or None


def _call_scraper(kw: RealEstateKeyword, eur_ron: Optional[float] = None, db=None) -> list:
    import asyncio
    platform = kw.platform
    # Cheile TREBUIE sa fie cele CITITE de scrapere (tip_anunt/tip_proprietate/pret_*/
    # camere_min/suprafata_*/locatie), NU numele coloanelor din model. Inainte scanner-ul
    # trimitea property_type/rooms/price_max (nepotrivite) -> filtrele nu ajungeau niciodata
    # la scrapere. tip_anunt/price_min sunt campuri noi pe keyword (vezi migrarea).
    filters = {
        "tip_anunt": kw.tip_anunt or "vanzare",
        "tip_proprietate": kw.property_type,
        "pret_min": int(float(kw.price_min)) if kw.price_min else None,
        "pret_max": int(float(kw.price_max)) if kw.price_max else None,
        "camere_min": kw.rooms,
        "suprafata_min": kw.area_min,
        "suprafata_max": kw.area_max,
        # Locatia trimisa la sursa e INTOTDEAUNA orasul (path/slug de oras confirmat live).
        # Zona (cartier) NU se mai suprapune peste oras — ramane criteriu LOCAL, verificat in
        # _matches_re_keyword (zone vs zone_normalized). Inainte "kw.zone or kw.city" trimitea
        # zona ca locatie => Storia cadea pe toata-romania, Imobiliare.ro primea path invalid,
        # OLX cauta textul zonei la nivel national.
        "locatie": kw.city,
        # IMO-1 — pe OLX zona intra in q- (cautare server-side si pe descrieri); pe
        # Storia/Imobiliare.ro zona ramane criteriu LOCAL, deci query-ul e neatins.
        "query": _olx_query_with_zone(kw.query, kw.zone) if platform == "olx" else kw.query,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    # OLX: categoria e servita PRE-CONVERTITA in EUR (fara carduri RON in SSR; sonda
    # 2026-07-11), iar filtrul de pret opereaza pe valoarea EUR afisata. Daca keyword-ul e in
    # RON, convertim marginile de pret in EUR inainte de a le trimite; altfel filtrul ar taia
    # dupa cifre RON pe preturi EUR. Fara curs (eur_ron None) lasam valorile neconvertite —
    # post-filtrul cu eur_ron=None ramane tolerant.
    if platform == "olx" and (kw.price_currency or "EUR").upper() == "RON" and eur_ron and eur_ron > 0:
        for _k in ("pret_min", "pret_max"):
            if filters.get(_k) is not None:
                filters[_k] = int(round(float(filters[_k]) / eur_ron))

    try:
        if platform == "olx":
            # query e deja in filters (search_olx_real_estate il transforma in segment q-).
            from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
            # IMO-1 — enrichment de detaliu doar pe anunturi NOI (mirror RP-3 din Radar):
            # trimitem external_id-urile deja cunoscute ale userului. Fara db (defensiv) ->
            # set gol, deci enrichment pe primele _ENRICH_CAP (comportament tolerant).
            skip = set()
            if db is not None:
                skip = {
                    ext for (ext,) in db.query(RealEstateListing.external_id)
                    .filter(RealEstateListing.user_id == kw.user_id,
                            RealEstateListing.platform == "olx",
                            RealEstateListing.external_id.isnot(None))
                    .all()
                }
            return asyncio.run(search_olx_real_estate(filters=filters, skip_enrich_ids=skip))
        elif platform == "storia":
            from app.scrapers.real_estate.storia_scraper import search_storia
            return asyncio.run(search_storia(filters=filters))
        elif platform == "imobiliare_ro":
            from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro
            return asyncio.run(search_imobiliare_ro(filters=filters))
        elif platform == "facebook_marketplace":
            # Scraper SINCRON (sync_playwright, sesiune storage_state) — apelat
            # direct, NU prin asyncio.run (sync_playwright nu merge in event loop).
            from app.scrapers.real_estate.facebook_real_estate import search_facebook_real_estate
            return search_facebook_real_estate(query=kw.query or "", filters=filters)
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"{platform} eroare: {str(exc)[:100]}")
    return []


def _save_listing(db: Session, kw: RealEstateKeyword,
                  raw: dict, groq_enabled: bool,
                  custom_aliases: dict,
                  eur_ron: Optional[float] = None) -> tuple:
    """Salveaza un anunt de platforma. Intoarce (listing | None, motiv) cu motiv in
    {"nou","duplicat","respins","invalid"} — scanner-ul numara dupa motiv."""
    ext_id = str(raw.get("external_id") or raw.get("platform_id") or "")
    if not ext_id:
        return None, "invalid"

    existing = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == kw.user_id,
        RealEstateListing.platform == kw.platform,
        RealEstateListing.external_id == ext_id,
    ).first()

    # Seed structurat din scraper (precedenta: scraper > regex/Groq).
    seed = _seed_from_raw(raw)
    title = seed["title"] or ""
    desc  = seed["description"] or ""
    text  = f"{title} {desc}"

    if existing:
        # Price change detection
        new_price_raw = raw.get("price") or raw.get("pret")
        try:
            new_price = float(new_price_raw) if new_price_raw else None
        except Exception:
            new_price = None
        if new_price and existing.price:
            old_p = float(existing.price)
            if old_p > 0:
                drop = (old_p - new_price) / old_p
                if drop >= 0.05:
                    # Price dropped ≥5% → update and flag
                    history = list(existing.price_history or [])
                    history.append({
                        "price": old_p,
                        "currency": existing.currency,
                        "date": existing.last_checked_at.isoformat()
                        if existing.last_checked_at else None,
                    })
                    existing.price_history = history
                    existing.price = new_price
                    existing.price_per_sqm = (
                        round(new_price / existing.area_sqm, 2)
                        if existing.area_sqm else None)
                    existing.last_price_change_at = datetime.now(timezone.utc)
                    log_manager.emit("real_estate", "WARN",
                        f"Preț scăzut {drop*100:.0f}%: {title[:60]}")
        existing.last_checked_at = datetime.now(timezone.utc)
        db.commit()
        return None, "duplicat"  # deja existent (nu e nou)

    # Excluderi per keyword (IM-6) — ORICE termen exclus in titlu+descriere => respins. Se aplica
    # DOAR salvarilor noi; un listing existent isi pastreaza update-ul de pret de mai sus.
    if not _matches_exclusions(text, kw.exclude_words):
        return None, "respins"

    # Extract structured data (regex/Groq), apoi suprascriem cu seed-ul scraperului.
    extracted = extract_all(text)

    # Overlay: campurile structurate din scraper au precedenta peste regex.
    for _k in ("rooms", "area_sqm", "floor"):
        if seed[_k] is not None:
            extracted[_k] = seed[_k]
    # Pret: daca regex-ul n-a prins pretul, foloseste-l pe cel din scraper (cu moneda lui).
    # FIX: inainte se citea raw.get("currency") inexistent la scraperele .ro => RON salvat ca EUR.
    if extracted.get("price") is None and seed["price"] is not None:
        extracted["price"] = seed["price"]
        extracted["currency"] = seed["currency"] or "EUR"
    # Recalculeaza pretul pe mp dupa orice suprascriere.
    _p, _a = extracted.get("price"), extracted.get("area_sqm")
    extracted["price_per_sqm"] = (round(_p / _a, 2) if _p and _a and _a > 0 else None)

    extracted = groq_extract(text, extracted, groq_enabled)

    # Zone normalization — text-first (zone_raw), cu fallback pe seed-ul structurat.
    zone_raw = (extracted.get("zone_raw") or seed["zone_hint"] or "")
    zone_norm = normalize_zone(zone_raw, kw.city, custom_aliases)

    # Filtru criterii pe listingul de platforma (inainte se aplica DOAR la Grupuri FB):
    # zona normalizata e injectata pentru comparatie; monedele diferite se normalizeaza cu
    # eur_ron in _matches_re_keyword.
    extracted["zone_normalized"] = zone_norm
    if not _matches_re_keyword(extracted, kw, eur_ron):
        return None, "respins"

    # Scoring
    zone_avg = get_zone_avg_ppm(
        db, RealEstateListing, kw.user_id,
        kw.city, zone_norm,
        extracted.get("rooms"), tip_anunt=kw.tip_anunt)
    price = extracted.get("price") or (float(raw.get("price") or 0) or None)
    currency = extracted.get("currency", "EUR")
    score, grade = (50, "C")
    if price and extracted.get("area_sqm"):
        score, grade = compute_re_score(
            price, currency, extracted["area_sqm"],
            extracted.get("rooms"), zone_norm, kw.city, zone_avg, tip_anunt=kw.tip_anunt)

    listing = RealEstateListing(
        user_id         = kw.user_id,
        keyword_id      = kw.id,
        platform        = kw.platform,
        external_id     = ext_id,
        source          = "platform",
        title           = title[:500],
        price           = price,
        currency        = currency,
        price_per_sqm   = extracted.get("price_per_sqm"),
        property_type   = seed["property_type"] or kw.property_type,
        rooms           = extracted.get("rooms"),
        area_sqm        = extracted.get("area_sqm"),
        floor           = extracted.get("floor"),
        zone_raw        = zone_raw[:200] if zone_raw else None,
        zone_normalized = zone_norm,
        city            = kw.city,
        furnished       = extracted.get("furnished"),
        image_url       = raw.get("thumbnail_url") or raw.get("image_url") or "",
        images_json     = raw.get("images", []),
        url             = raw.get("source_url") or raw.get("url") or "",
        # Vanzator (cand scraperul il ofera) — folosit pentru afisare in feed/export.
        seller_id       = raw.get("seller_id") or raw.get("owner_id") or None,
        description     = desc[:2000],
        score           = score,
        grade           = grade,
        listed_at       = seed["listed_at"],
        found_at        = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return listing, "nou"


def _parse_floor(val) -> Optional[int]:
    """Parseaza etajul extras (string liber) intr-un int comparabil; None daca nu se poate.

    "parter"/"demisol" -> 0, "3" -> 3, "3/10" -> 3. "mansarda"/"ultim"/altele necunoscute
    -> None (nu putem compara, deci nu respingem pe baza etajului)."""
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    if s.startswith("parter") or s.startswith("demisol"):
        return 0
    m = re.match(r"(\d{1,2})", s)
    if m:
        return int(m.group(1))
    return None


def _matches_re_keyword(extracted: dict, kw: RealEstateKeyword,
                        eur_ron: Optional[float] = None) -> bool:
    """True daca valorile extrase NU contrazic criteriile keyword-ului.

    TOLERANTA: un criteriu setat pe kw dar cu valoare extrasa necunoscuta (None) e tratat
    ca "nu se poate verifica" -> NU respinge. Respinge DOAR cand ambele valori exista si se
    contrazic clar. `property_type`, `tip_anunt` si `city` nu sunt produse de extractor, deci
    nu pot fi verificate din text (raman necontrolate).

    Pret: cand monedele coincid, comparatie directa (comportamentul de dinainte). Cand DIFERA
    si `eur_ron` e dat (>0), ambele parti se normalizeaza in EUR (valoare_ron / eur_ron)
    inainte de comparatie. Cand difera si eur_ron e None -> tolerant (nu respinge).
    """
    # Pret.
    price = extracted.get("price")
    if price is not None:
        ext_cur = (extracted.get("currency") or "EUR").upper()
        kw_cur = (kw.price_currency or "EUR").upper()
        try:
            p = float(price)
            if ext_cur == kw_cur:
                if kw.price_min is not None and p < float(kw.price_min):
                    return False
                if kw.price_max is not None and p > float(kw.price_max):
                    return False
            elif eur_ron and eur_ron > 0:
                # normalizeaza AMBELE parti in EUR si compara
                p_eur = p / eur_ron if ext_cur == "RON" else p
                kmin = kmax = None
                if kw.price_min is not None:
                    kmin = float(kw.price_min) / eur_ron if kw_cur == "RON" else float(kw.price_min)
                if kw.price_max is not None:
                    kmax = float(kw.price_max) / eur_ron if kw_cur == "RON" else float(kw.price_max)
                if kmin is not None and p_eur < kmin:
                    return False
                if kmax is not None and p_eur > kmax:
                    return False
            # else: monede diferite fara curs -> tolerant, nu respinge.
        except (TypeError, ValueError):
            pass

    # Camere — kw.rooms e MINIM (la fel ca filtrul trimis scraperelor: camere_min).
    rooms = extracted.get("rooms")
    if rooms is not None and kw.rooms is not None:
        try:
            if int(rooms) < int(kw.rooms):
                return False
        except (TypeError, ValueError):
            pass

    # IMO-1 — plafon de camere (rooms_max). Garsoniera = rooms=1 + rooms_max=1.
    if rooms is not None and getattr(kw, "rooms_max", None) is not None:
        try:
            if int(rooms) > int(kw.rooms_max):
                return False
        except (TypeError, ValueError):
            pass

    # Suprafata (min/max).
    area = extracted.get("area_sqm")
    if area is not None:
        try:
            a = float(area)
            if kw.area_min is not None and a < float(kw.area_min):
                return False
            if kw.area_max is not None and a > float(kw.area_max):
                return False
        except (TypeError, ValueError):
            pass

    # Etaj (min/max) — doar cand etajul extras e parsabil intr-un numar.
    floor = _parse_floor(extracted.get("floor"))
    if floor is not None:
        if kw.floor_min is not None and floor < kw.floor_min:
            return False
        if kw.floor_max is not None and floor > kw.floor_max:
            return False

    # Mobilat (bool) — ambele cunoscute si diferite -> respinge.
    furnished = extracted.get("furnished")
    if kw.furnished is not None and furnished is not None:
        if bool(kw.furnished) != bool(furnished):
            return False

    # Zona (substring, lax) — respinge doar cand ambele exista si nu se suprapun deloc.
    kw_zone = (kw.zone or "").strip().lower()
    zn = (extracted.get("zone_normalized") or "").strip().lower()
    if kw_zone and zn and kw_zone not in zn and zn not in kw_zone:
        return False

    return True


def _save_fb_group_post(db: Session, post: dict, kw: RealEstateKeyword,
                        groq_enabled: bool,
                        custom_aliases: dict,
                        eur_ron: Optional[float] = None) -> Optional[RealEstateListing]:
    """Convert facebook_group_post -> real_estate_listing pentru un keyword anume.

    FIX confiscare: postarea se salveaza DOAR daca datele extrase se POTRIVESC criteriilor
    keyword-ului (_matches_re_keyword, cu toleranta). Inainte, primul keyword care rula
    salva ORICE postare si o "confisca"; acum o postare pe care kw1 n-o potriveste ramane
    disponibila pentru kw2 s.a.m.d.

    O postare fizica se salveaza O SINGURA DATA per user — exista o constrangere DB unica
    pe (user_id, platform, external_id) (idx_re_listings_external), deci NU o putem stoca de
    mai multe ori (cate una per keyword). O prinde primul keyword care O POTRIVESTE; feed-ul
    nu arata duplicate ale aceleiasi postari sub keyword-uri diferite (cerinta de verificare).
    """
    ext_id = f"fbgroup_{post.get('id') or post.get('post_id','')}"
    if not ext_id or ext_id == "fbgroup_":
        return None

    # Deja salvata (de orice keyword al acestui user)? Constrangerea DB e pe user+platform+
    # external_id, deci verificam la fel — evitam un INSERT care ar crapa pe unicitate.
    existing = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == kw.user_id,
        RealEstateListing.external_id == ext_id,
    ).first()
    if existing:
        return None

    text = post.get("text") or ""
    # Excluderi per keyword (IM-6) — ORICE termen exclus in text => nu se salveaza.
    if not _matches_exclusions(text, kw.exclude_words):
        return None
    extracted = extract_all(text)
    extracted = groq_extract(text, extracted, groq_enabled)

    # Query (cautare libera) local — Grupurile FB nu se cauta la sursa; daca postarea nu
    # contine termenii din kw.query, nu o asociem acestui keyword.
    if kw.query and not _matches_query_local(text, kw.query):
        return None

    zone_raw = extracted.get("zone_raw") or post.get("zona") or ""
    zone_norm = normalize_zone(zone_raw, kw.city, custom_aliases)

    # Filtru criterii — postarea se asociaza cu acest keyword DOAR daca valorile extrase
    # nu contrazic criteriile lui (zona normalizata e injectata pentru comparatie; monedele
    # diferite se normalizeaza cu eur_ron).
    extracted["zone_normalized"] = zone_norm
    if not _matches_re_keyword(extracted, kw, eur_ron):
        return None

    price = extracted.get("price") or (float(post.get("pret") or 0) or None)
    currency = extracted.get("currency", "EUR")
    score, grade = 50, "C"
    if price and extracted.get("area_sqm"):
        zone_avg = get_zone_avg_ppm(
            db, RealEstateListing, kw.user_id, kw.city, zone_norm,
            extracted.get("rooms"), tip_anunt=kw.tip_anunt)
        score, grade = compute_re_score(
            price, currency, extracted["area_sqm"],
            extracted.get("rooms"), zone_norm, kw.city, zone_avg, tip_anunt=kw.tip_anunt)

    listing = RealEstateListing(
        user_id         = kw.user_id,
        keyword_id      = kw.id,
        platform        = "facebook_groups",
        external_id     = ext_id,
        source          = "facebook_groups",
        title           = text[:200],
        price           = price,
        currency        = currency,
        price_per_sqm   = extracted.get("price_per_sqm"),
        rooms           = extracted.get("rooms"),
        area_sqm        = extracted.get("area_sqm"),
        floor           = extracted.get("floor"),
        zone_raw        = zone_raw[:200] if zone_raw else None,
        zone_normalized = zone_norm,
        city            = kw.city,
        furnished       = extracted.get("furnished"),
        url             = post.get("group_url") or "",
        description     = text[:2000],
        score           = score,
        grade           = grade,
        listed_at       = post.get("created_at"),   # data postarii FB (deja pe post_dict)
        found_at        = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def run_real_estate_scan(db: Session, user_id: Optional[int] = None,
                         force_polling: bool = False,
                         platform: Optional[str] = None) -> None:
    """SCHED-2: scheduler-ul apeleaza cate o data PER PLATFORMA (`platform` setat),
    ca un scraper lent (FB Marketplace pe Playwright) sa nu-i intarzie pe ceilalti.
    Scan-now manual: user_id setat, platform=None. Polling-ul per keyword ramane
    autoritatea scadentei — jobul platformei doar restrange multimea.
    """
    set_log_user(user_id)  # MON-4 — scheduler: user_id=None (reset defensiv); manual: user-ul care a declansat
    query = db.query(RealEstateKeyword).join(User, RealEstateKeyword.user_id == User.id).filter(RealEstateKeyword.is_active == True, User.is_active == True)
    if user_id is not None:
        query = query.filter(RealEstateKeyword.user_id == user_id)
    if platform is not None:
        query = query.filter(RealEstateKeyword.platform == platform)
    keywords = query.all()
    if not keywords:
        return

    # Polling per keyword: scheduler-ul da tick des (5 min), dar scanam DOAR keyword-urile
    # scadente (decizia in _polling_due). Scan-ul manual paseaza force_polling=True si ocoleste
    # intervalul. Daca niciunul nu e scadent -> return FARA log (tick-ul de 5 min nu spameaza).
    now = datetime.now(timezone.utc)
    keywords = _due_keywords(keywords, now, force_polling)
    if not keywords:
        return

    log_manager.emit("real_estate", "SCAN",
        f"Imobiliare scan: {len(keywords)} keyword-uri scadente")

    # Curs BNR EUR/RON, O SINGURA DATA pe scan — normalizeaza monedele la filtrarea de pret
    # (post-filtru) si converteste marginile de pret OLX (categoria e servita in EUR). Daca nu
    # se poate obtine, ramane None => comparatiile pe monede diferite devin tolerante.
    try:
        from app.services.bnr_exchange import get_eur_ron
        eur_ron = get_eur_ron()
    except Exception:
        eur_ron = None

    for kw in keywords:
        set_log_user(kw.user_id)  # MON-4 — jurnalele acestui keyword apartin user-ului lui
        if not _within_hours(kw):
            log_manager.emit("real_estate", "INFO",
                f"Skip {kw.name!r} — interval orar inactiv")
            continue

        groq_enabled = _is_groq_enabled(db, kw.user_id)
        custom_aliases = {}
        settings = None
        try:
            from app.models.radar_settings import RadarSettings
            settings = db.query(RadarSettings).filter(
                RadarSettings.user_id == kw.user_id).first()
            if settings and settings.custom_zone_aliases:
                custom_aliases = dict(settings.custom_zone_aliases)
        except Exception:
            pass

        log_manager.emit("real_estate", "SCAN",
            f"Keyword {kw.name!r} · {kw.platform}")

        if kw.platform == "facebook_groups":
            # Pull unread posts from facebook_group_posts table
            new_count = 0
            try:
                from app.models.facebook_group_post import FacebookGroupPost
                from app.models.facebook_group_config import FacebookGroupConfig
                configs = db.query(FacebookGroupConfig).filter(
                    FacebookGroupConfig.user_id == kw.user_id,
                    FacebookGroupConfig.is_active == True,
                ).all()
                for cfg in configs:
                    # coloana FacebookGroupPost.created_at e naivă-UTC (default=datetime.utcnow);
                    # migrarea completă pe timezone-aware rămâne post-licență.
                    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)
                    posts = db.query(FacebookGroupPost).filter(
                        FacebookGroupPost.config_id == cfg.id,
                        FacebookGroupPost.created_at >= cutoff,
                    ).all()
                    for post in posts:
                        post_dict = {c.name: getattr(post, c.name)
                                     for c in post.__table__.columns}
                        saved = _save_fb_group_post(
                            db, post_dict, kw, groq_enabled, custom_aliases, eur_ron)
                        if saved:
                            new_count += 1
                            _notify_re(saved, kw, settings, db)
            except Exception as exc:
                log_manager.emit("real_estate", "ERR",
                    f"FB Groups ingest: {str(exc)[:80]}")
            log_manager.emit("real_estate", "OK",
                f"{kw.platform}: {new_count} anunțuri noi")
        else:
            results = _call_scraper(kw, eur_ron, db=db)
            total_brute = len(results)
            noi = dup = rej = 0
            for r in results:
                # Query (cautare libera) local DOAR pentru platformele care nu cauta la sursa
                # (Storia, Imobiliare.ro). Pe OLX/Facebook Marketplace query-ul merge la sursa.
                if kw.platform in ("storia", "imobiliare_ro") and kw.query:
                    seed = _seed_from_raw(r)
                    text_q = f"{seed['title'] or ''} {seed['description'] or ''}"
                    if not _matches_query_local(text_q, kw.query):
                        rej += 1
                        continue
                saved, motiv = _save_listing(db, kw, r, groq_enabled, custom_aliases, eur_ron)
                if motiv == "nou":
                    noi += 1
                    _notify_re(saved, kw, settings, db)
                elif motiv == "duplicat":
                    dup += 1
                elif motiv == "respins":
                    rej += 1
            log_manager.emit("real_estate", "OK",
                f"{kw.platform}: {total_brute} brute -> {noi} noi, {dup} duplicate, {rej} respinse")

        # Marcheaza scanul efectiv pentru polling-ul per keyword — DUPA procesare, indiferent de
        # rezultat (0 anunturi sau eroare deja logata). Un keyword sarit de _within_hours NU
        # ajunge aici, deci NU "consuma" intervalul.
        kw.last_scan_at = datetime.now(timezone.utc)
        db.commit()
    set_log_user(None)  # MON-4 — dupa bucla, emit-urile redevin system


def _notify_re(listing: RealEstateListing, kw: RealEstateKeyword,
               settings, db: Session) -> None:
    if kw.notify_discord:
        try:
            from app.services.discord_service import send_imob_notification
            from app.services.real_estate.scorer import get_zone_avg_ppm
            zone_avg = get_zone_avg_ppm(
                db, RealEstateListing, kw.user_id,
                listing.city, listing.zone_normalized, listing.rooms, tip_anunt=kw.tip_anunt)
            listing_dict = {c.name: getattr(listing, c.name)
                            for c in listing.__table__.columns}
            listing_dict["price"] = float(listing.price or 0)
            send_imob_notification(
                listing_dict, listing.grade, listing.score,
                kw.name, settings, f"re_{listing.id}", db, zone_avg)
        except Exception as exc:
            log_manager.emit("real_estate", "WARN",
                f"Notificare Discord imob esuata: {str(exc)[:60]}")

    if listing.grade in ("A", "B") and kw.notify_email:
        try:
            from app.models.user import User
            from app.services.email_service import is_configured as smtp_configured, send_email
            user = db.query(User).filter(User.id == kw.user_id).first()
            if user and user.email and smtp_configured():
                _send_email_alert_re(user, kw, listing, send_email)
        except Exception as exc:
            log_manager.emit("real_estate", "WARN",
                f"Email imob esuat: {str(exc)[:60]}")


def _send_email_alert_re(user, kw, listing, send_email) -> None:
    subject = f"[Imobiliare] {listing.grade} — {(listing.title or '')[:60]}"
    body = (
        f"Salut!\n\n"
        f"Un anunt cu grad {listing.grade} a fost detectat pe {listing.platform}.\n"
        f"Keyword: {kw.name}\n"
        f"Titlu: {listing.title}\n"
        f"Zona: {listing.zone_normalized or listing.city or '—'}\n"
        f"Camere: {listing.rooms or '—'} · Suprafata: {listing.area_sqm or '—'} mp\n"
        f"Pret: {listing.price} {listing.currency or 'EUR'}\n"
        f"Link: {listing.url}\n"
        f"\n-- FlipRadar Imobiliare"
    )
    send_email(user.email, subject, body)


def run_cleanup(db: Session) -> int:
    """Daily cleanup: HEAD check URLs, remove 404.

    CLEAN-1: ordonare pe last_checked_at (rotatie reala — inainte, fara ordering,
    aceleasi ~200 randuri arbitrare erau verificate zilnic si restul niciodata),
    curl_cffi cu impersonate in loc de `requests` gol (blocat de platforme), si
    ambele platforme facebook excluse (login-wall neautentificat = neverificabil).
    Doar 404/410 sterge; orice altceva sau exceptie inseamna doar ca randul a fost
    atins (last_checked_at=now), ca rotatia sa treaca mai departe.

    CLEAN-2: HEAD-ul nu mai e crezut singur — sonda a dovedit ca Publi24 raspunde 404
    la HEAD pe anunturi VII (GET 200), iar aici 404-ul STERGE definitiv. Singura
    decizie luata direct din HEAD e "e viu" (200); orice altceva se confirma cu GET.
    """
    import random
    import time

    from curl_cffi import requests as curl_requests

    listings = db.query(RealEstateListing).filter(
        RealEstateListing.status == "active",
        RealEstateListing.platform.notin_(("facebook_groups", "facebook_marketplace")),
        RealEstateListing.url.isnot(None),
    ).order_by(RealEstateListing.last_checked_at.asc().nullsfirst()).limit(200).all()

    deleted = 0
    for listing in listings:
        gone = False
        try:
            head = curl_requests.head(listing.url, impersonate="chrome110",
                                      timeout=10, allow_redirects=True)
            head_ok = head.status_code == 200
        except Exception:
            head_ok = False   # eroare de retea != anunt disparut; lasam GET-ul sa decida
        if not head_ok:
            # CLEAN-2 — orice non-200 la HEAD (inclusiv 404/410, care pe Publi24 apar
            # si pe anunturi vii) se confirma cu GET; doar GET-ul poate declansa stergerea.
            try:
                resp = curl_requests.get(listing.url, impersonate="chrome110",
                                         timeout=10, allow_redirects=True)
                gone = resp.status_code in (404, 410)
            except Exception:
                gone = False
        if gone:
            db.delete(listing)
            deleted += 1
        else:
            listing.last_checked_at = datetime.now(timezone.utc)
        time.sleep(random.uniform(0.4, 1.0))

    db.commit()
    if deleted:
        log_manager.emit("real_estate", "WARN",
            f"Cleanup: {deleted} anunțuri dispărute șterse")
    return deleted
