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
        "fuel_type": {"confirmed": True, "param": "fuel"},  # nume exact din documentatia oficiala
        "gearbox": {"confirmed": True, "param": "gearbox"},
        "engine_power_min": {"confirmed": True, "param": "power"},  # kW
        "drivetrain": {"confirmed": True, "param": "wheelFormula",  # sau driveType — verifica live
                       "values": {"fata": "FRONT", "spate": "REAR", "integrala": "ALL_WHEEL"}},
        # NOTA: parametrii oficiali sunt documentati pentru Search API (cu autentificare).
        # Scraper-ul actual e curl_cffi pe HTML public — VERIFICA live daca interfata publica
        # de cautare (suchen.mobile.de) accepta acesti parametri identic sau cu alt nume
        # (am confirmat doar vc=Car pentru vehicleClass pe interfata publica).
    },
    "autoscout24": {
        "mileage_max": {"confirmed": True, "param": "kmto"},
        "power_unit": {"confirmed": True, "param": "powertype", "values": {"kw": "kw"}},
        "fuel_type": None,  # NECONFIRMAT pe endpoint-ul modern /lst — nu implementa cu valori ghicite
        "gearbox": None,  # idem
    },
    "kleinanzeigen_auto": {
        "make": {"confirmed": True, "param": "autos.marke_s"},  # sintaxa: autos.{camp}_s:{valoare}
        "year": {"confirmed": True, "param": "autos.ez_i"},  # sintaxa: autos.{camp}_i:{valoare}
        "fuel_type": None,  # camp exista (confirmat ca "unmapped filter" intr-un proiect open
        # source), dar cheia exacta NU e confirmata — NU presupune "autos.kraftstoff_s"
        "gearbox": None,  # idem, posibil "autos.getriebe_s" dar NECONFIRMAT
    },
}


def apply_confirmed_filters(platform: str, filters: dict, params: dict,
                            aliases: dict | None = None) -> None:
    """Scrie in `params` DOAR campurile tehnice cu "confirmed": True ale platformei,
    citind valorile din `filters` (cheia = numele campului, ex. "fuel_type").

    - `aliases`: field_key -> cheie alternativa in filters (ex. scanner-ul auto trimite
      "fuel"/"body" in loc de "fuel_type"/"body_type").
    - Enum-uri (spec cu "values"): valoarea se trimite DOAR daca e in `values` (confirmata);
      altfel se sare — nu inventam un cod/slug pentru valori neconfirmate.
    - Campuri fara "values" (numerice): valoarea se trimite ca atare.
    NU inventeaza nimic: sursa de adevar pt param/values e AUTO_TECHNICAL_FIELDS.
    """
    tech = AUTO_TECHNICAL_FIELDS.get(platform) or {}
    aliases = aliases or {}
    for field_key, spec in tech.items():
        if not isinstance(spec, dict) or not spec.get("confirmed"):
            continue
        param = spec.get("param")
        if not param:
            continue
        val = filters.get(field_key)
        if val in (None, "") and field_key in aliases:
            val = filters.get(aliases[field_key])
        if val in (None, ""):
            continue
        values_map = spec.get("values")
        if values_map is not None:
            mapped = values_map.get(val)
            if mapped is None:
                continue  # valoare neconfirmata -> nu se trimite (nu inventam)
            val = mapped
        params[param] = val

