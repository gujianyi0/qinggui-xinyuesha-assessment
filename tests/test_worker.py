import asyncio
import json

import pytest

from backend.app.worker import Worker


class Message:
    def __init__(self, value):
        self.body = value

    def value(self):
        return json.dumps(self.body).encode()

    def topic(self):
        return "test"

    def partition(self):
        return 0

    def offset(self):
        return 7

    def error(self):
        return None


@pytest.mark.parametrize("payload", [[], None, "wrong", {"job_id": 3}, {"job_id": "j", "expected_generation": "0"}])
async def test_bad_envelope_is_committed_without_business_processing(payload):
    worker = Worker.__new__(Worker)
    committed = []

    class Consumer:
        def commit(self, **kwargs):
            committed.append(kwargs)

    worker.consumer = Consumer()
    await worker.handle(Message(payload))
    assert len(committed) == 1


async def test_poll_failure_rewinds_before_later_offset_can_commit():
    worker = Worker.__new__(Worker)
    worker.stopping = asyncio.Event()
    called = []

    class Database:
        async def initialize(self, _):
            pass

        async def close(self):
            pass

    class Consumer:
        def subscribe(self, topics):
            pass

        def poll(self, _):
            return Message({"job_id": "j", "expected_generation": 0})

        def seek(self, partition):
            called.append((partition.topic, partition.partition, partition.offset))
            worker.stopping.set()

        def close(self):
            pass

    async def failed(_):
        raise ConnectionError("database unavailable")

    async def outbox():
        await worker.stopping.wait()

    worker.database, worker.consumer, worker.settings = Database(), Consumer(), type('Config', (), {'kafka_topic': 'test'})()
    worker.handle, worker.outbox_loop = failed, outbox
    await worker.run()
    assert called == [("test", 0, 7)]
