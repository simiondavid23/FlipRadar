"""DEAL-2 — the deal feed's third source: HTML listing pages of non-Shopify shops.

The Shopify scanner (SHOP-2a) can enumerate a whole catalogue because Shopify
exposes `/products.json`. The other 46 validated domains expose nothing of the
sort, so until now a shop could only be watched one product at a time, by link.
This module closes that gap the only way the web allows: by walking the shop's
own *sale/outlet/discount* listing pages and reading the cards.

Every selector below is DECLARED IN THE REGISTRY, never guessed here, and every
one of them was measured on real dumps in probes LST-1 / LST-1b. The scanner is
therefore generic: adding a shop means adding a `listing` descriptor, not code.

Four facts from those probes shape the design and are not negotiable:

  * The stop condition cannot be the HTTP status ALONE. All four LST-1 pilots
    answer 200 well past their last page. otter and caseking then serve an EMPTY
    grid, noriel CLAMPS back to page 1, and bergfreunde CLAMPS to its last page. A
    scanner that stopped only on "no cards" would loop forever on two of four,
    re-ingesting the same page until `max_pages`. Hence the composite rule in
    `_scaneaza_domeniu`.
  * A fifth shop then showed the OTHER half of that lesson: buzzsneakers (SNK-2)
    serves 200 on all 39 of its pages and 404 on page 40. So the status is not the
    whole answer, but a 404 PAST a page that already succeeded is a real end of
    pagination, and treating it as a failure lost the entire scan. That case is
    handled next to the fetch, and only for 404.
  * The struck price is NOT a 30-day minimum. On otter and bergfreunde it is an
    explicitly-labelled recommended price (PRP/UVP); on caseking and noriel it
    carries no legal label at all. `reference_kind` in the descriptor records
    which, and nothing in this module ever claims "lowest price in 30 days".
  * Card matching must be on a SUBSET of classes. noriel tags every card
    container with the product id (`div.product-item.freegifts-223986`), so
    matching the full class list finds zero cards. CSS selectors do subset
    matching natively, which is exactly why the descriptors are selectors.

Reuses `deal_scanner` by IMPORT, never by copy: the threshold, the settings
lookup, the R1/R2 evaluation and the state row are one implementation shared by
both scanners, so the two sources cannot drift apart in what counts as a deal.
"""
import hashlib
import random
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.models.deal import Deal
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
from app.services.log_manager import set_log_user
# Shared with the Shopify scanner ON PURPOSE — see the module docstring. These are
# imported, not copied, so DEAL-2 cannot drift from SHOP-2a on what a deal is.
from app.services.deal_scanner import (
    _evalueaza, _prag, _pret_strict, _scrie_stare, _settings,
)
from app.services.shop_registry import listing_descriptor, listing_domains

# HTML listing pages are an order of magnitude heavier than `/products.json`
# (1-2.6 MB each in the probes), so the pause between pages is longer than the
# Shopify scanner's 1.5s — while staying under the probes' own politeness.
_PAUZA = 2.5
_JITTER = 1.5
_TIMEOUT = 25

_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Separate from the Shopify scanner's `_SCAN_LOCK`: the two scan DISJOINT domain
# sets and share no mutable state, so a common lock would pointlessly serialise
# the 6h job against the 24h one — the later job would just skip its slot.
_LISTING_LOCK = threading.Lock()

# Anti-avalanche cap, per domain per scan. See `_scaneaza_domeniu`.
_MAX_ALERTE = 10

# DEAL-2b — R1's own threshold on this path, far above the global one.
#
# The struck price in a listing card is a RECOMMENDED price (PRP/UVP) or an
# outlet reference, not an active merchant's `compare_at_price`. On an outlet the
# whole catalogue is permanently "reduced" against it: the first DEAL-2 scan
# produced 15.832 deals, 87% of everything otter.ro shows on /reduceri. At that
# rate R1 carries no information and buries R2 — a real drop below the historic
# minimum — under noise. 40% is a starting point, tunable per user from Settings.
#
# R2 keeps `deal_discount_threshold`: it is the clean signal and is not touched.
# The Shopify scanner also keeps the global threshold — there `compare_at_price`
# IS an active merchant's reference, so SHOP-2's semantics do not change.
DEFAULT_LISTING_R1_THRESHOLD = 40.0


