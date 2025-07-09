from aiokafka import AIOKafkaProducer
import json, os

class KafkaWriter:
    def __init__(self, topic: str):
        self._topic = topic
        self._producer = AIOKafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
            compression_type="gzip",
            value_serializer=lambda v: json.dumps(v).encode(),
        )

    async def start(self):
        await self._producer.start()

    async def send(self, payload: dict):
        await self._producer.send_and_wait(self._topic, value=payload)

    async def stop(self):
        await self._producer.stop()