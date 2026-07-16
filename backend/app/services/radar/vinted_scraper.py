"""Scraper pentru Vinted Romania prin libraria vinted-scraper.

Foloseste libraria `vinted-scraper`, care gestioneaza automat DataDome (fara cookie
de sesiune). Filtrarea pe categorie e server-side via `catalog_ids` (rezolvat din
VINTED_CATALOG_ID_MAP), iar filtrarea pe subcategorie se face post-scrape pe
titlu/descriere. La eroare returnam [] si logam — fara mecanism de fallback.
"""
import json
import re
import threading
import time
from datetime import datetime
from typing import Optional

from app.services.radar.base_scraper import is_excluded
from app.services.radar import vinted_html
from app.services.log_manager import log_manager


# ── Singleton VintedWrapper (JSON brut) — reutilizat la toate apelurile ─────────
# Elimina instantierea per-apel. Constructie cu retry (primul attempt poate da 406).
_wrapper = None
_wrapper_lock = threading.Lock()
_wrapper_fail_count = 0


def _get_wrapper():
    """Instanta VintedWrapper la nivel de modul (JSON brut), construita o singura
    data cu retry x3 + backoff 2/4/8s. None daca nu poate fi construita."""
    global _wrapper
    with _wrapper_lock:
        if _wrapper is not None:
            return _wrapper
        try:
            from vinted_scraper import VintedWrapper
        except Exception as exc:
            log_manager.emit("radar", "ERR", f"Vinted: libraria lipseste: {str(exc)[:80]}")
            return None
        last = None
        for attempt in range(3):
            try:
                _wrapper = VintedWrapper("https://www.vinted.ro")
                return _wrapper
            except Exception as exc:
                last = exc
                time.sleep(2 * (2 ** attempt))  # 2 / 4 / 8 s
        log_manager.emit("radar", "ERR",
            f"Vinted wrapper: constructie esuata dupa 3 incercari: {str(last)[:100]}")
        _wrapper = None
        return None


def _invalidate_wrapper():
    """Forteaza reconstruirea sesiunii la urmatorul apel (dupa esecuri repetate)."""
    global _wrapper, _wrapper_fail_count
    with _wrapper_lock:
        _wrapper = None
        _wrapper_fail_count = 0


