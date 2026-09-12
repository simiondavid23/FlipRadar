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

DEAL-D1 added a SECOND text parser. Until then every `price_text` descriptor went
through `_pret_eu_comma`, which deletes the dot as a thousands separator — right
for "1.393,94 lei", fatal for direct-running's "$117.63", which came out 11763.0
when LST-D1 ran the proposed descriptor through this very module (report §2.8).
The card carries no numeric attribute either, so the strict attribute path was
not an option. Hence `_pret_us_dot` and, with it, `price_parse` finally being
READ instead of merely documented — see `_pret_of`.

EMAG-D added `entries`: a descriptor may declare a LIST of listings instead of a
single one. Some shops have no aggregated discount URL worth walking — eMAG
Resigilate splits its 7996 resealed products across twelve department pages, each
paginated in the PATH (`/resigilate/<cat>/p{n}/d`). Before this, such a shop could
only enter the axis by picking one category and losing the rest.

What is per ENTRY and what is per SCAN is the whole of the design, and both halves
were chosen against a concrete failure:

  * per ENTRY — `linkuri_vazute` and the page counter. "Clamp" means *this list
    served me the previous page again*; two categories legitimately sharing a
    product are not a clamp, and treating them as one would cut every category
    after the first short. The page counter likewise: a 404 on page 1 of the
    second category must stay an ERROR (the hub changed), which a global counter
    would have swallowed as "end of pagination".
  * per SCAN — `vazute` and `calificate`. SCAN-1's duplicate guard exists because
    a product can be met twice; on eMAG that happens BETWEEN categories too, and
    a per-entry reset would re-enter the memory block and die on the unique key.
    `calificate` closes stale deals only after ALL entries, or the first category
    would close the second one's deals.

