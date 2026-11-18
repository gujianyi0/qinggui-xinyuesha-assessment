"""Real Redis + isolated PostgreSQL/pgvector + local BGE, including natural 300s TTL."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
from redis.asyncio import Redis
from sqlalchemy import select

from backend.app.catalog import Catalog, KnowledgeSearch
from backend.app.config import ROOT, Settings
from backend.app.db import Database
from backend.app.isolated_embedding import IsolatedEmbedder
from backend.app.jobs import Jobs
from backend.app.models import Job, User
from backend.app.native_process import WindowsJob, stop_owned


async def verify(label):
    if not label or "/" in label or "\\" in label or label in {".", ".."}:
        raise ValueError("label must be a single directory name")
    output = ROOT / "docs/evidence" / label
    output.mkdir(exist_ok=False)
    local = ROOT / ".local/infra" / label
    local.mkdir(exist_ok=False)
    dependency = json.loads((ROOT / ".local/native-redis/dependency.json").read_text(encoding="utf-8"))
    server = Path(dependency["server"]).resolve()
    if not server.is_relative_to((ROOT / ".local/native-redis").resolve()):
        raise ValueError("Redis dependency outside project")
    dbname = "assessment_cache_" + uuid.uuid4().hex[:10]
    admin = await asyncpg.connect(host="127.0.0.1", port=15433, user="assessment", database="postgres")
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')  # fixed prefix + generated hex, never user SQL
    finally:
        await admin.close()
    url = f"postgresql+asyncpg://assessment@127.0.0.1:15433/{dbname}"
    environment = {**os.environ, "DATABASE_URL": url, "MODEL_MODE": "mock"}
    migrated = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        timeout=40,
    )
    assert migrated.returncode == 0
    settings = Settings(
        _env_file=None,
        database_url=url,
        embedding_mode="local",
        embedding_threads=2,
        model_mode="mock",
        redis_url="redis://127.0.0.1:16479/0",
    )
    db = Database(settings)
    await db.initialize(settings)
    catalog, embedder = Catalog(settings), IsolatedEmbedder(settings)
    calls = 0

    class Counting:
        async def encode(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return await embedder.encode(*args, **kwargs)

    search = KnowledgeSearch(catalog, db, Counting(), settings)
    jobs = Jobs(settings, db, catalog, embedder)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    process, container, log = None, None, (output / "redis.log").open("ab")
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "database": dbname,
        "dependency": dependency,
        "scope": "Actual community Windows Redis 7.4.11, isolated PostgreSQL/pgvector and CPU BGE; no paid model or QQ calls",
        "checks": [],
        "ttl_samples": [],
    }

    async def start():
        nonlocal process, container
        container = WindowsJob()
        process = subprocess.Popen(
            [
                str(server),
                "--bind",
                "127.0.0.1",
                "--port",
                "16479",
                "--protected-mode",
                "yes",
                "--save",
                "",
                "--appendonly",
                "no",
                "--daemonize",
                "no",
            ],
            cwd=local,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        container.assign(process.pid)
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("isolated Redis exited")
            try:
                if await redis.ping():
                    return
            except Exception:
                pass
            await asyncio.sleep(0.25)
        raise TimeoutError("Redis startup timed out")

    async def stop():
        if process and process.poll() is None:
            try:
                await redis.shutdown(nosave=True)
            except Exception:
                await asyncio.to_thread(stop_owned, process)
        if container:
            container.close()
        if process:
            await asyncio.to_thread(stop_owned, process)

    async def imported(key):
        job = await jobs.create(user_id, catalog.active_id, key)
        await jobs.process(await jobs.claim(job.id, 0))
        await embedder.close()
        return job

    def check(name, **values):
        report["checks"].append({"name": name, "passed": True, **values})
        print("PASS " + name, flush=True)

    try:
        await start()
        async with db.sessions() as connection:
            user_id = await connection.scalar(select(User.id).where(User.username == "alice"))
        job = await imported("first-index")
        query = "诸葛亮空城"
        first = await search.search(query, catalog.active_id)
        began = time.monotonic()  # Measure from cache publication, including child cleanup time.
        assert first["mode"] == "pgvector" and first["items"] and calls == 1
        key = (await redis.keys("retrieval:*"))[0]
        assert 295 <= await redis.ttl(key) <= 300
        assert await search.search(query, catalog.active_id) == first and calls == 1
        await embedder.close()
        check("postgres_bge_miss_then_real_redis_hit", ttl=await redis.ttl(key), query_embedding_calls=calls)

        # Do not EXPIRE, delete or refresh this key: observe the production 300s TTL.
        async with httpx.AsyncClient(trust_env=False, timeout=5) as http:
            while await redis.exists(key):
                elapsed = time.monotonic() - began
                if elapsed > 315:
                    raise TimeoutError("default cache TTL did not expire")
                ttl = await redis.ttl(key)
                web, api = await asyncio.gather(
                    http.get("http://127.0.0.1:15174/"), http.get("http://127.0.0.1:15174/api/health")
                )
                assert web.status_code == api.status_code == 200
                report["ttl_samples"].append(
                    {"elapsed_seconds": round(elapsed, 3), "ttl": ttl, "web": web.status_code, "api": api.status_code}
                )
                if ttl > 1:
                    assert await search.search(query, catalog.active_id) == first and calls == 1
                (output / "progress.json").write_text(
                    json.dumps(
                        {
                            "phase": "natural_300_second_ttl",
                            "elapsed_seconds": elapsed,
                            "ttl": ttl,
                            "query_embedding_calls": calls,
                            "checks": report["checks"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                await asyncio.sleep(min(5, max(0.25, ttl)))
        duration = time.monotonic() - began
        assert duration >= 299
        assert await search.search(query, catalog.active_id) == first and calls == 2
        check(
            "natural_default_300_second_expiry_then_pgvector_read",
            observed_seconds=round(duration, 3),
            query_embedding_calls=calls,
        )

        bad_values = [{"stale_canary": True}, [], {**first, "snapshot_id": "other-snapshot"}, "{invalid-json"]
        for bad in bad_values:
            await redis.setex(key, 300, bad if isinstance(bad, str) else json.dumps(bad))
            before = calls
            assert await search.search(query, catalog.active_id) == first and calls == before + 1
            assert json.loads(await redis.get(key)) == first
        await embedder.close()
        check("bad_json_or_wrong_shape_or_foreign_snapshot_repaired", variants=len(bad_values))

        await redis.setex(key, 300, json.dumps({"old_index_canary": True}))
        new_job = await imported("republished-index")
        refreshed = await search.search(query, catalog.active_id)
        assert refreshed["items"] and "old_index_canary" not in refreshed and await redis.exists(key)
        check("new_publish_bypasses_live_old_index_cache", old_job_id=job.id, new_job_id=new_job.id)
        await embedder.close()
        await stop()
        pending = await jobs.create(user_id, catalog.active_id, "while-cache-offline")
        fallback = await search.search("红色牌当杀使用", catalog.active_id)
        assert fallback["mode"] == "pgvector" and fallback["items"]
        await jobs.cancel(pending.id)
        async with db.sessions() as connection:
            assert (await connection.get(Job, pending.id)).status == "cancelled"
            assert (await connection.get(Job, new_job.id)).status == "succeeded"
        await embedder.close()
        check("redis_shutdown_pgvector_fallback_and_postgres_job_authority", cancelled_job_id=pending.id)
        await start()
        before = calls
        assert (await search.search(query, catalog.active_id))["items"] and calls == before + 1
        assert await redis.keys("retrieval:*")
        assert (await search.search(query, catalog.active_id))["items"] and calls == before + 1
        check("redis_restart_reconnect_repopulate_then_hit")
        report.update(
            passed=True, query_embedding_calls=calls, actual_redis_version=(await redis.info("server"))["redis_version"]
        )
    except BaseException as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        await embedder.close()
        await stop()
        await redis.aclose()
        await search.close()
        await db.close()
        log.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "checks": len(report["checks"]), "evidence": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    asyncio.run(verify(parser.parse_args().label))