def _prag_r1(settings) -> float:
    """R1 threshold for listings: the user's setting, or the default."""
    valoare = getattr(settings, "listing_r1_threshold", None) if settings else None
    try:
        valoare = float(valoare)
    except (TypeError, ValueError):
        return DEFAULT_LISTING_R1_THRESHOLD
    return valoare if valoare > 0 else DEFAULT_LISTING_R1_THRESHOLD


def is_listing_scan_running() -> bool:
    """True while a listing scan holds the lock. Consulted by the manual endpoint
    so it can answer 409 instead of starting a thread that would exit at once."""
    return _LISTING_LOCK.locked()


def _pauza() -> None:
    time.sleep(_PAUZA + random.uniform(0, _JITTER))


def _pret_eu_comma(brut):
    """float from a EUROPEAN price string: "€ 47,97", "49,99 lei", "1.299,99 lei".

    Strict on purpose, exactly like `_pret_strict`: anything that does not end up
    a clean number returns None and the card is SKIPPED. A listing page that
    changed its markup must lose products loudly, not silently gain invented
    prices.

    The dot is a thousands separator and the comma is the decimal one — that is
    the measured format on both domains that use this parser (bergfreunde
    "€ 79,95" prefix, noriel "49,99\xa0lei" suffix, non-breaking space included).
    """
    if not isinstance(brut, str):
        return None
    # Drop the currency symbol, any words ("lei", "from"), and every kind of space
    # including the non-breaking one that noriel puts between number and currency.
    curat = re.sub(r"[^\d.,]", "", brut.replace("\xa0", " "))
    if not curat:
        return None
    curat = curat.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", curat):
        return None
    try:
        return float(curat)
    except ValueError:
        return None


def _external_id(url: str) -> str:
    """Stable product id for a listing URL: `lst:` + SHA1 of the normalised PATH.

    The path alone, without host, query or fragment: the same product reached as
    `?utm_source=…` or from a filtered listing must be ONE deal, not several. A
    hash rather than the URL because `Deal.external_id` is String(64) and real
    product URLs do not fit — the readable path goes to `handle`.
    """
    cale = urllib.parse.urlsplit(url).path.rstrip("/").lower() or "/"
    return "lst:" + hashlib.sha1(cale.encode("utf-8")).hexdigest()


def _text_of(nod) -> str:
    return re.sub(r"\s+", " ", nod.get_text(" ", strip=True)).strip() if nod else ""


def _link_of(card, descriptor, domain: str):
    """(absolute_url, link_element) or (None, None).

    `@parent_a` is noriel's shape, measured in LST-1: the product anchor WRAPS the
    whole card and carries no class, so it can only be reached by walking up.
    """
    selector = descriptor.get("link")
    if selector == "@parent_a":
        nod = card.find_parent("a", href=True)
    else:
        nod = card.select_one(selector) if selector else None
    if nod is None or not nod.get("href"):
        return None, None
    href = nod["href"].strip()
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return None, None
    return urllib.parse.urljoin(f"https://{domain}/", href), nod


def _titlu_of(card, descriptor, link_nod) -> str:
    if descriptor.get("title_from") == "link_aria_label" and link_nod is not None:
        return (link_nod.get("aria-label") or "").strip()
    selector = descriptor.get("title")
    return _text_of(card.select_one(selector)) if selector else ""


def _pret_of(card, descriptor, cheie_attr: str, cheie_text: str):
    """Paid/struck price for a card, by whichever way the descriptor declares.

    `*_attr` reads a numeric ATTRIBUTE (otter's `data-price-amount="98"`,
    caseking's `content="619.90"`) — dot-decimal, so it goes through the strict
    Shopify parser and never touches the comma logic. `*_text` reads the visible
    text and goes through `_pret_eu_comma`.
    """
    specificatie = descriptor.get(cheie_attr)
    if specificatie:
        selector, atribut = specificatie[0], specificatie[1]
        nod = card.select_one(selector)
        return _pret_strict(nod.get(atribut)) if nod is not None else None
    selector = descriptor.get(cheie_text)
    if selector:
        nod = card.select_one(selector)
        return _pret_eu_comma(_text_of(nod)) if nod is not None else None
    return None


