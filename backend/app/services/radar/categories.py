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
        # IDs marked CONFIRMED sunt din codul existent si au fost verificate.
        # IDs marcate VERIFY sunt estimari — trebuie validate cu GET /api/v2/catalog/categories.
        {
            "label": "Femei",
            "value": "1904",  # CONFIRMED
            "subcategories": [
                {"label": "Topuri și Bluze", "value": "4"},  # VERIFY
                {"label": "Rochii", "value": "3"},  # VERIFY
                {"label": "Pantaloni și Colanti", "value": "6"},  # VERIFY
                {"label": "Blugi", "value": "270"},  # VERIFY
                {"label": "Fuste", "value": "79"},  # VERIFY
                {"label": "Jachete și Paltoane", "value": "8"},  # VERIFY
                {"label": "Pulovere și Cardigan", "value": "256"},  # VERIFY
                {"label": "Hanorace", "value": "87"},  # VERIFY
                {"label": "Lenjerie și Pijamale", "value": "17"},  # VERIFY
                {"label": "Costume de Baie", "value": "15"},  # VERIFY
                {"label": "Ciorapi și Dresuri", "value": "68"},  # VERIFY
            ],
        },
        {
            "label": "Bărbati",
            "value": "5",  # VERIFY
            "subcategories": [
                {"label": "Tricouri și Maiouri", "value": "195"},  # VERIFY
                {"label": "Cămăși", "value": "198"},  # VERIFY
                {"label": "Pantaloni", "value": "201"},  # VERIFY
                {"label": "Blugi", "value": "196"},  # VERIFY
                {"label": "Pulovere și Cardigane", "value": "257"},  # VERIFY
                {"label": "Hanorace", "value": "255"},  # VERIFY
                {"label": "Jachete și Paltoane", "value": "197"},  # VERIFY
                {"label": "Costume și Sacouri", "value": "200"},  # VERIFY
                {"label": "Pantaloni Scurti", "value": "199"},  # VERIFY
            ],
        },
        {
            "label": "Copii și Bebeluși",
            "value": "2",  # VERIFY
            "subcategories": [
                {"label": "0-2 ani", "value": "151"},  # VERIFY
                {"label": "3-5 ani", "value": "152"},  # VERIFY
                {"label": "6-9 ani", "value": "153"},  # VERIFY
                {"label": "10-14 ani", "value": "154"},  # VERIFY
            ],
        },
        {
            "label": "Încăltăminte",
            "value": "1231",  # CONFIRMED
            "subcategories": [
                {"label": "Femei", "value": "16"},  # VERIFY
                {"label": "Bărbati", "value": "203"},  # VERIFY
                {"label": "Copii", "value": "155"},  # VERIFY
            ],
        },
        {
            "label": "Genti și Accesorii",
            "value": "1206",  # VERIFY
            "subcategories": [
                {"label": "Genti", "value": "1232"},  # VERIFY
                {"label": "Portofele", "value": "1234"},  # VERIFY
                {"label": "Bijuterii", "value": "1235"},  # VERIFY
                {"label": "Ceasuri", "value": "1236"},  # VERIFY
                {"label": "Ochelari", "value": "1237"},  # VERIFY
                {"label": "Pălării și Căciuli", "value": "1238"},  # VERIFY
                {"label": "Esarfe și Fular", "value": "1239"},  # VERIFY
            ],
        },
        {
            "label": "Sport",
            "value": "76",  # CONFIRMED
            "subcategories": [
                {"label": "Echipament Sportiv", "value": "62"},  # VERIFY
                {"label": "Încăltăminte Sport", "value": "61"},  # VERIFY
                {"label": "Fitness", "value": "63"},  # VERIFY
                {"label": "Sporturi Outdoor", "value": "64"},  # VERIFY
            ],
        },
        {
            "label": "Casă",
            "value": "1918",  # CONFIRMED
            "subcategories": [
                {"label": "Decoratiuni", "value": "1919"},  # VERIFY
                {"label": "Lenjerie de Pat", "value": "1920"},  # VERIFY
                {"label": "Veselă și Tacâmuri", "value": "1921"},  # VERIFY
                {"label": "Textile", "value": "1922"},  # VERIFY
            ],
        },
        {
            "label": "Frumusete",
            "value": "1203",  # VERIFY
            "subcategories": [
                {"label": "Cosmetice", "value": "1204"},  # VERIFY
                {"label": "Parfumuri", "value": "1240"},  # VERIFY
                {"label": "Îngrijire Corp", "value": "1241"},  # VERIFY
                {"label": "Îngrijire Păr", "value": "1242"},  # VERIFY
            ],
        },
        {
            "label": "Electronice și Gadgeturi",
            "value": "2994",  # CONFIRMED
            "subcategories": [
                {"label": "Telefoane", "value": "2995"},  # VERIFY
                {"label": "Tablete și E-readere", "value": "2996"},  # VERIFY
                {"label": "Căsti și Audio", "value": "2997"},  # VERIFY
                {"label": "Console și Jocuri", "value": "3025"},  # CONFIRMED
                {"label": "Laptopuri", "value": "2998"},  # VERIFY
            ],
        },
        {
            "label": "Cărti, Muzică și Film",
            "value": "3263",  # CONFIRMED
            "subcategories": [
                {"label": "Cărti", "value": "3264"},  # VERIFY
                {"label": "Muzică", "value": "3265"},  # VERIFY
                {"label": "Film", "value": "3266"},  # VERIFY
            ],
        },
    ],

    "okazii": [
        # URL format used by scraper: https://www.okazii.ro/{value}?q={keyword}
        # All slugs marked VERIFY — test before confirming.
        {
            "label": "Electronice",
            "value": "electronice",
            "subcategories": [
                {"label": "Telefoane Mobile", "value": "electronice/telefoane-gsm"},  # VERIFY
                {"label": "Laptopuri", "value": "electronice/laptopuri"},  # VERIFY
                {"label": "Tablete", "value": "electronice/tablete"},  # VERIFY
                {"label": "Calculatoare", "value": "electronice/calculatoare"},  # VERIFY
                {"label": "Componente PC", "value": "electronice/componente-pc"},  # VERIFY
                {"label": "Console și Jocuri Video", "value": "electronice/console-jocuri-video"},  # VERIFY
                {"label": "Audio-Video și TV", "value": "electronice/audio-video"},  # VERIFY
                {"label": "Foto și Video", "value": "electronice/aparate-foto"},  # VERIFY
                {"label": "Smartwatch-uri", "value": "electronice/smartwatch"},  # VERIFY
                {"label": "Accesorii Electronice", "value": "electronice/accesorii-electronice"},  # VERIFY
            ],
        },
        {
            "label": "Modă și Accesorii",
            "value": "moda-fashion",
            "subcategories": [
                {"label": "Îmbrăcăminte Femei", "value": "moda-fashion/imbracaminte-femei"},  # VERIFY
                {"label": "Îmbrăcăminte Bărbati", "value": "moda-fashion/imbracaminte-barbati"},  # VERIFY
                {"label": "Îmbrăcăminte Copii", "value": "moda-fashion/imbracaminte-copii"},  # VERIFY
                {"label": "Încăltăminte", "value": "moda-fashion/incaltaminte"},  # VERIFY
                {"label": "Genti și Accesorii", "value": "moda-fashion/genti-accesorii"},  # VERIFY
                {"label": "Bijuterii și Ceasuri", "value": "moda-fashion/bijuterii-ceasuri"},  # VERIFY
            ],
        },
        {
            "label": "Casă și Grădina",
            "value": "casa-gradina",
            "subcategories": [
                {"label": "Mobilă", "value": "casa-gradina/mobila"},  # VERIFY
                {"label": "Decoratiuni", "value": "casa-gradina/decoratiuni"},  # VERIFY
                {"label": "Electrocasnice", "value": "casa-gradina/electrocasnice"},  # VERIFY
                {"label": "Grădinărit", "value": "casa-gradina/gradinarit"},  # VERIFY
                {"label": "Bricolaj", "value": "casa-gradina/bricolaj"},  # VERIFY
            ],
        },
        {
            "label": "Auto și Moto",
            "value": "auto-moto",
            "subcategories": [
                {"label": "Piese Auto", "value": "auto-moto/piese-auto"},  # VERIFY
                {"label": "Accesorii Auto", "value": "auto-moto/accesorii-auto"},  # VERIFY
                {"label": "Motociclete", "value": "auto-moto/motociclete"},  # VERIFY
            ],
        },
        {
            "label": "Sport și Recreere",
            "value": "sport-recreere",
            "subcategories": [
                {"label": "Fitness", "value": "sport-recreere/fitness"},  # VERIFY
                {"label": "Biciclete", "value": "sport-recreere/biciclete"},  # VERIFY
                {"label": "Echipamente Sportive", "value": "sport-recreere/echipamente-sportive"},  # VERIFY
                {"label": "Sporturi Outdoor", "value": "sport-recreere/outdoor"},  # VERIFY
            ],
        },
        {
            "label": "Copii și Bebe",
            "value": "copii-bebe",
            "subcategories": [
                {"label": "Haine Copii", "value": "copii-bebe/haine"},  # VERIFY
                {"label": "Jucării", "value": "copii-bebe/jucarii"},  # VERIFY
                {"label": "Cărucioare", "value": "copii-bebe/carucioare"},  # VERIFY
                {"label": "Mobilier Copii", "value": "copii-bebe/mobilier"},  # VERIFY
            ],
        },
        {
            "label": "Sănătate și Frumusete",
            "value": "sanatate-frumusete",
            "subcategories": [
                {"label": "Cosmetice", "value": "sanatate-frumusete/cosmetice"},  # VERIFY
                {"label": "Suplimente", "value": "sanatate-frumusete/suplimente"},  # VERIFY
                {"label": "Echipamente Medicale", "value": "sanatate-frumusete/echipamente"},  # VERIFY
            ],
        },
        {
            "label": "Colectii și Artă",
            "value": "colectii-arta",
            "subcategories": [
                {"label": "Monede și Bancnote", "value": "colectii-arta/monede"},  # VERIFY
                {"label": "Filatelie", "value": "colectii-arta/filatelie"},  # VERIFY
                {"label": "Artă", "value": "colectii-arta/arta"},  # VERIFY
            ],
        },
        {
            "label": "Cărti, Muzică și Film",
            "value": "carti-muzica-film",
            "subcategories": [
                {"label": "Cărti", "value": "carti-muzica-film/carti"},  # VERIFY
                {"label": "Muzică", "value": "carti-muzica-film/muzica"},  # VERIFY
                {"label": "Film", "value": "carti-muzica-film/film"},  # VERIFY
            ],
        },
    ],

    "facebook": [
        # 1 level only. Values are category IDs used as &category={value} in URL.
        # IDs CONFIRMED sunt din codul existent.
        {"label": "Electronice și Gadgeturi", "value": "1561900557457147"},  # CONFIRMED
        {"label": "Îmbrăcăminte și Accesorii", "value": "1490277691221416"},  # CONFIRMED
        {"label": "Mobilă și Living", "value": "1577608482269133"},  # VERIFY
        {"label": "Vehicule și Accesorii", "value": "807311116002614"},  # CONFIRMED
        {"label": "Articole Sportive", "value": "1576585399249494"},  # VERIFY
        {"label": "Jocuri și Console", "value": "1597932930455716"},  # VERIFY
        {"label": "Instrumente Muzicale", "value": "1579655115447853"},  # VERIFY
        {"label": "Cărti, Muzică și Film", "value": "1580747392014085"},  # VERIFY
        {"label": "Articole pentru Copii", "value": "1580747392014090"},  # VERIFY
        {"label": "Electrocasnice", "value": "1581668735253847"},  # VERIFY
        {"label": "Animale de Companie", "value": "1583655371741708"},  # VERIFY
        {"label": "Sănătate și Frumusete", "value": "1584963078277600"},  # VERIFY
        {"label": "Grădinărit", "value": "1585543171552946"},  # VERIFY
        {"label": "Diverse", "value": None},
    ],

    "lajumate": [
        # 1 level. URL format: https://www.lajumate.ro/anunturi/{value}/
        {"label": "Electronice și IT", "value": "electronice-si-it"},  # VERIFY
        {"label": "Auto și Piese", "value": "auto-moto"},  # VERIFY
        {"label": "Modă și Accesorii", "value": "moda-accesorii"},  # VERIFY
        {"label": "Casă și Grădina", "value": "casa-gradina"},  # VERIFY
        {"label": "Sport și Timp Liber", "value": "sport-si-timp-liber"},  # VERIFY
        {"label": "Copii și Bebe", "value": "copii-bebe"},  # VERIFY
        {"label": "Animale de Companie", "value": "animale"},  # VERIFY
        {"label": "Sănătate și Frumusete", "value": "sanatate-frumusete"},  # VERIFY
        {"label": "Cărti, Muzică și Film", "value": "carti-muzica-film"},  # VERIFY
        {"label": "Colectii și Artă", "value": "colectii-arta"},  # VERIFY
        {"label": "Diverse", "value": None},
    ],

    "publi24": [
        # 1 level. URL format: https://www.publi24.ro/anunturi/vanzari/{value}/
        {"label": "Electronice și IT", "value": "electronice-si-it"},  # VERIFY
        {"label": "Auto, Moto și Ambarcatiuni", "value": "auto-moto-ambarcatiuni"},  # VERIFY
        {"label": "Modă și Accesorii", "value": "moda-accesorii"},  # VERIFY
        {"label": "Casă și Grădina", "value": "casa-gradina"},  # VERIFY
        {"label": "Sport și Hobby", "value": "sport-hobby"},  # VERIFY
        {"label": "Copii și Bebe", "value": "copii-bebe"},  # VERIFY
        {"label": "Animale de Companie", "value": "animale"},  # VERIFY
        {"label": "Sănătate și Frumusete", "value": "sanatate-frumusete"},  # VERIFY
        {"label": "Cărti, Muzică și Film", "value": "carti-muzica-film"},  # VERIFY
        {"label": "Industrie și Utilaje", "value": "industrie-utilaje"},  # VERIFY
        {"label": "Diverse", "value": None},
    ],
}


def get_platform_categories(platform: str) -> list:
    return PLATFORM_CATEGORIES.get(platform, [])
