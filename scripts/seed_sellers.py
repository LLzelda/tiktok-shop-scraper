import sys, sqlalchemy as sa
from config import DB_URL

def main(seller_id: int):
    eng = sa.create_engine(DB_URL)
    with eng.begin() as cx:
        cx.execute(sa.text("INSERT INTO seller_seed (seller_id) VALUES (:sid) ON CONFLICT DO NOTHING"), {"sid": seller_id})
        print("seeded seller", seller_id)

if __name__ == "__main__":
    main(int(sys.argv[1]))
