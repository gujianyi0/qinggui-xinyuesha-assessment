"""Actual PostgreSQL/pgvector/BGE and Kafka verification, in disposable local databases."""
import argparse
import asyncio
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
from sqlalchemy import func, select, text

from backend.app.config import Settings
from backend.app.jobs import StaleExecution
from backend.app.main import create_app
from backend.app.models import Feedback, IndexedChunk, Job, PublishedIndex, User

ROOT = Path(__file__).resolve().parents[1]


async def verify(args):
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        raise ValueError("label must be a single directory name")
    home = args.native_root / "native-postgres/pgsql"
    if not (home / "lib/vector.dll").is_file():
        raise ValueError("Prepare portable PostgreSQL and build pgvector first")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    state = ROOT / ".local/infra" / args.label
    evidence = ROOT / "docs/evidence" / args.label
    state.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    cluster = args.native_root / "infra" / args.label / "cluster"
    init = await asyncio.to_thread(subprocess.run, [str(home / "bin/initdb.exe"), "-D", str(cluster), "-U", "assessment", "-A", "trust", "--encoding=UTF8", "--locale=C"], capture_output=True, timeout=60)
    (evidence / "initdb.log").write_bytes(init.stdout + init.stderr)
    if init.returncode:
        raise RuntimeError("initdb failed; inspect evidence initdb.log")
    processes, handles, checks = [], [], []
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "scope": "Actual local PostgreSQL, pgvector, BGE CPU, Kafka and independent Worker; chat model remains mock; Redis/Compose/human trials remain separate"}

    def start():
        handle = (evidence / "postgres.log").open("ab")
        handles.append(handle)
        process = subprocess.Popen([str(home / "bin/postgres.exe"), "-D", str(cluster), "-p", str(args.port), "-h", "127.0.0.1"], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        return process

    def stop():
        if processes and processes[-1].poll() is None:
            subprocess.run([str(home / "bin/pg_ctl.exe"), "-D", str(cluster), "-m", "fast", "-w", "stop"], capture_output=True, timeout=30, check=True)
            processes[-1].wait(timeout=10)

    async def ready():
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if processes[-1].poll() is not None:
                raise RuntimeError("PostgreSQL process exited; inspect postgres.log")
            try:
                connection = await asyncpg.connect(host="127.0.0.1", port=args.port, user="assessment", database="postgres", timeout=2)
                return connection
            except (OSError, asyncpg.PostgresError):
                await asyncio.sleep(0.25)
        raise TimeoutError("PostgreSQL did not become ready")

    try:
        start()
        connection = await ready()
        report["postgres_version"] = await connection.fetchval("SHOW server_version")
        await connection.execute("CREATE DATABASE assessment")
        if args.kafka:
            await connection.execute("CREATE DATABASE kafka_tests")
        await connection.close()
        url = f"postgresql+asyncpg://assessment@127.0.0.1:{args.port}/assessment"
        env = {**os.environ, "DATABASE_URL": url}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
        settings = Settings(_env_file=None, database_url=url, model_mode="mock", embedding_mode="local", redis_url="redis://127.0.0.1:1/0")
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            database, jobs = app.state.database, app.state.jobs
            async with database.sessions() as db:
                user = await db.scalar(select(User).where(User.username == "alice"))
                report["pgvector_version"] = await db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            submitted = await asyncio.gather(*(jobs.create(user.id, app.state.catalog.active_id, "concurrent-create") for _ in range(8)))
            assert len({job.id for job in submitted}) == 1
            job = submitted[0]
            claimed = [value for value in await asyncio.gather(*(jobs.claim(job.id, 0) for _ in range(8))) if value]
            assert len(claimed) == 1
            started = time.perf_counter()
            await jobs.process(claimed[0])
            async with database.sessions() as db:
                saved = await db.get(Job, job.id)
                count = await db.scalar(select(func.count()).select_from(IndexedChunk).where(IndexedChunk.job_id == job.id))
                dimensions = (await db.execute(text("SELECT MIN(vector_dims(embedding)), MAX(vector_dims(embedding)) FROM vector_chunks"))).one()
                assert saved.status == "succeeded" and dimensions == (512, 512) and count == saved.result["chunks"]
            checks.append({"name": "postgres_concurrent_submit_claim_and_bge_pgvector_publish", "job_id": job.id, "concurrent_requests": 8, "attempts": saved.attempts, "chunks": count, "dimension": 512, "elapsed_seconds": round(time.perf_counter()-started,3), "passed": True})
            found = await app.state.search.search("没有手牌时不能成为杀和决斗的目标", job.snapshot_id)
            assert found["mode"] == "pgvector" and found["items"]
            checks.append({"name": "actual_pgvector_retrieval", "mode": found["mode"], "source_ids": [item["source"]["id"] for item in found["items"]], "passed": True})
            print("PASS PostgreSQL concurrent submit/claim, real BGE index and pgvector retrieval", flush=True)

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                alice = (await client.post("/auth/token", json={"username":"alice", "password":settings.demo_password})).json()
                client.headers["Authorization"] = f"Bearer {alice['access_token']}"
                session = (await client.post("/sessions", json={})).json()
                response = await client.post(f"/sessions/{session['id']}/runs", json={"message":"诸葛亮有哪些技能"})
                assert response.status_code == 200 and "event: completed" in response.text
                draft = (await client.post("/feedback-drafts", json={"session_id":session["id"], "actual":"PostgreSQL隔离验收的虚构异常"})).json()
                confirmed = await asyncio.gather(*(client.post(f"/feedback-drafts/{draft['id']}/confirm", json={"revision":1}) for _ in range(8)))
                assert all(result.status_code == 200 for result in confirmed)
                assert len({result.json()["id"] for result in confirmed}) == 1
                async with database.sessions() as db:
                    assert await db.scalar(select(func.count()).select_from(Feedback)) == 1
                bob = (await client.post("/auth/token", json={"username":"bob", "password":settings.demo_password})).json()
                denied = await client.get(f"/sessions/{session['id']}/messages", headers={"Authorization":f"Bearer {bob['access_token']}"})
                assert denied.status_code == 404
                checks.append({"name":"postgres_api_stream_feedback_concurrent_confirm_and_isolation", "session_id":session["id"], "confirmation_requests":8, "feedback_records":1, "bob_read_status":404, "model_mode":"mock", "passed":True})

            cancelled = await jobs.create(user.id, job.snapshot_id, "cancel-publish")
            active = await jobs.claim(cancelled.id, 0)
            await jobs.cancel(cancelled.id)
            try:
                await jobs.process(active)
                raise AssertionError("cancelled job published")
            except StaleExecution as error:
                await jobs.fail(cancelled.id, active.generation, error)
            async with database.sessions() as db:
                assert (await db.get(PublishedIndex, job.snapshot_id)).job_id == job.id
                assert (await db.get(Job, cancelled.id)).status == "cancelled"
            checks.append({"name":"postgres_cancel_preserves_prior_published_index", "job_id":cancelled.id, "passed":True})
            print("PASS PostgreSQL feedback race, identity isolation and cancellation", flush=True)

        if args.kafka:
            kafka_env = {**os.environ, "ASSESSMENT_VERIFY_DATABASE_URL":f"postgresql+asyncpg://assessment@127.0.0.1:{args.port}/kafka_tests"}
            log = (evidence / "kafka-verification.log").open("wb")
            try:
                result = await asyncio.to_thread(subprocess.run, [sys.executable, "scripts/verify_native_kafka.py", "--label", args.label+"-kafka", "--port", str(args.kafka_port)], cwd=ROOT, env=kafka_env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
                assert result.returncode == 0, "PostgreSQL+Kafka verification failed; inspect kafka-verification.log"
            finally:
                log.close()
            checks.append({"name":"postgres_and_real_kafka_six_fault_scenarios", "summary":f"../{args.label}-kafka/summary.json", "passed":True})
            print("PASS PostgreSQL plus actual Kafka/Worker fault matrix", flush=True)

        await asyncio.to_thread(stop)
        start()
        connection = await ready()
        await connection.close()
        restarted = create_app(settings)
        async with restarted.router.lifespan_context(restarted):
            async with restarted.state.database.sessions() as db:
                assert (await db.get(Job, job.id)).status == "succeeded"
                assert await db.scalar(select(func.count()).select_from(Feedback)) == 1
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://test", headers={"Authorization":f"Bearer {alice['access_token']}"}) as client:
                messages = await client.get(f"/sessions/{session['id']}/messages")
                assert messages.status_code == 200 and len(messages.json()) == 2
        checks.append({"name":"postgres_actual_process_restart_persistence", "passed":True})
        report["passed"] = True
        print("PASS actual PostgreSQL process restart persistence", flush=True)
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        await asyncio.to_thread(stop)
        for handle in handles:
            handle.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--kafka", action="store_true")
    parser.add_argument("--kafka-port", type=int, default=19092)
    args = parser.parse_args()
    # PostgreSQL's Windows bootstrap sends its install paths through the ANSI
    # code page. Use an ephemeral ASCII DOS path to the SAME .local directory;
    # this creates no file copy, changes no system locale and is removed after
    # every owned PostgreSQL process has stopped.
    drive = None
    args.native_root = ROOT / ".local"
    if os.name == "nt":
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drive = next((f"{letter}:" for letter in "RQPONMLKJIHG" if not mask & (1 << (ord(letter)-ord('A')))), None)
        if not drive:
            raise RuntimeError("No unused temporary DOS drive available for PostgreSQL Unicode-path compatibility")
        subprocess.run(["subst", drive, str(args.native_root)], check=True, capture_output=True)
        assert os.path.samefile(drive + "\\", args.native_root)
        args.native_root = Path(drive + "\\")
    try:
        asyncio.run(verify(args))
    finally:
        if drive and os.path.samefile(drive + "\\", ROOT / ".local"):
            subprocess.run(["subst", drive, "/D"], check=True, capture_output=True)
