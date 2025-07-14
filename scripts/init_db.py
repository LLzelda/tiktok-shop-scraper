import os
import sqlalchemy as sa

DB_URL = os.getenv("DB_URL")            # e.g. postgresql+psycopg://tiktok:tiktok@db:5432/tiktok
engine = sa.create_engine(DB_URL, isolation_level="AUTOCOMMIT")

DDL = """
-- 1. seed table (list of product_ids to crawl)
CREATE TABLE IF NOT EXISTS product_seed (
    product_id BIGINT PRIMARY KEY,
    added_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 2. latest snapshot
CREATE TABLE IF NOT EXISTS product_list (
    product_id   BIGINT PRIMARY KEY,
    seller_id    BIGINT NOT NULL,
    title        TEXT,
    price_cents  BIGINT,
    currency     CHAR(3),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 3. daily history
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

