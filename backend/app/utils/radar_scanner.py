"""Orchestratorul Radar Marketplace.

Ruleaza ca job APScheduler la fiecare 5 minute. Pentru fiecare user activ:
- itereaza keyword-urile active si poll-uieste platformele activate
- filtreaza listingurile deja vazute si vanzatorii blocati
- calculeaza scor + marja, sare peste cele filtrate
- salveaza listing-ul, ruleaza AI review (Groq), trimite alerte Discord + email + in-app

Scraperele ruleaza SECVENTIAL ca sa nu fie blocate de WAF-uri ca trafic abuziv.
La fiecare 10 cicluri se ruleaza cleanup-ul (mark sold/removed).
"""
import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.radar_keyword import RadarKeyword
from app.models.radar_listing import RadarListing
from app.models.radar_seen_id import RadarSeenId
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services.email_service import is_configured as smtp_configured, send_email
from app.services.push_service import is_push_configured, notify_user_push
from app.services.radar.cleanup_service import cleanup_sold_listings
from app.services.radar import health_watchdog
from app.services.discord_service import send_radar_notification
from app.services.log_manager import log_manager, set_log_user
from app.services.ml.feed_ml_bridge import try_save_to_ml
from app.services.radar.autovit_scraper import search_autovit
from app.services.radar.facebook_scraper import search_facebook
from app.services.radar.lajumate_scraper import search_lajumate
from app.services.radar.mobilede_scraper import search_mobilede
from app.services.radar.okazii_scraper import search_okazii
from app.services.radar.olx_scraper import search_olx, fetch_olx_offer_details
from app.services.radar.publi24_scraper import search_publi24
from app.services.radar.scorer import calculate_score, compute_seller_risk
from app.services.radar.exclusion_engine import check_exclusion
from app.services.radar.vinted_scraper import search_vinted, get_vinted_item_detail, apply_vinted_detail
from app.services.radar.vinted_html import guard_status as vinted_guard_status


# Contor global pentru frecventa cleanup-ului (ruleaza la fiecare 10 cicluri).
_cycle_counter = {"n": 0}

# RP-1 — plafoane de enrichment per CICLU de scan (resetate in run_radar_scan).
# OLX: inline inainte de save+notify (badge risc + descriere in notificare).
# Vinted: in fundal DUPA save+notify (pagina HTML, limiter >=6s per item).
_ENRICH_OLX_CAP = 15
_ENRICH_OLX_BACKLOG_CAP = 5
_ENRICH_VINTED_CAP = 8   # RP-1.1 — redus de la 15 (cadenta mai lenta contra blocarii DataDome)
_enrich_counters = {"olx": 0, "olx_backlog": 0, "vinted": 0}

# Delay intre scraping-urile platformelor pentru a evita blocaje.
_PLATFORM_DELAY_RANGE = (1.5, 3.5)

# MODULE 2 — delay (secunde) intre paginile aceleiasi platforme la paginare.
# MODIFICARE 6 — interval (min, max) per platforma; delay-ul real e aleator in
# interval ca sa nu existe un pattern temporal fix care sa fie detectat ca bot.
_PLATFORM_DELAY_RANGES: dict[str, tuple[float, float]] = {
    "olx":       (0.3, 0.9),
    "vinted":    (0.8, 1.6),
    "publi24":   (0.3, 0.8),
    "okazii":    (0.7, 1.5),
    "lajumate":  (0.7, 1.5),
    "facebook":  (1.5, 3.5),
    "autovit":   (0.5, 1.3),
    "mobilede":  (0.8, 1.8),
}


def _get_platform_delay(platform: str) -> float:
    """Returnează un delay aleator în intervalul platformei.
    Previne detectarea ca bot prin pattern temporal fix.
    """
    lo, hi = _PLATFORM_DELAY_RANGES.get((platform or "").lower(), (0.5, 1.5))
    return random.uniform(lo, hi)


# Seturi globale partajate cu router-ul: cand userul dezactiveaza/sterge un
# keyword in timp ce scanul ruleaza, marcam id-ul aici si bucla principala
# verifica la fiecare iteratie ca sa iasa imediat.
_cancelled_keyword_ids: set[int] = set()
_deleted_keyword_ids: set[int] = set()


def cancel_keyword_scan(keyword_id: int) -> None:
    _cancelled_keyword_ids.add(int(keyword_id))


def restore_keyword_scan(keyword_id: int) -> None:
    _cancelled_keyword_ids.discard(int(keyword_id))


def mark_keyword_deleted(keyword_id: int) -> None:
    _deleted_keyword_ids.add(int(keyword_id))


def _is_keyword_cancelled(keyword_id: int) -> bool:
    return keyword_id in _cancelled_keyword_ids or keyword_id in _deleted_keyword_ids


def _keyword_subcategory(keyword) -> Optional[str]:
    """MODIFICARE 4 — subcategoria e stocata in marketplace_config (JSON), nu intr-o
    coloana dedicata. O extragem pentru filtrarea post-scrape (ex. Vinted)."""
    raw = getattr(keyword, "marketplace_config", None)
    if not raw:
        return None
    try:
        cfg = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(cfg, dict):
            sub = cfg.get("subcategory")
            return sub.strip() if isinstance(sub, str) and sub.strip() else None
    except Exception:
        pass
    return None


def _keyword_marketplace_config(keyword) -> Optional[dict]:
    """marketplace_config parsat ca dict (RP-2: pentru vinted_catalog_id în resolver)."""
    raw = getattr(keyword, "marketplace_config", None)
    if not raw:
        return None
    try:
        cfg = json.loads(raw) if isinstance(raw, str) else raw
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None


