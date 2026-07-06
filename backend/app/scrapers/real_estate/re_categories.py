"""Campuri tehnice de filtrare per platforma imobiliara (Imobiliare Monitor).

REGULA (identica cu auto_categories.py): DOAR campurile cu "confirmed": True se conecteaza
in scrapere. "confirmed": False = documentat, NECONECTAT pana la o verificare live directa.
A inventa un param/slug plauzibil e o greseala grava — nu se repeta.

Surse marcate per camp:
  - "confirmat live"      : verificat direct pe platforma .ro in aceasta implementare.
  - "sister-docs"         : documentatie platforma-sora OLX Group (pyolx / pyotodom, .pl),
                            NEVERIFICAT pe .ro -> confirmed:False.
  - "UI Facebook"         : filtru vazut in UI Facebook Marketplace, dar NUMELE param neverificat.

"style":
  - lipsa / "query"       : params[param] = valoare (mapata prin "values" daca exista).
  - "custom"              : aplicat IN SCRAPER (format special: path/array), apply_re_filters il
                            SARE. Vezi scraperul respectiv.
"""

RE_TECHNICAL_FIELDS = {
    "storia": {
        # Locatia e PATH, nu query (rezultate/{tip}/{tip_prop}/{judet}/{oras} sau
        # /toata-romania) — confirmat live; nu se pune in query.
        "price_min": {"confirmed": True, "param": "priceMin"},   # confirmat live
        "price_max": {"confirmed": True, "param": "priceMax"},   # confirmat live
        # CONFIRMAT LIVE 2026-07-05: roomsNumber filtreaza DOAR in forma cu paranteze
        # roomsNumber=[X,Y] (set exact); "roomsNumber=THREE" simplu e IGNORAT. Aplicat IN
        # SCRAPER (storia_scraper._rooms_from_min: "[ENUM..FOUR]" de la min in sus) -> style custom.
        "rooms_min": {"confirmed": True, "param": "roomsNumber", "style": "custom"},
        # Restul — sister-docs (pyotodom), NEVERIFICATE pe storia.ro azi:
        "area_min": {"confirmed": False, "param": "search[filter_float_m:from]"},
        "area_max": {"confirmed": False, "param": "search[filter_float_m:to]"},
        "floor_min": {"confirmed": False, "param": "search[filter_enum_floor_select][0]"},
        "seller_type": {"confirmed": False, "param": "search[private_business]",
                        "values": {"persoana_fizica": "private", "agentie": "business"}},
        "market_type": {"confirmed": False, "param": "search[filter_enum_market][0]",
                        "values": {"nou": "primary", "vechi": "secondary"}},
    },
    "olx_real_estate": {
        "price_min": {"confirmed": True, "param": "search[filter_float_price:from]"},  # confirmat live
        "price_max": {"confirmed": True, "param": "search[filter_float_price:to]"},     # confirmat live
        # CORECTIE dupa verificare live 2026-07-05: rooms NU merge ca query param
        # search[filter_enum_rooms][0]=two (returneaza pagina JS fara carduri SSR -> 0 rezultate,
        # cauza reala a filtrului "mort" din scraperul vechi). Merge ca PATH /{N}-camere/
        # (N=1..4, /4-camere/ = 4+; match EXACT). Aplicat IN SCRAPER (olx_real_estate) -> custom.
        "rooms_min": {"confirmed": True, "param": "/{n}-camere/", "style": "custom"},
        # sister-docs (pyolx), neverificate direct pe olx.ro/imobiliare azi:
        "area_min": {"confirmed": False, "param": "search[filter_float_m:from]"},
        "area_max": {"confirmed": False, "param": "search[filter_float_m:to]"},
        "floor_min": {"confirmed": False, "param": "search[filter_enum_floor_select][0]"},
        "seller_type": {"confirmed": False, "param": "search[private_business]",
                        "values": {"persoana_fizica": "private", "agentie": "business"}},
        "building_type": {"confirmed": False, "param": "search[filter_enum_builttype][0]",
                          "values": {"bloc": "blok", "casa": "wolnostojacy"}},  # traduceri RO<->PL
        # aproximative, NEVERIFICATE pe .ro — nu presupune ca sunt identice cu poloneza.
    },
    "imobiliare_ro": {
        # NOTA (2026-07-05): param-urii de mai jos ajung CORECT in URL (confirmed:True, cerinta
        # initiala indeplinita), DAR imobiliare.ro NU ii aplica server-side — intoarce un set
        # 'featured' scopat doar pe LOCATIE (path). Filtrarea REALA pe pret/camere/suprafata se
        # face CLIENT-SIDE, in scraper (imobiliare_ro_scraper._passes_imob_filters, post-filtru),
        # nu de catre site. (Confirmat live: /iasi?pret_max=100000 intoarce si preturi > 100000.)
        "price_min": {"confirmed": True, "param": "pret_min"},        # in URL; filtrat local (post-filtru)
        "price_max": {"confirmed": True, "param": "pret_max"},        # in URL; filtrat local (post-filtru)
        "rooms_min": {"confirmed": True, "param": "nr_camere"},       # in URL; filtrat local (post-filtru)
        "area_min": {"confirmed": True, "param": "suprafata_min"},    # in URL; filtrat local (post-filtru)
        # NECONFIRMATE azi — nu am gasit un URL real cu aceste campuri:
        "area_max": None,
        "floor_min": None,
        "an_constructie_min": None,
    },
    "facebook_real_estate": {
        # minPrice/maxPrice — comportamentul deja existent al scraperului (Marketplace
        # Property Rentals). Restul: filtre VAZUTE in UI, dar numele param NEVERIFICAT ->
        # confirmed:False (nu ne bazam pe un nume de param neconfirmat, chiar daca filtrul exista).
        "price_min": {"confirmed": True, "param": "minPrice"},
        "price_max": {"confirmed": True, "param": "maxPrice"},
        # UI confirma "Number of bedrooms" (1+ .. 6+), dar numele exact al param (minBedrooms?)
        # NU e verificat live (necesita sesiune Playwright + citire URL rezultat). NECONECTAT.
        "rooms_min": {"confirmed": False, "param": "minBedrooms"},        # UI Facebook, param neverificat
        "bathrooms_min": {"confirmed": False, "param": "minBathrooms"},   # UI Facebook, param neverificat
        "area_max": {"confirmed": False, "param": "maxSquareFeet"},       # UI Facebook, param neverificat
        "private_only": {"confirmed": False, "param": "sellerType",
                         "values": {"persoana_fizica": "individual"}},    # UI Facebook, param neverificat
    },
}


