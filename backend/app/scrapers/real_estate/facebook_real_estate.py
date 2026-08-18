"""Facebook Marketplace — categoria Property Rentals (chirii imobiliare).

Reutilizeaza aceeasi sesiune autentificata ca facebook_auto_scraper (storage_state
Playwright salvat in data/facebook_session_{user_id}.json). Functie SINCRONA — la
fel ca facebook_auto, dispecerul din real_estate_scanner o apeleaza DIRECT, nu prin
asyncio.run (sync_playwright nu poate rula intr-un event loop asyncio).
"""
import json
import os
import re
import urllib.parse
from typing import Optional

from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES, RE_PROPERTY_TYPES

_CATEGORY_SLUGS = {"vanzare": "propertyforsale", "inchiriere": "propertyrentals"}


def _category_url(tip_anunt: str) -> str:
    slug = _CATEGORY_SLUGS.get((tip_anunt or "inchiriere").lower(), "propertyrentals")
    return f"https://www.facebook.com/marketplace/category/{slug}/"


def _parse_price(raw: str) -> Optional[float]:
    """SCRAPE-AUDIT: replace-ul orb facea "RON 1,500" -> 1.5 (Marketplace foloseste
    frecvent formatul EN cu virgula de mii). Virgula in grupuri de 3 = mii.

    Aceeasi regula, forma canonica pentru cod NOU: app/utils/number_format.parse_number
    (vezi si services/real_estate/extractor._clean_number). Copia asta ramane fiindca
    are preprocesare proprie si teste proprii — unificarea e o curatenie separata.
    """
    cleaned = re.sub(r"[^\d.,]", "", raw or "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", cleaned):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


# SCRAPE-1d: o linie de card e candidat de PRET doar daca poarta valuta explicit.
# Vechiul criteriu re.match(r"^\d", line) lua orice linie care incepe cu o cifra —
# titlul "2 camere de inchiriat, mobilat" iesea ca price=2.0 si impingea pretul real
# in pozitia de titlu. Lookaround-ul (?<![^\W\d_]) = "nu e lipit de o litera" (unicode,
# deci si diacriticele romanesti): prinde "1500lei" dar nu "Aleile" sau "leilor".
_CUR_TOKEN = r"(?:€|(?<![^\W\d_])(?:euro|eur|ron|lei)(?![^\W\d_]))"
_EUR_CURRENCY_RE = re.compile(r"€|(?<![^\W\d_])(?:euro|eur)(?![^\W\d_])", re.IGNORECASE)

# FBM-1b, pasul 1: linie PUR pret — toata linia e numar + valuta (+ perioada
# optionala): "350 €", "€350", "RON 1,500", "1.500 lei / luna".
_PURE_PRICE_RE = re.compile(
    rf"^\s*(?P<pre>{_CUR_TOKEN})?\s*(?P<num>\d[\d.,\s]*?)\s*(?P<post>{_CUR_TOKEN})?"
    rf"\s*(?:[/·]|\bpe\b)?\s*(?:lun[aă]|luna|month|mo)?\s*$", re.IGNORECASE)

# FBM-1b, pasul 2: numarul LIPIT de valuta, in ambele ordini. Pe "2 camere, 350 €/luna"
# da 350, spre deosebire de _parse_price pe toata linia care lipea cifrele in "2,350".
_ADJACENT_PRICE_RE = re.compile(
    rf"(?P<pre_cur>{_CUR_TOKEN})\s*(?P<num_after>\d[\d.,]*)"
    rf"|(?P<num_before>\d[\d.,]*)\s*(?P<post_cur>{_CUR_TOKEN})", re.IGNORECASE)


