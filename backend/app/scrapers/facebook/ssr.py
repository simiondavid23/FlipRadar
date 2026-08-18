"""Calea SSR: pagina de search citita direct, fara GraphQL.

E cea mai simpla cale, dar si cea mai ingusta: FB-0 a masurat ca din 51 de ancore
un SINGUR slug de oras e valid (`bucharest`). Restul sunt ignorate TACUT de
Facebook, care serveste setul implicit — deci o cautare pe un slug nevalidat ar
intoarce anunturi din alt oras, fara niciun semnal de eroare. De-aia treapta asta
se folosea DOAR pentru ancorele cu slug validat, niciodata "sa incercam".

SLUGURILE SUNT MOARTE SI AUTENTIFICAT (masurat la FBS-0b, cu sesiune atasata): nu
e o limitare a caii logat-out, cum s-ar putea presupune. `cluj-napoca`, `iasi` si
`timisoara` au primit toate trei ACELASI set bucurestean, cu Jaccard 1.000 intre
ele. Nu se revalideaza — e a doua masuratoare care spune acelasi lucru.

CE MERGE IN SCHIMB (FBS-0b + FBS-0c): ID-ul NUMERIC de locatie,
`/marketplace/{city_page_id}/search`, citit din
`listing.location.reverse_geocode.city_page`. Ancoreaza corect pe toate cele patru
orase testate (Cluj, Iasi, Timisoara, Brasov; Jaccard 0.000 intre ele) si accepta
`sortBy=creation_time_descend` plus `daysSinceListed=1`. Migrarea caii de aici pe
ID e treaba FBS-2, cu teste — nu se face in trecere.

CAPCANA, ca sa nu se piarda o runda pe ea (masurat la FBS-0d): feed-ul orasului,
`/marketplace/{id}/` fara `/search`, ARATA ca functioneaza dar nu functioneaza.
Intoarce 20 de anunturi si HTTP 200, dar ignora TOATE cele trei axe: ancora
(Jaccard 0.905 intre Timisoara si Zalau — practic acelasi set), recenta (varste de
peste 130 de zile, cu `daysSinceListed=1` trimis) si sortarea. Cine o incearca la o
runda viitoare primeste gunoi fara niciun semnal de eroare.

`/marketplace/{id}/search` FARA `query` nu e nici ea o alternativa: intoarce zero
anunturi si santinela `SERP_NO_RESULTS` (FBS-0d). Un baleiaj fara termen nu exista,
deci costul ramane ORASE x CUVINTE.
"""
from urllib.parse import urlencode

from app.services.log_manager import log_manager

from .parse import iter_listing_objects, looks_like_login_wall

BASE = "https://www.facebook.com"

# Parametrii de recenta, masurati ca RESPECTATI pe calea de ID (FBS-0c). Fereastra
# reala e insa de ~38 h, nu 24 — deci astia sunt un PREfiltru grosier, iar taierea
# fina se face local, in client, pe `creation_time`.
_SORTARE = "creation_time_descend"
_ZILE = "1"


def construieste_url(city_page_id: str, query: str, *, recenta: bool = True) -> str:
    """URL-ul de cautare SSR pentru un ID de locatie.

    Termenul se CODIFICA (`urlencode`). Pana la FBS-2 se interpola brut intr-un
    f-string, ceea ce era o defectiune latenta, nu o lipsa de rafinament: orice
    termen cu spatiu sau diacritice — adica majoritatea termenilor romanesti reali,
    „canapea extensibila", „masina de spalat" — producea un URL malformat. Nu s-a
    vazut pana acum doar fiindca sondele au rulat pe „canapea", un cuvant fara
    spatii si fara diacritice.
    """
    params = {"query": query}
    if recenta:
        params["sortBy"] = _SORTARE
        params["daysSinceListed"] = _ZILE
    return f"{BASE}/marketplace/{city_page_id}/search?{urlencode(params)}"


def cauta_ssr(client, city_page_id: str, query: str, *,
              recenta: bool = True) -> list[dict]:
    """Obiectele brute de anunt din pagina SSR. Lista goala la orice esec.

    `city_page_id` e ID-ul NUMERIC de locatie, nu un slug — slugurile sunt moarte pe
    ambele regimuri de acces (vezi nota de sus).
    """
    if not city_page_id:
        return []
    url = construieste_url(city_page_id, query, recenta=recenta)
    corp, status = client.get(url)
    if status != 200 or not corp:
        log_manager.emit("radar", "WARN",
            f"Facebook SSR: HTTP {status} pe locatia '{city_page_id}'")
        return []
    if looks_like_login_wall(corp):
        log_manager.emit("radar", "WARN",
            f"Facebook SSR: login-wall in corp pe locatia '{city_page_id}' "
            f"(HTTP {status})")
        return []
    return iter_listing_objects(corp)