# Categorie OLX (ID numeric din __PRERENDERED_STATE__, atasat ca listing["olx_category"])
# -> subcategoria din interfata FlipRadar.
# Generat automat — map_olx_categories.py — 2026-07-02
# Acoperire: 84/84 subcategorii FlipRadar · 1381 ID-uri OLX
OLX_CATEGORY_ID_TO_SUBCATEGORY = {
    "101": "Telefoane",
    "163": "Gradina",
    "231": "Jocuri - Jucarii",
    "235": "Alte produse copii",
    "282": "Electrocasnice",
    "431": "Arta - Obiecte de colectie",
    "461": "Biciclete - Fitness - Suplimente",
    "516": "La plimbare",
    "626": "Accesorii",
    "751": "Alimentatie - Ingrijire",
    "763": "Alte animale de companie",
    "883": "Haine - Incaltaminte copii si gravide",
    "885": "Camera copilului",
    "903": "Carti - Muzica - Filme",
    "916": "Tablete - eReadere",
    "930": "Electrocasnice",
    "942": "Telefoane",
    "944": "Telefoane",
    "946": "Telefoane",
    "948": "Telefoane",
    "950": "Telefoane",
    "952": "Telefoane",
    "956": "Telefoane",
    "958": "Telefoane",
    "979": "Electrocasnice",
    "987": "Biciclete - Fitness - Suplimente",
    "989": "Biciclete - Fitness - Suplimente",
    "991": "Carti - Muzica - Filme",
    "993": "Carti - Muzica - Filme",
    "995": "Carti - Muzica - Filme",
    "997": "Carti - Muzica - Filme",
    "1017": "Haine - Incaltaminte copii si gravide",
    "1019": "Haine - Incaltaminte copii si gravide",
    "1021": "La plimbare",
    "1023": "La plimbare",
    "1025": "Camera copilului",
    "1027": "Camera copilului",
    "1029": "Gradina",
    "1031": "Gradina",
    "1033": "Gradina",
    "1081": "Haine dama",
    "1083": "Haine barbati",
    "1085": "Incaltaminte dama",
    "1087": "Incaltaminte barbati",
    "1097": "Haine dama",
    "1133": "Incaltaminte dama",
    "1143": "Incaltaminte barbati",
    "1145": "Incaltaminte barbati",
    "1147": "Incaltaminte barbati",
    "1185": "Utilaje agricole si industriale",
    "1187": "Animale domestice si pasari",
    "1189": "Cereale - plante - pomi",
    "1191": "Produse piata - alimentatie",
    "1197": "Utilaje agricole si industriale",
    "1199": "Utilaje agricole si industriale",
    "1201": "Animale domestice si pasari",
    "1203": "Animale domestice si pasari",
    "1205": "Animale domestice si pasari",
    "1207": "Animale domestice si pasari",
    "1211": "Animale domestice si pasari",
    "1213": "Animale domestice si pasari",
    "1215": "Animale domestice si pasari",
    "1217": "Cereale - plante - pomi",
    "1219": "Cereale - plante - pomi",
    "1221": "Cereale - plante - pomi",
    "1223": "Produse piata - alimentatie",
    "1225": "Produse piata - alimentatie",
    "1227": "Produse piata - alimentatie",
    "1229": "Produse piata - alimentatie",
    "1233": "Produse piata - alimentatie",
    "1237": "Articole menaj",
    "1261": "Telefoane",
    "1263": "Biciclete - Fitness - Suplimente",
    "1275": "La plimbare",
    "1277": "Camera copilului",
    "1279": "Alimentatie - Ingrijire",
    "1281": "Alimentatie - Ingrijire",
    "1283": "Alimentatie - Ingrijire",
    "1285": "Haine - Incaltaminte copii si gravide",
    "1287": "Articole scolare - papetarie",
    "1293": "Utilaje agricole si industriale",
    "1341": "Telefoane",
    "1343": "Telefoane",
    "1345": "Telefoane",
    "1347": "Telefoane",
    "1349": "Telefoane",
    "1351": "Tablete - eReadere",
    "1353": "Tablete - eReadere",
    "1355": "Tablete - eReadere",
    "1357": "Tablete - eReadere",
    "1359": "Tablete - eReadere",
    "1376": "Gradina",
    "1377": "Gradina",
    "1379": "Gradina",
    "1380": "Gradina",
    "1530": "Telefoane",
    "1531": "Telefoane",
    "1532": "Telefoane",
    "1533": "Telefoane",
    "1534": "Telefoane",
    "1542": "Tablete - eReadere",
    "1543": "Tablete - eReadere",
    "1544": "Tablete - eReadere",
    "1545": "Tablete - eReadere",
    "1546": "Tablete - eReadere",
    "1556": "Telefoane",
    "1565": "Camping",
    "1569": "Fotbal",
    "1575": "Pescuit",
    "1576": "Sporturi de apa",
    "1577": "Sporturi de iarna",
    "1578": "Tenis",
    "1581": "Trotinete, role, skateboard",
    "1582": "Vanatoare",
    "1584": "Biciclete - Fitness - Suplimente",
    "1585": "Biciclete - Fitness - Suplimente",
    "1586": "Biciclete - Fitness - Suplimente",
    "1587": "Biciclete - Fitness - Suplimente",
    "1588": "Biciclete - Fitness - Suplimente",
    "1593": "Camping",
    "1594": "Camping",
    "1595": "Camping",
    "1596": "Camping",
    "1597": "Camping",
    "1605": "Fotbal",
    "1606": "Fotbal",
    "1607": "Pescuit",
    "1608": "Pescuit",
    "1609": "Pescuit",
    "1610": "Pescuit",
    "1611": "Pescuit",
    "1612": "Sporturi de apa",
    "1613": "Sporturi de apa",
    "1614": "Sporturi de apa",
    "1615": "Sporturi de apa",
    "1616": "Sporturi de apa",
    "1617": "Sporturi de iarna",
    "1618": "Sporturi de iarna",
    "1619": "Sporturi de iarna",
    "1620": "Sporturi de iarna",
    "1621": "Sporturi de iarna",
    "1622": "Sporturi de iarna",
    "1623": "Sporturi de iarna",
    "1624": "Tenis",
    "1625": "Tenis",
    "1626": "Tenis",
    "1627": "Tenis",
    "1628": "Tenis",
    "1629": "Trotinete, role, skateboard",
    "1630": "Trotinete, role, skateboard",
    "1631": "Trotinete, role, skateboard",
    "1632": "Trotinete, role, skateboard",
    "1633": "Trotinete, role, skateboard",
    "1634": "Trotinete, role, skateboard",
    "1635": "Adoptii",
    "1640": "Roti - Jante - Anvelope",
    "1641": "Consumabile - accesorii",
    "1642": "Caroserie - Interior",
    "1643": "Mecanica - electrica",
    "1644": "Alte piese",
    "1645": "Alte Vehicule",
    "1646": "Vehicule pentru dezmembrare",
    "1647": "Roti - Jante - Anvelope",
    "1648": "Roti - Jante - Anvelope",
    "1649": "Roti - Jante - Anvelope",
    "1650": "Consumabile - accesorii",
    "1651": "Consumabile - accesorii",
    "1652": "Caroserie - Interior",
    "1653": "Caroserie - Interior",
    "1654": "Mecanica - electrica",
    "1655": "Mecanica - electrica",
    "1656": "Mecanica - electrica",
    "1657": "Mecanica - electrica",
    "1658": "Mecanica - electrica",
    "1659": "Mecanica - electrica",
    "1660": "Alte piese",
    "1661": "Alte piese",
    "1662": "Alte Vehicule",
    "1663": "Alte Vehicule",
    "1664": "Alte Vehicule",
    "1665": "Alte Vehicule",
    "1666": "Alte Vehicule",
    "1667": "Ceasuri",
    "1671": "Videoproiectoare & Accesorii",
    "1672": "Videoproiectoare & Accesorii",
    "1673": "Videoproiectoare & Accesorii",
    "1674": "Videoproiectoare & Accesorii",
    "1675": "Videoproiectoare & Accesorii",
    "1676": "Ceasuri",
    "1677": "Ceasuri",
    "1678": "Ceasuri",
    "1679": "Ceasuri",
    "1680": "TV",
    "1681": "TV",
    "1682": "TV",
    "1692": "Haine dama",
    "1693": "Haine dama",
    "1694": "Haine dama",
    "1695": "Haine dama",
    "1696": "Haine dama",
    "1697": "Haine dama",
    "1698": "Haine dama",
    "1699": "Haine dama",
    "1700": "Haine dama",
    "1701": "Haine dama",
    "1702": "Haine dama",
    "1703": "Haine dama",
    "1704": "Haine dama",
    "1705": "Telefoane",
    "1706": "Telefoane",
    "1707": "Telefoane",
    "1708": "Telefoane",
    "1709": "Telefoane",
    "1710": "Tablete - eReadere",
    "1711": "Haine dama",
    "1712": "Haine dama",
    "1713": "Haine dama",
    "1714": "Haine dama",
    "1715": "Haine dama",
    "1716": "Haine dama",
    "1717": "Haine dama",
    "1718": "Haine dama",
    "1719": "Haine dama",
    "1720": "Haine dama",
    "1721": "Haine dama",
    "1722": "Haine dama",
    "1723": "Haine dama",
    "1724": "Haine dama",
    "1725": "Haine dama",
    "1726": "Haine dama",
    "1727": "Haine dama",
    "1728": "Haine dama",
    "1729": "Haine dama",
    "1730": "Haine dama",
    "1731": "Haine dama",
    "1732": "Haine dama",
    "1733": "Haine dama",
    "1734": "Haine dama",
    "1735": "Haine dama",
    "1736": "Haine dama",
    "1737": "Haine dama",
    "1738": "Haine dama",
    "1739": "Haine dama",
    "1740": "Haine dama",
    "1741": "Haine dama",
    "1742": "Haine dama",
    "1743": "Haine dama",
    "1744": "Haine dama",
    "1745": "Haine dama",
    "1747": "Haine dama",
    "1748": "Haine dama",
    "1749": "Haine dama",
    "1750": "Haine dama",
    "1751": "Haine dama",
    "1752": "Haine dama",
    "1753": "Haine dama",
    "1754": "Haine dama",
    "1756": "Haine dama",
    "1757": "Haine dama",
    "1758": "Haine dama",
    "1760": "Haine dama",
    "1761": "Haine dama",
    "1762": "Haine dama",
    "1764": "Haine dama",
    "1765": "Haine dama",
    "1767": "Haine dama",
    "1768": "Retelistica & Servere",
    "1769": "Retelistica & Servere",
    "1770": "Retelistica & Servere",
    "1771": "Retelistica & Servere",
    "1772": "Retelistica & Servere",
    "1773": "Retelistica & Servere",
    "1774": "Retelistica & Servere",
    "1775": "Retelistica & Servere",
    "1776": "Retelistica & Servere",
    "1777": "Retelistica & Servere",
    "1778": "Retelistica & Servere",
    "1779": "Retelistica & Servere",
    "1780": "Retelistica & Servere",
    "1781": "Retelistica & Servere",
    "1782": "Haine dama",
    "1783": "Lenjerie si costume de baie dama",
    "1784": "Haine pentru gravide",
    "1785": "Lenjerie si costume de baie dama",
    "1786": "Haine pentru gravide",
    "1787": "Lenjerie si costume de baie dama",
    "1788": "Haine pentru gravide",
    "1789": "Lenjerie si costume de baie dama",
    "1790": "Haine pentru gravide",
    "1791": "Lenjerie si costume de baie dama",
    "1792": "Haine pentru gravide",
    "1793": "Lenjerie si costume de baie dama",
    "1794": "Haine pentru gravide",
    "1795": "Lenjerie si costume de baie dama",
    "1796": "Haine pentru gravide",
    "1797": "Lenjerie si costume de baie dama",
    "1798": "Haine pentru gravide",
    "1799": "Lenjerie si costume de baie dama",
    "1800": "Haine pentru gravide",
    "1801": "Lenjerie si costume de baie dama",
    "1802": "Haine pentru gravide",
    "1803": "Lenjerie si costume de baie dama",
    "1804": "Haine pentru gravide",
    "1805": "Lenjerie si costume de baie dama",
    "1806": "Haine pentru gravide",
    "1807": "Lenjerie si costume de baie dama",
    "1808": "Haine pentru gravide",
    "1809": "Lenjerie si costume de baie dama",
    "1810": "Haine pentru gravide",
    "1811": "Piese telefoane & tablete",
    "1812": "Piese telefoane & tablete",
    "1813": "Piese telefoane & tablete",
    "1814": "Piese telefoane & tablete",
    "1815": "Piese telefoane & tablete",
    "1816": "Piese telefoane & tablete",
    "1817": "Piese telefoane & tablete",
    "1818": "Piese telefoane & tablete",
    "1819": "Piese telefoane & tablete",
    "1820": "Piese telefoane & tablete",
    "1821": "Lenjerie si costume de inot barbati",
    "1822": "Lenjerie si costume de inot barbati",
    "1823": "Lenjerie si costume de inot barbati",
    "1824": "Lenjerie si costume de inot barbati",
    "1825": "Lenjerie si costume de inot barbati",
    "1826": "Incaltaminte barbati",
    "1827": "Incaltaminte dama",
    "1828": "Haine barbati",
    "1829": "Incaltaminte barbati",
    "1830": "Incaltaminte dama",
    "1831": "Haine barbati",
    "1832": "Incaltaminte barbati",
    "1833": "Incaltaminte dama",
    "1834": "Haine barbati",
    "1835": "Incaltaminte barbati",
    "1836": "Incaltaminte dama",
    "1837": "Haine barbati",
    "1838": "Incaltaminte barbati",
    "1839": "Incaltaminte dama",
    "1840": "Haine barbati",
    "1841": "Incaltaminte barbati",
    "1842": "Incaltaminte dama",
    "1843": "Haine barbati",
    "1844": "Incaltaminte dama",
    "1845": "Haine barbati",
    "1846": "Incaltaminte dama",
    "1847": "Haine barbati",
    "1848": "Incaltaminte dama",
    "1849": "Haine barbati",
    "1850": "Haine barbati",
    "1851": "Haine barbati",
    "1852": "Haine barbati",
    "1853": "Periferice & Accesorii Laptop-PC-Gaming",
    "1854": "Periferice & Accesorii Laptop-PC-Gaming",
    "1855": "Periferice & Accesorii Laptop-PC-Gaming",
    "1856": "Periferice & Accesorii Laptop-PC-Gaming",
    "1857": "Periferice & Accesorii Laptop-PC-Gaming",
    "1858": "Periferice & Accesorii Laptop-PC-Gaming",
    "1859": "Periferice & Accesorii Laptop-PC-Gaming",
    "1860": "Periferice & Accesorii Laptop-PC-Gaming",
    "1861": "Periferice & Accesorii Laptop-PC-Gaming",
    "1862": "Periferice & Accesorii Laptop-PC-Gaming",
    "1863": "Periferice & Accesorii Laptop-PC-Gaming",
    "1864": "Periferice & Accesorii Laptop-PC-Gaming",
    "1865": "Periferice & Accesorii Laptop-PC-Gaming",
    "1866": "Periferice & Accesorii Laptop-PC-Gaming",
    "1867": "Periferice & Accesorii Laptop-PC-Gaming",
    "1868": "Periferice & Accesorii Laptop-PC-Gaming",
    "1869": "Periferice & Accesorii Laptop-PC-Gaming",
    "1870": "Laptop-Calculator-Gaming",
    "1871": "Ingrijire Personala",
    "1872": "Laptop-Calculator-Gaming",
    "1873": "Ingrijire Personala",
    "1874": "Laptop-Calculator-Gaming",
    "1875": "Ingrijire Personala",
    "1876": "Laptop-Calculator-Gaming",
    "1877": "Ingrijire Personala",
    "1878": "Laptop-Calculator-Gaming",
    "1879": "Ingrijire Personala",
    "1880": "Laptop-Calculator-Gaming",
    "1881": "Ingrijire Personala",
    "1882": "Laptop-Calculator-Gaming",
    "1883": "Ingrijire Personala",
    "1884": "Laptop-Calculator-Gaming",
    "1885": "Ingrijire Personala",
    "1886": "Laptop-Calculator-Gaming",
    "1887": "Ingrijire Personala",
    "1888": "Laptop-Calculator-Gaming",
    "1889": "Ingrijire Personala",
    "1890": "Laptop-Calculator-Gaming",
    "1891": "Ingrijire Personala",
    "1892": "Ingrijire Personala",
    "1893": "Ingrijire Personala",
    "1894": "Palarii, sepci si bandane",
    "1895": "Haine pentru nunta",
    "1896": "Palarii, sepci si bandane",
    "1897": "Haine pentru nunta",
    "1898": "Palarii, sepci si bandane",
    "1899": "Haine pentru nunta",
    "1900": "Palarii, sepci si bandane",
    "1901": "Haine pentru nunta",
    "1902": "Palarii, sepci si bandane",
    "1903": "Haine pentru nunta",
    "1904": "Palarii, sepci si bandane",
    "1905": "Haine pentru nunta",
    "1906": "Palarii, sepci si bandane",
    "1907": "Haine pentru nunta",
    "1908": "Palarii, sepci si bandane",
    "1909": "Haine pentru nunta",
    "1910": "Palarii, sepci si bandane",
    "1911": "Accesorii",
    "1912": "Accesorii",
    "1913": "Accesorii",
    "1914": "Accesorii",
    "1915": "Accesorii",
    "1916": "Accesorii",
    "1917": "Accesorii",
    "1918": "Accesorii",
    "1919": "Accesorii",
    "1920": "Accesorii",
    "1921": "Imprimante, scannere",
    "1922": "Home Cinema & Audio",
    "1923": "Gadgets, Wearables & Camere foto-video",
    "1924": "Imprimante, scannere",
    "1925": "Home Cinema & Audio",
    "1926": "Gadgets, Wearables & Camere foto-video",
    "1927": "Imprimante, scannere",
    "1928": "Home Cinema & Audio",
    "1929": "Gadgets, Wearables & Camere foto-video",
    "1930": "Imprimante, scannere",
    "1931": "Home Cinema & Audio",
    "1932": "Gadgets, Wearables & Camere foto-video",
    "1933": "Imprimante, scannere",
    "1934": "Home Cinema & Audio",
    "1935": "Gadgets, Wearables & Camere foto-video",
    "1936": "Imprimante, scannere",
    "1937": "Home Cinema & Audio",
    "1938": "Gadgets, Wearables & Camere foto-video",
    "1939": "Home Cinema & Audio",
    "1940": "Gadgets, Wearables & Camere foto-video",
    "1941": "Gadgets, Wearables & Camere foto-video",
    "1942": "Gadgets, Wearables & Camere foto-video",
    "1943": "Gadgets, Wearables & Camere foto-video",
    "1944": "Gadgets, Wearables & Camere foto-video",
    "1945": "Gadgets, Wearables & Camere foto-video",
    "1946": "Gadgets, Wearables & Camere foto-video",
    "1947": "Gadgets, Wearables & Camere foto-video",
    "1948": "Gadgets, Wearables & Camere foto-video",
    "1949": "Sanatate si frumusete",
    "1950": "Alte accesorii de moda si frumusete",
    "1951": "Sanatate si frumusete",
    "1952": "Sanatate si frumusete",
    "1953": "Sanatate si frumusete",
    "1954": "Sanatate si frumusete",
    "1955": "Sanatate si frumusete",
    "1956": "Sanatate si frumusete",
    "1957": "Sanatate si frumusete",
    "1958": "Sanatate si frumusete",
    "1959": "Sanatate si frumusete",
    "1960": "Sanatate si frumusete",
    "1961": "Sanatate si frumusete",
    "1963": "Sanatate si frumusete",
    "1964": "Sanatate si frumusete",
    "1965": "Sanatate si frumusete",
    "1966": "Sanatate si frumusete",
    "1967": "Sanatate si frumusete",
    "1968": "Sanatate si frumusete",
    "1969": "Sanatate si frumusete",
    "1970": "Sanatate si frumusete",
    "1971": "Sanatate si frumusete",
    "1972": "Sanatate si frumusete",
    "1973": "Sanatate si frumusete",
    "1974": "Sanatate si frumusete",
    "1975": "Sanatate si frumusete",
    "1976": "Haine dama",
    "1977": "Haine dama",
    "1978": "Incaltaminte dama",
    "1979": "Incaltaminte dama",
    "1980": "Incaltaminte dama",
    "1981": "Haine dama",
    "1982": "Haine dama",
    "1983": "Incaltaminte dama",
    "1984": "Incaltaminte dama",
    "1985": "Incaltaminte dama",
    "1986": "Haine dama",
    "1987": "Haine dama",
    "1988": "Incaltaminte dama",
    "1989": "Incaltaminte dama",
    "1990": "Incaltaminte dama",
    "1991": "Haine dama",
    "1992": "Incaltaminte dama",
    "1993": "Incaltaminte dama",
    "1994": "Haine dama",
    "1995": "Incaltaminte dama",
    "1996": "Incaltaminte dama",
    "1997": "Haine dama",
    "1998": "Incaltaminte dama",
    "1999": "Haine dama",
    "2000": "Incaltaminte dama",
    "2001": "Haine dama",
    "2002": "Incaltaminte dama",
    "2003": "Haine dama",
    "2004": "Haine dama",
    "2005": "Haine dama",
    "2006": "Haine dama",
    "2007": "Haine dama",
    "2008": "Incaltaminte dama",
    "2009": "Incaltaminte dama",
    "2010": "Incaltaminte dama",
    "2011": "Haine barbati",
    "2012": "Haine barbati",
    "2013": "Haine barbati",
    "2014": "Haine barbati",
    "2015": "Haine barbati",
    "2016": "Haine barbati",
    "2017": "Haine barbati",
    "2018": "Haine barbati",
    "2019": "Haine barbati",
    "2020": "Haine barbati",
    "2021": "Incaltaminte dama",
    "2022": "Incaltaminte dama",
    "2023": "Incaltaminte dama",
    "2024": "Haine barbati",
    "2025": "Haine barbati",
    "2026": "Haine barbati",
    "2027": "Haine barbati",
    "2028": "Haine barbati",
    "2029": "Haine barbati",
    "2030": "Haine barbati",
    "2031": "Haine barbati",
    "2032": "Haine barbati",
    "2033": "Haine barbati",
    "2034": "Incaltaminte dama",
    "2035": "Incaltaminte dama",
    "2036": "Incaltaminte dama",
    "2037": "Haine barbati",
    "2038": "Haine barbati",
    "2039": "Haine barbati",
    "2040": "Haine barbati",
    "2041": "Haine barbati",
    "2042": "Haine barbati",
    "2043": "Haine barbati",
    "2044": "Haine barbati",
    "2045": "Haine barbati",
    "2046": "Haine barbati",
    "2047": "Incaltaminte dama",
    "2048": "Incaltaminte dama",
    "2049": "Haine barbati",
    "2050": "Haine barbati",
    "2051": "Haine barbati",
    "2052": "Haine barbati",
    "2053": "Haine barbati",
    "2054": "Haine barbati",
    "2055": "Haine barbati",
    "2056": "Haine barbati",
    "2057": "Incaltaminte dama",
    "2058": "Haine barbati",
    "2059": "Haine barbati",
    "2060": "Haine barbati",
    "2061": "Haine barbati",
    "2062": "Haine barbati",
    "2063": "Haine barbati",
    "2064": "Haine barbati",
    "2065": "Incaltaminte dama",
    "2066": "Haine barbati",
    "2067": "Haine barbati",
    "2068": "Haine barbati",
    "2069": "Haine barbati",
    "2070": "Haine barbati",
    "2071": "Haine barbati",
    "2072": "Haine barbati",
    "2073": "Haine barbati",
    "2074": "Haine barbati",
    "2075": "Haine barbati",
    "2076": "Haine barbati",
    "2077": "Haine barbati",
    "2078": "Haine barbati",
    "2079": "Haine barbati",
    "2080": "Haine barbati",
    "2081": "Haine barbati",
    "2082": "Electrocasnice",
    "2083": "Electrocasnice",
    "2084": "Electrocasnice",
    "2085": "Electrocasnice",
    "2086": "Electrocasnice",
    "2087": "Electrocasnice",
    "2088": "Electrocasnice",
    "2089": "Electrocasnice",
    "2090": "Electrocasnice",
    "2091": "Electrocasnice",
    "2092": "Electrocasnice",
    "2093": "Electrocasnice",
    "2094": "Electrocasnice",
    "2095": "Electrocasnice",
    "2096": "Electrocasnice",
    "2097": "Electrocasnice",
    "2098": "Electrocasnice",
    "2099": "Drone & accesorii",
    "2100": "Componente Laptop-PC",
    "2101": "Casti Audio",
    "2102": "Casa inteligenta - Smarthome",
    "2103": "Drone & accesorii",
    "2104": "Componente Laptop-PC",
    "2105": "Casti Audio",
    "2106": "Casa inteligenta - Smarthome",
    "2107": "Drone & accesorii",
    "2108": "Componente Laptop-PC",
    "2109": "Casti Audio",
    "2110": "Casa inteligenta - Smarthome",
    "2111": "Componente Laptop-PC",
    "2112": "Casti Audio",
    "2113": "Casa inteligenta - Smarthome",
    "2114": "Componente Laptop-PC",
    "2115": "Casti Audio",
    "2116": "Casa inteligenta - Smarthome",
    "2117": "Componente Laptop-PC",
    "2118": "Casa inteligenta - Smarthome",
    "2119": "Componente Laptop-PC",
    "2120": "Casa inteligenta - Smarthome",
    "2121": "Componente Laptop-PC",
    "2122": "Componente Laptop-PC",
    "2123": "Componente Laptop-PC",
    "2124": "Componente Laptop-PC",
    "2125": "Componente Laptop-PC",
    "2126": "Componente Laptop-PC",
    "2127": "Componente Laptop-PC",
    "2128": "Componente Laptop-PC",
    "2129": "Componente Laptop-PC",
    "2130": "Componente Laptop-PC",
    "2131": "Componente Laptop-PC",
    "2132": "Componente Laptop-PC",
    "2133": "Incaltaminte barbati",
    "2134": "Incaltaminte barbati",
    "2135": "Incaltaminte barbati",
    "2136": "Incaltaminte barbati",
    "2137": "Incaltaminte barbati",
    "2138": "Incaltaminte barbati",
    "2139": "Palarii, sepci si bandane",
    "2140": "Palarii, sepci si bandane",
    "2141": "Haine pentru nunta",
    "2142": "Haine pentru nunta",
    "2143": "Haine pentru nunta",
    "2144": "Accesorii",
    "2145": "Accesorii",
    "2146": "Accesorii",
    "2147": "Incaltaminte barbati",
    "2148": "Incaltaminte barbati",
    "2149": "Incaltaminte barbati",
    "2150": "Incaltaminte barbati",
    "2151": "Incaltaminte barbati",
    "2152": "Incaltaminte barbati",
    "2153": "Palarii, sepci si bandane",
    "2154": "Palarii, sepci si bandane",
    "2155": "Haine pentru nunta",
    "2156": "Haine pentru nunta",
    "2157": "Haine pentru nunta",
    "2158": "Accesorii",
    "2159": "Accesorii",
    "2160": "Accesorii",
    "2161": "Incaltaminte barbati",
    "2162": "Incaltaminte barbati",
    "2163": "Incaltaminte barbati",
    "2164": "Incaltaminte barbati",
    "2165": "Incaltaminte barbati",
    "2166": "Incaltaminte barbati",
    "2167": "Haine pentru nunta",
    "2168": "Haine pentru nunta",
    "2169": "Haine pentru nunta",
    "2170": "Accesorii",
    "2171": "Accesorii",
    "2172": "Accesorii",
    "2173": "Incaltaminte barbati",
    "2174": "Incaltaminte barbati",
    "2175": "Incaltaminte barbati",
    "2176": "Incaltaminte barbati",
    "2177": "Haine pentru nunta",
    "2178": "Haine pentru nunta",
    "2179": "Haine pentru nunta",
    "2180": "Accesorii",
    "2181": "Accesorii",
    "2182": "Incaltaminte barbati",
    "2183": "Incaltaminte barbati",
    "2184": "Haine pentru nunta",
    "2185": "Haine pentru nunta",
    "2186": "Accesorii",
    "2187": "Accesorii",
    "2188": "Haine pentru nunta",
    "2189": "Haine pentru nunta",
    "2190": "Accesorii",
    "2191": "Accesorii",
    "2192": "Haine pentru nunta",
    "2193": "Haine pentru nunta",
    "2194": "Accesorii",
    "2195": "Accesorii",
    "2196": "Haine pentru nunta",
    "2197": "Haine pentru nunta",
    "2198": "Accesorii",
    "2199": "Haine pentru nunta",
    "2200": "Haine pentru nunta",
    "2201": "Accesorii",
    "2202": "Haine pentru nunta",
    "2203": "Haine pentru nunta",
    "2204": "Accesorii",
    "2205": "Accesorii",
    "2206": "Accesorii",
    "2207": "Audio Hi Fi & Profesionale",
    "2208": "Aparate medicale & Wellness",
    "2209": "Accesorii telefoane & tablete",
    "2210": "Audio Hi Fi & Profesionale",
    "2211": "Aparate medicale & Wellness",
    "2212": "Accesorii telefoane & tablete",
    "2213": "Audio Hi Fi & Profesionale",
    "2214": "Aparate medicale & Wellness",
    "2215": "Accesorii telefoane & tablete",
    "2216": "Audio Hi Fi & Profesionale",
    "2217": "Aparate medicale & Wellness",
    "2218": "Accesorii telefoane & tablete",
    "2219": "Audio Hi Fi & Profesionale",
    "2220": "Aparate medicale & Wellness",
    "2221": "Accesorii telefoane & tablete",
    "2222": "Audio Hi Fi & Profesionale",
    "2223": "Aparate medicale & Wellness",
    "2224": "Accesorii telefoane & tablete",
    "2225": "Audio Hi Fi & Profesionale",
    "2226": "Aparate medicale & Wellness",
    "2227": "Accesorii telefoane & tablete",
    "2228": "Audio Hi Fi & Profesionale",
    "2230": "Accesorii telefoane & tablete",
    "2231": "Audio Hi Fi & Profesionale",
    "2232": "Aparate medicale & Wellness",
    "2233": "Accesorii telefoane & tablete",
    "2234": "Audio Hi Fi & Profesionale",
    "2235": "Accesorii telefoane & tablete",
    "2236": "Audio Hi Fi & Profesionale",
    "2237": "Accesorii telefoane & tablete",
    "2238": "Accesorii telefoane & tablete",
    "2239": "Accesorii telefoane & tablete",
    "2240": "Accesorii telefoane & tablete",
    "2241": "Accesorii telefoane & tablete",
    "2242": "Accesorii telefoane & tablete",
    "2243": "Accesorii telefoane & tablete",
    "2244": "Accesorii telefoane & tablete",
    "2245": "Aparate medicale & Wellness",
    "2246": "Aparate medicale & Wellness",
    "2248": "Accesorii telefoane & tablete",
    "2249": "Accesorii telefoane & tablete",
    "2250": "Aparate medicale & Wellness",
    "2251": "Aparate medicale & Wellness",
    "2253": "Accesorii telefoane & tablete",
    "2254": "Accesorii telefoane & tablete",
    "2255": "Aparate medicale & Wellness",
    "2256": "Aparate medicale & Wellness",
    "2258": "Accesorii telefoane & tablete",
    "2259": "Accesorii telefoane & tablete",
    "2260": "Aparate medicale & Wellness",
    "2262": "Accesorii telefoane & tablete",
    "2263": "Accesorii telefoane & tablete",
    "2264": "Aparate medicale & Wellness",
    "2265": "Accesorii telefoane & tablete",
    "2266": "Aparate medicale & Wellness",
    "2267": "Accesorii telefoane & tablete",
    "2268": "Aparate medicale & Wellness",
    "2269": "Accesorii telefoane & tablete",
    "2270": "Accesorii telefoane & tablete",
    "2271": "Accesorii",
    "2272": "Accesorii",
    "2273": "Accesorii",
    "2274": "Accesorii",
    "2275": "Accesorii",
    "2276": "Accesorii",
    "2277": "Accesorii",
    "2278": "Sanatate si frumusete",
    "2279": "Sanatate si frumusete",
    "2280": "Sanatate si frumusete",
    "2281": "Sanatate si frumusete",
    "2282": "Sanatate si frumusete",
    "2283": "Accesorii",
    "2284": "Accesorii",
    "2285": "Accesorii",
    "2286": "Accesorii",
    "2287": "Accesorii",
    "2288": "Accesorii",
    "2289": "Accesorii",
    "2290": "Sanatate si frumusete",
    "2291": "Sanatate si frumusete",
    "2292": "Sanatate si frumusete",
    "2293": "Sanatate si frumusete",
    "2294": "Sanatate si frumusete",
    "2295": "Accesorii",
    "2296": "Accesorii",
    "2297": "Accesorii",
    "2298": "Accesorii",
    "2299": "Accesorii",
    "2300": "Accesorii",
    "2301": "Sanatate si frumusete",
    "2302": "Sanatate si frumusete",
    "2303": "Sanatate si frumusete",
    "2304": "Sanatate si frumusete",
    "2305": "Sanatate si frumusete",
    "2306": "Accesorii",
    "2307": "Accesorii",
    "2308": "Accesorii",
    "2309": "Accesorii",
    "2310": "Sanatate si frumusete",
    "2311": "Sanatate si frumusete",
    "2312": "Sanatate si frumusete",
    "2313": "Sanatate si frumusete",
    "2314": "Sanatate si frumusete",
    "2315": "Accesorii",
    "2316": "Accesorii",
    "2318": "Sanatate si frumusete",
    "2319": "Sanatate si frumusete",
    "2320": "Sanatate si frumusete",
    "2321": "Sanatate si frumusete",
    "2322": "Accesorii",
    "2323": "Accesorii",
    "2324": "Sanatate si frumusete",
    "2325": "Sanatate si frumusete",
    "2326": "Sanatate si frumusete",
    "2327": "Sanatate si frumusete",
    "2328": "Sanatate si frumusete",
    "2329": "Sanatate si frumusete",
    "2330": "Sanatate si frumusete",
    "2331": "Sanatate si frumusete",
    "2332": "Sanatate si frumusete",
    "2333": "Sanatate si frumusete",
    "2334": "Sanatate si frumusete",
    "2335": "Sanatate si frumusete",
    "2336": "Sanatate si frumusete",
    "2337": "Sanatate si frumusete",
    "2338": "Sanatate si frumusete",
    "2339": "Sanatate si frumusete",
    "2340": "Sanatate si frumusete",
    "2341": "Sanatate si frumusete",
    "2342": "Sanatate si frumusete",
    "2343": "Sanatate si frumusete",
    "2344": "Gadgets, Wearables & Camere foto-video",
    "2345": "Gadgets, Wearables & Camere foto-video",
    "2346": "Gadgets, Wearables & Camere foto-video",
    "2347": "Home Cinema & Audio",
    "2348": "Imprimante, scannere",
    "2349": "Imprimante, scannere",
    "2351": "Imprimante, scannere",
    "2352": "Ingrijire Personala",
    "2353": "Ingrijire Personala",
    "2354": "Ingrijire Personala",
    "2355": "Ingrijire Personala",
    "2356": "Laptop-Calculator-Gaming",
    "2357": "Laptop-Calculator-Gaming",
    "2358": "Laptop-Calculator-Gaming",
    "2359": "Periferice & Accesorii Laptop-PC-Gaming",
    "2360": "Periferice & Accesorii Laptop-PC-Gaming",
    "2361": "Periferice & Accesorii Laptop-PC-Gaming",
    "2362": "Periferice & Accesorii Laptop-PC-Gaming",
    "2363": "Periferice & Accesorii Laptop-PC-Gaming",
    "2364": "Periferice & Accesorii Laptop-PC-Gaming",
    "2365": "Periferice & Accesorii Laptop-PC-Gaming",
    "2366": "Piese telefoane & tablete",
    "2367": "Retelistica & Servere",
    "2368": "Retelistica & Servere",
    "2369": "Retelistica & Servere",
    "2370": "Retelistica & Servere",
    "2371": "Retelistica & Servere",
    "2372": "Gadgets, Wearables & Camere foto-video",
    "2373": "Gadgets, Wearables & Camere foto-video",
    "2374": "Gadgets, Wearables & Camere foto-video",
    "2375": "Home Cinema & Audio",
    "2376": "Imprimante, scannere",
    "2377": "Imprimante, scannere",
    "2378": "Imprimante, scannere",
    "2379": "Imprimante, scannere",
    "2380": "Ingrijire Personala",
    "2381": "Ingrijire Personala",
    "2382": "Ingrijire Personala",
    "2383": "Ingrijire Personala",
    "2384": "Laptop-Calculator-Gaming",
    "2385": "Laptop-Calculator-Gaming",
    "2386": "Laptop-Calculator-Gaming",
    "2387": "Periferice & Accesorii Laptop-PC-Gaming",
    "2388": "Periferice & Accesorii Laptop-PC-Gaming",
    "2389": "Periferice & Accesorii Laptop-PC-Gaming",
    "2390": "Periferice & Accesorii Laptop-PC-Gaming",
    "2391": "Periferice & Accesorii Laptop-PC-Gaming",
    "2392": "Periferice & Accesorii Laptop-PC-Gaming",
    "2393": "Periferice & Accesorii Laptop-PC-Gaming",
    "2394": "Piese telefoane & tablete",
    "2395": "Retelistica & Servere",
    "2396": "Retelistica & Servere",
    "2397": "Retelistica & Servere",
    "2398": "Retelistica & Servere",
    "2399": "Retelistica & Servere",
    "2400": "Imprimante, scannere",
    "2401": "Ingrijire Personala",
    "2402": "Ingrijire Personala",
    "2403": "Laptop-Calculator-Gaming",
    "2404": "Laptop-Calculator-Gaming",
    "2405": "Periferice & Accesorii Laptop-PC-Gaming",
    "2406": "Periferice & Accesorii Laptop-PC-Gaming",
    "2407": "Periferice & Accesorii Laptop-PC-Gaming",
    "2408": "Laptop-Calculator-Gaming",
    "2409": "Laptop-Calculator-Gaming",
    "2410": "Laptop-Calculator-Gaming",
    "2411": "Laptop-Calculator-Gaming",
    "2412": "Laptop-Calculator-Gaming",
    "2413": "Laptop-Calculator-Gaming",
    "2414": "Laptop-Calculator-Gaming",
    "2415": "Laptop-Calculator-Gaming",
    "2416": "Laptop-Calculator-Gaming",
    "2417": "Laptop-Calculator-Gaming",
    "2418": "Laptop-Calculator-Gaming",
    "2419": "Laptop-Calculator-Gaming",
    "2420": "Laptop-Calculator-Gaming",
    "2421": "Laptop-Calculator-Gaming",
    "2422": "Laptop-Calculator-Gaming",
    "2423": "Laptop-Calculator-Gaming",
    "2424": "Laptop-Calculator-Gaming",
    "2425": "Sanatate si frumusete",
    "2426": "Sanatate si frumusete",
    "2427": "Sanatate si frumusete",
    "2428": "Sanatate si frumusete",
    "2429": "Sanatate si frumusete",
    "2430": "Sanatate si frumusete",
    "2431": "Sanatate si frumusete",
    "2432": "Sanatate si frumusete",
    "2433": "Sanatate si frumusete",
    "2434": "Sanatate si frumusete",
    "2435": "Sanatate si frumusete",
    "2436": "Sanatate si frumusete",
    "2437": "Sanatate si frumusete",
    "2438": "Sanatate si frumusete",
    "2439": "Sanatate si frumusete",
    "2440": "Sanatate si frumusete",
    "2441": "Sanatate si frumusete",
    "2442": "Sanatate si frumusete",
    "2443": "Sanatate si frumusete",
    "2444": "Sanatate si frumusete",
    "2445": "Sanatate si frumusete",
    "2446": "Sanatate si frumusete",
    "2447": "Sanatate si frumusete",
    "2448": "Sanatate si frumusete",
    "2449": "Sanatate si frumusete",
    "2450": "Sanatate si frumusete",
    "2451": "Sanatate si frumusete",
    "2452": "Sanatate si frumusete",
    "2453": "Sanatate si frumusete",
    "2454": "Sanatate si frumusete",
    "2455": "Sanatate si frumusete",
    "2456": "Sanatate si frumusete",
    "2457": "Sanatate si frumusete",
    "2458": "Sanatate si frumusete",
    "2459": "Electrocasnice",
    "2460": "Electrocasnice",
    "2462": "Audio Hi Fi & Profesionale",
    "2463": "Casa inteligenta - Smarthome",
    "2464": "Casa inteligenta - Smarthome",
    "2465": "Casti Audio",
    "2466": "Casti Audio",
    "2467": "Casti Audio",
    "2468": "Casti Audio",
    "2469": "Componente Laptop-PC",
    "2470": "Componente Laptop-PC",
    "2471": "Componente Laptop-PC",
    "2472": "Componente Laptop-PC",
    "2473": "Componente Laptop-PC",
    "2474": "Componente Laptop-PC",
    "2475": "Componente Laptop-PC",
    "2476": "Electrocasnice",
    "2477": "Electrocasnice",
    "2478": "Electrocasnice",
    "2479": "Electrocasnice",
    "2480": "Electrocasnice",
    "2481": "Electrocasnice",
    "2482": "Electrocasnice",
    "2483": "Electrocasnice",
    "2484": "Electrocasnice",
    "2485": "Electrocasnice",
    "2486": "Electrocasnice",
    "2487": "Audio Hi Fi & Profesionale",
    "2488": "Casa inteligenta - Smarthome",
    "2489": "Casa inteligenta - Smarthome",
    "2490": "Casti Audio",
    "2491": "Casti Audio",
    "2492": "Casti Audio",
    "2493": "Casti Audio",
    "2494": "Componente Laptop-PC",
    "2495": "Componente Laptop-PC",
    "2496": "Componente Laptop-PC",
    "2497": "Componente Laptop-PC",
    "2498": "Componente Laptop-PC",
    "2499": "Componente Laptop-PC",
    "2500": "Componente Laptop-PC",
    "2501": "Electrocasnice",
    "2502": "Electrocasnice",
    "2503": "Electrocasnice",
    "2505": "Electrocasnice",
    "2506": "Electrocasnice",
    "2507": "Electrocasnice",
    "2508": "Electrocasnice",
    "2509": "Electrocasnice",
    "2510": "Electrocasnice",
    "2511": "Electrocasnice",
    "2512": "Audio Hi Fi & Profesionale",
    "2513": "Componente Laptop-PC",
    "2514": "Electrocasnice",
    "2515": "Electrocasnice",
    "2516": "Electrocasnice",
    "2517": "Electrocasnice",
    "2518": "Electrocasnice",
    "2519": "Electrocasnice",
    "2521": "Electrocasnice",
    "2522": "Audio Hi Fi & Profesionale",
    "2523": "Componente Laptop-PC",
    "2524": "Electrocasnice",
    "2525": "Electrocasnice",
    "2526": "Electrocasnice",
    "2527": "Electrocasnice",
    "2528": "Componente Laptop-PC",
    "2529": "Electrocasnice",
    "2530": "Electrocasnice",
    "2531": "Componente Laptop-PC",
    "2532": "Electrocasnice",
    "2537": "Cadouri",
    "2563": "Drone & accesorii",
    "2564": "Aparate medicale & Wellness",
    "2565": "Aparate medicale & Wellness",
    "2566": "Aparate medicale & Wellness",
    "2567": "Aparate medicale & Wellness",
    "2568": "Aparate medicale & Wellness",
    "2569": "Electrocasnice",
    "2570": "Electrocasnice",
    "2571": "Hale metalice, structuri metalice si containere",
    "2572": "Sanatate si frumusete",
    "2637": "Imprimante, scannere",
    "2638": "Gadgets, Wearables & Camere foto-video",
    "2639": "Pescuit",
    "2641": "Sanatate si frumusete",
    "2642": "Electrocasnice",
    "2644": "Utilaje agricole si industriale",
    "2645": "Utilaje agricole si industriale",
    "2646": "Utilaje agricole si industriale",
    "2647": "Utilaje agricole si industriale",
    "2648": "Utilaje agricole si industriale",
    "2649": "Utilaje agricole si industriale",
    "2650": "Utilaje agricole si industriale",
    "2651": "Utilaje agricole si industriale",
    "2652": "Utilaje agricole si industriale",
    "2653": "Utilaje agricole si industriale",
    "2654": "Utilaje agricole si industriale",
    "2655": "Utilaje agricole si industriale",
    "2656": "Utilaje agricole si industriale",
    "2657": "Utilaje agricole si industriale",
    "2658": "Utilaje agricole si industriale",
    "2688": "Echipamente pentru magazine si birouri",
    "2691": "Horeca",
    "2697": "Alte echipamente profesionale",
    "2698": "Echipamente pentru magazine si birouri",
    "2699": "Echipamente pentru magazine si birouri",
    "2700": "Echipamente pentru magazine si birouri",
    "2701": "Echipamente pentru magazine si birouri",
    "2702": "Echipamente pentru magazine si birouri",
    "2703": "Echipamente pentru magazine si birouri",
    "2704": "Echipamente pentru magazine si birouri",
    "2705": "Echipamente pentru magazine si birouri",
    "2707": "Horeca",
    "2709": "Horeca",
    "2710": "Horeca",
    "2711": "Horeca",
    "2757": "Utilaje agricole si industriale",
    "2758": "Utilaje agricole si industriale",
    "2759": "Utilaje agricole si industriale",
    "2760": "Utilaje agricole si industriale",
    "2761": "Utilaje agricole si industriale",
    "2762": "Utilaje agricole si industriale",
    "2763": "Utilaje agricole si industriale",
    "2764": "Utilaje agricole si industriale",
    "2765": "Utilaje agricole si industriale",
    "2766": "Utilaje agricole si industriale",
    "2767": "Utilaje agricole si industriale",
    "2768": "Utilaje agricole si industriale",
    "2769": "Utilaje agricole si industriale",
    "2880": "Accesorii pentru animale de companie",
    "2882": "Mancare si gustari pentru animale de companie",
    "2883": "Caini",
    "2884": "Pisici",
    "2887": "Constructii",
    "2888": "Constructii",
    "2889": "Constructii",
    "2890": "Constructii",
    "2891": "Constructii",
    "2892": "Constructii",
    "2893": "Constructii",
    "2894": "Constructii",
    "2895": "Constructii",
    "2896": "Constructii",
    "2897": "Constructii",
    "2898": "Constructii",
    "2899": "Constructii",
    "2900": "Constructii",
    "2901": "Constructii",
    "2902": "Constructii",
    "2903": "Constructii",
    "2904": "Constructii",
    "2905": "Constructii",
    "2906": "Constructii",
    "2907": "Constructii",
    "2908": "Constructii",
    "2909": "Constructii",
    "2911": "Constructii",
    "2912": "Constructii",
    "2913": "Constructii",
    "2914": "Constructii",
    "2915": "Constructii",
    "2917": "Constructii",
    "2918": "Constructii",
    "2919": "Finisaj interior",
    "2920": "Finisaj interior",
    "2921": "Finisaj interior",
    "2922": "Finisaj interior",
    "2923": "Finisaj interior",
    "2924": "Finisaj interior",
    "2925": "Finisaj interior",
    "2926": "Finisaj interior",
    "2927": "Finisaj interior",
    "2928": "Finisaj interior",
    "2929": "Finisaj interior",
    "2930": "Finisaj interior",
    "2931": "Finisaj interior",
    "2932": "Finisaj interior",
    "2933": "Finisaj interior",
    "2934": "Finisaj interior",
    "2935": "Finisaj interior",
    "2936": "Finisaj interior",
    "2937": "Finisaj interior",
    "2938": "Finisaj interior",
    "2939": "Finisaj interior",
    "2940": "Finisaj interior",
    "2941": "Finisaj interior",
    "2942": "Finisaj interior",
    "2943": "Finisaj interior",
    "2944": "Finisaj interior",
    "2945": "Finisaj interior",
    "2946": "Finisaj interior",
    "2947": "Finisaj interior",
    "2948": "Finisaj interior",
    "2949": "Finisaj interior",
    "2950": "Finisaj interior",
    "2951": "Finisaj interior",
    "2952": "Finisaj interior",
    "2953": "Finisaj interior",
    "2955": "Gradina",
    "2956": "Gradina",
    "2957": "Gradina",
    "2958": "Gradina",
    "2959": "Gradina",
    "2960": "Gradina",
    "2961": "Gradina",
    "2962": "Gradina",
    "2963": "Gradina",
    "2967": "Gradina",
    "2968": "Gradina",
    "2969": "Gradina",
    "2970": "Gradina",
    "2971": "Gradina",
    "2972": "Gradina",
    "2973": "Gradina",
    "2974": "Gradina",
    "2975": "Gradina",
    "2976": "Gradina",
    "2977": "Gradina",
    "2978": "Gradina",
    "2979": "Gradina",
    "2980": "Gradina",
    "2981": "Gradina",
    "2982": "Gradina",
    "2983": "Gradina",
    "2984": "Gradina",
    "2985": "Gradina",
    "2986": "Gradina",
    "2987": "Gradina",
    "2988": "Gradina",
    "2989": "Gradina",
    "2990": "Gradina",
    "2991": "Gradina",
    "2992": "Gradina",
    "2993": "Gradina",
    "2994": "Gradina",
    "2995": "Gradina",
    "2996": "Gradina",
    "2997": "Gradina",
    "2998": "Gradina",
    "2999": "Gradina",
    "3000": "Gradina",
    "3001": "Gradina",
    "3002": "Gradina",
    "3003": "Gradina",
    "3004": "Gradina",
    "3005": "Gradina",
    "3006": "Gradina",
    "3007": "Gradina",
    "3008": "Gradina",
    "3009": "Gradina",
    "3010": "Gradina",
    "3011": "Gradina",
    "3012": "Gradina",
    "3013": "Gradina",
    "3014": "Gradina",
    "3015": "Gradina",
    "3016": "Gradina",
    "3017": "Gradina",
    "3018": "Gradina",
    "3019": "Gradina",
    "3020": "Gradina",
    "3021": "Gradina",
    "3022": "Gradina",
    "3023": "Gradina",
    "3024": "Gradina",
    "3025": "Gradina",
    "3026": "Gradina",
    "3027": "Gradina",
    "3028": "Gradina",
    "3029": "Gradina",
    "3030": "Gradina",
    "3031": "Gradina",
    "3032": "Gradina",
    "3033": "Gradina",
    "3034": "Gradina",
    "3035": "Gradina",
    "3036": "Gradina",
    "3037": "Gradina",
    "3038": "Gradina",
    "3039": "Gradina",
    "3040": "Gradina",
    "3041": "Gradina",
    "3042": "Gradina",
    "3043": "Gradina",
    "3044": "Gradina",
    "3045": "Gradina",
    "3048": "Gradina",
    "3050": "Utilaje agricole si industriale",
    "3051": "Mobila",
    "3052": "Mobila",
    "3053": "Mobila",
    "3054": "Mobila",
    "3055": "Mobila",
    "3056": "Mobila",
    "3057": "Mobila",
    "3058": "Mobila",
    "3059": "Mobila",
    "3060": "Mobila",
    "3061": "Mobila",
    "3062": "Mobila",
    "3063": "Mobila",
    "3064": "Mobila",
    "3065": "Mobila",
    "3066": "Mobila",
    "3067": "Mobila",
    "3068": "Mobila",
    "3069": "Mobila",
    "3070": "Mobila",
    "3071": "Mobila",
    "3072": "Mobila",
    "3073": "Mobila",
    "3074": "Mobila",
    "3075": "Mobila",
    "3076": "Mobila",
    "3077": "Mobila",
    "3078": "Mobila",
    "3079": "Mobila",
    "3080": "Mobila",
    "3081": "Mobila",
    "3082": "Mobila",
    "3083": "Mobila",
    "3084": "Mobila",
    "3085": "Mobila",
    "3086": "Mobila",
    "3087": "Mobila",
    "3088": "Mobila",
    "3089": "Mobila",
    "3090": "Mobila",
    "3091": "Mobila",
    "3092": "Mobila",
    "3093": "Mobila",
    "3094": "Mobila",
    "3095": "Mobila",
    "3096": "Mobila",
    "3097": "Mobila",
    "3098": "Mobila",
    "3099": "Mobila",
    "3100": "Mobila",
    "3101": "Mobila",
    "3102": "Mobila",
    "3115": "Decoratiuni pentru interior",
    "3129": "Decoratiuni pentru interior",
    "3130": "Decoratiuni pentru interior",
    "3131": "Decoratiuni pentru interior",
    "3132": "Decoratiuni pentru interior",
    "3133": "Decoratiuni pentru interior",
    "3134": "Decoratiuni pentru interior",
    "3135": "Decoratiuni pentru interior",
    "3136": "Decoratiuni pentru interior",
    "3137": "Decoratiuni pentru interior",
    "3138": "Decoratiuni pentru interior",
    "3139": "Decoratiuni pentru interior",
    "3140": "Decoratiuni pentru interior",
    "3141": "Decoratiuni pentru interior",
    "3142": "Decoratiuni pentru interior",
    "3143": "Decoratiuni pentru interior",
    "3144": "Decoratiuni pentru interior",
    "3145": "Decoratiuni pentru interior",
    "3214": "Scule, unelte, feronerie",
    "3215": "Scule, unelte, feronerie",
    "3216": "Scule, unelte, feronerie",
    "3217": "Scule, unelte, feronerie",
    "3218": "Scule, unelte, feronerie",
    "3219": "Scule, unelte, feronerie",
    "3220": "Scule, unelte, feronerie",
    "3221": "Iluminat",
    "3222": "Iluminat",
    "3223": "Iluminat",
    "3224": "Iluminat",
    "3225": "Iluminat",
    "3226": "Iluminat",
    "3227": "Iluminat",
    "3228": "Iluminat",
    "3229": "Iluminat",
    "3230": "Iluminat",
    "3231": "Instalatii termice",
    "3232": "Instalatii termice",
    "3233": "Instalatii termice",
    "3234": "Instalatii termice",
    "3235": "Instalatii termice",
    "3236": "Instalatii termice",
    "3237": "Instalatii termice",
    "3238": "Instalatii termice",
    "3239": "Instalatii termice",
    "3240": "Instalatii termice",
    "3241": "Instalatii termice",
    "3242": "Instalatii termice",
    "3243": "Instalatii termice",
    "3244": "Instalatii termice",
    "3245": "Instalatii termice",
    "3246": "Instalatii termice",
    "3247": "Instalatii termice",
    "3248": "Instalatii termice",
    "3249": "Instalatii termice",
    "3250": "Instalatii termice",
    "3251": "Instalatii termice",
    "3252": "Instalatii termice",
    "3253": "Instalatii termice",
    "3254": "Instalatii termice",
    "3255": "Instalatii termice",
    "3256": "Instalatii termice",
    "3257": "Instalatii termice",
    "3258": "Instalatii electrice",
    "3259": "Instalatii electrice",
    "3260": "Instalatii electrice",
    "3261": "Instalatii electrice",
    "3262": "Instalatii electrice",
    "3263": "Instalatii electrice",
    "3264": "Instalatii electrice",
    "3265": "Instalatii electrice",
    "3266": "Instalatii electrice",
    "3267": "Instalatii electrice",
    "3268": "Instalatii electrice",
    "3269": "Instalatii electrice",
    "3270": "Instalatii electrice",
    "3271": "Instalatii electrice",
    "3272": "Instalatii electrice",
    "3273": "Instalatii electrice",
    "3274": "Instalatii sanitare",
    "3275": "Instalatii sanitare",
    "3276": "Instalatii sanitare",
    "3277": "Instalatii sanitare",
    "3278": "Instalatii sanitare",
    "3279": "Instalatii sanitare",
    "3280": "Instalatii sanitare",
    "3281": "Instalatii sanitare",
    "3282": "Instalatii sanitare",
    "3283": "Instalatii sanitare",
    "3284": "Instalatii sanitare",
    "3285": "Instalatii sanitare",
    "3298": "Utilaje agricole si industriale",
}


