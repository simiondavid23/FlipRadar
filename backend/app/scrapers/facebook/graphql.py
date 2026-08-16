"""POST-ul GraphQL: mutarea variabilelor in sablon + trimiterea cererii.

Sablonul vine INTREG din pagina (vezi bootstrap.py) si se transforma cat mai putin
posibil: termenul, ancora si raza. `count` NU se atinge (A2) — s-a masurat ca e
plafonat server-side la 24, iar 48 si 100 aduc tot 24, deci singurul efect al
modificarii ar fi sa ne faca vizibili.

Paginarea NU e implementata: logat-out, pagina 2 raspunde `edges: []` cu
`page_info: null`. Traseul explicit prin `edges` ar fi necesar doar pentru cursor
si page_info; anunturile se iau STRUCTURAL, ca sa nu depindem de forma raspunsului.
"""
import copy
import json
from typing import Optional

from app.services.log_manager import log_manager

from .parse import walk_listing_objects

URL_GRAPHQL = "https://www.facebook.com/api/graphql/"
BASE = "https://www.facebook.com"


def _cale_exista(d: dict, cale: str) -> bool:
    """`params.bqf.query` exista in dict, cu fiecare segment intermediar dict?"""
    cur = d
    for seg in cale.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return False
        cur = cur[seg]
    return True


def _seteaza(d: dict, cale: str, valoare) -> None:
    cur = d
    segmente = cale.split(".")
    for seg in segmente[:-1]:
        cur = cur[seg]
    cur[segmente[-1]] = valoare


def muta(sablon: dict, *, query: str, lat: float, lon: float,
         raza_km: float, cursor: Optional[str] = None) -> Optional[dict]:
    """Sablonul din pagina, cu termenul si ancora mutate. None daca forma s-a schimbat.

    GARDA: fiecare cale se verifica INAINTE de scriere. Daca lipseste, se logheaza
    numele ei si NU se trimite nicio cerere. Alternativa "scriem oricum, poate merge"
    e exact ce a produs 6 apeluri esuate consecutiv la sonda 3 (toate cu
    `missing_required_variable_value`): o cale inventata nu e ignorata de Facebook,
    ci invalideaza intreaga cerere — si o face TACUT, cu HTTP 200.
    """
    if not isinstance(sablon, dict):
        log_manager.emit("radar", "WARN",
            "Facebook GraphQL: sablon inexistent sau de alt tip — cererea nu se trimite")
        return None

    scrieri = [
        ("savedSearchQuery", query),
        ("params.bqf.query", query),
        ("buyLocation", {"latitude": lat, "longitude": lon}),
        ("params.browse_request_params.filter_location_latitude", lat),
        ("params.browse_request_params.filter_location_longitude", lon),
        # Raza e IGNORATA de Facebook logat-out (masurat: 65 si 500 km dau acelasi
        # set). O trimitem oricum, ca sa nu mintim sablonul despre ce cerem.
        ("params.browse_request_params.filter_radius_km", raza_km),
    ]
    if cursor is not None:
        scrieri.append(("cursor", cursor))

    for cale, _ in scrieri:
        if not _cale_exista(sablon, cale):
            log_manager.emit("radar", "WARN",
                f"Facebook GraphQL: sablonul nu are calea '{cale}' — "
                f"forma s-a schimbat, cererea NU se trimite")
            return None

    v = copy.deepcopy(sablon)
    for cale, valoare in scrieri:
        _seteaza(v, cale, valoare)
    return v


def _payloads(corp: str) -> list[dict]:
    """Raspunsul poate fi un singur JSON sau mai multe, unul pe linie, uneori cu
    prefixul anti-JSON-hijacking `for (;;);`."""
    corp = (corp or "").strip()
    if not corp:
        return []
    if corp.startswith("for (;;);"):
        corp = corp[9:]
    try:
        unul = json.loads(corp)
        return [unul] if isinstance(unul, dict) else []
    except Exception:
        pass
    out = []
    for linie in corp.split("\n"):
        linie = linie.strip()
        if linie.startswith("for (;;);"):
            linie = linie[9:]
        if not linie:
            continue
        try:
            p = json.loads(linie)
        except Exception:
            continue
        if isinstance(p, dict):
            out.append(p)
    return out


def cauta(client, boot, variabile: dict) -> Optional[dict]:
    """POST pe /api/graphql/. Intoarce JSON-ul parsat, sau None la orice esec.

    None e SEMNALUL pentru client sa invalideze bootstrap-ul si sa reincerce o
    singura data (treapta 2 din scara): un `errors` la radacina inseamna aproape
    intotdeauna ca sablonul salvat s-a invechit fata de ce serveste Facebook acum.

    Invelis subtire peste `cauta_cu_cod`, pastrat cu semnatura si comportamentul
    neschimbate — treapta 2 din client depinde de ele.
    """
    return cauta_cu_cod(client, boot, variabile)[0]


def cauta_cu_cod(client, boot, variabile: dict) -> tuple:
    """Ca `cauta`, dar intoarce si CODUL erorii de resolver: (json|None, cod|None).

    Codul distinge lucruri care arata la fel de la distanta: 1675004 ("Rate limit
    exceeded", masurat la FB-4a pe doc_id-ul de browse) e un refuz de ACCES, pe cand
    1675012 ("missing_required_variable_value") inseamna sablon invechit. Primul nu
    se repara reincercand; al doilea da. Pana acum codul se pierdea in `cauta`.
    """
    date = {
        "av": "0", "__user": "0", "__a": "1", "__req": "1", "dpr": "1",
        "__ccg": "EXCELLENT", "server_timestamps": "true",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": boot.friendly_name,
        "variables": json.dumps(variabile),
        "doc_id": boot.doc_id,
        "lsd": boot.lsd,
    }
    antete = {
        "content-type": "application/x-www-form-urlencoded",
        "x-fb-friendly-name": boot.friendly_name,
        "x-fb-lsd": boot.lsd,
        "origin": BASE,
        "referer": f"{BASE}/marketplace/bucharest/search",
    }

    corp, status = client.post(URL_GRAPHQL, data=date, headers=antete)
    if status != 200 or not corp:
        log_manager.emit("radar", "WARN",
            f"Facebook GraphQL: HTTP {status} ({len(corp or '')} octeti)")
        return None, None

    payloads = _payloads(corp)
    if not payloads:
        log_manager.emit("radar", "WARN",
            "Facebook GraphQL: raspuns neparsabil ca JSON")
        return None, None

    for p in payloads:
        erori = p.get("errors")
        if erori:
            mesaj, cod = "", None
            if isinstance(erori, list) and erori and isinstance(erori[0], dict):
                mesaj = str(erori[0].get("message") or "")[:120]
                brut = erori[0].get("code")
                cod = brut if isinstance(brut, int) else None
            log_manager.emit("radar", "WARN",
                f"Facebook GraphQL: eroare de resolver — {mesaj or 'fara mesaj'}"
                + (f" (code {cod})" if cod is not None else ""))
            return None, cod

    return (payloads[0] if len(payloads) == 1 else {"payloads": payloads}), None


def extrage_anunturi(json_raspuns: dict) -> list[dict]:
    """Obiectele brute de anunt din raspuns, structural (dicturi cu
    `marketplace_listing_title` si `id`) — acelasi criteriu ca pe SSR."""
    if not json_raspuns:
        return []
    return walk_listing_objects(json_raspuns)
