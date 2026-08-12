from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint,
)

from app.database import Base


class Deal(Base):
    """SHOP-2a — un chilipir DESCOPERIT de aplicatie pe un magazin Shopify.

    Deliberat separat de Product/ProductSource: alea sunt lucruri pe care userul a
    decis sa le urmareasca, pe cand un deal e o OBSERVATIE a scannerului, care
    apare si dispare singura. Promovarea (`promoted_product_id`) e exact puntea
    dintre cele doua lumi.

    Randurile sunt GLOBALE pe instanta, fara `user_id`: aplicatia se distribuie ca
    instanta locala single-user (acelasi argument ca `api_key` in clar). Setarile
    care le guverneaza (prag, webhook, magazine dezactivate) raman per-user pe
    RadarSettings, ca tot restul.

    Ciclu de viata (D7): nou -> vazut / ignorat / promovat. Disparitia din scan NU
    sterge randul, ci scrie `ended_at` — istoria deal-urilor e informatie de
    arbitraj. Reaparitia unui deal `ignorat` nu il face din nou `nou`.
    """

    __tablename__ = "deals"
    # Ambele coloane sunt NOT NULL, deci constrangerea chiar protejeaza si pe
    # SQLite (unde NULL-urile ar fi considerate distincte intre ele).
    __table_args__ = (UniqueConstraint("shop_domain", "external_id",
                                       name="uq_deals_shop_external"),)

    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(100), nullable=False, index=True)
    external_id = Column(String(64), nullable=False)   # product_id Shopify, ca string
    handle = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False)
    url = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    currency = Column(String(3), nullable=False)
    price = Column(Float, nullable=False)
    compare_at_price = Column(Float, nullable=True)
    # Procentul care a CALIFICAT deal-ul: maximul dintre R1 si R2 la momentul
    # calculului (nu se recalculeaza retroactiv).
    discount_pct = Column(Float, nullable=False)
    reason = Column(String(20), nullable=False)        # compare_at | istoric | ambele
    # D6 — etichetele marimilor in stoc, metadata de card (nu intra in evaluare).
    sizes_available = Column(JSON, default=list)
    # Snapshot informativ din memoria de pret la momentul deal-ului.
    min_price_seen = Column(Float, nullable=True)
    state = Column(String(10), nullable=False, default="nou", index=True)
    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    promoted_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