# Slug de subcategorie OLX (normalizedName al nodului-ancora) -> subcategoria
# FlipRadar. Generat automat — map_olx_categories.py. Folosit ca fallback cand
# keyword.category e stocat ca slug (ex. ".../telefoane-mobile") si nu exista
# subcategorie in marketplace_config, ca sa activam filtrul de subcategorie.
OLX_SUBCATEGORY_SLUG_TO_NAME = {
    "accesorii": "Accesorii",
    "accesorii-pentru-animale-de-companie": "Accesorii pentru animale de companie",
    "accesorii-telefoane-si-tablete": "Accesorii telefoane & tablete",
    "adoptii": "Adoptii",
    "alimentatie-produse-bio": "Produse piata - alimentatie",
    "alte-accesorii-moda-frumusete": "Alte accesorii de moda si frumusete",
    "alte-animale": "Alte animale de companie",
    "alte-echipamente-profesionale": "Alte echipamente profesionale",
    "alte-piese": "Alte piese",
    "alte-vehicule": "Alte Vehicule",
    "animale-domestice-pasari": "Animale domestice si pasari",
    "aparate-medicale-si-wellness": "Aparate medicale & Wellness",
    "arta-antichitati": "Arta - Obiecte de colectie",
    "articole-menaj": "Articole menaj",
    "articole-scolare-papetarie": "Articole scolare - papetarie",
    "audio-hi-fi-si-profesionale": "Audio Hi Fi & Profesionale",
    "biciclete-fitness": "Biciclete - Fitness - Suplimente",
    "cadouri": "Cadouri",
    "caini": "Caini",
    "camping": "Camping",
    "caroserie-interior": "Caroserie - Interior",
    "carti-muzica-filme": "Carti - Muzica - Filme",
    "carucioare-si-patuturi": "La plimbare",
    "casa-inteligenta-smarthome": "Casa inteligenta - Smarthome",
    "casti-audio": "Casti Audio",
    "ceasuri": "Ceasuri",
    "componente-laptop-pc": "Componente Laptop-PC",
    "constructii": "Constructii",
    "consumabile-accesorii": "Consumabile - accesorii",
    "decoratiuni-interior": "Decoratiuni pentru interior",
    "diverse": "Alte produse copii",
    "drone-si-accesorii": "Drone & accesorii",
    "echipamente-pentru-magazine-si-birouri": "Echipamente pentru magazine si birouri",
    "electrocasnice": "Electrocasnice",
    "finisaj-interior": "Finisaj interior",
    "fotbal": "Fotbal",
    "gadgets-wearables-si-camere-foto-video": "Gadgets, Wearables & Camere foto-video",
    "gradina": "Gradina",
    "haine-barbati": "Haine barbati",
    "haine-dama": "Haine dama",
    "haine-incaltaminte-copii-si-gravide": "Haine - Incaltaminte copii si gravide",
    "haine-nunta": "Haine pentru nunta",
    "haine_gravide": "Haine pentru gravide",
    "hale-metalice-structuri-metalice-si-containere": "Hale metalice, structuri metalice si containere",
    "home-cinema-si-audio": "Home Cinema & Audio",
    "horeca": "Horeca",
    "iluminat": "Iluminat",
    "imprimante-scannere": "Imprimante, scannere",
    "incaltaminte-barbati": "Incaltaminte barbati",
    "incaltaminte-dama": "Incaltaminte dama",
    "ingrijire-personala": "Ingrijire Personala",
    "instalatii-electrice": "Instalatii electrice",
    "instalatii-sanitare": "Instalatii sanitare",
    "instalatii-termice": "Instalatii termice",
    "jocuri-jucarii": "Jocuri - Jucarii",
    "laptop-calculator-gaming": "Laptop-Calculator-Gaming",
    "lenjerie-costume-inot-barbati": "Lenjerie si costume de inot barbati",
    "lenjerie_costume_baie_dama": "Lenjerie si costume de baie dama",
    "mancare-accesorii": "Alimentatie - Ingrijire",
    "mancare-si-gustari-pentru-animale-de-companie": "Mancare si gustari pentru animale de companie",
    "mecanica-electrica": "Mecanica - electrica",
    "mobila": "Mobila",
    "palarii-sepci-bandane": "Palarii, sepci si bandane",
    "patuturi-mobilier": "Camera copilului",
    "periferice-si-accesorii-laptop-pc-gaming": "Periferice & Accesorii Laptop-PC-Gaming",
    "pescuit": "Pescuit",
    "piese-telefoane-si-tablete": "Piese telefoane & tablete",
    "pisici": "Pisici",
    "retelistica-si-servere": "Retelistica & Servere",
    "roti-jante-anvelope": "Roti - Jante - Anvelope",
    "sanatate-frumusete": "Sanatate si frumusete",
    "scule-unelte-feronerie": "Scule, unelte, feronerie",
    "seminte-plante-pomi": "Cereale - plante - pomi",
    "sporturi-de-apa": "Sporturi de apa",
    "sporturi-de-iarna": "Sporturi de iarna",
    "tablete": "Tablete - eReadere",
    "telefoane-mobile": "Telefoane",
    "televizoare": "TV",
    "tenis": "Tenis",
    "trotinete-role-skateboard": "Trotinete, role, skateboard",
    "utilaje-agricole": "Utilaje agricole si industriale",
    "vanatoare": "Vanatoare",
    "vehicule-pentru-dezmembrare": "Vehicule pentru dezmembrare",
    "videoproiectoare-si-accesorii": "Videoproiectoare & Accesorii",
}


