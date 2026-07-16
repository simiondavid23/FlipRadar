from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class TrackedProduct(Base):
    """FlipRadar — Produse Urmarite: model unificat care inlocuieste FavoriteItem
    si WatchlistItem. Un singur rand per (user, produs); `monitoring_active`
    distinge produsul doar salvat de cel monitorizat activ pentru pret.
    Pragul de alerta NU sta aici — traieste in modelul Alert (alert_type=price_drop)."""

    __tablename__ = "tracked_products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_tracked_products_user_product"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    monitoring_active = Column(Boolean, default=False, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="tracked_items")
    product = relationship("Product", back_populates="tracked_items")
