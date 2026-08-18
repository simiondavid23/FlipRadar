"""FBS-5 — citirea si normalizarea lui `FB_MOD`, o singura data pentru toti trei.

DE CE S-A REDENUMIT `logout` IN `nucleu`: valoarea trimitea la nucleul FB-1, iar
nucleul e AUTENTIFICAT din FBS-1 — incarca `FB_SESIUNE_PATH` si trimite corp cu
identitate. Cine citeste configuratia peste luni si vede `FB_MOD=logout` crede ca a
OPRIT sesiunea, cand de fapt a pornit-o. Numele descria ceva ce nu mai e adevarat.

`logout` ramane ALIAS acceptat, cu WARN: o configuratie existenta nu are voie sa se
rupa la un redeploy, dar nici sa ramana tacut inselatoare.

Valorile:
  sesiune  (implicit)  calea veche, per-utilizator, scrapeaza la cerere
  nucleu               nucleul FBS-1/FBS-2 — SSR-pe-ID, cu sesiunea de infrastructura
  bazin                citeste din `fb_pool`, ZERO retea
"""
import os

from app.services.log_manager import log_manager

MODURI = ("sesiune", "nucleu", "bazin")
_ALIASURI = {"logout": "nucleu"}


def mod_fb(modul_log: str = "radar") -> str:
    """`FB_MOD` normalizat. Necunoscutul se intoarce ca atare — dispecerul fiecarui
    consumator decide ce face cu el (azi: WARN + calea de sesiune)."""
    brut = (os.getenv("FB_MOD") or "sesiune").strip().lower()
    if brut in _ALIASURI:
        nou = _ALIASURI[brut]
        log_manager.emit(modul_log, "WARN",
            f"Facebook: FB_MOD='{brut}' e un nume INVECHIT — nucleul e autentificat "
            f"din FBS-1 (incarca FB_SESIUNE_PATH), deci 'logout' descrie ceva ce nu "
            f"mai e adevarat. Foloseste '{nou}'; aliasul merge in continuare.")
        return nou
    return brut
