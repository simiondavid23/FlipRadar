# FlipRadar — model pentru anunturi reale de piata (date istorice de vanzari),
# folosit la injectarea contextului de piata in analiza AB a Consilierului AI.
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, JSON, Index
from datetime import datetime
from app.database import Base


class MarketListing(Base):
    __tablename__ = "market_listings"

    # FlipRadar — index compus pentru queries ML (agregari pe categorie/brand,
    # filtrate dupa starea de vanzare).
    __table_args__ = (
        Index("ix_market_listings_category_brand_sold", "category", "brand", "sold_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100))
    brand = Column(String(100))
    platform = Column(String(50))
    external_id = Column(String(200), nullable=True)
    title = Column(Text)
    features = Column(JSON, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(10), default="EUR")
    listed_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    sold_at = Column(DateTime, nullable=True)
    days_to_sell = Column(Integer, nullable=True)
    source_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
