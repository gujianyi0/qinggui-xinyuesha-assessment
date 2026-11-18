"""One independently runnable process: outbox, Kafka consumer and lease recovery."""
import asyncio
import contextlib
import faulthandler
import json
import logging
import os
import signal

from confluent_kafka import Consumer, Producer, TopicPartition
from sqlalchemy import select

from .catalog import Catalog, Embedder
from .config import Settings
from .db import Database
from .isolated_embedding import IsolatedEmbedder
from .jobs import Jobs, StaleExecution
from .models import Outbox
from .resource_metrics import process_memory, system_memory

log = logging.getLogger("assessment.worker")


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings)
        self.catalog = Catalog(settings)
        embedder = IsolatedEmbedder(settings) if settings.embedding_mode == "local" else Embedder(settings)
        self.jobs = Jobs(settings, self.database, self.catalog, embedder)
        self.stopping = asyncio.Event()
        self.consumer = Consumer({"bootstrap.servers": settings.kafka_bootstrap_servers, "group.id": settings.kafka_consumer_group, "auto.offset.reset": "earliest", "enable.auto.commit": False, "enable.auto.offset.store": False, "max.poll.interval.ms": 900000, "session.timeout.ms": 10000, "queued.min.messages": 10, "queued.max.messages.kbytes": 4096, "fetch.message.max.bytes": 1048576})
        self.producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers, "enable.idempotence": True, "acks": "all", "message.timeout.ms": 10000, "queue.buffering.max.messages": 100, "queue.buffering.max.kbytes": 1024})

    def publish(self, payload: dict):
        errors = []
        self.producer.produce(self.settings.kafka_topic, key=payload["job_id"], value=json.dumps(payload).encode(), on_delivery=lambda error, _: errors.append(error) if error else None)
        pending = self.producer.flush(12)
        if pending or errors:
            raise ConnectionError("Kafka delivery unavailable")

    async def outbox_loop(self):
        while not self.stopping.is_set():
            try:
                await self.jobs.recover()
                async with self.database.sessions.begin() as db:
                    events = list((await db.scalars(select(Outbox).where(Outbox.delivered.is_(False)).order_by(Outbox.created_at).limit(20).with_for_update(skip_locked=True))).all())
                    for event in events:
                        await asyncio.to_thread(self.publish, event.payload)
                        if self.settings.enable_test_faults and os.environ.get("ASSESSMENT_CRASH_AT") == "after_publish":
                            os._exit(81)
                        event.delivered = True
            except MemoryError:
                raise  # An exhausted process must be replaced, not keep allocating retries.
            except Exception:
                log.exception("outbox/recovery deferred")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=1)

    async def handle(self, message):
        try:
            payload = json.loads(message.value())
            if not isinstance(payload, dict):
                raise ValueError("invalid task envelope")
            if not isinstance(payload.get("job_id"), str) or not isinstance(payload.get("expected_generation"), int):
                raise ValueError("invalid task envelope")
        except (ValueError, TypeError):
            # An invalid transport envelope has no business job; retain a structured diagnostic.
            log.error("invalid_envelope topic=%s partition=%s offset=%s", message.topic(), message.partition(), message.offset())
            await asyncio.to_thread(self.consumer.commit, message=message, asynchronous=False)
            return
        job = await self.jobs.claim(payload["job_id"], payload["expected_generation"])
        if job:
            log.info("job_claimed job_id=%s generation=%s", job.id, job.generation)
            if self.settings.enable_test_faults and os.environ.get("ASSESSMENT_CRASH_AT") == "memory_after_claim":
                raise MemoryError("explicit isolated recovery test; no memory pressure allocated")
            if self.settings.enable_test_faults and os.environ.get("ASSESSMENT_CRASH_AT") == "after_claim":
                os._exit(83)
            async def keep_alive():
                while True:
                    await asyncio.sleep(self.settings.heartbeat_seconds)
                    await self.jobs.heartbeat(job.id, job.generation)
            heartbeat = asyncio.create_task(keep_alive())
            try:
                fault = os.environ.get("ASSESSMENT_JOB_FAULT") if self.settings.enable_test_faults else None
                await self.jobs.process(job, fault=fault)
                if self.settings.enable_test_faults and os.environ.get("ASSESSMENT_CRASH_AT") == "after_business_commit":
                    os._exit(82)
            except asyncio.CancelledError:
                # Lease recovery owns interrupted work. No offset commit on forced shutdown.
                raise
            except StaleExecution as error:
                await self.jobs.fail(job.id, job.generation, error)
            except MemoryError:
                raise
            except Exception as error:
                await self.jobs.fail(job.id, job.generation, error)
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                close = getattr(self.jobs.embedder, "close", None)
                if close is not None:
                    await close()
                log.info("job_released job_id=%s memory=%s", job.id, json.dumps(process_memory()))
        await asyncio.to_thread(self.consumer.commit, message=message, asynchronous=False)

    async def run(self):
        await self.database.initialize(self.settings)
        self.consumer.subscribe([self.settings.kafka_topic])
        outbox = asyncio.create_task(self.outbox_loop())
        diagnostics = asyncio.create_task(self.diagnostics_loop())
        try:
            while not self.stopping.is_set():
                if outbox.done():
                    outbox.result()  # Propagate background MemoryError to the process boundary.
                    raise RuntimeError("outbox loop stopped unexpectedly")
                message = await asyncio.to_thread(self.consumer.poll, 0.5)
                if message is None or message.error():
                    continue
                try:
                    await self.handle(message)
                except MemoryError:
                    raise
                except Exception:
                    log.exception("message retained for retry")
                    # poll() already advanced the local position. Rewind before polling
                    # again so a later commit cannot acknowledge this failed message.
                    await asyncio.to_thread(self.consumer.seek, TopicPartition(message.topic(), message.partition(), message.offset()))
                    await asyncio.sleep(1)
        finally:
            self.stopping.set()
            outbox.cancel()
            diagnostics.cancel()
            await asyncio.gather(outbox, diagnostics, return_exceptions=True)
            await asyncio.to_thread(self.consumer.close)
            await self.database.close()

    async def diagnostics_loop(self):
        while not self.stopping.is_set():
            log.info("worker_resources %s", json.dumps({"process": process_memory(), "system": system_memory(),
                     "async_tasks": len(asyncio.all_tasks())}))
            await asyncio.sleep(30)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    worker = Worker(Settings())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stopping.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(worker.stopping.set))
    await worker.run()


if __name__ == "__main__":
    faulthandler.enable()
    try:
        asyncio.run(main())
    except MemoryError:
        # Avoid traceback/JSON allocation while memory is exhausted. Native supervisor
        # already retains recent resource samples and the exit code.
        os.write(2, b"worker_fatal MemoryError exit_code=75; lease recovery required\n")
        os._exit(75)
