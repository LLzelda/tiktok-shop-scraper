import sys, os, sqlalchemy as sa
from datetime import datetime

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("DB_URL not set"); sys.exit(1)

engine = sa.create_engine(DB_URL)
product_ids = [int(arg) for arg in sys.argv[1:]]

if not product_ids:
    print("⚠️  provide at least one product_id"); sys.exit(1)

with engine.begin() as cx:
    for pid in product_ids:
        cx.execute(
            sa.text("INSERT INTO product_seed (product_id) VALUES (:pid) "
                    "ON CONFLICT DO NOTHING"),
            {"pid": pid}
        )

print(f"✅ inserted/kept {len(product_ids)} product_id(s) "
      f"@ {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
