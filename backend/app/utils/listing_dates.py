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
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# HOTFIX CI — fusul in care traiesc anunturile, EXPLICIT. Pana acum conversia se facea
# cu `.astimezone()` fara argument, adica la fusul MASINII: pe laptopul din Romania
# iesea ora corecta, pe runner-ul GitHub Actions (UTC) iesea cu 3 ore mai putin, si
# patru teste care asertau ora absoluta picau doar acolo.
#
# Platformele monitorizate sunt romanesti si emit ore locale (OLX trimite `+03:00`
# vara, `+02:00` iarna), deci momentul afisat trebuie sa fie ora Bucurestiului
# indiferent unde ruleaza procesul. ZoneInfo, nu un offset fix: Romania are DST.
FUS_ANUNTURI = ZoneInfo("Europe/Bucharest")

# FRONT-1 — pragul de la care o reactualizare conteaza. Sub o zi e zgomot, nu semnal:
# pe OLX `lastRefreshTime == createdTime` cand anuntul n-a fost bumpat niciodata, iar pe
# Storia `pushedUpAt` si `createdAtFirst` pot diferi cu o secunda din cauze de sistem.
PRAG_REACTUALIZARE = timedelta(hours=24)


def este_reactualizat(listed_at, refreshed_at, prag: timedelta = PRAG_REACTUALIZARE) -> bool:
    """True daca anuntul a fost REPROMOVAT: `refreshed_at - listed_at >= prag` (24 h).

    Semnalul pe care il marcheaza: un anunt vechi dupa data publicarii, dar reactualizat
    recent, inseamna marfa care nu pleaca — deci loc de negociere. Masurat la DATE-2 pe
    Storia: mediana diferentei 31 de zile, maximul 807.

    Perechea trebuie sa fie COMPARABILA. Cand una dintre date lipseste, nu e datetime,
    sau una e naiva si cealalta aware (conventiile difera per modul: Radar/Auto tin naiv
    local, Imobiliare trece prin `fromisoformat`), raspunsul e False — niciodata exceptie.
    Fara `listed_at` nu stim vechimea, deci nu marcam nimic; `refreshed_at` singur ramane
    afisabil, dar nu declanseaza eticheta.

    Perechea in frontend e `bumpInfo` din components/shared/listingHelpers.js — aceeasi
    regula, aceleasi cazuri, testate pe ambele parti.
    """
    if not isinstance(listed_at, datetime) or not isinstance(refreshed_at, datetime):
        return False
    if (listed_at.tzinfo is None) != (refreshed_at.tzinfo is None):
        return False
    try:
        return (refreshed_at - listed_at) >= prag
    except TypeError:
        return False


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

    HOTFIX CI — conversia se face la `FUS_ANUNTURI` (Europe/Bucharest), EXPLICIT, nu la
    fusul masinii: rezultatul trebuie sa fie acelasi pe laptop si pe runner-ul UTC.
    """
    txt = normalize_iso(s)
    if not txt:
        return None
    try:
        dt = datetime.fromisoformat(txt)
    except (TypeError, ValueError):
        return None
    return dt.astimezone(FUS_ANUNTURI).replace(tzinfo=None) if dt.tzinfo is not None else dt
