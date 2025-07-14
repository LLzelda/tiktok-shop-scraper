import asyncio, json, logging, datetime as dt
from decimal import Decimal
from typing import Optional

from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel, Field, ValidationError, validator
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from etl.models import ENGINE, ProductList, ProductDetail
from tiktok_scraper.config import DB_URL, KAFKA_BOOTSTRAP, KAFKA_TOPIC

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("etl")


#pydantic schema 
class ProductSchema(BaseModel):
    product_id: int
    seller_id:  int
    price:      str | float | Decimal
    currency:   str = "USD"
    snapshot_ts: Optional[str] = None

    @validator("snapshot_ts", pre=True, always=True)
    def default_ts(cls, v):
        return v or dt.datetime.utcnow().isoformat()

# Helpers
def price_to_cents(p) -> int:
    return int(Decimal(p) * 100)

async def save(record: ProductSchema):
    snap_dt   = dt.datetime.fromisoformat(record.snapshot_ts)
    price_c   = price_to_cents(record.price)
    today     = snap_dt.date()

    with ENGINE.begin() as cx:
        # upsert latest
        stmt = insert(ProductList).values(
            product_id  = record.product_id,
            seller_id   = record.seller_id,
            price_cents = price_c,
            currency    = record.currency,
            updated_at  = snap_dt,
        ).on_conflict_do_update(
            index_elements=[ProductList.product_id],
            set_={
                "price_cents": price_c,
                "currency":    record.currency,
                "updated_at":  snap_dt
            }
        )
        cx.execute(stmt)

        # insert daily snapshot (ignore duplicates)
        stmt = insert(ProductDetail).values(
            product_id  = record.product_id,
            seller_id   = record.seller_id,
            snap_date   = today,
            price_cents = price_c,
            currency    = record.currency,
            stock       = None
        ).on_conflict_do_nothing()
        cx.execute(stmt)

# ──────────────────────────────────────────────────────────────────────────────
# Kafka consumer loop
# ──────────────────────────────────────────────────────────────────────────────
async def consumer_loop():
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="etl_group",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            try:
                schema = ProductSchema.model_validate_json(msg.value.decode())
                await save(schema)
            except ValidationError as e:
                log.warning("Schema error: %s", e)
            except Exception as e:
                log.error("DB save error: %s", e)
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(consumer_loop())
