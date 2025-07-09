import os, dotenv

dotenv.load_dotenv()

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://tiktok:tiktok@db:5432/tiktok")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
PROXY_POOL = [p.strip() for p in os.getenv("PROXY_POOL", "").split(",") if p.strip()]
SHOP_BATCH_SIZE = int(os.getenv("SHOP_BATCH_SIZE", 5))
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "tiktok_shop_raw")


#no proxy pool
# MAX_REQ_PER_MIN = int(os.getenv("MAX_REQ_PER_MIN", "240"))
# SCROLL_PAGES     = int(os.getenv("SCROLL_PAGES", "8"))
# RANDOM_SLEEP_MIN = float(os.getenv("RANDOM_SLEEP_MIN", "1.0"))
# RANDOM_SLEEP_MAX = float(os.getenv("RANDOM_SLEEP_MAX", "2.5"))