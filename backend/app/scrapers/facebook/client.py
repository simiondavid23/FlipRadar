"""Transportul si scara de robustete a nucleului Facebook logat-out.

Transport: curl_cffi cu profilul centralizat (`impersonate_for("facebook")`), FARA
suprascrierea User-Agent-ului (lectia IMP-1: un UA rotit peste o amprenta TLS de
Chrome e o contradictie pe care niciun browser real n-o produce). Jar de cookie-uri
GOL — nimic incarcat de pe disc: calea logat-out nu are si nu trebuie sa aiba
sesiune. Calea AUTENTIFICATA existenta ramane neatinsa in radar/, aleasa la FB-4/FB-5
printr-un comutator manual `FB_MOD`; nucleul asta nu e un fallback automat pentru ea.

Scara de robustete a lui `search`, cu WARN la FIECARE coborare:
  1. GraphQL cu bootstrap din cache
  2. invalideaza() + re-bootstrap FORTAT o singura data + retry GraphQL
  3. SSR pe `fb_slug`, doar daca e dat (validat: practic doar Bucuresti)
  4. WARN + report_outcome(BLOCKED) + lista goala

O coborare de la treapta 1 la 2 urmata de succes e un rezultat NORMAL, nu o eroare:
sablonul se invecheste, il reimprospatam, mergem mai departe.

Log-urile merg pe modulul `radar`: log_manager NU are modul `network` si rescrie
TACUT modulele necunoscute peste `radar` (vezi log_manager.emit) — deci un `network`
n-ar da eroare, doar ar ascunde de unde vine mesajul.
"""
import os
import random
import time
from typing import Optional

from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.network.binding import curl_kwargs
from app.services.radar.base_scraper import (
    build_headers, rate_limit_backoff, report_outcome, Outcome,
)
from app.utils.http_profile import impersonate_for

from .bootstrap import incarca_sau_bootstrapeaza, invalideaza
from .graphql import muta, cauta, extrage_anunturi
from .parse import canonic
from .ssr import cauta_ssr

TIMEOUT = 30
_MAX_RETRY = 2                  # incercari SUPLIMENTARE, doar pe retea si 5xx
_PAUZA_MIN_IMPLICIT = 4.0
_PAUZA_MAX_IMPLICIT = 12.0


def _pauza_range() -> tuple[float, float]:
    def _f(nume, implicit):
        try:
            return float(os.getenv(nume) or implicit)
        except (TypeError, ValueError):
            return implicit
    lo = _f("FB_PAUZA_MIN_S", _PAUZA_MIN_IMPLICIT)
    hi = _f("FB_PAUZA_MAX_S", _PAUZA_MAX_IMPLICIT)
    return (lo, hi) if hi >= lo else (lo, lo)


class FacebookClient:
    """Sesiune curl_cffi cu jar gol si pauze intre cereri.

    `sleep` e injectabil ca testele sa nu astepte real. Dupa un 403/429 clientul se
    ZAVORASTE (`_blocat`): orice cerere ulterioara din acelasi apel se refuza fara
    trafic. Fara zavor, scara de robustete ar continua sa coboare treptele si ar
    trimite inca 2-3 cereri exact catre serverul care tocmai ne-a limitat.
    """

    def __init__(self, *, sleep=time.sleep):
        self._sleep = sleep
        self._sesiune = curl_requests.Session(impersonate=impersonate_for("facebook"))
        self._sesiune.cookies.clear()        # jar GOL, explicit
        self._prima = True
        self._blocat = False

    # ── infrastructura ───────────────────────────────────────────────────────
    def _pauza(self):
        if self._prima:
            self._prima = False
            return
        lo, hi = _pauza_range()
        self._sleep(random.uniform(lo, hi))

    def _blocheaza(self, status: int, url: str):
        self._blocat = True
        log_manager.emit("radar", "WARN",
            f"Facebook: HTTP {status} — blocaj, nu se reincearca ({url[:70]})")
        report_outcome("facebook", Outcome.BLOCKED)

    def _cere(self, metoda: str, url: str, **kw) -> tuple[str, Optional[int]]:
        if self._blocat:
            return "", None
        antete = build_headers(kw.pop("headers", None))
        kwargs = dict(curl_kwargs("facebook"))        # {} azi: facebook e _NEVER_ROUTED
        kwargs.update(kw)

        for incercare in range(_MAX_RETRY + 1):
            self._pauza()
            try:
                r = getattr(self._sesiune, metoda)(
                    url, headers=antete, timeout=TIMEOUT, **kwargs)
            except Exception as exc:
                if incercare >= _MAX_RETRY:
                    log_manager.emit("radar", "WARN",
                        f"Facebook: eroare de retea ({type(exc).__name__}) "
                        f"dupa {incercare + 1} incercari")
                    return "", None
                self._sleep(rate_limit_backoff(incercare))
                continue

            status = r.status_code
            if status in (403, 429):
                self._blocheaza(status, url)
                return (r.text or ""), status
            if 500 <= status < 600 and incercare < _MAX_RETRY:
                self._sleep(rate_limit_backoff(incercare))
                continue
            return (r.text or ""), status
        return "", None

    def get(self, url: str) -> tuple[str, Optional[int]]:
        return self._cere("get", url)

    def post(self, url: str, data=None, headers=None) -> tuple[str, Optional[int]]:
        return self._cere("post", url, data=data, headers=headers)


