"""Transportul si scara de robustete a nucleului Facebook logat-out.

Transport: curl_cffi cu profilul centralizat (`impersonate_for("facebook")`), FARA
suprascrierea User-Agent-ului (lectia IMP-1: un UA rotit peste o amprenta TLS de
Chrome e o contradictie pe care niciun browser real n-o produce). Jar de cookie-uri
GOL — nimic incarcat de pe disc: calea logat-out nu are si nu trebuie sa aiba
sesiune. Calea AUTENTIFICATA existenta ramane neatinsa in radar/, aleasa la FB-4/FB-5
printr-un comutator manual `FB_MOD`; nucleul asta nu e un fallback automat pentru ea.

Scara de robustete a lui `search`, INVERSATA la FBS-2, cu WARN la FIECARE coborare:
  1. SSR pe `city_page_id`, cu recenta — doar daca ancora are ID
  2. GraphQL cu bootstrap din cache
  3. invalideaza() + re-bootstrap FORTAT o singura data + retry GraphQL
  4. WARN + report_outcome(BLOCKED) + lista goala

DE CE SSR E ACUM PRIMA: GraphQL are trei jetoane care se rotesc la fiecare redeploy
Facebook (`doc_id`, `lsd`, `fb_dtsg`); SSR pe ID n-are niciunul. In plus, SSR accepta
`sortBy` si `daysSinceListed`, deci intoarce DIRECT ce ne intereseaza, in loc sa
aducem 24 de anunturi si sa taiem local. Ancorele fara `city_page_id` sar treapta 1
si incep de la GraphQL, exact ca inainte de FBS-2.

O coborare de la o treapta la urmatoarea urmata de succes e un rezultat NORMAL, nu o
eroare: sablonul se invecheste, il reimprospatam, mergem mai departe. Dar santinela
de zero rezultate OPRESTE coborarea — un zero confirmat de Facebook nu se
reconfirma cheltuind cereri GraphQL.

Log-urile merg pe modulul `radar`: log_manager NU are modul `network` si rescrie
TACUT modulele necunoscute peste `radar` (vezi log_manager.emit) — deci un `network`
n-ar da eroare, doar ar ascunde de unde vine mesajul.
"""
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.network.binding import curl_kwargs
from app.services.radar.base_scraper import (
    build_headers, rate_limit_backoff, report_outcome, Outcome,
)
from app.utils.http_profile import impersonate_for

from .bootstrap import incarca_sau_bootstrapeaza, invalideaza
from .graphql import (
    muta, cauta_cu_cod, extrage_anunturi, identitate_din, COD_IDENTITATE_INVALIDA,
)
from .parse import (
    canonic, filtreaza_dupa_varsta, looks_like_login_wall, looks_like_no_results,
)
from .ssr import cauta_ssr

TIMEOUT = 30
_MAX_RETRY = 2                  # incercari SUPLIMENTARE, doar pe retea si 5xx
_PAUZA_MIN_IMPLICIT = 4.0
_PAUZA_MAX_IMPLICIT = 12.0
# Fereastra locala de recenta (`FB_VARSTA_MAX_ORE`). Serverul lasa sa treaca ~38 h
# la `daysSinceListed=1` (masurat la FBS-0c), deci taierea fina se face aici.
_VARSTA_MAX_IMPLICIT_ORE = 24.0


def _pauza_range() -> tuple[float, float]:
    def _f(nume, implicit):
        try:
            return float(os.getenv(nume) or implicit)
        except (TypeError, ValueError):
            return implicit
    lo = _f("FB_PAUZA_MIN_S", _PAUZA_MIN_IMPLICIT)
    hi = _f("FB_PAUZA_MAX_S", _PAUZA_MAX_IMPLICIT)
    return (lo, hi) if hi >= lo else (lo, lo)


