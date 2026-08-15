"""Nucleul Facebook Marketplace pe calea LOGAT-OUT (FB-1).

Inert pana la FB-4/FB-5: niciun consumator (Radar, Auto, Imobiliare) nu importa
inca de aici. Calea autentificata existenta din `app/services/radar/facebook_scraper.py`
ramane intacta si va fi aleasa printr-un comutator manual `FB_MOD` la cablare.

Public: `ANCORE` si `selecteaza` (registrul de ancore, FB-2), `Planificator` si
`ConfigPlanificator` (planificatorul pe perechi, FB-3), `search` si `fetch_detail`
(nucleul, FB-1).
"""
from .anchors import ANCORE, selecteaza
from .client import search
from .detail import fetch_detail
from .planner import ConfigPlanificator, Planificator

__all__ = ["ANCORE", "ConfigPlanificator", "Planificator", "selecteaza",
           "search", "fetch_detail"]
