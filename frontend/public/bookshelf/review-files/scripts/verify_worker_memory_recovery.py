"""Controlled MemoryError in an isolated job DB/topic, on the real local broker."""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.catalog import Catalog, Embedder
from backend.app.config import ROOT, Settings
from backend.app.db import Database
from backend.app.jobs import Jobs
from backend.app.models import Job, User
from backend.app.native_process import WindowsJob, stop_owned


async def run():
    identifier = "worker-memory-fatal-" + uuid.uuid4().hex[:8]
    output = ROOT / "docs/evidence" / identifier
    output.mkdir()
    local = ROOT / ".local" / identifier
    local.mkdir()
    url = f"sqlite+aiosqlite:///{(local/'jobs.sqlite3').as_posix()}"
    environment = {**os.environ, "DATABASE_URL": url, "CREATE_SCHEMA": "false", "SEED_USERS": "true",
                   "MODEL_MODE": "mock", "EMBEDDING_MODE": "test", "ENABLE_TEST_FAULTS": "true",
                   "KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:19094", "KAFKA_TOPIC": identifier,
                   "KAFKA_CONSUMER_GROUP": identifier, "LEASE_SECONDS": "3", "HEARTBEAT_SECONDS": "1",
                   "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    environment.pop("ASSESSMENT_JOB_FAULT", None)
    environment.pop("ASSESSMENT_CRASH_AT", None)
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"],
                                     cwd=ROOT, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0
    settings = Settings(_env_file=None, database_url=url, embedding_mode="test", create_schema=False,
                        model_mode="mock", lease_seconds=3, heartbeat_seconds=1)
    db = Database(settings)
    await db.initialize(settings)
    catalog = Catalog(settings)
    jobs = Jobs(settings, db, catalog, Embedder(settings))
    async with db.sessions() as connection:
        user = await connection.scalar(select(User.id).where(User.username == "alice"))
    job = await jobs.create(user, catalog.active_id, "controlled-memory-error")
    processes, containers, handles = [], [], []
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "job_id": job.id,
              "scope": "Real Kafka, independent Worker; isolated SQLite/test vectors, explicit MemoryError without real memory exhaustion"}

    def spawn(crash=False):
        handle = (output / ("memory-error-worker.log" if crash else "replacement-worker.log")).open("wb")
        handles.append(handle)
        container = WindowsJob()
        containers.append(container)
        env = {**environment, **({"ASSESSMENT_CRASH_AT": "memory_after_claim"} if crash else {})}
        process = subprocess.Popen([sys.executable, "-m", "backend.app.worker"], cwd=ROOT, env=env,
                                   stdout=handle, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        container.assign(process.pid)
        processes.append(process)
        return process

    try:
        failed = spawn(True)
        code = await asyncio.to_thread(failed.wait, timeout=45)
        assert code == 75, code
        report["fatal_exit_code"] = code
        spawn()
        for _ in range(160):
            async with db.sessions() as connection:
                restored = await connection.get(Job, job.id)
            if restored.status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.5)
        assert restored.status == "succeeded" and restored.attempts == 2
        report.update(passed=True, status=restored.status, attempts=restored.attempts, generation=restored.generation)
    except BaseException as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        for container in containers:
            container.close()
        for process in processes:
            await asyncio.to_thread(stop_owned, process)
        for handle in handles:
            handle.close()
        await db.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output/"summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"evidence": str(output), **report}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(run())
