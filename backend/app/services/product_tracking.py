"""MAG-1 — starea de urmarire a produselor, intr-un singur loc.

Pagina „Produse Urmarite” s-a fuzionat cu „Descopera Oportunitati”, deci lista de
produse (`GET /api/products/`) are nevoie de aceleasi trei campuri pe care pana acum
le calcula doar `GET /api/tracked-products/`: starea de monitorizare, pragul de alerta
si ultimele puncte de pret. Doua implementari ale aceluiasi lucru ar fi deviat la
prima schimbare (pragul a MAI migrat o data, din randul de tracking in modelul Alert),
asa ca ambii apelanti trec pe aici.

Totul e in BATCH pe o lista de id-uri — trei interogari indiferent de cate produse
sunt. Varianta naiva (o interogare per produs) ar fi fost N+1 pe o pagina de 100.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.price_history import PriceHistory
from app.models.tracked_product import TrackedProduct

# Cate puncte de pret intra in sparkline. Aceeasi valoare ca inainte de fuziune:
# frontend-ul taie tot la 7, deci a trimite mai multe ar fi trafic irosit.
PUNCTE_ISTORIC = 7


def _puncte(randuri) -> list[dict]:
    """Ultimele `PUNCTE_ISTORIC` puncte, in ordine CRONOLOGICA (cel mai vechi intai) —
    taierea se face la coada, deci ordinea ramasa e cea in care le deseneaza UI-ul."""
    return [
        {"price": float(h.price),
         "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None}
        for h in randuri[-PUNCTE_ISTORIC:]
    ]


def enrich_with_tracking(db: Session, user_id: int,
                         product_ids: Iterable[int]) -> dict[int, dict]:
    """{product_id: {monitoring_active, alert_threshold, price_history}} pentru
    produsele cerute, din perspectiva lui `user_id`.

    Produsele fara rand de tracking NU lipsesc din rezultat: primesc
    `monitoring_active=False`, ca apelantul sa nu fie nevoit sa trateze absenta.
    Istoricul se intoarce insa pentru toate, monitorizate sau nu — sparkline-ul e
    informatie despre produs, nu despre abonament.
    """
    pids = list(dict.fromkeys(int(p) for p in product_ids))   # unic, ordine pastrata
    iesire: dict[int, dict] = {
        pid: {"monitoring_active": False, "alert_threshold": None, "price_history": []}
        for pid in pids
    }
    if not pids:
        return iesire

    for t in (db.query(TrackedProduct)
              .filter(TrackedProduct.user_id == user_id,
                      TrackedProduct.product_id.in_(pids))
              .all()):
        if t.product_id in iesire:
            iesire[t.product_id]["monitoring_active"] = t.monitoring_active

    # Pragul de alerta: ultima alerta price_drop ACTIVA si nedeclansata per produs.
    # Ordonat crescator dupa id -> ultima castiga (acelasi criteriu ca inainte).
    for a in (db.query(Alert)
              .filter(Alert.user_id == user_id,
                      Alert.product_id.in_(pids),
                      Alert.alert_type == "price_drop",
                      Alert.is_active == True,          # noqa: E712 (expresie SQL)
                      Alert.is_triggered == False,      # noqa: E712
                      )
              .order_by(Alert.product_id, Alert.id)
              .all()):
        if a.product_id in iesire:
            iesire[a.product_id]["alert_threshold"] = float(a.target_price)

    # Istoricul: un singur query, grupat in Python. Taierea la 7 se face DUPA grupare,
    # nu in SQL — un LIMIT global ar fi taiat produse intregi, nu cozile fiecaruia.
    pe_produs: dict[int, list] = {}
    for h in (db.query(PriceHistory)
              .filter(PriceHistory.product_id.in_(pids))
              .order_by(PriceHistory.product_id, PriceHistory.recorded_at.asc())
              .all()):
        pe_produs.setdefault(h.product_id, []).append(h)
    for pid, randuri in pe_produs.items():
        if pid in iesire:
            iesire[pid]["price_history"] = _puncte(randuri)

    return iesire