def _client_implicit() -> FacebookClient:
    return FacebookClient()


def _are_cheia(obj, cheie: str) -> bool:
    """Cheia exista oriunde in structura? Distinge un `edges: []` legitim (zero
    rezultate, raspuns valid) de un raspuns cu ALTA forma (esec de parsare)."""
    if isinstance(obj, dict):
        if cheie in obj:
            return True
        return any(_are_cheia(v, cheie) for v in obj.values())
    if isinstance(obj, list):
        return any(_are_cheia(v, cheie) for v in obj)
    return False


def _obiecte_sau_none(raspuns) -> Optional[list]:
    """Obiectele brute din raspuns, sau None daca treapta a ESUAT.

    Zero obiecte NU inseamna automat esec: daca raspunsul contine `edges`, e o
    cautare fara rezultate — corecta. Fara `edges`, forma e alta decat cea asteptata
    si merita coborata o treapta.
    """
    if raspuns is None:
        return None
    obiecte = extrage_anunturi(raspuns)
    if obiecte:
        return obiecte
    return [] if _are_cheia(raspuns, "edges") else None


def _canonice(obiecte: list) -> list[dict]:
    """Forma canonica + dedup pe external_id, in interiorul apelului."""
    vazute, out = set(), []
    for o in obiecte:
        c = canonic(o)
        if not c:
            continue
        if c["external_id"] in vazute:
            continue
        vazute.add(c["external_id"])
        out.append(c)
    return out


def search(query: str, lat: float, lon: float, *, raza_km: float = 65,
           fb_slug: Optional[str] = None, client: Optional[FacebookClient] = None
           ) -> list[dict]:
    """Anunturi CANONICE pentru o ancora geografica. Lista goala = nimic obtinut.

    `client` e o cusatura de test (injecteaza un dublu cu get/post); in productie
    ramane None si se creeaza unul implicit.
    """
    cl = client if client is not None else _client_implicit()

    # ── treapta 1: GraphQL cu bootstrap din cache ────────────────────────────
    boot = incarca_sau_bootstrapeaza(cl)
    obiecte = None
    if boot is not None:
        variabile = muta(boot.variables, query=query, lat=lat, lon=lon, raza_km=raza_km)
        if variabile is not None:
            obiecte = _obiecte_sau_none(cauta(cl, boot, variabile))
    if obiecte is not None:
        return _canonice(obiecte)

    # ── treapta 2: sablon invechit -> re-bootstrap fortat, O SINGURA DATA ─────
    log_manager.emit("radar", "WARN",
        "Facebook treapta 1->2: GraphQL cu sablonul din cache a esuat, "
        "reimprospatez bootstrap-ul si reincerc")
    invalideaza()
    boot = incarca_sau_bootstrapeaza(cl, forteaza=True)
    if boot is not None:
        variabile = muta(boot.variables, query=query, lat=lat, lon=lon, raza_km=raza_km)
        if variabile is not None:
            obiecte = _obiecte_sau_none(cauta(cl, boot, variabile))
    if obiecte is not None:
        return _canonice(obiecte)

    # ── treapta 3: SSR, doar cu slug validat ─────────────────────────────────
    if fb_slug:
        log_manager.emit("radar", "WARN",
            f"Facebook treapta 2->3: GraphQL a esuat si dupa re-bootstrap, "
            f"incerc SSR pe slug-ul '{fb_slug}'")
        brute = cauta_ssr(cl, fb_slug, query)
        if brute:
            return _canonice(brute)
        motiv = f"SSR pe '{fb_slug}' nu a intors anunturi"
    else:
        motiv = "fara fb_slug validat, calea SSR nu se poate incerca"

    # ── treapta 4: nimic ─────────────────────────────────────────────────────
    log_manager.emit("radar", "WARN",
        f"Facebook treapta 3->4: {motiv} — nicio cale nu a functionat")
    report_outcome("facebook", Outcome.BLOCKED)
    return []
