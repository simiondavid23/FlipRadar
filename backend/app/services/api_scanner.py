"""VAL D — `api_enum`: a patra sursa a feed-ului de deal-uri, API de catalog VTEX.

Primele trei surse citesc HTML sau `/products.json`. Asta citeste un API de
catalog PUBLIC, paginat, cu totaluri publicate — deci poate enumera un catalog
intreg (f64.ro: ~52.500 de produse) fara sa ghiceasca nimic despre randare.

Fiecare mecanism de mai jos e MASURAT in sondele VTX-1/1b/1c/2, VTX-3 si VTX-4, pe
dump-uri reale (`scripts/diagnostics/dumps_vtx1*/`, `dumps_vtx3/`, `dumps_vtx4/`).
Sase fapte au format designul si nu sunt negociabile:

  * FEREASTRA E DE 50 DE ELEMENTE, nu de 50 la valoarea lui `_to`. Mesajul de
    eroare („Parameter _to can't be greater than 50.") induce in eroare: VTX-3 a
    cerut `_from=2450&_to=2500` (51 de elemente) si a primit 400, apoi
    `_from=2450&_to=2499` (50) si a primit 206 cu fix 50 de produse. Un `_to` de
    2499 trece, deci plafonul e pe NUMAR, nu pe valoare.
  * 2xx INCLUDE SI 206, SI 200. Un segment plin raspunde 206 Partial Content; unul
    gol raspunde 200 cu `[]` (VTX-3, C3). O garda pe `== 200` inchide API-ul (a
    fost greseala primei treceri VTX); una pe `== 206` pierde segmentele goale.
  * TOTALURILE DIN `resources` SUNT ORIENTATIVE. Masurat: 52.930 -> 52.629 ->
    52.542 in patru zile, iar in fata sta CloudFront cu `s-maxage=300`. De aceea
    NICIO conditie de oprire nu se sprijina pe egalitatea cu totalul: un segment
    se inchide pe FEREASTRA GOALA sau pe `_from > 2500`, atat.
  * ENUMERAREA LINIARA ACOPERA ~2.550. `_from` nu poate depasi 2.500 (masurat:
    2540 -> 400), deci un segment mai mare CERE segmentare. De aici descenderea
    adaptiva: recensamant ieftin (o cerere, `_from=0&_to=0`, se citeste doar
    headerul), apoi liniar sub prag, copii de nivel 2 peste el, benzi de pret la
    frunzele care tot depasesc.
  * SEGMENTAREA PE CATEGORII CERE CALEA, NU ID-UL. `fq=C:1000027` intoarce ZERO;
    `fq=C:1000000/1000027` intoarce 2.217 (VTX-4). Runda 3 a presupus id-ul gol si
    a pierdut 24.420 de produse din 4 categorii, acoperind 3,8% din catalog.
    Forma canonica o publica API-ul in fiecare produs si era in dump-uri de la
    inceput: `categoriesIds: ["/1000003/1000067/1000228/", "/1000003/1000067/",
    "/1000003/"]`. De aceea descenderea transporta calea acumulata, iar `/` NU se
    procent-codeaza. Corolar masurat: un produs apartine mai multor cai simultan,
    deci totalurile copiilor NU se aduna si nu se reconciliaza cu parintele.
  * PRETUL 0 NU E O OFERTA, si pe f64 e o masa uriasa. Segmentul EOL are 20.766
    de produse din 20.779 cu pretul indexat 0 (masurat VTX/3g: `fq=P:[0 TO 0]`
    intoarce 20.766, iar benzile insumeaza exact totalul segmentului). Ele n-au ce
    cauta in feed — `_extrage_produse` le-ar sari oricum pe `Price <= 0` — dar
    taierea binara pe pret converge la banda degenerata `[0 TO 0]`, fiindca toate
    impart acelasi punct. De aceea banda aia se RECENSEAZA si NU se enumereaza:
    cifra ei explica reziduul de acoperire, in loc sa fie cheltuita in ~415 de
    ferestre care n-ar ingera nimic. Corolar: acoperirea unui domeniu se citeste
    fata de catalogul CU PRET, nu fata de recensamantul nefiltrat.
  * COMBINATIA `fq=C:` + `fq=P:` E NEMASURATA. `fq=P:[100 TO 200]` singur a fost
    validat la VTX-3 (206, 1.894 din 52.542, si 10/10 produse chiar in banda), dar
    impreuna cu `fq=C:` nu a fost incercat niciodata. Prima folosire o VERIFICA
    (status + total diferit de al parintelui) si, daca pica, domeniul trece pe
    rezerva descrisa la `_enumereaza_frunza` — fara sa opreasca scanul.

ARTICOLELE-TAXA SE INGEREAZA DELIBERAT (decizie de runda, reversibila). Segmentul
EOL contine si intrari care nu sunt marfa — masurat: „Taxa livrare si ambalare S1",
`Price == ListPrice == 49.99`. Nu se filtreaza, din doua motive: sunt INERTE pentru
feed (pret egal cu referinta inseamna ca R1 n-are ce califica, iar pretul lor e
stabil, deci nici R2), si orice filtru pe nume ar fi o regula INVENTATA, nu
masurata. Daca vreodata produc zgomot, aici e locul unde se taie.

Refoloseste `deal_scanner` si `listing_scanner` PRIN IMPORT, niciodata prin copie:
pragurile, evaluarea R1/R2, randul de stare si plafonul de alerte sunt o singura
implementare, partajata de toate cele patru surse.
"""
import json
import random
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from app.models.deal import Deal
from app.models.shop_price_memory import ShopPriceMemory
from app.services.log_manager import set_log_user
# Partajate DELIBERAT — vezi docstringul modulului.
from app.services.deal_scanner import _evalueaza, _prag, _scrie_stare, _settings
from app.services.listing_scanner import _e_primul_scan, _prag_r1
from app.services.shop_registry import catalog_api_descriptor, catalog_api_domains