# Markerii de checkpoint, ALESI PRIN MASURATOARE pe cele 35 de raspunsuri reale de
# care dispunem (23 din sondele FBS-0* + fixture-urile FB-1). Fiecare are ZERO
# aparitii pe raspunsurile sanatoase.
#
# `/checkpoint/` — markerul evident, si GRESIT — a fost RESPINS: apare in tabelele de
# rute din JS-ul unei pagini de marketplace perfect sanatoase (masurat pe
# fb_ssr_search.html si fb_ssr_categorie.html). Folosit ca detector, ar fi declarat
# sesiunea moarta la PRIMA cerere a oricarui scan autentificat. Acelasi lucru pentru
# `/checkpoint/block`. De-aia markerii de mai jos sunt mai lungi si mai specifici.
#
# Ce NU avem: o mostra reala de pagina de checkpoint — 23 de cereri autentificate,
# zero checkpoint-uri. Deci lista e validata NEGATIV (nu da fals pozitiv pe nimic
# cunoscut-bun), nu POZITIV. Prima mostra reala trebuie sa o confirme.
_MARKERI_CHECKPOINT = ('"checkpoint"', "/checkpoint/?next", "checkpoint_flow",
                       "CheckpointBlock")


def _are_checkpoint(corp: str) -> bool:
    return any(m in (corp or "") for m in _MARKERI_CHECKPOINT)


def _injecteaza_sesiune(sesiune, cale: str) -> Optional[str]:
    """Cookie-urile Facebook dintr-un `storage_state` Playwright, in jar. Intoarce `c_user`.

    Regulile sunt cele MASURATE la FBS-0, nu inventate: se injecteaza doar cookie-uri
    de pe `.facebook.com` si doar NEexpirate. Sonda a sarit `wd` (expirat la
    2026-07-16) si `_GRECAPTCHA` (domeniu google.com) — un cookie expirat trimis
    inapoi e zgomot care poate declansa exact reactia pe care vrem s-o evitam.

    NU arunca niciodata: fisier lipsa, JSON corupt sau alta forma inseamna DEGRADARE
    la jar gol, adica exact calea logat-out, nu prabusirea unui scan intreg.
    """
    try:
        brut = json.loads(Path(cale).read_text(encoding="utf-8"))
        cookieuri = brut.get("cookies")
        if not isinstance(cookieuri, list):
            raise ValueError("lipseste lista 'cookies'")
    except Exception as exc:
        log_manager.emit("radar", "WARN",
            f"Facebook: sesiunea de la '{str(cale)[:80]}' nu s-a putut citi "
            f"({type(exc).__name__}) — se continua cu jar GOL, ca logat-out")
        return None

    c_user, puse, sarite = None, [], []
    for c in cookieuri:
        nume, domeniu = c.get("name"), (c.get("domain") or "")
        expira = c.get("expires")
        if "facebook.com" not in domeniu:
            sarite.append(f"{nume} (alt domeniu: {domeniu})")
            continue
        if isinstance(expira, (int, float)) and 0 < expira < time.time():
            sarite.append(f"{nume} (expirat)")
            continue
        try:
            sesiune.cookies.set(nume, c.get("value") or "", domain=domeniu,
                                path=c.get("path") or "/", secure=bool(c.get("secure")))
        except Exception:
            sarite.append(f"{nume} (nesetabil)")
            continue
        puse.append(nume)
        if nume == "c_user":
            c_user = str(c.get("value") or "") or None

    log_manager.emit("radar", "INFO",
        f"Facebook: sesiune incarcata, {len(puse)} cookie-uri injectate ({puse})"
        + (f"; sarite: {sarite}" if sarite else "")
        + ("" if c_user else " — ATENTIE: fara `c_user`, deci fara identitate"))
    return c_user


