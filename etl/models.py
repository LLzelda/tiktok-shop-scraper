from sqlalchemy import (Column, BigInteger, Numeric, Integer, TIMESTAMP, DATE,
                        text, create_engine, String)
from sqlalchemy.orm import declarative_base
import os

Base = declarative_base()

class ProductList(Base):
    """Keeps **latest** state per product. Overwritten on each crawl."""
    __tablename__ = "product_list"

    product_id   = Column(BigInteger, primary_key=True)
    seller_id    = Column(BigInteger, nullable=False)
    shop_id      = Column(BigInteger)                     # nullable
    title        = Column(String(512))
    price_cents  = Column(BigInteger)
    currency     = Column(String(3))
    sold_count   = Column(BigInteger)
    inventory    = Column(Integer)
    rating       = Column(Numeric(3, 2))
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class ProductDetail(Base):
    """Daily snapshot table: (product_id, snapshot_date) PK"""
    __tablename__ = "product_detail"

    product_id     = Column(BigInteger, primary_key=True)
    snapshot_date  = Column(DATE,      primary_key=True)     # yyyy‑mm‑dd at UTC

    seller_id    = Column(BigInteger, nullable=False)
    shop_id      = Column(BigInteger)
    title        = Column(String(512))
    price_cents  = Column(BigInteger)
    currency     = Column(String(3))
    sold_count   = Column(BigInteger)
    inventory    = Column(Integer)
    rating       = Column(Numeric(3, 2))
    scraped_at   = Column(TIMESTAMP(timezone=True), server_default=text("now()"))

# shared engine
ENGINE = create_engine(os.getenv("DB_URL"))