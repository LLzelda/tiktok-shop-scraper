import sqlalchemy as sa
from models import Base, ENGINE

with ENGINE.begin() as cx:
    Base.metadata.create_all(cx)
    cx.execute("""
        CREATE TABLE IF NOT EXISTS seller_seed (
            seller_id BIGINT PRIMARY KEY,
            added_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)