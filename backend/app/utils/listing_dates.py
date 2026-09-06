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

TZ-1 — CONVENTIA, pe scurt: in DB toate datetime-urile sunt NAIVE, in ora de perete a
locului unde conteaza, iar conversia se face O SINGURA DATA, LA SCRIERE. Frontend-ul
afiseaza ce primeste, fara sa mai converteasca nimic (un string fara offset e citit de
browser ca ora locala, adica a aceleiasi masini).

Doua ceasuri, deliberat separate:
  * `acum_local()` — ceasul NOSTRU (`found_at`, `log_entries.created_at`, pragurile de
    cleanup/retentie/filtre): ora sistemului pe care ruleaza aplicatia;
  * `to_naive_local()` / `din_fus()` — ora DECLARATA de platforma (`listed_at`,
    `refreshed_at`): `FUS_ANUNTURI`, ca „postat 12:54" sa arate ca pe olx.ro.
Pe masina de productie (GTB Standard Time) cele doua dau exact aceeasi valoare.
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


def acum_local() -> datetime:
    """Acum, ca datetime NAIV in ora sistemului pe care ruleaza aplicatia.

    TZ-1 — ceasul NOSTRU (`found_at`, `log_entries.created_at`, pragurile de cleanup /
    retentie / filtre de data). Pana acum se folosea `datetime.now(timezone.utc)`, iar
    SQLite ii arunca offset-ul si pastra ora de perete UTC: pe un anunt Facebook,
    `found_at` iesea 16:23 in timp ce `listed_at` (deja ora RO) era 16:50, adica „gasit
    cu 27 de minute inainte de a fi postat".

    Exista ca functie, nu ca `datetime.now()` imprastiat, din doua motive: se poate
    mock-ui intr-un singur loc in teste, si se poate cauta cu grep cand cineva se
    intreaba ce ceas foloseste o comparatie.
    """
    return datetime.now()


def to_naive_local(x) -> Optional[datetime]:
    """Orice moment venit de la o platforma -> datetime NAIV, in ora anunturilor.

    Accepta: datetime aware (convertit), datetime naiv (intors NESCHIMBAT — contractul
    e ca naivul e DEJA in ora corecta), string ISO cu sau fara offset (`Z` normalizat),
    epoch int/float. `None` la lipsa, tip nesuportat sau text neparsabil — niciodata
    exceptie.

    TZ-1 / varianta A — tinta e `FUS_ANUNTURI`, nu fusul masinii. Sunt doua ceasuri
    diferite in aplicatie, deliberat:
      * `acum_local()` = ceasul NOSTRU (cand a gasit scanerul anuntul) -> ora masinii;
      * asta = ora DECLARATA de piata (cand a fost postat anuntul) -> ora Romaniei.
    Pe masina de productie (GTB) cele doua coincid bit cu bit. Diferenta apare doar pe
    o masina din alt fus, unde e si corect sa difere: „postat 12:54" trebuie sa arate
    la fel ca pe olx.ro, indiferent de unde te uiti la feed.
    """
    if x is None:
        return None
    if isinstance(x, datetime):
        dt = x
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            return datetime.fromtimestamp(x, tz=FUS_ANUNTURI).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(x, str):
        txt = normalize_iso(x)
        if not txt:
            return None
        try:
            dt = datetime.fromisoformat(txt)
        except (TypeError, ValueError):
            return None
    else:
        return None
    return dt.astimezone(FUS_ANUNTURI).replace(tzinfo=None) if dt.tzinfo is not None else dt


def din_fus(dt_naiv, nume_fus: str) -> Optional[datetime]:
    """Un datetime NAIV citit de pe un site strain -> naiv, in ora anunturilor.

    Kleinanzeigen afiseaza „Heute, 13:25" in ora Germaniei; fara conversie ajungea in
    feed ca 13:25 ora Romaniei, adica o ora in urma vara. `nume_fus` e o cheie IANA
    (`Europe/Berlin`), deci DST-ul fiecarei parti se aplica singur — un offset fix ar fi
    gresit de doua ori pe an, si diferit pentru fiecare pereche de fusuri.

    `None` la lipsa sau la un fus necunoscut (nu oprim un scan pentru asta).
    """
    if not isinstance(dt_naiv, datetime):
        return None
    if dt_naiv.tzinfo is not None:
        return to_naive_local(dt_naiv)
    try:
        sursa = ZoneInfo(nume_fus)
    except Exception:
        return None
    return dt_naiv.replace(tzinfo=sursa).astimezone(FUS_ANUNTURI).replace(tzinfo=None)


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

    TZ-1 — a devenit un alias subtire peste `to_naive_local`, care face acelasi lucru
    dar accepta si datetime si epoch. Numele ramane: are patru consumatori.
    """
    return to_naive_local(s)
