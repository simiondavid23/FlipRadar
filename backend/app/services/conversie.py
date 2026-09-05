"""CONV-1 — REGULA UNICA de conversie valutara a aplicatiei.

Pana aici, aceeasi regula traia in patru copii, adaugate pe rand (FBS-11, FBS-12, CUR-1,
CUR-2): `radar/base_scraper.pret_comparabil_ron`, `auto_listings_scanner._in_ron`,
`real_estate/scorer._in_eur` si `radar_scanner._price_to_ron`. Copiile n-au divergat inca,
dar fiecare runda de moneda le atingea pe toate — iar una uitata insemna un modul care
citeste 15 000 GBP ca 15 000 RON.

REGULA (hibrida, stabilita la CUR-1 si pastrata identic):
  * RON            — identitate;
  * EUR / USD      — prin adaptorul `bnr_exchange` (cache pe zi, fallback propriu). Cursul
                     se poate PASA (`eur_ron`/`usd_ron`); cand nu e pasat, se cheama prin
                     MODUL — `bnr_exchange.get_eur_ron()` — fiindca asa ramane inlocuibil
                     din teste. Apelantul care are deja cursul scanului il paseaza, ca
                     valoarea sa fie aceeasi peste tot in acel scan.
  * orice alt cod  — din catalogul BNR: `cursuri` cand apelantul il are deja
                     (`currency_service.catalog_ron()`, luat o data pe scan), altfel
                     `currency_service.get_rate_strict(cod)`;
  * necunoscut     — None. NICIODATA 1.0. `_get_rate` are voie sa spuna „1:1" fiindca
                     `convert` prefera o suma nealterata unei exceptii; portile de pret si
                     scorarea NU au voie sa confunde „nu stiu moneda" cu „valoreaza cat un
                     leu" — un anunt de 800 GBP tratat 1:1 trece drept 800 RON si primeste
                     un grad fals.

CELE TREI DECIZII (FBS-11, ale lui David; mutate aici ca sursa unica):
  D1 — EUR si USD se convertesc INAINTE de comparatia cu pragurile; RON trece prin
       identitate. Pragurile raman semantic RON.
  D2 — o moneda pe care n-o stim da None, iar apelantul decide ce face cu asta. Radar e
       PERMISIV (anuntul trece porțile, numarat) fiindca acolo un anunt fara scor nu
       exista in feed; Auto lasa anuntul in feed FARA grad (deci si fara alerta);
       Imobiliare cade pe scorul neutru si pastreaza filtrul tolerant. Politica e a
       APELANTULUI — modulul asta spune doar „nu se poate".
  D3 — daca cursul nu raspunde, tot None: filtrarea nu are voie sa pice fiindca BNR-ul e
       indisponibil. Garda e DEFENSIVA. Distinctia D2/D3 ramane vizibila prin
       `moneda_convertibila` (True + None de la conversie = D3).

CE NU FACE: nu decide politica pe necunoscut, nu logheaza, nu tine stare. Nu importa
nimic din `app.services.radar`, `app.scrapers` sau `app.utils` — importurile de curs sunt
LOCALE, ca modulul sa poata fi importat de oriunde fara cicluri.

APELANTI (toti pastreaza semnaturile lor publice):
  * `radar/base_scraper.pret_comparabil_ron` / `moneda_convertibila` — portile de pret FB;
  * `auto_listings_scanner._in_ron` — scorare + prag de revanzare pe Auto;
  * `real_estate/scorer._in_eur` — scorare + filtru de pret pe Imobiliare;
  * `radar_scanner._price_to_ron` — NU delegheaza: e PURA prin contract (nu atinge
    niciodata reteaua, cursurile se paseaza) si are fail-open cu WARN. Vezi comentariul de
    acolo pentru de ce a ramas separata.
"""
from typing import Optional


def normalizeaza_moneda(moneda) -> str:
    """Codul de moneda, majuscule si fara spatii: „eur ", „EUR", „ Eur" -> „EUR"."""
    return (moneda or "").strip().upper()


