from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class ShopScanState(Base):
    """SHOP-2a — starea ultimului scan per magazin.

    Alimenteaza panoul de sanatate din SHOP-2b: un magazin care esueaza tacut (tema
    schimbata, enumerare inchisa, blocaj anti-bot) trebuie sa se VADA, nu sa se
    manifeste ca lipsa de deal-uri. Randul se scrie la finalul fiecarui scan de
    magazin, si pe calea de eroare.
    """

    __tablename__ = "shop_scan_state"

    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(100), nullable=False, unique=True)
    last_scan_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)      # ok | partial | error
    products_seen = Column(Integer, default=0)
    deals_active = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
