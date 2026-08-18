"""Bootstrap dinamic: query-ul GraphQL si variabilele lui, luate DIN PAGINA.

Principiul (masurat la sondele FB-PROBE-3/4): NU inventam nimic. Pagina SSR contine
CHIAR query-ul folosit de Facebook, cu variabilele lui complete, intr-un bloc de
preloader Relay:

    "preloaderID":"adp_CometMarketplaceSearchContentContainerQueryRelayPreloader_...",
    "queryID":"27517490627932547",
    "variables":{ "buyLocation":{...}, "params":{...}, "count":24, ... }

Prima incercare de GraphQL, cu variabile construite din memorie, a esuat cu
`missing_required_variable_value` la TOATE apelurile. Daca Facebook schimba forma,
o mostenim automat — cu conditia sa nu hardcodam nimic (doc_id, nume de query,
forma variabilelor).

CAPCANA (nu o incalca): doc_id-urile din bundle-urile JS sunt pentru ALTE variante
ale query-ului. Singura sursa acceptabila e preloader-ul din pagina.

Suprafata logat-out se misca activ (la FB-0 setul implicit al paginii de fallback a
trecut de la ~24 la 1 anunt in 24 de ore), de-aici TTL-ul scurt si `invalideaza()`
apelat de client la ORICE eroare de resolver, nu doar la expirare.
"""
import json
import os
import re
import tempfile
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from typing import Optional

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import report_outcome, Outcome

BASE = "https://www.facebook.com"
# Bucuresti e SINGURUL slug de oras validat (FB-0: 1 din 51). Termenul e indiferent:
# `muta()` il suprascrie oricum — conteaza doar ca pagina sa fie una de SEARCH, ca
# sablonul sa contina `params.bqf.query`.
URL_SEARCH = f"{BASE}/marketplace/bucharest/search?query=canapea"
URL_CATEGORIE = f"{BASE}/marketplace/category/propertyrentals/"

_TTL_IMPLICIT_H = 6
_NUME_CACHE = "fb_bootstrap.json"

# FBS-1 — acelasi tipar cu care se scoate LSD-ul, pe cheia jetonului de sesiune.
_DTSG_RE = re.compile(r'"DTSGInitialData".{0,120}?"token"\s*:\s*"([^"]+)"', re.DOTALL)

_memo: Optional["Bootstrap"] = None


@dataclass(frozen=True)
class Bootstrap:
    doc_id: str
    variables: dict          # sablonul complet, netransformat
    lsd: str
    friendly_name: str       # numele query-ului, luat din pagina (vezi extrage_bootstrap)
    captured_at: datetime
    sursa: str               # "search" sau "categorie"
    sursa_html_len: int
    # FBS-1 — identitatea, optionala. Ambele raman None logat-out, deci bootstrap-ul
    # de azi ramane valid neschimbat si `identitate_din()` intoarce None.
    fb_dtsg: Optional[str] = None    # din PAGINA, acelasi tipar ca LSD
    c_user: Optional[str] = None     # din JAR-ul clientului, nu din pagina


def obiect_echilibrat(text: str, start: int) -> Optional[str]:
    """Decupeaza obiectul JSON care incepe la prima acolada de dupa `start`.

    Respecta stringurile si escape-urile: o acolada dintr-o valoare de string
    ("titlu {ca asta}") NU se numara. Varianta din sonda `fb_graphql_coverage_probe`
    numara acoladele orbeste — a mers pe mostrele de-atunci din noroc, fiindca
    acoladele nebalansate din stringuri sunt rare, dar `{` intr-un string JSON e
    perfect valid si ar taia obiectul gresit, TACUT. Un regex nu e o optiune:
    blocurile sunt JS minificat, imbricat pe zeci de niveluri.
    """
    j = text.find("{", start)
    if j < 0:
        return None
    adancime = 0
    in_string = False
    escapat = False
    for k in range(j, len(text)):
        c = text[k]
        if in_string:
            if escapat:
                escapat = False
            elif c == "\\":
                escapat = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            adancime += 1
        elif c == "}":
            adancime -= 1
            if adancime == 0:
                return text[j:k + 1]
    return None


