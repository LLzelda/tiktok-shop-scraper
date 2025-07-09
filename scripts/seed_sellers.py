import sys, os, sqlalchemy as sa
from datetime import datetime

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("DB_URL not set"); sys.exit(1)

engine = sa.create_engine(DB_URL)
seller_ids = [int(arg) for arg in sys.argv[1:]]

with engine.begin() as cx:
    for sid in seller_ids:
        cx.execute(
            sa.text("INSERT INTO seller_seed (seller_id) VALUES (:sid) "
                    "ON CONFLICT DO NOTHING"),
            {"sid": sid}
        )
print(f"✅ inserted/kept {len(seller_ids)} seller_id(s) @ {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
