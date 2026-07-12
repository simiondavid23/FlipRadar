from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Legatura cu articolul de inventar la momentul crearii (GE-6a). Integer simplu, fara
    # FK: articolele se sterg la stoc 0, iar id-ul ramas e markerul ca vanzarea a fost din
    # inventar — necesar la restaurarea stocului.
    inventory_item_id = Column(Integer, nullable=True)
    product_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    quantity = Column(Integer, default=1, nullable=False)
    sale_price = Column(Float, nullable=False)
    currency = Column(String, default="EUR", nullable=False)
    cost_price = Column(Float, nullable=True)
    extra_costs = Column(Float, nullable=True)  # total pe vanzare, in moneda vanzarii (GE-4)
    platform = Column(String, nullable=True)
    buyer = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    sold_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