class FacebookClient:
    """Sesiune curl_cffi cu jar gol si pauze intre cereri.

    `sleep` e injectabil ca testele sa nu astepte real. Dupa un 403/429 clientul se
    ZAVORASTE (`_blocat`): orice cerere ulterioara din acelasi apel se refuza fara
    trafic. Fara zavor, scara de robustete ar continua sa coboare treptele si ar
    trimite inca 2-3 cereri exact catre serverul care tocmai ne-a limitat.
    """

    def __init__(self, *, sleep=time.sleep, sesiune_path: Optional[str] = None):
        self._sleep = sleep
        self._sesiune = curl_requests.Session(impersonate=impersonate_for("facebook"))
        self._sesiune.cookies.clear()        # jar GOL, explicit
        self._prima = True
        self._blocat = False
        self._sesiune_invalida = False
        self._santinela_ultima = False
        self._c_user = None
        # `sesiune_path` lipsa = EXACT comportamentul de dinainte de FBS-1, cu tot cu
        # jar gol. Injectia se face DUPA `clear()`, deliberat: golirea ramane regula,
        # iar sesiunea e o exceptie ceruta explicit de apelant.
        if sesiune_path:
            self._c_user = _injecteaza_sesiune(self._sesiune, sesiune_path)

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
            corp = r.text or ""
            self._inspecteaza(corp, url)
            if status in (403, 429):
                self._blocheaza(status, url)
                return corp, status
            if 500 <= status < 600 and incercare < _MAX_RETRY:
                self._sleep(rate_limit_backoff(incercare))
                continue
            return corp, status
        return "", None

    def _inspecteaza(self, corp: str, url: str) -> None:
        """Semnalele care se citesc din CORP, nu din status. Un singur loc, fiindca
        `_cere` e gatuirea prin care trec TOATE cererile — bootstrap, GraphQL si SSR
        deopotriva. Altfel fiecare treapta ar trebui sa-si faca propria verificare,
        iar `ssr.py` nici n-ar putea (calea aia intoarce obiecte, nu corp).
        """
        self._santinela_ultima = looks_like_no_results(corp)

        # Login-wall/checkpoint conteaza DOAR daca avem o sesiune de pierdut. Fara
        # `c_user`, calea logat-out primeste frecvent formularul de login in corp
        # (vezi `cauta_ssr`), iar acolo comportamentul de azi ramane neatins — D9.
        if not self._c_user or self._sesiune_invalida:
            return
        if looks_like_login_wall(corp) or _are_checkpoint(corp):
            self._sesiune_invalida = True
            log_manager.emit("radar", "WARN",
                f"Facebook: login-wall sau checkpoint cu sesiune atasata "
                f"({url[:70]}) — sesiunea e moarta, nu se mai insista pe trepte")

    @property
    def blocat(self) -> bool:
        """Zavorul de 403/429, expus public: e dovada DURA de refuz, iar executorul
        (FB-6a) trebuie sa poata deosebi „blocat" de „n-am gasit nimic"."""
        return self._blocat

    @property
    def sesiune_invalida(self) -> bool:
        """Login-wall sau checkpoint peste o sesiune atasata. Ramane False pe calea
        logat-out, oricat de multe formulare de login ar servi Facebook acolo."""
        return self._sesiune_invalida

    @property
    def santinela_ultima(self) -> bool:
        """Ultimul raspuns purta santinela de zero rezultate?"""
        return self._santinela_ultima

    @property
    def c_user(self) -> Optional[str]:
        """Identitatea contului din jar, sau None logat-out. `bootstrap.py` o
        citeste de aici ca sa cupleze cache-ul cu contul."""
        return self._c_user

    def get(self, url: str) -> tuple[str, Optional[int]]:
        return self._cere("get", url)

    def post(self, url: str, data=None, headers=None) -> tuple[str, Optional[int]]:
        return self._cere("post", url, data=data, headers=headers)


# Regimul se logheaza o SINGURA data per configuratie, nu la fiecare client: un
# `search` isi construieste clientul propriu, deci un log neconditionat ar scrie o
# linie pentru fiecare cerere din tick. Cheia include calea si daca s-a obtinut
# identitate, ca o reconectare din UI sa se vada imediat in jurnal.
_regim_logat = None