# Tipuri de proprietate per platforma (confirmed/neconfirmat — aceeasi regula ca RE_TECHNICAL_FIELDS:
# DOAR "confirmed": True se conecteaza in scraper; False = documentat, NECONECTAT pana la verificare
# live directa). Storia/Imobiliare.ro/OLX "comercial" confirmate live 2026-07-06 (URL-uri in
# comentariile de mai jos); Facebook "vanzare" (propertyforsale) NECONFIRMAT — vezi nota de la
# categorie_tip_anunt (intoarce doar Partner listings, nu vanzari imobiliare).
RE_PROPERTY_TYPES = {
    "olx": {
        "apartament": {"confirmed": True}, "garsoniera": {"confirmed": True},
        "casa": {"confirmed": True}, "teren": {"confirmed": True}, "comercial": {"confirmed": True},
    },
    "storia": {
        "apartament": {"confirmed": True}, "garsoniera": {"confirmed": True},
        "casa": {"confirmed": True}, "teren": {"confirmed": True},
        "comercial": {"confirmed": True},   # confirmat live 2026-07-06: /ro/rezultate/vanzare/spatiu-comercial/{oras}
    },
    "imobiliare_ro": {
        "apartament": {"confirmed": True}, "garsoniera": {"confirmed": True},
        "casa": {"confirmed": True}, "teren": {"confirmed": True},
        "comercial": {"confirmed": True},   # confirmat live 2026-07-06: /vanzare-spatii-comerciale/
    },
    "facebook_real_estate": {
        "categorie_tip_anunt": {
            # INVESTIGAT LIVE 2026-07-06 (sesiune valida, scroll adanc, cu/fara query):
            # /category/propertyforsale/ intoarce DOAR "Partner listing" — electronice
            # (laptop/telefon) + chirii, ZERO vanzari imobiliare reale. Query-ul e ignorat.
            # Deci NECONFIRMAT ca sursa de vanzari. propertyrentals (chirii) merge corect.
            "vanzare": {"confirmed": False, "slug": "propertyforsale"},
            "inchiriere": {"confirmed": True, "slug": "propertyrentals"},
        },
        # tip_proprietate in interiorul categoriei — de investigat in Partea B, sectiunea 3.
    },
}


