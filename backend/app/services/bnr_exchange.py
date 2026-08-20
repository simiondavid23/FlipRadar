"""Cursul BNR EUR->RON pentru Radar / Auto / Imobiliare — adaptor subtire.

BNR-1 (2026-08-13): modulul avea propriul fetch + parser + cache, paralel cu
`app.services.currency_service`. Cand feed-ul BNR s-a mutat de pe www.bnr.ro pe
curs.bnr.ro, URL-ul trebuia schimbat in DOUA locuri, iar cele doua module puteau
raspunde diferit la aceeasi intrebare. Implementarea (fetch, parser, cache, lant de
rezerva, persistenta pe disc) e acum unificata in `currency_service`; aici ramane doar
numele, ca cele 11 situri de apel din scoring sa nu se atinga.
"""
from app.services import currency_service


def get_eur_ron() -> float:
    """Cursul EUR -> RON curent. Deleaga catre implementarea unica.

    Deleagarea e prin MODUL, nu `from ... import get_eur_ron_rate`: altfel adaptorul
    ar prinde o referinta proprie la functie, iar delegarea ar fi doar aparenta
    (o schimbare in currency_service n-ar mai fi vazuta aici).
    """
    return currency_service.get_eur_ron_rate()


def get_usd_ron() -> float:
    """Cursul USD -> RON curent. Deleaga catre aceeasi implementare unica (FBS-12).

    USD era deja emis de parserele Facebook si deja suportat de `currency_service`
    (acelasi lant de rezerva, cu fallback static propriu); lipsea doar adaptorul, iar
    filtrele de pret il lasau sa treaca neconvertit.

    Merge prin `get_all_rates()`, nu prin `_get_rate("USD")`: nu exista un
    `get_usd_ron_rate` public, iar un adaptor n-are ce cauta intr-un nume privat al
    altui modul. Costul e o citire in plus pentru EUR, care vine din acelasi cache si
    din acelasi fetch (feed-ul BNR aduce toate ratele deodata).
    """
    return currency_service.get_all_rates()["USD_RON"]
