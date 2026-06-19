"""Facebook Marketplace — categoria auto (car_truck).

Facebook Marketplace NU permite cautare anonima: rezultatele cer o sesiune
autentificata. In FlipRadar exista deja un scraper bazat pe sesiune Playwright
(app/services/radar/facebook_scraper.py), insa acela depinde de un cookie/sesiune
salvata si nu poate fi apelat anonim ca celelalte scrapere curl_cffi de aici.

TODO: a se conecta la sesiunea Facebook existenta (facebook_auth/facebook_scraper)
si a aplica filtrele auto de mai jos. Pana atunci returnam [] (fail-safe), ca
search-ul agregat sa continue cu celelalte platforme.

Filtre suportate (cand se va activa sesiunea):
  vehicleType=car_truck, minYear, maxYear, minMileage, maxMileage, minPrice, maxPrice
"""


async def search_facebook_auto(query: str, filters: dict = {}) -> list:
    filters = filters or {}
    # Fara sesiune autentificata nu putem accesa Marketplace; nu blocam agregarea.
    print("[facebook_auto] indisponibil anonim (necesita sesiune autentificata) — returnez [].")
    return []
