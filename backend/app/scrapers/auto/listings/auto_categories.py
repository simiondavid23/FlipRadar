"""Categorii + campuri tehnice de filtrare per platforma auto (Auto Anunturi).

REGULA: valorile de aici sunt EXACT cele confirmate live prin cercetare (nu inventate).
Campurile marcate cu value=None sau "confirmed": False NU se conecteaza in scrapere —
raman doar documentate pana la o verificare live directa. A inventa un slug/cod plauzibil
e o greseala grava (s-a intamplat o data cu ID-uri Vinted gresite — nu se repeta).

Facebook Auto e EXCLUS intentionat: platforma nu suporta filtre tehnice structurate.
"""

AUTO_PLATFORM_CATEGORIES = {
    "autovit": [
        {"label": "Autoturisme", "value": "autoturisme"},
        {"label": "Autoutilitare", "value": "autoutilitare"},
        {"label": "Motociclete", "value": "motociclete"},
        {"label": "Camioane", "value": "camioane"},
        {"label": "Remorci", "value": "remorci"},
    ],  # confirmat live din navigarea site-ului (7 categorii top; Piese/Constructii/Agro omise, irelevante pt arbitraj auto)
    "olx_auto": [
        {"label": "Autoturisme", "value": "autoturisme"},
        {"label": "Autoutilitare", "value": "autoutilitare"},
        {"label": "Camioane, Utilaje, Rulote, Remorci", "value": "camioane-utilaje-rulote-remorci"},
        {"label": "Motociclete", "value": "motociclete"},
        {"label": "Scutere, ATV, UTV", "value": "scutere-atv-utv"},
        {"label": "Ambarcațiuni", "value": "ambarcatiuni"},
    ],  # confirmat live, identic cu fix-ul deja aplicat in categories.py (Radar) pt olx
    "mobile_de": [
        {"label": "Mașini", "value": "Car"},
        {"label": "Motociclete", "value": "Motorbike"},
        # vehicleClass confirmat din documentatia oficiala mobile.de. Truck/Trailer/Caravan
        # EXISTA (confirmat in schema oficiala) dar valoarea exacta de vehicleClass pt ele
        # nu a fost verificata azi — TODO: NU adauga randuri pentru ele pana la verificare live.
    ],
    "autoscout24": [
        {"label": "Mașini", "value": "C"},  # atype=C, confirmat in 5+ exemple reale
        {"label": "Motociclete", "value": None},  # confirmat existenta paginii /motorcycle/,
        # dar NU parametrul de query — daca implementezi, foloseste path-ul /motorcycle/
        # in loc de query param, e mai sigur (confirmat direct).
        {"label": "Autorulote", "value": None},  # idem, /lst-caravan confirmat ca path, nu param
    ],
    "kleinanzeigen_auto": [
        {"label": "Autos", "value": "c216"},  # confirmat direct din URL real
        {"label": "Motociclete/Scutere", "value": None},  # categorie confirmata ca existand
        # (Motorräder & Motorroller), cod c### NECONFIRMAT — nu inventa numarul.
        {"label": "Utilitare/Remorci", "value": None},  # idem (Nutzfahrzeuge & Anhänger)
        {"label": "Rulote/Autorulote", "value": None},  # idem (Wohnwagen & -mobile)
    ],
}