# Generat automat — map_vinted_categories.py — 2026-07-03
# Acoperire: 590/590 subcategorii · 669 intrari (tab/categorie/subcategorie)
VINTED_CATALOG_ID_MAP: dict[tuple[str, str, str], int] = {
    ("Femei", "", ""): 1904,
    ("Femei", "Accesorii", ""): 1187,
    ("Femei", "Accesorii", "Accesorii pentru păr"): 1123,
    ("Femei", "Accesorii", "Alte accesorii"): 1140,
    ("Femei", "Accesorii", "Bandane și panglici"): 2931,
    ("Femei", "Accesorii", "Batiste"): 2932,
    ("Femei", "Accesorii", "Bijuterii"): 21,
    ("Femei", "Accesorii", "Brelocuri"): 1852,
    ("Femei", "Accesorii", "Ceasuri"): 22,
    ("Femei", "Accesorii", "Curele"): 20,
    ("Femei", "Accesorii", "Fulare și eșarfe"): 89,
    ("Femei", "Accesorii", "Mănuși"): 90,
    ("Femei", "Accesorii", "Ochelari de soare"): 26,
    ("Femei", "Accesorii", "Pălării și șepci"): 88,
    ("Femei", "Accesorii", "Umbrele"): 1851,
    ("Femei", "Frumusețe", ""): 146,
    ("Femei", "Frumusețe", "Alte articole de frumusețe"): 153,
    ("Femei", "Frumusețe", "Instrumente pentru înfrumusețare"): 1906,
    ("Femei", "Frumusețe", "Machiaj"): 964,
    ("Femei", "Frumusețe", "Parfum"): 152,
    ("Femei", "Frumusețe", "Îngrijirea corpului"): 956,
    ("Femei", "Frumusețe", "Îngrijirea mâinilor"): 1264,
    ("Femei", "Frumusețe", "Îngrijirea părului"): 1902,
    ("Femei", "Frumusețe", "Îngrijirea tenului"): 948,
    ("Femei", "Frumusețe", "Îngrijirea unghiilor"): 960,
    ("Femei", "Genți", ""): 19,
    ("Femei", "Genți", "Borsete"): 1848,
    ("Femei", "Genți", "Genți bucket"): 2942,
    ("Femei", "Genți", "Genți de călătorie și valize"): 1850,
    ("Femei", "Genți", "Genți de mână"): 156,
    ("Femei", "Genți", "Genți de umăr"): 158,
    ("Femei", "Genți", "Genți hobo"): 2945,
    ("Femei", "Genți", "Genți pentru cosmetice"): 161,
    ("Femei", "Genți", "Genți plajă"): 2940,
    ("Femei", "Genți", "Genți sport"): 2944,
    ("Femei", "Genți", "Genți tip poștas"): 1784,
    ("Femei", "Genți", "Genți și saci de voiaj"): 1849,
    ("Femei", "Genți", "Plicuri"): 159,
    ("Femei", "Genți", "Poșete de mână"): 2939,
    ("Femei", "Genți", "Poșete și portofele"): 160,
    ("Femei", "Genți", "Rucsacuri"): 157,
    ("Femei", "Genți", "Saci protecție haine"): 2943,
    ("Femei", "Genți", "Sacoșe"): 552,
    ("Femei", "Genți", "Serviete"): 2941,
    ("Femei", "Haine", ""): 4,
    ("Femei", "Haine", "Alte articole de îmbrăcăminte"): 18,
    ("Femei", "Haine", "Blugi"): 183,
    ("Femei", "Haine", "Costume de baie"): 28,
    ("Femei", "Haine", "Costume și blazere"): 8,
    ("Femei", "Haine", "Costume și ținute speciale"): 1782,
    ("Femei", "Haine", "Fuste"): 11,
    ("Femei", "Haine", "Fustă-pantaloni scurtă"): 5491,
    ("Femei", "Haine", "Haine maternitate"): 1176,
    ("Femei", "Haine", "Lenjerie intimă și pijamale"): 29,
    ("Femei", "Haine", "Pantaloni scurți și pantaloni trei sferturi"): 15,
    ("Femei", "Haine", "Pantaloni și colanți"): 9,
    ("Femei", "Haine", "Pulovere"): 13,
    ("Femei", "Haine", "Rochii"): 10,
    ("Femei", "Haine", "Salopete lungi și scurte"): 1035,
    ("Femei", "Haine", "Topuri și tricouri"): 12,
    ("Femei", "Haine", "Îmbrăcăminte de exterior"): 1037,
    ("Femei", "Haine", "Îmbrăcăminte pentru sport"): 73,
    ("Femei", "Pantofi", ""): 16,
    ("Femei", "Pantofi", "Balerini"): 2955,
    ("Femei", "Pantofi", "Cizme și ghete"): 1049,
    ("Femei", "Pantofi", "Espadrile"): 2953,
    ("Femei", "Pantofi", "Flip-flops și șlapi"): 2952,
    ("Femei", "Pantofi", "Pantofi Mary Jane și T-bar"): 2950,
    ("Femei", "Pantofi", "Pantofi cu toc"): 543,
    ("Femei", "Pantofi", "Pantofi cu șiret"): 2951,
    ("Femei", "Pantofi", "Pantofi sport"): 2632,
    ("Femei", "Pantofi", "Pantofi tip boat shoe, loaferi și mocasini"): 2954,
    ("Femei", "Pantofi", "Papuci de casă"): 215,
    ("Femei", "Pantofi", "Saboți"): 2623,
    ("Femei", "Pantofi", "Sandale"): 2949,
    ("Femei", "Pantofi", "Încălțăminte sport"): 2630,
    ("Bărbați", "", ""): 5,
    ("Bărbați", "Accesorii", ""): 82,
    ("Bărbați", "Accesorii", "Altele"): 99,
    ("Bărbați", "Accesorii", "Bandane și eșarfe de păr"): 2960,
    ("Bărbați", "Accesorii", "Batiste"): 2958,
    ("Bărbați", "Accesorii", "Batiste buzunar"): 2957,
    ("Bărbați", "Accesorii", "Bijuterii"): 95,
    ("Bărbați", "Accesorii", "Bretele"): 2959,
    ("Bărbați", "Accesorii", "Ceasuri"): 97,
    ("Bărbați", "Accesorii", "Cravate și papioane"): 2956,
    ("Bărbați", "Accesorii", "Curele"): 96,
    ("Bărbați", "Accesorii", "Fulare și eșarfe"): 87,
    ("Bărbați", "Accesorii", "Genți și rucsacuri"): 94,
    ("Bărbați", "Accesorii", "Mănuși"): 91,
    ("Bărbați", "Accesorii", "Ochelari de soare"): 98,
    ("Bărbați", "Accesorii", "Pălării și șepci"): 86,
    ("Bărbați", "Haine", ""): 2050,
    ("Bărbați", "Haine", "Alte articole de îmbrăcăminte"): 83,
    ("Bărbați", "Haine", "Blugi"): 257,
    ("Bărbați", "Haine", "Costume de baie"): 84,
    ("Bărbați", "Haine", "Costume și blazere"): 32,
    ("Bărbați", "Haine", "Costume și ținute speciale"): 92,
    ("Bărbați", "Haine", "Haine de dormit"): 2910,
    ("Bărbați", "Haine", "Pantaloni"): 34,
    ("Bărbați", "Haine", "Pantaloni scurți"): 80,
    ("Bărbați", "Haine", "Pulovere"): 79,
    ("Bărbați", "Haine", "Topuri și tricouri"): 76,
    ("Bărbați", "Haine", "Îmbrăcăminte de exterior"): 1206,
    ("Bărbați", "Haine", "Îmbrăcăminte pentru sport"): 30,
    ("Bărbați", "Haine", "Șosete și lenjerie intimă"): 85,
    ("Bărbați", "Pantofi", ""): 1231,
    ("Bărbați", "Pantofi", "Cizme și ghete"): 1233,
    ("Bărbați", "Pantofi", "Espadrile"): 2657,
    ("Bărbați", "Pantofi", "Flip-flops și șlapi"): 2969,
    ("Bărbați", "Pantofi", "Pantofi eleganți"): 1238,
    ("Bărbați", "Pantofi", "Pantofi sport"): 1242,
    ("Bărbați", "Pantofi", "Pantofi tip boat shoe, loaferi și mocasini"): 2656,
    ("Bărbați", "Pantofi", "Papuci de casă"): 2659,
    ("Bărbați", "Pantofi", "Saboți și papuci"): 2970,
    ("Bărbați", "Pantofi", "Sandale"): 2968,
    ("Bărbați", "Pantofi", "Încălțăminte sport"): 1452,
    ("Bărbați", "Îngrijire", ""): 139,
    ("Bărbați", "Îngrijire", "Aftershave și apă de colonie"): 145,
    ("Bărbați", "Îngrijire", "Alte articole de îngrijire"): 968,
    ("Bărbați", "Îngrijire", "Instrumente și accesorii"): 2055,
    ("Bărbați", "Îngrijire", "Machiaj"): 144,
    ("Bărbați", "Îngrijire", "Seturi de îngrijire"): 1863,
    ("Bărbați", "Îngrijire", "Îngrijirea corpului"): 141,
    ("Bărbați", "Îngrijire", "Îngrijirea mâinilor și a unghiilor"): 142,
    ("Bărbați", "Îngrijire", "Îngrijirea părului"): 140,
    ("Bărbați", "Îngrijire", "Îngrijirea tenului"): 143,
    ("Designer", "", ""): 2993,
    ("Designer", "Designer bărbați", ""): 2988,
    ("Designer", "Designer bărbați", "Accesorii de designer"): 2991,
    ("Designer", "Designer bărbați", "Pantofi de designer"): 2990,
    ("Designer", "Designer bărbați", "Îmbrăcăminte de designer"): 2992,
    ("Designer", "Designer femei", ""): 2983,
    ("Designer", "Designer femei", "Accesorii de designer"): 2986,
    ("Designer", "Designer femei", "Genți de designer"): 2984,
    ("Designer", "Designer femei", "Pantofi de designer"): 2985,
    ("Designer", "Designer femei", "Îmbrăcăminte de designer"): 2987,
    ("Copii", "", ""): 1193,
    ("Copii", "Cărucioare, landouri și scaune auto", ""): 1496,
    ("Copii", "Cărucioare, landouri și scaune auto", "Accesorii Buggy"): 1511,
    ("Copii", "Cărucioare, landouri și scaune auto", "Accesorii scaune auto"): 3385,
    ("Copii", "Cărucioare, landouri și scaune auto", "Cărucioare"): 1612,
    ("Copii", "Cărucioare, landouri și scaune auto", "Scaune auto"): 3383,
    ("Copii", "Cărucioare, landouri și scaune auto", "Sisteme de purtare și wrap-uri pentru bebeluși"): 3461,
    ("Copii", "Cărucioare, landouri și scaune auto", "Înălțătoare"): 3384,
    ("Copii", "Echipamente de protecție și siguranță pentru copii", ""): 3427,
    ("Copii", "Echipamente de protecție și siguranță pentru copii", "Accesorii de protecție pentru copii"): 3429,
    ("Copii", "Echipamente de protecție și siguranță pentru copii", "Hamuri și centuri de siguranță"): 3431,
    ("Copii", "Echipamente de protecție și siguranță pentru copii", "Porți și protecții pentru copii"): 3428,
    ("Copii", "Echipamente de protecție și siguranță pentru copii", "Protecție fonică"): 3430,
    ("Copii", "Jucării", ""): 1499,
    ("Copii", "Jucării", "Activități și jucării pentru copii"): 3344,
    ("Copii", "Jucării", "Arte și meșteșuguri"): 3314,
    ("Copii", "Jucării", "Costumează-te și intră în rol"): 3329,
    ("Copii", "Jucării", "Cuburi și jucării de construit"): 1767,
    ("Copii", "Jucării", "Figurine și accesorii"): 1730,
    ("Copii", "Jucării", "Jucării educative"): 1763,
    ("Copii", "Jucării", "Jucării electronice"): 1725,
    ("Copii", "Jucării", "Jucării moi și animale de pluș"): 1764,
    ("Copii", "Jucării", "Jucării muzicale și instrumente de jucărie"): 1766,
    ("Copii", "Jucării", "Jucării pentru exterior și sportive"): 1771,
    ("Copii", "Jucării", "Mașini, trenuri și alte vehicule de jucărie"): 3375,
    ("Copii", "Jucării", "Noutăți și jucării fidget"): 3336,
    ("Copii", "Jucării", "Păpuși și accesorii"): 1731,
    ("Copii", "Mobilier și decorațiuni", ""): 1498,
    ("Copii", "Mobilier și decorațiuni", "Covoare și carpete"): 3290,
    ("Copii", "Mobilier și decorațiuni", "Decorațiuni și suveniruri"): 3276,
    ("Copii", "Mobilier și decorațiuni", "Mese și birouri"): 3294,
    ("Copii", "Mobilier și decorațiuni", "Mobilier de joacă"): 3292,
    ("Copii", "Mobilier și decorațiuni", "Mobilier pentru camera copilului"): 3284,
    ("Copii", "Mobilier și decorațiuni", "Rafturi"): 3293,
    ("Copii", "Mobilier și decorațiuni", "Saltele pentru copii"): 1567,
    ("Copii", "Mobilier și decorațiuni", "Saltele și covoare de joacă"): 1572,
    ("Copii", "Mobilier și decorațiuni", "Scaune"): 3291,
    ("Copii", "Mobilier și decorațiuni", "Șezlonguri și cuiburi"): 3275,
    ("Copii", "Mobilier și decorațiuni", "Șifoniere"): 3295,
    ("Copii", "Mobilier și decorațiuni", "Țarcuri de joacă"): 1573,
    ("Copii", "Rechizite școlare", ""): 1501,
    ("Copii", "Rechizite școlare", "Cutii și pungi pentru prânz"): 3269,
    ("Copii", "Rechizite școlare", "Ghiozdane"): 1508,
    ("Copii", "Rechizite școlare", "Rechizite școlare"): 1509,
    ("Copii", "Sănătate și sarcină", ""): 3419,
    ("Copii", "Sănătate și sarcină", "Aspiratoare nazale"): 3421,
    ("Copii", "Sănătate și sarcină", "Centuri de susținere pentru sarcină"): 3425,
    ("Copii", "Sănătate și sarcină", "Cântare"): 3426,
    ("Copii", "Sănătate și sarcină", "Perne pentru sarcină"): 3424,
    ("Copii", "Sănătate și sarcină", "Termometre"): 3422,
    ("Copii", "Sănătate și sarcină", "Umidificatoare"): 3420,
    ("Copii", "Sănătate și sarcină", "Îngrijirea postpartum"): 3423,
    ("Copii", "Îmbrăcăminte pentru băieți", ""): 1194,
    ("Copii", "Îmbrăcăminte pentru băieți", "Accesorii"): 1714,
    ("Copii", "Îmbrăcăminte pentru băieți", "Alte haine pentru băieți"): 1205,
    ("Copii", "Îmbrăcăminte pentru băieți", "Costume de baie"): 1202,
    ("Copii", "Îmbrăcăminte pentru băieți", "Genți și rucsacuri"): 1257,
    ("Copii", "Îmbrăcăminte pentru băieți", "Lenjerie intimă și șosete"): 1203,
    ("Copii", "Îmbrăcăminte pentru băieți", "Pachete îmbrăcăminte"): 1760,
    ("Copii", "Îmbrăcăminte pentru băieți", "Pantaloni și salopete"): 1200,
    ("Copii", "Îmbrăcăminte pentru băieți", "Pantofi"): 1256,
    ("Copii", "Îmbrăcăminte pentru băieți", "Pijamale"): 1752,
    ("Copii", "Îmbrăcăminte pentru băieți", "Pulovere și hanorace cu glugă"): 1199,
    ("Copii", "Îmbrăcăminte pentru băieți", "Topuri și tricouri"): 1198,
    ("Copii", "Îmbrăcăminte pentru băieți", "Îmbrăcăminte de exterior"): 1197,
    ("Copii", "Îmbrăcăminte pentru băieți", "Îmbrăcăminte pentru bebe băiat"): 1196,
    ("Copii", "Îmbrăcăminte pentru băieți", "Îmbrăcăminte pentru gemeni"): 1761,
    ("Copii", "Îmbrăcăminte pentru băieți", "Îmbrăcăminte sportivă"): 1204,
    ("Copii", "Îmbrăcăminte pentru băieți", "Ținute de ocazie"): 2083,
    ("Copii", "Îmbrăcăminte pentru băieți", "Ținute și costume de carnaval"): 1762,
    ("Copii", "Îmbrăcăminte pentru fete", ""): 1195,
    ("Copii", "Îmbrăcăminte pentru fete", "Accesorii"): 1574,
    ("Copii", "Îmbrăcăminte pentru fete", "Alte articole de îmbrăcăminte pentru fete"): 1254,
    ("Copii", "Îmbrăcăminte pentru fete", "Costume de baie"): 1251,
    ("Copii", "Îmbrăcăminte pentru fete", "Fuste"): 1248,
    ("Copii", "Îmbrăcăminte pentru fete", "Genți și rucsacuri"): 1258,
    ("Copii", "Îmbrăcăminte pentru fete", "Lenjerie intimă și șosete"): 1252,
    ("Copii", "Îmbrăcăminte pentru fete", "Pachete îmbrăcăminte"): 1510,
    ("Copii", "Îmbrăcăminte pentru fete", "Pantaloni și pantaloni scurți"): 1249,
    ("Copii", "Îmbrăcăminte pentru fete", "Pantofi"): 1255,
    ("Copii", "Îmbrăcăminte pentru fete", "Pijamale"): 1594,
    ("Copii", "Îmbrăcăminte pentru fete", "Pulovere și hanorace cu glugă"): 1246,
    ("Copii", "Îmbrăcăminte pentru fete", "Rochii"): 1247,
    ("Copii", "Îmbrăcăminte pentru fete", "Topuri și tricouri"): 1245,
    ("Copii", "Îmbrăcăminte pentru fete", "Îmbrăcăminte de exterior"): 1244,
    ("Copii", "Îmbrăcăminte pentru fete", "Îmbrăcăminte pentru bebe fată"): 1243,
    ("Copii", "Îmbrăcăminte pentru fete", "Îmbrăcăminte pentru gemeni"): 1604,
    ("Copii", "Îmbrăcăminte pentru fete", "Îmbrăcăminte sportivă"): 1253,
    ("Copii", "Îmbrăcăminte pentru fete", "Ținute de ocazie"): 2080,
    ("Copii", "Îmbrăcăminte pentru fete", "Ținute și costume de carnaval"): 1606,
    ("Copii", "Îmbăiere și înfășare", ""): 3393,
    ("Copii", "Îmbăiere și înfășare", "Baie"): 3412,
    ("Copii", "Îmbăiere și înfășare", "Depozitarea și eliminarea scutecelor"): 3403,
    ("Copii", "Îmbăiere și înfășare", "Genți pentru înfășat"): 3394,
    ("Copii", "Îmbăiere și înfășare", "Olițe"): 3417,
    ("Copii", "Îmbăiere și înfășare", "Saltele pentru schimbat și huse"): 3395,
    ("Copii", "Îmbăiere și înfășare", "Scaune cu trepte"): 3418,
    ("Copii", "Îmbăiere și înfășare", "Scutece"): 3399,
    ("Copii", "Îmbăiere și înfășare", "Îngrijirea pielii și igienă"): 3408,
    ("Casă", "", ""): 1918,
    ("Casă", "Accesorii pentru casă", ""): 1934,
    ("Casă", "Accesorii pentru casă", "Accesorii decorative"): 3823,
    ("Casă", "Accesorii pentru casă", "Accesorii pentru șemineu"): 3833,
    ("Casă", "Accesorii pentru casă", "Ceasuri"): 1936,
    ("Casă", "Accesorii pentru casă", "Decorațiune de perete"): 3846,
    ("Casă", "Accesorii pentru casă", "Depozitare și organizare"): 1939,
    ("Casă", "Accesorii pentru casă", "Iluminat"): 3834,
    ("Casă", "Accesorii pentru casă", "Lumânări și parfumuri pentru casă"): 1935,
    ("Casă", "Accesorii pentru casă", "Oglinzi"): 1938,
    ("Casă", "Accesorii pentru casă", "Plante și flori artificiale"): 3830,
    ("Casă", "Accesorii pentru casă", "Rafturi de prezentare"): 1941,
    ("Casă", "Accesorii pentru casă", "Rame foto și imagini"): 1937,
    ("Casă", "Accesorii pentru casă", "Sculpturi și figurine"): 3822,
    ("Casă", "Accesorii pentru casă", "Vaze"): 1940,
    ("Casă", "Animale", ""): 5106,
    ("Casă", "Animale", "Animale de companie mici"): 5111,
    ("Casă", "Animale", "Câini"): 5107,
    ("Casă", "Animale", "Pești"): 5112,
    ("Casă", "Animale", "Pisici"): 5108,
    ("Casă", "Animale", "Păsări"): 5110,
    ("Casă", "Animale", "Reptile"): 5109,
    ("Casă", "Aparate electrocasnice mici", ""): 3474,
    ("Casă", "Aparate electrocasnice mici", "Accesorii pentru electrocasnice mici de bucătărie"): 3490,
    ("Casă", "Aparate electrocasnice mici", "Aparate pentru cafea, ceai și espresso"): 3480,
    ("Casă", "Aparate electrocasnice mici", "Aparate specializate"): 3489,
    ("Casă", "Aparate electrocasnice mici", "Blendere, mixere și procesoare de alimente"): 3482,
    ("Casă", "Aparate electrocasnice mici", "Ceainice"): 3479,
    ("Casă", "Aparate electrocasnice mici", "Dozatoare pentru apă și suc"): 3488,
    ("Casă", "Aparate electrocasnice mici", "Friteuze"): 3484,
    ("Casă", "Aparate electrocasnice mici", "Grătare și grătare electrice"): 3486,
    ("Casă", "Aparate electrocasnice mici", "Microunde"): 3483,
    ("Casă", "Aparate electrocasnice mici", "Piese pentru electrocasnice mici de bucătărie"): 3491,
    ("Casă", "Aparate electrocasnice mici", "Plite"): 3485,
    ("Casă", "Aparate electrocasnice mici", "Prăjitoare de pâine"): 3481,
    ("Casă", "Aparate electrocasnice mici", "Storcătoare"): 3487,
    ("Casă", "Articole de masă", ""): 1920,
    ("Casă", "Articole de masă", "Pahare"): 2005,
    ("Casă", "Articole de masă", "Tacâmuri"): 1931,
    ("Casă", "Articole de masă", "Veselă"): 1932,
    ("Casă", "Consumabile de birou", ""): 5428,
    ("Casă", "Consumabile de birou", "Accesorii pentru birou"): 5434,
    ("Casă", "Consumabile de birou", "Aparate electronice de birou"): 5441,
    ("Casă", "Consumabile de birou", "Bandă adezivă, cleme și elemente de fixare"): 5438,
    ("Casă", "Consumabile de birou", "Caiete și blocuri de scris"): 5430,
    ("Casă", "Consumabile de birou", "Calculatoare"): 5433,
    ("Casă", "Consumabile de birou", "Capsatoare și perforatoare"): 5439,
    ("Casă", "Consumabile de birou", "Consumabile pentru scris"): 5436,
    ("Casă", "Consumabile de birou", "Instrumente pentru desen tehnic"): 5437,
    ("Casă", "Consumabile de birou", "Materiale pentru prezentări"): 5440,
    ("Casă", "Consumabile de birou", "Organizatoare de documente"): 5435,
    ("Casă", "Consumabile de birou", "Penare"): 5431,
    ("Casă", "Consumabile de birou", "Planificatoare și agende personale"): 5429,
    ("Casă", "Consumabile de birou", "Seifuri"): 5442,
    ("Casă", "Consumabile de birou", "Semne de carte"): 5432,
    ("Casă", "Exterior și grădină", ""): 3812,
    ("Casă", "Exterior și grădină", "Accesorii pentru unelte electrice de exterior"): 3889,
    ("Casă", "Exterior și grădină", "Decor pentru exterior și grădină"): 3893,
    ("Casă", "Exterior și grădină", "Echipament de udare"): 3892,
    ("Casă", "Exterior și grădină", "Ghivece, jardiniere și accesorii"): 3891,
    ("Casă", "Exterior și grădină", "Instrumente meteorologice"): 3896,
    ("Casă", "Exterior și grădină", "Spa-uri, piscine și echipamente"): 3895,
    ("Casă", "Exterior și grădină", "Unelte de mână pentru exterior"): 3890,
    ("Casă", "Exterior și grădină", "Unelte electrice pentru exterior"): 3888,
    ("Casă", "Exterior și grădină", "Unelte pentru îndepărtarea zăpezii"): 3897,
    ("Casă", "Exterior și grădină", "Ustensile pentru grătar și gătit în aer liber"): 3894,
    ("Casă", "Festivități și sărbători", ""): 2915,
    ("Casă", "Festivități și sărbători", "Bannere, steaguri și fanioane"): 2917,
    ("Casă", "Festivități și sărbători", "Coronițe"): 2926,
    ("Casă", "Festivități și sărbători", "Cărți poștale și plicuri"): 2918,
    ("Casă", "Festivități și sărbători", "Decor de sărbători"): 2922,
    ("Casă", "Festivități și sărbători", "Decorațiuni de masă"): 2924,
    ("Casă", "Festivități și sărbători", "Decorațiuni de petrecere"): 2923,
    ("Casă", "Festivități și sărbători", "Decorațiuni pentru copaci"): 2925,
    ("Casă", "Festivități și sărbători", "Hârtie și pungi de cadouri"): 2921,
    ("Casă", "Textile", ""): 1919,
    ("Casă", "Textile", "Covoare și covorașe"): 1927,
    ("Casă", "Textile", "Fețe de masă"): 1928,
    ("Casă", "Textile", "Huse"): 3869,
    ("Casă", "Textile", "Lenjerie de pat"): 1924,
    ("Casă", "Textile", "Perdele și jaluzele"): 1926,
    ("Casă", "Textile", "Perne decorative"): 1974,
    ("Casă", "Textile", "Prosoape"): 1930,
    ("Casă", "Textile", "Pături"): 1925,
    ("Casă", "Textile", "Tapiserii"): 1929,
    ("Casă", "Unelte și DIY", ""): 3811,
    ("Casă", "Unelte și DIY", "Accesorii pentru unelte"): 3882,
    ("Casă", "Unelte și DIY", "Casă inteligentă și securitate"): 3887,
    ("Casă", "Unelte și DIY", "Echipament de protecție"): 3883,
    ("Casă", "Unelte și DIY", "Echipament pentru electricieni"): 3880,
    ("Casă", "Unelte și DIY", "Echipamente pentru atelier și șantier"): 3885,
    ("Casă", "Unelte și DIY", "Feronerie"): 3886,
    ("Casă", "Unelte și DIY", "Instrumente de măsurare"): 3877,
    ("Casă", "Unelte și DIY", "Transport și depozitare unelte"): 3884,
    ("Casă", "Unelte și DIY", "Unelte de zidărie"): 3881,
    ("Casă", "Unelte și DIY", "Unelte electrice"): 3875,
    ("Casă", "Unelte și DIY", "Unelte instalații sanitare"): 3879,
    ("Casă", "Unelte și DIY", "Unelte manuale"): 3876,
    ("Casă", "Unelte și DIY", "Unelte și accesorii pentru vopsit"): 3878,
    ("Casă", "Ustensile de bucătărie", ""): 3477,
    ("Casă", "Ustensile de bucătărie", "Boluri de amestecare"): 3521,
    ("Casă", "Ustensile de bucătărie", "Cântar de bucătărie"): 3518,
    ("Casă", "Ustensile de bucătărie", "Căni și linguri de măsurat"): 3519,
    ("Casă", "Ustensile de bucătărie", "Depozitarea alimentelor"): 3523,
    ("Casă", "Ustensile de bucătărie", "Sită, strecurătoare"): 3522,
    ("Casă", "Ustensile de bucătărie", "Termometre alimentare"): 3520,
    ("Casă", "Ustensile de bucătărie", "Tocătoare"): 3515,
    ("Casă", "Ustensile de bucătărie", "Unelte de bucătărie speciale"): 3524,
    ("Casă", "Ustensile de bucătărie", "Ustensile de gătit"): 3516,
    ("Casă", "Ustensile de bucătărie", "Ustensile pentru bar"): 3562,
    ("Casă", "Ustensile de gătit și de copt", ""): 3476,
    ("Casă", "Ustensile de gătit și de copt", "Accesorii pentru vase de gătit și de copt"): 3513,
    ("Casă", "Ustensile de gătit și de copt", "Forme de copt"): 3511,
    ("Casă", "Ustensile de gătit și de copt", "Oale"): 3507,
    ("Casă", "Ustensile de gătit și de copt", "Tavă de copt"): 3509,
    ("Casă", "Ustensile de gătit și de copt", "Tigăi"): 3508,
    ("Casă", "Ustensile de gătit și de copt", "Tăvi de cuptor și prăjit"): 3510,
    ("Casă", "Ustensile de gătit și de copt", "Ustensile de gătit și de copt speciale"): 3514,
    ("Casă", "Ustensile de gătit și de copt", "Ustensile pentru gătit și copt"): 3512,
    ("Casă", "Îngrijirea gospodăriei", ""): 3478,
    ("Casă", "Îngrijirea gospodăriei", "Aspirare și curățare"): 3527,
    ("Casă", "Îngrijirea gospodăriei", "Fiare de călcat și îngrijire îmbrăcăminte"): 3526,
    ("Casă", "Îngrijirea gospodăriei", "Încălzire, răcire și aerisire"): 3525,
    ("Electronice", "", ""): 2994,
    ("Electronice", "Alte dispozitive și accesorii", ""): 2995,
    ("Electronice", "Alte dispozitive și accesorii", "Adaptoare"): 3005,
    ("Electronice", "Alte dispozitive și accesorii", "Alte accesorii"): 3013,
    ("Electronice", "Alte dispozitive și accesorii", "Baterii externe"): 3792,
    ("Electronice", "Alte dispozitive și accesorii", "Baterii și surse de alimentare"): 3794,
    ("Electronice", "Alte dispozitive și accesorii", "Cabluri"): 3006,
    ("Electronice", "Alte dispozitive și accesorii", "Cântare pentru bagaje"): 3791,
    ("Electronice", "Alte dispozitive și accesorii", "Detectoare de obiecte"): 3052,
    ("Electronice", "Alte dispozitive și accesorii", "GPS și dispozitive de navigație prin satelit"): 3789,
    ("Electronice", "Alte dispozitive și accesorii", "Imprimare și scanare 3D"): 3788,
    ("Electronice", "Alte dispozitive și accesorii", "Protecții la supratensiune și prelungitoare"): 3793,
    ("Electronice", "Alte dispozitive și accesorii", "Încărcătoare"): 3008,
    ("Electronice", "Audio, căști și hi-fi", ""): 3566,
    ("Electronice", "Audio, căști și hi-fi", "Accesorii pentru dispozitive audio"): 3686,
    ("Electronice", "Audio, căști și hi-fi", "Boxe portabile"): 3681,
    ("Electronice", "Audio, căști și hi-fi", "Căști și earbuds"): 3678,
    ("Electronice", "Audio, căști și hi-fi", "Difuzoare inteligente"): 3682,
    ("Electronice", "Audio, căști și hi-fi", "Piese audio și hi-fi"): 3687,
    ("Electronice", "Audio, căști și hi-fi", "Playere muzicale portabile"): 3679,
    ("Electronice", "Audio, căști și hi-fi", "Radiouri portabile"): 3680,
    ("Electronice", "Audio, căști și hi-fi", "Sisteme audio pentru acasă"): 3683,
    ("Electronice", "Calculatoare și accesorii", ""): 3564,
    ("Electronice", "Calculatoare și accesorii", "Accesorii pentru computere"): 3584,
    ("Electronice", "Calculatoare și accesorii", "Accesorii pentru laptop"): 3585,
    ("Electronice", "Calculatoare și accesorii", "Blank media"): 3583,
    ("Electronice", "Calculatoare și accesorii", "Calculatoare desktop"): 3581,
    ("Electronice", "Calculatoare și accesorii", "Camere web"): 3593,
    ("Electronice", "Calculatoare și accesorii", "Difuzoare pentru computer"): 3591,
    ("Electronice", "Calculatoare și accesorii", "Dispozitive de rețea"): 3594,
    ("Electronice", "Calculatoare și accesorii", "Docking stations și hub-uri USB"): 3586,
    ("Electronice", "Calculatoare și accesorii", "Imprimante și accesorii"): 3595,
    ("Electronice", "Calculatoare și accesorii", "Laptopuri"): 3580,
    ("Electronice", "Calculatoare și accesorii", "Microfoane de calculator"): 3592,
    ("Electronice", "Calculatoare și accesorii", "Monitoare și accesorii"): 3590,
    ("Electronice", "Calculatoare și accesorii", "Mouse pad-uri"): 3589,
    ("Electronice", "Calculatoare și accesorii", "Mouse-uri"): 3588,
    ("Electronice", "Calculatoare și accesorii", "Piese și componente de calculator"): 3582,
    ("Electronice", "Calculatoare și accesorii", "Plăcuțe tactile și stylus"): 3597,
    ("Electronice", "Calculatoare și accesorii", "Scanere și accesorii"): 3596,
    ("Electronice", "Calculatoare și accesorii", "Tastaturi și accesorii"): 3587,
    ("Electronice", "Camere foto și accesorii", ""): 3054,
    ("Electronice", "Camere foto și accesorii", "Accesorii"): 3059,
    ("Electronice", "Camere foto și accesorii", "Alte echipamente fotografice"): 3064,
    ("Electronice", "Camere foto și accesorii", "Blițuri"): 3062,
    ("Electronice", "Camere foto și accesorii", "Camere foto"): 3060,
    ("Electronice", "Camere foto și accesorii", "Carduri de memorie"): 3063,
    ("Electronice", "Camere foto și accesorii", "Drone cu cameră și accesorii"): 3716,
    ("Electronice", "Camere foto și accesorii", "Echipament de studio"): 3066,
    ("Electronice", "Camere foto și accesorii", "Echipament pentru camera obscură"): 3715,
    ("Electronice", "Camere foto și accesorii", "Obiective"): 3061,
    ("Electronice", "Camere foto și accesorii", "Piese de schimb pentru aparat foto"): 3717,
    ("Electronice", "Camere foto și accesorii", "Stabilizatoare și suporturi"): 3065,
    ("Electronice", "Camere foto și accesorii", "Trepieduri și monopieduri"): 3067,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", ""): 3569,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Bărbierit și îndepărtarea părului"): 3760,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Cântare pentru uz personal"): 3764,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Instrumente de coafură"): 3758,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Instrumente de masaj"): 3761,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Instrumente de înfrumusețare"): 3759,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Instrumente pentru îngrijirea unghiilor"): 3763,
    ("Electronice", "Electronice pentru frumusețe și îngrijire personală", "Îngrijire dentară și orală electrică"): 3762,
    ("Electronice", "Jocuri video și console", ""): 3002,
    ("Electronice", "Jocuri video și console", "Accesorii"): 3024,
    ("Electronice", "Jocuri video și console", "Console"): 3025,
    ("Electronice", "Jocuri video și console", "Controlere"): 3570,
    ("Electronice", "Jocuri video și console", "Căști pentru jocuri"): 3571,
    ("Electronice", "Jocuri video și console", "Jocuri"): 3026,
    ("Electronice", "Jocuri video și console", "Realitate virtuală"): 3576,
    ("Electronice", "Jocuri video și console", "Simulatoare"): 3575,
    ("Electronice", "Portabile", ""): 3004,
    ("Electronice", "Portabile", "Benzi de schimb"): 3032,
    ("Electronice", "Portabile", "Carcase pentru ceasuri inteligente"): 3810,
    ("Electronice", "Portabile", "Ceasuri inteligente"): 3035,
    ("Electronice", "Portabile", "Inele inteligente"): 3034,
    ("Electronice", "Portabile", "Monitoare de fitness"): 3031,
    ("Electronice", "Portabile", "Ochelari inteligenți"): 3033,
    ("Electronice", "TV și home cinema", ""): 3568,
    ("Electronice", "TV și home cinema", "Accesorii TV și home cinema"): 3750,
    ("Electronice", "TV și home cinema", "Alte dispozitive de redare video"): 3749,
    ("Electronice", "TV și home cinema", "Antene TV"): 3741,
    ("Electronice", "TV și home cinema", "Antene satelit"): 3742,
    ("Electronice", "TV și home cinema", "DVD playere"): 3747,
    ("Electronice", "TV și home cinema", "Decodificatoare video"): 3743,
    ("Electronice", "TV și home cinema", "Dispozitive de streaming"): 3740,
    ("Electronice", "TV și home cinema", "Playere Blu-ray"): 3746,
    ("Electronice", "TV și home cinema", "Proiectoare"): 3739,
    ("Electronice", "TV și home cinema", "Receptoare de televiziune"): 3744,
    ("Electronice", "TV și home cinema", "Sisteme home cinema"): 3745,
    ("Electronice", "TV și home cinema", "Televizoare"): 3738,
    ("Electronice", "TV și home cinema", "Videocasetofoane"): 3748,
    ("Electronice", "Tablete, e-readere și accesorii", ""): 3567,
    ("Electronice", "Tablete, e-readere și accesorii", "Accesorii"): 3732,
    ("Electronice", "Tablete, e-readere și accesorii", "Agende electronice"): 3730,
    ("Electronice", "Tablete, e-readere și accesorii", "E-readere"): 3729,
    ("Electronice", "Tablete, e-readere și accesorii", "PDAs"): 3731,
    ("Electronice", "Tablete, e-readere și accesorii", "Tablete"): 3728,
    ("Electronice", "Telefoane mobile și comunicare", ""): 3565,
    ("Electronice", "Telefoane mobile și comunicare", "Comunicații radio"): 3665,
    ("Electronice", "Telefoane mobile și comunicare", "Faxuri"): 3664,
    ("Electronice", "Telefoane mobile și comunicare", "Piese și accesorii pentru telefoane mobile"): 3662,
    ("Electronice", "Telefoane mobile și comunicare", "Telefoane fixe"): 3663,
    ("Electronice", "Telefoane mobile și comunicare", "Telefoane mobile"): 3661,
    ("Electronice", "Telefoane mobile și comunicare", "Telefoane mobile demo"): 3666,
    ("Media și cărți", "", ""): 2309,
    ("Media și cărți", "Cărți", ""): 2312,
    ("Media și cărți", "Cărți", "Benzi desenate, manga și romane grafice"): 5425,
    ("Media și cărți", "Cărți", "Copii și tineri adulți"): 2318,
    ("Media și cărți", "Cărți", "Cărți de colorat, puzzle și activități"): 5427,
    ("Media și cărți", "Cărți", "Ficțiune"): 2319,
    ("Media și cărți", "Cărți", "Manuale și materiale de studiu"): 5426,
    ("Media și cărți", "Cărți", "Non-ficțiune"): 2320,
    ("Media și cărți", "Muzică", ""): 3036,
    ("Media și cărți", "Muzică", "CD-uri"): 3039,
    ("Media și cărți", "Muzică", "Casete audio"): 3038,
    ("Media și cărți", "Muzică", "Discuri de vinil"): 3041,
    ("Media și cărți", "Muzică", "MiniDiscuri"): 3040,
    ("Media și cărți", "Reviste", ""): 5424,
    ("Media și cărți", "Video", ""): 3037,
    ("Media și cărți", "Video", "4K Blu-ray"): 3042,
    ("Media și cărți", "Video", "Betamax"): 3043,
    ("Media și cărți", "Video", "Blu-ray"): 3044,
    ("Media și cărți", "Video", "DVD"): 3045,
    ("Media și cărți", "Video", "HD DVD"): 3046,
    ("Media și cărți", "Video", "LaserDisc"): 3047,
    ("Media și cărți", "Video", "VHS"): 3048,
    ("Hobbyuri și colecții", "", ""): 4824,
    ("Hobbyuri și colecții", "Accesorii pentru jocuri", ""): 4916,
    ("Hobbyuri și colecții", "Accesorii pentru jocuri", "Alte accesorii pentru jocuri"): 4920,
    ("Hobbyuri și colecții", "Accesorii pentru jocuri", "Covoare pentru jocuri"): 4919,
    ("Hobbyuri și colecții", "Accesorii pentru jocuri", "Pietre și jetoane de joc"): 4918,
    ("Hobbyuri și colecții", "Accesorii pentru jocuri", "Zar"): 4917,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", ""): 5151,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Caligrafie"): 5293,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Cusut, tricotat și broderie"): 5152,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Desene și schițe"): 5276,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Fabricarea lumânărilor"): 5349,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Materiale pentru artizanat"): 5372,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Mărgele și accesorii de bijuterii"): 5301,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Papercraft"): 5322,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Pictură"): 5251,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Sculptură și olărit"): 5357,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Tăiere cu matrița"): 5339,
    ("Hobbyuri și colecții", "Arte și meșteșuguri", "Unelte de meșteșugărit"): 5401,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", ""): 4874,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Carduri de tranzacționare individuale"): 4875,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Cutii Booster"): 4877,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Loturi de carduri de tranzacționare"): 4879,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Pachete Booster"): 4876,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Pachete de cărți de joc"): 4878,
    ("Hobbyuri și colecții", "Carduri de tranzacționare", "Poster cu carduri"): 4880,
    ("Hobbyuri și colecții", "Cărți poștale", ""): 4894,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", ""): 4906,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Albume și clasoare"): 4907,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Covoare pentru puzzle"): 4914,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Cutii pentru pachete de cărți"): 4911,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Cutii pentru păstrarea obiectelor de colecție"): 4908,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Depozitarea altor obiecte de colecție"): 4915,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Folii pentru albume și clasoare"): 4913,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Huse pentru cărți de joc"): 4909,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Separatoare pentru albume și clasoare"): 4912,
    ("Hobbyuri și colecții", "Depozitare obiecte de colecție", "Suporturi de carduri cu șurub"): 4910,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", ""): 4825,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Accesorii pentru creație muzicală"): 4831,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Amplificatoare și pedale"): 4826,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Chitare și chitare bas"): 4828,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Claviaturi și sintetizatoare"): 4830,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Echipament DJ"): 5091,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Echipament de studio și sunet live"): 4833,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Echipament pentru karaoke"): 4829,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Instrumente cu coarde"): 4832,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Instrumente de suflat"): 4834,
    ("Hobbyuri și colecții", "Instrumente muzicale și echipamente", "Tobe și percuție"): 4827,
    ("Hobbyuri și colecții", "Jocuri de masă și în miniatură", ""): 4883,
    ("Hobbyuri și colecții", "Jocuri de societate", ""): 4881,
    ("Hobbyuri și colecții", "Monede și bancnote", ""): 4895,
    ("Hobbyuri și colecții", "Monede și bancnote", "Bancnote"): 4896,
    ("Hobbyuri și colecții", "Monede și bancnote", "Certificate de acțiuni"): 4900,
    ("Hobbyuri și colecții", "Monede și bancnote", "Loturi și seturi"): 4898,
    ("Hobbyuri și colecții", "Monede și bancnote", "Medalii și recompense"): 4899,
    ("Hobbyuri și colecții", "Monede și bancnote", "Monede"): 4897,
    ("Hobbyuri și colecții", "Puzzle-uri", ""): 4882,
    ("Hobbyuri și colecții", "Suveniruri", ""): 4901,
    ("Hobbyuri și colecții", "Suveniruri", "Alte suveniruri"): 4905,
    ("Hobbyuri și colecții", "Suveniruri", "Suvenir sportiv"): 4902,
    ("Hobbyuri și colecții", "Suveniruri", "Suveniruri de film și TV"): 4904,
    ("Hobbyuri și colecții", "Suveniruri", "Suveniruri muzicale"): 4903,
    ("Hobbyuri și colecții", "Timbre", ""): 4888,
    ("Hobbyuri și colecții", "Timbre", "Cataloage și ghiduri de timbre"): 4892,
    ("Hobbyuri și colecții", "Timbre", "First day covers (FDC)"): 4891,
    ("Hobbyuri și colecții", "Timbre", "Instrumente și echipamente pentru timbre"): 4893,
    ("Hobbyuri și colecții", "Timbre", "Loturi și seturi de timbre"): 4890,
    ("Hobbyuri și colecții", "Timbre", "Timbre individuale"): 4889,
    ("Sporturi", "", ""): 4332,
    ("Sporturi", "Box și arte marțiale", ""): 4342,
    ("Sporturi", "Box și arte marțiale", "Alte echipamente pentru arte marțiale"): 4625,
    ("Sporturi", "Box și arte marțiale", "Centuri de arte marțiale"): 4621,
    ("Sporturi", "Box și arte marțiale", "Fășii pentru protecția mâinilor"): 4620,
    ("Sporturi", "Box și arte marțiale", "Mănuși de box și arte marțiale"): 4619,
    ("Sporturi", "Box și arte marțiale", "Protecție corporală pentru box și arte marțiale"): 4617,
    ("Sporturi", "Box și arte marțiale", "Protecție pentru cap pentru box și arte marțiale"): 4616,
    ("Sporturi", "Box și arte marțiale", "Protecții pentru lovituri cu pumnul și piciorul"): 4618,
    ("Sporturi", "Box și arte marțiale", "Saci de box grei"): 4622,
    ("Sporturi", "Box și arte marțiale", "Saci de box viteză"): 4624,
    ("Sporturi", "Ciclism", ""): 4333,
    ("Sporturi", "Ciclism", "Accesorii și unelte pentru ciclism"): 4349,
    ("Sporturi", "Ciclism", "Biciclete pentru copii"): 4347,
    ("Sporturi", "Ciclism", "Căști pentru biciclete"): 4348,
    ("Sporturi", "Ciclism", "Piese de bicicletă"): 4353,
    ("Sporturi", "Ciclism", "Remorci pentru biciclete"): 4351,
    ("Sporturi", "Ciclism", "Scaune pentru biciclete pentru copii"): 4352,
    ("Sporturi", "Echitație", ""): 4340,
    ("Sporturi", "Echitație", "Caschete de echitație"): 4810,
    ("Sporturi", "Echitație", "Huse de mătase pentru căști de echitație"): 4812,
    ("Sporturi", "Echitație", "Mănuși de echitație"): 4811,
    ("Sporturi", "Echitație", "Veste de protecție pentru călărie"): 4809,
    ("Sporturi", "Echitație", "Șei și accesorii"): 4742,
    ("Sporturi", "Fitness, alergare și yoga", ""): 4334,
    ("Sporturi", "Fitness, alergare și yoga", "Accesorii de fitness pentru acasă"): 4417,
    ("Sporturi", "Fitness, alergare și yoga", "Alergare"): 4415,
    ("Sporturi", "Fitness, alergare și yoga", "Antrenament de forță"): 4414,
    ("Sporturi", "Fitness, alergare și yoga", "Echipament pentru yoga și pilates"): 4416,
    ("Sporturi", "Fitness, alergare și yoga", "Sticle de apă"): 4698,
    ("Sporturi", "Golf", ""): 4339,
    ("Sporturi", "Golf", "Accesorii de golf"): 4470,
    ("Sporturi", "Golf", "Crose de golf"): 4473,
    ("Sporturi", "Golf", "Cărucioare de golf"): 4475,
    ("Sporturi", "Golf", "Echipament de antrenament pentru golf"): 4476,
    ("Sporturi", "Golf", "Mingi de golf"): 4472,
    ("Sporturi", "Golf", "Mănuși de golf"): 4474,
    ("Sporturi", "Golf", "Saci de golf"): 4471,
    ("Sporturi", "Skateboard-uri și scutere", ""): 4341,
    ("Sporturi", "Skateboard-uri și scutere", "Căști de skateboarding"): 4608,
    ("Sporturi", "Skateboard-uri și scutere", "Piese și accesorii pentru skate"): 4610,
    ("Sporturi", "Skateboard-uri și scutere", "Piese și accesorii pentru skateboard"): 4611,
    ("Sporturi", "Skateboard-uri și scutere", "Plăci de longboard"): 4606,
    ("Sporturi", "Skateboard-uri și scutere", "Protecție pentru skateboard"): 4609,
    ("Sporturi", "Skateboard-uri și scutere", "Scutere"): 4818,
    ("Sporturi", "Skateboard-uri și scutere", "Skateboarduri"): 4607,
    ("Sporturi", "Sporturi cu rachetă", ""): 4338,
    ("Sporturi", "Sporturi cu rachetă", "Badminton"): 4479,
    ("Sporturi", "Sporturi cu rachetă", "Padel"): 4482,
    ("Sporturi", "Sporturi cu rachetă", "Pickleball"): 4483,
    ("Sporturi", "Sporturi cu rachetă", "Protecție pentru ochi în sporturile cu rachetă"): 4484,
    ("Sporturi", "Sporturi cu rachetă", "Racquetball"): 4480,
    ("Sporturi", "Sporturi cu rachetă", "Squash"): 4478,
    ("Sporturi", "Sporturi cu rachetă", "Tenis"): 4477,
    ("Sporturi", "Sporturi cu rachetă", "Tenis de masă"): 4481,
    ("Sporturi", "Sporturi de echipă", ""): 4337,
    ("Sporturi", "Sporturi de echipă", "Alte echipamente pentru sporturi de echipă"): 4499,
    ("Sporturi", "Sporturi de echipă", "Baschet"): 4486,
    ("Sporturi", "Sporturi de echipă", "Baseball și softball"): 4492,
    ("Sporturi", "Sporturi de echipă", "Cricket"): 4493,
    ("Sporturi", "Sporturi de echipă", "Echipament de antrenament și de arbitraj"): 4490,
    ("Sporturi", "Sporturi de echipă", "Fotbal"): 4485,
    ("Sporturi", "Sporturi de echipă", "Fotbal american"): 4491,
    ("Sporturi", "Sporturi de echipă", "Handball"): 4487,
    ("Sporturi", "Sporturi de echipă", "Hochei de sală"): 4495,
    ("Sporturi", "Sporturi de echipă", "Hochei pe iarbă"): 4494,
    ("Sporturi", "Sporturi de echipă", "Lacrosse"): 4497,
    ("Sporturi", "Sporturi de echipă", "Netball"): 4498,
    ("Sporturi", "Sporturi de echipă", "Rugby"): 4489,
    ("Sporturi", "Sporturi de echipă", "Sporturi gaelice"): 4496,
    ("Sporturi", "Sporturi de echipă", "Volei"): 4488,
    ("Sporturi", "Sporturi de iarnă", ""): 4344,
    ("Sporturi", "Sporturi de iarnă", "Accesorii pentru patinaj artistic"): 4716,
    ("Sporturi", "Sporturi de iarnă", "Căști pentru sporturi de iarnă"): 4721,
    ("Sporturi", "Sporturi de iarnă", "Echipament de schi"): 4713,
    ("Sporturi", "Sporturi de iarnă", "Echipament pentru snowboard"): 4714,
    ("Sporturi", "Sporturi de iarnă", "Ghetre"): 4719,
    ("Sporturi", "Sporturi de iarnă", "Hochei pe gheață"): 4715,
    ("Sporturi", "Sporturi de iarnă", "Ochelari de schi"): 4720,
    ("Sporturi", "Sporturi de iarnă", "Rachete de zăpadă"): 4718,
    ("Sporturi", "Sporturi de iarnă", "Săniuș"): 4717,
    ("Sporturi", "Sporturi nautice", ""): 4336,
    ("Sporturi", "Sporturi nautice", "Accesorii pentru sporturi nautice"): 4769,
    ("Sporturi", "Sporturi nautice", "Caiace"): 4759,
    ("Sporturi", "Sporturi nautice", "Colac remorcabil"): 4763,
    ("Sporturi", "Sporturi nautice", "Costume, mănuși și ghete de neopren"): 4768,
    ("Sporturi", "Sporturi nautice", "Căști pentru sporturi nautice"): 4767,
    ("Sporturi", "Sporturi nautice", "Dispozitive personale de plutire"): 4766,
    ("Sporturi", "Sporturi nautice", "Kiteboarduri"): 4760,
    ("Sporturi", "Sporturi nautice", "Plute gonflabile"): 4758,
    ("Sporturi", "Sporturi nautice", "Plăci de paddleboarding"): 4784,
    ("Sporturi", "Sporturi nautice", "Plăci de wakeboard"): 4764,
    ("Sporturi", "Sporturi nautice", "Schiuri de apă"): 4765,
    ("Sporturi", "Sporturi nautice", "Skimboards"): 4761,
    ("Sporturi", "Sporturi nautice", "Înot"): 4747,
    ("Sporturi", "Sporturi în aer liber", ""): 4335,
    ("Sporturi", "Sporturi în aer liber", "Alte accesorii pentru sporturi în aer liber"): 4666,
    ("Sporturi", "Sporturi în aer liber", "Arzătoare de camping și ustensile de gătit"): 4657,
    ("Sporturi", "Sporturi în aer liber", "Bețe de trekking"): 4663,
    ("Sporturi", "Sporturi în aer liber", "Binocluri și lunete"): 4658,
    ("Sporturi", "Sporturi în aer liber", "Busole"): 4664,
    ("Sporturi", "Sporturi în aer liber", "Corturi de camping și echipament de dormit"): 4652,
    ("Sporturi", "Sporturi în aer liber", "Cățărare și bouldering"): 4626,
    ("Sporturi", "Sporturi în aer liber", "Mobilier de camping"): 4661,
    ("Sporturi", "Sporturi în aer liber", "Pescuit și vânătoare"): 4627,
    ("Sporturi", "Sporturi în aer liber", "Rucsacuri pentru drumeții"): 4665,
    ("Sporturi", "Sporturi în aer liber", "Răcitoare"): 4659,
    ("Sporturi", "Sporturi în aer liber", "Sisteme și pachete de hidratare"): 4660,
    ("Sporturi", "Sporturi în aer liber", "Torțe, faruri și lanterne"): 4662,
    ("Sporturi", "Sporturi și jocuri ocazionale", ""): 4343,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Biliard american și snooker"): 4687,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Boules & alte jocuri"): 4682,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Bowling cu zece popice"): 4689,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Echipament pentru darts"): 4683,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Frisbee și disc golf"): 4684,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Mingi pentru terenul de joacă"): 4686,
    ("Sporturi", "Sporturi și jocuri ocazionale", "Roundnet și spikeball"): 4688,
}


