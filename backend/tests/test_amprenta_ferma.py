"""FBS-9a — detectorul de amprenta de ferma, pe fixture-uri EXTRASE DIN DUMP-URI REALE.

Fixture-urile din `fixtures/facebook_ferma/` nu sunt inventate: sunt anunturile parsate
cu `iter_listing_objects` + `canonic` din raspunsurile SSR pastrate de sondele FBS-V1b
si FBS-V2, reduse la cele cinci campuri de care are nevoie detectorul.

`listed_at` e ABSOLUT (momentul crearii anuntului), iar detectorul lucreaza pe diferente
RELATIVE intre anunturile aceluiasi feed — deci fixture-urile pot imbatrani oricat fara
sa strice semnalul de rafala. Nu exista nicio comparatie cu „acum" nici aici, nici in
modul.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.services.radar.amprenta_ferma import (
    MOTIV_PRET, MOTIV_RAFALA, MOTIV_SUFIX, PRAG_CLUSTER,
    are_sufix_gunoi, detecteaza_ferme, titlu_cheie,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "facebook_ferma")
_AWARE = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def _incarca(nume: str) -> list[dict]:
    """Fixture JSON -> dicturi canonice. `listed_at` se intoarce la datetime: modulul
    consuma EXACT ce emite `parse.canonic`, nu siruri — conversia sta aici, la granita,
    nu in detector."""
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        anunturi = json.load(f)
    for c in anunturi:
        c["listed_at"] = (datetime.fromisoformat(c["listed_at"])
                          if c["listed_at"] else None)
    return anunturi


def _fals(ext, titlu, *, pret=1000.0, minute=0):
    """Anunt sintetic, pentru regulile care nu se pot demonstra pe date reale."""
    return {"external_id": str(ext), "title": titlu, "price": pret, "currency": "RON",
            "listed_at": _AWARE + timedelta(minutes=minute)}


# ══════════════════════════════════════════════════════════════════════════════
# 1. `are_sufix_gunoi` — semnalul S1, pe titlul BRUT
# ══════════════════════════════════════════════════════════════════════════════
# Toate cozile DISTINCTE observate in clusterul A din FBS-V2 (zece, nu sapte cum
# spunea rezumatul rundei — lista completa se vede in dump).
_SUFIXE_REALE = ["//-", "-*****", "--=", "==--", "-**/", "--*-/", "==-", "*--",
                 "---***", "=="]


@pytest.mark.parametrize("coada", _SUFIXE_REALE)
def test_sufixele_reale_din_clusterul_a_sunt_gunoi(coada):
    assert are_sufix_gunoi(f"Apple iphone 14promax{coada}") is True


# (titlu, asteptat, de_ce)
_SUFIX_CASES = [
    # Punctuatia NORMALA nu e decoratie — pragul de doua caractere e chiar granita.
    ("iPhone 15 Pro Max Full Box!", False, "un singur `!` e entuziasm, nu decoratie"),
    ("Vand iPhone, ca nou.", False, "un singur `.` la final"),
    ("iPhone 15 Pro Max 256GB -", False, "o singura cratima"),
    ("iPhone 15 Pro Max 256GB", False, "se termina alfanumeric"),
    ("iPhone 17 pro max 512 Go ", False, "spatiu la coada: strip, apoi `o`"),
    # Doua caractere decorative = prag ATINS.
    ("iPhone 15 Pro Max!!", True, "doua semne = pragul e atins"),
    ("Vand iPhone, ca nou...", True,
     "fals-pozitiv ACCEPTAT pe S1: semnalul singur nu condamna, vezi testul de mai jos"),
    # Diacriticele romanesti NU sunt decoratie (`\\w` e unicode-aware).
    ("Canapea extensibila noua", False, "titlu romanesc curat"),
    ("Masina de spalat ca noua", False, "se termina in litera romaneasca"),
    # Marginile.
    ("", False, "titlu gol"),
    (None, False, "titlu None"),
    ("--", True, "titlu format doar din decoratie"),
    ("-", False, "un singur caracter, sub prag"),
]


@pytest.mark.parametrize("titlu,asteptat,de_ce", _SUFIX_CASES)
def test_are_sufix_gunoi(titlu, asteptat, de_ce):
    assert are_sufix_gunoi(titlu) is asteptat, de_ce


# ══════════════════════════════════════════════════════════════════════════════
# 2. `titlu_cheie` — cheia de clustering
# ══════════════════════════════════════════════════════════════════════════════
# (titlu, cheie_asteptata, de_ce)
_CHEIE_CASES = [
    # Rostul cheii: anunturile decorate DIFERIT trebuie sa cada pe aceeasi cheie.
    ("Apple iphone 14promax-*****", "apple iphone 14promax", "sufixul cade"),
    ("Apple iphone 14promax==", "apple iphone 14promax", "alt sufix, aceeasi cheie"),
    ("Apple iphone 14promax", "apple iphone 14promax", "fara sufix, aceeasi cheie"),
    ("iphone 14pro max//-", "iphone 14pro max", "spatiere diferita = ALTA cheie"),
    # Normalizarea e fold-ul productiei.
    ("iPhone15 Pro Max GB", "iphone15 pro max gb", "lowercase"),
    ("Canapea extensibilă bejă", "canapea extensibila beja", "diacritice"),
    ("  iPhone   15   Pro  ", "iphone 15 pro", "spatii colapsate si taiate"),
    # Decoratia de la INCEPUT cade si ea, simetric — asa cad pe aceeasi cheie cele doua
    # variante reale ale clusterului A, cea decorata la coada si cea decorata in fata.
    ("·Apple iphone 14promax", "apple iphone 14promax",
     "middle-dot (U+00B7) la inceput: cade"),
    ("·Apple iphone 14promax==", "apple iphone 14promax",
     "decorat la ambele capete: aceeasi cheie"),
    ("***Canapea extensibila", "canapea extensibila", "mai multe caractere la inceput"),
    # Pragul de la inceput e UNU, spre deosebire de coada unde e doi: niciun titlu real
    # nu incepe cu punctuatie, deci nu exista ce sa rupem dintr-un titlu legitim.
    ("-Canapea extensibila", "canapea extensibila", "un singur caracter la inceput cade"),
    ("Canapea extensibila-", "canapea extensibila-",
     "un singur caracter la COADA ramane: acolo pragul e doi"),
    ("", "", "titlu gol"),
    (None, "", "titlu None"),
]


@pytest.mark.parametrize("titlu,cheie,de_ce", _CHEIE_CASES)
def test_titlu_cheie(titlu, cheie, de_ce):
    assert titlu_cheie(titlu) == cheie, de_ce


# ══════════════════════════════════════════════════════════════════════════════
# 3. Regula in doua jumatati: niciuna nu condamna singura
# ══════════════════════════════════════════════════════════════════════════════
def test_clusterul_singur_nu_condamna():
    """Trei vanzatori care scriu la fel, la ore diferite, cu preturi normale: CURAT."""
    feed = [_fals(1, "Canapea extensibila", minute=0),
            _fals(2, "Canapea extensibila", minute=600),
            _fals(3, "Canapea extensibila", minute=1200)]

    assert detecteaza_ferme(feed) == {}


def test_agravantul_singur_nu_condamna():
    """Doua anunturi decorate, in rafala, la pret aberant — dar sub `PRAG_CLUSTER`."""
    feed = [_fals(1, "Canapea extensibila!!", pret=10.0, minute=0),
            _fals(2, "Canapea extensibila!!", pret=10.0, minute=1),
            _fals(3, "Fotoliu normal", pret=5000.0, minute=2)]

    assert detecteaza_ferme(feed) == {}


def test_cluster_cu_agravant_condamna():
    feed = [_fals(i, "Canapea extensibila--", minute=i) for i in range(PRAG_CLUSTER)]

    ferme = detecteaza_ferme(feed)

    assert len(ferme) == PRAG_CLUSTER
    assert all(MOTIV_SUFIX in m and MOTIV_RAFALA in m for m in ferme.values())


def test_rafala_e_fereastra_glisanta_nu_span_total():
    """O ferma care mai posteaza un anunt peste doua zile nu scapa fiindca a intins
    coada: fereastra se cauta GLISANT, nu pe spanul total al clusterului."""
    feed = [_fals(1, "Canapea extensibila", minute=0),
            _fals(2, "Canapea extensibila", minute=1),
            _fals(3, "Canapea extensibila", minute=2),
            _fals(4, "Canapea extensibila", minute=2880)]

    ferme = detecteaza_ferme(feed)

    assert len(ferme) == 4, "toti membrii clusterului poarta motivul, inclusiv coada"
    assert MOTIV_RAFALA in ferme["1"]


def test_anunturile_fara_pret_sau_data_participa_la_cluster_dar_nu_la_semnal():
    feed = [_fals(1, "Canapea extensibila", minute=0),
            _fals(2, "Canapea extensibila", minute=1),
            dict(_fals(3, "Canapea extensibila"), listed_at=None, price=None)]

    # Doar doua anunturi au data -> sub `PRAG_CLUSTER`, deci rafala NU se aprinde,
    # desi clusterul are trei membri.
    assert detecteaza_ferme(feed) == {}


def test_titlurile_goale_nu_formeaza_cluster():
    feed = [_fals(i, "", minute=i) for i in range(5)]

    assert detecteaza_ferme(feed) == {}


# ══════════════════════════════════════════════════════════════════════════════
# 4. Integrare pe dump-urile reale
# ══════════════════════════════════════════════════════════════════════════════
def test_control_bucuresti_clusterul_b_prins_integral():
    """Clusterul B: 10 anunturi cu titlu IDENTIC, 286-329 RON, rafala de ~29 min.
    Trece de filtrul de cifre din FBS-8 (chiar E modelul cerut), deci asta e singura
    aparare care il vede."""
    feed = _incarca("control_bucuresti.json")
    ferme = detecteaza_ferme(feed)

    b = [c for c in feed if titlu_cheie(c["title"]) == "iphone15 pro max gb"]
    assert len(b) == 10
    assert all(str(c["external_id"]) in ferme for c in b)
    motive = ferme[str(b[0]["external_id"])]
    assert MOTIV_RAFALA in motive and MOTIV_PRET in motive
    assert MOTIV_SUFIX not in motive, "clusterul B nu e decorat — pretul si rafala vorbesc"


def test_control_bucuresti_clusterul_a_prins_cu_sufix_si_rafala():
    """Clusterul A: „14promax" decorat diferit la fiecare anunt, 1204-1588 RON, rafala
    de ~7 min. Preturile stau PESTE mediana feed-ului, deci semnalul de pret tace —
    exact cazul pentru care exista S1 si S3."""
    feed = _incarca("control_bucuresti.json")
    ferme = detecteaza_ferme(feed)

    a = [c for c in feed if "14pro" in titlu_cheie(c["title"])]
    prinse = [c for c in a if str(c["external_id"]) in ferme]
    assert len(a) == 14

    # 14 din 14, DUPA decizia din addendumul FBS-9a: `titlu_cheie` curata decoratia si
    # de la inceputul titlului. Prima versiune curata doar coada si scapa exact cele
    # doua anunturi decorate cu un middle-dot in fata („·Apple iphone 14promax"), care
    # ramaneau pe o cheie proprie de doi membri, sub `PRAG_CLUSTER`. Calibrarea a
    # masurat schimbarea inainte de a fi facuta: 14/14 aici, ZERO fals-pozitive pe
    # setul genuin, si exact doua titluri cu cheia schimbata in toate cele opt dump-uri.
    assert len(prinse) == 14
    assert any(c["title"].startswith("·") for c in prinse), \
        "cele decorate in fata trebuie sa fie printre cele prinse, nu pe langa"

    motive = ferme[str(prinse[0]["external_id"])]
    assert MOTIV_SUFIX in motive and MOTIV_RAFALA in motive
    assert MOTIV_PRET not in motive, "preturile clusterului A sunt langa mediana feedului"


def test_setul_genuin_nu_are_niciun_steag():
    """13 anunturi legitime, stranse din cinci dump-uri V1b/V2 si rulate ca UN feed —
    cazul cel mai sever pentru fals-pozitive, fiindca amestecul creste sansa de cluster."""
    feed = _incarca("genuin.json")

    assert detecteaza_ferme(feed) == {}


def test_ferma_fara_sufix_prinsa_doar_de_rafala():
    """FBS-V1b: 24 de anunturi cu titlu identic, 1400-1491 RON, rafala de 32 min, ZERO
    decoratie. Aici semnalul de pret e ORB prin constructie — cand tot feed-ul e ferma,
    mediana clusterului E mediana feed-ului. Fara rafala, apararea ar fi tacut."""
    feed = _incarca("ferma_fara_sufix.json")
    ferme = detecteaza_ferme(feed)

    assert len(ferme) == len(feed) == 24
    motive = next(iter(ferme.values()))
    assert motive == [MOTIV_RAFALA], f"doar rafala, nu {motive}"


def test_acelasi_titlu_cheie_e_ferma_intr_un_feed_si_genuin_in_altul():
    """Proprietatea care tine genuinul in viata: domeniul e UN feed.

    „iphone 15 pro max 256gb" e cheia a 24 de anunturi de ferma la FBS-V1b SI a unui
    anunt genuin de 1622 RON la FBS-V2/Cluj. Un detector global i-ar strange la un loc
    si l-ar condamna pe cel genuin; separati pe feed, raman separati."""
    ferma = _incarca("ferma_fara_sufix.json")
    genuin = _incarca("genuin.json")

    cheie = "iphone 15 pro max 256gb"
    genuin_cu_cheia = [c for c in genuin if titlu_cheie(c["title"]) == cheie]
    assert len(genuin_cu_cheia) == 1 and genuin_cu_cheia[0]["price"] == 1622.0
    assert all(titlu_cheie(c["title"]) == cheie for c in ferma)

    assert len(detecteaza_ferme(ferma)) == 24
    assert str(genuin_cu_cheia[0]["external_id"]) not in detecteaza_ferme(genuin)


def test_detectorul_nu_se_uita_la_ceas():
    """Fixture-urile imbatranesc; semnalul nu are voie sa se schimbe. Aceleasi anunturi
    mutate cu un an in trecut trebuie sa dea EXACT acelasi rezultat."""
    feed = _incarca("control_bucuresti.json")
    acum = detecteaza_ferme(feed)

    for c in feed:
        if c["listed_at"]:
            c["listed_at"] = c["listed_at"] - timedelta(days=365)

    assert detecteaza_ferme(feed) == acum


def test_intrari_degenerate_nu_arunca():
    assert detecteaza_ferme([]) == {}
    assert detecteaza_ferme(None) == {}
    assert detecteaza_ferme([None, {}, {"title": "fara id"}]) == {}


def test_momente_naive_si_aware_amestecate_nu_arunca():
    """Un feed cu momente amestecate ar ridica TypeError la scadere — adica fix
    intr-un scaner. Naivul se citeste ca UTC."""
    feed = [_fals(1, "Canapea extensibila--", minute=0),
            _fals(2, "Canapea extensibila--", minute=1),
            dict(_fals(3, "Canapea extensibila--"),
                 listed_at=(_AWARE + timedelta(minutes=2)).replace(tzinfo=None))]

    ferme = detecteaza_ferme(feed)

    assert len(ferme) == 3 and MOTIV_RAFALA in ferme["3"]
