"""Amprenta de ferma — detector PUR de anunturi produse in serie (FBS-9a).

DE UNDE VINE. FBS-V2 a masurat un feed de control pe Bucuresti in care 24 din 24 de
sloturi erau ocupate de doua ferme de tepe, iar apararile existente tac pe amandoua:

  * Clusterul A — 14 anunturi „Apple iphone 14promax" cu sufixe-gunoi diferite
    (`//-`, `==--`, `-*****`, `--=`, `**/`, `---***`, `*--`), 1204-1588 RON, rafala de
    ~7 minute. Preturile stau APROAPE de mediana feed-ului, deci filtrul de pret tace;
    vorbesc sufixele si rafala. Sufixele nu ocolesc excluderile noastre — ocolesc
    dedup-ul Facebook, care altfel ar strange 14 anunturi identice intr-unul.
  * Clusterul B — 10 anunturi cu titlul IDENTIC „iPhone15 Pro Max GB", 286-329 RON,
    rafala de ~29 minute. Fara sufixe; vorbesc pretul aberant si rafala. Trece si de
    filtrul de cifre din FBS-8, fiindca CHIAR e modelul cerut.

REGULA, in doua jumatati care nu se pot inlocui una pe alta:
  * clusterul singur NU condamna — trei vanzatori care scriu la fel nu sunt o ferma;
  * agravantul singur NU condamna — un titlu cu „!!" la coada e doar entuziasm.
Condamna doar clusterul CU cel putin un agravant.

DOMENIUL E UN SINGUR FEED, deliberat. Detectorul primeste anunturile UNEI cereri si
nu vede nimic dincolo de ele. Nu e o limitare de implementare, e ce tine genuinul in
viata: „iPhone 15 Pro Max 256GB" la 1400-1491 RON e o ferma masurata (FBS-V1b, 24 de
anunturi intr-o rafala de 32 min), iar „IPHONE 15 PRO MAX 256GB" la 1622 RON e un
anunt genuin (FBS-V2, Cluj) — au acelasi titlu-cheie si i-ar strange la un loc orice
detector global. Separati de feed, raman separati.

FARA CEAS: nicio comparatie cu „acum" in tot modulul. Rafala se masoara in diferente
RELATIVE intre anunturile aceluiasi feed, deci fixture-urile pot imbatrani oricat fara
sa strice semnalul.

Functii PURE: fara DB, fara mediu, fara retea. Singura dependinta din `radar` e
`normalize` — fold-ul PRODUCTIEI, refolosit ca sa nu existe o a doua normalizare
tinuta sincronizata cu atentie. `exclusion_engine` nu importa nimic din `radar`, deci
importul nu poate crea ciclu.
"""
import re
from datetime import timedelta, timezone

from app.services.radar.exclusion_engine import normalize

# ── praguri ──────────────────────────────────────────────────────────────────
# Valorile initiale sunt cele aprobate la FBS-9a si CALIBRATE offline pe dump-urile
# reale V1b/V2. Marjele masurate sunt largi (vezi raportul rundei): cea mai stransa
# fereastra de rafala observata la o ferma reala e de ordinul secundelor fata de
# pragul de 45 de minute, iar clusterul cu pret aberant sta la 0.23 din mediana
# feed-ului fata de pragul de 0.5.
PRAG_CLUSTER = 3              # cate anunturi cu acelasi titlu-cheie fac un cluster
FEREASTRA_RAFALA_MIN = 45     # minute; fereastra in care PRAG_CLUSTER anunturi = rafala
FRACTIE_PRET = 0.5            # sub cat din mediana feed-ului e „pret aberant"
PRAG_SUFIX_GUNOI = 2          # cate caractere decorative la coada fac un sufix-gunoi

MOTIV_SUFIX = "cluster+sufix"
MOTIV_RAFALA = "cluster+rafala"
MOTIV_PRET = "cluster+pret"

