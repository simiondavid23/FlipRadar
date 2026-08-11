"""Rezolvarea caii sesiunii Facebook (storage_state Playwright), PER USER.

FB-AUDIT A2+A3: Auto si Imobiliare-Marketplace luau "cel mai recent fisier de pe
disc" — glob("data/facebook_session_*.json") + max pe mtime. Doua bug-uri intr-unul:

  A2 (multi-user): scanul userului B rula pe sesiunea — deci pe CONTUL — userului A
     daca acela se logase mai recent. Exact comportamentul care atrage checkpoint.
  A3 (cale relativa): globul pleca din CWD, in timp ce Radar salveaza sesiunea pe
     RadarSettings.facebook_session_path, cu default in DATA_DIR (PKG-DATA). Cu
     FLIPRADAR_DATA_DIR setat sau in build-ul PyInstaller, Radar vedea "sesiune
     activa" iar Auto/FBM/stats vedeau "sesiune inexistenta" — divergenta tacuta.

Sursa unica de adevar de acum: setarea userului, cu fallback pe calea default a
aceluiasi user. Nicaieri nu se mai alege un fisier dupa mtime.
"""
from typing import Optional


def resolve_facebook_session_path(db, user_id) -> Optional[str]:
    """Calea sesiunii Facebook a userului dat (fisierul poate sa nu existe inca).

    (a) RadarSettings.facebook_session_path, daca userul are setari si calea e setata;
    (b) altfel calea DEFAULT per-user, prin acelasi helper pe care il foloseste Radar
        (DATA_DIR-based, nu CWD-based) — deci Radar si Auto/FBM/stats vad acelasi fisier.
    (c) NU exista fallback pe glob sau pe sesiunea altui user: daca fisierul de la calea
        rezolvata lipseste, validatorii (is_facebook_session_valid / _is_session_valid)
        intorc False si apelantii isi pastreaza comportamentul de "sesiune inexistenta".

    Singurul I/O propriu e query-ul pe RadarSettings; helperul de default face in plus
    un mkdir idempotent pe DATA_DIR/data (comportamentul lui existent, nereimplementat).
    `user_id` lipsa -> None (nu putem alege sesiunea nimanui).
    """
    if not user_id:
        return None

    try:
        from app.models.radar_settings import RadarSettings
        s = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
        if s and s.facebook_session_path:
            return s.facebook_session_path
    except Exception:
        # DB indisponibil / tabel lipsa: cadem pe calea default, NU pe alt user.
        pass

    # Import local: helperul sta in routerul Radar, iar un import de modul la nivel de
    # fisier ar lega serviciile de routere (si ar risca un ciclu).
    from app.routers.radar import _default_facebook_session_path
    return _default_facebook_session_path(user_id)
