import asyncio, json, logging, datetime as dt
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel, Field, ValidationError
import sqlalchemy as sa
from .models import Base, Shop, ProductSnapshot
from tiktok_scraper.config import POSTGRES_DSN, KAFKA_BOOTSTRAP, KAFKA_TOPIC

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("etl")

class ProductSchema(BaseModel):
    url: str
    data: dict = Field(...)

engine = sa.create_engine(POSTGRES_DSN)
Base.metadata.create_all(engine)

async def save(record: ProductSchema):
    data = record.data.get("data", {})
    products = data.get("items", [])
    with engine.begin() as cx:
        for p in products:
            cx.execute(sa.insert(ProductSnapshot).values(
                product_id=p["id"],
                shop_id=p["shop_id"],
                name=p.get("title"),
                price=p.get("price"),
                currency=p.get("currency", "USD"),
                sold_count=p.get("sold"),
                stock=p.get("stock"),
                rating=p.get("rating"),
                scraped_at=dt.datetime.utcnow(),
            ).on_conflict_do_update(
                index_elements=[ProductSnapshot.product_id],
                set_={
                    "price": p.get("price"),
                    "sold_count": p.get("sold"),
                    "stock": p.get("stock"),
                    "scraped_at": dt.datetime.utcnow(),
                }))

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
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(consumer_loop())
