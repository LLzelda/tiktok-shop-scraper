import os, sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

ENGINE = sa.create_engine(os.getenv("DB_URL"))
Base = declarative_base()

class ProductList(Base):
    __tablename__ = "product_list"
    product_id   = sa.Column(sa.BigInteger, primary_key=True)
    seller_id    = sa.Column(sa.BigInteger, nullable=False)
    title        = sa.Column(sa.Text)
    price_cents  = sa.Column(sa.BigInteger)
    currency     = sa.Column(sa.String(3))
    updated_at   = sa.Column(sa.DateTime(timezone=True),
                             server_default=func.now(), onupdate=func.now())

class ProductDetail(Base):
    __tablename__ = "product_detail"
    product_id   = sa.Column(sa.BigInteger, primary_key=True)
    seller_id    = sa.Column(sa.BigInteger, nullable=False)
    snap_date    = sa.Column(sa.Date, primary_key=True)
    price_cents  = sa.Column(sa.BigInteger)
    currency     = sa.Column(sa.String(3))
    stock        = sa.Column(sa.Integer)

Base.metadata.create_all(ENGINE)