# Coada de caractere care nu sunt nici alfanumerice, nici spatii. `\w` e unicode-aware
# in Python 3, deci literele romanesti („noua", „masina") NU intra aici — un titlu care
# se termina in „a" nu e decorat. Underscore-ul conteaza ca litera, deliberat: nu e
# decoratie de ferma in niciun exemplu masurat, iar varianta conservatoare e sa nu-l
# numeri.
_SUFIX_GUNOI = re.compile(r"[^\w\s]{%d,}$" % PRAG_SUFIX_GUNOI)
# Decoratia de la AMBELE margini, pentru cheia de clustering. Pragurile difera
# deliberat, si asimetria e sustinuta de masuratoare, nu de gust:
#   * la COADA e nevoie de doua caractere, fiindca unul singur e punctuatie obisnuita
#     („Full Box!", „ca nou.") si l-am rupe din titluri legitime;
#   * la INCEPUT e de ajuns unul, fiindca niciun titlu real nu incepe cu punctuatie.
# Calibrarea FBS-9a a verificat exact asta pe cele 8 dump-uri: un singur caracter la
# inceput schimba cheia a DOUA titluri in total, ambele din clusterul A („·Apple
# iphone 14promax", U+00B7), si ZERO din setul genuin.
_DECOR_MARGINI = re.compile(r"^[^\w\s]+|[^\w\s]{%d,}$" % PRAG_SUFIX_GUNOI)
_SPATII = re.compile(r"\s+")


# ── componente pure ──────────────────────────────────────────────────────────
def are_sufix_gunoi(title) -> bool:
    """True daca titlul BRUT se termina in cel putin `PRAG_SUFIX_GUNOI` caractere
    decorative (nici alfanumerice, nici spatii), dupa strip de spatii.

    Se lucreaza pe titlul BRUT, nu pe cel normalizat: `normalize` pastreaza punctuatia,
    dar cheia de clustering o ARUNCA, iar semnalul are nevoie tocmai de ea.

    Pragul de DOUA caractere e ce separa decoratia de punctuatia normala: „Full Box!"
    si „ca nou." raman curate. Un „ca nou..." iese semnalat — dar semnalul singur nu
    condamna, deci costul e zero pana cand titlul ala apare de trei ori in acelasi feed.
    """
    t = (title or "").strip()
    return bool(t) and _SUFIX_GUNOI.search(t) is not None


def titlu_cheie(title) -> str:
    """Cheia de clustering: normalize + curatarea decoratiei de la AMBELE margini +
    colapsarea spatiilor.

    Decoratia cade ca sa se stranga la un loc anunturile pe care ferma le-a decorat
    DIFERIT tocmai ca sa nu se stranga: `...14promax-*****`, `...14promax==` si
    `·Apple iphone 14promax` sunt acelasi anunt scris de trei ori.

    Ambele margini, nu doar coada: prima versiune curata doar sufixul, iar calibrarea
    FBS-9a a masurat ca asa scapau exact doua anunturi din clusterul A, decorate cu un
    middle-dot la INCEPUT. Curatarea simetrica le aduce inapoi (14/14) fara niciun
    fals-pozitiv pe setul genuin — vezi `_DECOR_MARGINI` pentru pragurile diferite.

    S1 (`are_sufix_gunoi`) ramane pe COADA, neschimbat: cheia si semnalul sunt lucruri
    diferite. Cheia strange serii; semnalul spune ca seria e decorata.
    """
    t = _DECOR_MARGINI.sub("", normalize(title).strip())
    return _SPATII.sub(" ", t).strip()


def _pret(c):
    """Pretul, doar daca e un numar strict pozitiv. MONEDA E IGNORATA, limita asumata:
    pe un feed cu monede amestecate mediana ar fi fara sens. Feed-urile masurate sunt
    integral RON; daca asta se schimba, semnalul de pret are nevoie de normalizare."""
    p = c.get("price")
    return float(p) if isinstance(p, (int, float)) and p > 0 else None