# Fereastra API: EXACT 50 de elemente (masurat VTX-3, vezi docstring).
_FEREASTRA = 50
# `_from` nu poate depasi 2.500 (masurat: 2540 -> 400).
_MAX_FROM = 2500
# Peste atata, un segment nu mai incape in enumerarea liniara si cere descindere.
# 2.500, nu 2.550: marginea ramane la scanner, nu la limita API-ului.
_PRAG_SEGMENT = 2500

# Cadenta JSON, ca la scannerul Shopify (`deal_scanner`), NU cea de 2,5s a
# paginilor HTML: raspunsurile astea sunt de ordinul sutelor de KB, nu de MB.
_PAUZA = 1.5
_JITTER = 0.6
_TIMEOUT = 30

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Lock PROPRIU, ca la celelalte doua scannere: cele trei parcurg multimi de
# domenii disjuncte, deci un lock comun ar serializa degeaba joburile.
_API_LOCK = threading.Lock()

# Anti-avalansa, per domeniu per scan — aceeasi valoare ca la DEAL-2.
_MAX_ALERTE = 10

# Plasa globala de cereri per scan. Aritmetica documentata: ~1.100-1.300 de cereri
# pentru catalogul intreg (52.500/50 = 1.050 minim, plus ferestrele partiale ale
# fiecarui segment si recensamintele). 1.600 lasa loc de crestere fara sa permita
# o bucla scapata sa cheltuie o noapte intreaga.
_MAX_CERERI = 1600

# Benzi de pret: cel mult atatea per frunza, si intervalul de plecare.
#
# 16, nu 8 (RUNDA 3e). Aritmetica o cere: EOL are 20.779 de produse si ZERO copii
# in arbore, deci benzile sunt singura lui segmentare — iar 8 x 2.500 = 20.000 nu
# l-ar fi acoperit nici in cazul ideal al unei impartiri perfect uniforme.
# 16 x 2.500 = 40.000 lasa marja si pentru cresterea catalogului.
#
# Ramane o alegere de BUGET, nu o masuratoare: o frunza care tot depaseste pragul
# la ultima banda se enumereaza partial si se CONSEMNEAZA, nu se reia la infinit.
_MAX_BENZI = 16
_PRET_MAX = 100000


# RUNDA 3c — comutator de DIAGNOSTIC, implicit OPRIT. Cand e True,
# `_scaneaza_domeniu` aduna contoare per segment/fereastra si returneaza `diag`.
# Nu atinge nicio decizie: aceleasi cereri, aceleasi randuri in baza.
DIAGNOSTIC = False


class _PlafonCereri(Exception):
    """Plasa globala atinsa. Se prinde in `_scaneaza_domeniu`, ca scanul sa se
    incheie ORDONAT (stare `error` + log), nu cu o exceptie scapata in job."""


def is_api_scan_running() -> bool:
    """True cat timp o scanare de API tine lock-ul. Consultat de endpointul manual
    ca sa raspunda 409 in loc sa porneasca un thread care oricum ar iesi imediat."""
    return _API_LOCK.locked()


def _pauza() -> None:
    time.sleep(_PAUZA + random.uniform(0, _JITTER))


def _fereastra(de_la: int) -> int:
    """`_to` pentru o fereastra care incepe la `de_la`: EXACT 50 de elemente.

    `de_la + 49`, nu `de_la + 50`: indicii sunt inclusivi la ambele capete, iar
    VTX-3 a masurat ca 51 de elemente dau 400.
    """
    return de_la + _FEREASTRA - 1


def _e_2xx(status) -> bool:
    """Orice 2xx, fiindca API-ul foloseste DOUA: 206 pe segment plin, 200 pe gol."""
    try:
        return int(status) // 100 == 2
    except (TypeError, ValueError):
        return False


def _e_5xx(status) -> bool:
    """Eroare de server: singura clasa care merita o reincercare."""
    try:
        return int(status) // 100 == 5
    except (TypeError, ValueError):
        return False


def _parse_resources(brut):
    """`"2450-2499/52542"` -> `(2450, 2499, 52542)`, altfel None.

    Tolerant DELIBERAT: totalul e orientativ, deci un header lipsa sau stricat nu
    are voie sa rupa scanul — apelantii trateaza None ca „nu stiu cat e".
    """
    if not isinstance(brut, str):
        return None
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*/\s*(\d+)\s*", brut)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _external_id(product_id) -> str:
    """`api:` + productId. `productId` e stabil si unic in VTEX, iar prefixul tine
    sursa asta separata de `lst:` (listari) in acelasi tabel."""
    return "api:" + str(product_id)