def _resolve_from_map(category, subcategory):
    """Rezolvare din harta hardcodata VINTED_CATALOG_ID_MAP (fallback-ul istoric).

    Doua formate coexista pe keyword.category:
      • wizard: "Tab > Categorie" + subcategory text -> lookup in map (arborele live);
      • edit form vechi: catalog_id numeric brut din dropdown -> folosit direct ca filtru.
    Ordine descrescatoare de specificitate: subcategorie -> categorie -> tab. None daca nimic.
    """
    if not category:
        return None
    sub_raw = (subcategory or "").strip()
    if sub_raw.isdigit():
        return int(sub_raw)
    if str(category).strip().isdigit():
        return int(str(category).strip())
    parts = [p.strip() for p in category.split(">")]
    tab = parts[0] if len(parts) > 0 else ""
    cat = parts[1] if len(parts) > 1 else ""
    sub = (subcategory or "").strip()
    if sub:
        cid = VINTED_CATALOG_ID_MAP.get((tab, cat, sub))
        if cid:
            return cid
    if cat:
        cid = VINTED_CATALOG_ID_MAP.get((tab, cat, ""))
        if cid:
            return cid
    return VINTED_CATALOG_ID_MAP.get((tab, "", ""))


def _resolve_vinted_catalog_id(category, subcategory, db=None, marketplace_config=None):
    """RP-2 — rezolvare cu PRECEDENȚĂ: config > tabelul dinamic vinted_catalogs > harta.
    Logheaza sursa. `db`/`marketplace_config` sunt optionale (compat: fara ele = doar harta).
    """
    # 1) catalog_id explicit din marketplace_config (wizard-ul nou)
    if isinstance(marketplace_config, dict):
        raw = marketplace_config.get("vinted_catalog_id")
        if raw:
            try:
                cid = int(raw)
                log_manager.emit("radar", "INFO", f"Vinted catalog_id={cid} (sursă: config)")
                return cid
            except (TypeError, ValueError):
                pass
    # 2) tabelul dinamic vinted_catalogs (după titluri normalizate pe path)
    if db is not None:
        try:
            from app.services.radar.vinted_catalog_service import find_catalog_id_by_titles
            cid = find_catalog_id_by_titles(db, category, subcategory)
            if cid:
                log_manager.emit("radar", "INFO", f"Vinted catalog_id={cid} (sursă: db)")
                return cid
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Vinted catalog DB lookup eșuat: {str(exc)[:60]}")
    # 3) harta hardcodata (fallback existent, zero regresii)
    cid = _resolve_from_map(category, subcategory)
    if cid:
        log_manager.emit("radar", "INFO", f"Vinted catalog_id={cid} (sursă: map)")
    return cid