def _in_stoc(card, descriptor) -> bool:
    """False only when the descriptor declares a stock attribute AND it disagrees.

    Mirrors the Shopify scanner's treatment of sold-out variants: an unbuyable
    product is not a bargain, so it is skipped entirely — including from the price
    memory, so the historic minimum is never polluted with unbuyable prices.
    """
    specificatie = descriptor.get("stock_attr")
    if not specificatie:
        return True
    selector, atribut, asteptat = specificatie[0], specificatie[1], specificatie[2]
    nod = card.select_one(selector)
    if nod is None:
        return True                       # nothing declared on this card: assume buyable
    return (nod.get(atribut) or "").strip() == asteptat


# IMG-1b — respinse ca imagine de produs. `no-image`/`noimage`/`no_image` vin de la
# toolnation, unde ld+json poarta `.../placeholder/default/toolnation-no-image-2_3.jpg`
# pe TOATE produsele; `lazyimage` de la intersport, care are acelasi fisier fix in
# `src` pe fiecare card.
_RESPINSE_IMG = ("placeholder", "lazyimage", "blank", "1x1", "loading",
                 "no-image", "noimage", "no_image")

# `Deal.image_url` e `Text`, deci nu exista o lungime de coloana de respectat. Plafonul
# e defensiv, in spiritul trunchierilor vecine (`handle` 255, `title` 500): un URL de
# CDN masurat in sonde nu trece de ~250 de caractere, deci 2048 nu taie nimic real, dar
# opreste o valoare patologica sa umfle randul.
_MAX_IMG = 2048


def normalizeaza_imagine(valoare, domain: str) -> str | None:
    """URL absolut de imagine de produs, sau None. Public: testele il conduc direct.

    Formele masurate de sondele IMG-1a/1a2, pe cele 14 domenii de listari:

      * intersport.ro — `src` e un placeholder FIX pe fiecare card
        (`//…/lazyimage/photogallerynormal.jpg`), iar poza reala sta in `data-src`,
        protocol-relativa, cu query `?lm=<hash>`. De aici si respingerea dupa nume,
        si completarea schemei.
      * buzzsneakers.ro — `data-original-img` e RELATIV la radacina (`/files/thumbs/…`),
        deci are nevoie de gazda ca sa devina utilizabil.
      * caseking.de — `srcset` cu patru candidati separati prin virgula, fiecare
        urmat de descriptorul de latime; se ia primul token.
      * otter.ro / tezyo.ro — primele `<img>` din card sunt INSIGNE
        (`/product_label_image/label_nou_1.png`), nu poza; ele se ocolesc prin
        selectorul `img.product-image-photo` din registru, nu de aici — normalizatorul
        n-are cum sa distinga o insigna valida de o fotografie.
      * caseking.de — un al doilea `<img>` e eticheta energetica `.svg`, respinsa
        prin extensie.
    """
    if not valoare:
        return None
    v = str(valoare).strip()
    if not v:
        return None
    # srcset: „url 150w, url 300w" -> primul URL. Acelasi taietor acopera si forma
    # cu un singur candidat urmat de descriptor („url 2x").
    if "," in v or " " in v:
        v = re.split(r"[,\s]", v, maxsplit=1)[0].strip()
    if not v or v.lower().startswith("data:"):
        return None

    scazut = v.lower()
    cale = urllib.parse.urlsplit(scazut).path or scazut
    if cale.endswith(".svg") or cale.endswith(".gif"):
        return None
    if any(s in scazut for s in _RESPINSE_IMG):
        return None

    if v.startswith("//"):
        v = "https:" + v
    elif v.startswith("/"):
        v = f"https://{domain}{v}"
    elif not v.startswith(("http://", "https://")):
        # Nici absolut, nici ancorat la radacina: un nume de fisier singur nu poate fi
        # rezolvat fara o baza masurata, iar a o ghici ar produce 404-uri tacute.
        return None
    return v[:_MAX_IMG]