def _extrage_produse(payload, domain: str, contoare=None,
                     observator=None) -> list[dict]:
    """Un raspuns de catalog -> lista de produse. Public: testele il conduc direct
    pe raspunsurile reale din dump-urile VTX.

    Pretul platit e `Price`; referinta e `ListPrice`, dar DOAR cand e strict peste
    `Price`. Pe f64 cele doua sunt egale pe majoritatea catalogului (masurat: doar
    ~10% au `ListPrice > Price`), iar scrise ca referinta ar da o reducere de 0%
    peste tot. Semantica lui `ListPrice` e de PRP, deci pragul lui R1 e cel de
    listare, nu cel global — vezi `reference_kind: "prp"` din registru.

    RUNDA 3c — `contoare` si `observator` sunt canale de DIAGNOSTIC, amandoua
    optionale si amandoua strict de SCRIERE catre apelant: cand lipsesc (cazul
    productiei si al testelor), functia se comporta identic. `contoare` numara
    motivele de saritura; `observator` primeste `(productId, categoriesIds)` pentru
    FIECARE produs din payload, sarit sau nu. Niciunul nu schimba ce se cere, ce se
    intoarce sau ce se scrie in baza.
    """
    if not isinstance(payload, list):
        return []

    def _numara(motiv):
        if contoare is not None:
            contoare[motiv] = contoare.get(motiv, 0) + 1

    iesire = []
    for produs in payload:
        if not isinstance(produs, dict):
            _numara("alt")
            continue
        if observator is not None:
            observator(produs.get("productId"), produs.get("categoriesIds"))
        if not (produs.get("categoriesIds") or []):
            _numara("fara_categorie")     # OBSERVATIE, nu saritura
        oferta = _prima_oferta(produs)
        if oferta is None:
            _numara("fara_oferta")
            continue
        pret = oferta.get("Price")
        if not isinstance(pret, (int, float)) or pret <= 0:
            _numara("fara_pret")
            continue                      # fara pret valid nu se ghiceste nimic
        # DECIZIA RUNDEI, reversibila: un produs indisponibil nu e chilipir, deci
        # nu intra nici in deal-uri, nici in memoria de pret — altfel minimul
        # istoric s-ar polua cu preturi necumparabile. Acelasi rationament ca
        # `_in_stoc` la DEAL-2. In dump-urile VTX nu exista niciun produs cu
        # `IsAvailable=False`, deci ramura e implementata pe contract, nu pe
        # observatie: daca se dovedeste gresita, se scoate de aici.
        if oferta.get("IsAvailable") is False:
            _numara("indisponibil")
            continue

        referinta = oferta.get("ListPrice")
        if not isinstance(referinta, (int, float)) or referinta <= pret:
            referinta = None

        iesire.append({
            "external_id": _external_id(produs.get("productId")),
            "title": (produs.get("productName") or "")[:500],
            "url": produs.get("link") or f"https://{domain}/",
            "handle": urllib.parse.urlsplit(produs.get("link") or "").path[:255],
            "price": float(pret),
            "compare_at": float(referinta) if referinta is not None else None,
        })
    return iesire


def _prima_oferta(produs: dict):
    """`items[].sellers[].commertialOffer` — prima oferta gasita.

    „Prima", nu „cea mai buna": VTX-2 a masurat UN SINGUR seller pe toate cele 10
    produse ale lotului, deci f64 nu e marketplace si nu exista intre ce alege.
    Daca asta se schimba, aici e locul.
    """
    for item in produs.get("items") or []:
        for seller in item.get("sellers") or []:
            oferta = seller.get("commertialOffer")
            if isinstance(oferta, dict):
                return oferta
    return None


# ── arborele si descenderea ─────────────────────────────────────────────────

def _radacini_utile(arbore, excluse) -> list[dict]:
    """Nodurile de nivel 1 fara categoriile ne-catalog.

    Cele 7 nume sunt in registru, nu aici: sunt date despre magazin, nu despre
    algoritm. Masurat: 41 de radacini, 34 raman dupa excluderi.
    """
    fara = {str(n).strip().lower() for n in (excluse or [])}
    return [nod for nod in (arbore or [])
            if isinstance(nod, dict)
            and str(nod.get("name") or "").strip().lower() not in fara]


def _are_nevoie_de_descindere(total) -> bool:
    """Peste prag, enumerarea liniara n-ar acoperi segmentul (`_from <= 2500`).

    Un total NECUNOSCUT (`None`, header stricat) se trateaza ca „incape": costa cel
    mult o enumerare liniara degeaba, pe cand presupunerea inversa ar declansa o
    descindere completa pe un segment poate minuscul.
    """
    if total is None:
        return False
    return total > _PRAG_SEGMENT


# Marcaj pentru „inca nerecenzat", ca `None` sa poata insemna EXCLUSIV
# „recensamant picat" (D8) — altfel cele doua s-ar confunda in coada.
_NERECENZAT = object()