def _cale_sesiune() -> Optional[str]:
    """Calea sesiunii SCRAPERULUI, citita LA APEL, nu la import.

    Acelasi motiv ca la `_cale_cache()`: testele trebuie s-o poata redirecta, iar un
    build PyInstaller ar fixa-o la valoarea de la pornire.

    D10 — sesiunea scraperului e INFRASTRUCTURA, nu a unui utilizator. NU se
    foloseste `resolve_facebook_session_path(db, user_id)`: acela e per-utilizator si
    ramane pentru fluxul manual de conectare din UI. Executorul e un job global, iar
    varianta „ia prima sesiune valida de utilizator" ar fi pus scraperul sa lucreze
    TACUT pe contul personal al cuiva. Contul lucrator e separat, prin configuratie.

    GARDA E CHIAR ABSENTA CAII: nesetata sau fisier inexistent inseamna exact
    comportamentul de azi, cu jar gol. Un singur buton, fara a doua setare care sa
    intre in conflict.
    """
    cale = (os.getenv("FB_SESIUNE_PATH") or "").strip()
    if not cale:
        return None
    return cale if Path(cale).is_file() else None


def _logheaza_regim(cale: Optional[str], c_user: Optional[str]) -> None:
    global _regim_logat
    cheie = (cale, bool(c_user))
    if _regim_logat == cheie:
        return
    _regim_logat = cheie
    if not cale:
        log_manager.emit("radar", "INFO",
            "Facebook: regim LOGAT-OUT (FB_SESIUNE_PATH nesetata sau fisier "
            "inexistent) — jar gol, exact calea de dinainte de FBS-1")
    elif c_user:
        log_manager.emit("radar", "INFO",
            f"Facebook: regim AUTENTIFICAT pe sesiunea '{cale[:80]}'")
    else:
        log_manager.emit("radar", "WARN",
            f"Facebook: sesiunea '{cale[:80]}' s-a citit dar NU are `c_user` — "
            f"regimul ramane logat-out. Un scraper care se crede autentificat si nu "
            f"e trebuie sa se vada in jurnal, nu sa fie dedus din rezultate")


def _client_implicit() -> FacebookClient:
    cale = _cale_sesiune()
    cl = FacebookClient(sesiune_path=cale)
    _logheaza_regim(cale, cl.c_user)
    return cl


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


COD_REFUZ_ACCES = 1675004      # "Rate limit exceeded", masurat la FB-4a pe browse


@dataclass(frozen=True)
class StareCautare:
    """Ce s-a intamplat la o cautare, nu doar ce a gasit.

    `search` intoarce doar lista, deci un rezultat gol e ambiguu: loc chiar gol,
    sablon invechit sau refuz de acces? Executorul (FB-6a) trebuie sa deosebeasca —
    la `blocat` opreste tot tick-ul, la `gol` merge mai departe linistit.
    """
    # FBS-1 a adaugat `sesiune_invalida`: login-wall/checkpoint peste o sesiune
    # atasata, sau identitate respinsa de DOUA ori (1357004). E deliberat separata
    # de `blocat` — un 403 se asteapta, o sesiune moarta se reautentifica.
    eticheta: str                  # ok | gol | blocat | esec | sesiune_invalida
    cod: Optional[int] = None      # codul de resolver, daca a existat
    trepte_incercate: int = 0
    # FBS-1b — `gol` are DOUA intelesuri de cand exista santinela, si detectorul de
    # anomalie are nevoie sa le deosebeasca: „Facebook a spus explicit zero" (sanatos)
    # fata de „n-am obtinut nimic si nu stiu de ce" (suspect). Fara steagul asta, o
    # noapte linistita si o sesiune moarta arata identic.
    zero_confirmat: bool = False


def _varsta_max_ore() -> float:
    try:
        return float(os.getenv("FB_VARSTA_MAX_ORE") or _VARSTA_MAX_IMPLICIT_ORE)
    except (TypeError, ValueError):
        return _VARSTA_MAX_IMPLICIT_ORE


