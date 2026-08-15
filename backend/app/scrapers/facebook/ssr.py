"""Calea SSR: pagina de search citita direct, fara GraphQL.

E cea mai simpla cale, dar si cea mai ingusta: FB-0 a masurat ca din 51 de ancore
un SINGUR slug de oras e valid (`bucharest`). Restul sunt ignorate TACUT de
Facebook, care serveste setul implicit — deci o cautare pe un slug nevalidat ar
intoarce anunturi din alt oras, fara niciun semnal de eroare. De-aia treapta asta
se foloseste DOAR pentru ancorele cu `fb_slug` validat, niciodata "sa incercam".
"""
from app.services.log_manager import log_manager

from .parse import iter_listing_objects, looks_like_login_wall

BASE = "https://www.facebook.com"


def cauta_ssr(client, slug: str, query: str) -> list[dict]:
    """Obiectele brute de anunt din pagina SSR. Lista goala la orice esec."""
    if not slug:
        return []
    url = f"{BASE}/marketplace/{slug}/search?query={query}"
    corp, status = client.get(url)
    if status != 200 or not corp:
        log_manager.emit("radar", "WARN",
            f"Facebook SSR: HTTP {status} pe slug-ul '{slug}'")
        return []
    if looks_like_login_wall(corp):
        log_manager.emit("radar", "WARN",
            f"Facebook SSR: login-wall in corp pe slug-ul '{slug}' (HTTP {status})")
        return []
    return iter_listing_objects(corp)