def _olx_subcategory_from_slug(category):
    """Deriveaza subcategoria FlipRadar din slug-ul OLX stocat pe keyword.category
    (ex. "electronice-si-electrocasnice/telefoane-mobile" -> "Telefoane"). Fallback
    pentru keyword-urile old-form fara subcategorie in marketplace_config. Returneaza
    None daca slug-ul nu corespunde niciunei subcategorii cunoscute (filtrul ramane
    inactiv -> nicio regresie)."""
    if not category:
        return None
    last = str(category).strip().strip("/").split("/")[-1].strip().lower()
    return OLX_SUBCATEGORY_SLUG_TO_NAME.get(last)


def _olx_listing_matches_subcategory(listing: dict, expected_subcategory: str) -> bool:
    """True daca listing-ul OLX apartine subcategoriei alese de utilizator.

    Safe default: daca nu avem categoria (extractie esuata) sau ID-ul nu e mapat,
    pastram anuntul — mai bine un fals pozitiv decat sa excludem anunturi legitime.
    """
    if not expected_subcategory:
        return True
    raw = (listing.get("olx_category") or "").strip()
    if not raw:
        return True  # fara info de categorie -> nu excludem
    mapped = OLX_CATEGORY_ID_TO_SUBCATEGORY.get(raw)
    if mapped is None:
        return True  # ID necunoscut -> safe default, pastram
    match = mapped.strip().lower() == expected_subcategory.strip().lower()
    if not match:
        print(f"[OlxScraper] Exclus (categorie OLX {raw}='{mapped}' ≠ "
              f"'{expected_subcategory}'): {str(listing.get('title', ''))[:60]}")
    return match