def _strip_accents(s: Optional[str]) -> str:
    return (s or "").lower().replace("ă", "a").replace("â", "a").replace("î", "i") \
        .replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")


def _apply_subcategory_filter(results: list, subcategory: Optional[str]) -> list:
    """MODIFICARE 4 — filtrare post-scrape pe subcategorie (Vinted nu întoarce
    metadata de categorie în rezultate). Un anunț trece dacă subcategoria apare
    ca substring (accent-insensitive) în titlu sau descriere.

    Non-destructiv: dacă filtrul ar elimina TOATE rezultatele (ex: forme flexionare
    diferite gen "rochie"/"Rochii"), păstrăm rezultatele filtrate pe keyword ca să
    nu golim feed-ul; logăm before/after ca să fie vizibil în Jurnale Live.
    """
    if not subcategory:
        return results
    full = _strip_accents(subcategory)
    if not full:
        return results
    # Stem-ul primului cuvant (max 5 caractere) tolereaza plural/singular romanesc
    # ("Rochii"->"rochi" prinde "rochie"; "Rucsacuri"->"rucsa" prinde "rucsac").
    first_word = full.split()[0] if full.split() else full
    stem = first_word[:5] if len(first_word) >= 5 else first_word

    def _matches(r: dict) -> bool:
        hay = _strip_accents(r.get("title")) + " " + _strip_accents(r.get("description"))
        return (full in hay) or (len(stem) >= 4 and stem in hay)

    before = len(results)
    filtered = [r for r in results if isinstance(r, dict) and _matches(r)]
    log_manager.emit("radar", "INFO",
                     f"Vinted subcategorie '{subcategory}': {before} → {len(filtered)} după filtrare")
    if not filtered and before:
        # Nicio potrivire (probabil flexionare) — nu golim feed-ul, pastram keyword-only.
        log_manager.emit("radar", "WARN",
                         f"Vinted subcategorie '{subcategory}': 0 potriviri pe titlu/descriere — pastrez rezultatele pe keyword")
        return results
    return filtered


