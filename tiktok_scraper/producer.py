"""Kafka producer helper - offloads writes from the scraper loop."""
import asyncio, json, logging
from aiokafka import AIOKafkaProducer
from .config import KAFKA_BOOTSTRAP, KAFKA_TOPIC

log = logging.getLogger(__name__)

class KafkaWriter:
    def __init__(self):
        self._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)

    async def __aenter__(self):
        await self._producer.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._producer.stop()

    async def send(self, record: dict):
        await self._producer.send_and_wait(KAFKA_TOPIC, json.dumps(record).encode())
        log.debug("→ kafka:%s", record.get("product_id"))