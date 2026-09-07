"""Helperi generici de data pentru scrapere — conversia intre forma ISO de pe site
si cele doua conventii ale proiectului.

Cele doua conventii, stabilite la DATE-1 si nemodificate de atunci:
  * Radar si Auto tin `listed_at` / `refreshed_at` ca datetime NAIV LOCAL. Motivul e
    `_too_old` (RAD-1), care compara `datetime.now()` naiv cu data anuntului: un
    datetime aware ar arunca TypeError acolo. -> `iso_to_naive_bucuresti`.
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
  * `to_naive_bucuresti()` / `din_fus()` — ora DECLARATA de platforma (`listed_at`,
    `refreshed_at`): `FUS_ANUNTURI`, ca „postat 12:54" sa arate ca pe olx.ro.
Pe masina de productie (GTB Standard Time) cele doua dau exact aceeasi valoare.

TZ-2 — regula s-a extins la TOATE coloanele de timp din baza: `acum_local()` peste tot,
`to_naive_bucuresti()` pentru datele DECLARATE de sursa (`listed_at`, `refreshed_at`,
`posted_at`, `auction_date`). Nu mai exista niciun `utcnow()` pe o coloana din baza si
niciun serializator care sa stampileze `Z` (`schemas/_types.py` a disparut).

EXCEPTIILE, singurele locuri unde UTC ramane corect, si de ce:

  A. CONTRACT EXTERN — valoarea e produsa SAU consumata de altcineva decat aplicatia:
     * `utils/auth.py` — `exp` din JWT: il decodeaza biblioteca, dupa RFC;
     * `services/license_service.py` — expirarea cheii de licenta, emisa in afara;
     * `scrapers/facebook/bootstrap.py` — `captured_at`, prospetimea sesiunii FB, si
       `facebook_group_configs.cookies_saved_at`: se judeca fata de ce spune Facebook;
     * `scrapers/facebook/atingere.py` — marcajul `...Z` al aceleiasi sesiuni;
     * `routers/health.py` — raspuns citit de monitorizare, ISO cu offset.

  B. CONTRACT INTERN, subsistemul Facebook (`scrapers/facebook/{executor,planner,
     bazin,parse}.py`, coloanele `fb_scan_state.last_run_at`/`next_due_at` si
     `fb_pool.prima_vedere_at`/`ultima_vedere_at`). Acolo `_acum()` intoarce UTC AWARE,
     naivul din baza INSEAMNA UTC, iar forma orara a traficului se citeste in
     `FUS_LOCAL = Europe/Bucharest`, FIXAT explicit. Motivul e in `planner.py:51-52`:
     „un server in alt fus n-are voie sa schimbe forma traficului catre Facebook".
     E aceeasi specie ca `FUS_ANUNTURI` — o regula ancorata in PIATA, nu in masina —
     deci a urma ceasul sistemului ar fi fost o regresie, nu o uniformizare. Fiecare
     coercitie „naiv inseamna UTC" de acolo poarta un comentariu `TZ-2 — EXCEPTIE`.
     `services/radar/amprenta_ferma.py` citeste canonicul FB, deci intra tot aici.

TZ-3 — CE RULEAZA UNDE, si ce mai are voie sa fixeze un fus.

  CI: suita ruleaza cu `TZ=Europe/Bucharest`, pus in DOUA locuri, deliberat:
  `.github/workflows/ci.yml` (vizibil in log-ul rularii) si `tests/conftest.py`, la NIVEL
  DE MODUL, cu `setdefault` (deci un `TZ=UTC pytest ...` explicit CASTIGA). Fara asta,
  runner-ul GitHub era in UTC si sapte teste care asertau ore ABSOLUTE picau doar acolo —
  o problema de mediu, nu de cod. Pe Windows blocul e no-op (`time.tzset` nu exista);
  CRT-ul citeste `TZ` la pornirea procesului, deci `TZ=UTC` din shell functioneaza si
  acolo, iar suita se poate rula sub alt fus si pe laptop.

  Cele TREI ceasuri, care nu se amesteca NICIODATA intre ele:
    * ceasul NOSTRU  — `acum_local()` scrie, `la_ora_sistemului()` citeste. Fusul MASINII.
      Perechea de citire lipsea pana la TZ-3, si de aici veneau amestecurile: o valoare
      scrisa cu ceasul nostru era citita inapoi cu ceasul PIETEI, adica pe alt ceas.
    * ceasul PIETEI  — `to_naive_bucuresti()` / `din_fus()`. `FUS_ANUNTURI`, Bucuresti FIXAT.
    * ceasul FACEBOOK — `_acum()` din nucleu, UTC aware (exceptia B de mai sus).

  Ce MAI fixeaza un fus, dupa runda, si de ce (lista e EXECUTABILA — `_FUSURI_FIXE_PERMISE`
  din `tests/test_tz_3.py` o verifica pe tot `app/`, deci un al patrulea ceas nu mai poate
  aparea tacit):
    * `FUS_ANUNTURI` de mai jos si `la_ora_sistemului` — mecanismele insele;
    * `scrapers/facebook/planner.py` — `FUS_LOCAL`, exceptia B;
    * `main.py` — `timezone="Europe/Bucharest"` pe scheduler: ORARUL joburilor (cron de
      noapte, mementoul de sesiune FB la 09:00) e ancorat in piata romaneasca, nu in
      masina. Aceeasi specie ca `FUS_ANUNTURI`. De notat asimetria, DELIBERATA si
      documentata: `utils/ore_active.py` judeca fereastra orara a keyword-urilor pe
      `datetime.now()`, adica pe ceasul masinii (decizia FB-7a, pastrata ca atare) —
      cele doua nu schimba valori intre ele, deci nu se pot corupe reciproc;
    * `kleinanzeigen_auto.py` / `auto/listings/detail.py` — `Europe/Berlin` e fusul
      SURSEI, intrarea in `din_fus`, care aterizeaza tot in `FUS_ANUNTURI`;
    * `utils/radar_scanner.py` — `astimezone()` gol pe capatul de SCRIERE al stampilei de
      scanare; citirea o desface cu `la_ora_sistemului`, deci perechea sta pe un ceas.

TZ-3b — NUMELE, si a doua garda.

  `to_naive_local` -> `to_naive_bucuresti`, `iso_to_naive_local` -> `iso_to_naive_bucuresti`
  (52 + 50 de aparitii, 21 de fisiere). Numele vechi mintea exact acolo unde conta: „local"
  se citea „ceasul masinii", cand functia fixeaza `Europe/Bucharest`. TOATE cele patru
  amestecuri reparate la TZ-3 au intrat pe usa aia — cineva avea de citit inapoi o valoare
  scrisa cu `acum_local()` si a ales functia al carei nume suna a pereche. Ca sa se vada de
  ce a fost o capcana, si nu neglijenta: singura diferenta vizibila la locul apelului era
  `to_naive_local` vs `la_ora_sistemului`, si amandoua pareau „ora locala".

  Garda: `_CEAS_PIETEI_PERMIS` din `tests/test_tz_3.py` tine cele doua simboluri pe caile
  de DATA (12 fisiere: scraperele + `routers/auto.py`), enumerate cu motiv, si le interzice
  oriunde altundeva. Registru SEPARAT de `_FUSURI_FIXE_PERMISE`, fiindca listele au fisiere
  diferite si tocmai diferenta e ce se pazeste: `radar_scanner.py` e in primul (are un
  `astimezone()` gol legitim, capatul de scriere al stampilei) si trebuie sa fie in AFARA
  celui de-al doilea. Un apel de ceas al pietei de acolo e prins de patru teste.

  CE GARANTEAZA CE. Testele care aserteaza ore absolute (TZ-1, TZ-2) dovedesc offsetul si
  au nevoie de fusul fixat de conftest. Doar testele de CONSISTENTA din `tests/test_tz_3.py`
  — cele doua capete ale unei conversii pe acelasi ceas — tin conventia independent de
  masina; ele se ruleaza `TZ=UTC pytest tests/test_tz_3.py` ca sa DISCRIMINEZE, fiindca pe
  o masina din Romania cele doua ceasuri sunt acelasi ceas si ar trece si stricate.
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


def la_ora_sistemului(x) -> Optional[datetime]:
    """Un moment AWARE (sau naiv-UTC prin conventie) -> datetime NAIV pe ceasul NOSTRU.

    Perechea de conversie a lui `acum_local()`: acolo unde o valoare a fost scrisa cu
    ceasul sistemului, ea trebuie CITITA tot cu ceasul sistemului. Exista ca functie, si
    nu ca `.astimezone()` imprastiat, ca „fusul local al sistemului" sa aiba UN SINGUR
    mecanism in tot proiectul (TZ-3) — la fel cum `acum_local()` a strans intr-un loc
    toate `datetime.now()`-urile.

    Perechea de confundat e `to_naive_bucuresti`: aia duce la `FUS_ANUNTURI` (Bucuresti
    FIXAT), fiindca acolo traiesc orele DECLARATE de platforme; asta duce la fusul
    MASINII, fiindca acolo traieste ceasul nostru. Pe masina de productie (GTB) cele doua
    dau acelasi rezultat — de aceea amestecul lor a putut sta ascuns pana cand suita a
    rulat pe un runner UTC. Pana la TZ-3b cealalta se numea `to_naive_local`, si CHIAR
    citea ca perechea asteia: cele patru amestecuri reparate la TZ-3 s-au strecurat toate
    pe numele ala. Redenumirea e jumatate din reparatie; cealalta jumatate e garda
    `_CEAS_PIETEI_PERMIS` din `tests/test_tz_3.py`, care tine simbolul pe caile de data.

    Naivul de la intrare se intoarce NESCHIMBAT (contractul e ca un naiv e deja pe
    ceasul nostru), la fel ca la `to_naive_bucuresti`. `None` la lipsa sau tip nesuportat.
    """
    if not isinstance(x, datetime):
        return None
    return x.astimezone().replace(tzinfo=None) if x.tzinfo is not None else x


def to_naive_bucuresti(x) -> Optional[datetime]:
    """Orice moment venit de la o platforma -> datetime NAIV, in ora anunturilor.

    TZ-3b — s-a numit `to_naive_local` pana acum, si numele mintea in singurul fel care
    conta: „local" se citea „ceasul masinii", cand de fapt functia fixeaza
    `Europe/Bucharest`. Toate cele patru amestecuri de fusuri reparate la TZ-3 au intrat
    prin usa aia — cineva avea de citit inapoi o valoare scrisa cu `acum_local()` si a
    ales functia al carei nume suna la fel. Numele nou nu mai lasa loc de citit gresit.

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
        return to_naive_bucuresti(dt_naiv)
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


def iso_to_naive_bucuresti(s) -> Optional[datetime]:
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

    TZ-1 — a devenit un alias subtire peste `to_naive_bucuresti`, care face acelasi lucru
    dar accepta si datetime si epoch. A supravietuit fiindca isi anunta intrarea (un
    STRING ISO) in nume, si fiindca are cinci module consumatoare.

    TZ-3b — redenumit din `iso_to_naive_local` odata cu functia pe care o inveleste,
    pentru acelasi motiv: „local" se citea „ceasul masinii".
    """
    return to_naive_bucuresti(s)
