import asyncio
import ctypes
import os

import pytest

from backend.app.catalog import Embedder
from backend.app.config import Settings
from backend.app.isolated_embedding import IsolatedEmbedder
from backend.app.resource_metrics import process_memory, process_tree, system_memory
from backend.app.service_supervisor import WorkerSupervisor
from backend.app.worker import Worker


class Process:
    def __init__(self, pid, code=None):
        self.pid, self.code = pid, code

    def poll(self):
        return self.code


async def test_worker_restart_preserves_other_services_and_retains_exit_reason():
    old, replacement = Process(1, 75), Process(2)
    events, stopped = [], []

    async def stop(process):
        stopped.append(process.pid)

    supervisor = WorkerSupervisor(old, lambda: replacement, stop, events.append)
    await supervisor.tick(0)
    assert supervisor.status["state"] == "backoff" and supervisor.process is old
    await supervisor.tick(1)
    assert supervisor.process is replacement and supervisor.status["restart_count"] == 1
    assert supervisor.status["last_exit"] == {"pid": 1, "code": 75}
    assert not stopped and [e["event"] for e in events] == ["worker_exited", "worker_restarted"]


async def test_memory_limit_recycles_only_worker_and_crash_loop_has_a_bound():
    process = Process(1)
    events, stopped = [], []

    async def stop(process):
        stopped.append(process.pid)
        process.code = -15

    supervisor = WorkerSupervisor(process, lambda: Process(2), stop, events.append, memory_limit=100, max_restarts=1)
    await supervisor.tick(0, private_bytes=101)
    await supervisor.tick(1)
    supervisor.process.code = 75
    await supervisor.tick(2)
    assert stopped == [1] and supervisor.status["state"] == "circuit_open"
    await supervisor.tick(500)
    assert supervisor.status["restart_count"] == 1
    assert any(e["event"] == "worker_memory_limit" for e in events)


async def test_failed_spawn_also_consumes_restart_budget():
    def spawn():
        raise OSError("fixture")

    async def stop(_):
        raise AssertionError("dead process should not be stopped again")

    supervisor = WorkerSupervisor(Process(1, 1), spawn, stop, lambda _: None, max_restarts=1)
    await supervisor.tick(0)
    await supervisor.tick(1)
    await supervisor.tick(2)
    assert supervisor.status["state"] == "circuit_open"


async def test_embedding_child_returns_same_vectors_and_closes_after_each_job():
    settings = Settings(_env_file=None, embedding_mode="test")
    isolated = IsolatedEmbedder(settings)
    try:
        expected = await Embedder(settings).encode(["青龙与空城", "摸牌阶段两张"])
        assert await isolated.encode(["青龙与空城", "摸牌阶段两张"]) == expected
        first = isolated.process
        await isolated.close()
        assert first.returncode == 0 and isolated.process is None
        assert await isolated.encode(["青龙与空城"]) == expected[:1]
        assert isolated.process.pid != first.pid
    finally:
        await isolated.close()


async def test_embedding_child_cancellation_releases_process():
    isolated = IsolatedEmbedder(Settings(_env_file=None, embedding_mode="test"))
    await isolated.encode(["fixture"])
    process = isolated.process
    await isolated.close()
    assert process.returncode is not None


async def test_background_memory_error_is_fatal_and_closes_consumer_database():
    worker = Worker.__new__(Worker)
    worker.stopping = asyncio.Event()
    worker.settings = type("Config", (), {"kafka_topic": "test"})()
    closed = []

    class Database:
        async def initialize(self, _):
            pass

        async def close(self):
            closed.append("database")

    class Consumer:
        def subscribe(self, _):
            pass

        def poll(self, _):
            return None

        def close(self):
            closed.append("consumer")

    async def oom():
        raise MemoryError("controlled fixture; no allocation pressure")

    worker.database, worker.consumer, worker.outbox_loop = Database(), Consumer(), oom
    with pytest.raises(MemoryError):
        await worker.run()
    assert closed == ["consumer", "database"]


@pytest.mark.skipif(os.name != "nt", reason="Windows native preview telemetry")
def test_resource_sampling_does_not_leak_windows_handles():
    before = process_memory()
    process_tree(os.getpid())
    pointer_types = len(ctypes._pointer_type_cache)
    for _ in range(30):
        own = process_memory()
        assert own["available"] and own["private_bytes"] > 0
        assert system_memory()["commit_limit_bytes"] > 0
        assert any(p["pid"] == os.getpid() for p in process_tree(os.getpid()))
    assert process_memory()["handles"] <= before["handles"] + 3
    assert len(ctypes._pointer_type_cache) == pointer_types