def _condition_label(api_label: Optional[str]) -> Optional[str]:
    if not api_label:
        return None
    t = api_label.lower()
    if "nou" in t or "new" in t:
        return "nou"
    if "bun" in t or "good" in t or "satisf" in t or "purtat" in t or "rezonab" in t:
        return "second hand"
    return None


def _search_vinted_library(
    keyword: str,
    max_price: Optional[float],
    min_price: Optional[float],
    category: Optional[str],
    exclude_words: list,
    exclude_description_words: list,
    subcategory: Optional[str] = None,
    page: int = 1,
    catalog_id: Optional[int] = None,
) -> list:
    """Cauta pe Vinted prin VintedWrapper (JSON brut, sesiune singleton). Returneaza
    intotdeauna o lista (goala la eroare sau zero rezultate).

    Fata de varianta veche (VintedScraper tipizat, instanta per-apel): reutilizeaza
    sesiunea si citeste direct din dict-ul brut al search-ului `user.login`/`user.id`
    (nume/id vanzator), `photo.high_resolution.timestamp` (data postarii) si
    `view_count`/`favourite_count` (in `extra_attributes`). `description` NU exista in
    search (dovedit RP-DIAG) -> ramane None pana la enrichment.
    """
    global _wrapper_fail_count
    wrapper = _get_wrapper()
    if wrapper is None:
        return []

    params = {"search_text": (keyword or "").strip(), "order": "newest_first", "per_page": 96}
    if page > 1:
        params["page"] = page
    if max_price and max_price > 0:
        params["price_to"] = int(max_price)
    if min_price and min_price > 0:
        params["price_from"] = int(min_price)
    # Filtrare server-side: catalog_id-ul e rezolvat de apelant (search_vinted) cu
    # precedența config > db > map. Aici doar îl aplicăm dacă a fost furnizat.
    if catalog_id:
        params["catalog_ids"] = [catalog_id]
        _label = (category or "") + (f" > {subcategory}" if subcategory else "")
        print(f"[VintedScraper] catalog_id={catalog_id} pentru '{_label}'")

    try:
        raw = wrapper.search(params)
        _wrapper_fail_count = 0
    except Exception as exc:
        _wrapper_fail_count += 1
        log_manager.emit("radar", "ERR",
            f"Vinted search eroare ({_wrapper_fail_count}/2): {str(exc)[:100]}")
        # Dupa 2 esecuri consecutive, invalideaza sesiunea (se reconstruieste la urmatorul apel).
        if _wrapper_fail_count >= 2:
            _invalidate_wrapper()
        return []

    items = raw.get("items") if isinstance(raw, dict) else None
    results = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title or is_excluded(title, exclude_words):
            continue

        price_obj = item.get("price")
        try:
            if isinstance(price_obj, dict):
                price = float(price_obj.get("amount"))
            elif price_obj is not None:
                price = float(price_obj)
            else:
                price = None
        except (TypeError, ValueError):
            price = None
        if price is None or price <= 0:
            continue
        if max_price and price > max_price:
            continue
        if min_price and price < min_price:
            continue
        currency = (price_obj.get("currency_code") if isinstance(price_obj, dict) else None) or "RON"

        user = item.get("user") or {}
        seller_name = user.get("login") if isinstance(user, dict) else None
        seller_id = str(user.get("id")) if isinstance(user, dict) and user.get("id") is not None else None

        photo = item.get("photo") or {}
        thumb = None
        ts = None
        if isinstance(photo, dict):
            thumb = photo.get("url") or photo.get("full_size_url")
            hr = photo.get("high_resolution") or {}
            ts = hr.get("timestamp") if isinstance(hr, dict) else None
        listed_at = None
        if ts:
            try:
                listed_at = datetime.fromtimestamp(int(ts))  # naiv local (conventia scraperelor)
            except (TypeError, ValueError, OSError):
                listed_at = None

        item_id = item.get("id")
        url = item.get("url") or (f"https://www.vinted.ro/items/{item_id}" if item_id else "")

        extra = {}
        if item.get("view_count") is not None:
            extra["view_count"] = item.get("view_count")
        if item.get("favourite_count") is not None:
            extra["favourite_count"] = item.get("favourite_count")
        if item.get("brand_title"):
            extra["brand"] = item.get("brand_title")

        results.append({
            "external_id": f"vinted_{item_id}" if item_id else None,
            "platform": "vinted",
            "title": title,
            "price": price,
            "currency": currency,
            "condition": _condition_label(str(item.get("status") or "")),
            "location": None,
            "url": url,
            "images": [thumb] if thumb else [],
            "description": None,  # nu exista in search (RP-DIAG) — vine la enrichment
            "seller_name": seller_name,
            "seller_id": seller_id,
            "listed_at": listed_at,
            "extra_attributes": extra or None,
        })
    # Nota: `exclude_description_words` nu se poate aplica la Vinted in search (payload-ul
    # nu contine descriere) — filtrarea pe descriere ramane la enrichment/altele.
    _ = exclude_description_words
    log_manager.emit("radar", "OK", f"Vinted: {len(results)} rezultate pentru '{keyword}'")
    return results