class _BenziIndisponibile(Exception):
    """Semnal intern: combinatia `fq=C` + `fq=P` nu tine pe domeniul asta.

    Ridicata de `_benzi_de_pret` cand o TAIETURA arata ca al doilea `fq` e ignorat
    (vezi D6). Prinsa in `enumereaza_frunza`, care trece pe enumerare liniara.
    """


def _benzi_de_pret(recensamant, maxim: int = _MAX_BENZI, sus: int = _PRET_MAX,
                   total_parinte=None, partiale=None):
    """Taie `[0, sus]` in benzi de pret sub prag, prin injumatatire binara.

    `recensamant(a, b)` intoarce totalul benzii (sau None). Se imparte NUMAI banda
    care depaseste pragul, deci taieturile se aduna acolo unde e densitatea —
    la f64, in zona de sub cateva sute de lei. Fiecare banda se recenseaza EXACT
    o data: totalul calculat la taiere calatoreste cu ea in coada.

    D6 (runda 3f) — DETECTAREA FILTRULUI MORT se face pe TAIETURA, nu pe banda.
    Versiunea de la runda 3 declara `fq=P` ignorat cand o banda intorcea totalul
    parintelui, si a gresit live: tot segmentul EOL e sub 50.000 RON, deci banda
    `[0 TO 50000]` chiar continea toate cele 20.779 de produse — masurat, verbatim:
        206  resources=0-0/20779  ...&fq=C:1000013&fq=P:[0 TO 50000]
    Fallback-ul declansat asa a plafonat segmentul la 2.550 si a pierdut 18.231 de
    produse (34,7% din catalog). Criteriul corect: un produs nu poate sta in DOUA
    benzi disjuncte, deci daca AMBELE jumatati intorc totalul parintelui, al doilea
    `fq` chiar e ignorat. Una plina si una goala inseamna filtru VIU.

    D7 (runda 3f) — o banda GOALA se arunca si NU consuma din buget. Altfel
    jumatatile moarte ale unui catalog inghesuit mananca plafonul, iar banda cu
    marfa ramane prea larga ca sa incapa in enumerarea liniara.

    D8 (runda 3g) — o banda al carei recensamant NU raspunde (`None`: 5xx epuizat
    sau zid clasificat) se pastreaza ca banda FINALA si se raporteaza in `partiale`.
    Nu se mai taie — n-avem cifra pe care sa decidem taierea — dar nici nu opreste
    restul: surorile ei continua normal. Apelantul o enumereaza cat poate.

    Bugetul de `maxim` benzi ramane o limita DURA: cand se atinge, ce a mai ramas
    in coada devine banda finala asa cum e. O banda finala poate deci sa fie inca
    peste prag; apelantul o enumereaza partial si o consemneaza.
    """
    finale: list[tuple[int, int]] = []
    # Fiecare intrare e (interval, total_cunoscut) — `None` inseamna nerecenzat.
    coada: list[tuple[tuple[int, int], object]] = [((0, sus), _NERECENZAT)]

    while coada:
        (a, b), total = coada.pop(0)
        if len(finale) + len(coada) + 1 >= maxim or a >= b:
            finale.append((a, b))
            finale.extend(interval for interval, _ in coada)
            break
        if total is _NERECENZAT:
            total = recensamant(a, b)
        if total is None:
            finale.append((a, b))         # D8: nemasurabila, dar nu se pierde
            if partiale is not None:
                partiale.append((a, b))
            continue
        if total == 0:
            continue                      # D7: goala — nici in rezultat, nici in buget
        if not _are_nevoie_de_descindere(total):
            finale.append((a, b))
            continue

        mijloc = (a + b) // 2
        stanga, dreapta = (a, mijloc), (mijloc + 1, b)
        t_stanga = recensamant(*stanga)
        t_dreapta = recensamant(*dreapta)

        if (total_parinte is not None and t_stanga is not None
                and t_dreapta is not None and t_stanga == total_parinte
                and t_dreapta == total_parinte):
            raise _BenziIndisponibile(
                "fq=P ignorat: ambele jumatati ale [%d, %d] dau %s"
                % (a, b, total_parinte))

        for interval, t in ((stanga, t_stanga), (dreapta, t_dreapta)):
            if t == 0:
                continue                  # D7
            if t is None:
                finale.append(interval)   # D8: nemasurabila, dar nu se pierde
                if partiale is not None:
                    partiale.append(interval)
                continue
            coada.append((interval, t))

    return finale


# ── scanul ──────────────────────────────────────────────────────────────────

