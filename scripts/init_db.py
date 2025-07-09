# scripts/init_db.py
import os, sqlalchemy as sa

engine = sa.create_engine(os.getenv("DB_URL"))
with engine.begin() as cx:
    cx.execute("""
      CREATE TABLE IF NOT EXISTS shop_seed (
        shop_id  BIGINT PRIMARY KEY,
        added_at TIMESTAMPTZ DEFAULT NOW()
      )
    """)