def _imagine_of(card, descriptor: dict, domain: str) -> str | None:
    """Prima valoare utilizabila, in ordinea declarata de descriptor.

    Ordinea atributelor CONTEAZA: la intersport `src` exista si e valid ca URL, dar e
    placeholderul; `data-src` trebuie incercat inainte. Registrul o declara per domeniu
    (IMG-1a/1a2), aici nu se ghiceste nimic.

    Fara `<noscript>` si fara `<source>`: sondele n-au gasit niciun domeniu din cele 14
    care sa aiba poza DOAR acolo, deci le-am fi cautat degeaba pe toate cardurile.
    """
    selector = descriptor.get("image") or "img"
    atribute = descriptor.get("image_attr") or ["data-src", "srcset", "src"]
    for nod in card.select(selector):
        for atribut in atribute:
            gasit = normalizeaza_imagine(nod.get(atribut), domain)
            if gasit:
                return gasit
    return None


def extrage_carduri(html: str, descriptor: dict, domain: str) -> list[dict]:
    """Parse one listing page into card dicts. Public: the tests drive it directly
    on fragments cut from the real LST-1 dumps.

    VAL D runda 4a — punctul de plug al familiei „listare-din-stare": daca
    descriptorul declara `state_extractor`, datele NU sunt in DOM si nu exista
    selector CSS de scris, deci parsarea se deleaga extractorului inregistrat, care
    intoarce EXACT aceeasi forma de card. Restul functiei ramane calea CSS,
    neatinsa. Importul e amanat aici fiindca modulul de extractoare are nevoie de
    `_external_id` de mai sus — la nivel de modul ar fi ciclu.
    """
    nume_extractor = descriptor.get("state_extractor")
    if nume_extractor:
        from app.services import listing_state_extractors as _lse
        return _lse.LISTING_STATE_EXTRACTORS[nume_extractor](html, descriptor)

    soup = BeautifulSoup(html or "", "html.parser")
    iesire = []
    for card in soup.select(descriptor["card"]):
        url, link_nod = _link_of(card, descriptor, domain)
        if url is None:
            continue                      # a card with no link is not actionable
        pret = _pret_of(card, descriptor, "price_attr", "price_text")
        if pret is None or pret <= 0:
            continue                      # no valid paid price -> skip, never guess
        if not _in_stoc(card, descriptor):
            continue
        compare_at = _pret_of(card, descriptor, "compare_attr", "compare_text")
        if compare_at is not None and compare_at <= 0:
            compare_at = None
        iesire.append({
            "url": url,
            "external_id": _external_id(url),
            "handle": urllib.parse.urlsplit(url).path[:255],
            "title": _titlu_of(card, descriptor, link_nod)[:500],
            "price": pret,
            "compare_at": compare_at,
            "image_url": _imagine_of(card, descriptor, domain),
        })
    return iesire


def _pagina_url(descriptor: dict, numar: int) -> str:
    """Page 1 uses the MEASURED entry URL, not the template with n=1: the probes
    measured `/reduceri` and `/outlet/`, and there is no evidence that `?p=1` or
    `/outlet/1/` behaves identically."""
    if numar == 1:
        return descriptor["url"]
    return descriptor["page_url_template"].format(n=numar)


def _e_primul_scan(db, domain: str) -> bool:
    """True until a domain has one successful scan behind it.

    Read BEFORE scanning, because `_scrie_stare` stamps "ok" straight after.
    """
    stare = (db.query(ShopScanState)
             .filter(ShopScanState.shop_domain == domain).first())
    return stare is None or stare.last_status != "ok"


