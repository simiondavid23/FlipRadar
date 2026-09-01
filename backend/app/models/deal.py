from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint,
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
    # DEAL-3 — indexul compus deserveste interogarea principala a paginii:
    # `WHERE ended_at IS NULL ORDER BY discount_pct DESC`. Fara el, EXPLAIN pe
    # productie da `SCAN deals` + `USE TEMP B-TREE FOR ORDER BY` pe 21k randuri
    # active, adica tabela intreaga citita si resortata la fiecare cerere.
    # Ordinea coloanelor conteaza: ended_at filtreaza, discount_pct ordoneaza.
    __table_args__ = (UniqueConstraint("shop_domain", "external_id",
                                       name="uq_deals_shop_external"),
                      Index("ix_deals_ended_discount", "ended_at", "discount_pct"))

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
    # DEAL-1 — de UNDE vine randul. Feed-ul are mai multe surse, iar proveniența
    # trebuie sa fie citibila fara sa ghicesti dupa `reason`:
    #   shopify_enum — scannerul care enumera magazinele Shopify (SHOP-2a)
    #   refresh_diff — o scadere prinsa de refresh-ul surselor urmarite (DEAL-1)
    # viitoare: listing_scan. Default-ul acopera randurile existente, toate ale
    # scannerului; caile care creeaza randuri il seteaza EXPLICIT, ca intentia sa
    # fie scrisa la locul crearii, nu dedusa din default.
    deal_source = Column(String(20), nullable=False, default="shopify_enum")
    # D6 — etichetele marimilor in stoc, metadata de card (nu intra in evaluare).
    sizes_available = Column(JSON, default=list)
    # Snapshot informativ din memoria de pret la momentul deal-ului.
    min_price_seen = Column(Float, nullable=True)
    state = Column(String(10), nullable=False, default="nou", index=True)
    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    promoted_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
