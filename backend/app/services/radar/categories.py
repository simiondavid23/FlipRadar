"""
Categorii per platforma — mapare display label -> valoare specifica scraper-ului.
OLX: slug URL (ex: "electronice-si-electrocasnice/telefoane-mobile")
Vinted: catalog ID ca string (ex: "2994"), convertit la int de scraper
Okazii/LaJumate/Publi24: slug URL
Facebook: category ID ca string
"""
from typing import Optional

PLATFORM_CATEGORIES = {
    "olx": [
        {
            "label": "Electronice și Electrocasnice",
            "value": "electronice-si-electrocasnice",
            "subcategories": [
                {"label": "Telefoane Mobile", "value": "electronice-si-electrocasnice/telefoane-mobile"},
                {"label": "Tablete", "value": "electronice-si-electrocasnice/tablete"},
                {"label": "Laptopuri", "value": "electronice-si-electrocasnice/laptop-calculator"},
                {"label": "Calculatoare și Accesorii", "value": "electronice-si-electrocasnice/calculatoare-si-accesorii"},  # VERIFY
                {"label": "Componente PC", "value": "electronice-si-electrocasnice/componente-pc"},  # VERIFY
                {"label": "Monitoare", "value": "electronice-si-electrocasnice/monitoare"},  # VERIFY
                {"label": "Imprimante și Consumabile", "value": "electronice-si-electrocasnice/imprimante-si-consumabile"},  # VERIFY
                {"label": "Audio-Video", "value": "electronice-si-electrocasnice/audio-video"},
                {"label": "Aparate Foto și Video", "value": "electronice-si-electrocasnice/aparate-foto-si-video"},  # VERIFY
                {"label": "Jocuri și Console", "value": "electronice-si-electrocasnice/console-jocuri-video"},
                {"label": "Accesorii IT", "value": "electronice-si-electrocasnice/accesorii-it"},  # VERIFY
                {"label": "Accesorii Telefoane", "value": "electronice-si-electrocasnice/accesorii-telefoane"},  # VERIFY
                {"label": "Ceasuri și Brătări Smart", "value": "electronice-si-electrocasnice/ceasuri-inteligente"},  # VERIFY
                {"label": "GPS și Navigatie", "value": "electronice-si-electrocasnice/gps-navigatie"},  # VERIFY
                {"label": "Electrocasnice Mari", "value": "electronice-si-electrocasnice/electrocasnice-mari"},  # VERIFY
                {"label": "Electrocasnice Mici", "value": "electronice-si-electrocasnice/electrocasnice-mici"},  # VERIFY
                {"label": "Climatizare și Ventilare", "value": "electronice-si-electrocasnice/climatizare"},  # VERIFY
            ],
        },
        {
            "label": "Modă și Accesorii",
            "value": "moda-si-accesorii",
            "subcategories": [
                {"label": "Haine Femei", "value": "moda-si-accesorii/haine-femei"},  # VERIFY
                {"label": "Haine Bărbati", "value": "moda-si-accesorii/haine-barbati"},  # VERIFY
                {"label": "Haine Copii", "value": "moda-si-accesorii/haine-copii"},  # VERIFY
                {"label": "Încăltăminte Femei", "value": "moda-si-accesorii/incaltaminte-femei"},  # VERIFY
                {"label": "Încăltăminte Bărbati", "value": "moda-si-accesorii/incaltaminte-barbati"},  # VERIFY
                {"label": "Încăltăminte Copii", "value": "moda-si-accesorii/incaltaminte-copii"},  # VERIFY
                {"label": "Genti și Portofele", "value": "moda-si-accesorii/genti-si-portofele"},  # VERIFY
                {"label": "Bijuterii și Ceasuri", "value": "moda-si-accesorii/bijuterii-si-ceasuri"},  # VERIFY
                {"label": "Ochelari", "value": "moda-si-accesorii/ochelari"},  # VERIFY
            ],
        },
        {
            "label": "Auto, Moto și Ambarcatiuni",
            "value": "auto-moto-si-ambarcatiuni",
            "subcategories": [
                {"label": "Autoturisme", "value": "auto-moto-si-ambarcatiuni/autoturisme"},  # VERIFY
                {"label": "Motociclete, Scutere și ATV", "value": "auto-moto-si-ambarcatiuni/motociclete-scutere-si-atv"},  # VERIFY
                {"label": "Autoutilitare și Camioane", "value": "auto-moto-si-ambarcatiuni/autoutilitare-si-camioane"},  # VERIFY
                {"label": "Piese Auto", "value": "auto-moto-si-ambarcatiuni/piese-auto"},  # VERIFY
                {"label": "Accesorii Auto-Moto", "value": "auto-moto-si-ambarcatiuni/accesorii-auto-si-moto"},  # VERIFY
                {"label": "Rulote și Remorci", "value": "auto-moto-si-ambarcatiuni/rulote-si-remorci"},  # VERIFY
                {"label": "Ambarcatiuni", "value": "auto-moto-si-ambarcatiuni/ambarcatiuni"},  # VERIFY
            ],
        },
        {
            "label": "Casă și Grădină",
            "value": "casa-si-gradina",
            "subcategories": [
                {"label": "Mobilă", "value": "casa-si-gradina/mobila"},  # VERIFY
                {"label": "Decoratiuni Interioare", "value": "casa-si-gradina/decoratiuni-interioare"},  # VERIFY
                {"label": "Grădinărit", "value": "casa-si-gradina/gradinarit"},  # VERIFY
                {"label": "Bricolaj și Scule", "value": "casa-si-gradina/bricolaj"},  # VERIFY
                {"label": "Articole de Uz Casnic", "value": "casa-si-gradina/articole-casnice"},  # VERIFY
                {"label": "Iluminat", "value": "casa-si-gradina/iluminat"},  # VERIFY
                {"label": "Curătenie", "value": "casa-si-gradina/curatenie"},  # VERIFY
            ],
        },
        {
            "label": "Sport, Timp Liber și Hobby",
            "value": "sport-timp-liber-si-hobby",
            "subcategories": [
                {"label": "Biciclete și Trotinete", "value": "sport-timp-liber-si-hobby/biciclete-si-trotinete"},  # VERIFY
                {"label": "Fitness și Sport", "value": "sport-timp-liber-si-hobby/fitness-si-sport"},  # VERIFY
                {"label": "Echipament Sportiv", "value": "sport-timp-liber-si-hobby/echipament-sportiv"},  # VERIFY
                {"label": "Muzică și Instrumente", "value": "sport-timp-liber-si-hobby/muzica-si-instrumente"},  # VERIFY
                {"label": "Jucării", "value": "sport-timp-liber-si-hobby/jucarii"},  # VERIFY
                {"label": "Cărti și Reviste", "value": "sport-timp-liber-si-hobby/carti-reviste-si-muzica"},  # VERIFY
                {"label": "Colectii și Artă", "value": "sport-timp-liber-si-hobby/colectii-si-arta"},  # VERIFY
                {"label": "Vânătoare și Pescuit", "value": "sport-timp-liber-si-hobby/vanatoare-si-pescuit"},  # VERIFY
            ],
        },
        {
            "label": "Animale de Companie",
            "value": "animale-de-companie",
            "subcategories": [
                {"label": "Câini", "value": "animale-de-companie/caini"},  # VERIFY
                {"label": "Pisici", "value": "animale-de-companie/pisici"},  # VERIFY
                {"label": "Accesorii Animale", "value": "animale-de-companie/accesorii-animale"},  # VERIFY
                {"label": "Alte Animale", "value": "animale-de-companie/alte-animale"},  # VERIFY
            ],
        },
        {
            "label": "Copii și Mame",
            "value": "copii-si-mame",
            "subcategories": [
                {"label": "Haine și Încăltăminte", "value": "copii-si-mame/haine-si-incaltaminte"},  # VERIFY
                {"label": "Jucării și Jocuri", "value": "copii-si-mame/jucarii-si-jocuri"},  # VERIFY
                {"label": "Cărucioare și Scaune Auto", "value": "copii-si-mame/carucioare-si-scaune-auto"},  # VERIFY
                {"label": "Mobilier Copii", "value": "copii-si-mame/mobilier-copii"},  # VERIFY
                {"label": "Articole Bebe", "value": "copii-si-mame/articole-bebe"},  # VERIFY
            ],
        },
    ],

    "vinted": [
        # Valorile sunt catalog_id-uri Vinted validate 2026-07-03 contra arborelui live
        # (VINTED_CATALOG_ID_MAP din vinted_scraper.py, construit din /api/v2/catalog).
        # Comentariul arata calea reala Tab > Categorie > Subcategorie. Cateva subcategorii
        # inventate (grupe de varsta, "Echipament sportiv" generic, camasi, hanorace) NU au
        # nod echivalent pe Vinted -> colapseaza la cel mai apropiat nod real. Vechile ID-uri
        # (multe gresite — ex. Telefoane=2995 = de fapt "Alte dispozitive") sunt remapate pe
        # datele deja salvate de migrarea remap_vinted_category_ids_to_live_tree (db_migrate).
        {
            "label": "Femei",
            "value": "1904",  # Femei
            "subcategories": [
                {"label": "Topuri și Bluze", "value": "12"},   # Femei > Haine > Topuri și tricouri
                {"label": "Rochii", "value": "10"},            # Femei > Haine > Rochii
                {"label": "Pantaloni și Colanti", "value": "9"},    # Femei > Haine > Pantaloni și colanți
                {"label": "Blugi", "value": "183"},            # Femei > Haine > Blugi
                {"label": "Fuste", "value": "11"},             # Femei > Haine > Fuste
                {"label": "Jachete și Paltoane", "value": "1037"},  # Femei > Haine > Îmbrăcăminte de exterior
                {"label": "Pulovere și Cardigan", "value": "13"},   # Femei > Haine > Pulovere
                {"label": "Hanorace", "value": "4"},           # Femei > Haine (fara nod dedicat)
                {"label": "Lenjerie și Pijamale", "value": "29"},   # Femei > Haine > Lenjerie intimă și pijamale
                {"label": "Costume de Baie", "value": "28"},   # Femei > Haine > Costume de baie
                {"label": "Ciorapi și Dresuri", "value": "4"}, # Femei > Haine (fara nod dedicat)
            ],
        },
        {
            "label": "Bărbati",
            "value": "5",  # Bărbați
            "subcategories": [
                {"label": "Tricouri și Maiouri", "value": "76"},    # Bărbați > Haine > Topuri și tricouri
                {"label": "Cămăși", "value": "2050"},          # Bărbați > Haine (fara nod dedicat)
                {"label": "Pantaloni", "value": "34"},         # Bărbați > Haine > Pantaloni
                {"label": "Blugi", "value": "257"},            # Bărbați > Haine > Blugi
                {"label": "Pulovere și Cardigane", "value": "79"},  # Bărbați > Haine > Pulovere
                {"label": "Hanorace", "value": "2050"},        # Bărbați > Haine (fara nod dedicat)
                {"label": "Jachete și Paltoane", "value": "1206"},  # Bărbați > Haine > Îmbrăcăminte de exterior
                {"label": "Costume și Sacouri", "value": "32"},     # Bărbați > Haine > Costume și blazere
                {"label": "Pantaloni Scurti", "value": "80"},  # Bărbați > Haine > Pantaloni scurți
            ],
        },
        {
            "label": "Copii și Bebeluși",
            "value": "1193",  # Copii
            # Vinted nu filtreaza dupa varsta -> toate grupele colapseaza la tab-ul Copii.
            "subcategories": [
                {"label": "0-2 ani", "value": "1193"},   # Copii
                {"label": "3-5 ani", "value": "1193"},   # Copii
                {"label": "6-9 ani", "value": "1193"},   # Copii
                {"label": "10-14 ani", "value": "1193"}, # Copii
            ],
        },
        {
            "label": "Încăltăminte",
            "value": "1231",  # Bărbați > Pantofi (nu exista nod unic "toata incaltamintea")
            "subcategories": [
                {"label": "Femei", "value": "16"},       # Femei > Pantofi
                {"label": "Bărbati", "value": "1231"},   # Bărbați > Pantofi
                {"label": "Copii", "value": "1193"},     # Copii (fara nod dedicat pantofi copii)
            ],
        },
        {
            "label": "Genti și Accesorii",
            "value": "1187",  # Femei > Accesorii
            "subcategories": [
                {"label": "Genti", "value": "19"},        # Femei > Genți
                {"label": "Portofele", "value": "160"},   # Femei > Genți > Poșete și portofele
                {"label": "Bijuterii", "value": "21"},    # Femei > Accesorii > Bijuterii
                {"label": "Ceasuri", "value": "22"},      # Femei > Accesorii > Ceasuri
                {"label": "Ochelari", "value": "26"},     # Femei > Accesorii > Ochelari de soare
                {"label": "Pălării și Căciuli", "value": "88"},  # Femei > Accesorii > Pălării și șepci
                {"label": "Esarfe și Fular", "value": "89"},     # Femei > Accesorii > Fulare și eșarfe
            ],
        },
        {
            "label": "Sport",
            "value": "4332",  # Sporturi
            "subcategories": [
                {"label": "Echipament Sportiv", "value": "4332"},  # Sporturi (generic, fara nod unic)
                {"label": "Încăltăminte Sport", "value": "4332"},  # Sporturi (fara nod dedicat pantofi sport)
                {"label": "Fitness", "value": "4334"},    # Sporturi > Fitness, alergare și yoga
                {"label": "Sporturi Outdoor", "value": "4335"},    # Sporturi > Sporturi în aer liber
            ],
        },
        {
            "label": "Casă",
            "value": "1918",  # Casă
            "subcategories": [
                {"label": "Decoratiuni", "value": "1934"},       # Casă > Accesorii pentru casă
                {"label": "Lenjerie de Pat", "value": "1924"},   # Casă > Textile > Lenjerie de pat
                {"label": "Veselă și Tacâmuri", "value": "1920"},   # Casă > Articole de masă
                {"label": "Textile", "value": "1919"},           # Casă > Textile
            ],
        },
        {
            "label": "Frumusete",
            "value": "146",  # Femei > Frumusețe
            "subcategories": [
                {"label": "Cosmetice", "value": "964"},   # Femei > Frumusețe > Machiaj
                {"label": "Parfumuri", "value": "152"},   # Femei > Frumusețe > Parfum
                {"label": "Îngrijire Corp", "value": "956"},    # Femei > Frumusețe > Îngrijirea corpului
                {"label": "Îngrijire Păr", "value": "1902"},    # Femei > Frumusețe > Îngrijirea părului
            ],
        },
        {
            "label": "Electronice și Gadgeturi",
            "value": "2994",  # Electronice
            "subcategories": [
                {"label": "Telefoane", "value": "3661"},  # Electronice > Telefoane mobile și comunicare > Telefoane mobile
                {"label": "Tablete și E-readere", "value": "3567"},  # Electronice > Tablete, e-readere și accesorii
                {"label": "Căsti și Audio", "value": "3566"},   # Electronice > Audio, căști și hi-fi
                {"label": "Console și Jocuri", "value": "3002"},     # Electronice > Jocuri video și console
                {"label": "Laptopuri", "value": "3580"},  # Electronice > Calculatoare și accesorii > Laptopuri
            ],
        },
        {
            "label": "Cărti, Muzică și Film",
            "value": "2309",  # Media și cărți
            "subcategories": [
                {"label": "Cărti", "value": "2312"},      # Media și cărți > Cărți
                {"label": "Muzică", "value": "3036"},     # Media și cărți > Muzică
                {"label": "Film", "value": "3037"},       # Media și cărți > Video
            ],
        },
    ],

    "okazii": [
        {
            "label": "Fashion & Beauty",
            "value": None,
            "subcategories": [
                {"label": "Accesorii moda", "value": "accesorii-moda"},
                {"label": "Bijuterii", "value": "bijuterii"},
                {"label": "Ceasuri", "value": "ceasuri"},
                {"label": "Cosmetice femei", "value": "cosmetice-femei"},
                {"label": "Cosmetice barbati", "value": "cosmetice-barbati"},
                {"label": "Gravide si mamici", "value": "gravide-si-mamici"},
                {"label": "Handmade", "value": "handmade"},
                {"label": "Imbracaminte", "value": "imbracaminte"},
                {"label": "Incaltaminte", "value": "incaltaminte"},
                {"label": "Parfumuri", "value": "parfumuri"},
                {"label": "Nunta", "value": "nunta"},
                {"label": "Ochelari", "value": "ochelari"},
                {"label": "Produse sanatate", "value": "sanatate"},
                {"label": "Turism", "value": "turism"},
            ],
        },
        {
            "label": "Telefoane mobile & Tablete",
            "value": None,
            "subcategories": [
                {"label": "Accesorii GSM", "value": "accesorii-gsm"},
                {"label": "Accesorii tablete", "value": "accesorii-tablete"},
                {"label": "Cartela SIM", "value": "cartele-sim"},
                {"label": "Piese telefoane", "value": "piese-telefoane"},
                {"label": "Piese tablete", "value": "piese-tablete"},
                {"label": "Servicii gsm", "value": "servicii-gsm"},
                {"label": "Tablete", "value": "tablete"},
                {"label": "Telefoane mobile", "value": "telefoane-mobile-si-smartphones"},
            ],
        },
        {
            "label": "Laptop, Computere, Gadgets",
            "value": None,
            "subcategories": [
                {"label": "Accesorii laptop", "value": "accesorii-laptop"},
                {"label": "Componente PC", "value": "componente-computere"},
                {"label": "Computere", "value": "computere"},
                {"label": "Gadget", "value": "gadget"},
                {"label": "Imprimante", "value": "imprimante"},
                {"label": "Laptop", "value": "laptopuri"},
                {"label": "Monitoare", "value": "monitoare"},
                {"label": "Piese si componente laptop", "value": "piese-componente-laptop"},
                {"label": "Accesorii computere", "value": "periferice-multimedia"},
                {"label": "Produse retelistica", "value": "retelistica-telecomunicatii"},
            ],
        },
        {
            "label": "Electrocasnice",
            "value": None,
            "subcategories": [
                {"label": "Aer conditionat si incalzire", "value": "aer-conditionat-incalzire"},
                {"label": "Aragaze si hote", "value": "aragazuri-hote"},
                {"label": "Aparate frigorifice", "value": "aparate-frigorifice"},
                {"label": "Aspiratoare", "value": "aspiratoare"},
                {"label": "Cuptoare", "value": "cuptoare"},
                {"label": "Electrocasnice mici pentru bucatarie", "value": "electrocasnice-mici-bucatarie"},
                {"label": "Espressoare, cafetiere, cafea", "value": "espressoare-cafetiere-cafea"},
                {"label": "Fiare si statii de calcat", "value": "fiare-statii-calcat"},
                {"label": "Electrocasnice ingrijire personala", "value": "ingrijire-personala"},
                {"label": "Masini de spalat", "value": "masini-de-spalat"},
            ],
        },
        {
            "label": "TV, Electronice & Foto",
            "value": None,
            "subcategories": [
                {"label": "Aparate foto", "value": "aparate-foto"},
                {"label": "Audio", "value": "audio"},
                {"label": "Camere video si accesorii", "value": "camere-video-si-accesorii"},
                {"label": "Componente electronice", "value": "componente-electronice"},
                {"label": "Console jocuri si gaming", "value": "console-jocuri-si-accesorii"},
                {"label": "Echipamente DJ si studio", "value": "echipamente-dj-si-studio"},
                {"label": "Home Cinema si Media Player", "value": "homecinema"},
                {"label": "Receivere, antene si accesorii tv", "value": "receivere-antene-accesorii-tv"},
                {"label": "Sisteme de supraveghere", "value": "sisteme-supraveghere"},
                {"label": "Televizoare", "value": "televizoare"},
                {"label": "Videoproiectoare si accesorii", "value": "videoproiectoare-accesorii"},
                {"label": "Conectica", "value": "conectica"},
            ],
        },
        {
            "label": "Universul copiilor",
            "value": None,
            "subcategories": [
                {"label": "Alimentatia si ingrijirea copilului", "value": "alimentatia-si-ingrijirea-copilului"},
                {"label": "Camera copilului", "value": "camera-copilului"},
                {"label": "Carucioare copii si accesorii", "value": "carucioare-copii"},
                {"label": "Jucarii copii", "value": "jucarii-fete-si-baieti"},
                {"label": "Jocuri educative", "value": "jocuri-educative"},
                {"label": "Jucarii exterior", "value": "jucarii-exterior"},
                {"label": "Jucarii de interior", "value": "jucarii-interior-pentru-copii"},
                {"label": "Lego", "value": "jocuri-lego"},
                {"label": "Petreceri copii", "value": "petreceri-copii"},
                {"label": "Transportarea copiilor", "value": "transportarea-copiilor"},
            ],
        },
        {
            "label": "Librarie",
            "value": None,
            "subcategories": [
                {"label": "Accesorii instrumente muzicale", "value": "accesorii-instrumente-muzicale"},
                {"label": "Carti", "value": "carti"},
                {"label": "Filme", "value": "filme"},
                {"label": "Instrumente muzicale", "value": "instrumente-muzicale"},
                {"label": "Muzica", "value": "muzica"},
                {"label": "Papetarie si birotica", "value": "papetarie-si-birotica"},
            ],
        },
        {
            "label": "Artă și obiecte de colecție",
            "value": None,
            "subcategories": [
                {"label": "Antichitati", "value": "antichitati"},
                {"label": "Arta", "value": "arta"},
                {"label": "Carti postale", "value": "carti-postale"},
                {"label": "Colectii", "value": "colectii"},
                {"label": "Obiecte bisericesti", "value": "obiecte-bisericesti"},
                {"label": "Numismatica", "value": "numismatica"},
                {"label": "Timbre", "value": "timbre"},
            ],
        },
        {
            "label": "Casă, Grădină și Imobiliare",
            "value": None,
            "subcategories": [
                {"label": "Alimente", "value": "alimente"},
                {"label": "Bauturi", "value": "bauturi"},
                {"label": "Casa", "value": "casa"},
                {"label": "Decoratiuni", "value": "decoratiuni"},
                {"label": "Do it yourself", "value": "do-it-yourself"},
                {"label": "Gradina", "value": "gradina"},
                {"label": "Imobiliare", "value": "imobiliare"},
                {"label": "Materiale de constructii", "value": "materiale-de-constructii-si-amenajari"},
                {"label": "Mobila", "value": "mobila"},
                {"label": "Petshop", "value": "animale"},
                {"label": "Scule si unelte", "value": "scule-si-unelte"},
            ],
        },
        {
            "label": "Sport",
            "value": None,
            "subcategories": [
                {"label": "Accesorii sport", "value": "accesorii-sport"},
                {"label": "Airsoft", "value": "airsoft"},
                {"label": "Sporturi echipa", "value": "sport-echipa"},
                {"label": "Biciclete", "value": "biciclete"},
                {"label": "Fitness", "value": "fitness"},
                {"label": "Fan zone", "value": "fan-zone"},
                {"label": "Pescuit", "value": "pescuit"},
                {"label": "Outdoor", "value": "outdoor"},
                {"label": "Role si skateboard", "value": "role-si-skateboard"},
                {"label": "Sporturi de iarna", "value": "sporturi-de-iarna"},
                {"label": "Sporturi de camera", "value": "sporturi-de-camera"},
                {"label": "Sporturi nautice", "value": "sporturi-nautice"},
                {"label": "Vanatoare", "value": "vanatoare"},
                {"label": "Sporturi cu paleta", "value": "sporturi-cu-paleta"},
                {"label": "Sporturi de precizie", "value": "sporturi-de-precizie"},
                {"label": "Sporturi contact", "value": "sporturi-contact"},
            ],
        },
        {
            "label": "Auto-moto, piese, accesorii",
            "value": None,
            "subcategories": [
                {"label": "Accesorii si consumabile auto", "value": "accesorii-si-consumabile-auto"},
                {"label": "Anvelope si jante", "value": "anvelope-si-jante"},
                {"label": "ATV-uri si Accesorii", "value": "atv-si-accesorii"},
                {"label": "Anunturi auto gratuite", "value": "anunturi-auto"},
                {"label": "Barci", "value": "barci"},
                {"label": "Detectoare si statii radio", "value": "detectoare-si-statii-radio"},
                {"label": "Dezmembrari", "value": "dezmembrari"},
                {"label": "Diagnoza si manuale auto", "value": "diagnoza-si-manuale"},
                {"label": "Echipament moto", "value": "echipament-moto"},
                {"label": "GPS & Accesorii", "value": "gps"},
                {"label": "Multimedia auto", "value": "audio-video-auto"},
                {"label": "Piese auto", "value": "piese-auto"},
                {"label": "Piese si accesorii moto", "value": "piese-si-accesorii-moto"},
                {"label": "Scule si echipamente service", "value": "scule-echipamente-service"},
                {"label": "Scutere si vehicule electrice", "value": "scutere-si-mopede"},
                {"label": "Tuning", "value": "tuning"},
                {"label": "Motociclete", "value": "motociclete"},
            ],
        },
    ],

    "facebook": [
        # Taxonomie descoperita LIVE 2026-07-04 (curl_cffi + sesiune reala). "value" =
        # marketplace_listing_category_id, folosit pentru filtrare CLIENT-SIDE in
        # search_facebook (NU &category= in URL). Etichete traduse in romana, stil
        # consistent cu restul platformelor. Comentariile pastreaza numele oficial FB
        # (engleza) + share/n/incredere din esantionare, pentru trasabilitate.
        # NOTA: id-uri duplicate intre categorii nelegate (zgomot de esantionare pe
        # pagini cu inventar RO redus) au fost eliminate — pastrata doar eticheta cu
        # incredere/esantion mai mare.
        {
            "label": "Îmbrăcăminte", "value": None,
            "subcategories": [
                {"label": "Genți și Bagaje", "value": "1567543000236608"},  # Bags & Luggage HIGH share=1.0 n=20
                {"label": "Damă", "value": "1266429133383966"},  # Women's HIGH share=1.0 n=20
                {"label": "Bărbați", "value": "931157863635831"},  # Men's HIGH share=1.0 n=20
                {"label": "Bijuterii și Accesorii", "value": "214968118845643"},  # Jewelry & Accessories HIGH share=0.88 n=24
            ],
        },
        {"label": "Mica Publicitate", "value": None, "subcategories": []},  # Classifieds
        {
            "label": "Electronice", "value": "1792291877663080",  # Electronics vertical mono-id share=0.95 n=20
            "subcategories": [
                {"label": "Telefoane Mobile", "value": "1557869527812749"},  # Cell Phones HIGH share=1.0 n=20
                {"label": "Jocuri și Console", "value": "686977074745292"},  # Video Games & Consoles MED share=0.75 n=20
            ],
        },
        {
            "label": "Divertisment", "value": None,
            "subcategories": [
                {"label": "Cărți, Filme și Muzică", "value": "613858625416355"},  # Books, Movies & Music HIGH share=1.0 n=20
            ],
        },
        {
            "label": "Familie", "value": None,
            "subcategories": [
                {"label": "Articole Bebeluși și Copii", "value": "624859874282116"},  # Baby & Kids Items HIGH share=1.0 n=20
                {"label": "Sănătate și Frumusețe", "value": "1555452698044988"},  # Health & Beauty HIGH share=1.0 n=20
            ],
        },
        {"label": "Gratuități", "value": None, "subcategories": []},  # Free Stuff
        {"label": "Grădină și Exterior", "value": "800089866739547", "subcategories": []},  # Garden & Outdoor vertical mono-id, confirmat din arborele oficial FB create-item (before/after 74->49, 66%)
        {
            "label": "Hobby-uri", "value": None,
            "subcategories": [
                {"label": "Biciclete", "value": "1658310421102081"},  # Bicycles HIGH share=1.0 n=24
                {"label": "Piese Auto", "value": "757715671026531"},  # Auto Parts HIGH share=1.0 n=20
                {"label": "Artă și Creație", "value": "1534799543476160"},  # Arts & Crafts HIGH share=1.0 n=11
                {"label": "Antichități și Obiecte de Colecție", "value": "393860164117441"},  # Antiques & Collectibles HIGH share=0.85 n=20
            ],
        },
        {
            "label": "Articole pentru Casă", "value": None,
            "subcategories": [
                {"label": "Electrocasnice", "value": "678754142233400"},  # Appliances HIGH share=1.0 n=20
                {"label": "Mobilă", "value": "1583634935226685"},  # Furniture HIGH share=0.9 n=20
                {"label": "Lenjerii și Textile", "value": "1569171756675761"},  # Bedding HIGH share=0.85 n=20
            ],
        },
        {
            "label": "Bricolaj și Amenajări", "value": None,
            "subcategories": [
                {"label": "Unelte", "value": "1670493229902393"},  # Tools HIGH share=1.0 n=20
            ],
        },
        {"label": "Vânzări Imobiliare", "value": None, "subcategories": []},  # Home Sales
        {"label": "Instrumente Muzicale", "value": "676772489112490", "subcategories": []},  # Musical Instruments vertical mono-id share=1.0 n=20 (subcateg. Percussion eliminata: filtra 24->1, B1)
        {"label": "Papetărie și Birou", "value": None, "subcategories": []},  # Office Supplies
        {"label": "Articole pentru Animale", "value": "1550246318620997", "subcategories": []},  # Pet Supplies vertical mono-id, confirmat din arborele oficial FB create-item (before/after 52->17, 33%)
        {"label": "Chirii Imobiliare", "value": "1468271819871448", "subcategories": []},  # Property Rentals vertical mono-id share=0.96 n=24
        {"label": "Articole Sportive", "value": "1383948661922113", "subcategories": []},  # Sporting Goods vertical mono-id share=1.0 n=20
        {"label": "Jucării și Jocuri", "value": "606456512821491", "subcategories": []},  # Toys & Games vertical mono-id share=0.95 n=20
        {"label": "Auto, Moto și Ambarcațiuni", "value": "807311116002614", "subcategories": []},  # Vehicles vertical mono-id share=1.0 n=20 — coincide cu vechiul CONFIRMED
    ],

    "lajumate": [
        {
            "label": "Agro si Industrie",
            "value": "agro-si-industrie",
            "subcategories": [
                {"label": "Animale domestice si pasari", "value": "agro-si-industrie/animale-domestice-si-pasari"},
                {"label": "Cereale - plante - pomi", "value": "agro-si-industrie/cereale-plante-pomi"},
                {"label": "Echipamente si articole zootehnie", "value": "agro-si-industrie/echipamente-si-articole-zootehnie"},
                {"label": "Produse piata - alimentatie", "value": "agro-si-industrie/produse-piata-alimentatie"},
                {"label": "Utilaje agricole si industriale", "value": "agro-si-industrie/utilaje-agricole-si-industriale"},
            ],
        },
        {
            "label": "Animale de companie",
            "value": "animale-de-companie",
            "subcategories": [
                {"label": "Accesorii pentru animale de companie", "value": "animale-de-companie/accesorii-pentru-animale-de-companie"},
                {"label": "Adoptii", "value": "animale-de-companie/adoptii"},
                {"label": "Alte animale de companie", "value": "animale-de-companie/alte-animale-de-companie"},
                {"label": "Câini", "value": "animale-de-companie/caini"},
                {"label": "Mâncare și gustări pentru animale de companie", "value": "animale-de-companie/mancare-si-gustari-pentru-animale-de-companie"},
                {"label": "Pisici", "value": "animale-de-companie/pisici"},
                {"label": "Servicii pentru animale de companie", "value": "animale-de-companie/servicii-pentru-animale-de-companie"},
            ],
        },
        {
            "label": "Auto, moto si ambarcatiuni",
            "value": "auto-moto-si-ambarcatiuni",
            "subcategories": [
                {"label": "Ambarcatiuni", "value": "auto-moto-si-ambarcatiuni/ambarcatiuni"},
                {"label": "Autoturisme", "value": "auto-moto-si-ambarcatiuni/autoturisme"},
                {"label": "Autoutilitare", "value": "auto-moto-si-ambarcatiuni/autoutilitare"},
                {"label": "Camioane - Rulote - Remorci", "value": "auto-moto-si-ambarcatiuni/camioane-rulote-remorci"},
                {"label": "Motociclete", "value": "auto-moto-si-ambarcatiuni/motociclete"},
                {"label": "Scutere - ATV - UTV", "value": "auto-moto-si-ambarcatiuni/scutere-atv-utv"},
            ],
        },
        {
            "label": "Casa si gradina",
            "value": "casa-si-gradina",
            "subcategories": [
                {"label": "Articole menaj", "value": "casa-si-gradina/articole-menaj"},
                {"label": "Constructii", "value": "casa-si-gradina/constructii-casa-si-gradina"},
                {"label": "Decoratiuni pentru interior", "value": "casa-si-gradina/decoratiuni-pentru-interior"},
                {"label": "Finisaj interior", "value": "casa-si-gradina/finisaj-interior"},
                {"label": "Gradina", "value": "casa-si-gradina/gradina"},
                {"label": "Hale metalice, structuri metalice si containere", "value": "casa-si-gradina/hale-metalice-structuri-metalice-si-containere"},
                {"label": "Iluminat", "value": "casa-si-gradina/iluminat"},
                {"label": "Instalatii electrice", "value": "casa-si-gradina/instalatii-electrice"},
                {"label": "Instalatii sanitare", "value": "casa-si-gradina/instalatii-sanitare"},
                {"label": "Instalatii termice", "value": "casa-si-gradina/instalatii-termice"},
                {"label": "Mobila", "value": "casa-si-gradina/mobila"},
                {"label": "Scule, unelte, feronerie", "value": "casa-si-gradina/scule-unelte-feronerie"},
            ],
        },
        {
            "label": "Afaceri și echipamente profesionale",
            "value": "echipamente-profesionale-si-vanzare-companii",
            "subcategories": [
                {"label": "Alte echipamente profesionale", "value": "echipamente-profesionale-si-vanzare-companii/alte-echipamente-profesionale"},
                {"label": "Echipamente de lucru și protecție", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-de-lucru-si-protectie"},
                {"label": "Echipamente pentru evenimente", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-pentru-evenimente"},
                {"label": "Echipamente pentru industria textilă", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-pentru-industria-textila"},
                {"label": "Echipamente pentru magazine si birouri", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-pentru-magazine-si-birouri"},
                {"label": "Echipamente pentru reparații auto și spălătorii auto", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-pentru-reparatii-auto-si-spalatorii-auto"},
                {"label": "Echipamente profesionale de construcții", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-profesionale-de-constructii"},
                {"label": "Echipamente profesionale de curățenie", "value": "echipamente-profesionale-si-vanzare-companii/echipamente-profesionale-de-curatenie"},
                {"label": "Firme și licențe de vanzare", "value": "echipamente-profesionale-si-vanzare-companii/firme-si-licente-de-vanzare"},
                {"label": "Horeca", "value": "echipamente-profesionale-si-vanzare-companii/horeca"},
            ],
        },
        {
            "label": "Electronice si electrocasnice",
            "value": "electronice-si-electrocasnice",
            "subcategories": [
                {"label": "Accesorii telefoane & tablete", "value": "electronice-si-electrocasnice/accesorii-telefoane-tablete"},
                {"label": "Aparate medicale & Wellness", "value": "electronice-si-electrocasnice/aparate-medicale-wellness"},
                {"label": "Audio Hi Fi & Profesionale", "value": "electronice-si-electrocasnice/audio-hi-fi-profesionale"},
                {"label": "Casa inteligenta - Smarthome", "value": "electronice-si-electrocasnice/casa-inteligenta-smarthome"},
                {"label": "Casti Audio", "value": "electronice-si-electrocasnice/casti-audio"},
                {"label": "Componente Laptop-PC", "value": "electronice-si-electrocasnice/componente-laptop-pc"},
                {"label": "Drone & accesorii", "value": "electronice-si-electrocasnice/drone-accesorii"},
                {"label": "Electrocasnice", "value": "electronice-si-electrocasnice/electrocasnice"},
                {"label": "Gadgets, Wearables & Camere foto-video", "value": "electronice-si-electrocasnice/gadgets-wearables-camere-foto-video"},
                {"label": "Home Cinema & Audio", "value": "electronice-si-electrocasnice/home-cinema-audio"},
                {"label": "Imprimante, scannere", "value": "electronice-si-electrocasnice/imprimante-scannere"},
                {"label": "Ingrijire Personala", "value": "electronice-si-electrocasnice/ingrijire-personala"},
                {"label": "Laptop-Calculator-Gaming", "value": "electronice-si-electrocasnice/laptop-calculator-gaming"},
                {"label": "Periferice & Accesorii Laptop-PC-Gaming", "value": "electronice-si-electrocasnice/periferice-accesorii-laptop-pc-gaming"},
                {"label": "Piese telefoane & tablete", "value": "electronice-si-electrocasnice/piese-telefoane-tablete"},
                {"label": "Retelistica & Servere", "value": "electronice-si-electrocasnice/retelistica-servere"},
                {"label": "Tablete - eReadere", "value": "electronice-si-electrocasnice/tablete-ereadere"},
                {"label": "Telefoane", "value": "electronice-si-electrocasnice/telefoane"},
                {"label": "Televizoare si accesorii", "value": "electronice-si-electrocasnice/televizoare-si-accesorii"},
                {"label": "Videoproiectoare & Accesorii", "value": "electronice-si-electrocasnice/videoproiectoare-accesorii"},
            ],
        },
        {
            "label": "Imobiliare",
            "value": "imobiliare",
            "subcategories": [
                {"label": "Alte proprietati", "value": "imobiliare/alte-proprietati"},
                {"label": "Apartamente de inchiriat", "value": "imobiliare/apartamente-de-inchiriat"},
                {"label": "Apartamente de vanzare", "value": "imobiliare/apartamente-de-vanzare"},
                {"label": "Birouri - Spatii comerciale", "value": "imobiliare/birouri-spatii-comerciale"},
                {"label": "Case-Vile de inchiriat", "value": "imobiliare/case-vile-de-inchiriat"},
                {"label": "Case-Vile de vanzare", "value": "imobiliare/case-vile-de-vanzare"},
                {"label": "Caut coleg - Camere de inchiriat", "value": "imobiliare/caut-coleg-camere-de-inchiriat"},
                {"label": "Cazare-Turism", "value": "imobiliare/cazare-turism-imobiliare"},
                {"label": "Depozite si Hale de inchiriat", "value": "imobiliare/depozite-si-hale-de-inchiriat"},
                {"label": "Depozite si Hale de vanzare", "value": "imobiliare/depozite-si-hale-de-vanzare"},
                {"label": "Garsoniere de inchiriat", "value": "imobiliare/garsoniere-de-inchiriat"},
                {"label": "Garsoniere de vanzare", "value": "imobiliare/garsoniere-de-vanzare"},
                {"label": "Parcari si Garaje de inchiriat", "value": "imobiliare/parcari-si-garaje-de-inchiriat"},
                {"label": "Parcari si Garaje de vanzare", "value": "imobiliare/parcari-si-garaje-de-vanzare"},
                {"label": "Schimburi Imobiliare", "value": "imobiliare/schimburi-imobiliare"},
                {"label": "Terenuri", "value": "imobiliare/terenuri"},
            ],
        },
        {
            "label": "Inchiriere Bunuri si Vehicule",
            "value": "inchiriere-bunuri-si-vehicule",
            "subcategories": [
                {"label": "Închiriere Alte Articole", "value": "inchiriere-bunuri-si-vehicule/inchiriere-alte-articole"},
                {"label": "Închiriere Articole Modă & Copii", "value": "inchiriere-bunuri-si-vehicule/inchiriere-articole-moda-copii"},
                {"label": "Închiriere Articole Sport", "value": "inchiriere-bunuri-si-vehicule/inchiriere-articole-sport"},
                {"label": "Închiriere Echipament de Construcții", "value": "inchiriere-bunuri-si-vehicule/inchiriere-echipament-de-constructii"},
                {"label": "Închiriere Electronice & Jocuri", "value": "inchiriere-bunuri-si-vehicule/inchiriere-electronice-jocuri"},
                {"label": "Închiriere Materiale pentru Evenimente", "value": "inchiriere-bunuri-si-vehicule/inchiriere-materiale-pentru-evenimente"},
                {"label": "Închiriere Vehicule", "value": "inchiriere-bunuri-si-vehicule/inchiriere-vehicule"},
            ],
        },
        {
            "label": "Locuri de munca",
            "value": "locuri-de-munca",
            "subcategories": [
                {"label": "Agenti - consultanti vanzari", "value": "locuri-de-munca/agenti-consultanti-vanzari"},
                {"label": "Agricultura - Zootehnie", "value": "locuri-de-munca/agricultura-zootehnie"},
                {"label": "Alte locuri de munca", "value": "locuri-de-munca/alte-locuri-de-munca"},
                {"label": "Bone - Menajere", "value": "locuri-de-munca/bone-menajere"},
                {"label": "Call center - Suport clienti", "value": "locuri-de-munca/call-center-suport-clienti"},
                {"label": "Casieri - Lucratori comerciali", "value": "locuri-de-munca/casieri-lucratori-comerciali"},
                {"label": "Confectii - Croitori", "value": "locuri-de-munca/confectii-croitori"},
                {"label": "Cosmeticieni - Frizeri - Saloane", "value": "locuri-de-munca/cosmeticieni-frizeri-saloane"},
                {"label": "Educatie - Training", "value": "locuri-de-munca/educatie-training"},
                {"label": "Evenimente si divertisment", "value": "locuri-de-munca/evenimente-si-divertisment"},
                {"label": "Finante - contabilitate", "value": "locuri-de-munca/finante-contabilitate"},
                {"label": "Ingineri - Meseriasi - Constructori", "value": "locuri-de-munca/ingineri-meseriasi-constructori"},
                {"label": "Internship - Munca temporara - sezoniera", "value": "locuri-de-munca/internship-munca-temporara-sezoniera"},
                {"label": "IT - Telecomunicatii", "value": "locuri-de-munca/it-telecomunicatii"},
                {"label": "Lucratori productie - depozit - logistica", "value": "locuri-de-munca/lucratori-productie-depozit-logistica"},
                {"label": "Marketing - PR - Media", "value": "locuri-de-munca/marketing-pr-media"},
                {"label": "Munca in strainatate", "value": "locuri-de-munca/munca-in-strainatate"},
                {"label": "Paza si protectie", "value": "locuri-de-munca/paza-si-protectie"},
                {"label": "Personal administrativ - secretariat", "value": "locuri-de-munca/personal-administrativ-secretariat"},
                {"label": "Personal hotelier - restaurant", "value": "locuri-de-munca/personal-hotelier-restaurant"},
                {"label": "Personal medical", "value": "locuri-de-munca/personal-medical-locuri-de-munca"},
                {"label": "Resurse Umane", "value": "locuri-de-munca/resurse-umane"},
                {"label": "Soferi - Servicii auto - Curierat", "value": "locuri-de-munca/soferi-servicii-auto-curierat"},
                {"label": "Administrarea afacerii", "value": "locuri-de-munca/administrarea-afacerii"},
            ],
        },
        {
            "label": "Mama si copilul",
            "value": "mama-si-copilul",
            "subcategories": [
                {"label": "Alimentatie - Ingrijire", "value": "mama-si-copilul/alimentatie-ingrijire"},
                {"label": "Alte produse copii", "value": "mama-si-copilul/alte-produse-copii"},
                {"label": "Articole scolare - papetarie", "value": "mama-si-copilul/articole-scolare-papetarie"},
                {"label": "Camera copilului", "value": "mama-si-copilul/camera-copilului"},
                {"label": "Haine - Incaltaminte copii si gravide", "value": "mama-si-copilul/haine-incaltaminte-copii-si-gravide"},
                {"label": "Jocuri - Jucarii", "value": "mama-si-copilul/jocuri-jucarii"},
                {"label": "La plimbare", "value": "mama-si-copilul/la-plimbare"},
            ],
        },
        {
            "label": "Moda si frumusete",
            "value": "moda-si-frumusete",
            "subcategories": [
                {"label": "Accesorii", "value": "moda-si-frumusete/accesorii"},
                {"label": "Alte accesorii de moda si frumusete", "value": "moda-si-frumusete/alte-accesorii-de-moda-si-frumusete"},
                {"label": "Cadouri", "value": "moda-si-frumusete/cadouri"},
                {"label": "Ceasuri", "value": "moda-si-frumusete/ceasuri"},
                {"label": "Haine barbati", "value": "moda-si-frumusete/haine-barbati"},
                {"label": "Haine dama", "value": "moda-si-frumusete/haine-dama"},
                {"label": "Haine pentru gravide", "value": "moda-si-frumusete/haine-pentru-gravide"},
                {"label": "Haine pentru nunta", "value": "moda-si-frumusete/haine-pentru-nunta"},
                {"label": "Incaltaminte barbati", "value": "moda-si-frumusete/incaltaminte-barbati"},
                {"label": "Incaltaminte dama", "value": "moda-si-frumusete/incaltaminte-dama"},
                {"label": "Lenjerie si costume de baie dama", "value": "moda-si-frumusete/lenjerie-si-costume-de-baie-dama"},
                {"label": "Lenjerie si costume de inot barbati", "value": "moda-si-frumusete/lenjerie-si-costume-de-inot-barbati"},
                {"label": "Palarii, sepci si bandane", "value": "moda-si-frumusete/palarii-sepci-si-bandane"},
                {"label": "Sanatate si frumusete", "value": "moda-si-frumusete/sanatate-si-frumusete"},
            ],
        },
        {
            "label": "Piese auto",
            "value": "piese-auto",
            "subcategories": [
                {"label": "Alte piese", "value": "piese-auto/alte-piese"},
                {"label": "Piese Ambarcatiuni", "value": "piese-auto/piese-ambarcatiuni-auto"},
                {"label": "Piese Autoutilitare", "value": "piese-auto/piese-autoutilitare"},
                {"label": "Piese Camioane - Rulote - Remorci", "value": "piese-auto/piese-camioane-rulote-remorci"},
                {"label": "Piese Motociclete", "value": "piese-auto/piese-motociclete"},
                {"label": "Piese Scutere - ATV - UTV", "value": "piese-auto/piese-scutere-atv-utv"},
                {"label": "Caroserie - Interior", "value": "piese-auto/caroserie-interior"},
                {"label": "Consumabile - accesorii", "value": "piese-auto/consumabile-accesorii"},
                {"label": "Mecanica - electrica", "value": "piese-auto/mecanica-electrica"},
                {"label": "Roti - Jante- Anvelope", "value": "piese-auto/roti-jante-anvelope"},
                {"label": "Vehicule pentru dezmembrare", "value": "piese-auto/vehicule-pentru-dezmembrare"},
            ],
        },
        {
            "label": "Servicii",
            "value": "servicii",
            "subcategories": [
                {"label": "Cursuri - Meditatii", "value": "servicii/cursuri-meditatii"},
                {"label": "Evenimente", "value": "servicii/evenimente"},
                {"label": "Meseriasi - Constructori", "value": "servicii/meseriasi-constructori"},
                {"label": "Reparatii electrocasnice, electronice si telefoane", "value": "servicii/reparatii-electrocasnice-electronice-si-telefoane"},
                {"label": "Servicii Auto - Transport", "value": "servicii/servicii-auto-transport"},
                {"label": "Servicii de curatenie", "value": "servicii/servicii-de-curatenie"},
                {"label": "Servicii de infrumusetare", "value": "servicii/servicii-de-infrumusetare"},
                {"label": "Servicii diverse", "value": "servicii/servicii-diverse"},
                {"label": "Servicii medicale - Servicii de ingrijire - Croitorie", "value": "servicii/servicii-medicale-servicii-de-ingrijire-croitorie"},
                {"label": "Servicii specializate si servicii pentru afaceri", "value": "servicii/servicii-specializate-si-servicii-pentru-afaceri"},
            ],
        },
        {
            "label": "Sport, timp liber, arta",
            "value": "sport-timp-liber-arta",
            "subcategories": [
                {"label": "Airsoft", "value": "sport-timp-liber-arta/airsoft"},
                {"label": "Alergare", "value": "sport-timp-liber-arta/alergare"},
                {"label": "Alpinism, escalada", "value": "sport-timp-liber-arta/alpinism-escalada"},
                {"label": "Arta - Obiecte de colectie", "value": "sport-timp-liber-arta/arta-obiecte-de-colectie"},
                {"label": "Baschet", "value": "sport-timp-liber-arta/baschet"},
                {"label": "Basebal", "value": "sport-timp-liber-arta/basebal"},
                {"label": "Biciclete – Fitness - Suplimente", "value": "sport-timp-liber-arta/biciclete-fitness-suplimente"},
                {"label": "Biliard", "value": "sport-timp-liber-arta/biliard"},
                {"label": "Box", "value": "sport-timp-liber-arta/box"},
                {"label": "Camping", "value": "sport-timp-liber-arta/camping"},
                {"label": "Carti - Muzica - Filme", "value": "sport-timp-liber-arta/carti-muzica-filme"},
                {"label": "Dans, gimnastica", "value": "sport-timp-liber-arta/dans-gimnastica"},
                {"label": "Drumetie", "value": "sport-timp-liber-arta/drumetie"},
                {"label": "Echipamente sportive si de turism", "value": "sport-timp-liber-arta/echipamente-sportive-si-de-turism"},
                {"label": "Echitatie", "value": "sport-timp-liber-arta/echitatie"},
                {"label": "Evenimente - Divertisment", "value": "sport-timp-liber-arta/evenimente-divertisment"},
                {"label": "Fotbal", "value": "sport-timp-liber-arta/fotbal"},
                {"label": "Genti, trolere", "value": "sport-timp-liber-arta/genti-trolere"},
                {"label": "Golf", "value": "sport-timp-liber-arta/golf"},
                {"label": "Karate - Judo", "value": "sport-timp-liber-arta/karate-judo"},
                {"label": "Moto, enduro, atv", "value": "sport-timp-liber-arta/moto-enduro-atv"},
                {"label": "Parapante", "value": "sport-timp-liber-arta/parapante"},
                {"label": "Pescuit", "value": "sport-timp-liber-arta/pescuit"},
                {"label": "Sporturi de apa", "value": "sport-timp-liber-arta/sporturi-de-apa"},
                {"label": "Sporturi de iarna", "value": "sport-timp-liber-arta/sporturi-de-iarna"},
                {"label": "Tenis", "value": "sport-timp-liber-arta/tenis"},
                {"label": "Tir cu arcul", "value": "sport-timp-liber-arta/tir-cu-arcul"},
                {"label": "Trambuline", "value": "sport-timp-liber-arta/trambuline"},
                {"label": "Trotinete, role, skateboard", "value": "sport-timp-liber-arta/trotinete-role-skateboard"},
                {"label": "Vanatoare", "value": "sport-timp-liber-arta/vanatoare"},
                {"label": "Volei", "value": "sport-timp-liber-arta/volei"},
            ],
        },
    ],

    "publi24": [
        {
            "label": "Imobiliare",
            "value": "imobiliare",
            "subcategories": [
                {"label": "De vanzare", "value": "imobiliare/de-vanzare"},
                {"label": "De inchiriat", "value": "imobiliare/de-inchiriat"},
            ],
        },
        {
            "label": "Auto moto",
            "value": "auto-moto",
            "subcategories": [
                {"label": "Autoturisme", "value": "auto-moto/masini-second-hand"},
                {"label": "Piese si accesorii", "value": "auto-moto/piese-accesorii"},
                {"label": "Utilaje", "value": "auto-moto/utilaje"},
                {"label": "Moto", "value": "auto-moto/motociclete-second-hand"},
                {"label": "Transport", "value": "auto-moto/transport"},
            ],
        },
        {
            "label": "Locuri de muncă",
            "value": "locuri-de-munca",
            "subcategories": [
                {"label": "Constructii - Arhitectura - Design", "value": "locuri-de-munca/constructii-arhitectura-design"},
                {"label": "Soferi - Transporturi", "value": "locuri-de-munca/soferi-transporturi"},
                {"label": "Muncitori productie - depozit - logistica", "value": "locuri-de-munca/muncitori-productie-depozit-logistica"},
                {"label": "Horeca", "value": "locuri-de-munca/horeca"},
                {"label": "Casieri si lucratori comerciali", "value": "locuri-de-munca/casieri-lucratori-comerciali"},
                {"label": "Menaj si ingrijire persoane", "value": "locuri-de-munca/menaj-ingrijire-persoane"},
                {"label": "Agenti - consultanti vanzari", "value": "locuri-de-munca/agenti-consultanti-vanzari"},
                {"label": "Service si spalatorie auto", "value": "locuri-de-munca/service-spalatorie-auto"},
                {"label": "Agent securitate", "value": "locuri-de-munca/agent-securitate"},
                {"label": "Medicina umana", "value": "locuri-de-munca/medicina-umana"},
                {"label": "Frizerie - Coafura - Cosmetica", "value": "locuri-de-munca/frizerie-coafura-cosmetica"},
                {"label": "Salubrizare – Curatenie – Dezinsectie", "value": "locuri-de-munca/salubrizare-curatenie-dezinsectie"},
                {"label": "Agricultura - Silvicultura - Zootehnie", "value": "locuri-de-munca/agricultura-silvicultura-zootehnie"},
                {"label": "Administratie", "value": "locuri-de-munca/administratie"},
                {"label": "Industrie alimentara", "value": "locuri-de-munca/industrie-alimentara"},
                {"label": "Finante contabilitate", "value": "locuri-de-munca/finante-contabilitate"},
                {"label": "Marketing Publicitate", "value": "locuri-de-munca/marketing-publicitate"},
                {"label": "Confectii croitorie", "value": "locuri-de-munca/confectii-croitorie"},
                {"label": "IT - Telecomunicatii", "value": "locuri-de-munca/it-telecomunicatii"},
                {"label": "Profesori- Traineri", "value": "locuri-de-munca/profesori-traineri"},
                {"label": "Divertisment evenimente", "value": "locuri-de-munca/divertisment-evenimente"},
                {"label": "Medicina veterinara", "value": "locuri-de-munca/medicina-veterinara"},
                {"label": "Traduceri", "value": "locuri-de-munca/traduceri"},
            ],
        },
        {
            "label": "Matrimoniale",
            "value": "matrimoniale",
            "subcategories": [
                {"label": "Escorte", "value": "matrimoniale/escorte"},
                {"label": "El pentru ea", "value": "matrimoniale/el-pentru-ea"},
                {"label": "Webcam", "value": "matrimoniale/webcam"},
                {"label": "Gay/Lesbi", "value": "matrimoniale/gay-lesbi"},
                {"label": "Saloane masaj", "value": "matrimoniale/saloane-masaj"},
                {"label": "Diverse", "value": "matrimoniale/diverse"},
                {"label": "Hotline", "value": "matrimoniale/hotline"},
                {"label": "Prietenii/Casatorii", "value": "matrimoniale/prietenii-casatorii"},
            ],
        },
        {
            "label": "Servicii",
            "value": "servicii",
            "subcategories": [
                {"label": "Constructii-Amenajari", "value": "servicii/constructii-amenajari"},
                {"label": "Alte servicii", "value": "servicii/alte-servicii"},
                {"label": "Auto-Transporturi", "value": "servicii/auto-transporturi"},
                {"label": "Firme / Echipamente profesionale", "value": "servicii/firme-echipamente-profesionale"},
                {"label": "Cursuri - Meditatii", "value": "servicii/cursuri-meditatii"},
                {"label": "Catering / Nunti / Evenimente", "value": "servicii/catering-nunti-evenimente"},
                {"label": "Cosmetica-Wellness-Medicale", "value": "servicii/cosmetica-wellnes-medicale"},
                {"label": "Reparatii Electronice / Electrocasnice / PC", "value": "servicii/reparatii-electronice-electrocasnice-pc"},
                {"label": "Foto / Filmari / Muzica", "value": "servicii/foto-filmari-muzica"},
                {"label": "Menaj - Ingrijire persoane", "value": "servicii/menaj-ingrijire-persoane"},
                {"label": "Contabilitate / Juridic", "value": "servicii/contabilitate-juridic"},
                {"label": "Servicii IT", "value": "servicii/servicii-it"},
                {"label": "Publicitate", "value": "servicii/publicitate"},
                {"label": "Achizitii", "value": "servicii/achizitii"},
                {"label": "Transport persoane intern", "value": "servicii/transport-persoane-intern"},
                {"label": "Traduceri", "value": "servicii/traduceri"},
                {"label": "Transport persoane international", "value": "servicii/transport-persoane-international"},
                {"label": "Asigurari", "value": "servicii/asigurari"},
                {"label": "Tehnic - Mentenanta", "value": "servicii/tehnic-mentenanta"},
                {"label": "Instalatori", "value": "servicii/instalatori"},
                {"label": "Decodari / Modari", "value": "servicii/decodari-modari"},
            ],
        },
        {
            "label": "Electronice",
            "value": "electronice",
            "subcategories": [
                {"label": "Alte aparate", "value": "electronice/altele"},
                {"label": "Audio/Video", "value": "electronice/audio-video"},
                {"label": "Televizoare", "value": "electronice/televizoare"},
                {"label": "Electrocasnice", "value": "electronice/electrocasnice"},
                {"label": "Calculatoare", "value": "electronice/calculatoare"},
                {"label": "Telefoane mobile", "value": "electronice/telefoane-mobile"},
                {"label": "Accesorii electronice", "value": "electronice/accesorii-electronice"},
                {"label": "Laptop", "value": "electronice/laptop"},
                {"label": "Console/Jocuri", "value": "electronice/console-jocuri"},
                {"label": "Aparate foto", "value": "electronice/aparate-foto"},
                {"label": "Aparate medicale", "value": "electronice/aparate-medicale"},
                {"label": "Echipamente auto", "value": "electronice/echipamente-auto"},
                {"label": "Smartwatch", "value": "electronice/smartwatch"},
                {"label": "Tablete", "value": "electronice/tablete"},
            ],
        },
        {
            "label": "Modă și accesorii",
            "value": "moda-accesorii",
            "subcategories": [
                {"label": "Haine", "value": "moda-accesorii/haine"},
                {"label": "Accesorii", "value": "moda-accesorii/accesorii"},
                {"label": "Incaltaminte", "value": "moda-accesorii/incaltaminte"},
                {"label": "Cosmetice - Ingrijire", "value": "moda-accesorii/cosmetice-ingrijire"},
            ],
        },
        {
            "label": "Animale",
            "value": "animale",
            "subcategories": [
                {"label": "Animale de ferma", "value": "animale/animale-de-ferma"},
                {"label": "Caini", "value": "animale/caini"},
                {"label": "Pisici", "value": "animale/pisici"},
                {"label": "Pasari", "value": "animale/pasari"},
                {"label": "Accesorii", "value": "animale/accesorii"},
                {"label": "Adoptii", "value": "animale/adoptii"},
                {"label": "Pesti", "value": "animale/pesti"},
                {"label": "Servicii", "value": "animale/servicii"},
                {"label": "Reptile", "value": "animale/reptile"},
            ],
        },
        {
            "label": "Casă și grădină",
            "value": "casa-si-gradina",
            "subcategories": [
                {"label": "Constructii", "value": "casa-si-gradina/constructii"},
                {"label": "Pentru casa", "value": "casa-si-gradina/pentru-casa"},
                {"label": "Produse agricole", "value": "casa-si-gradina/produse-agricole"},
                {"label": "Pentru gradina", "value": "casa-si-gradina/pentru-gradina"},
            ],
        },
        {
            "label": "Timp liber și sport",
            "value": "timp-liber-sport",
            "subcategories": [
                {"label": "Arta si antichitati", "value": "timp-liber-sport/arta-si-antichitati"},
                {"label": "Carti - Muzica - Filme", "value": "timp-liber-sport/carti-muzica-filme"},
                {"label": "Biciclete - Accesorii", "value": "timp-liber-sport/biciclete-accesorii"},
                {"label": "Trotinete role skateboard", "value": "timp-liber-sport/trotinete-role-skateboard"},
                {"label": "Camping, Drumetie, Alpinism", "value": "timp-liber-sport/camping-drumetie-alpinism"},
                {"label": "Alte echipamente sportive", "value": "timp-liber-sport/alte-echipamente-sportive"},
                {"label": "Pescuit", "value": "timp-liber-sport/pescuit"},
                {"label": "Echipament fitness", "value": "timp-liber-sport/echipament-fitness"},
                {"label": "Ambarcatiuni", "value": "timp-liber-sport/ambarcatiuni"},
                {"label": "Sporturi de iarna", "value": "timp-liber-sport/sporturi-de-iarna"},
                {"label": "Fotbal", "value": "timp-liber-sport/fotbal"},
                {"label": "Tenis", "value": "timp-liber-sport/tenis"},
                {"label": "Sporturi de apa", "value": "timp-liber-sport/sporturi-de-apa"},
                {"label": "Alergare", "value": "timp-liber-sport/alergare"},
                {"label": "Trolere - echipament turistic", "value": "timp-liber-sport/trolere-echipament-turistic"},
                {"label": "Imbracaminte si accesorii vanatoare", "value": "timp-liber-sport/imbracaminte-accesorii-vanatoare"},
                {"label": "Trotinete electrice", "value": "timp-liber-sport/trotinete-electrice"},
            ],
        },
        {
            "label": "Mama și copilul",
            "value": "mama-si-copilul",
            "subcategories": [
                {"label": "Jucarii", "value": "mama-si-copilul/jucarii"},
                {"label": "Haine pentru copii", "value": "mama-si-copilul/haine-copii"},
                {"label": "Alte produse pentru copii", "value": "mama-si-copilul/alte-produse-copii"},
                {"label": "Plimbare", "value": "mama-si-copilul/plimbare"},
                {"label": "Camera copilului", "value": "mama-si-copilul/camera-copilului"},
                {"label": "Incaltaminte pentru copii", "value": "mama-si-copilul/incaltaminte-copii"},
                {"label": "Ingrijire si alimentatie", "value": "mama-si-copilul/ingrijire-alimentatie"},
                {"label": "Articole scolare educative", "value": "mama-si-copilul/articole-scolare-educative"},
                {"label": "Haine pentru gravide", "value": "mama-si-copilul/haine-gravide"},
            ],
        },
        {
            "label": "Cazare turism",
            "value": "cazare-turism",
            "subcategories": [
            ],
        },
    ],
}


def get_platform_categories(platform: str) -> list:
    return PLATFORM_CATEGORIES.get(platform, [])


# ──────────────────────────────────────────────────────────────────────────────
# Lookup invers pentru AFISARE (valoare tehnica stocata -> label human-readable).
# Construit o singura data din PLATFORM_CATEGORIES — aceeasi structura din care se
# populeaza dropdown-ul de categorii. keyword.category stocheaza mereu un `value` de
# aici (slug OLX "cat/subcat", catalog_id Vinted "2995", slug okazii etc.), deci
# inversul lui reda exact label-ul pe care utilizatorul l-a selectat.
#   olx  "electronice-si-electrocasnice/telefoane-mobile" -> "Electronice și Electrocasnice > Telefoane Mobile"
#   vinted "2995" -> "Electronice și Gadgeturi > Telefoane"
# ──────────────────────────────────────────────────────────────────────────────
_VALUE_TO_LABEL: dict[tuple, str] = {}
for _platform, _cats in PLATFORM_CATEGORIES.items():
    for _cat in _cats:
        _cval, _clabel = _cat.get("value"), _cat.get("label")
        if _cval is not None and _clabel:
            _VALUE_TO_LABEL[(_platform, str(_cval))] = _clabel
        for _sub in (_cat.get("subcategories") or []):
            _sval, _slabel = _sub.get("value"), _sub.get("label")
            if _sval is not None and _slabel:
                _VALUE_TO_LABEL[(_platform, str(_sval))] = (
                    f"{_clabel} > {_slabel}" if _clabel else _slabel
                )


def get_category_label(platform: Optional[str], category: Optional[str]) -> Optional[str]:
    """Converteste valoarea tehnica stocata pe keyword la label human-readable.

    Sursa e PLATFORM_CATEGORIES (dropdown-ul de categorii). Daca maparea esueaza —
    valoare necunoscuta sau text deja lizibil (ex. "Femei > Haine" din wizard) —
    intoarce valoarea bruta ca fallback (nicio regresie).
    """
    if not category:
        return None
    cat = str(category).strip()
    if platform:
        label = _VALUE_TO_LABEL.get((platform, cat))
        if label:
            return label
    # platforma lipsa/necunoscuta -> incearca in oricare platforma
    for (_p, _v), _lbl in _VALUE_TO_LABEL.items():
        if _v == cat:
            return _lbl
    return category