def _scaneaza_domeniu(db, domain: str, settings, prag: float) -> dict:
    """Walk one shop's discount listing. Raises only on a failed page fetch — the
    caller records that in ShopScanState so one dead shop cannot stop the rest."""
    from app.services.discord_service import send_deal_notification
    from app.services.scraper_service import _fetch_shop_url_guarded

    descriptor = listing_descriptor(domain)
    if not descriptor:
        raise RuntimeError(f"{domain} nu are descriptor de listare")

    moneda = descriptor.get("currency")
    acum = datetime.now(timezone.utc)

    # Anti-avalanche (design decision, deliberate): on a domain's FIRST successful
    # scan nothing is sent to Discord. R1 is free on this path — every card that
    # shows a struck price qualifies instantly — so a first scan of otter alone
    # would fire hundreds of messages for products that have been on sale for
    # weeks. The first scan establishes the baseline; from the second on, only
    # genuinely NEW deals notify, capped so a shop-wide sale cannot flood either.
    primul_scan = _e_primul_scan(db, domain)

    prag_r1 = _prag_r1(settings)

    vazute: set[str] = set()
    # DEAL-2b — `calificate` != `vazute`: primul e "am citit produsul", al doilea
    # "produsul CHIAR e un deal acum". Inchiderea se face pe al doilea, vezi jos.
    calificate: set[str] = set()
    linkuri_vazute: set[str] = set()
    produse_vazute = 0
    alerte = 0
    pagini = 0
    # D7 — notificarile se strang aici si pleaca DUPA commit-ul paginii, ca un
    # timeout de retea catre Discord sa nu mai prelungeasca tranzactia.
    de_notificat: list[Deal] = []

    for numar in range(1, int(descriptor.get("max_pages") or 1) + 1):
        if numar > 1:
            _pauza()
        url = _pagina_url(descriptor, numar)
        raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS, timeout=_TIMEOUT)

        # VAL D — 404 pe o pagina > 1, cu cel putin o pagina reusita in ACELASI
        # scan, e SFARSIT DE PAGINARE, nu esec. Masurat pe buzzsneakers (SNK-2):
        # cele 39 de pagini raspund 200, iar pagina 40 da 404 — a treia forma de
        # final, dupa „grila goala pe 200" si „pagina repetata" din docstring.
        # Precedentul exista deja in codebase: `olx_scraper.py` are
        # „404 = paginare depasita (pagina nu exista) -> stop curat, nu eroare".
        #
        # Miza nu e cosmetica: RuntimeError cade INAINTE de `db.commit()`, deci un
        # 404 la final pierdea TOT scanul, inclusiv paginile deja citite.
        #
        # Doua granite, amandoua deliberate:
        #   * pe pagina 1 (`pagini == 0`) 404 ramane EROARE — acolo inseamna
        #     listare moarta (URL mutat, categorie stearsa), nu sfarsit;
        #   * DOAR 404. Un 403 sau un 5xx e zid ori defectiune si trebuie sa se
        #     vada ca eroare, nu sa fie confundat cu un final de paginare.
        if (raspuns is not None and raspuns.status_code == 404
                and numar > 1 and pagini > 0):
            break

        if raspuns is None or raspuns.status_code != 200:
            raise RuntimeError(
                f"listare esuata la pagina {numar} "
                f"(status: {getattr(raspuns, 'status_code', None)})")

        carduri = extrage_carduri(raspuns.text, descriptor, domain)
        linkuri_pagina = {c["url"] for c in carduri}

        # --- composite stop condition (measured in LST-1b, see module docstring) ---
        if not linkuri_pagina:
            break                                   # empty grid: otter, caseking
        if linkuri_pagina <= linkuri_vazute:
            break                                   # clamp: noriel (p1), bergfreunde (last)
        linkuri_vazute |= linkuri_pagina
        pagini += 1

        for card in carduri:
            external_id = card["external_id"]
            # SCAN-1 — a product ALREADY handled in this scan is skipped outright.
            # A shop's listing re-sorts between requests, so an item on a page
            # boundary can slide onto the next page and be seen twice. Without this
            # guard the second sighting re-entered the memory block, and because
            # `SessionLocal` runs with `autoflush=False` the row added by the first
            # sighting was still invisible to the query — so a SECOND row was added
            # and the commit died on the unique key. `vazute` already tracks exactly
            # "seen in this scan", so no new bookkeeping is needed.
            #
            # A local set rather than a `flush()` after each add: flushing per
            # product would break the insertmany batching at commit and cost ~13k
            # round-trips on a scan the size of bergfreunde, to buy the same answer.
            #
            # Skipping the whole iteration (not just the memory write) is deliberate:
            # the FIRST sighting already read the old minimum and decided the deal.
            # Re-evaluating on the second one would compare the price against a
            # minimum this same scan has just lowered, inventing a discount.
            if external_id in vazute:
                continue
            produse_vazute += 1
            vazute.add(external_id)

            # --- R2 memory: the OLD minimum is read before being updated ---
            memorie = (db.query(ShopPriceMemory)
                       .filter(ShopPriceMemory.shop_domain == domain,
                               ShopPriceMemory.external_id == external_id)
                       .first())
            if memorie is None:
                min_price_vechi = None               # first sighting: R2 has no history
                db.add(ShopPriceMemory(
                    shop_domain=domain, external_id=external_id,
                    min_price=card["price"], last_price=card["price"],
                    last_seen_at=acum))
            else:
                min_price_vechi = memorie.min_price
                memorie.min_price = min(memorie.min_price, card["price"])
                memorie.last_price = card["price"]
                memorie.last_seen_at = acum

            discount_pct, reason = _evalueaza(
                card["price"], card["compare_at"], min_price_vechi, prag,
                prag_r1=prag_r1)
            if discount_pct is None:
                continue
            calificate.add(external_id)

            deal = (db.query(Deal)
                    .filter(Deal.shop_domain == domain,
                            Deal.external_id == external_id)
                    .first())
            if deal is None:
                deal = Deal(
                    shop_domain=domain, external_id=external_id,
                    handle=card["handle"], title=card["title"], url=card["url"],
                    image_url=card.get("image_url"), currency=moneda, price=card["price"],
                    compare_at_price=card["compare_at"], discount_pct=discount_pct,
                    reason=reason, sizes_available=[],
                    min_price_seen=min_price_vechi, state="nou",
                    deal_source="listing_scan",
                    first_seen_at=acum, last_seen_at=acum)
                db.add(deal)
                db.flush()
                if not primul_scan:
                    de_notificat.append(deal)
            else:
                # D7: the state belongs to the USER, so it stays untouched —
                # `ignorat` stays `ignorat`. No alert on reappearance.
                deal.title = card["title"]
                # IMG-1b — `or deal.image_url`: un scan in care extractia da None
                # (tema schimbata, card fara poza in acea zi) nu STERGE o poza deja
                # avuta. Pierderea ar fi vizibila imediat in feed, iar recuperarea ar
                # cere un scan reusit ulterior.
                deal.image_url = card.get("image_url") or deal.image_url
                deal.url = card["url"]
                deal.handle = card["handle"]
                deal.price = card["price"]
                deal.compare_at_price = card["compare_at"]
                deal.discount_pct = discount_pct
                deal.reason = reason
                deal.min_price_seen = min_price_vechi
                deal.last_seen_at = acum
                deal.ended_at = None

        # D6 — commit dupa FIECARE pagina, nu o data la finalul domeniului.
        # Motivul e lock-ul de scriere SQLite: cu un singur commit la final,
        # tranzactia traversa si `_pauza()`-ul si fetch-ul HTTP al paginii
        # urmatoare, deci pe un domeniu mare lock-ul de scriere se tinea zeci de
        # secunde. busy_timeout-ul celorlalti scriitori (30s) expira si cadeau in
        # lant cu "database is locked". Comitand per pagina, lock-ul se tine sub
        # o secunda intre doua pauze, deci restul aplicatiei apuca sa scrie.
        #
        # Pozitia e la SFARSITUL corpului buclei, deci dupa procesarea cardurilor
        # paginii curente si inainte de fetch-ul urmatoarei. Toate cele trei
        # iesiri timpurii (404 = paginare depasita, grila goala, pagina repetata)
        # cad INAINTE de bucla pe carduri, deci cand una se declanseaza ultima
        # pagina procesata cu succes a fost deja comisa la iteratia ei.
        #
        # Consecinta asumata: `db.rollback()`-ul din apelant anuleaza acum doar
        # pagina curenta, nu tot domeniul — paginile deja comise raman. E
        # acceptabil: blocul de inchidere pe `calificate` ruleaza doar la final,
        # deci un domeniu picat la jumatate nu inchide nimic gresit, iar scanul
        # urmator recalculeaza si corecteaza.
        db.commit()
        # Notificarea pleaca DOAR pentru randuri deja comise: altfel am putea
        # anunta un deal pe care un rollback ulterior l-ar face sa nu fi existat.
        # Plafonul se verifica aici, nu la append, ca sa ramana global pe domeniu.
        for deal in de_notificat:
            if alerte < _MAX_ALERTE and send_deal_notification(deal, settings):
                alerte += 1
        de_notificat.clear()

    # --- deals that no longer QUALIFY are ENDED, not deleted ---
    # DEAL-2b: the criterion used to be `not in vazute`, so only VANISHED products
    # were closed. A product still on the page but no longer over the threshold
    # (price went up, or the threshold was raised from Settings) hit `continue`
    # above and its row stayed "active" with stale numbers forever. On
    # `calificate`, the first scan after a threshold change cleans up after
    # itself — no manual SQL, no data migration.
    #
    # Filtered on deal_source too: refresh_diff deals can sit on the SAME domain
    # (a user tracking an otter.ro product by link), and this scan says nothing
    # about whether those are still live.
    active = (db.query(Deal)
              .filter(Deal.shop_domain == domain,
                      Deal.ended_at.is_(None),
                      Deal.deal_source == "listing_scan")
              .all())
    for deal in active:
        if deal.external_id not in calificate:
            deal.ended_at = acum

    ramase = sum(1 for d in active if d.external_id in calificate)
    db.commit()
    return {"produse": produse_vazute, "deals_active": ramase,
            "alerte": alerte, "pagini": pagini}