def _moment(c):
    """`listed_at` ca datetime comparabil. Naivul se citeste ca UTC — altfel un feed cu
    momente amestecate ar ridica TypeError la scadere, adica exact intr-un scaner."""
    la = c.get("listed_at")
    if la is None or not hasattr(la, "tzinfo"):
        return None
    return la.replace(tzinfo=timezone.utc) if la.tzinfo is None else la


def _mediana(valori):
    v = sorted(x for x in valori if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2.0


def _e_rafala(membri) -> bool:
    """True daca `PRAG_CLUSTER` membri incap intr-o fereastra de `FEREASTRA_RAFALA_MIN`.

    Fereastra e GLISANTA peste momentele sortate, nu spanul total al clusterului: o
    ferma care mai posteaza un anunt peste doua zile nu trebuie sa scape fiindca a
    intins coada. Anunturile fara `listed_at` participa la cluster, dar nu la semnal.
    """
    momente = sorted(m for m in (_moment(c) for c in membri) if m is not None)
    if len(momente) < PRAG_CLUSTER:
        return False
    limita = timedelta(minutes=FEREASTRA_RAFALA_MIN)
    return any(momente[i + PRAG_CLUSTER - 1] - momente[i] <= limita
               for i in range(len(momente) - PRAG_CLUSTER + 1))


def _pret_aberant(membri, mediana_feed) -> bool:
    """True daca mediana clusterului e sub `FRACTIE_PRET` din mediana feed-ului.

    Se compara MEDIANE, nu minime: o ferma isi imprastie preturile pe cateva zeci de
    lei (1204-1588 la clusterul A), iar un minim ar fi la mila unui singur anunt.
    Anunturile fara pret pozitiv participa la cluster, dar nu la semnal.
    """
    if not mediana_feed or mediana_feed <= 0:
        return False
    mediana_cluster = _mediana([_pret(c) for c in membri])
    if mediana_cluster is None:
        return False
    return mediana_cluster < FRACTIE_PRET * mediana_feed


# ── functia principala ───────────────────────────────────────────────────────
def detecteaza_ferme(canonice) -> dict:
    """Anunturile de ferma dintr-UN feed: `{external_id: [motive]}`.

    Cheile sunt DOAR anunturile semnalate — cele curate lipsesc din dict, deci
    `len(rezultat)` e direct numarul de semnalari, iar `rezultat.get(ext, [])` da lista
    goala pentru un anunt curat. Motivele sunt de CLUSTER, nu per anunt: daca un
    cluster a castigat `cluster+sufix`, il poarta toti membrii lui, inclusiv cei fara
    sufix — ei sunt aceeasi serie, iar decoratia diferita e chiar metoda.

    `canonice` sunt dicturile emise de `parse.canonic` (`listed_at` = datetime).
    """
    anunturi = [c for c in (canonice or []) if c and c.get("external_id")]
    mediana_feed = _mediana([_pret(c) for c in anunturi])

    grupuri: dict[str, list] = {}
    for c in anunturi:
        cheie = titlu_cheie(c.get("title"))
        if cheie:                        # titlurile goale nu se aduna intr-un cluster
            grupuri.setdefault(cheie, []).append(c)

    ferme: dict[str, list[str]] = {}
    for membri in grupuri.values():
        if len(membri) < PRAG_CLUSTER:
            continue
        motive = []
        if any(are_sufix_gunoi(c.get("title")) for c in membri):
            motive.append(MOTIV_SUFIX)
        if _e_rafala(membri):
            motive.append(MOTIV_RAFALA)
        if _pret_aberant(membri, mediana_feed):
            motive.append(MOTIV_PRET)
        if not motive:                   # cluster curat: clusterul singur nu condamna
            continue
        for c in membri:
            ferme[str(c["external_id"])] = list(motive)
    return ferme