AUTO_TECHNICAL_FIELDS = {
    # ── AUTOVIT ── style "query", param search[...]. TOATE confirmate functional 2026-07-05
    # prin delta de rezultate live pe /autoturisme (BASE=42005): fiecare valoare de mai jos
    # ingusteaza numarul de anunturi; valorile invalide dau pagina fara "X anunturi" (respinse).
    "autovit": {
        # 7 combustibili confirmati (petrol 13638, diesel 21734, hybrid 2094, plugin-hybrid 2973,
        # electric 1003, petrol-lpg 540, petrol-cng 21). hydrogen = invalid (respins).
        "fuel_type": {"confirmed": True, "param": "search[filter_enum_fuel_type]",
                      "values": {"benzina": "petrol", "diesel": "diesel", "hibrid": "hybrid",
                                 "hibrid_plugin": "plugin-hybrid", "electric": "electric",
                                 "gpl": "petrol-lpg", "gnc": "petrol-cng"}},
        "gearbox": {"confirmed": True, "param": "search[filter_enum_gearbox]",
                    "values": {"manuala": "manual", "automata": "automatic"}},  # 13783 / 28212
        # 8 caroserii confirmate (sedan 8227, combi 5134, compact 3684, coupe 1165, cabrio 479,
        # suv 18270, minivan 2349, city-car 2007). station-wagon/off-road = invalid.
        "body_type": {"confirmed": True, "param": "search[filter_enum_body_type]",
                      "values": {"sedan": "sedan", "break": "combi", "hatchback": "compact",
                                 "coupe": "coupe", "cabrio": "cabrio", "suv": "suv",
                                 "monovolum": "minivan", "minicar": "city-car"}},
        # tractiune (filter_enum_transmission): fata 20949, spate 3215. Codul de 4x4 NU a fost
        # gasit (4x4-permanent/automatic/manual/all-wheel-drive toate invalide) -> doar 2 valori.
        "drivetrain": {"confirmed": True, "param": "search[filter_enum_transmission]",
                       "values": {"fata": "front-wheel", "spate": "rear-wheel"}},
        "door_count": {"confirmed": True, "param": "search[filter_enum_door_count]",
                       "values": {"2": "2", "3": "3", "4": "4", "5": "5"}},  # 1146/743/7426/32515
        # stare (filter_enum_damaged): 1=avariat (183), 0=neavariat (34993). yes/no = ignorate.
        "condition": {"confirmed": True, "param": "search[filter_enum_damaged]",
                      "values": {"avariat": "1", "neavariat": "0"}},
        # norma poluare euro-1..euro-6 confirmate (6/19/64/704/3356/15978).
        "emission_standard": {"confirmed": True, "param": "search[filter_enum_pollution_standard]",
                              "values": {"euro1": "euro-1", "euro2": "euro-2", "euro3": "euro-3",
                                         "euro4": "euro-4", "euro5": "euro-5", "euro6": "euro-6"}},
        # vanzator: doar "dealer autorizat" (=1, 5304) confirmat; persoana fizica negasita.
        # type "boolean" -> checkbox in UI. Fara "values": apply_confirmed_filters trimite
        # valoarea "1" ca atare (param=1). O singura valoare cu sens -> nu are rost dropdown.
        "seller_type": {"confirmed": True, "param": "search[filter_enum_authorized_dealer]",
                        "type": "boolean"},
        # factura cu TVA (filter_enum_vat=1, 14554) — tot boolean (o singura valoare "1").
        "vat_invoice": {"confirmed": True, "param": "search[filter_enum_vat]", "type": "boolean"},
        # range-uri filter_float (query, param :from/:to). Confirmate: engine_capacity(from=2000 -> 8255),
        # engine_power(from=200 -> 12095), nr_seats(from=7 -> 1398).
        "engine_capacity_min": {"confirmed": True, "param": "search[filter_float_engine_capacity:from]"},
        "engine_capacity_max": {"confirmed": True, "param": "search[filter_float_engine_capacity:to]"},
        "engine_power_min": {"confirmed": True, "param": "search[filter_float_engine_power:from]"},
        "engine_power_max": {"confirmed": True, "param": "search[filter_float_engine_power:to]"},
        "seats_min": {"confirmed": True, "param": "search[filter_float_nr_seats:from]"},
        # culoare confirmata PER-VALOARE 2026-07-05 (delta rezultate, BASE 42008): black 10431,
        # white 8360, gray 10041, silver 2501, blue 5085, red 1952, green 825, brown 1268,
        # orange 336, other 452. ("grey"/beige/gold/yellow/violet = slug invalid, respinse).
        "color": {"confirmed": True, "param": "search[filter_enum_color]",
                  "values": {"negru": "black", "alb": "white", "gri": "gray", "argintiu": "silver",
                             "albastru": "blue", "rosu": "red", "verde": "green", "maro": "brown",
                             "portocaliu": "orange", "alta": "other"}},
    },
    # ── OLX AUTO ── style "query", param search[filter_enum_X] / search[filter_float_X:from|:to].
    # Confirmate 2026-07-05 prin total din __PRERENDERED_STATE__ (BASE autoturisme=118781).
    # Valorile invalide colapseaza la 40 (podeaua de zgomot) -> respinse.
    "olx_auto": {
        # 6 combustibili (petrol 35049, diesel 71129, hybrid 3034, electric 1342, lpg 1851,
        # plugin-hybrid 3427). hybrid-plugin/cng = 40 (invalide).
        "fuel_type": {"confirmed": True, "param": "search[filter_enum_petrol]",
                      "values": {"benzina": "petrol", "diesel": "diesel", "hibrid": "hybrid",
                                 "electric": "electric", "gpl": "lpg", "hibrid_plugin": "plugin-hybrid"}},
        # NOU: OLX ARE filtru structurat de cutie (nota veche "nu exista" era gresita) —
        # manual 63795, automatic 51044.
        "gearbox": {"confirmed": True, "param": "search[filter_enum_gearbox]",
                    "values": {"manuala": "manual", "automata": "automatic"}},
        # 6 caroserii (sedan 29455, coupe 4734, suv 29583, hatchback 22048, minibus 2150, pickup 1073).
        # cabrio/combi/compact/minivan/city-car/station-wagon = 40 (slug-uri OLX diferite, neconfirmate).
        "body_type": {"confirmed": True, "param": "search[filter_enum_car_body]",
                      "values": {"sedan": "sedan", "coupe": "coupe", "suv": "suv",
                                 "hatchback": "hatchback", "minibus": "minibus", "pickup": "pickup"}},
        # culoare (filter_enum_color): black 28417, white 19298, silver 5581, blue 13825, red 5552,
        # gray 28491. ("grey"=40 invalid — e "gray"). Mai exista culori netestate azi.
        "color": {"confirmed": True, "param": "search[filter_enum_color]",
                  "values": {"negru": "black", "alb": "white", "argintiu": "silver",
                             "albastru": "blue", "rosu": "red", "gri": "gray"}},
        # stare: nou 2996, rulat 108502.
        "condition": {"confirmed": True, "param": "search[filter_enum_state]",
                      "values": {"nou": "new", "rulat": "used"}},
        # vanzator: business confirmat (format search[private_business]=business, din research anterior);
        # valoarea pt persoana fizica ramane None (nu se trimite).
        "seller_type": {"confirmed": True, "param": "search[private_business]",
                        "values": {"business": "business", "persoana_fizica": None}},
        # range-uri: capacitate (enginesize from=2000 -> 29051) + an (year from=2020 -> 23396).
        # Putere/rulaj NU au param confirmat pe OLX (enginepower/rulaj/mileage = None).
        "engine_capacity_min": {"confirmed": True, "param": "search[filter_float_enginesize:from]"},
        "engine_capacity_max": {"confirmed": True, "param": "search[filter_float_enginesize:to]"},
        "year_min": {"confirmed": True, "param": "search[filter_float_year:from]"},
        "year_max": {"confirmed": True, "param": "search[filter_float_year:to]"},
    },
    # ── MOBILE.DE ── Interfata de CAUTARE (suchen.mobile.de) e blocata de Imperva din acest
    # mediu (403 / "Zugriff verweigert", reconfirmat 2026-07-05). Deci param-ii de search NU pot
    # fi confirmati functional (test cu/fara filtru imposibil). Pastram ce a fost confirmat live
    # intr-o runda anterioara (ft/fr/p/ml). Am gasit insa API-ul OFICIAL refdata (NEBLOCAT):
    # services.mobile.de/refdata/sites/GERMANY/classes/Car/{categories,makes,features,usedcarseals}.
    # `categories` = caroseriile REALE (vezi body_type). Fuel/gearbox/culoare NU exista ca endpoint
    # refdata (fuelTypes/gearboxes/colours -> 404) — sunt enum-uri fixe in schema ad.
    "mobile_de": {
        "fuel_type": {"confirmed": True, "param": "ft", "style": "query_repeat",
                      "values": {"benzina": "PETROL", "diesel": "DIESEL", "electric": "ELECTRICITY"}},
        "year_min": {"confirmed": True, "param": "fr", "style": "query_range_colon"},   # fr=MIN:MAX
        "price_min": {"confirmed": True, "param": "p", "style": "query_range_colon"},    # p=MIN:MAX
        "mileage_max": {"confirmed": True, "param": "ml", "style": "query_range_colon"}, # ml=MIN:MAX
        # VALORI REALE de caroserie din refdata (Car/categories, citate exact): Cabrio,
        # EstateCar, Limousine, OffRoad, SmallCar, SportsCar, Van, OtherCar. confirmed:False
        # fiindca param-ul de search (candidat "c") NU s-a putut testa (suchen.mobile.de blocat).
        "body_type": {"confirmed": False, "param": "c",
                      "values": {"cabrio": "Cabrio", "break": "EstateCar", "sedan": "Limousine",
                                 "suv": "OffRoad", "minicar": "SmallCar", "coupe": "SportsCar",
                                 "monovolum": "Van"}},
        # ── Documentat din API-ul OFICIAL search-api.html (services.mobile.de/search-api),
        # care NECESITA AUTENTIFICARE (cont API/Dealer) — DIFERIT de interfata publica
        # suchen.mobile.de (ft/fr/p/ml de mai sus, blocata Imperva). Toate confirmed:False:
        # NEVERIFICATE pe interfata publica + nu avem credentiale API. Valorile sunt REALE
        # (search-api.html + endpoint-urile refdata neblocate, citate live 2026-07-05).
        "gearbox": {"confirmed": False, "param": "gearbox",  # sursa: search-api.html (Set enum)
                    "values": {"manuala": "MANUAL_GEAR", "automata": "AUTOMATIC_GEAR",
                               "semiautomata": "SEMIAUTOMATIC_GEAR"}},
        "drivetrain": {"confirmed": False, "param": "driveType",  # sursa: refdata/drivetypes
                       "values": {"fata": "FRONT", "spate": "REAR", "integrala": "ALL_WHEEL"}},
        "door_count": {"confirmed": False, "param": "doorCount",  # sursa: search-api.html
                       "values": {"2_3": "TWO_OR_THREE", "4_5": "FOUR_OR_FIVE"}},
        # 13 culori reale din refdata/colors (cod:eticheta): BLACK/GREY/BEIGE/BROWN/RED/GREEN/
        # BLUE/PURPLE/GOLD/WHITE/ORANGE/SILVER/YELLOW.
        "color": {"confirmed": False, "param": "exteriorColor",  # sursa: refdata/colors
                  "values": {"negru": "BLACK", "gri": "GREY", "bej": "BEIGE", "maro": "BROWN",
                             "rosu": "RED", "verde": "GREEN", "albastru": "BLUE", "violet": "PURPLE",
                             "auriu": "GOLD", "alb": "WHITE", "portocaliu": "ORANGE",
                             "argintiu": "SILVER", "galben": "YELLOW"}},
        "engine_power_min": {"confirmed": False, "param": "power.min"},  # kW, sursa: search-api.html
        "engine_power_max": {"confirmed": False, "param": "power.max"},  # kW
        "seats_min": {"confirmed": False, "param": "numSeats.min"},      # sursa: search-api.html
        "seats_max": {"confirmed": False, "param": "numSeats.max"},
    },
    # ── AUTOSCOUT24 ── style "query", coduri scurte. Confirmate 2026-07-05 prin numberOfResults
    # din __NEXT_DATA__ (BASE atype=C=2122552). Fiecare cod de mai jos ingusteaza.
    "autoscout24": {
        # combustibil (fuel): B benzina 989156, D diesel 663573, E electric 116823, 2 gpl 289854,
        # 3 gnc 29816 (coduri AutoScout24 standard + confirmate ca ingusteaza). Hibrid: cod neclar
        # azi -> nu il mapam.
        "fuel_type": {"confirmed": True, "param": "fuel",
                      "values": {"benzina": "B", "diesel": "D", "electric": "E",
                                 "gpl": "2", "gnc": "3"}},
        # cutie (gear): M manual 829957, A automat 1235860, S semi 41960.
        "gearbox": {"confirmed": True, "param": "gear",
                    "values": {"manuala": "M", "automata": "A"}},
        "mileage_max": {"confirmed": True, "param": "kmto"},           # kmto=50000 -> 943140
        "power_unit": {"confirmed": True, "param": "powertype", "values": {"kw": "kw"}},
        "engine_power_min": {"confirmed": True, "param": "powerfrom"}, # powerfrom=110(&powertype=kw) -> 1032548
        "engine_power_max": {"confirmed": True, "param": "powerto"},
        "year_min": {"confirmed": True, "param": "fregfrom"},          # fregfrom=2020 -> 1337243
        "year_max": {"confirmed": True, "param": "fregto"},
        "door_count_min": {"confirmed": True, "param": "doorfrom"},    # doorfrom=5 -> 1486666
        "seats_min": {"confirmed": True, "param": "seatsfrom"},        # seatsfrom=7 -> 85737
        # caroseria (param "body", coduri 1-7) SI culoarea (param "bcol", coduri 1-6) ingusteaza
        # (deci PARAM-ul e real), DAR maparea cod->tip nu a putut fi verificata pe continut azi
        # (bodyType lipseste din __NEXT_DATA__) -> confirmed False, nu le conectam cu valori ghicite.
        "body_type": {"confirmed": False, "param": "body"},   # coduri 1..7 valide (ingusteaza), mapare neverificata
        "color": {"confirmed": False, "param": "bcol"},       # coduri 1..6 valide (ingusteaza), mapare neverificata
    },
    # ── KLEINANZEIGEN ── style "path_suffix" "+autos.CAMP:VALOARE" dupa /c216. NERETESTAT COMPLET
    # azi: platforma NU expune un total numeric de rezultate + soft-throttling dupa multe cereri
    # (pagina intoarce 0 carduri). Pastram valorile confirmate live in runda anterioara (scraperul
    # a intors 27 anunturi VW reale cu aceste filtre). Valori suplimentare de combustibil/caroserie
    # raman de confirmat cand platforma nu throttle-uieste.
    "kleinanzeigen_auto": {
        "fuel_type": {"confirmed": True, "param": "autos.fuel_s", "style": "path_suffix",
                      "values": {"benzina": "benzin"}},  # doar benzin confirmat; diesel/rest de reverificat
        "gearbox": {"confirmed": True, "param": "autos.shift_s", "style": "path_suffix",
                    "values": {"automata": "automatik"}},
        "mileage_max": {"confirmed": True, "param": "autos.km_i", "style": "path_suffix"},  # ",MAX"
        "body_type": {"confirmed": True, "param": "autos.typ_s", "style": "path_suffix",
                      "values": {"suv": "suv", "combi": "kombi"}},
        "make": {"confirmed": True, "param": "autos.marke_s", "style": "path_suffix"},
        "year_min": {"confirmed": True, "param": "autos.ez_i", "style": "path_suffix"},  # "MIN,MAX"
        # Parametri noi gasiti in biblioteca Go julez-dev/goebaykleinanzeigen (site public,
        # neautentificat). NECONFIRMATI 2026-07-05: mecanismul de sufix "+autos.X:Y" a intors
        # 0 carduri din acest mediu (baza fara sufix = 27), INCLUSIV pentru un param cunoscut-bun
        # (autos.marke_s) -> soft-block anti-bot pe pattern-ul de sufix, nu specific acestor 3.
        # De reverificat cand platforma nu blocheaza sufixele. confirmed:False -> nu se conecteaza.
        "model": {"confirmed": False, "param": "autos.model_s", "style": "path_suffix"},  # model ca text
        "power_i_kw": {"confirmed": False, "param": "autos.power_i", "style": "path_suffix"},  # putere (interval?)
        "tuev_year": {"confirmed": False, "param": "autos.tuevy_i", "style": "path_suffix"},  # an valabilitate ITP
        # Sursa: julez-dev/goebaykleinanzeigen (site PUBLIC — baseURL "ebay-kleinanzeigen.de";
        # searchparam.go:52-54 Provider privat/gewerblich, :144-152 fmtProvider -> "/anbieter:VAL").
        # Vanzator (persoana fizica vs dealer) — CONFIRMAT FUNCTIONAL live 2026-07-05:
        # /anbieter:privat/c216 vs /anbieter:gewerblich/c216 sunt DISJUNCTE (Jaccard 0.00, ambele
        # 27 carduri, ambele != /c216 root). DAR merge DOAR in structura category-root
        # "/anbieter:VAL/c216", NU in structura scraperului nostru "/s-autos/{keyword}/c216"
        # (acolo a intors 0). Deci confirmed:False: e un segment de PATH inainte de /c216, nu un
        # sufix "+autos." — necesita modificare de scraper (alta structura URL) ca sa fie conectat.
        "seller_type": {"confirmed": False, "param": "anbieter",  # format /anbieter:VAL/ (NU +sufix)
                        "values": {"persoana_fizica": "privat", "dealer": "gewerblich"}},
    },
}


