"""Enrichment on-demand pentru un anunt: descriere completa + galeria de poze.

Mutat din `fetch_facebook_listing_detail` (radar/facebook_scraper.py), IDENTIC in
afara de doua diferente inevitabile pe calea logat-out:
  · nu mai primeste `session_path` si nu mai verifica valabilitatea sesiunii;
  · nu mai incarca cookie-uri — fetch-ul trece prin clientul cu jar gol.
Restul (descrierea cea mai lunga, galeria cea mai mare, verificarea
login/checkpoint, returul cu None la orice esec) ramane neschimbat.

FB-0 a masurat 20/20 pagini de detaliu servite fara login-wall logat-out, deci
calea e viabila fara cont.
"""
import json

from app.services.log_manager import log_manager

from .parse import SCRIPT_JSON_RE, collect_key, looks_like_login_wall


def fetch_detail(url: str, *, client=None) -> dict:
    """Descrierea si pozele unui anunt Facebook, din pagina de detaliu.

    Cheile exacte au fost confirmate live pe pagina de detaliu (diagnostic Partea A):
      - descriere: cheia 'redacted_description' -> {"text": "<descrierea vanzatorului>"}
      - galerie:   cheia 'listing_photos' -> [{"image": {"uri": "<...fbcdn...>"}}, ...]
    Cautam STRUCTURAL dupa aceste doua chei (nu presupunem calea completa din JSON).

    Returneaza {"description": str|None, "images": [urls]|None}. La orice eroare /
    fetch esuat / login-wall -> {"description": None, "images": None} (fara exceptie).

    `client` e o cusatura de test; in productie ramane None si se creeaza unul implicit.
    """
    if not url:
        return {"description": None, "images": None}
    try:
        if client is None:
            from .client import FacebookClient
            client = FacebookClient()
        html, status = client.get(url)
        if not html or status != 200:
            return {"description": None, "images": None}
        if looks_like_login_wall(html):
            log_manager.emit("radar", "WARN",
                "Facebook detail: login-wall in corp — pagina nu e citibila logat-out")
            return {"description": None, "images": None}

        description = None
        images: list[str] = []
        for block in SCRIPT_JSON_RE.findall(html):
            try:
                data = json.loads(block)
            except Exception:
                continue
            # descriere — pastram cea mai lunga valoare redacted_description.text
            for rd in collect_key(data, "redacted_description"):
                txt = rd.get("text") if isinstance(rd, dict) else rd
                if isinstance(txt, str) and txt.strip():
                    txt = txt.strip()
                    if description is None or len(txt) > len(description):
                        description = txt
            # galerie — pastram cea mai mare lista listing_photos (uri per element)
            for lst in collect_key(data, "listing_photos"):
                if not isinstance(lst, list):
                    continue
                uris = []
                for el in lst:
                    if isinstance(el, dict):
                        uri = (el.get("image") or {}).get("uri")
                        if isinstance(uri, str) and uri:
                            uris.append(uri)
                if len(uris) > len(images):
                    images = uris

        return {"description": description, "images": images or None}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Facebook detail esuat: {str(exc)[:100]}")
        return {"description": None, "images": None}