def search_vinted(
    keyword: str,
    max_price: float,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    exclude_description_words: Optional[list] = None,
    page: int = 1,
    subcategory: Optional[str] = None,
    db=None,
    marketplace_config=None,
) -> list[dict]:
    """Cauta pe Vinted prin libraria vinted-scraper (DataDome gestionat automat).

    `category` ("Tab > Categorie") + `subcategory` sunt rezolvate la un `catalog_id`
    Vinted cu precedența config > db > map (RP-2) și trimise ca filtru server-side.
    Daca rezolvarea reuseste, filtrarea pe subcategorie o face Vinted; altfel se aplica
    local pe titlu/descriere (fallback fara regresie). `db`/`marketplace_config` sunt
    optionale (compat: fara ele = doar harta hardcodata, exact ca inainte).
    """
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []

    # Rezolvam catalog_id-ul O SINGURA DATA (config > db > map). Daca e non-None,
    # Vinted filtreaza server-side -> NU mai aplicam filtrul local pe text.
    catalog_id = _resolve_vinted_catalog_id(category, subcategory, db=db, marketplace_config=marketplace_config)
    _local_sub = None if catalog_id is not None else subcategory

    results = _search_vinted_library(
        keyword_clean, max_price, min_price, category,
        exclude_words or [], exclude_description_words or [],
        subcategory=subcategory, page=page, catalog_id=catalog_id,
    )
    return _apply_subcategory_filter(results, _local_sub)


