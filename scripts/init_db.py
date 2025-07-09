"""Boot-strap all tables on container start."""
import os, sqlalchemy as sa

DB_URL = os.getenv("DB_URL")
engine = sa.create_engine(DB_URL, isolation_level="AUTOCOMMIT")

DDL = """
CREATE TABLE IF NOT EXISTS seller_seed (
    seller_id  BIGINT PRIMARY KEY,
    added_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_list (
    product_id   BIGINT PRIMARY KEY,
    seller_id    BIGINT NOT NULL,
    title        TEXT,
    price_cents  BIGINT,
    currency     CHAR(3),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_detail (
    product_id   BIGINT,
    seller_id    BIGINT NOT NULL,
    snap_date    DATE,
    price_cents  BIGINT,
    currency     CHAR(3),
    stock        INT,
    PRIMARY KEY (product_id, snap_date)
);
"""

with engine.begin() as cx:
    cx.execute(sa.text(DDL))
print("✅  schema ready")