def _search_intern(query: str, lat: float, lon: float, *, raza_km: float = 65,
                   city_page_id: Optional[str] = None,
                   pret_min: Optional[int] = None,
                   pret_max: Optional[int] = None,
                   client: Optional[FacebookClient] = None) -> tuple:
    """Scara de robustete, cu verdict. Intoarce (canonice, StareCautare)."""
    cl = client if client is not None else _client_implicit()
    cod = None
    trepte = 0

    def _verdict(lista, eticheta_reusita, *, zero_confirmat=False):
        """`zero_confirmat` se propaga DOAR cand verdictul chiar e `gol`: pe un „ok"
        n-are inteles, iar un „blocat" nu e un zero explicat, e un refuz.

        FBS-14, D3: un gol produs de FILTRUL de varsta pe treptele degradate NU e
        `zero_confirmat` — serverul n-a confirmat niciun zero, noi am taiat. Apelantii
        de acolo nu paseaza steagul, deci implicitul `False` e chiar regula."""
        e = eticheta_reusita if lista else "gol"
        if _pare_blocat(cl, cod):
            e = "blocat"
        return lista, StareCautare(e, cod, trepte,
                                   zero_confirmat=zero_confirmat and e == "gol")

    def _oprit_de_sesiune():
        """Sesiunea moarta NU urca treptele: un re-bootstrap nu invie un cont."""
        return getattr(cl, "sesiune_invalida", False)

    def _santinela():
        """Facebook a spus explicit „zero rezultate" — raspuns valid, oprim aici."""
        return getattr(cl, "santinela_ultima", False)

    def _dupa_varsta_degradata(canonice):
        """Taierea de varsta pe treptele DEGRADATE (2-3), cu contoare SEPARATE.

        FBS-14 — pana aici filtrul se aplica doar treptei 1, deci o degradare la
        GraphQL intorcea anunturi NESORTATE si de ORICE varsta, care in aval aratau ca
        oricare altele. Garantia devine uniforma: nimic DATAT peste prag nu iese din
        nucleu, indiferent de treapta. Pragul e ACELASI (`_varsta_max_ore`), citit din
        aceeasi sursa ca la treapta 1 — doua praguri ar fi doua adevaruri.

        Nedatatele se PASTREAZA (regula lui `filtreaza_dupa_varsta`: „nu stiu varsta"
        nu inseamna „vechi"), si tocmai de-aia se numara SEPARAT de cele taiate.
        Acoperirea lui `listed_at` e masurata 100% doar pe SSR; pe GraphQL e
        NEMASURATA. Contoarele astea sunt instrumentul care va spune, la prima
        degradare reala, daca filtrul chiar musca sau doar exista — si deci daca
        marcarea treptei in bazin (varianta B din audit) trebuie redeschisa.

        UN emit per apel, si numai daca are ce raporta.
        """
        ore = _varsta_max_ore()
        proaspete = filtreaza_dupa_varsta(canonice, ore)
        taiate = len(canonice) - len(proaspete)
        nedatate = sum(1 for c in proaspete if c.get("listed_at") is None)
        if taiate or nedatate:
            log_manager.emit("radar", "INFO",
                f"Facebook GraphQL (treapta {trepte}): {taiate} din {len(canonice)} "
                f"anunturi peste pragul de {ore:g} h, {nedatate} fara data pastrate")
        return proaspete

    # ── treapta 1: SSR pe `city_page_id` — calea FIERBINTE de la FBS-2 ───────
    # Ancorele fara ID sar treapta asta si incep de la GraphQL, exact ca inainte.
    if city_page_id:
        trepte = 1
        brute = cauta_ssr(cl, city_page_id, query, pret_min=pret_min,
                          pret_max=pret_max)
        if _oprit_de_sesiune():
            return [], StareCautare("sesiune_invalida", cod, trepte)
        if brute:
            # Calea a FUNCTIONAT. Filtrul local de varsta se aplica si aici, si pe
            # treptele degradate (FBS-14) — dar din motive DIFERITE, si de-aia codul e
            # separat: aici recenta s-a cerut SI serverului (`daysSinceListed=1`), iar
            # filtrul doar strange fereastra lui, care e de ~38 h, nu 24; pe 2-3 nu s-a
            # cerut nimanui nimic, deci filtrul e singura garantie. Difera si verdictul
            # la gol — vezi `_dupa_varsta_degradata`. Daca filtrul goleste rezultatul, NU se
            # cade la GraphQL: caderea e pentru esec de transport, nu pentru un
            # verdict de filtru — altfel am inlocui „nimic proaspat aici" cu un teanc
            # de anunturi vechi de saptamani, si am plati si cereri pentru el.
            canonice = _canonice(brute)
            proaspete = filtreaza_dupa_varsta(canonice, _varsta_max_ore())
            if len(proaspete) != len(canonice):
                log_manager.emit("radar", "INFO",
                    f"Facebook SSR '{city_page_id}': {len(canonice) - len(proaspete)} "
                    f"din {len(canonice)} anunturi peste pragul de "
                    f"{_varsta_max_ore():g} h — fereastra serverului e mai larga")
            # `zero_confirmat` si cand filtrul a golit: e cel mai bine explicat gol
            # posibil — transportul a REUSIT si avem dovada POZITIVA a ce a venit
            # (anunturi reale, doar prea vechi), spre deosebire de santinela, unde
            # avem doar cuvantul serverului. Fara steag, detectorul de anomalie din
            # FBS-1b ar numara drept tick suspect exact zonele linistite si ar
            # strange frana degeaba.
            return _verdict(proaspete, "ok", zero_confirmat=True)
        if _santinela():
            # Zero CONFIRMAT: nu se mai cheltuie cererile GraphQL. Fara asta,
            # inversarea ar adauga o cerere per cautare pe toate zonele linistite —
            # si alea sunt majoritatea (randament masurat: 1-6 anunturi per oras).
            return [], StareCautare("gol", cod, trepte, zero_confirmat=True)
        log_manager.emit("radar", "WARN",
            f"Facebook treapta 1->2: SSR pe locatia '{city_page_id}' n-a intors "
            f"anunturi si nici santinela — esec ambiguu, incerc GraphQL")

    # ── treapta 2: GraphQL cu bootstrap din cache ────────────────────────────
    # FBS-6/FBS-10, D3: nici `pret_min`, nici `pret_max` NU se trimit pe GraphQL —
    # degradarea intoarce feed NEFILTRAT, iar filtrele locale ale apelantilor raman
    # plasa de siguranta.
    trepte = 2
    boot = incarca_sau_bootstrapeaza(cl)
    obiecte = None
    cod_ultim = None
    if boot is not None:
        variabile = muta(boot.variables, query=query, lat=lat, lon=lon, raza_km=raza_km)
        if variabile is not None:
            raspuns, cod_nou = cauta_cu_cod(cl, boot, variabile,
                                            identitate=identitate_din(boot))
            cod_ultim = cod_nou
            cod = cod_nou if cod_nou is not None else cod
            obiecte = _obiecte_sau_none(raspuns)
    if _oprit_de_sesiune():
        return [], StareCautare("sesiune_invalida", cod, trepte)
    if _santinela():
        return [], StareCautare("gol", cod, trepte, zero_confirmat=True)
    if obiecte is not None:
        return _verdict(_dupa_varsta_degradata(_canonice(obiecte)), "ok")

    # ── treapta 2: sablon invechit -> re-bootstrap fortat, O SINGURA DATA ─────
    trepte = 3
    log_manager.emit("radar", "WARN",
        "Facebook treapta 2->3: GraphQL cu sablonul din cache a esuat, "
        "reimprospatez bootstrap-ul si reincerc")
    invalideaza()
    boot = incarca_sau_bootstrapeaza(cl, forteaza=True)
    if boot is not None:
        variabile = muta(boot.variables, query=query, lat=lat, lon=lon, raza_km=raza_km)
        if variabile is not None:
            raspuns, cod_nou = cauta_cu_cod(cl, boot, variabile,
                                            identitate=identitate_din(boot))
            cod_ultim = cod_nou
            cod = cod_nou if cod_nou is not None else cod
            obiecte = _obiecte_sau_none(raspuns)
    if _oprit_de_sesiune():
        return [], StareCautare("sesiune_invalida", cod, trepte)
    if cod_ultim == COD_IDENTITATE_INVALIDA:
        # A DOUA respingere a aceleiasi identitati, de data asta cu jeton proaspat.
        # Nu e blocaj (nu ni s-a refuzat accesul) si nu mai e sablon invechit — e
        # sesiune moarta, si cere alta reactie la FBS-1b decat un 403.
        log_manager.emit("radar", "WARN",
            "Facebook: identitatea a fost respinsa si dupa re-bootstrap (1357004) — "
            "sesiune invalida, nu blocaj; scara se opreste aici")
        return [], StareCautare("sesiune_invalida", cod, trepte)
    if _santinela():
        return [], StareCautare("gol", cod, trepte, zero_confirmat=True)
    if obiecte is not None:
        return _verdict(_dupa_varsta_degradata(_canonice(obiecte)), "ok")

    motiv = ("nici SSR pe ID, nici GraphQL n-au intors anunturi" if city_page_id
             else "ancora n-are `city_page_id`, iar GraphQL a esuat pe ambele trepte")

    # ── treapta 4: nimic ─────────────────────────────────────────────────────
    trepte = 4
    log_manager.emit("radar", "WARN",
        f"Facebook treapta 3->4: {motiv} — nicio cale nu a functionat")
    if _oprit_de_sesiune():
        return [], StareCautare("sesiune_invalida", cod, trepte)
    report_outcome("facebook", Outcome.BLOCKED)
    return [], StareCautare("blocat" if _pare_blocat(cl, cod) else "esec", cod, trepte)


