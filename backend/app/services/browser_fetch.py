"""BR-1 — harness de browser: A TREIA cale de fetch pentru paginile de produs.

Pana aici existau doua cai: fetch HTTP prin poarta guarded C-14 (majoritatea
magazinelor) si endpoint-ul Ajax al Shopify. Grupul 4 e multimea magazinelor pe
care NICIUNA nu functioneaza — nu fiindca datele lipsesc, ci fiindca HTML-ul
initial nu le poarta (randare pe client) sau fiindca cererea fara browser real e
respinsa. Sondele G4/G4b (2026-08-13) au masurat cele patru cazuri:

  orange.ro   — CSR curat: 200, 840KB, dar ld+json apare abia in DOM-ul randat
  makeup.ro   — interstitiu JS servit cu 202 pe paginile de produs (corp identic
                la octet pe toate treptele de impersonare, deci nu e amprenta TLS)
  hhv.de      — challenge servit pe 200 (~2KB JS obfuscat) si, pe headless,
                ERR_CONNECTION_RESET; headed trece curat
  sephora.ro  — 403 cu corp de 519B fara browser; headed trece

Prototipul e mobile_de_scraper (Imperva): context MINIMAL fara stealth — un
user_agent custom strica exact consistenta cu Client Hints pe care o verifica
detectoarele — plus Chrome real prin channel, cu fallback pe Chromium bundled.
DIFERENTA fata de prototip: acolo se asteapta FIX 6s dupa navigare. G4b a masurat
timpul real pana la continut (2.53s / 0.47s / 0.57s pe hhv, 0.39s pe sephora), deci
in 3 din 4 cazuri continutul e gata la PRIMA incercare. Aici asteptarea fixa e
inlocuita cu parse-poll: incercam sa parsam la fiecare ~1.5s si iesim la primul
succes. Plafonul de 20s ramane doar pentru cazurile care chiar nu se randeaza.

Harness-ul NU importa extractorul si nu stie ce inseamna "produs": validarea vine
de la apelant, ca un callback (dispecerul ii da `parse_product_html`). Asta tine
patchright in afara grafului de import al extractorului si face harness-ul
testabil fara browser.
"""
import re
import threading
import time
import urllib.parse

from app.services.log_manager import log_manager
from app.services.shop_registry import browser_domains, browser_profile_of


class BrowserFetchError(Exception):
    """Baza celor trei esecuri ale harness-ului (dispecerul le mapeaza pe reason-uri)."""


class BrowserFetchBlocked(BrowserFetchError):
    """Pagina a fost servita, dar e un interstitiu anti-bot, nu continut."""


class BrowserFetchUnavailable(BrowserFetchError):
    """Browserul n-a putut fi folosit: patchright lipsa, lansare esuata, navigare
    esuata, sau destinatie nesanctionata."""


class BrowserFetchTooSoon(BrowserFetchError):
    """Domeniul are interval minim configurat si n-a trecut destul de la ultima
    vizita. Nu se lanseaza browser deloc."""


# Un SINGUR Chromium in orice moment, indiferent cate fire cer pagini. Lock-ul e
# BLOCANT, nu try-acquire: apelurile vin din refresh-ul de preturi, care e deja
# serializat, deci nu se aduna coada — iar un al doilea browser ar dubla varful de
# RAM. Tinta de rulare e un Raspberry Pi, unde un Chromium headed costa deja
# suficient cat sa nu-l vrem in doua exemplare.
_LOCK = threading.Lock()

# Domeniu -> momentul (monotonic) la care s-a INCHEIAT ultima vizita. Se citeste si
# se scrie doar sub _LOCK, deci n-are nevoie de sincronizare proprie.
_ULTIMA_VIZITA: dict[str, float] = {}

_POLL_INTERVAL_S = 1.5
_POLL_PLAFON_S = 20.0
_GOTO_TIMEOUT_MS = 45000

# Markere de blocare, in TEXTUL randat al paginii (nu in sursa). Lista e cea
# validata de sondele G4/G4b; cautarea in inner_text, nu in HTML, e deliberata —
# in sursa, "challenge-platform" apare si pe pagini perfect normale servite prin
# Cloudflare si a produs deja un fals pozitiv la sonda Grupului 1.
_MARKERE_BLOCARE = (
    "just a moment", "checking your browser", "attention required",
    "access denied", "zugriff verweigert", "captcha", "verifying you are human",
)

