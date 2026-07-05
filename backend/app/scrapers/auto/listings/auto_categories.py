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
    "autovit": {
        # doar "petrol" a fost confirmat direct; hybrid/electric/lpg sunt presupunere
        # rezonabila de enum — marcate # VERIFY, de testat live inainte de a te baza pe ele.
        "fuel_type": {"confirmed": True, "param": "search[filter_enum_fuel_type]",
                      "values": {"benzina": "petrol", "diesel": "diesel", "hibrid": "hybrid",  # hibrid # VERIFY
                                 "electric": "electric", "gpl": "lpg"}},  # electric # VERIFY, gpl # VERIFY
        # confirmat pe otomoto.pl (aceeasi platforma), NEtestat direct pe autovit.ro
        "gearbox": {"confirmed": False, "param": "search[filter_enum_gearbox]",
                    "values": {"manuala": "manual", "automata": "automatic"}},
        # idem, confirmat pe otomoto.pl, NEtestat pe autovit.ro
        "engine_power_min": {"confirmed": False, "param": "search[filter_float_engine_power:from]"},
    },
    "olx_auto": {
        # doar benzina/diesel confirmate direct; hibrid/electric/gpl NECONFIRMATE (VERIFY)
        "fuel_type": {"confirmed": True, "param": "search[filter_enum_petrol]",
                      "values": {"benzina": "petrol", "diesel": "diesel"}},
        "engine_capacity_min": {"confirmed": True, "param": "search[filter_float_enginesize:from]"},
        "engine_capacity_max": {"confirmed": True, "param": "search[filter_float_enginesize:to]"},
        # doar sedan confirmat direct, restul valorilor de body VERIFY
        "body_type": {"confirmed": True, "param": "search[filter_enum_car_body]",
                      "values": {"sedan": "sedan"}},
        "condition": {"confirmed": True, "param": "search[filter_enum_state]",
                      "values": {"rulat": "used"}},
        # doar "business" confirmat direct; valoarea pt persoana fizica NECONFIRMATA (poate fi
        # "private" sau lipsa parametrului = ambele) → o lasam None, deci nu se trimite.
        "seller_type": {"confirmed": True, "param": "search[private_business]",
                        "values": {"business": "business", "persoana_fizica": None}},
        "gearbox": None,  # NU EXISTA filtru structurat pe OLX — doar text liber. Nu implementa.
    },
    "mobile_de": {
        # REVIZUIT: confirmat pe interfata PUBLICA suchen.mobile.de (nu pe API-ul autentificat,
        # cum era gresit sursa inainte). Doar benzina/diesel/electric confirmate direct.
        "fuel_type": {"confirmed": True, "param": "ft", "style": "query_repeat",
                      "values": {"benzina": "PETROL", "diesel": "DIESEL", "electric": "ELECTRICITY"}},
                      # hibrid/gpl VERIFY — nu le adauga in values
        "year_min": {"confirmed": True, "param": "fr", "style": "query_range_colon"},   # fr=MIN:MAX
        "price_min": {"confirmed": True, "param": "p", "style": "query_range_colon"},    # p=MIN:MAX
        "mileage_max": {"confirmed": True, "param": "ml", "style": "query_range_colon"}, # ml=MIN:MAX
        "gearbox": None,  # NECONFIRMAT pe interfata publica — cautat activ azi, niciun exemplu real
                          # (desi documentatia API autentificat il mentioneaza).
        "engine_power_min": None,  # un candidat "pw=" gasit o singura data, insuficient de sigur.
        "drivetrain": None,  # eliminat wheelFormula — venea din documentatia API gresita.
    },
    "autoscout24": {
        "mileage_max": {"confirmed": True, "param": "kmto"},
        "power_unit": {"confirmed": True, "param": "powertype", "values": {"kw": "kw"}},
        "fuel_type": None,  # NECONFIRMAT pe endpoint-ul modern /lst — nu implementa cu valori ghicite
        "gearbox": None,  # idem
    },
    "kleinanzeigen_auto": {
        # REVIZUIT din exemple reale: filtrele merg ca SUFIX de path "+autos.CAMP:VALOARE" dupa
        # /c216 (style="path_suffix"). Sufix _s = string; _i = interval numeric "MIN,MAX".
        "fuel_type": {"confirmed": True, "param": "autos.fuel_s", "style": "path_suffix",
                      "values": {"benzina": "benzin"}},  # doar benzin confirmat; diesel/rest VERIFY
        "gearbox": {"confirmed": True, "param": "autos.shift_s", "style": "path_suffix",
                    "values": {"automata": "automatik"}},  # doar automatik confirmat; manual VERIFY
        "mileage_max": {"confirmed": True, "param": "autos.km_i", "style": "path_suffix"},  # ",MAX"
        "body_type": {"confirmed": True, "param": "autos.typ_s", "style": "path_suffix",
                      "values": {"suv": "suv", "combi": "kombi"}},  # doar aceste 2 confirmate
        "make": {"confirmed": True, "param": "autos.marke_s", "style": "path_suffix"},
        "year_min": {"confirmed": True, "param": "autos.ez_i", "style": "path_suffix"},  # "MIN,MAX"
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

