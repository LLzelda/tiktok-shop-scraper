import os

DB_URL            = os.getenv("DB_URL")
#PROXY_POOL  = [p for p in os.getenv("PROXY_POOL", "").split(",") if p]
MAX_REQ_PER_MIN   = int(os.getenv("MAX_REQ_PER_MIN", "240"))
SCROLL_PAGES      = int(os.getenv("SCROLL_PAGES", "8"))
RANDOM_SLEEP_MIN  = float(os.getenv("RANDOM_SLEEP_MIN", "1"))
RANDOM_SLEEP_MAX  = float(os.getenv("RANDOM_SLEEP_MAX", "2.5"))
KAFKA_TOPIC = "tiktok_raw"
# we seed by seller only
SEED_TABLE = "seller_seed"