def _scaneaza_domeniu(db, domain: str, settings, prag: float) -> dict:
    """Enumereaza catalogul unui domeniu prin API. Ridica `_PlafonCereri` daca se
    atinge plasa globala; apelantul o scrie in ShopScanState si incheie ordonat."""
    from app.services.discord_service import send_deal_notification
    from app.services.scraper_service import _fetch_shop_url_guarded

    descriptor = catalog_api_descriptor(domain)
    if not descriptor:
        raise RuntimeError(f"{domain} nu are descriptor de API de catalog")

    moneda = descriptor.get("currency")
    # Baza din descriptor, nu din cheia de registru: cheia e `f64.ro`, dar API-ul
    # raspunde pe `www.f64.ro` — vezi comentariul din registru.
    baza = descriptor.get("base") or f"https://{domain}"
    acum = datetime.now(timezone.utc)
    primul_scan = _e_primul_scan(db, domain)
    prag_r1 = _prag_r1(settings)

    stare = {"cereri": 0}
    vazute: set[str] = set()
    calificate: set[str] = set()
    produse_vazute = 0
    alerte = 0
    # DEAL-SCAN-2 — deal-urile noi ale ferestrei curente, in asteptarea commit-ului.
    # Lista se MUTEAZA pe loc (append/clear), niciodata nu se re-leaga, deci `inghite`
    # o vede fara `nonlocal`.
    de_notificat: list[Deal] = []
    jurnal = {"liniare": 0, "descinse": 0, "cu_benzi": 0, "fallback": 0,
              "partiale": 0, "benzi_indisponibile": False,
              "retry_5xx": 0, "abandonate_5xx": 0,
              "retry_transport": 0, "benzi_partiale": 0,
              "pret_zero_neenumerat": 0}
    # RUNDA 3c — diagnostic PUR. Nu intra in nicio decizie: nici ce se cere, nici
    # ce se scrie. `diag["activ"]` ramane False daca nimeni nu-l porneste.
    diag = {"activ": bool(DIAGNOSTIC), "segmente": [], "primul_segment": {},
            "radacini": {}, "sarite": {}}
    _diag_curent = {"seg": None}

    def cere(cale: str, **param):
        """O cerere prin poarta de productie, cu O reincercare pe 5xx.

        `/` ramane NEESCAPAT in `fq`: caile de categorie sunt `C:1000000/1000027`,
        exact forma masurata la VTX-4. Procent-codarea lui n-a fost incercata
        niciodata, deci nu se presupune ca merge.
        """
        bucati = []
        for cheie, valoare in param.items():
            if cheie == "fq":
                for unul in (valoare if isinstance(valoare, list) else [valoare]):
                    bucati.append("fq=" + urllib.parse.quote(str(unul), safe=":[]/"))
            else:
                bucati.append(f"{cheie}={valoare}")
        url = baza + cale + ("?" + "&".join(bucati) if bucati else "")

        # AMENDAMENT 3b, extins la 3g — ESECURI DE TRANSPORT, reincercate o data.
        #
        # Doua forme, tratate la fel fiindca sunt la fel de tranzitorii:
        #   * 5xx — runda 3 a incasat 4 pe cereri obisnuite, VTX-4 unul pe
        #     combinatia C+P („Erro ao realizar uma busca:"), iar 3f zece pe cinci
        #     URL-uri distincte, patru dintre ele ferestre fara `fq=P` deloc;
        #   * `raspuns is None` — de la AMZ-1a incoace, poarta intoarce None SI pe
        #     zid anti-bot clasificat, nu doar pe eroare de retea. Verbatim din
        #     `scraper_service`: „De ce blocajul intoarce None, adica EXACT forma de
        #     la eroarea de retea: valoarea de retur n-are camp de motiv". Cele doua
        #     sunt deci NEDISTINCTIBILE aici, si nici nu trebuie distinse: ambele
        #     inseamna „cererea asta n-a adus date", adica exact cazul in care o
        #     reincercare e ieftina si o degradare locala e raspunsul corect.
        #
        # Ce NU are voie sa se intample: un transport picat sa fie citit ca
        # „fereastra goala" (ar inchide segmentul declarandu-l terminat) sau ca
        # eroare de scan (ar pica tot domeniul).
        raspuns = None
        for incercare in (1, 2):
            if stare["cereri"] >= _MAX_CERERI:
                raise _PlafonCereri(
                    f"plasa globala de {_MAX_CERERI} cereri atinsa pe {domain}")
            if stare["cereri"]:
                _pauza()
            stare["cereri"] += 1
            raspuns = _fetch_shop_url_guarded(url, headers=_HEADERS,
                                              timeout=_TIMEOUT)
            status = getattr(raspuns, "status_code", None)
            if _e_2xx(status):
                break
            transport_picat = raspuns is None or _e_5xx(status)
            if incercare == 1 and transport_picat:
                jurnal["retry_transport"] += 1
                if _e_5xx(status):
                    jurnal["retry_5xx"] += 1
                continue
            if transport_picat:
                jurnal["abandonate_5xx"] += 1
            return None, None

        try:
            corp = json.loads(raspuns.text or "null")
        except (ValueError, TypeError, AttributeError):
            return None, None
        resurse = _parse_resources((getattr(raspuns, "headers", None) or {})
                                   .get("resources"))
        return corp, resurse

    def recensamant(**param):
        """Totalul unui segment, cu o singura cerere: fereastra minima, se citeste
        DOAR headerul. `_to=0` a fost masurat ca acceptat (VTX-3, C5-C7)."""
        _, resurse = cere(descriptor["endpoint"], _from=0, _to=0, **param)
        return resurse[2] if resurse else None

    def inghite(produse) -> None:
        """Produsele unei ferestre -> memorie de pret, evaluare, deal-uri."""
        nonlocal produse_vazute, alerte
        for produs in produse:
            external_id = produs["external_id"]
            # SCAN-1: un produs deja tratat in ACEST scan se sare. Aici conteaza
            # dublu — benzile `[a TO b]` se pot atinge la capete, iar acelasi
            # produs poate sta in doua categorii.
            if external_id in vazute:
                continue
            produse_vazute += 1
            vazute.add(external_id)

            memorie = (db.query(ShopPriceMemory)
                       .filter(ShopPriceMemory.shop_domain == domain,
                               ShopPriceMemory.external_id == external_id)
                       .first())
            if memorie is None:
                min_price_vechi = None
                db.add(ShopPriceMemory(
                    shop_domain=domain, external_id=external_id,
                    min_price=produs["price"], last_price=produs["price"],
                    last_seen_at=acum))
            else:
                min_price_vechi = memorie.min_price
                memorie.min_price = min(memorie.min_price, produs["price"])
                memorie.last_price = produs["price"]
                memorie.last_seen_at = acum

            discount_pct, reason = _evalueaza(
                produs["price"], produs["compare_at"], min_price_vechi, prag,
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
                    handle=produs["handle"], title=produs["title"],
                    url=produs["url"], image_url=None, currency=moneda,
                    price=produs["price"], compare_at_price=produs["compare_at"],
                    discount_pct=discount_pct, reason=reason, sizes_available=[],
                    min_price_seen=min_price_vechi, state="nou",
                    deal_source="api_enum", first_seen_at=acum, last_seen_at=acum)
                db.add(deal)
                db.flush()
                de_notificat.append(deal)
            else:
                # D7: starea apartine USERULUI, deci ramane neatinsa.
                deal.title = produs["title"]
                deal.url = produs["url"]
                deal.handle = produs["handle"]
                deal.price = produs["price"]
                deal.compare_at_price = produs["compare_at"]
                deal.discount_pct = discount_pct
                deal.reason = reason
                deal.min_price_seen = min_price_vechi
                deal.last_seen_at = acum

        # DEAL-SCAN-2 — commit la finalul FIECAREI ferestre, nu o data la finalul
        # descinderii. Tiparul reparat in DEAL-SCAN-1 pe ceilalti doi scanneri era
        # aici in forma cea mai grava: o descindere in arbore tine 33-48 de minute si
        # pana la 1.600 de cereri, deci lock-ul de scriere SQLite se tinea TOT acest
        # timp, iar busy_timeout-ul celorlalti scriitori (30s) expira de mult inainte.
        # Acum se tine cat o fereastra de 50 de produse — sub o secunda — si se
        # elibereaza inaintea urmatoarei cereri HTTP.
        #
        # Consecinta asumata: `db.rollback()`-ul din `run_api_scan` anuleaza acum doar
        # fereastra curenta, nu toata descinderea. E acceptabil, si chiar de dorit:
        # `_inchide_dealurile` ruleaza abia la final, pe `calificate`, deci un domeniu
        # picat la jumatate nu inchide nimic gresit, iar ce s-a scris pana atunci era
        # oricum corect. Inainte, un esec la a 1.500-a cerere arunca tot.
        db.commit()
        # Notificarea pleaca DOAR pentru randuri deja comise: altfel am putea anunta
        # un deal pe care un rollback ulterior l-ar face sa nu fi existat.
        #
        # Plafonul se verifica AICI, la trimitere, nu la `append`: in cursul ferestrei
        # `alerte` nu se mai incrementeaza, deci verificat la adaugare ar lasa o
        # fereastra intreaga sa treaca peste plafon. Acelasi tipar ca in
        # listing_scanner dupa DEAL-SCAN-1.
        for deal in de_notificat:
            if not primul_scan and alerte < _MAX_ALERTE:
                if send_deal_notification(deal, settings):
                    alerte += 1
        de_notificat.clear()

    def enumereaza(**param) -> int:
        """Parcurge liniar un segment. Intoarce cate ferestre a citit.

        Oprire: fereastra GOALA sau `_from > 2500`. NICIODATA pe egalitatea cu
        totalul din `resources` — vezi docstringul modulului.
        """
        eticheta = str(param.get("fq"))
        seg = {"fq": eticheta, "brut": 0, "noi": 0, "rep_in_segment": 0,
               "rep_alt_segment": 0, "ferestre": []}
        if diag["activ"]:
            diag["segmente"].append(seg)
            _diag_curent["seg"] = eticheta

        ferestre = 0
        de_la = 0
        while de_la <= _MAX_FROM:
            corp, _ = cere(descriptor["endpoint"], _from=de_la,
                           _to=_fereastra(de_la), **param)
            if corp is None:
                break                     # status neasteptat: segmentul se inchide
            contoare = diag["sarite"] if diag["activ"] else None
            observator = _observa if diag["activ"] else None
            produse = _extrage_produse(corp, domain, contoare, observator)
            if not corp:
                break                     # fereastra goala = finalul segmentului
            ferestre += 1
            if diag["activ"]:
                _masoara_fereastra(seg, de_la, produse, eticheta)
            inghite(produse)
            de_la += _FEREASTRA
        return ferestre

    def _observa(product_id, categorii):
        """Diagnostic: retine radacinile de categorie ale fiecarui produs vazut."""
        radacini = set()
        for cale in (categorii or []):
            parti = [x for x in str(cale).split("/") if x]
            if parti:
                radacini.add(parti[0])
        diag["radacini"][str(product_id)] = sorted(radacini)

    def _masoara_fereastra(seg, de_la, produse, eticheta):
        """Diagnostic: curba repetarii INAINTE ca `inghite` sa mute `vazute`."""
        noi = rep_in = rep_alt = 0
        for produs in produse:
            eid = produs["external_id"]
            if eid not in vazute:
                noi += 1
                continue
            if diag["primul_segment"].get(eid) == eticheta:
                rep_in += 1
            else:
                rep_alt += 1
        for produs in produse:
            diag["primul_segment"].setdefault(produs["external_id"], eticheta)
        seg["brut"] += len(produse)
        seg["noi"] += noi
        seg["rep_in_segment"] += rep_in
        seg["rep_alt_segment"] += rep_alt
        seg["ferestre"].append({"de_la": de_la, "n_parsate": len(produse),
                                "n_deja_vazute": rep_in + rep_alt})

    def enumereaza_frunza(cale) -> None:
        """O frunza peste prag: benzi de pret, cu rezerva daca ele nu merg.

        `fq=C:` + `fq=P:` impreuna e NEMASURAT. Prima incercare o verifica: daca
        raspunsul nu vine, sau daca totalul benzii e IDENTIC cu al parintelui
        (semnul ca al doilea `fq` a fost ignorat tacit), se trece pe rezerva —
        enumerare liniara a primelor ~2.550, cu warning explicit. Scanul continua.
        """
        fq_c = f"C:{cale}"
        total_parinte = recensamant(fq=fq_c)

        if jurnal["benzi_indisponibile"]:
            jurnal["fallback"] += 1
            enumereaza(fq=fq_c)
            return

        # D8 (runda 3g) — un recensamant de banda picat NU mai e dovada ca perechea
        # `fq=C`+`fq=P` nu tine. Runda 3f a masurat de ce: un 5xx tranzitoriu pe
        # banda [25001, 50000] abandona strategia pe TOT domeniul si arunca EOL pe
        # liniar plafonat la 2.550, pierzand 18.229 de produse — desi celelalte
        # patru recensaminte combinate din aceeasi taietura iesisera 2xx. Acum
        # banda respectiva se pastreaza ca finala, se enumereaza cat se poate si se
        # CONSEMNEAZA ca partiala; surorile ei se taie mai departe normal.
        partiale: list[tuple[int, int]] = []

        totaluri: dict[tuple[int, int], object] = {}

        def recensamant_banda(a, b):
            total = recensamant(fq=[fq_c, f"P:[{a} TO {b}]"])
            totaluri[(a, b)] = total      # D9 citeste de aici, fara cereri in plus
            return total

        try:
            benzi = _benzi_de_pret(recensamant_banda, total_parinte=total_parinte,
                                   partiale=partiale)
        except _BenziIndisponibile:
            jurnal["benzi_indisponibile"] = True
            jurnal["fallback"] += 1
            print(f"[ApiScan] {domain}: fq=C+fq=P NU tine pe {cale} — "
                  f"trec pe enumerare liniara partiala pentru frunzele peste prag")
            enumereaza(fq=fq_c)
            return

        jurnal["cu_benzi"] += 1
        if partiale:
            jurnal["benzi_partiale"] += len(partiale)
            print(f"[ApiScan] {domain}: {len(partiale)} benzi ale categoriei {cale} "
                  f"n-au putut fi recenzate (transport) — enumerate PARTIAL: "
                  f"{partiale}")
        for a, b in benzi:
            # D9 (runda 3h) — banda DEGENERATA de pret 0 se recenseaza, dar NU se
            # enumereaza. Masurat la 3g pe EOL: `fq=P:[0 TO 0]` intoarce 20.766 din
            # 20.779, adica 99,94% din segment sta pe acelasi punct de pret. Taierea
            # binara nu-i poate separa — impart aceeasi valoare — deci converge aici
            # si, enumerata, banda manca 51 de ferestre si lovea plafonul liniar
            # fara sa aduca nimic nou.
            #
            # Pretul 0 nu e o oferta: `_extrage_produse` sare deja orice produs cu
            # `Price <= 0` (contorul `fara_pret`), deci enumerarea benzii ar cere
            # ~415 de ferestre ca sa arunce tot ce aduc. Cifra recensata e insa
            # VALOROASA — e exact termenul care explica reziduul de acoperire — asa
            # ca se pastreaza in jurnal in loc sa fie cheltuita in cereri.
            if (a, b) == (0, 0):
                total_zero = totaluri.get((0, 0))
                if isinstance(total_zero, int) and total_zero > 0:
                    jurnal["pret_zero_neenumerat"] += total_zero
                    print(f"[ApiScan] {domain}: banda [0 TO 0] a categoriei {cale} "
                          f"are {total_zero} produse cu pret 0 — RECENSATE, "
                          f"neenumerate (pretul 0 nu e oferta)")
                continue

            ferestre = enumereaza(fq=[fq_c, f"P:[{a} TO {b}]"])
            if ferestre * _FEREASTRA > _MAX_FROM:
                jurnal["partiale"] += 1
                print(f"[ApiScan] {domain}: banda [{a} TO {b}] a categoriei "
                      f"{cale} depaseste plafonul — segment PARTIAL")

    def trateaza(nod, prefix: str = "") -> None:
        """Un nod de categorie: liniar sub prag, copii peste, benzi la frunza.

        `prefix` e CALEA parintelui. Copiii se cer ca `C:{parinte}/{copil}`, nu ca
        `C:{copil}` — asta a fost defectul rundei 3, masurat la VTX-4.
        """
        cale = f"{prefix}/{nod.get('id')}" if prefix else str(nod.get("id"))
        total = recensamant(fq=f"C:{cale}")
        if not _are_nevoie_de_descindere(total):
            jurnal["liniare"] += 1
            enumereaza(fq=f"C:{cale}")
            return
        copii = [c for c in (nod.get("children") or []) if isinstance(c, dict)]
        if copii:
            jurnal["descinse"] += 1
            for copil in copii:
                trateaza(copil, cale)
            return
        enumereaza_frunza(cale)

    # ── corpul scanului ─────────────────────────────────────────────────────
    arbore, _ = cere(descriptor["tree"])
    if arbore is None:
        raise RuntimeError(f"{domain}: arborele de categorii nu a raspuns")
    for radacina in _radacini_utile(arbore, descriptor.get("exclude_categories")):
        trateaza(radacina)

    _inchide_dealurile(db, domain, calificate, acum)
    db.commit()
    return {"produse": produse_vazute, "deals_active": len(calificate),
            "alerte": alerte, "cereri": stare["cereri"], "jurnal": jurnal,
            "diag": diag if diag["activ"] else None}


