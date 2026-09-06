"""Helperi generici de data pentru scrapere — conversia intre forma ISO de pe site
si cele doua conventii ale proiectului.

Cele doua conventii, stabilite la DATE-1 si nemodificate de atunci:
  * Radar si Auto tin `listed_at` / `refreshed_at` ca datetime NAIV LOCAL. Motivul e
    `_too_old` (RAD-1), care compara `datetime.now()` naiv cu data anuntului: un
    datetime aware ar arunca TypeError acolo. -> `iso_to_naive_local`.
  * Imobiliare emite STRING ISO din scraper si il trece prin `fromisoformat` in
    scanner. -> `normalize_iso`, ca stringul persistat sa aiba mereu aceeasi forma.

OLX-STATE-1: functiile astea au stat pana acum in `utils/olx_state.py`, unde ajunsesera
sa fie importate de Autovit, Storia si `detail.py` (AutoScout24) — module fara nicio
legatura cu OLX. Numele modulului mintea; continutul e neschimbat.
"""
from datetime import datetime
from typing import Optional


def normalize_iso(s) -> Optional[str]:
    """String ISO cu sufix `Z` -> acelasi moment scris `+00:00`; restul, neatins.

    `datetime.fromisoformat` accepta `Z` abia din Python 3.11; normalizarea aici tine
    lantul portabil pe orice versiune din proiect si face ca stringul PERSISTAT de
    Imobiliare sa fie mereu in aceeasi forma. `None`/gol -> `None`.
    """
    if not s:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    if txt[-1] in ("Z", "z"):
        txt = txt[:-1] + "+00:00"
    return txt


def iso_to_naive_local(s) -> Optional[datetime]:
    """String ISO -> datetime NAIV LOCAL (conventia Radar/Auto).

    Aceeasi semantica ca `_naiv_local` din `services/radar/facebook_scraper.py`
    (`astimezone().replace(tzinfo=None)`), dar pornind de la un STRING, nu de la un
    datetime: sursele OLX/Autovit dau text ISO. Corpul e copiat, nu importat, fiindca
    `_naiv_local` e privat intr-un modul Facebook din `services/radar/`, de unde
    `olx_auto`/`autovit` nu au voie sa importe.

    `_too_old` (RAD-1) compara `datetime.now()` naiv cu `listed_at`, deci un datetime
    aware ar arunca TypeError acolo — de aici conversia. Un input deja naiv se intoarce
    neschimbat (e local prin conventie). `None` la lipsa sau la text neparsabil.
    """
    txt = normalize_iso(s)
    if not txt:
        return None
    try:
        dt = datetime.fromisoformat(txt)
    except (TypeError, ValueError):
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt
