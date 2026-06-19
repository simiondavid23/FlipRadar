"""Facebook Marketplace — categoria Properties (imobiliare).

Ca si la auto/marketplace, Facebook NU permite cautare anonima — rezultatele cer
o sesiune autentificata. Exista deja un scraper bazat pe sesiune Playwright
(app/services/radar/facebook_scraper.py), insa nu poate fi apelat anonim aici.

TODO: a se conecta la sesiunea Facebook existenta si a aplica filtrele imobiliare:
  listingType=RENT|BUY, propertyType=apartment|house, numBedrooms,
  minPrice, maxPrice, location + radius.
Pana atunci returnam [] (fail-safe), ca agregarea sa continue cu celelalte platforme.
"""


async def search_facebook_real_estate(filters: dict = {}) -> list:
    filters = filters or {}
    print("[facebook_re] indisponibil anonim (necesita sesiune autentificata) — returnez [].")
    return []
