"""Validate actual Redis cache lifecycle and persistent job authority in isolation."""
import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import select

from backend.app.catalog import Catalog, Embedder, KnowledgeSearch
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.jobs import Jobs
from backend.app.models import Job, User

ROOT = Path(__file__).resolve().parents[1]


async def verify(args):
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        raise ValueError("label must be a single directory name")
    dependency = json.loads((ROOT / ".local/native-redis/dependency.json").read_text(encoding="utf-8"))
    server = Path(dependency["server"]).resolve()
    if not server.is_relative_to((ROOT / ".local/native-redis").resolve()):
        raise ValueError("Redis test dependency must stay inside the project")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    state = ROOT / ".local/infra" / args.label
    evidence = ROOT / "docs/evidence" / args.label
    state.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    url = f"sqlite+aiosqlite:///{(state / 'jobs.sqlite3').as_posix()}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    settings = Settings(_env_file=None, database_url=url, embedding_mode="test", redis_url=f"redis://127.0.0.1:{args.port}/0")
    database = Database(settings)
    await database.initialize(settings)
    catalog, embedder = Catalog(settings), Embedder(settings)
    jobs = Jobs(settings, database, catalog, embedder)
    search = KnowledgeSearch(catalog, database, embedder, settings)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    processes, handles, checks = [], [], []
    record = {"started_at":datetime.now(timezone.utc).isoformat(), "checks":checks,
              "dependency":{key:dependency[key] for key in ["version", "source", "sha256", "provenance"]},
              "scope":"Actual community Redis 7.4.11 Windows process, SQLite persistent job state and test vectors; Linux Compose and live chat model remain separate"}

    def start():
        output = (evidence / "redis.log").open("ab")
        handles.append(output)
        process = subprocess.Popen([str(server), "--bind", "127.0.0.1", "--port", str(args.port),
                                    "--protected-mode", "yes", "--save", "", "--appendonly", "no", "--daemonize", "no"],
                                   cwd=state, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        return process

    async def ready():
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if processes[-1].poll() is not None:
                raise RuntimeError("Redis exited; inspect redis.log")
            try:
                if await redis.ping():
                    return
            except (OSError, ConnectionError, TimeoutError):
                pass
            except Exception as error:
                if type(error).__name__ not in {"ConnectionError", "TimeoutError"}:
                    raise
            await asyncio.sleep(0.2)
        raise TimeoutError("Redis did not become ready")

    async def stop():
        if processes and processes[-1].poll() is None:
            try:
                await redis.shutdown(nosave=True)
            except Exception:
                processes[-1].terminate()
            await asyncio.to_thread(processes[-1].wait, timeout=10)

    calls = 0
    original = embedder.encode

    async def counted(*values, **keywords):
        nonlocal calls
        calls += 1
        return await original(*values, **keywords)

    try:
        start()
        await ready()
        info = await redis.info("server")
        assert info["redis_version"].startswith("7.4.")
        record["actual_redis_version"] = info["redis_version"]
        async with database.sessions() as db:
            user = await db.scalar(select(User).where(User.username == "alice"))
        job = await jobs.create(user.id, catalog.active_id, "indexed")
        await jobs.process(await jobs.claim(job.id, 0))
        embedder.encode = counted
        query = "诸葛亮空城"
        first = await search.search(query, job.snapshot_id)
        assert first["mode"] == "test_vectors" and calls == 1
        keys = await redis.keys("retrieval:*")
        assert len(keys) == 1
        key = keys[0]
        ttl = await redis.ttl(key)
        assert 295 <= ttl <= 300
        second = await search.search(query, job.snapshot_id)
        assert second == first and calls == 1
        checks.append({"name":"real_cache_miss_then_hit", "embedding_calls":calls, "ttl_seconds":ttl, "passed":True})
        print("PASS actual cache miss/hit and default 300-second TTL", flush=True)

        await redis.expire(key, 1)
        deadline = time.monotonic() + 4
        while await redis.exists(key) and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        assert not await redis.exists(key)
        await search.search(query, job.snapshot_id)
        assert calls == 2
        checks.append({"name":"real_ttl_expiry_then_source_read", "expiry_for_test_seconds":1, "production_default_seconds":300, "passed":True})

        # A stale cached result is deliberately kept alive across a new publish.
        await redis.setex(key, 300, json.dumps({"stale_canary":True}))
        new_job = await jobs.create(user.id, job.snapshot_id, "republished")
        await jobs.process(await jobs.claim(new_job.id, 0))
        refreshed = await search.search(query, job.snapshot_id)
        assert "stale_canary" not in refreshed and await redis.exists(key)
        new_keys = [candidate for candidate in await redis.keys("retrieval:*") if candidate != key]
        assert len(new_keys) == 1
        checks.append({"name":"publish_generation_bypasses_old_live_cache", "new_job_id":new_job.id, "old_key_still_exists":True, "passed":True})

        await redis.setex(new_keys[0], 300, "{invalid-json")
        assert (await search.search(query, job.snapshot_id))["items"]
        assert isinstance(json.loads(await redis.get(new_keys[0])), dict)
        checks.append({"name":"malformed_cache_value_recovers", "passed":True})

        await stop()
        pending = await jobs.create(user.id, job.snapshot_id, "created-while-cache-down")
        fallback = await search.search("红色牌当杀使用", job.snapshot_id)
        assert fallback["mode"] == "test_vectors" and fallback["items"]
        async with database.sessions() as db:
            assert (await db.get(Job, pending.id)).status == "queued"
            assert (await db.get(Job, job.id)).status == "succeeded"
        await jobs.cancel(pending.id)
        checks.append({"name":"redis_process_stopped_search_falls_back_jobs_remain_authoritative", "pending_job_id":pending.id, "passed":True})
        print("PASS Redis shutdown fallback and persistent job operations", flush=True)

        start()
        await ready()
        restored = await search.search(query, job.snapshot_id)
        assert restored["items"] and await redis.keys("retrieval:*")
        async with database.sessions() as db:
            assert (await db.get(Job, pending.id)).status == "cancelled"
        checks.append({"name":"redis_process_restart_reconnect_and_repopulate", "passed":True})
        record["passed"] = True
        print("PASS Redis restart, reconnect and cache repopulation", flush=True)
    except Exception as error:
        record.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        await stop()
        await redis.aclose()
        await search.close()
        await database.close()
        for output in handles:
            output.close()
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "summary.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--port", type=int, default=16379)
    asyncio.run(verify(parser.parse_args()))