def _parse_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    return []


def _get_or_create_settings(db: Session, user_id: int) -> RadarSettings:
    s = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
    if s:
        return s
    s = RadarSettings(user_id=user_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _platform_enabled_in_settings(platform: str, settings: RadarSettings) -> bool:
    p = (platform or "").lower()
    if p == "olx":
        return bool(settings.platform_olx_enabled)
    if p == "vinted":
        return bool(settings.platform_vinted_enabled)
    if p == "okazii":
        return bool(settings.platform_okazii_enabled)
    if p == "facebook":
        return bool(settings.platform_facebook_enabled)
    if p == "lajumate":
        return bool(getattr(settings, "platform_lajumate_enabled", True))
    if p == "publi24":
        return bool(getattr(settings, "platform_publi24_enabled", True))
    if p == "autovit":
        return bool(getattr(settings, "platform_autovit_enabled", True))
    if p == "mobilede":
        return bool(getattr(settings, "platform_mobilede_enabled", True))
    return False


def _should_scan_keyword(keyword: RadarKeyword) -> bool:
    """True daca intervalul de polling a expirat de la ultimul scan."""
    if keyword.last_scan_at is None:
        return True
    elapsed = datetime.now(timezone.utc) - keyword.last_scan_at.replace(tzinfo=timezone.utc) if keyword.last_scan_at.tzinfo is None else datetime.now(timezone.utc) - keyword.last_scan_at
    return elapsed >= timedelta(minutes=keyword.poll_interval_minutes or 5)


def _run_scraper(
    platform: str,
    keyword: RadarKeyword,
    settings: RadarSettings,
    exclude_words: list[str],
    page: int = 1,
    advanced: bool = False,
    db=None,
    skip_enrich_ids: Optional[set] = None,
) -> list[dict]:
    """Apel sincron la scraperul potrivit. Try/except per scraper ca un crash
    pe o platforma sa nu opreasca scanul pentru celelalte.

    RP-2: in modul `advanced`, scraperele primesc liste de excluderi GOALE — filtrarea
    o face centralizat `_apply_advanced_exclusions` dupa intoarcere (ca sa nu se
    dubleze cu regulile vechi din is_excluded).
    """
    try:
        # MODULE 1d — cuvinte excluse pe descriere (doar OLX & Vinted le primesc)
        desc_raw = getattr(keyword, "exclude_description_words", None)
        desc_exclude = desc_raw if isinstance(desc_raw, list) else _parse_json_list(desc_raw)
        if advanced:
            # engine-ul v2 filtreaza dupa intoarcere; scraperele NU mai exclud.
            exclude_words = []
            desc_exclude = []
        if platform == "olx":
            return search_olx(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                judet=keyword.judet,
                oras=keyword.oras,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                min_price=keyword.min_price,
                category=keyword.category,
                exclude_description_words=desc_exclude,
            )
        if platform == "vinted":
            return search_vinted(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                min_price=keyword.min_price,
                category=keyword.category,
                exclude_description_words=desc_exclude,
                # MODIFICARE 4 — subcategoria (din marketplace_config) filtreaza post-scrape.
                subcategory=_keyword_subcategory(keyword),
                # RP-2 — resolver cu precedență config > db > map.
                db=db,
                marketplace_config=_keyword_marketplace_config(keyword),
            )
        if platform == "okazii":
            return search_okazii(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                min_price=keyword.min_price,
                category=keyword.category,
                skip_enrich_ids=skip_enrich_ids,
            )
        if platform == "facebook":
            return search_facebook(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                judet=keyword.judet,
                oras=keyword.oras,
                exclude_words=exclude_words,
                session_path=settings.facebook_session_path,
                min_price=keyword.min_price,
                category=keyword.category,
            )
        if platform == "lajumate":
            return search_lajumate(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                judet=keyword.judet,
                oras=keyword.oras,
                category=keyword.category,
                skip_enrich_ids=skip_enrich_ids,
            )
        if platform == "publi24":
            return search_publi24(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                judet=keyword.judet,
                oras=keyword.oras,
                category=keyword.category,
                skip_enrich_ids=skip_enrich_ids,
            )
        if platform in ("autovit", "mobilede"):
            try:
                car_filters_dict = json.loads(keyword.car_filters) if keyword.car_filters else None
            except (json.JSONDecodeError, TypeError):
                car_filters_dict = None
            if platform == "autovit":
                return search_autovit(
                    keyword=keyword.name,
                    page=page,
                    max_price=keyword.max_price,
                    min_price=keyword.min_price,
                    exclude_words=exclude_words,
                    car_filters=car_filters_dict,
                )
            return search_mobilede(
                keyword=keyword.name,
                page=page,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                exclude_words=exclude_words,
                car_filters=car_filters_dict,
            )
    except Exception as exc:
        print(f"[RadarScanner] Scraperul {platform} a crapat: {exc}")
        health_watchdog.note_error(platform)
    return []


def _already_seen(db: Session, user_id: int, platform: str, external_id: str) -> bool:
    seen = (
        db.query(RadarSeenId)
        .filter(
            RadarSeenId.user_id == user_id,
            RadarSeenId.platform == platform,
            RadarSeenId.external_id == external_id,
        )
        .first()
    )
    return seen is not None


def _mark_seen(db: Session, user_id: int, platform: str, external_id: str) -> None:
    db.add(RadarSeenId(user_id=user_id, platform=platform, external_id=external_id))


def _fmt_dt(dt) -> str:
    if not dt:
        return "Necunoscut"
    try:
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "Necunoscut"


def _send_email_alert(
    user: User,
    listing: dict,
    keyword: RadarKeyword,
    score: str,
    margin_pct: float,
    listed_at=None,
    found_at=None,
) -> None:
    if not smtp_configured() or not user.email:
        return
    subject = f"[Radar] {score} — {listing.get('title', '')[:60]}"
    body = (
        f"Salut!\n\n"
        f"Un deal cu scor {score} a fost detectat pe {listing.get('platform', '?')}.\n"
        f"Keyword: {keyword.name}\n"
        f"Titlu: {listing.get('title')}\n"
        f"Preț cerut: {listing.get('price')} {listing.get('currency', 'RON')}\n"
        f"Marjă estimată: {margin_pct:.0f}%\n"
        f"Postat pe platformă: {_fmt_dt(listed_at)}\n"
        f"Găsit de FlipRadar: {_fmt_dt(found_at)}\n"
        f"Link: {listing.get('url')}\n"
        f"\n-- FlipRadar Radar"
    )
    try:
        send_email(user.email, subject, body)
    except Exception as exc:
        print(f"[RadarScanner] Email esuat: {exc}")


def _is_within_active_hours(kw) -> bool:
    """Returns True if the keyword should be scanned at the current time.
    Supports overnight ranges: e.g. start=22, end=6 → active 22:00–05:59.
    """
    if kw.active_hours_start is None or kw.active_hours_end is None:
        return True
    h = datetime.now().hour
    s, e = kw.active_hours_start, kw.active_hours_end
    if s <= e:
        return s <= h < e
    else:  # overnight
        return h >= s or h < e


def _seller_persist_fields(listing: dict, kw: RadarKeyword) -> tuple:
    """(seller_reviews, seller_rating, seller_risk, attributes_json) pentru un listing.

    Aduna `extra_attributes` (view/favourite Vinted, okazii_seller_type, ...) + badge-uri
    + olx_member_since/olx_numeric_id + atributele Vinted + `risk_reason` intr-un singur
    JSON si calculeaza badge-ul de risc (compute_seller_risk).
    """
    seller_reviews = listing.get("seller_reviews")
    seller_rating = listing.get("seller_rating")
    extra = dict(listing.get("extra_attributes") or {})
    if listing.get("olx_member_since") is not None:
        extra["olx_member_since"] = listing.get("olx_member_since")
    if listing.get("olx_numeric_id") is not None:
        extra["olx_numeric_id"] = listing.get("olx_numeric_id")
    if listing.get("seller_badges"):
        extra["seller_badges"] = listing.get("seller_badges")
    if listing.get("attributes"):
        extra["attributes"] = listing.get("attributes")

    risk, reason = compute_seller_risk(
        platform=listing.get("platform"),
        price=listing.get("price"),
        resale_price=kw.resale_price,
        seller_name=listing.get("seller_name"),
        seller_reviews=seller_reviews,
        seller_rating=seller_rating,
        extra=extra,
    )
    if reason:
        extra["risk_reason"] = reason
    attributes_json = json.dumps(extra, ensure_ascii=False) if extra else None
    return seller_reviews, seller_rating, risk, attributes_json


def _maybe_enrich_olx_inline(listing: dict) -> None:
    """Enrichment OLX inline (inainte de save+notify) prin /api/v1/offers/{id}, cu
    plafon _ENRICH_OLX_CAP pe ciclu + delay 2-4s jitter. Muta seller/data/descriere/
    member_since in listing. La cap sau lipsa id numeric, nu face nimic."""
    nid = listing.get("olx_numeric_id")
    if not nid or _enrich_counters["olx"] >= _ENRICH_OLX_CAP:
        return
    if _enrich_counters["olx"] > 0:
        time.sleep(random.uniform(2.0, 4.0))
    _enrich_counters["olx"] += 1
    try:
        det = fetch_olx_offer_details(nid)
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"OLX enrichment inline: {str(exc)[:80]}")
        return
    for k in ("seller_name", "seller_id", "listed_at", "description", "olx_member_since"):
        if det.get(k) is not None:
            listing[k] = det[k]