def _parse_card_lines(lines: list) -> tuple:
    """Imparte liniile unui card Marketplace in (price, currency, title, location).

    Pas 1: prima linie PUR pret da pretul si se CONSUMA (nu mai poate ajunge titlu).
    Pas 2 (fallback, doar daca nu exista linie pur-pret): pretul se citeste din
    substringul lipit de valuta intr-o linie oarecare — e aproape sigur titlul cu
    pretul inclus, deci linia NU se consuma si ramane candidata la titlu.
    Moneda se decide pe pretul gasit, nu pe tot textul cardului.
    """
    price = None
    currency = None
    consumed = None

    for i, line in enumerate(lines):
        m = _PURE_PRICE_RE.match(line)
        if not m or not (m.group("pre") or m.group("post")):
            continue                      # fara valuta explicita nu e pret
        pv = _parse_price(m.group("num"))
        if pv is not None and pv > 0:
            price = pv
            currency = "EUR" if _EUR_CURRENCY_RE.search(line) else "RON"
            consumed = i
            break

    if price is None:
        for line in lines:
            m = _ADJACENT_PRICE_RE.search(line)
            if not m:
                continue
            pv = _parse_price(m.group("num_after") or m.group("num_before"))
            if pv is not None and pv > 0:
                price = pv
                tok = m.group("pre_cur") or m.group("post_cur")
                currency = "EUR" if _EUR_CURRENCY_RE.search(tok) else "RON"
                break

    title = ""
    location = None
    for i, line in enumerate(lines):
        if i == consumed:
            continue
        if not title and not re.match(r"^[\d.,]+$", line):
            title = line
            continue
        if not location:
            location = line
    return price, currency, title, location


def _price_in_bounds(price, filters: dict) -> bool:
    """FBM-1d: post-filtru local pe AMBELE margini de pret.

    minPrice/maxPrice pleaca si server-side, dar nimeni n-a confirmat ca Marketplace
    chiar le aplica pe pagina de categorie — verificam si local. Scannerul trimite
    cheile romanesti (pret_min/pret_max), API-ul mai vechi pe cele engleze: acceptam
    ambele, prima gasita. Margine absenta (sau neparsabila) = nelimitat. `price` e
    deja non-None aici — cardurile fara pret sunt sarite in bucla (FBM-1a).
    """
    filters = filters or {}

    def _bound(*keys):
        for k in keys:
            if filters.get(k):        # 0/""/None = margine nesetata
                try:
                    return float(filters[k])
                except (TypeError, ValueError):
                    return None
        return None

    pmin = _bound("pret_min", "price_min")
    pmax = _bound("pret_max", "price_max")
    if pmin is not None and float(price) < pmin:
        return False
    if pmax is not None and float(price) > pmax:
        return False
    return True


# FBM-1e (F5, echivalentul R3 de la Radar): markerii formularului de login servit
# IN pagina. Facebook raspunde frecvent 200 pe URL-ul ORIGINAL, cu formularul de
# login in corpul paginii si fara redirect — verificarea pe page.url nu-l prinde.
# R3: detectorul s-a mutat in services/radar/facebook_scraper (modulul FB canonic,
# folosit acum de toate cele trei module Facebook). Numele ramane legat aici pentru
# ca modulul chiar il APELEAZA mai jos — nu e un re-export de compatibilitate.
from app.services.radar.facebook_scraper import _looks_like_login_wall   # noqa: E402

# FB-4: nucleul logat-out (FB-1) + registrul de ancore (FB-2). Aliasul `nucleu_search`
# exista ca testele sa poata inlocui O SINGURA tinta pe modulul asta, fara sa atinga
# nucleul. Calea de sesiune de mai jos nu il foloseste deloc.
from app.scrapers.facebook import search as nucleu_search   # noqa: E402
from app.scrapers.facebook.anchors import dupa_slug   # noqa: E402


# FBM-1c: browserul pornea fara nicio masca — user-agent "HeadlessChrome/141.0" si
# navigator.webdriver=true. Scanul ruleaza periodic din scheduler pe storage_state-ul
# contului REAL, deci fiecare rulare anunta "sunt bot" cu sesiunea utilizatorului
# (profil clasic de checkpoint pe cont). Masca e copiata de la facebook_group_scraper,
# care o are deja — tinem cele trei constante la nivel de modul ca sa fie verificabile
# fara browser.
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

