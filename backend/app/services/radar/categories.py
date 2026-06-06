"""Maparea categoriilor logice -> identificatori specifici platformei.

Lista de categorii (asa cum apare in UI) e single source of truth. Pentru
fiecare scraper avem un mic dict cu valoarea adaugata in URL/query. Cand o
categorie nu e mapata, scraperul cade pe rezultatele globale, fara filtru.
"""

# Lista canonica afisata in dropdown-ul UI
CATEGORY_OPTIONS = [
    "Telefoane",
    "Tablete",
    "Laptopuri",
    "Electronice",
    "Îmbrăcăminte",
    "Încălțăminte",
    "Jocuri",
    "Cărți",
    "Sport",
    "Casă și grădină",
    "Auto",
    "Altele",
]


# OLX foloseste slug-uri in URL: /d/oferte/<categorie>/q-<keyword>/
OLX_CATEGORY_SLUGS = {
    "Telefoane": "telefoane-mobile",
    "Tablete": "tablete",
    "Laptopuri": "laptop-calculator",
    "Electronice": "electronice-si-electrocasnice",
    "Îmbrăcăminte": "moda",
    "Încălțăminte": "moda",
    "Jocuri": "electronice-si-electrocasnice/console-jocuri-video",
    "Cărți": "hobby",
    "Sport": "sport-timp-liber",
    "Casă și grădină": "casa-gradina",
    "Auto": "auto-moto-ambarcatiuni",
    "Altele": None,
}


# Vinted catalog_ids — valorile sunt id-urile de categorie (oficial sunt mult mai
# multe sub-categorii; folosim cele de top-level care exista pe vinted.ro)
VINTED_CATEGORY_IDS = {
    "Telefoane": 2994,        # Electronice -> Telefoane
    "Tablete": 2994,
    "Laptopuri": 2994,
    "Electronice": 2994,
    "Îmbrăcăminte": 1904,     # Imbracaminte femei (catalog mare)
    "Încălțăminte": 1231,
    "Jocuri": 3025,           # Jucarii si jocuri
    "Cărți": 3263,
    "Sport": 76,
    "Casă și grădină": 1918,
    "Auto": 2310,
    "Altele": None,
}


# Okazii foloseste path-uri scurte
OKAZII_CATEGORY_SLUGS = {
    "Telefoane": "telefoane",
    "Tablete": "tablete",
    "Laptopuri": "laptopuri",
    "Electronice": "electronice",
    "Îmbrăcăminte": "imbracaminte",
    "Încălțăminte": "incaltaminte",
    "Jocuri": "jocuri-video",
    "Cărți": "carti",
    "Sport": "sport-aer-liber",
    "Casă și grădină": "casa-gradina",
    "Auto": "auto-moto",
    "Altele": None,
}


# Facebook Marketplace categoryID-uri (valori folosite in URL ca `category=...`)
FACEBOOK_CATEGORY_IDS = {
    "Telefoane": "1561900557457147",
    "Tablete": "1561900557457147",
    "Laptopuri": "1561900557457147",
    "Electronice": "1561900557457147",
    "Îmbrăcăminte": "1490277691221416",
    "Încălțăminte": "1490277691221416",
    "Jocuri": "1561900557457147",
    "Cărți": None,
    "Sport": None,
    "Casă și grădină": None,
    "Auto": "807311116002614",
    "Altele": None,
}
