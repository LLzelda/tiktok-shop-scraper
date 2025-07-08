from sqlalchemy.orm import declarative_base, Mapped, mapped_column
import sqlalchemy as sa, datetime as dt

Base = declarative_base()

class Shop(Base):
    __tablename__ = "shop"
    shop_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    shop_name: Mapped[str | None]
    rating: Mapped[float | None]
    review_count: Mapped[int | None]
    followers: Mapped[int | None]
    scraped_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

class ProductSnapshot(Base):
    __tablename__ = "product_snapshot"
    product_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    shop_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("shop.shop_id"))
    name: Mapped[str | None]
    price: Mapped[float | None]
    currency: Mapped[str | None]
    sold_count: Mapped[int | None]
    stock: Mapped[int | None]
    rating: Mapped[float | None]
    scraped_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)