Reuses `deal_scanner` by IMPORT, never by copy: the threshold, the settings
lookup, the R1/R2 evaluation and the state row are one implementation shared by
both scanners, so the two sources cannot drift apart in what counts as a deal.
"""
import hashlib
import logging
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
    _evalueaza, _prag, _pret_strict, _scrie_stare, _settings, preincarca_pagina,
)
from app.services.browser_fetch import (
    BrowserFetchBlocked,
    BrowserFetchTooSoon,
    BrowserFetchUnavailable,
    fetch_browser_html,
)
from app.services.shop_registry import (deal_channel, listing_descriptor,
                                         listing_domains)
from app.utils.listing_dates import acum_local

# STATE-1 — un logger de modul, doar pentru sfarsitul de intrare pe non-200. Restul
# modulului scrie in continuare cu `print("[ListingScan] …")`; nu se converteste
# nimic aici, fiindca ce trebuia sa se schimbe e o singura linie, iar un `print`
# n-ar putea fi verificat de un test (`caplog` vede doar `logging`).
logger = logging.getLogger(__name__)

# HTML listing pages are an order of magnitude heavier than `/products.json`
# (1-2.6 MB each in the probes), so the pause between pages is longer than the
# Shopify scanner's 1.5s — while staying under the probes' own politeness.
_PAUZA = 2.5
_JITTER = 1.5

# GUARD-1 — asteptarea SUPLIMENTARA dinaintea singurului retry de pe pagina 1, peste
# `_pauza()`. Zece secunde fiindca `None`-ul pe care-l tratam nu e o eroare de
# sintaxa a cererii, ci una de moment (poarta, retea, poate un cookie de edge care
# se aseaza) — o repetare imediata ar cadea pe aceeasi stare.
_PAUZA_RETRY_S = 10
_TIMEOUT = 25

# BRW-1 — plafonul asteptarii de politete de pe calea de browser, si valoarea de
# rezerva cand mesajul lui `BrowserFetchTooSoon` nu se poate citi. 240 s fiindca
# cel mai mare interval configurat azi e 180 s (sephora), iar un domeniu care ar
# cere mai mult n-ar avea ce cauta intr-un scan de listare: BRW-0b a masurat 180 s
# de asteptare pentru O pagina, adica ~15 minute pentru cinci.
_BROWSER_ASTEPTARE_MAX_S = 240
_BROWSER_ASTEPTARE_IMPLICITA_S = 30

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


def _pret_us_dot(brut):
    """float from an AMERICAN price string: "$117.63", "$1,299.00", "170.00".

    The mirror image of `_pret_eu_comma`, and exactly as strict: the comma is the
    thousands separator and gets deleted, the dot is the decimal one and stays.
    Anything that does not end up a clean number returns None and the card is
    SKIPPED — a listing that changed its markup must lose products loudly, not
    silently gain invented prices.

    Measured on direct-running.com (LST-D1 §2.1): 24/24 cards priced with the
    symbol BEFORE the amount and a dot decimal. Running them through the European
    parser produced 11763.0 instead of 117.63 — a 100x error that looks perfectly
    plausible in a feed, which is why the two parsers are separate functions
    chosen by the descriptor and not one function guessing from the string.
    """
    if not isinstance(brut, str):
        return None
    # Same cleanup as the European parser, non-breaking space included.
    curat = re.sub(r"[^\d.,]", "", brut.replace("\xa0", " "))
    if not curat:
        return None
    curat = curat.replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", curat):
        return None
    try:
        return float(curat)
    except ValueError:
        return None


def _pret_eu_sup(brut):
    """float from a European price whose DECIMALS live in a `<sup>` with NO
    separator between them and the integer part: "529 99 lei", "NOU: 1.474 99 lei".

    evomag renders `<span class="real_price">529<sup class="price_sup">99</sup>
    lei</span>`. `_text_of` is `get_text(" ")`-based, so the sup becomes a separate
    word and the string reaching a parser is "529 99 lei". Both parsers that
    existed before this stripped every non-digit and read 52999.0 — a 100x error,
    on 64/64 cards, measured by the LST-D2 control (§4). It is the direct-running
    failure of DEAL-D1 with a different cause, which is why the answer is again a
    NAMED parser the registry chooses, never a heuristic guessing from the string:
    "529 99" and "52999" are indistinguishable once the space is gone.

    A comma anywhere means the shop is rendering the normal European form on this
    card, so the string goes to `_pret_eu_comma` verbatim. That delegation is what
    keeps a domain from breaking the day it stops splitting the decimals — the
    descriptor does not have to be edited in the same deploy.

    As strict as its two siblings: anything that is not exactly `<integer>` or
    `<integer> <two digits>` returns None and the card is SKIPPED. "529 9" (one
    decimal digit) and "52 99 99" (two groups) are both None, deliberately — a
    listing that changed its markup must lose products loudly, not silently gain
    invented prices.
    """
    if not isinstance(brut, str):
        return None
    # Same cleanup as the other two, except the SPACE survives: here it is the
    # separator that carries the meaning, not noise to delete.
    curat = re.sub(r"[^\d.,\s]", "", brut.replace("\xa0", " "))
    curat = re.sub(r"\s+", " ", curat).strip()
    if not curat:
        return None
    if "," in curat:
        return _pret_eu_comma(curat)
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+|\d+)(?: (\d{2}))?", curat)
    if not m:
        return None
    intreg = m.group(1).replace(".", "")
    try:
        return float(f"{intreg}.{m.group(2)}" if m.group(2) else intreg)
    except ValueError:
        return None


# The text parsers a descriptor may name, by the value of its `price_parse`.
# Absent is the same as "eu_comma": the ten CSS descriptors that predate DEAL-D1
# all declare it, but the mapping stays tolerant so the key's meaning is
# "which parser", not "a field you must remember to add".
_PARSERE_TEXT = {
    "eu_comma": _pret_eu_comma,
    "us_dot": _pret_us_dot,
    "eu_sup": _pret_eu_sup,
}


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


# DEAL-D3 — spatiile din INTERIORUL unui `href` se codifica.
#
# brickdepot randeaza ancora cardului cu un spatiu literal dupa slash:
#   href="https://brickdepot.ro/lego-super-mario-c-120/ mario-kart-luigi-si-mach-8-p-30375.html"
# Fara gardul asta, URL-ul iese cu spatiul in el si ajunge asa in `deals.url` si in
# orice fetch de refresh de pe axa L — un URL cu spatiu brut nu e un URL.
#
# MASURAT, si e important: caracterul din dump NU e `U+0020`, ci `U+00A0` (spatiu
# neseparator). De aia clasa de mai jos il contine explicit — o garda scrisa doar
# pentru ` `, `\t`, `\n` ar fi lasat neatins exact cazul care a cerut-o.
#
# Toate variantele se codifica `%20`, inclusiv U+00A0. Strict vorbind, forma UTF-8
# a lui U+00A0 ar fi `%C2%A0`; alegerea lui `%20` e deliberata (un spatiu
# neseparator intr-un slug e o greseala de redactare, nu o intentie), dar RAMANE
# NEVERIFICATA LIVE — runda DEAL-D3 n-a facut nicio cerere. Daca un refresh pe
# brickdepot da 404, aici se uita.
#
# Doar spatii. Diacriticele necodificate raman cum sunt, fiindca asa le accepta
# deja `extract_product` pe axa L.
_SPATII_IN_HREF = re.compile(r"[ \t\n\r\f\v ]")


def _fara_spatii(href: str) -> str:
    return _SPATII_IN_HREF.sub("%20", href)


def _link_of(card, descriptor, domain: str):
    """(absolute_url, link_element) or (None, None).

    `@parent_a` is noriel's shape, measured in LST-1: the product anchor WRAPS the
    whole card and carries no class, so it can only be reached by walking up.

    DEAL-D10a — `@self` e simetricul lui: cardul E chiar ancora. Forma masurata la
    LST-D9 pe foto-erhardt: cele 48 de `a.products__product` sunt copii DIRECTI ai
    containerului `div.products`, cu ZERO ancore interioare. Nici `select_one`
    (care cauta doar descendenti) nici `@parent_a` (care urca la container, nu la
    o ancora) nu-l pot atinge — de aceea e nevoie de un al treilea mod, nu de un
    selector mai destept.

    Ce se intampla cand `@self` e cerut pe un card care NU e ancora: cardul se
    SARE, ca la orice link lipsa. Alternativa — sa cadem inapoi pe `select_one` —
    ar face un descriptor gresit sa mearga pe jumatate din pagini si sa taca pe
    restul, adica exact felul de descriptor care pare ca merge.
    """
    selector = descriptor.get("link")
    if selector == "@self":
        nod = card if (card.name == "a" and card.get("href")) else None
    elif selector == "@parent_a":
        nod = card.find_parent("a", href=True)
    else:
        nod = card.select_one(selector) if selector else None
    if nod is None or not nod.get("href"):
        return None, None
    href = nod["href"].strip()
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return None, None
    return urllib.parse.urljoin(f"https://{domain}/", _fara_spatii(href)), nod


def _titlu_of(card, descriptor, link_nod) -> str:
    if descriptor.get("title_from") == "link_aria_label" and link_nod is not None:
        return (link_nod.get("aria-label") or "").strip()
    # DEAL-D4 — officeshoes: ancora produsului n-are TEXT (doar un `<img>`), iar
    # numele complet sta in atributul `title` al ei:
    # `<a class="send-search" title="Calvin Klein Pantofi sport Kobe M 1C">`.
    # `h2.product_list_title` exista, dar da doar modelul („Kobe M 1C"), fara marca.
    # Lipsa atributului cade pe `title`, ca un deploy care-l scoate sa piarda marca,
    # nu produsul.
    if descriptor.get("title_from") == "link_title" and link_nod is not None:
        din_atribut = (link_nod.get("title") or "").strip()
        if din_atribut:
            return din_atribut
    selector = descriptor.get("title")
    return _text_of(card.select_one(selector)) if selector else ""


def _pret_of(card, descriptor, cheie_attr: str, cheie_text: str, domain: str = ""):
    """Paid/struck price for a card, by whichever way the descriptor declares.

    `*_attr` reads a numeric ATTRIBUTE (otter's `data-price-amount="98"`,
    caseking's `content="619.90"`) — dot-decimal, so it goes through the strict
    Shopify parser and never touches the comma logic. That path is untouched.

    `*_text` reads the visible text, and DEAL-D1 made the parser a choice instead
    of a constant: `price_parse` names it — `eu_comma` (or absent, for the ten
    descriptors written before this) for "1.393,94 lei", `us_dot` for
    direct-running's "$117.63", `eu_sup` (DEAL-D2) for evomag's "529 99 lei",
    where the decimals come out of a `<sup>` with no separator. None of the three
    can be told apart from the string alone: "1.299,00" and "1,299.00" are both
    valid and mean the same amount, "117.63" means 117.63 to one parser and
    11763.0 to another, and "529 99" is 529.99 or 52999 depending only on how the
    shop renders it. Only the shop knows, so only the registry may say.

    An unknown value raises instead of falling back. A silent default would let a
    typo in the registry price every card through the wrong parser and publish a
    feed of 100x-wrong deals that look entirely plausible; raising kills the scan
    of that one domain at its first card, which the caller already records in
    `ShopScanState` without stopping the other shops.
    """
    specificatie = descriptor.get(cheie_attr)
    if specificatie:
        selector, atribut = specificatie[0], specificatie[1]
        nod = card.select_one(selector)
        return _pret_strict(nod.get(atribut)) if nod is not None else None
    selector = descriptor.get(cheie_text)
    if selector:
        # DEAL-D2 — `compare_parse`, citit DOAR pe latura de referinta.
        #
        # `price_parse` a fost pana aici o cheie unica pe descriptor, si a mers
        # fiindca nimeni nu amestecase caile: cele trei descriptoare cu
        # `price_attr` (caseking, otter, tezyo) isi iau si referinta din atribut,
        # iar zooplus n-are referinta deloc. itgalaxy.ro e primul care citeste
        # pretul din ATRIBUT (`data-pprice="2815.99"`, parser strict impus de
        # calea de cod) si referinta din TEXT („PRP: 525,00 lei") — doua parsere
        # diferite, un singur camp. Fara cheia asta, `attr_float` ajungea in
        # `_PARSERE_TEXT` si ridica ValueError la primul card.
        #
        # Optionala si fara efect pe cele 19 descriptoare de dinainte: absenta,
        # se cade inapoi pe `price_parse`, adica exact linia dinainte.
        nume = (descriptor.get("compare_parse")
                if cheie_text == "compare_text" else None)
        nume = nume or descriptor.get("price_parse") or "eu_comma"
        parser = _PARSERE_TEXT.get(nume)
        if parser is None:
            raise ValueError(
                f"{domain or '<domeniu necunoscut>'}: `price_parse` necunoscut "
                f"{nume!r} — valorile admise pe text sunt "
                f"{sorted(_PARSERE_TEXT)}")
        nod = card.select_one(selector)
        return parser(_text_of(nod)) if nod is not None else None
    return None


def _referinta_din_economie(card, descriptor, pret: float, domain: str):
    """Referinta RECONSTRUITA din economia afisata: `pret + economie`.

    DEAL-D10a, din LST-D9 §3.1. foto-erhardt e primul magazin al axei care nu-si
    arata deloc reducerea ca pret taiat — masurat pe PATRU pagini ale lui (cele
    doua de la LST-D5 plus `/dealzone.html` si `/offers.html`): zero `<del>`, zero
    `<s>`, zero `line-through`, zero `UVP`, zero `statt`, zero `-N%`. Reducerea e
    scrisa ca ECONOMIE, si e acolo pe 48/48 de carduri:

        <small class="products__ribbon">Save 50,00€ NOW!</small>
        <span  class="products__price products__price--standard">699,00 €</span>
        <small class="products__price products__price--saved"> 50,00 € saved</small>

    699,00 + 50,00 = 749,00. Parserul e ACELASI ca al pretului (`price_parse`),
    fiindca e acelasi magazin care scrie ambele numere: `eu_comma` curata singur
    si „saved", si „€", si spatiul neintrerupt.

    SEMANTICA, si de ce `reference_kind` NU primeste o valoare noua: 749,00 nu e
    un pret pe care magazinul l-a DECLARAT vreodata, ci unul pe care il calculam
    noi din doua numere pe care le-a declarat. E o reconstructie aritmetic
    corecta, dar nu o referinta legala — nici PRP, nici minim de 30 de zile. Deci
    ramane `nemarcat`, exact ca un pret taiat fara eticheta: acelasi grad de
    incredere, aceeasi tratare in aval.

    Fail-safe pe None in loc de ghicit: daca lipseste nodul, daca textul nu se
    parseaza, sau daca economia e <= 0, nu se intoarce nimic. O economie de zero
    inseamna „produsul nu e redus acum", nu „referinta e egala cu pretul" — a doua
    citire ar publica un deal de 0%.
    """
    selector = descriptor.get("compare_saving_text")
    if not selector:
        return None
    nod = card.select_one(selector)
    if nod is None:
        return None
    nume = descriptor.get("price_parse") or "eu_comma"
    parser = _PARSERE_TEXT.get(nume)
    if parser is None:
        raise ValueError(
            f"{domain or '<domeniu necunoscut>'}: `price_parse` necunoscut "
            f"{nume!r} pe `compare_saving_text` — valorile admise sunt "
            f"{sorted(_PARSERE_TEXT)}")
    economie = parser(_text_of(nod))
    if economie is None or economie <= 0:
        return None
    return round(pret + economie, 2)


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


# IMG-1b — respinse ca imagine de produs. `no-image` vine de la toolnation, unde
# ld+json poarta `.../placeholder/default/toolnation-no-image-2_3.jpg` pe TOATE
# produsele; `lazyimage` de la intersport, care are acelasi fisier fix in `src` pe
# fiecare card.
#
# IMG-1b2 — potrivire pe TOKEN, nu ca subsir, si numai in CALEA URL-ului. Ca subsir,
# `blank` respingea `sleeping-blanket-blue.jpg` si `loading` respingea
# `unloading-dock.jpg` — poze de produs perfect valide, aruncate tacut. Delimitatorii
# sunt exact separatorii care apar in numele de fisiere de pe CDN-uri (`/`, `_`, `-`,
# `.`) plus capetele de sir. Query-string-ul e in afara potrivirii: acolo stau
# parametri de redimensionare si cache-busting (intersport are `?lm=<hash>`), care nu
# spun nimic despre ce ARATA poza.
_RESPINSE_IMG_RE = re.compile(
    r"(?:^|[/_\-.])(?:placeholder|lazyimage|blank|1x1|loading|no[-_]?image)(?:$|[/_\-.])")

# `Deal.image_url` e `Text`, deci nu exista o lungime de coloana de respectat. Plafonul
# e defensiv, in spiritul trunchierilor vecine (`handle` 255, `title` 500): un URL de
# CDN masurat in sonde nu trece de ~250 de caractere, deci 2048 nu taie nimic real, dar
# opreste o valoare patologica sa umfle randul.
_MAX_IMG = 2048


# IMG-2 — forma unui `srcset` REAL: unul sau mai multi candidati, fiecare urmat de
# un descriptor de latime (`400w`) sau de densitate (`2x`), separati prin virgula.
# Ancorat la ambele capete: o valoare care contine un srcset dar are si altceva
# in jur nu e un srcset, iar un URL cu virgule in cale nu se potriveste deloc.
_SRCSET_CU_DESCRIPTORI = re.compile(
    r"^\S+\s+\d+(?:\.\d+)?[wx](?:\s*,\s*\S+\s+\d+(?:\.\d+)?[wx])*\s*$")


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

    IMG-2 — a saptea forma, si prima care a cerut o REGULA, nu o exceptie:
    endclothing.com serveste pozele printr-un CDN de tip Cloudinary, unde
    transformarile stau intr-un segment de CALE cu virgule:

        https://media.endclothing.com/media/f_auto,q_auto:eco,w_400,h_400
               /prodmedia/media/catalog/product/B/R/BR_SS26-100-OAT_1_1.jpg

    Taietorul de mai jos vedea virgulele si oprea la prima, adica exact la
    `.../media/f_auto` — un URL sintactic valid, care da 404 (masurat la DEAL-D7,
    alaturi de forma intreaga, care da 200 `image/jpeg`). Si e cel mai rau fel de
    esec: feed-ul are un placeholder pentru imaginea LIPSA, dar n-are cum sa se
    apere de una care pare sa existe.

    Regula corecta vine din chiar definitia lui `srcset`: candidatii sunt separati
    prin virgula, dar fiecare poarta un DESCRIPTOR — `<url> 400w` sau `<url> 2x`.
    O virgula fara descriptor dupa ea nu separa nimic, e parte din cale. De aceea
    taierea se face doar cand valoarea CHIAR arata a srcset; altfel URL-ul trece
    intreg, cu virgule cu tot.
    """
    if not valoare:
        return None
    v = str(valoare).strip()
    if not v:
        return None
    # IMG-2 — trei cazuri, in ordinea asta:
    #
    #   1. SRCSET CU DESCRIPTORI („url 150w, url 300w", „url 2x") -> primul
    #      candidat. Descriptorul e ce dovedeste ca virgula separa: fara el,
    #      valoarea poate fi la fel de bine un URL cu virgule in cale.
    #   2. valoare cu SPATII dar fara descriptori („url1, url2", „url1 url2") ->
    #      primul token, ca inainte. Forma nu s-a masurat pe niciun magazin, dar
    #      taierea veche o acoperea, si o pastram ca sa nu schimbam decat ce
    #      trebuie.
    #   3. orice altceva, INCLUSIV o valoare cu virgule si fara spatii -> intreaga.
    #      Aici intra Cloudinary-ul de la endclothing.
    if _SRCSET_CU_DESCRIPTORI.match(v):
        v = v.split(None, 1)[0].strip()
    elif " " in v or "\t" in v:
        v = re.split(r"[,\s]", v, maxsplit=1)[0].strip()
    if not v or v.lower().startswith("data:"):
        return None

    scazut = v.lower()
    cale = urllib.parse.urlsplit(scazut).path or scazut
    if cale.endswith(".svg") or cale.endswith(".gif"):
        return None
    if _RESPINSE_IMG_RE.search(cale):
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
        pret = _pret_of(card, descriptor, "price_attr", "price_text", domain)
        if pret is None or pret <= 0:
            continue                      # no valid paid price -> skip, never guess
        if not _in_stoc(card, descriptor):
            continue
        compare_at = _pret_of(card, descriptor, "compare_attr", "compare_text",
                              domain)
        if compare_at is None:
            compare_at = _referinta_din_economie(card, descriptor, pret, domain)
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


def _intrari(descriptor: dict) -> list[dict]:
    """The list of listing ENTRIES a descriptor declares, normalised to one shape.

    EMAG-D — a descriptor may declare either a single `url` (+ its template) or a
    list of `entries`, never both. The two forms differ only in how many listings
    the shop needs walking; everything downstream (selectors, currency,
    reference_kind) is per DOMAIN and stays at the top level. Normalising here
    means `_scaneaza_domeniu` has one loop shape and the eighteen descriptors that
    predate this key keep working untouched — the `url` form simply yields a
    one-element list.

    `max_pages` resolves per entry: its own value if it has one, else the
    descriptor's. eMAG needs that fallback because the hub publishes ONE total
    (7996 products) and no per-category count, so a per-entry cap could only be
    invented.

    DISC-1 — `channel` se plimba mai departe (None pe forma `url`, fiindca acolo
    canalul e al DOMENIULUI si sta in registru, nu in descriptor). Normalizarea
    reconstruieste dictul cheie cu cheie, deci o cheie necarata s-ar pierde tacut
    intre registru si scanner — iar simptomul ar fi cel mai prost cu putinta:
    rutare corecta pe 98 de magazine si gresita doar pe eMAG.
    """
    brute = descriptor.get("entries")
    if not brute:
        return [{"url": descriptor["url"],
                 "page_url_template": descriptor.get("page_url_template"),
                 "max_pages": int(descriptor.get("max_pages") or 1),
                 "channel": None}]
    return [{"url": intrare["url"],
             "page_url_template": intrare.get("page_url_template"),
             "max_pages": int(intrare.get("max_pages")
                              or descriptor.get("max_pages") or 1),
             "channel": intrare.get("channel")}
            for intrare in brute]


def _pagina_url(intrare: dict, numar: int) -> str:
    """Page 1 uses the MEASURED entry URL, not the template with n=1: the probes
    measured `/reduceri` and `/outlet/`, and there is no evidence that `?p=1` or
    `/outlet/1/` behaves identically.

    Takes an ENTRY, not the descriptor (EMAG-D). The two are shaped alike on the
    keys this reads, so a `url`-form descriptor still works verbatim — which is
    why the eighteen existing tests that pass one kept passing.
    """
    if numar == 1:
        return intrare["url"]
    return intrare["page_url_template"].format(n=numar)


def _validator_grila(descriptor: dict, domain: str):
    """Callback-ul de continut al caii de browser: pagina e gata cand chiar are o
    GRILA, nu cand corpul e nevid.

    `fetch_browser_html` cu `valideaza=None` accepta primul corp nevid — si asta
    nu e o subtilitate teoretica: la BRW-0c sonda a cerut asa un `home` de pe
    vexio.ro si a primit interstitiul Cloudflare (6.105 octeti, zero ancore,
    `<title>Just a moment...</title>`) drept continut, in 1,29 s, fara ca
    `_detecteaza_blocare` sa fie macar chemat. Callback-ul de continut e chiar ce
    face zidul detectabil.

    Criteriul e `extrage_carduri` INSUSI, nu o euristica paralela: ce nu se poate
    parsa cu descriptorul domeniului nu e pagina cautata, oricat de mare ar fi
    corpul. Un al doilea criteriu ar putea diverge de primul si atunci scannerul
    ar accepta pagini din care apoi citeste zero produse.
    """
    def valideaza(html):
        carduri = extrage_carduri(html, descriptor, domain)
        if not carduri:
            raise ValueError(f"{domain}: inca zero carduri in HTML-ul randat")
        return carduri
    return valideaza


def _secunde_de_asteptat(mesaj: str) -> float:
    """Cat mai e de asteptat, citit din mesajul lui `BrowserFetchTooSoon`.

    Forma mesajului e a lui `browser_fetch`: „<domeniu>: <trecut>s de la ultima
    vizita, minimul e <interval>s". Se scade, nu se ia intervalul intreg: la
    BRW-0b sephora avea 180 s de interval, trecusera 23, iar asteptarea corecta a
    fost de 157 s. Fara scadere s-ar fi dormit 180 degeaba.
    """
    minim = re.search(r"minimul e (\d+(?:\.\d+)?)s", mesaj or "")
    trecut = re.search(r"(\d+(?:\.\d+)?)s de la ultima", mesaj or "")
    if not minim:
        return _BROWSER_ASTEPTARE_IMPLICITA_S
    ramas = float(minim.group(1)) - (float(trecut.group(1)) if trecut else 0.0)
    return max(1.0, min(ramas, _BROWSER_ASTEPTARE_MAX_S))


def _pagina_prin_browser(url: str, domain: str, descriptor: dict,
                         numar: int, pagini_intrare: int) -> str | None:
    """HTML-ul RANDAT al unei pagini de listare. `None` = sfarsit de intrare.

    **De ce `via` si nu `method`.** `method` descrie cum se citeste un PDP (axa L);
    `via` descrie cum se aduce o pagina de LISTARE (axa D). Cele doua axe sunt
    independente, si conrad.com o dovedeste: e `method: "browser"` fiindca PDP-ul
    lui da 403 pe poarta HTTP, dar listarea lui de reduceri raspunde 200 pe HTTP
    si ramane deliberat pe calea ieftina (DEAL-D9). O ramura care ar alege dupa
    `method` l-ar fi mutat pe browser fara sa fi masurat nimic — si l-ar fi
    scumpit de la ~1 s la ~5 s pe pagina, in cel mai bun caz.

    **Costul, si de ce e bimodal.** Masurat la BRW-0/0b, pe Windows cu Chrome
    real: o pagina care se valideaza costa **2,1–6,3 s**; una care NU se valideaza
    costa plafonul intreg de poll plus lansarea, adica **22–38 s**. Esecul e de
    sapte ori mai scump decat reusita, deci `max_pages` pe calea asta se alege din
    COST, nu din adancimea catalogului: recomandarea e <= 5.

    **Un `Blocked` nu se reincearca.** GUARD-1 are un retry, dar strict pe `None`
    — „n-am ajuns la magazin". Un zid e un raspuns REAL al magazinului, iar G4b a
    masurat ca insistenta pe acelasi URL inrautateste situatia (acolo a produs
    Access Denied-ul). Pe pagina 1 zidul inseamna intrare moarta si se ridica; pe
    o pagina > 1 a unei intrari care a citit deja ceva e sfarsit de intrare, cu
    paginile de dinainte pastrate — exact regula pe care scannerul o are deja
    pentru 404 (VAL D) si pentru 5xx (STATE-1).

    `TooSoon` e singura exceptie tratata prin asteptare, si tot o singura data:
    domeniul are interval de politete si el se RESPECTA, nu se ocoleste. A doua
    oara inseamna ca altcineva tine magazinul ocupat, si atunci se aplica regula
    zidului.
    """
    valideaza = _validator_grila(descriptor, domain)
    for incercare in (1, 2):
        try:
            return fetch_browser_html(url, domain, valideaza=valideaza)
        except BrowserFetchTooSoon as exc:
            if incercare == 2:
                return _zid(domain, url, numar, pagini_intrare, str(exc))
            asteptare = _secunde_de_asteptat(str(exc))
            logger.warning(
                "[ListingScan] %s: interval de politete neimplinit pe pagina %s, "
                "astept %.0fs si reincerc o data", domain, numar, asteptare)
            time.sleep(asteptare)
        except BrowserFetchBlocked as exc:
            return _zid(domain, url, numar, pagini_intrare, str(exc))
        except BrowserFetchUnavailable as exc:
            # Browserul lipseste sau nu s-a putut lansa: nu e vina magazinului si
            # nu e sfarsit de nimic. Se ridica pe ORICE pagina, ca defectiunea sa
            # ajunga in ShopScanState in loc sa treaca drept „gata devreme".
            raise RuntimeError(
                f"listare esuata la pagina {numar}: browserul nu e disponibil "
                f"({exc})") from exc
    return None                                   # pragmatic: bucla are `return` pe toate caile


def _zid(domain: str, url: str, numar: int, pagini_intrare: int,
         motiv: str) -> None:
    """Un zid de browser: sfarsit de intrare pe o pagina > 1 deja productiva,
    eroare oriunde altundeva. Fara a doua incercare (v. `_pagina_prin_browser`)."""
    if numar > 1 and pagini_intrare > 0:
        logger.warning(
            "[ListingScan] %s: intrarea s-a oprit la pagina %s (%s) — "
            "paginile citite raman comise", domain, numar, motiv)
        return None
    raise RuntimeError(f"listare esuata la pagina {numar} ({motiv})")


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
    acum = acum_local()

    # BRW-1 — implicit `"http"`: cei 55 de descriptori de dinainte n-au cheia si
    # raman pe poarta guarded, neatinsi.
    via_browser = descriptor.get("via") == "browser"

    # Anti-avalanche (design decision, deliberate): on a domain's FIRST successful
    # scan nothing is sent to Discord. R1 is free on this path — every card that
    # shows a struck price qualifies instantly — so a first scan of otter alone
    # would fire hundreds of messages for products that have been on sale for
    # weeks. The first scan establishes the baseline; from the second on, only
    # genuinely NEW deals notify, capped so a shop-wide sale cannot flood either.
    primul_scan = _e_primul_scan(db, domain)

    prag_r1 = _prag_r1(settings)

    # EMAG-D — ce e per SCAN si ce e per INTRARE, si de ce.
    #
    # `vazute` ramane per SCAN: garda SCAN-1 exista fiindca un produs poate aparea
    # de doua ori, iar pe eMAG asta se intampla si INTRE categorii (un produs
    # listat si la „Laptop" si la „PC"), nu doar intre paginile aceleiasi liste.
    # Resetat per intrare, al doilea contact ar re-intra in blocul de memorie si
    # ar cadea pe cheia unica, exact bug-ul pe care SCAN-1 l-a reparat.
    #
    # `calificate` la fel: inchiderea dealurilor necalificate se face DUPA toate
    # intrarile, altfel prima categorie ar inchide dealurile celei de-a doua.
    #
    # `linkuri_vazute`, in schimb, e per INTRARE (vezi bucla). Clamp-ul inseamna
    # „lista asta mi-a servit iar pagina precedenta"; doua categorii care impart
    # un produs NU sunt un clamp, si tratate ca atare ar taia a doua categorie
    # dupa prima pagina.
    vazute: set[str] = set()
    # DEAL-2b — `calificate` != `vazute`: primul e "am citit produsul", al doilea
    # "produsul CHIAR e un deal acum". Inchiderea se face pe al doilea, vezi jos.
    calificate: set[str] = set()
    produse_vazute = 0
    alerte = 0
    pagini = 0
    # D7 — notificarile se strang aici si pleaca DUPA commit-ul paginii, ca un
    # timeout de retea catre Discord sa nu mai prelungeasca tranzactia.
    # DISC-1 — perechi (deal, canal), nu doar deal-uri: canalul se stie AICI, din
    # intrarea de listare care tocmai a produs cardul, si nu se mai poate deduce
    # din randul comis (Deal n-are coloana de canal, deliberat — rutarea e o
    # proprietate a registrului, nu a observatiei, si trebuie sa se schimbe cand
    # se schimba registrul, nu la urmatorul scan).
    de_notificat: list[tuple[Deal, str]] = []

    intrari = _intrari(descriptor)
    for indice_intrare, intrare in enumerate(intrari):
        # Menajarea magazinului nu se opreste la granita dintre doua liste: fara
        # pauza aici, ultima pagina a unei categorii si prima a urmatoarei ar
        # pleca spate-in-spate.
        if indice_intrare > 0:
            _pauza()
        linkuri_vazute: set[str] = set()
        pagini_intrare = 0

        for numar in range(1, intrare["max_pages"] + 1):
            if numar > 1:
                _pauza()
            url = _pagina_url(intrare, numar)
            if via_browser:
                # BRW-1 — a doua cale de fetch a scannerului de listari. Vezi
                # `_pagina_prin_browser` pentru de ce `via` si nu `method`.
                html_pagina = _pagina_prin_browser(url, domain, descriptor,
                                                   numar, pagini_intrare)
                if html_pagina is None:
                    break                 # zid pe o pagina > 1: sfarsit de intrare
            else:
                raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS,
                                                  timeout=_TIMEOUT)

                # GUARD-1 — UN SINGUR retry, si numai pe `None`, si numai pe pagina 1.
                #
                # Trei observatii independente, toate cu aceeasi forma — poarta intoarce
                # `None` o data si merge la cererea urmatoare, pe acelasi URL, cu acelasi
                # profil:
                #   * GATE-1  — nike.com;
                #   * GATE-3  — computeruniverse.net: `/de` a intors `None` la LST-D5, iar
                #               sonda a cerut EXACT acelasi URL prin ACEEASI poarta si a
                #               primit 200 din primul hop (1.101.369 de octeti). Runda aia
                #               a exclus cu cifre RATE, allow-list, normalizarea si
                #               interstitiul; cauza a ramas nestabilita;
                #   * LST-D5  — action.com, `prod1`.
                #
                # `None` inseamna „n-am ajuns la magazin" (exceptie de retea, poarta
                # inchisa), NU „magazinul a spus nu". De aia retry-ul e strict pe `None`:
                # un 403 sau un 500 e un raspuns REAL si repetarea lui n-ar face decat sa
                # mai bata o data la o usa care tocmai s-a inchis — exact ce a produs
                # Access Denied-ul de la G4b, unde insistenta pe acelasi URL a inrautatit
                # situatia.
                #
                # Un singur retry, nu o bucla: daca a doua cerere e tot `None`, e o
                # defectiune reala si trebuie sa se auda. Iar WARN-ul de pe calea
                # reusita nu e decor — e MASURATOAREA care lipseste: din frecventa lui
                # se vede daca `None`-urile tranzitorii se aduna pe domeniile Cloudflare
                # (ipoteza `__cf_bm` din GATE-3) sau sunt uniforme.
                if raspuns is None and numar == 1:
                    _pauza()
                    time.sleep(_PAUZA_RETRY_S)
                    raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS,
                                                      timeout=_TIMEOUT)
                    if raspuns is not None and raspuns.status_code == 200:
                        logger.warning(
                            "[ListingScan] %s: `None` tranzitoriu pe pagina 1 (%s), "
                            "reusit la a doua cerere", domain, url)
                    else:
                        status = getattr(raspuns, "status_code", None)
                        raise RuntimeError(
                            f"listare esuata la pagina {numar} dupa retry "
                            f"(status: {status})")

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
                #   * pe pagina 1 (`pagini_intrare == 0`) 404 ramane EROARE — acolo
                #     inseamna listare moarta (URL mutat, categorie stearsa), nu sfarsit;
                #   * DOAR 404. Un 403 sau un 5xx e zid ori defectiune si trebuie sa se
                #     vada ca eroare, nu sa fie confundat cu un final de paginare.
                #
                # EMAG-D — contorul e cel AL INTRARII, nu cel global. Cu `pagini > 0`,
                # un 404 pe pagina 1 a categoriei a doua ar fi fost inghitit ca „final
                # de paginare" doar fiindca prima categorie citise deja pagini, iar o
                # categorie moarta ar fi disparut din scan in tacere — exact ce trebuie
                # sa se auda, fiindca inseamna ca hub-ul s-a schimbat.
                if (raspuns is not None and raspuns.status_code == 404
                        and numar > 1 and pagini_intrare > 0):
                    break

                if raspuns is None or raspuns.status_code != 200:
                    # STATE-1 — pe o pagina > 1 a unei intrari care a citit deja cel
                    # putin o pagina, ORICE raspuns nereusit (5xx, 403, 429, sau un
                    # `None` din poarta) e SFARSIT DE INTRARE, nu esec de scan.
                    #
                    # Masurat pe prm (LST-D4): coada listarii `/ro/s/final-sale` da
                    # HTTP 500. Cum `RuntimeError` cade INAINTE de `db.commit()`, un
                    # singur 500 la pagina 30 arunca tot ce citisera primele 29 —
                    # aceeasi pierdere pe care VAL D o reparase deja pentru 404, doar
                    # pe alt cod de stare. Cu 42 de domenii pe axa, un 5xx tranzitoriu
                    # devine o certitudine statistica, nu o ipoteza.
                    #
                    # Doua granite raman NESCHIMBATE, si amandoua deliberat:
                    #   * pe pagina 1 (`pagini_intrare == 0`) orice non-200 ramane
                    #     EROARE — acolo inseamna intrare moarta (URL mutat, categorie
                    #     stearsa), care trebuie sa se auda, nu sa treaca drept „gata";
                    #   * 404 ramane sfarsit TACUT (ramura de mai sus), fiindca acolo
                    #     „pagina nu exista" chiar e raspunsul asteptat la coada.
                    # Diferenta fata de 404 e tocmai zgomotul: aici se scrie un WARN,
                    # fiindca un 500 e o anomalie a magazinului, nu o granita normala.
                    status = getattr(raspuns, "status_code", None)
                    if numar > 1 and pagini_intrare > 0:
                        logger.warning(
                            "[ListingScan] %s: intrarea %s s-a oprit la pagina %s "
                            "(status: %s) — paginile citite raman comise",
                            domain, intrare.get("url"), numar, status)
                        break
                    raise RuntimeError(
                        f"listare esuata la pagina {numar} "
                        f"(status: {status})")
                html_pagina = raspuns.text

            carduri = extrage_carduri(html_pagina, descriptor, domain)
            linkuri_pagina = {c["url"] for c in carduri}

            # --- composite stop condition (measured in LST-1b, see module docstring) ---
            if not linkuri_pagina:
                # BRW-1 — pe calea de browser, „zero carduri pe pagina 1" NU e o
                # grila goala: `fetch_browser_html` intoarce HTML si cand
                # validatorul n-a trecut niciodata (dupa plafonul de poll), iar
                # validatorul de aici E chiar detectorul de grila. Deci corpul asta
                # e un shell nerandat sau un zid pe care garda nu l-a recunoscut —
                # si a costat plafonul intreg de poll (22–38 s, masurat la BRW-0
                # §7). Tacerea ar transforma un domeniu mort intr-un scan „reusit
                # cu 0 produse"; pe HTTP tacerea e corecta, fiindca acolo un 200 cu
                # grila goala chiar inseamna „momentan nicio reducere".
                if via_browser and numar == 1:
                    raise RuntimeError(
                        f"listare esuata la pagina {numar}: browserul a intors "
                        f"HTML nevalidat (zero carduri)")
                break                                   # empty grid: otter, caseking
            if linkuri_pagina <= linkuri_vazute:
                break                                   # clamp: noriel (p1), bergfreunde (last)
            linkuri_vazute |= linkuri_pagina
            pagini += 1
            pagini_intrare += 1

            # D10 — doua interogari pe pagina in loc de doua per card. Pozitia e DUPA
            # conditiile de oprire de mai sus: pe o pagina care declanseaza `break` n-are
            # rost sa mai intrebam baza de date nimic.
            ids_pagina = [c["external_id"] for c in carduri
                          if c["external_id"] not in vazute]
            memorii, dealuri = preincarca_pagina(db, domain, ids_pagina)

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
                memorie = memorii.get(external_id)
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

                deal = dealuri.get(external_id)
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
                        de_notificat.append((deal, deal_channel(domain, intrare)))
                else:
                    # D7: the state belongs to the USER, so it stays untouched —
                    # `vazut` stays `vazut` (MAG-1 removed `ignorat`). No alert on
                    # reappearance.
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
            # DISC-1 — plafonul numara DEAL-URI, nu mesaje: un deal care pleaca si
            # pe `toate` si pe canalul lui consuma o singura unitate din buget.
            # `send_deal_notification` intoarce True daca a plecat macar unul.
            for deal, canal in de_notificat:
                if alerte < _MAX_ALERTE and send_deal_notification(deal, settings, canal):
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


