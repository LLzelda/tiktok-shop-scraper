"""
seed a few shop IDs into PostgreSQL so the DAG has something to crawl.
"""
import sys, os, sqlalchemy as sa, dotenv

dotenv.load_dotenv()
engine = sa.create_engine(os.getenv("POSTGRES_DSN", "postgresql://tiktok:tiktok@localhost:5432/tiktok"))
with engine.begin() as cx:
    cx.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS shop_seed (
        shop_id BIGINT PRIMARY KEY,
        added_at TIMESTAMP DEFAULT now()
    );
    """))
    for arg in sys.argv[1:]:
        cx.execute(sa.text("INSERT INTO shop_seed (shop_id) VALUES (:s) ON CONFLICT DO NOTHING"), {"s": int(arg)})
print("Seed complete ✨")