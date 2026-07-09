from sqlalchemy import Column, BigInteger, Integer, Text, DateTime
from datetime import datetime, timezone

from app.database import Base


class VintedCatalog(Base):
    """Arborele de categorii Vinted, reconstruit periodic din pagina /catalog
    (RP-2). `id` = id-ul real Vinted (nu autoincrement). Tabel tranzacțional:
    la refresh se rescrie complet (vezi vinted_catalog_service.refresh_catalog_tree).
    """
    __tablename__ = "vinted_catalogs"

    id = Column(BigInteger, primary_key=True, autoincrement=False)        # id-ul Vinted
    parent_id = Column(BigInteger, nullable=True, index=True)             # None = rădăcină
    title = Column(Text, nullable=False)
    code = Column(Text, nullable=True)
    path = Column(Text, nullable=False)      # ex. "Femei > Îmbrăcăminte > Rochii"
    depth = Column(Integer, nullable=False)  # 0 = rădăcină
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
