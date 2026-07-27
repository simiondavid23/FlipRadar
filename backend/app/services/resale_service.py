"""FASHION-3a — calculul net al unei referinte de revanzare.

Totul e mediat prin RON: e singura moneda in care BNR ne da rate directe, deci
orice conversie cross-valutara (referinta in EUR, taxe fixe in USD) trece prin
ea. Netul NU se stocheaza NICIODATA — se recalculeaza din profilul de taxe
curent, ca o editare a taxelor sa se vada imediat peste tot.

FEZABILITATE AUTO (sonda 3c, 2026-07-26) — de ce referintele raman MANUALE
--------------------------------------------------------------------------
Intrebarea "se pot culege automat preturile de referinta?" a fost masurata, nu
presupusa. Raspunsul e NU pe ambele platforme, din motive DIFERITE:

  StockX — curl e blocat (403). patchright serveste continut, dar sub challenge:
           ce se obtine e partial si fragil, adica exact felul de sursa care
           produce preturi gresite fara sa semnaleze nimic.
  GOAT   — curl intoarce 200 stabil, deci accesul NU e problema. Problema e ca
           SSR-ul livreaza `productTemplate` cu lowestPriceCents,
           newLowestPriceCents si usedLowestPriceCents = 0, iar `offers` = None:
           preturile de piata se hidrateaza printr-un XHR de dupa incarcare, deci
           nu exista in HTML-ul pe care il primim.

Concluzia: `mode='auto'` ramane REZERVAT (campul exista in model tocmai ca o
implementare viitoare sa nu ceara migrare), iar manual-first nu e o etapa
intermediara, ci forma completa a functionalitatii.

Redeschiderea e CONDITIONATA de o sonda noua, nu de o presupunere: daca o
platforma isi schimba servirea, se remasoara si abia apoi se decide (acelasi
tipar ca la flanco.ro in valurile RETAIL).
"""
from sqlalchemy.orm import Session

from app.models.resale_fee_profile import ResaleFeeProfile
from app.models.resale_reference import ResaleReference
from app.services.currency_service import get_all_rates


def _rate_to_ron(currency: str) -> float:
    """Cursul <moneda> -> RON, din get_all_rates (cheile sunt "EUR_RON"/"USD_RON").

    Ridica ValueError pentru o moneda pe care BNR nu ne-o da: mai bine o eroare
    explicita decat un net calculat cu rata 1.0, care ar arata plauzibil.
    """
    cur = (currency or "RON").upper()
    if cur == "RON":
        return 1.0
    rate = (get_all_rates() or {}).get(f"{cur}_RON")
    if not rate:
        raise ValueError(f"Nu am curs valutar pentru {cur} — nu pot calcula netul.")
    return float(rate)


def _to_ron(amount, currency: str) -> float:
    """`amount` exprimat in RON. None -> 0.0 (o taxa nesetata nu scade nimic)."""
    if amount is None:
        return 0.0
    return float(amount) * _rate_to_ron(currency)


def compute_net_ron(ref_price, ref_currency: str, profile) -> float:
    """Cat ramane, in RON, dupa taxele platformei:

        net_ron = to_ron(ref) × (1 − (commission + processing + extra) / 100)
                  − to_ron(fixed_fee + shipping_cost, moneda_profilului)

    Procentele se aplica pe pretul BRUT, iar sumele fixe se scad dupa — ordinea
    platformelor de resale. Taxele fixe se convertesc separat fiindca profilul
    poate fi in alta moneda decat referinta (GOAT in USD peste o referinta EUR).

    `profile` None = profil neconfigurat inca: tratam toate taxele ca zero si
    intoarcem referinta convertita. E o subestimare vizibila (netul == brutul),
    nu o valoare inventata — userul vede imediat ca n-a completat profilul.

    NU rotunjeste: rotunjirea intermediara ar compune eroarea. Vezi `net_in`.
    """
    gross_ron = _to_ron(ref_price, ref_currency)
    if profile is None:
        return gross_ron
    pct = (float(profile.commission_pct or 0.0)
           + float(profile.processing_pct or 0.0)
           + float(profile.extra_pct or 0.0)) / 100.0
    fixed = float(profile.fixed_fee or 0.0) + float(profile.shipping_cost or 0.0)
    return gross_ron * (1.0 - pct) - _to_ron(fixed, profile.currency)


def net_in(net_ron: float, target_currency: str) -> float:
    """Netul din RON in moneda ceruta, rotunjit la 2 zecimale (e o suma de bani,
    singurul loc unde rotunjim)."""
    return round(float(net_ron) / _rate_to_ron(target_currency), 2)


def refresh_product_resale_price(db: Session, product) -> None:
    """Rescrie Product.resale_price din referinta PRIMARA a produsului.

    Asta e tot ce leaga FASHION-3a de restul aplicatiei: `resale_price` alimenta
    deja calculul si filtrarea ROI din listarea de produse, deci referinta se
    "aprinde" acolo fara nicio linie noua de cod in produse.

    Fara referinta primara -> None (produsul iese din filtrarea ROI, corect: nu
    mai avem pe ce baza sa estimam revanzarea).

    NU face commit: apelantul decide granita tranzactiei.
    """
    ref = (
        db.query(ResaleReference)
        .filter(ResaleReference.product_id == product.id,
                ResaleReference.is_primary == True)  # noqa: E712 (SQL, nu Python)
        .first()
    )
    if ref is None:
        product.resale_price = None
        return
    profile = (
        db.query(ResaleFeeProfile)
        .filter(ResaleFeeProfile.user_id == product.user_id,
                ResaleFeeProfile.platform == ref.platform)
        .first()
    )
    net_ron = compute_net_ron(ref.ref_price, ref.ref_currency, profile)
    product.resale_price = net_in(net_ron, product.currency)