def run_listing_scan(db) -> dict:
    """Job entry point (APScheduler, every 24h). Returns a summary for logging."""
    # MON-4 — defensive reset: jobs run on pool threads, and a user_id left over
    # from an earlier run would mislabel the logs.
    set_log_user(None)

    # Non-blocking DELIBERATELY, as in the Shopify scanner: a scan that queued up
    # would start right after the current one and redo the same work.
    if not _LISTING_LOCK.acquire(blocking=False):
        print("[ListingScan] scanare deja in curs — cererea a fost ignorata")
        return {"skipped": "scan deja in curs", "magazine": 0}

    try:
        settings = _settings(db)
        if settings is not None and not getattr(settings, "deal_scan_enabled", True):
            return {"skipped": "deal_scan_enabled=False", "magazine": 0}

        dezactivate = set(getattr(settings, "deal_shops_disabled", None) or []) if settings else set()
        domenii = sorted(listing_domains() - dezactivate)
        prag = _prag(settings)

        rezumat = {"magazine": 0, "produse": 0, "alerte": 0, "erori": 0}
        for domain in domenii:
            try:
                rezultat = _scaneaza_domeniu(db, domain, settings, prag)
            except Exception as exc:                # noqa: BLE001
                # A dead shop (changed markup, block, network) does NOT stop the
                # rest: its state shows up in the health panel, the others carry on.
                db.rollback()
                _scrie_stare(db, domain, "error", eroare=f"{type(exc).__name__}: {exc}"[:500])
                rezumat["erori"] += 1
                print(f"[ListingScan] {domain}: eroare — {type(exc).__name__}: {exc}")
                continue
            _scrie_stare(db, domain, "ok", produse=rezultat["produse"],
                         deals_active=rezultat["deals_active"])
            rezumat["magazine"] += 1
            rezumat["produse"] += rezultat["produse"]
            rezumat["alerte"] += rezultat["alerte"]
            print(f"[ListingScan] {domain}: {rezultat['pagini']} pagini, "
                  f"{rezultat['produse']} produse, {rezultat['deals_active']} deal-uri "
                  f"active, {rezultat['alerte']} alerte")
        return rezumat
    finally:
        _LISTING_LOCK.release()