def _are_forma_de_cautare(v) -> bool:
    """Sablonul bun e cel care are SIMULTAN `buyLocation` la radacina si calea
    `params.bqf.query` — adica exact campurile pe care `muta()` le rescrie.

    Filtrul nu e cosmetic: aceeasi pagina mai are preloadere cu `buyLocation` dar cu
    alta forma (`useCometLogInFormQuery` are `params` LISTA goala, iar query-urile de
    categorie au `categoryIDArray`/`radius` in loc de `params`). Fara verificarea
    asta s-ar alege un sablon pe care `muta()` l-ar respinge oricum, dupa ce am fi
    cheltuit deja o cerere.
    """
    if not isinstance(v, dict) or "buyLocation" not in v:
        return False
    params = v.get("params")
    if not isinstance(params, dict):
        return False
    bqf = params.get("bqf")
    return isinstance(bqf, dict) and "query" in bqf


def _friendly_name(html: str, i: int) -> Optional[str]:
    """Numele query-ului, din `preloaderID`: `adp_<Nume>RelayPreloader_<hash>`.

    Cheia `fb_api_req_friendly_name` NU exista in HTML-ul paginii (masurat: 0
    aparitii in toate mostrele), desi antetul cu acest nume TREBUIE trimis la POST.
    Numele traieste in preloaderID, de unde il luam structural — asa ramane "din
    pagina", nu hardcodat.
    """
    inainte = html[max(0, i - 300):i]
    poz = inainte.rfind("adp_")
    if poz < 0:
        return None
    nume = inainte[poz + 4:]
    return nume or None


def extrage_bootstrap(html: str, sursa: str) -> Optional[Bootstrap]:
    """Cauta in HTML preloaderul Relay cu forma de cautare. None daca nu exista
    (NU arunca): apelantul decide daca incearca alta sursa."""
    if not html:
        return None

    lsd = re.search(r'"LSD".{0,120}?"token"\s*:\s*"([^"]+)"', html, re.DOTALL)
    if not lsd:
        return None

    # `fb_dtsg` sta in pagina exact cu forma LSD-ului, doar sub alta cheie. Lipsa lui
    # NU e un esec: pe pagina logat-out nu exista, si acolo nici n-avem nevoie de el.
    dtsg = _DTSG_RE.search(html)

    for m in re.finditer("RelayPreloader", html):
        i = m.start()
        vi = html.find('"variables"', i)
        if vi < 0 or vi - i > 6000:
            continue
        brut = obiect_echilibrat(html, vi)
        if not brut:
            continue
        try:
            variables = json.loads(brut)
        except Exception:
            continue
        if not _are_forma_de_cautare(variables):
            continue

        qid = re.search(r'"queryID"\s*:\s*"(\d+)"', html[i:i + 4000])
        if not qid:
            continue
        nume = _friendly_name(html, i)
        if not nume:
            continue

        return Bootstrap(
            doc_id=qid.group(1), variables=variables, lsd=lsd.group(1),
            friendly_name=nume, captured_at=datetime.now(timezone.utc),
            sursa=sursa, sursa_html_len=len(html),
            fb_dtsg=dtsg.group(1) if dtsg else None,
        )
    return None


# ── cache pe disc ────────────────────────────────────────────────────────────
def _cale_cache():
    """DATA_DIR se citeste LA APEL, nu la import: altfel testele nu-l pot redirecta
    spre tmp_path, iar build-ul PyInstaller l-ar fixa la valoarea de la pornire."""
    from app import config
    return config.DATA_DIR / "data" / _NUME_CACHE


def _ttl_ore() -> float:
    try:
        return float(os.getenv("FB_BOOTSTRAP_TTL_H") or _TTL_IMPLICIT_H)
    except (TypeError, ValueError):
        return _TTL_IMPLICIT_H


def acelasi_cont(a, b) -> bool:
    """Doua identitati sunt ale ACELUIASI cont?

    `None` (logat-out) si un `c_user` sunt identitati DIFERITE, nu una lipsa. De-aia
    comparatia e stricta in ambele sensuri: un cache scris logat-out nu se refoloseste
    logat-in (n-are `fb_dtsg`), iar unul scris cu un cont nu se refoloseste cu altul
    (`fb_dtsg` e legat de sesiune, si un jeton strain produce EXACT 1357004).
    """
    return (a or None) == (b or None)