# Scraperele RE citesc filtrele cu cheile "pret_min"/"camere_min"/"suprafata_min" (interfata
# de facto, folosita si de /api/real-estate/search + scanner-ul vechi). Le mapam la field_key-urile
# din RE_TECHNICAL_FIELDS ca apply_re_filters sa le gaseasca. Acelasi rol ca aliases in Auto.
RE_FILTER_ALIASES = {
    "price_min": "pret_min",
    "price_max": "pret_max",
    "rooms_min": "camere_min",
    "area_min": "suprafata_min",
    "area_max": "suprafata_max",
}


def apply_re_filters(platform: str, filters: dict, params: dict,
                     aliases: dict | None = None) -> None:
    """Aplica in `params` DOAR campurile tehnice cu "confirmed": True ale platformei.

    Adaptat din auto_categories.apply_confirmed_filters. Suporta:
      - style lipsa / "query"          : params[param] = valoare (mapata prin "values").
      - style "query_range_colon"      : params[param] = "MIN:MAX".
      - style "custom"                 : SARIT (aplicat separat in scraper — format special).

    `aliases`: field_key -> cheia reala din `filters` (ex. scraperele RE folosesc "pret_min"/
    "camere_min"/"suprafata_min" in loc de "price_min"/"rooms_min"/"area_min"). Enum-uri: se
    trimit DOAR daca valoarea e in "values" (confirmata); altfel se sare — nu inventam.
    Nu returneaza nimic (spre deosebire de Auto — imobiliarele nu au path_suffix).
    """
    tech = RE_TECHNICAL_FIELDS.get(platform) or {}
    aliases = aliases or {}

    def _get(field_key):
        v = filters.get(field_key)
        if v in (None, "") and field_key in aliases:
            v = filters.get(aliases[field_key])
        return v

    def _map(spec, val):
        vm = spec.get("values")
        return val if vm is None else vm.get(val)  # None daca valoarea nu e confirmata

    for field_key, spec in tech.items():
        if not isinstance(spec, dict) or not spec.get("confirmed"):
            continue
        style = spec.get("style") or "query"
        if style == "custom":
            continue  # aplicat in scraper (path/array), nu ca query param
        param = spec.get("param")
        if not param:
            continue

        if style == "query_range_colon":
            base = field_key.rsplit("_", 1)[0]
            lo, hi = _get(f"{base}_min"), _get(f"{base}_max")
            if lo in (None, "") and hi in (None, ""):
                continue
            params[param] = f"{'' if lo in (None, '') else lo}:{'' if hi in (None, '') else hi}"
        else:  # "query"
            val = _get(field_key)
            if val in (None, ""):
                continue
            mapped = _map(spec, val)
            if mapped is not None:
                # Preturi/suprafete intregi -> fara ".0" in URL (ex 50000, nu 50000.0).
                if isinstance(mapped, float) and mapped.is_integer():
                    mapped = int(mapped)
                params[param] = mapped