def _enrich_vinted_background(db: Session, user: User) -> None:
    """Enrichment Vinted in FUNDAL, dupa save+notify: pentru listingurile cu
    vinted_detail_fetched=False (recente intai), pana la _ENRICH_VINTED_CAP pe ciclu.
    Fiecare fetch trece prin guard-ul+limiterul vinted_html (throttle 20–30s, plafon
    zilnic, circuit breaker). La succes persista poze/descriere/data/atribute/vanzator
    + recalculeaza risc + marcheaza fetched."""
    if _enrich_counters["vinted"] >= _ENRICH_VINTED_CAP:
        return
    # RP-1.1 — respecta guard-ul INAINTE de batch: daca breaker-ul e deschis / plafonul
    # zilnic e atins, sari TOT batch-ul cu O SINGURA linie (nu 8 incercari degeaba).
    gs = vinted_guard_status("vinted.ro")
    if not gs["allowed"]:
        log_manager.emit("radar", "INFO",
            f"Enrichment Vinted: batch sarit (guard: {gs['reason']})")
        return
    remaining = _ENRICH_VINTED_CAP - _enrich_counters["vinted"]
    rows = (
        db.query(RadarListing)
        .filter(
            RadarListing.user_id == user.id,
            RadarListing.platform == "vinted",
            RadarListing.vinted_detail_fetched == False,  # noqa: E712
        )
        .order_by(RadarListing.found_at.desc())
        .limit(remaining)
        .all()
    )
    for row in rows:
        if _enrich_counters["vinted"] >= _ENRICH_VINTED_CAP:
            break
        _enrich_counters["vinted"] += 1
        item_id = (row.external_id or "").replace("vinted_", "", 1)
        if not item_id:
            continue
        try:
            detail = get_vinted_item_detail(item_id)
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Vinted enrichment {row.id}: {str(exc)[:80]}")
            detail = None
        if not detail:
            # RP-1.1 — daca fetch-ul a esuat SI breaker-ul tocmai s-a deschis, opreste
            # batch-ul imediat (nu continua cu restul itemilor din ciclul curent).
            if vinted_guard_status("vinted.ro")["reason"] == "breaker_open":
                log_manager.emit("radar", "WARN",
                    "Enrichment Vinted: breaker deschis — opresc batch-ul")
                break
            continue  # ramane fetched=False -> reincearca on-demand / ciclul urmator
        kw = db.query(RadarKeyword).filter(RadarKeyword.id == row.keyword_id).first()
        apply_vinted_detail(row, detail, kw.resale_price if kw else None)
        log_manager.emit("radar", "OK", f"Vinted enrichment: {row.title[:50]} (reviews={row.seller_reviews})")
    try:
        db.commit()
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"Vinted enrichment commit: {str(exc)[:80]}")
        db.rollback()