def _pare_blocat(cl, cod) -> bool:
    """Dovada DURA de refuz: zavorul de 403/429 sau codul de refuz de acces.

    Un sablon invechit (1675012) NU intra aici — acela se repara singur la treapta 2.
    """
    return bool(getattr(cl, "blocat", False)) or cod == COD_REFUZ_ACCES


def search(query: str, lat: float, lon: float, *, raza_km: float = 65,
           city_page_id: Optional[str] = None,
           pret_min: Optional[int] = None,
           pret_max: Optional[int] = None,
           client: Optional[FacebookClient] = None) -> list[dict]:
    """Anunturi CANONICE pentru o ancora geografica. Lista goala = nimic obtinut.

    `client` e o cusatura de test (injecteaza un dublu cu get/post); in productie
    ramane None si se creeaza unul implicit.

    FBS-2: `fb_slug` a fost INLOCUIT cu `city_page_id`. Parametrii sunt keyword-only,
    deci un apel vechi cu `fb_slug=` ridica TypeError — zgomotos, nu tacut. Alegerea
    e deliberata: un slug acceptat si ignorat ar ancora in alt oras fara niciun semnal.

    `pret_min` (FBS-6) si `pret_max` (FBS-10) pleaca SERVER-SIDE, dar numai pe
    treapta 1 — vezi `ssr.py` pentru masuratori si pentru rezerva de recall.
    """
    return _search_intern(query, lat, lon, raza_km=raza_km,
                          city_page_id=city_page_id, pret_min=pret_min,
                          pret_max=pret_max, client=client)[0]


def search_cu_stare(query: str, lat: float, lon: float, *, raza_km: float = 65,
                    city_page_id: Optional[str] = None,
                    pret_min: Optional[int] = None,
                    pret_max: Optional[int] = None,
                    client: Optional[FacebookClient] = None) -> tuple:
    """Ca `search`, dar intoarce (canonice, StareCautare)."""
    return _search_intern(query, lat, lon, raza_km=raza_km,
                          city_page_id=city_page_id, pret_min=pret_min,
                          pret_max=pret_max, client=client)
