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