def _enrich_olx_backlog(db: Session, user: User) -> None:
    """Backlog OLX (dupa scan): re-imbogateste rowuri OLX fara seller_name care au
    olx_numeric_id persistat in attributes_json, max _ENRICH_OLX_BACKLOG_CAP pe ciclu."""
    if _enrich_counters["olx_backlog"] >= _ENRICH_OLX_BACKLOG_CAP:
        return
    remaining = _ENRICH_OLX_BACKLOG_CAP - _enrich_counters["olx_backlog"]
    rows = (
        db.query(RadarListing)
        .filter(
            RadarListing.user_id == user.id,
            RadarListing.platform == "olx",
            RadarListing.seller_name.is_(None),
        )
        .order_by(RadarListing.found_at.desc())
        .limit(remaining * 4)  # supra-esantionam; unele rowuri n-au id numeric persistat
        .all()
    )
    done = 0
    for row in rows:
        if done >= remaining:
            break
        try:
            extra = json.loads(row.attributes_json) if row.attributes_json else {}
        except Exception:
            extra = {}
        nid = extra.get("olx_numeric_id")
        if not nid:
            continue
        done += 1
        _enrich_counters["olx_backlog"] += 1
        time.sleep(random.uniform(2.0, 4.0))
        try:
            det = fetch_olx_offer_details(nid)
        except Exception:
            det = None
        if not det:
            continue
        if det.get("seller_name"):
            row.seller_name = det["seller_name"]
        if det.get("seller_id"):
            row.seller_id = det["seller_id"]
        if det.get("listed_at"):
            row.listed_at = det["listed_at"]
        if det.get("description") and not row.description:
            row.description = det["description"]
        if det.get("olx_member_since") is not None:
            extra["olx_member_since"] = det["olx_member_since"]
        kw = db.query(RadarKeyword).filter(RadarKeyword.id == row.keyword_id).first()
        risk, reason = compute_seller_risk(
            "olx", row.price, kw.resale_price if kw else None, row.seller_name,
            row.seller_reviews, row.seller_rating, extra,
        )
        row.seller_risk = risk
        if reason:
            extra["risk_reason"] = reason
        else:
            extra.pop("risk_reason", None)
        row.attributes_json = json.dumps(extra, ensure_ascii=False) if extra else None
    try:
        db.commit()
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"OLX backlog commit: {str(exc)[:80]}")
        db.rollback()


