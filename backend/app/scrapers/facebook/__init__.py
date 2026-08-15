"""Nucleul Facebook Marketplace pe calea LOGAT-OUT (FB-1).

Inert pana la FB-4/FB-5: niciun consumator (Radar, Auto, Imobiliare) nu importa
inca de aici. Calea autentificata existenta din `app/services/radar/facebook_scraper.py`
ramane intacta si va fi aleasa printr-un comutator manual `FB_MOD` la cablare.

Public: doar `search` si `fetch_detail`.
"""
from .client import search
from .detail import fetch_detail

__all__ = ["search", "fetch_detail"]