def apply_confirmed_filters(platform: str, filters: dict, params: dict,
                            aliases: dict | None = None) -> str:
    """Aplica DOAR campurile tehnice cu "confirmed": True ale platformei. Suporta 4 stiluri
    de aplicare (cheia "style" din spec; implicit "query" = comportamentul vechi, neschimbat):

      - "query"             : params[param] = valoare (mapata daca are "values").
      - "query_repeat"      : lista -> param repetat (params[param] = [v1, v2]); single -> v.
      - "query_range_colon" : params[param] = "MIN:MAX" (capat gol daca lipseste bound-ul).
      - "path_suffix"       : NU scrie in params; acumuleaza "+param:val" (param _i -> "MIN,MAX").

    Intoarce `path_suffix` (str): "" daca niciun camp path_suffix, altfel "+p1:v1+p2:v2".
    `aliases`: field_key -> cheie alternativa in filters (ex. scanner-ul trimite "fuel"/"body"/
    "km_max" in loc de "fuel_type"/"body_type"/"mileage_max"). Enum-uri: valoarea se trimite
    DOAR daca e in "values" (confirmata); altfel se sare — nu inventam.
    """
    tech = AUTO_TECHNICAL_FIELDS.get(platform) or {}
    aliases = aliases or {}
    path_parts = []

    def _get(key):
        v = filters.get(key)
        if v in (None, "") and key in aliases:
            v = filters.get(aliases[key])
        return v

    def _map(spec, val):
        vm = spec.get("values")
        return val if vm is None else vm.get(val)  # None daca valoarea nu e confirmata

    def _range_pair(field_key):
        # "price_min"/"mileage_max" -> baza "price"/"mileage"; citeste ambele capete.
        base = field_key.rsplit("_", 1)[0]
        lo, hi = _get(f"{base}_min"), _get(f"{base}_max")
        if hi in (None, "") and field_key.endswith("_max"):
            hi = _get(field_key)  # aliasul poate fi pe field_key exact (ex mileage_max->km_max)
        if lo in (None, "") and field_key.endswith("_min"):
            lo = _get(field_key)
        if lo in (None, "") and hi in (None, ""):
            return None
        return ("" if lo in (None, "") else str(lo), "" if hi in (None, "") else str(hi))

    for field_key, spec in tech.items():
        if not isinstance(spec, dict) or not spec.get("confirmed"):
            continue
        param = spec.get("param")
        if not param:
            continue
        style = spec.get("style") or "query"

        if style == "query_range_colon":
            pair = _range_pair(field_key)
            if pair is not None:
                params[param] = f"{pair[0]}:{pair[1]}"

        elif style == "query_repeat":
            val = _get(field_key)
            if val in (None, ""):
                continue
            items = val if isinstance(val, (list, tuple)) else [val]
            mapped = [m for m in (_map(spec, it) for it in items) if m is not None]
            if mapped:
                params[param] = mapped if len(mapped) > 1 else mapped[0]

        elif style == "path_suffix":
            if param.endswith("_i"):  # interval numeric (ez_i/km_i) -> "MIN,MAX"
                pair = _range_pair(field_key)
                if pair is not None:
                    path_parts.append(f"{param}:{pair[0]},{pair[1]}")
            else:  # _s string/enum
                m = _map(spec, _get(field_key)) if _get(field_key) not in (None, "") else None
                if m is not None:
                    path_parts.append(f"{param}:{str(m).lower()}")

        else:  # "query" (implicit) — comportament vechi
            val = _get(field_key)
            if val in (None, ""):
                continue
            m = _map(spec, val)
            if m is not None:
                params[param] = m

    return ("+" + "+".join(path_parts)) if path_parts else ""