def _scan_user(db: Session, user: User) -> dict:
    """Scaneaza toate keyword-urile active ale unui user. Returneaza statistici."""
    stats = {"new_listings": 0, "alerts_sent": 0}
    settings = _get_or_create_settings(db, user.id)
    keywords = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.user_id == user.id, RadarKeyword.is_active == True)
        .all()
    )

    for kw in keywords:
        if _is_keyword_cancelled(kw.id):
            print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters — sare peste.")
            continue
        if not _should_scan_keyword(kw):
            continue

        if not _is_within_active_hours(kw):
            log_manager.emit("radar", "INFO",
                f'Keyword "{kw.name}" — skip (interval orar {kw.active_hours_start:02d}:00–{kw.active_hours_end:02d}:00 inactiv)')
            continue

        if kw.platform:
            platforms = [kw.platform]
        else:
            platforms = _parse_json_list(kw.platforms) or []
        exclude_words = _parse_json_list(kw.exclude_words)
        # RP-2 — engine de excluderi v2 (opt-in). In `advanced`, scraperele NU exclud
        # (liste goale) si filtram centralizat cu check_exclusion dupa intoarcere.
        _adv = (getattr(kw, "exclude_matching_mode", "simple") or "simple") == "advanced"
        _desc_raw = getattr(kw, "exclude_description_words", None)
        _adv_desc = _desc_raw if isinstance(_desc_raw, list) else _parse_json_list(_desc_raw)
        _adv_exceptions = _parse_json_list(getattr(kw, "exclude_exceptions", None))

        cancelled_mid_loop = False
        for idx, platform in enumerate(platforms):
            if _is_keyword_cancelled(kw.id):
                print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters mid-scan — opresc.")
                cancelled_mid_loop = True
                break
            platform = (platform or "").lower()
            if not _platform_enabled_in_settings(platform, settings):
                continue
            if idx > 0:
                time.sleep(random.uniform(*_PLATFORM_DELAY_RANGE))

            log_manager.emit("radar", "SCAN", f'Keyword "{kw.name}" · {platform} · ciclu #{_cycle_counter["n"]}')
            # FlipRadar — RP-3: enrichment doar pe anunturi noi. Setul de external_id
            # deja vazute (per user+platforma) e pasat in search_* ca buclele de
            # enrichment sa sara fetch-urile de detaliu pentru ele.
            _skip_enrich: Optional[set] = None
            if platform in ("okazii", "lajumate", "publi24"):
                _skip_enrich = {
                    ext for (ext,) in db.query(RadarSeenId.external_id)
                    .filter(RadarSeenId.user_id == user.id, RadarSeenId.platform == platform)
                    .all()
                }
            # MODULE 2 — paginare: aduna pagini pana cand una nu mai aduce anunturi
            # noi (necunoscute). Procesarea de mai jos ruleaza pe setul combinat.
            listings = []
            _seen_ext: set = set()
            _page = 1
            while True:
                page_listings = _run_scraper(platform, kw, settings, exclude_words, page=_page, advanced=_adv, db=db, skip_enrich_ids=_skip_enrich)
                # RP-6 — watchdog: rezultate BRUTE (o platforma care returneaza doar
                # anunturi deja vazute e sanatoasa; filtrarea vine dupa).
                health_watchdog.note_results(platform, len(page_listings))
                # RP-2 — filtrare centralizata cu engine-ul v2 (doar in modul advanced).
                # Nota: Vinted NU are descriere in search -> excluderile pe descriere
                # devin efective abia la enrichment (documentat in raport).
                if _adv and page_listings:
                    _kept = []
                    for _r in page_listings:
                        _excl, _rule = check_exclusion(
                            _r.get("title"), _r.get("description"),
                            exclude_words, _adv_desc, _adv_exceptions,
                        )
                        if not _excl:
                            _kept.append(_r)
                    if len(_kept) != len(page_listings):
                        log_manager.emit("radar", "INFO",
                            f"Excluderi v2 ({platform}): {len(page_listings)} → {len(_kept)} după filtrare")
                    page_listings = _kept
                # OLX — filtrare pe subcategorie folosind categoria extrasa din
                # __PRERENDERED_STATE__ (listing["olx_category"]). Safe default in helper.
                if platform == "olx":
                    # subcategoria vine din marketplace_config (wizard); daca lipseste
                    # (keyword old-form), o derivam din slug-ul category (.../telefoane-mobile).
                    _olx_sub = _keyword_subcategory(kw) or _olx_subcategory_from_slug(getattr(kw, "category", None))
                    if _olx_sub and page_listings:
                        _before = len(page_listings)
                        page_listings = [
                            r for r in page_listings
                            if _olx_listing_matches_subcategory(r, _olx_sub)
                        ]
                        if len(page_listings) != _before:
                            log_manager.emit("radar", "INFO",
                                f"OLX subcategorie '{_olx_sub}': {_before} → {len(page_listings)} după filtrare")
                if not page_listings:
                    break
                fresh = [r for r in page_listings
                         if r.get("external_id") and r.get("external_id") not in _seen_ext]
                for r in fresh:
                    _seen_ext.add(r.get("external_id"))
                new_on_page = [r for r in fresh
                               if not _already_seen(db, user.id, platform, r.get("external_id"))]
                listings.extend(fresh)
                log_manager.emit("radar", "INFO",
                    f'{platform} pagina {_page}: {len(page_listings)} găsite · {len(new_on_page)} potențial noi')
                # Facebook deruleaza intern (infinite scroll) si intoarce tot setul
                # intr-un singur apel — nu mai paginam ca sa nu re-derulam degeaba.
                if platform == "facebook":
                    break
                if not new_on_page:
                    break
                _page += 1
                # MODIFICARE 6 — delay aleator proaspăt la fiecare pagină (nu fix).
                time.sleep(_get_platform_delay(platform))
            _new_before = stats["new_listings"]
            for listing in listings:
                if _is_keyword_cancelled(kw.id):
                    print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters — opresc procesarea.")
                    cancelled_mid_loop = True
                    break
                try:
                    ext_id = listing.get("external_id")
                    if not ext_id:
                        continue
                    if _already_seen(db, user.id, platform, ext_id):
                        continue

                    score_data = calculate_score(
                        listing_price=listing.get("price") or 0,
                        resale_price=kw.resale_price,
                        min_margin_pct=kw.min_margin_pct or 10.0,
                        grade_a_min=kw.grade_a_min,
                        grade_b_min=kw.grade_b_min,
                        grade_c_min=kw.grade_c_min,
                    )
                    if score_data["filtered"] and score_data["score"] is None:
                        # marja negativa — nici nu salvam, e zgomot
                        _mark_seen(db, user.id, platform, ext_id)
                        continue

                    _mark_seen(db, user.id, platform, ext_id)

                    # RP-1 — OLX: enrichment inline INAINTE de save+notify (numele
                    # vanzatorului, data exacta, member_since, descrierea -> in alerta si badge).
                    if platform == "olx":
                        _maybe_enrich_olx_inline(listing)
                    # Campuri vanzator + badge de risc (recalculat la enrichment Vinted).
                    _srev, _srat, _srisk, _sattr = _seller_persist_fields(listing, kw)

                    listing_db = RadarListing(
                        user_id=user.id,
                        keyword_id=kw.id,
                        external_id=ext_id,
                        platform=platform,
                        title=listing.get("title", "")[:500],
                        price=float(listing.get("price") or 0),
                        currency=listing.get("currency") or "RON",
                        condition=listing.get("condition"),
                        location=listing.get("location"),
                        url=listing.get("url", ""),
                        images=json.dumps(listing.get("images") or [], ensure_ascii=False),
                        description=listing.get("description"),
                        seller_name=listing.get("seller_name"),
                        seller_id=listing.get("seller_id"),
                        score=score_data["score"],
                        margin_pct=score_data["margin_pct"],
                        status="active",
                        ai_review=None,
                        listed_at=listing.get("listed_at"),
                        seller_reviews=_srev,
                        seller_rating=_srat,
                        seller_risk=_srisk,
                        attributes_json=_sattr,
                    )
                    db.add(listing_db)
                    db.flush()
                    stats["new_listings"] += 1

                    # MODULE 5 — bridge ML: daca titlul matchuieste o categorie
                    # (Apple/BMW), salveaza si in market_listings. Erorile ML nu
                    # trebuie sa rupa niciodata scanul Radar.
                    try:
                        try_save_to_ml(
                            db=db,
                            title=listing.get("title") or "",
                            price=float(listing.get("price") or 0),
                            currency=listing.get("currency") or "RON",
                            external_id=listing.get("external_id") or str(listing_db.id),
                            platform=platform,
                            source_url=listing.get("url") or "",
                            thumbnail_url=(listing.get("images") or [None])[0] or "",
                            description=listing.get("description") or "",
                        )
                    except Exception:
                        pass

                    if score_data["score"] == "A":
                        log_manager.emit("radar", "OK",
                            f'Deal: {listing.get("title","")[:60]} — {int(float(listing.get("price") or 0))} RON · '
                            f'Marjă {int(score_data["margin_pct"] or 0)}% · Grad A')

                    if not score_data["filtered"]:
                        # Discord doar daca keyword-ul are notify_discord activ
                        if getattr(kw, "notify_discord", False):
                            _price = float(listing.get("price") or 0)
                            _resale = float(kw.resale_price or 0)
                            listing_dict = {
                                "title": listing.get("title", ""),
                                "price": listing.get("price"),
                                "currency": listing.get("currency") or "RON",
                                "url": listing.get("url", ""),
                                "image_url": (listing.get("images") or [None])[0] or "",
                                "location": listing.get("location") or "",
                                "platform": listing.get("platform") or platform,
                                "resale_price": int(_resale) if _resale else None,
                                "margin": int(_resale - _price) if (_resale and _price) else None,
                            }
                            queued = send_radar_notification(
                                listing=listing_dict,
                                grade=score_data["score"],
                                score=int(round(score_data.get("margin_pct") or 0)),
                                keyword_name=kw.name,
                                settings=settings,
                                listing_id=str(listing_db.id),
                                db=db,
                            )
                            stats["alerts_sent"] += queued or 0
                            if queued:
                                log_manager.emit("radar", "NOTIF", f"Discord în coadă → {queued} canal(e)")
                        # Email doar daca scor A/B SI keyword-ul are notify_email activ
                        if score_data["score"] in ("A", "B") and getattr(kw, "notify_email", False):
                            _send_email_alert(
                                user, listing, kw,
                                score_data["score"], score_data["margin_pct"],
                                listed_at=listing.get("listed_at"),
                                found_at=listing_db.found_at,
                            )
                        # Web Push pentru deal-uri prioritare (A/B)
                        if score_data["score"] in ("A", "B") and is_push_configured():
                            try:
                                notify_user_push(
                                    db, user.id,
                                    title=f"[{score_data['score']}] {listing.get('title', '')[:50]}",
                                    body=(
                                        f"{int(listing.get('price') or 0)} RON · "
                                        f"Marjă {score_data['margin_pct']:.0f}% · "
                                        f"{platform} · {listing.get('location') or '—'}"
                                    ),
                                    url=f"/dashboard/radar?listing={listing_db.id}",
                                )
                            except Exception as exc:
                                print(f"[RadarScanner] Push esuat: {exc}")
                except Exception as exc:
                    print(f"[RadarScanner] Eroare la procesare listing: {exc}")
                    log_manager.emit("radar", "ERR", f"Eroare {platform}: {str(exc)[:100]}")
                    continue
            _new_count = stats["new_listings"] - _new_before
            log_manager.emit("radar", "OK", f"{platform}: {_new_count} anunțuri noi · {len(listings)} verificate")
            if cancelled_mid_loop:
                break

        # Daca keyword-ul a fost sters in timpul scanarii, nu mai actualizam
        # nimic in DB pentru el — rowul oricum dispare in cateva milisecunde.
        if kw.id in _deleted_keyword_ids:
            _deleted_keyword_ids.discard(kw.id)
            continue
        kw.last_scan_at = datetime.now(timezone.utc)
        db.commit()

    # RP-1 — enrichment in fundal DUPA procesarea keyword-urilor ciclului:
    # Vinted (pagina HTML, seller+atribute) + backlog OLX (rowuri fara vanzator).
    try:
        _enrich_vinted_background(db, user)
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"Vinted enrichment user {user.id}: {str(exc)[:80]}")
        try:
            db.rollback()
        except Exception:
            pass
    try:
        _enrich_olx_backlog(db, user)
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"OLX backlog user {user.id}: {str(exc)[:80]}")
        try:
            db.rollback()
        except Exception:
            pass

    return stats


def run_radar_scan() -> None:
    """Punctul de intrare apelat de APScheduler la fiecare 5 minute."""
    set_log_user(None)  # MON-4 — reset defensiv: thread de pool reutilizat poate mosteni context
    print(f"[RadarScanner] Pornit la {datetime.now().strftime('%H:%M:%S')}")
    db: Session = SessionLocal()
    total_new = 0
    total_alerts = 0
    # RP-1 — reset plafoane de enrichment la inceputul fiecarui ciclu de scan.
    _enrich_counters["olx"] = 0
    _enrich_counters["olx_backlog"] = 0
    _enrich_counters["vinted"] = 0
    # RP-6 — deschide ciclul watchdog-ului (agregam rezultate/erori per platforma).
    health_watchdog.open_cycle()
    try:
        active_user_ids = {
            row[0] for row in db.query(RadarKeyword.user_id)
            .filter(RadarKeyword.is_active == True)
            .distinct().all()
        }
        if not active_user_ids:
            print("[RadarScanner] Niciun user cu keyword-uri active.")
            return

        users = db.query(User).filter(User.id.in_(active_user_ids), User.is_active == True).all()
        for user in users:
            set_log_user(user.id)  # MON-4 — jurnalele emise in _scan_user apartin acestui user
            try:
                stats = _scan_user(db, user)
                total_new += stats["new_listings"]
                total_alerts += stats["alerts_sent"]
            except Exception as exc:
                print(f"[RadarScanner] Eroare la scan user {user.id}: {exc}")
                try:
                    db.rollback()
                except Exception:
                    pass
        set_log_user(None)  # MON-4 — dupa bucla, emit-urile (watchdog etc.) redevin system

        # RP-6 — evaluarea watchdog-ului la finalul ciclului complet.
        try:
            health_watchdog.close_cycle(db)
        except Exception as exc:
            print(f"[RadarScanner] Watchdog esuat: {exc}")

        _cycle_counter["n"] += 1
        if _cycle_counter["n"] % 10 == 0:
            try:
                cleanup_sold_listings(db)
            except Exception as exc:
                print(f"[RadarScanner] Cleanup esuat: {exc}")

        print(f"[RadarScanner] Scan completat: {total_new} listinguri noi, {total_alerts} alerte trimise")
    except Exception as exc:
        print(f"[RadarScanner] EROARE NEASTEPTATA: {exc}")
        import traceback
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
