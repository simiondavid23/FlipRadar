"""DEAL-4 — curatenia zilnica a feed-ului de deal-uri.

Doua actiuni, in ordinea de mai jos:

  1. garda de stale — un deal activ pe care scannerul nu l-a mai vazut de
     DEAL_STALE_DAYS zile primeste `ended_at`. Inchiderea normala se face DOAR
     la un scan reusit (`_scaneaza_magazin` compara `calificate` cu randurile
     active la finalul magazinului), deci un domeniu care pica — tema schimbata,
     blocaj, retea — isi lasa deal-urile active la nesfarsit. Nu e ipotetic: pe
     01.09 toate cele 21.471 de randuri active aveau `last_seen_at` mai vechi de
     8 zile, fiindca scanul se oprise, iar feed-ul continua sa prezinte preturi
     de acum o saptamana ca fiind de acum.
  2. retentie — deal-urile INCHEIATE de mai mult de DEAL_RETENTION_DAYS zile se
     sterg. Nu se sterg la incheiere fiindca istoricul e informatie de arbitraj
     (D7): un produs care a mai fost la -40% acum trei saptamani spune ceva
     despre cat de des scade. Dupa o luna nu mai spune destul cat sa merite
     randul.

Cele doua nu se calca pe picioare: un rand inchis ACUM de garda primeste
`ended_at = acum`, deci nu intra in fereastra de retentie in aceeasi rulare —
isi primeste intreaga luna, ca oricare altul.

Deal-urile PROMOVATE nu se sterg niciodata, din doua motive independente:
`promoted_product_id` e cheie straina spre `products`, deci stergerea ar rupe-o;
si promovarea e o decizie explicita a userului, nu o observatie a aplicatiei.
Filtrul verifica AMANDOUA semnele (`state` si FK-ul), fiindca sunt scrise in
locuri diferite si un rand cu doar unul dintre ele e tocmai cazul dubios pe care
nu vrem sa-l stergem.

`shop_price_memory` NU se atinge (D4, amanat): e memoria minimului istoric pe
care se sprijina regula R2, iar taierea ei ar INVENTA deal-uri — un produs fara
istoric intra cu `min_price_vechi = None`, deci prima reaparitie ii reseteaza
minimul la pretul curent.
"""
import os
from datetime import datetime, timedelta, timezone

from app.models.deal import Deal
from app.services.log_manager import log_manager


def _zile(nume: str, implicit: int) -> int:
    """Numar de zile din mediu, cu plasa. O valoare nenumerica sau <= 0 ar sterge
    exact ce trebuia pastrat (un prag de 0 zile inseamna „tot"), deci cade pe
    implicit si o spune tare la pornire, nu in tacere."""
    brut = os.getenv(nume)
    if brut is None or not str(brut).strip():
        return implicit
    try:
        valoare = int(str(brut).strip())
    except (TypeError, ValueError):
        print(f"[DealCleanup] {nume}={brut!r} nu e numar intreg — folosesc {implicit}.")
        return implicit
    if valoare <= 0:
        print(f"[DealCleanup] {nume}={valoare} nu e pozitiv — folosesc {implicit}.")
        return implicit
    return valoare


# D3 si D2 — pragurile aprobate, citite la import ca restul constantelor de mediu.
DEAL_STALE_DAYS = _zile("DEAL_STALE_DAYS", 3)
DEAL_RETENTION_DAYS = _zile("DEAL_RETENTION_DAYS", 30)


def run_deal_cleanup(db) -> dict:
    """Ruleaza cele doua actiuni si intoarce cate randuri a atins fiecare.

    Doua instructiuni in masa (UPDATE + DELETE) intr-o singura tranzactie scurta,
    nu un obiect ORM per rand: pe 21k randuri active, materializarea ar costa
    exact ce a eliminat DEAL-3, iar lock-ul de scriere SQLite s-ar tine minute
    intregi — lectia din DEAL-SCAN-1.

    O exceptie face rollback si pleaca mai departe: apelantul din `main.py` o
    prinde si o scrie in consola, iar jobul urmator reincearca. Curatenia care
    esueaza pe jumatate ar fi mai rea decat una care nu ruleaza deloc.
    """
    acum = datetime.now(timezone.utc)
    prag_stale = acum - timedelta(days=DEAL_STALE_DAYS)
    prag_retentie = acum - timedelta(days=DEAL_RETENTION_DAYS)

    try:
        stale = (db.query(Deal)
                 .filter(Deal.ended_at.is_(None),
                         Deal.last_seen_at < prag_stale)
                 .update({Deal.ended_at: acum}, synchronize_session=False))
        sterse = (db.query(Deal)
                  .filter(Deal.ended_at.isnot(None),
                          Deal.ended_at < prag_retentie,
                          Deal.state != "promovat",
                          Deal.promoted_product_id.is_(None))
                  .delete(synchronize_session=False))
        db.commit()
    except Exception as exc:                        # noqa: BLE001
        db.rollback()
        log_manager.emit(
            "catalog", "WARN",
            f"Deal cleanup esuat: {type(exc).__name__}: {str(exc)[:160]}")
        raise

    log_manager.emit(
        "catalog", "OK",
        f"Deal cleanup: {stale} inchise (stale >{DEAL_STALE_DAYS}z), "
        f"{sterse} sterse (incheiate >{DEAL_RETENTION_DAYS}z)")
    return {"stale_inchise": stale, "sterse": sterse}
