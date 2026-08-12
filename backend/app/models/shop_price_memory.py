from sqlalchemy import Column, DateTime, Float, Index, Integer, String, UniqueConstraint

from app.database import Base


class ShopPriceMemory(Base):
    """SHOP-2a — memoria de pret care alimenteaza referinta R2 (minimul istoric).

    Un rand per produs VAZUT, nu per deal: R2 compara pretul curent cu minimul de
    pana acum, deci are nevoie de memorie pentru TOT catalogul scanat, altfel n-are
    fata de ce compara. Compact prin constructie — fara istoric, doar minimul si
    ultima observatie. Istoricul complet ramane privilegiul produselor promovate in
    tracking (PriceHistory).
    """

    __tablename__ = "shop_price_memory"
    __table_args__ = (
        UniqueConstraint("shop_domain", "external_id", name="uq_shop_price_memory_key"),
        Index("idx_shop_price_memory_key", "shop_domain", "external_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(100), nullable=False)
    external_id = Column(String(64), nullable=False)
    min_price = Column(Float, nullable=False)
    last_price = Column(Float, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
