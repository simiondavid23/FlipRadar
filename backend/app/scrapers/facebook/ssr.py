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
from typing import Optional
from urllib.parse import urlencode

from app.services.log_manager import log_manager

from .parse import iter_listing_objects, looks_like_login_wall

BASE = "https://www.facebook.com"

# Parametrii de recenta, masurati ca RESPECTATI pe calea de ID (FBS-0c). Fereastra
# reala e insa de ~38 h, nu 24 — deci astia sunt un PREfiltru grosier, iar taierea
# fina se face local, in client, pe `creation_time`.
_SORTARE = "creation_time_descend"
_ZILE = "1"


def construieste_url(city_page_id: str, query: str, *, recenta: bool = True,
                     pret_min: Optional[int] = None,
                     pret_max: Optional[int] = None) -> str:
    """URL-ul de cautare SSR pentru un ID de locatie.

    Termenul se CODIFICA (`urlencode`). Pana la FBS-2 se interpola brut intr-un
    f-string, ceea ce era o defectiune latenta, nu o lipsa de rafinament: orice
    termen cu spatiu sau diacritice — adica majoritatea termenilor romanesti reali,
    „canapea extensibila", „masina de spalat" — producea un URL malformat. Nu s-a
    vazut pana acum doar fiindca sondele au rulat pe „canapea", un cuvant fara
    spatii si fara diacritice.

    `pret_min` (FBS-6) e MASURAT ca respectat de server, la FBS-V1b: doua praguri
    discriminante (1500 si 3000), Jaccard 0.000 fata de referinta la amandoua, zero
    scapari sub prag dintr-o referinta care avea 24 din 24 sub el, iar seturile
    difereau strict pe axa de pret (setul cu pragul mare era submultime a celui cu
    pragul mic, fara exact anunturile din banda dintre praguri). Sortarea
    `creation_time_descend` a ramas intacta, 0 inversiuni. E PRIMUL parametru din
    serie care nu e ignorat tacit, spre deosebire de raza (FB-PROBE-2), slugurile de
    oras (FBS-0b) si `category_id` (FBS-V1).

    REZERVA MASURATA, scrisa aici ca sa nu fie citita mai tarziu drept defect de
    cablare: fereastra `daysSinceListed=1` e ELASTICA — se intinde cat ii trebuie
    serverului ca sa umple sloturile si variaza de la o cerere la alta. O rulare cu
    prag s-a oprit la 17.79 h si a omis doua anunturi eligibile de 32-41 h pe care o
    rulare fara prag le avea. Filtrul deci NU lasa nimic SUB prag sa treaca, dar nici
    nu garanteaza tot ce e PESTE prag. Un prag pus prea sus poate infometa feed-ul.

    `pret_max` (FBS-10) e MASURAT la fel de strict respectat, la FBS-V3: cu plafon 1000
    au iesit ZERO scapari peste el dintr-o referinta care avea 23 din 24 deasupra, iar
    combinatia `minPrice=1245` + `maxPrice=1588` a intors 24 din 24 in interval si a
    fost SUPRASET al benzii de referinta — a pastrat toate cele 11 anunturi pe care
    referinta le avea in banda si a mai scos la iveala inca 13, invizibile fara filtru.
    Superset-ul e dovada mai tare decat Jaccard-ul: rotatia de inventar nu adauga
    anunturi FIX in banda ceruta, doar filtrarea la sursa elibereaza sloturi asa.
    Ordinea cheilor (`minPrice` inaintea lui `maxPrice`) e cea masurata acolo.

    Aceeasi rezerva se aplica si aici, mai apasat: pe COMBINATIE fereastra elastica
    s-a intins pana la ~35 h, cu mediana 20.9 h. Cu `FB_VARSTA_MAX_ORE` la 24 h
    jumatate din recolta ar fi fost taiata de filtrul de varsta al treptei 1; la 48 h,
    cat e configurat, incape.
    """
    params = {"query": query}
    if recenta:
        params["sortBy"] = _SORTARE
        params["daysSinceListed"] = _ZILE
    # Zero sau negativ inseamna semantic „fara prag" — aceeasi conventie ca in
    # `_build_search_url` din radar/facebook_scraper.py, ca sa nu existe doua
    # intelesuri ale aceleiasi valori pe cai diferite. Cheile se adauga ULTIMELE,
    # deliberat: in absenta lor URL-ul ramane BYTE-IDENTIC cu cel de dinainte, deci
    # fixture-urile si testele de URL existente raman valide. `maxPrice` intra DUPA
    # `minPrice`, ca forma trimisa sa fie exact cea masurata la FBS-V3 — si ca URL-ul
    # cu prag dar fara plafon sa ramana byte-identic cu forma post-FBS-6.
    if pret_min is not None and pret_min > 0:
        params["minPrice"] = pret_min
    if pret_max is not None and pret_max > 0:
        params["maxPrice"] = pret_max
    return f"{BASE}/marketplace/{city_page_id}/search?{urlencode(params)}"


def cauta_ssr(client, city_page_id: str, query: str, *,
              recenta: bool = True, pret_min: Optional[int] = None,
              pret_max: Optional[int] = None) -> list[dict]:
    """Obiectele brute de anunt din pagina SSR. Lista goala la orice esec.

    `city_page_id` e ID-ul NUMERIC de locatie, nu un slug — slugurile sunt moarte pe
    ambele regimuri de acces (vezi nota de sus).
    """
    if not city_page_id:
        return []
    url = construieste_url(city_page_id, query, recenta=recenta, pret_min=pret_min,
                           pret_max=pret_max)
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