def _citeste_cache() -> Optional[Bootstrap]:
    cale = _cale_cache()
    try:
        brut = json.loads(cale.read_text(encoding="utf-8"))
        captat = datetime.fromisoformat(brut["captured_at"])
        if captat.tzinfo is None:
            captat = captat.replace(tzinfo=timezone.utc)
        varsta_h = (datetime.now(timezone.utc) - captat).total_seconds() / 3600
        if varsta_h > _ttl_ore():
            return None
        return Bootstrap(
            doc_id=brut["doc_id"], variables=brut["variables"], lsd=brut["lsd"],
            friendly_name=brut["friendly_name"], captured_at=captat,
            sursa=brut.get("sursa", "search"),
            sursa_html_len=brut.get("sursa_html_len", 0),
            fb_dtsg=brut.get("fb_dtsg"), c_user=brut.get("c_user"),
        )
    except Exception:
        return None          # lipsa, corupt sau cu alta forma: se re-bootstrapeaza


def _scrie_cache(boot: Bootstrap) -> None:
    """Scriere ATOMICA: fisier temporar in acelasi director + os.replace. Altfel un
    proces oprit la jumatatea scrierii lasa un JSON trunchiat pe care urmatoarea
    pornire il citeste ca 'cache corupt' — recuperabil, dar dupa o cerere in plus."""
    cale = _cale_cache()
    try:
        cale.parent.mkdir(parents=True, exist_ok=True)
        d = asdict(boot)
        d["captured_at"] = boot.captured_at.isoformat()
        fd, tmp = tempfile.mkstemp(dir=str(cale.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(tmp, cale)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as exc:
        log_manager.emit("radar", "WARN",
            f"Facebook bootstrap: cache nescris ({str(exc)[:80]})")


def invalideaza() -> None:
    """Sterge bootstrap-ul din memorie SI de pe disc. Apelat de client la orice
    eroare de resolver GraphQL, nu doar la expirare."""
    global _memo
    _memo = None
    try:
        _cale_cache().unlink()
    except (FileNotFoundError, OSError):
        pass


def incarca_sau_bootstrapeaza(client, *, forteaza: bool = False) -> Optional[Bootstrap]:
    """Bootstrap din cache, altfel din pagina. None daca ambele surse esueaza.

    Sursa alternativa (pagina de categorie) e redundanta la SINGURUL punct de care
    depinde acoperirea nationala, nu o treapta noua in scara de robustete.
    """
    global _memo
    # Identitatea CURENTA a clientului decide daca un bootstrap salvat mai e bun.
    # `getattr` cu implicit: dublurile de test n-au proprietatea, si atunci se
    # comporta exact ca un client logat-out — comportamentul de dinainte de FBS-1.
    c_user = getattr(client, "c_user", None)

    if not forteaza:
        if _memo is not None and acelasi_cont(_memo.c_user, c_user):
            return _memo
        din_disc = _citeste_cache()
        if din_disc is not None and acelasi_cont(din_disc.c_user, c_user):
            _memo = din_disc
            return _memo
        if din_disc is not None:
            log_manager.emit("radar", "WARN",
                "Facebook bootstrap: cache-ul e al altui cont (sau al caii "
                "logat-out) — se ignora si se re-bootstrapeaza, altfel fb_dtsg-ul "
                "strain ar produce eroarea de identitate 1357004")

    for url, sursa in ((URL_SEARCH, "search"), (URL_CATEGORIE, "categorie")):
        corp, status = client.get(url)
        boot = extrage_bootstrap(corp or "", sursa)
        if boot is not None:
            if c_user:
                boot = replace(boot, c_user=str(c_user))
            if sursa != "search":
                log_manager.emit("radar", "WARN",
                    "Facebook bootstrap: pagina de search nu a dat sablon, "
                    f"folosesc sursa alternativa '{sursa}'")
            _memo = boot
            _scrie_cache(boot)
            return boot
        log_manager.emit("radar", "WARN",
            f"Facebook bootstrap: fara sablon valid din '{sursa}' "
            f"(HTTP {status}, {len(corp or '')} octeti)")

    # A3: esecul de bootstrap e ZGOMOTOS, nu amanat — fara sablon nu exista
    # acoperire nationala, deci nu e o degradare partiala.
    log_manager.emit("radar", "WARN",
        "Facebook bootstrap: NICIO sursa nu a dat sablon valid (search + categorie)")
    report_outcome("facebook", Outcome.BLOCKED)
    return None