def _balanced_json(s: str, start: int) -> Optional[str]:
    """Returneaza sub-stringul `{...}` echilibrat care incepe la `start` (s[start]='{'),
    respectand string-urile si escape-urile. None daca nu se inchide."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None


def _plugin_data(rsc: str, name: str) -> Optional[dict]:
    """Extrage obiectul `data` al pluginului `name` din RSC-ul decodat. Blocurile au
    forma {"name":"<name>","type":"<name>","section":...,"data":{...}} — folosim si
    `type` ca ancora ca sa nu prindem aparitii intamplatoare ale numelui (S1)."""
    marker = f'"name":"{name}","type":"{name}"'
    idx = rsc.find(marker)
    if idx < 0:
        return None
    d = rsc.find('"data":', idx)
    if d < 0:
        return None
    brace = rsc.find("{", d)
    if brace < 0:
        return None
    raw = _balanced_json(rsc, brace)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_item_rsc(rsc: str) -> dict:
    """Extrage din RSC-ul decodat (React Flight) datele item-ului. Functie PURA —
    testabila pe fixture, fara retea. Returneaza seller_name/seller_reviews/
    seller_rating (feedback_reputation×5, scara 0-5)/seller_badges, atributele (perechi
    RO titlu->valoare), galeria de poze si descrierea (pluginul description)."""
    out = {
        "seller_name": None, "seller_reviews": None, "seller_rating": None,
        "seller_badges": [], "attributes": {}, "images": [], "description": None,
    }
    uih = _plugin_data(rsc, "user_info_header") or {}
    if uih:
        out["seller_name"] = uih.get("name")
        fc = uih.get("feedback_count")
        if isinstance(fc, (int, float)):
            out["seller_reviews"] = int(fc)
        fr = uih.get("feedback_reputation")
        if isinstance(fr, (int, float)):
            out["seller_rating"] = round(float(fr) * 5, 2)

    sbi = _plugin_data(rsc, "seller_badges_info") or {}
    for b in (sbi.get("badges") or []):
        t = b.get("type") if isinstance(b, dict) else None
        if t:
            out["seller_badges"].append(t)
    if not out["seller_name"] and sbi.get("username"):
        out["seller_name"] = sbi.get("username")

    ap = _plugin_data(rsc, "attributes") or {}
    for a in (ap.get("attributes") or []):
        data = a.get("data") if isinstance(a, dict) else None
        if isinstance(data, dict) and data.get("title"):
            out["attributes"][str(data.get("title"))] = data.get("value")

    g = _plugin_data(rsc, "gallery") or {}
    for ph in (g.get("photos") or []):
        if isinstance(ph, dict):
            u = ph.get("full_size_url") or ph.get("url")
            if u:
                out["images"].append(u)

    dp = _plugin_data(rsc, "description") or {}
    if dp.get("description"):
        out["description"] = str(dp["description"]).strip() or None
    return out


def get_vinted_item_detail(item_id: str) -> Optional[dict]:
    """Detaliul complet al unui articol Vinted, prin PAGINA HTML (nu API-ul de detaliu,
    care da 403 — dovedit RP-DIAG). Extrage:
      - ld+json: descriere (garantat), culoare, brand, stare;
      - RSC decodat: feedback_count/reputation (user_info_header), badge-uri
        (seller_badges_info), atribute item (attributes), galerie (gallery);
      - listed_at: min al timestamp-urilor din URL-urile pozelor.
    Contract de retur compatibil (images/description/listed_at) + chei noi
    (attributes/seller_reviews/seller_rating/seller_badges/seller_name). None la esec.
    """
    try:
        page = vinted_html.fetch_item_page(item_id)
        if not page:
            return None
        # RAD-1 — 404 curat: itemul nu mai exista pe Vinted. Propagam marcajul
        # inainte de orice parsare; apelantul il trece pe status removed.
        if isinstance(page, dict) and page.get("gone"):
            return {"_gone": True}
        html = page.get("html") or ""
        rsc = page.get("decoded") or ""

        # ── ld+json (Product) — sursa garantata pentru descriere/culoare/brand ──
        ld = {}
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                ld = json.loads(m.group(1))
            except Exception:
                ld = {}

        # ── extractie pura din RSC (seller/atribute/poze/descriere) ──
        ext = _extract_item_rsc(rsc)
        seller_name = ext["seller_name"]
        seller_reviews = ext["seller_reviews"]
        seller_rating = ext["seller_rating"]
        seller_badges = ext["seller_badges"]
        attributes = dict(ext["attributes"])

        # ── galerie: din RSC, fallback pe imaginea ld+json ──
        images = list(ext["images"])
        if not images and ld.get("image"):
            img = ld.get("image")
            images = [img] if isinstance(img, str) else (img if isinstance(img, list) else [])

        # ── descriere: ld+json garantat, altfel pluginul description din RSC ──
        description = None
        if ld.get("description"):
            description = str(ld["description"]).strip() or None
        if not description and ext["description"]:
            description = ext["description"]

        # ── completeaza atributele din ld+json daca lipsesc ──
        if ld.get("color") and "Culoare" not in attributes:
            attributes["Culoare"] = ld["color"]
        brand = ld.get("brand")
        if isinstance(brand, dict) and brand.get("name") and "Brand" not in attributes:
            attributes["Brand"] = brand["name"]

        # ── listed_at: cel mai vechi timestamp din URL-urile pozelor ──
        listed_at = None
        ts_list = [int(x) for x in re.findall(r"/(\d{10})\.webp", html)]
        if ts_list:
            try:
                listed_at = datetime.fromtimestamp(min(ts_list))
            except (ValueError, OSError):
                listed_at = None

        return {
            "images": images,
            "description": description,
            "listed_at": listed_at,
            "attributes": attributes or None,
            "seller_name": seller_name,
            "seller_reviews": seller_reviews,
            "seller_rating": seller_rating,
            "seller_badges": seller_badges or None,
        }
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Vinted item detail HTML eșuat ({item_id}): {str(exc)[:100]}")
        return None


def apply_vinted_detail(row, detail: dict, resale_price=None) -> None:
    """Aplica rezultatul get_vinted_item_detail pe un RadarListing (FARA commit) si
    recalculeaza seller_risk. Folosit atat de scanner (enrichment in fundal) cat si
    de router (on-demand) ca sa nu duplicam maparea. Marcheaza vinted_detail_fetched=True.
    """
    from app.services.radar.scorer import compute_seller_risk

    if detail.get("images"):
        row.images = json.dumps(detail["images"], ensure_ascii=False)
    if detail.get("description"):
        row.description = detail["description"]
    if detail.get("listed_at"):
        row.listed_at = detail["listed_at"]
    if detail.get("seller_name") and not row.seller_name:
        row.seller_name = detail["seller_name"]
    if detail.get("seller_reviews") is not None:
        row.seller_reviews = detail["seller_reviews"]
    if detail.get("seller_rating") is not None:
        row.seller_rating = detail["seller_rating"]

    try:
        extra = json.loads(row.attributes_json) if row.attributes_json else {}
    except Exception:
        extra = {}
    if detail.get("attributes"):
        extra["attributes"] = detail["attributes"]
    if detail.get("seller_badges"):
        extra["seller_badges"] = detail["seller_badges"]

    risk, reason = compute_seller_risk(
        "vinted", row.price, resale_price, row.seller_name,
        row.seller_reviews, row.seller_rating, extra,
    )
    row.seller_risk = risk
    if reason:
        extra["risk_reason"] = reason
    else:
        extra.pop("risk_reason", None)
    row.attributes_json = json.dumps(extra, ensure_ascii=False) if extra else None
    row.vinted_detail_fetched = True
