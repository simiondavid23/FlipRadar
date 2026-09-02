"""DEAL-4 — curatenia zilnica a feed-ului de deal-uri.

Patru actiuni, in ordinea de mai jos:

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

  3. D4a — randurile din `shop_price_memory` nevazute de mai mult de
     DEAL_MEMORY_DAYS zile se sterg. Tabela nu era curatata NICIODATA si crestea
     monoton (89.231 de randuri la masuratoare). Pragul e generos deliberat: memoria
     e minimul istoric pe care se sprijina R2, iar stergerea ei nu e neutra — un
     produs fara istoric reintra cu `min_price_vechi = None`, deci prima reaparitie
     ii reseteaza minimul la pretul curent si nu mai poate produce un deal pe R2
     pana nu scade din nou. La trei luni nevazut, referinta e oricum moarta: pretul
     de atunci nu mai spune nimic despre magazinul de azi, iar produsul se comporta
     corect ca unul nou.
  4. D4b — randurile domeniilor SCOASE din registru se sterg din toate cele trei
     tabele. Lectia caliroots (REG-1): domeniul a iesit din `SHOP_REGISTRY`, deci
     scannerul nu mai trece pe el niciodata, deci nimeni nu-i mai scrie `ended_at`
     si nimeni nu-i mai curata memoria — a fost nevoie de curatenie manuala, cu
     serviciul oprit. De acum se face singura.

     `refresh_diff` e EXCLUS din stergere: acolo `shop_domain` vine din `ps.source`,
     care poate sa nu fie deloc un domeniu din registru (un produs urmarit prin link
     de pe orice site). Ar fi fost sters ca „orfan" desi e perfect valid. Se ating
     doar cele trei surse de scanner.

     Promovatele raman, aici ca peste tot: `promoted_product_id` e cheie straina
     spre `products`, iar promovarea e decizia userului, nu o observatie.

Primii doi pasi nu se calca pe picioare: un rand inchis ACUM de garda primeste
`ended_at = acum`, deci nu intra in fereastra de retentie in aceeasi rulare —
isi primeste intreaga luna, ca oricare altul.

Deal-urile PROMOVATE nu se sterg niciodata, din doua motive independente:
`promoted_product_id` e cheie straina spre `products`, deci stergerea ar rupe-o;
si promovarea e o decizie explicita a userului, nu o observatie a aplicatiei.
Filtrul verifica AMANDOUA semnele (`state` si FK-ul), fiindca sunt scrise in
locuri diferite si un rand cu doar unul dintre ele e tocmai cazul dubios pe care
nu vrem sa-l stergem.

`shop_price_memory` se atinge DOAR pe varsta si pe domenii orfane (D4a/D4b),
niciodata pe deal-uri: un produs cu deal incheiat isi pastreaza memoria, altfel
urmatoarea lui reaparitie ar arata ca o scadere din nimic.
"""
import os
from datetime import datetime, timedelta, timezone

from app.models.deal import Deal
from app.models.shop_price_memory import ShopPriceMemory
from app.models.shop_scan_state import ShopScanState
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
DEAL_MEMORY_DAYS = _zile("DEAL_MEMORY_DAYS", 90)

# D4b — sursele scrise de SCANNERE, singurele pentru care `shop_domain` e garantat un
# domeniu din registru. `refresh_diff` lipseste deliberat: vezi docstring-ul.
_SURSE_SCANNER = ("shopify_enum", "listing_scan", "api_enum")


def run_deal_cleanup(db) -> dict:
    """Ruleaza cei patru pasi si intoarce cate randuri a atins fiecare.

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
    prag_memorie = acum - timedelta(days=DEAL_MEMORY_DAYS)

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

        # D4a — memoria de pret prea veche ca sa mai fie o referinta.
        memorie_sterse = (db.query(ShopPriceMemory)
                          .filter(ShopPriceMemory.last_seen_at < prag_memorie)
                          .delete(synchronize_session=False))

        # D4b — domeniile scoase din registru. Importul e AICI, nu la nivel de modul:
        # `shop_registry` nu importa nimic de aici, dar tinandu-l local registrul se
        # citeste la fiecare rulare, deci o schimbare de registru se vede fara
        # repornire — si testele il pot inlocui.
        from app.services.shop_registry import SHOP_REGISTRY

        cunoscute = set(SHOP_REGISTRY)
        orfane = (
            {d for (d,) in db.query(ShopScanState.shop_domain).distinct()}
            | {d for (d,) in db.query(ShopPriceMemory.shop_domain).distinct()}
            | {d for (d,) in db.query(Deal.shop_domain)
               .filter(Deal.deal_source.in_(_SURSE_SCANNER)).distinct()}
        ) - cunoscute

        orfane_deals = orfane_mem = orfane_state = 0
        if orfane:
            # Lista sortata, nu multimea: ordinea parametrilor din `IN` devine
            # determinista, deci si SQL-ul din jurnale e comparabil intre rulari.
            lista = sorted(orfane)
            orfane_deals = (db.query(Deal)
                            .filter(Deal.shop_domain.in_(lista),
                                    Deal.deal_source.in_(_SURSE_SCANNER),
                                    Deal.state != "promovat",
                                    Deal.promoted_product_id.is_(None))
                            .delete(synchronize_session=False))
            orfane_mem = (db.query(ShopPriceMemory)
                          .filter(ShopPriceMemory.shop_domain.in_(lista))
                          .delete(synchronize_session=False))
            orfane_state = (db.query(ShopScanState)
                            .filter(ShopScanState.shop_domain.in_(lista))
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
        f"{sterse} sterse (incheiate >{DEAL_RETENTION_DAYS}z), "
        f"{memorie_sterse} memorie >{DEAL_MEMORY_DAYS}z, "
        f"{orfane_deals}/{orfane_mem}/{orfane_state} orfane "
        f"({', '.join(sorted(orfane)) or '-'})")
    return {"stale_inchise": stale, "sterse": sterse,
            "memorie_sterse": memorie_sterse,
            "orfane_deals": orfane_deals, "orfane_mem": orfane_mem,
            "orfane_state": orfane_state, "orfane": sorted(orfane)}
