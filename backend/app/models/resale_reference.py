from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class ResaleReference(Base):
    """FASHION-3a — pretul de referinta al unui produs pe o platforma de revanzare,
    optional pe o marime anume.

    Referinta e BRUTA (cat cere piata); netul nu se stocheaza, ci se recalculeaza
    din profilul de taxe curent — altfel o editare a taxelor ar lasa in urma
    valori vechi, imposibil de distins de cele proaspete.

    O singura referinta per produs are `is_primary`: ea alimenteaza
    Product.resale_price (in moneda produsului) si, prin el, filtrarea ROI care
    exista deja in listarea de produse.
    """

    __tablename__ = "resale_references"
    __table_args__ = (
        UniqueConstraint("product_id", "platform", "variant",
                         name="uq_resale_reference_product_platform_variant"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    # CONVENTIA din FASHION-1a: '' = fara varianta (referinta la nivel de produs),
    # NOT NULL DEFAULT '' fiindca in SQLite NULL-urile sunt distincte intr-un
    # UNIQUE, deci un NULL ar permite duplicate pe aceeasi platforma.
    variant = Column(String, nullable=False, default="", server_default="")

    ref_price = Column(Float, nullable=False)
    ref_currency = Column(String, nullable=False, default="EUR")
    source_url = Column(String, nullable=True)
    # "manual" acum; lasa loc unei culegeri automate fara migrare (FASHION-3b+).
    mode = Column(String, nullable=False, default="manual")
    fetched_at = Column(DateTime, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    product = relationship("Product")