def _mmss(secunde: float) -> str:
    """`mm:ss`, cu minutele NEROSTOGOLITE peste 60 — un scan de 71 de minute se
    scrie `71:04`, nu `01:11:04`. Scanurile de aici se compara intre ele in
    minute, si o forma cu ore ar cere impartit in minte la fiecare citire."""
    intreg = int(secunde)
    return f"{intreg // 60:02d}:{intreg % 60:02d}"


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

        # PROD-1 — pana aici scanul nu-si consemna nici inceputul, nici sfarsitul,
        # si asta se vedea in analiza primului scan cu 55 de domenii: durata (51 si
        # 59 de minute pe cele doua rulari din 10 septembrie) a trebuit DEDUSA din
        # `last_scan_at`-urile din `shop_scan_state`, adica dintr-un efect
        # secundar. Cu 55 de domenii, „cat a durat tot" si „cat a durat fiecare"
        # sunt chiar cifrele din care se aleg plafoanele — vezi bergfreunde si
        # otter, care singure au mancat 28 din cele 51 de minute.
        #
        # `logger`, nu `print`, din acelasi motiv ca la STATE-1: un `print` nu
        # poate fi verificat de un test.
        t_scan = time.monotonic()
        logger.info("[ListingScan] start: %d domenii, ora %s",
                    len(domenii), acum_local().strftime("%H:%M:%S"))
        try:
            for domain in domenii:
                t_domeniu = time.monotonic()
                try:
                    rezultat = _scaneaza_domeniu(db, domain, settings, prag)
                except Exception as exc:                # noqa: BLE001
                    # A dead shop (changed markup, block, network) does NOT stop the
                    # rest: its state shows up in the health panel, the others carry on.
                    db.rollback()
                    _scrie_stare(db, domain, "error", eroare=f"{type(exc).__name__}: {exc}"[:500])
                    rezumat["erori"] += 1
                    # Durata si pe ramura de eroare, nu doar pe cea reusita: un 404
                    # pe pagina 1 pica in doua secunde, un blocaj de retea in
                    # zeci — acelasi mesaj, alt diagnostic.
                    print(f"[ListingScan] {domain}: eroare dupa {_mmss(time.monotonic() - t_domeniu)}"
                          f" — {type(exc).__name__}: {exc}")
                    continue
                _scrie_stare(db, domain, "ok", produse=rezultat["produse"],
                             deals_active=rezultat["deals_active"])
                rezumat["magazine"] += 1
                rezumat["produse"] += rezultat["produse"]
                rezumat["alerte"] += rezultat["alerte"]
                print(f"[ListingScan] {domain}: {rezultat['pagini']} pagini, "
                      f"{rezultat['produse']} produse, {rezultat['deals_active']} deal-uri "
                      f"active, {rezultat['alerte']} alerte, {_mmss(time.monotonic() - t_domeniu)}")
        finally:
            # In `finally` DELIBERAT: daca ceva cade in afara buclei (sau bucla e
            # intrerupta), linia de final trebuie sa se scrie oricum — altfel
            # exact scanurile care esueaza raman cele fara durata consemnata.
            rezumat["durata_s"] = round(time.monotonic() - t_scan, 1)
            logger.info("[ListingScan] final: %d domenii, %d ok, %d erori, %s",
                        len(domenii), rezumat["magazine"], rezumat["erori"],
                        _mmss(rezumat["durata_s"]))
        return rezumat
    finally:
        _LISTING_LOCK.release()