def in_ron(valoare, moneda, *, cursuri=None, eur_ron=None, usd_ron=None,
           accepta_text: bool = True, cere_pozitiv: bool = True,
           moneda_implicita: str = "RON") -> Optional[float]:
    """Valoarea adusa in RON, sau None daca nu se poate.

    Cele trei argumente de POLITICA exista fiindca apelantii difera REAL, iar CONV-1 n-a
    avut voie sa le armonizeze tacit (ar fi schimbat comportament in productie):

      accepta_text      — Auto/Imobiliare parseaza `float(valoare)`, deci accepta "100";
                          portile de pret cer un numar adevarat (`isinstance`), fiindca
                          un text acolo inseamna un parser rupt, nu un pret.
      cere_pozitiv      — scorarea refuza 0 si negativele (un pret 0 dadea marja 100% si
                          grad A fals, vezi SCRAPE-AUDIT); portile de pret le lasa sa
                          treaca si le compara cu pragurile, ca azi.
      moneda_implicita  — cand codul lipseste: „RON" pe Auto, „EUR" pe Imobiliare, iar pe
                          portile de pret NIMIC ("") — un anunt fara moneda e D2, nu RON.

    `cursuri` dat (chiar si gol) inseamna „foloseste DOAR catalogul asta"; None inseamna
    „intreaba `currency_service`". Distinctia conteaza: un scan care si-a luat catalogul
    o data nu trebuie sa mai atinga lantul de curs per anunt.
    """
    if accepta_text:
        try:
            v = float(valoare)
        except (TypeError, ValueError):
            return None
    else:
        if not isinstance(valoare, (int, float)):
            return None
        v = float(valoare)
    if cere_pozitiv and v <= 0:
        return None

    cod = normalizeaza_moneda(moneda) or normalizeaza_moneda(moneda_implicita)
    if cod == "RON":
        return v

    if cod in ("EUR", "USD"):
        pasat = eur_ron if cod == "EUR" else usd_ron
        if pasat is not None:
            curs = pasat
        else:
            from app.services import bnr_exchange       # local: fara cicluri
            try:
                curs = (bnr_exchange.get_eur_ron() if cod == "EUR"
                        else bnr_exchange.get_usd_ron())
            except Exception:                           # noqa: BLE001 — D3, orice esec
                return None
    elif cursuri is not None:
        curs = cursuri.get(cod)
    else:
        from app.services import currency_service       # local: acelasi motiv
        try:
            curs = currency_service.get_rate_strict(cod)
        except Exception:                               # noqa: BLE001 — D3
            return None
        if curs is None:
            return None                                 # D2 — nu e in catalogul BNR

    try:
        curs = float(curs or 0)
    except (TypeError, ValueError):
        return None
    return v * curs if curs > 0 else None


def in_eur(valoare, moneda, *, eur_ron, cursuri=None, usd_ron=None,
           moneda_implicita: str = "EUR") -> Optional[float]:
    """Valoarea adusa in EUR, sau None daca nu se poate. Folosit de Imobiliare, unde
    referintele de pret pe metru patrat sunt in EUR.

    EUR e identitate si NU cere `eur_ron` — asa e si azi in `scorer._in_eur`, iar un
    apelant care are doar preturi in EUR nu trebuie sa aiba curs ca sa le foloseasca.
    Pentru orice altceva, drumul e prin RON: `in_ron(...) / eur_ron`, deci aceeasi regula
    unica, aceleasi surse de curs.
    """
    cod = normalizeaza_moneda(moneda) or normalizeaza_moneda(moneda_implicita)
    try:
        v = float(valoare)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if cod == "EUR":
        return v
    try:
        rata = float(eur_ron or 0)
    except (TypeError, ValueError):
        return None
    if rata <= 0:
        return None
    ron = in_ron(v, cod, cursuri=cursuri, eur_ron=rata, usd_ron=usd_ron)
    return None if ron is None else ron / rata


def moneda_convertibila(moneda, *, cursuri=None) -> bool:
    """True daca stim sa aducem moneda in RON.

    Exista ca apelantul sa poata DEOSEBI cele doua motive pentru care conversia intoarce
    None — moneda pe care n-o stim (D2) fata de cursul care n-a raspuns (D3) — fara sa-si
    tina o a doua lista de monede, care ar diverge. Distinctia ramane INTACTA pentru
    EUR/USD (singurele pe care D3 chiar le poate lovi separat); pentru restul catalogului
    cele doua cazuri se confunda, fiindca acolo „curs indisponibil" si „cod necunoscut"
    ies amandoua ca None din `get_rate_strict`.
    """
    cod = normalizeaza_moneda(moneda)
    if cod in ("RON", "EUR", "USD"):
        return True
    if cursuri is not None:
        try:
            return float(cursuri.get(cod) or 0) > 0
        except (TypeError, ValueError):
            return False
    from app.services import currency_service           # local: evita ciclul la import
    try:
        return currency_service.get_rate_strict(cod) is not None
    except Exception:                                   # noqa: BLE001 — la fel ca D3
        return False