_CONTEXT_KWARGS = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1366, "height": 768},
    "locale": "ro-RO",
}

_STEALTH_INIT_JS = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            window.chrome = {runtime: {}};
        """


# ── FB-4: configurarea caii logat-out ────────────────────────────────────────
# Termenii pentru keyword-ul GOL, masurati la FB-4b pe cluj-napoca: uniune 185 din
# 191 intoarse, contributie marginala 19-24 fiecare — practic disjuncti, deci toti
# opt isi merita cererea. Fara diacritice: asa au fost masurati.
_TERMENI_GOL_IMPLICIT = ("chirie", "inchiriez", "de inchiriat", "apartament",
                         "garsoniera", "casa", "camera", "regim hotelier")

# Categoria dominanta a chiriilor pe search, MASURATA la FB-4b (80.7% la termenii
# imobiliari) si cross-confirmata: e acelasi id cu `categoryIDArray` al paginii
# propertyrentals. Zgomotul cert vazut alaturi: 1583634935226685 (canapele).
_CATEGORII_IMPLICITE = ("1468271819871448",)

_ANCORA_IMPLICITA = "bucuresti"


def _guard_categorie(filters: dict) -> bool:
    """GUARD: nu porni scan pe o categorie NECONFIRMATA (ex. propertyforsale/vanzare —
    intoarce doar Partner listings/electronice+chirii, nu vanzari imobiliare reale).
    Vezi re_categories.RE_PROPERTY_TYPES["facebook_real_estate"]["categorie_tip_anunt"].

    Extras din calea de sesiune la FB-4 ca sa fie apelat IDENTIC de ambele cai —
    singura refactorizare facuta codului de sesiune. False = scan omis.
    """
    from app.services.log_manager import log_manager
    tip_anunt = ((filters or {}).get("tip_anunt") or "inchiriere").lower()
    spec = RE_PROPERTY_TYPES["facebook_real_estate"]["categorie_tip_anunt"].get(tip_anunt)
    if not spec or not spec.get("confirmed"):
        log_manager.emit("real_estate", "WARN",
            f"Facebook RE: categoria pentru tip_anunt='{tip_anunt}' e neconfirmata "
            f"(vezi re_categories.RE_PROPERTY_TYPES) — scan omis, 0 rezultate.")
        return False
    return True


def _termeni_gol() -> list:
    """Termenii in care se expandeaza un keyword GOL (FB_IMOBILIARE_TERMENI_GOL, CSV)."""
    brut = os.getenv("FB_IMOBILIARE_TERMENI_GOL") or ""
    alesi = [t.strip() for t in brut.split(",") if t.strip()]
    return alesi or list(_TERMENI_GOL_IMPLICIT)


def _categorii_permise() -> set:
    """Id-urile de categorie pastrate (FB_IMOBILIARE_CATEGORII, CSV)."""
    brut = os.getenv("FB_IMOBILIARE_CATEGORII") or ""
    alese = {c.strip() for c in brut.split(",") if c.strip()}
    return alese or set(_CATEGORII_IMPLICITE)


def _ancora_configurata():
    """Ancora geografica a apelului (FB_IMOBILIARE_ANCORA, slug din registrul FB-2).

    O SINGURA ancora per apel: scanner-ul de azi nu stie de ancore, iar acoperirea pe
    toate cele 51 vine cu planificatorul la FB-6. Slug necunoscut = WARN + Bucuresti,
    nu eroare: un scan ingust e recuperabil, unul care nu porneste nu se vede.
    """
    from app.services.log_manager import log_manager
    slug = (os.getenv("FB_IMOBILIARE_ANCORA") or _ANCORA_IMPLICITA).strip().lower()
    ancora = dupa_slug(slug)
    if ancora is None:
        log_manager.emit("real_estate", "WARN",
            f"Facebook RE: ancora '{slug}' nu exista in registru — folosesc "
            f"'{_ANCORA_IMPLICITA}'.")
        ancora = dupa_slug(_ANCORA_IMPLICITA)
    return ancora


def _search_logout(query: str, filters: dict) -> list:
    """Calea LOGAT-OUT (FB_MOD=logout): search prin nucleul FB-1, fara sesiune.

    Designul (Q), fixat de masuratorile FB-4a/FB-4b: pagina de CATEGORIE nu e
    ancorabila logat-out (doc_id-ul de browse e refuzat cu code 1675004 in acelasi
    minut in care search-ul intoarce 24 de anunturi), deci mergem pe SEARCH. Un
    keyword cu termeni = o cautare; un keyword GOL = expandare in termenii de baza.

    Nu exista parghie de recenta la sursa: `commerce_search_and_rp_ctime_days`
    goleste raspunsul logat-out (0 anunturi la 1 si la 7 zile, masurat). Prospetimea
    vine din scanare repetata + dedup — bazinul e mult mai mare decat cele 24.
    """
    from app.services.log_manager import log_manager
    filters = filters or {}
    if not _guard_categorie(filters):
        return []

    q = (query or "").strip()
    termeni = [q] if q else _termeni_gol()
    ancora = _ancora_configurata()
    categorii = _categorii_permise()

    log_manager.emit("real_estate", "SCAN",
        f"Facebook RE logat-out: {q!r} -> {len(termeni)} termen(i) pe ancora "
        f"'{ancora.slug}'")

    rezultate, vazute = [], set()
    intrate = trecute = fara_categorie = respinse = 0

    for termen in termeni:
        canonice = nucleu_search(termen, ancora.lat, ancora.lon, raza_km=65.0,
                                 city_page_id=ancora.city_page_id) or []
        log_manager.emit("real_estate", "INFO",
            f"Facebook RE nucleu: '{termen}' -> {len(canonice)} anunturi")
        intrate, trecute, fara_categorie, respinse = _adauga_canonice_re(
            canonice, filters, categorii, rezultate, vazute,
            intrate, trecute, fara_categorie, respinse)

    log_manager.emit("real_estate", "OK",
        f"Facebook RE nucleu: {len(rezultate)} rezultate din {intrate} intrate "
        f"({trecute} trecute, {fara_categorie} fara categorie, {respinse} respinse "
        f"de filtrul de categorie)")
    return rezultate


def _adauga_canonice_re(canonice, filters, categorii, rezultate, vazute,
                        intrate, trecute, fara_categorie, respinse):
    """Dicturi CANONICE -> forma Imobiliare, adaugate in `rezultate`.

    Extras din `_search_logout` la FBS-5 si folosit IDENTIC de calea de bazin: o
    singura implementare a formei, deci o singura forma. Intoarce contoarele.
    """
    if True:
        for c in canonice:
            intrate += 1
            cid = c.get("category_id")
            if cid is None:
                # Lipsa campului nu e dovada de zgomot — pastram, dar numaram separat.
                fara_categorie += 1
            elif str(cid) not in categorii:
                respinse += 1
                continue

            ext_id = str(c.get("external_id") or "")
            if not ext_id or ext_id in vazute:
                continue

            # Aceeasi regula ca pe sesiune: fara pret nu putem aplica marginile
            # keyword-ului, iar `_price_in_bounds` presupune `price` non-None.
            price = c.get("price")
            if price is None or price <= 0:
                continue
            if not _price_in_bounds(price, filters):
                continue

            vazute.add(ext_id)
            trecute += 1
            # `listed_at` pleaca STRING ISO: `_seed_from_raw` il trece prin
            # `datetime.fromisoformat`, iar stringul poarta offsetul — asa nu se
            # pierde caracterul UTC-aware al lui `canonic` (capcana notata la FB-1).
            listed = c.get("listed_at")
            rezultate.append({
                "external_id":   ext_id,
                "title":         c.get("title"),
                "price":         price,
                "currency":      c.get("currency"),
                "location":      c.get("location"),
                "url":           c.get("source_url"),
                "source_url":    c.get("source_url"),
                "image_url":     c.get("image_url") or "",
                "listed_at":     listed.isoformat() if listed else None,
                "platform":      "facebook_marketplace",
            })

    return intrate, trecute, fara_categorie, respinse


def _search_bazin(query: str, filters: dict, keyword_id) -> list:
    """Citire din `fb_pool`, ZERO retea. Acelasi formator ca pe calea vie."""
    # Import LOCAL, ca in restul fisierului (vezi `_search_logout`): modulul nu tine
    # `log_manager` la nivel de modul.
    from app.services.log_manager import log_manager
    if not keyword_id:
        log_manager.emit("real_estate", "WARN",
            f"Facebook RE bazin: fara `keyword_id` pentru {query!r} — bazinul e "
            f"cheiat pe el. Apelantul trebuie sa-l paseze (vezi FBS-5).")
        return []
    categorii = _categorii_permise()
    from app.database import SessionLocal
    from app.scrapers.facebook.bazin import citeste
    db = SessionLocal()
    try:
        canonice = citeste(db, "real_estate", keyword_id)
    finally:
        db.close()
    rezultate, vazute = [], set()
    _adauga_canonice_re(canonice, filters, categorii, rezultate, vazute, 0, 0, 0, 0)
    log_manager.emit("real_estate", "SCAN",
        f"Facebook RE bazin {query!r}: {len(rezultate)} din {len(canonice)} in bazin")
    return rezultate


def search_facebook_real_estate(query: str = "", filters: dict = {},
                                session_path: Optional[str] = None,
                                keyword_id: Optional[int] = None) -> list:
    """FB-AUDIT A2: `session_path` vine de la apelant (real_estate_scanner._call_scraper),
    rezolvat PER USER cu resolve_facebook_session_path. Fara descoperire pe disc aici.

    FB-4 (A4): dispecer pe `FB_MOD`. `logout` = nucleul logat-out (fara sesiune,
    fara Playwright); ORICE altceva, inclusiv variabila absenta, = calea de sesiune
    de pana acum, neschimbata. Implicitul ramane `sesiune` DELIBERAT: adaptorul
    logat-out scaneaza deocamdata o singura ancora per apel, deci ar INGUSTA
    geografic feed-ul fata de sesiune; comutarea implicitului se face la FB-6, cand
    planificatorul aduce acoperirea pe toate ancorele. Nu exista fallback automat
    intre cai — comutarea e manuala, prin variabila de mediu.
    """
    from app.services.log_manager import log_manager
    from app.scrapers.facebook.mod import mod_fb
    mod = mod_fb("real_estate")
    if mod == "bazin":
        return _search_bazin(query, filters, keyword_id)
    if mod == "nucleu":
        return _search_logout(query, filters)
    if mod != "sesiune":
        log_manager.emit("real_estate", "WARN",
            f"Facebook RE: FB_MOD='{mod}' necunoscut — folosesc calea de sesiune.")
    return _search_sesiune(query, filters, session_path)


def _search_sesiune(query: str = "", filters: dict = {},
                    session_path: Optional[str] = None) -> list:
    """Calea de sesiune, FB_MOD=sesiune — mutata verbatim din
    search_facebook_real_estate la FB-4."""
    from app.services.log_manager import log_manager
    from app.scrapers.auto.listings.facebook_auto_scraper import _is_session_valid
    filters = filters or {}

    if not _guard_categorie(filters):
        return []

    if not session_path or not _is_session_valid(session_path):
        log_manager.emit("real_estate", "WARN",
            "Facebook RE: sesiune expirata sau inexistenta. "
            "Reautentifica-te din Setari Radar → Facebook.")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("real_estate", "ERR", "Facebook RE: Playwright nu e instalat.")
        return []

    params = {}
    if query:
        params["query"] = query
    # Doar minPrice/maxPrice sunt confirmate (comportament existent). Filtrele de dormitoare/
    # bai/suprafata exista in UI dar au NUMELE param neverificat -> NECONECTATE (re_categories).
    apply_re_filters("facebook_real_estate", filters, params, aliases=RE_FILTER_ALIASES)
    url = _category_url(filters.get("tip_anunt")) + ("?" + urllib.parse.urlencode(params) if params else "")

    log_manager.emit("real_estate", "SCAN", f"Facebook RE Playwright: {query!r}")

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    storage = json.load(f)
                context = browser.new_context(storage_state=storage, **_CONTEXT_KWARGS)
            except Exception:
                context = browser.new_context(**_CONTEXT_KWARGS)
            # Ascunde indicatorii de automatizare (ambele ramuri de context).
            context.add_init_script(_STEALTH_INIT_JS)
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(4000)
                if "login" in page.url.lower():
                    log_manager.emit("real_estate", "WARN",
                        "Facebook RE: login wall — reconecteaza-te.")
                    return []
                for _ in range(2):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(800)

                items = page.query_selector_all('a[href*="/marketplace/item/"]')
                log_manager.emit("real_estate", "INFO",
                    f"Facebook RE: {len(items)} carduri gasite")

                # F5: zero carduri poate insemna "chiar n-are ce afisa" SAU sesiune
                # moarta cu formularul de login servit in pagina, pe 200, fara redirect
                # (deci verificarea pe page.url de mai sus tace). Inainte, al doilea caz
                # raporta "0 rezultate" cu status OK — zile intregi, fara avertisment,
                # iar bannerul din feed se uita doar la varsta fisierului de sesiune.
                # Citim HTML-ul DOAR pe ramura goala — pe calea cu iteme ar fi cost inutil.
                if not items:
                    try:
                        html = page.content()
                    except Exception:
                        html = ""
                    if _looks_like_login_wall(html):
                        log_manager.emit("real_estate", "WARN",
                            "Facebook RE: pagina de login servita fara redirect — sesiune "
                            "posibil invalida. Reconecteaza-te din Setari Radar, "
                            "sectiunea Facebook.")
                        return []

                seen = set()
                for it in items[:40]:
                    try:
                        href = it.get_attribute("href") or ""
                        full = href if href.startswith("http") else f"https://www.facebook.com{href}"
                        full = full.split("?")[0]
                        if "/marketplace/item/" not in full or full in seen:
                            continue
                        seen.add(full)
                        m = re.search(r"/marketplace/item/(\d+)", full)
                        if not m:
                            continue
                        ext_id = m.group(1)

                        text = (it.inner_text() or "").strip()
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        price, currency, title, location = _parse_card_lines(lines)
                        if not title:
                            continue
                        # Fara pret pe card nu putem aplica price_min/max ale keyword-ului
                        # (toleranta din _matches_re_keyword lasa sa treaca orice) —
                        # precedentul Radar/SCRAPE-1a: fara pret => skip. Chiriile au
                        # aproape intotdeauna pretul pe card.
                        if price is None or price <= 0:
                            continue
                        if not _price_in_bounds(price, filters):
                            continue

                        img_el = it.query_selector("img")
                        thumb = (img_el.get_attribute("src") or img_el.get_attribute("data-src")) if img_el else ""

                        results.append({
                            "external_id":   ext_id,
                            "title":         title,
                            "price":         price,
                            "currency":      currency,
                            "location":      location,
                            "url":           full,
                            "source_url":    full,
                            "thumbnail_url": thumb or "",
                            "platform":      "facebook_marketplace",
                        })
                        if len(results) >= 30:
                            break
                    except Exception:
                        continue
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"Facebook RE Playwright eroare: {str(exc)[:100]}")

    log_manager.emit("real_estate", "OK",
        f"Facebook RE: {len(results)} rezultate pentru {query!r}")
    return results