def _inchide_dealurile(db, domain: str, calificate: set, acum) -> None:
    """Deal-urile care nu mai CALIFICA se incheie, nu se sterg — ca la DEAL-2b.

    Filtrat pe `deal_source`, fiindca acelasi domeniu poate avea si deal-uri
    `refresh_diff` (un produs urmarit prin link), despre care scanul asta nu spune
    nimic.
    """
    active = (db.query(Deal)
              .filter(Deal.shop_domain == domain,
                      Deal.ended_at.is_(None),
                      Deal.deal_source == "api_enum")
              .all())
    for deal in active:
        if deal.external_id not in calificate:
            deal.ended_at = acum


def run_api_scan(db) -> dict:
    """Intrarea de job (APScheduler, la 24h). Intoarce un rezumat pentru logging."""
    # MON-4 — reset defensiv: joburile ruleaza pe thread-uri de pool.
    set_log_user(None)

    # Non-blocant DELIBERAT, ca la celelalte doua scannere.
    if not _API_LOCK.acquire(blocking=False):
        print("[ApiScan] scanare deja in curs — cererea a fost ignorata")
        return {"skipped": "scan deja in curs", "magazine": 0}

    try:
        settings = _settings(db)
        if settings is not None and not getattr(settings, "deal_scan_enabled", True):
            return {"skipped": "deal_scan_enabled=False", "magazine": 0}

        dezactivate = set(getattr(settings, "deal_shops_disabled", None) or []) if settings else set()
        domenii = sorted(catalog_api_domains() - dezactivate)
        prag = _prag(settings)

        rezumat = {"magazine": 0, "produse": 0, "alerte": 0, "erori": 0,
                   "cereri": 0, "jurnal": {}}
        for domain in domenii:
            try:
                rezultat = _scaneaza_domeniu(db, domain, settings, prag)
            except _PlafonCereri as exc:
                # Plasa atinsa: NU e o exceptie scapata, e o incheiere ordonata.
                # Ce s-a citit pana aici e deja in sesiune, deci se comite.
                db.commit()
                _scrie_stare(db, domain, "error", eroare=str(exc)[:500])
                rezumat["erori"] += 1
                print(f"[ApiScan] {domain}: {exc}")
                continue
            except Exception as exc:                # noqa: BLE001
                db.rollback()
                _scrie_stare(db, domain, "error",
                             eroare=f"{type(exc).__name__}: {exc}"[:500])
                rezumat["erori"] += 1
                print(f"[ApiScan] {domain}: eroare — {type(exc).__name__}: {exc}")
                continue
            _scrie_stare(db, domain, "ok", produse=rezultat["produse"],
                         deals_active=rezultat["deals_active"])
            rezumat["magazine"] += 1
            rezumat["produse"] += rezultat["produse"]
            rezumat["alerte"] += rezultat["alerte"]
            rezumat["cereri"] += rezultat["cereri"]
            for cheie, valoare in (rezultat.get("jurnal") or {}).items():
                if isinstance(valoare, bool):
                    rezumat["jurnal"][cheie] = rezumat["jurnal"].get(cheie, False) or valoare
                elif isinstance(valoare, int):
                    rezumat["jurnal"][cheie] = rezumat["jurnal"].get(cheie, 0) + valoare
            print(f"[ApiScan] {domain}: {rezultat['cereri']} cereri, "
                  f"{rezultat['produse']} produse, {rezultat['deals_active']} "
                  f"deal-uri active, {rezultat['alerte']} alerte, "
                  f"segmente {rezultat['jurnal']}")
        return rezumat
    finally:
        _API_LOCK.release()