# Shell de interstitiu: corp mic, zero ancore si titlu gol-sau-lipsa. Regula e
# COMPLEMENTARA markerelor de text — interstitiul de 202 al makeup.ro are <title>
# GOL si niciun marker, iar challenge-ul hhv.de servit pe 200 e ~2KB de JS
# obfuscat fara titlu deloc. O pagina de produs reala are sute de KB si zeci de
# ancore, deci conjunctia celor trei conditii n-o poate atinge.
_PRAG_SHELL_OCTETI = 15000

# Un singur click permis in v1, si numai pe refuzul de cookie-uri: e singura
# interactiune care poate debloca CONTINUTUL (unele bannere blocheaza randarea),
# nu o cale de navigare. Ordinea acopera RO/DE/EN plus cele doua CMP-uri uzuale.
_SELECTORI_REFUZ = (
    "#onetrust-reject-all-handler",
    "button#didomi-notice-disagree-button",
    "button:has-text('Refuz')",
    "button:has-text('Respinge')",
    "button:has-text('Doar necesare')",
    "button:has-text('Ablehnen')",
    "button:has-text('Reject')",
)

_RE_TITLU = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _gazda(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _verifica_destinatia(url: str, domain: str) -> None:
    """Browserul navigheaza DOAR pe tinte sanctionate.

    Doua conditii, ambele necesare: gazda URL-ului trebuie acoperita de `domain`
    (suffix-safe, aceeasi regula ca allow-list-ul C-14 — un redirect catre
    evil-orange.ro.attacker.com nu se potriveste), iar `domain` trebuie sa fie
    marcat `method: "browser"` in registru. Prima conditie opreste un URL strain
    strecurat pe o cerere legitima; a doua opreste folosirea harness-ului ca proxy
    de navigare generic.

    `match_shop_domain` se importa LENES: modulul asta e incarcat el insusi lenes,
    din corpul extractorului, ca patchright sa nu devina dependinta de import a
    extractorului. Un import la nivel de modul aici ar functiona azi (importul
    invers e lenes), dar ar face directia fragila la prima reorganizare — iar
    regula de potrivire e prea sensibila ca s-o duplicam intr-o a doua copie.
    """
    from app.services.product_page_extractor import match_shop_domain

    domain = (domain or "").lower()
    if not domain or match_shop_domain(_gazda(url), {domain}) is None:
        raise BrowserFetchUnavailable(
            f"URL-ul nu apartine domeniului cerut ({domain!r}): {(url or '')[:120]}")
    if match_shop_domain(domain, browser_domains()) is None:
        raise BrowserFetchUnavailable(
            f"Domeniul {domain!r} nu e marcat pentru harness-ul de browser")


def _accepta(html: str, valideaza) -> bool:
    """True daca `html` e continutul cautat. Fara callback, orice corp nevid trece."""
    if not (html or "").strip():
        return False
    if valideaza is None:
        return True
    try:
        valideaza(html)
        return True
    except Exception:
        return False


def _asteapta_continutul(page, valideaza, plafon_s: float):
    """Parse-poll: incearca imediat, apoi la fiecare ~1.5s pana la `plafon_s`.

    Intoarce (html_castigator | None, ultimul_html_vazut). Prima incercare e la 0s
    tocmai fiindca G4b a masurat continutul gata din prima in 3 din 4 cazuri —
    asteptarea fixa de 6s a prototipului irosea ~5.5s per pagina.
    """
    limita = time.monotonic() + plafon_s
    ultim = ""
    while True:
        try:
            ultim = page.content() or ""
        except Exception:
            ultim = ultim or ""
        if _accepta(ultim, valideaza):
            return ultim, ultim
        if time.monotonic() >= limita:
            return None, ultim
        try:
            page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
        except Exception:
            return None, ultim


def _detecteaza_blocare(page, html: str):
    """Motivul blocarii, sau None daca pagina pare continut real."""
    try:
        text = (page.inner_text("body") or "")[:1500].lower()
    except Exception:
        text = ""
    for marker in _MARKERE_BLOCARE:
        if marker in text:
            return f"marker in body: {marker!r}"

    corp = html or ""
    if len(corp) < _PRAG_SHELL_OCTETI and "<a " not in corp.lower():
        potrivire = _RE_TITLU.search(corp)
        if potrivire is None or not potrivire.group(1).strip():
            return f"shell fara ancore si fara titlu ({len(corp)} octeti)"
    return None


def _refuza_cookieurile(page) -> bool:
    """Un SINGUR click, pe primul buton de refuz gasit. True daca s-a apasat ceva."""
    for selector in _SELECTORI_REFUZ:
        try:
            page.click(selector, timeout=2000)
            return True
        except Exception:
            continue
    return False


def _lanseaza(p, headed: bool):
    """(browser, canal). Chrome real e cheia consistentei UA/Client Hints; daca nu e
    instalat cadem pe Chromium-ul bundled de patchright — se logheaza, nu se crapa.
    """
    for canal in ("chrome", None):
        try:
            if canal:
                return p.chromium.launch(headless=not headed, channel=canal), canal
            return p.chromium.launch(headless=not headed), "chromium bundled"
        except Exception:
            continue
    raise BrowserFetchUnavailable("nu s-a putut lansa niciun browser")


def fetch_browser_html(url: str, domain: str, valideaza=None) -> str:
    """HTML-ul RANDAT al `url`, printr-o sesiune de browser dedicata.

    `valideaza` e callback-ul de continut: primeste HTML-ul si trebuie sa ridice
    exceptie daca nu e inca pagina cautata (dispecerul ii da parse_product_html).
    Fara el, primul corp nevid castiga.

    Ridica BrowserFetchTooSoon / BrowserFetchBlocked / BrowserFetchUnavailable.
    Cand pagina se randeaza dar nu se valideaza, intoarce totusi HTML-ul: eroarea
    de continut o formuleaza apelantul, care stie ce cauta.
    """
    _verifica_destinatia(url, domain)
    profil = browser_profile_of(domain)
    interval = profil.get("min_fetch_interval_s")

    # Verificarea intervalului sta SUB lock, nu inaintea lui: altfel doua fire ar
    # putea trece amandoua de ea si ar vizita magazinul spate-in-spate, exact ce
    # incearca sa previna. Costul e ca un apel prea devreme poate astepta intai
    # sesiunea in curs — acceptabil, apelurile vin din refresh serializat.
    with _LOCK:
        if interval:
            trecut = time.monotonic() - _ULTIMA_VIZITA.get(domain, float("-inf"))
            if trecut < interval:
                raise BrowserFetchTooSoon(
                    f"{domain}: {trecut:.0f}s de la ultima vizita, minimul e {interval}s")
        try:
            return _sesiune(url, domain, bool(profil.get("headed")), valideaza)
        finally:
            # Momentul de referinta e SFARSITUL vizitei, ca intervalul sa masoare
            # pauza reala dintre doua atingeri ale magazinului. Se stampileaza si
            # pe esec: o incercare blocata l-a atins la fel de tare — la sonda G4b,
            # tocmai insistenta pe acelasi URL a produs Access Denied-ul.
            _ULTIMA_VIZITA[domain] = time.monotonic()


def _sesiune(url: str, domain: str, headed: bool, valideaza) -> str:
    """O sesiune-per-pagina: lansare, navigare, poll, inchidere. Fara reutilizare de
    context intre pagini — D12 a masurat ca storage_state nu aduce castig
    (orange.ro: 7.16s prima vizita vs 7.22s a doua), iar o sesiune curata e si
    politicoasa, si lipsita de stare care sa se acumuleze."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserFetchUnavailable("patchright nu e instalat") from exc

    with sync_playwright() as p:
        browser, canal = _lanseaza(p, headed)
        try:
            log_manager.emit("catalog", "INFO",
                f"Browser: {domain} ({'headed' if headed else 'headless'}, {canal})")
            # Context MINIMAL, fara stealth si fara user_agent propriu: exact
            # configul validat pe mobile.de. Singura optiune e limba, si doar pe
            # magazinele romanesti, ca vitrina sa serveasca preturile in RON.
            kwargs = {"locale": "ro-RO"} if domain.endswith(".ro") else {}
            context = browser.new_context(**kwargs)
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=_GOTO_TIMEOUT_MS)
            except Exception as exc:
                raise BrowserFetchUnavailable(
                    f"navigare esuata pe {domain}: {str(exc)[:120]}") from exc

            html, ultim = _asteapta_continutul(page, valideaza, _POLL_PLAFON_S)
            if html is not None:
                return html

            motiv = _detecteaza_blocare(page, ultim)
            if motiv:
                log_manager.emit("catalog", "WARN", f"Browser: {domain} blocat — {motiv}")
                raise BrowserFetchBlocked(f"{domain}: {motiv}")

            # Nu e blocaj: poate fi un banner de consimtamant care tine continutul
            # ascuns. Un singur refuz, o singura re-incercare scurta.
            if _refuza_cookieurile(page):
                html, ultim = _asteapta_continutul(page, valideaza, _POLL_INTERVAL_S * 2)
                if html is not None:
                    return html
            # Randata, dar nealtcumva validabila: intoarcem ce avem si lasam
            # apelantul sa ridice eroarea lui, cu motivul ei exact.
            return ultim
        finally:
            try:
                browser.close()
            except Exception:
                pass
