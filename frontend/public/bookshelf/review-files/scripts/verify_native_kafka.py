"""Verify real Kafka and crash/restart behavior with an isolated SQLite test database.

This supplements, and does not replace, PostgreSQL/Compose verification.
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import func, select

from backend.app.catalog import Catalog, Embedder
from backend.app.chunking import chunk_documents
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.jobs import Jobs
from backend.app.models import IndexedChunk, Job, Outbox, User
from backend.app.native_process import java_executable, stop_owned

ROOT = Path(__file__).resolve().parents[1]


async def until(check, timeout=70):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await check()
        if result:
            return result
        await asyncio.sleep(0.25)
    raise TimeoutError("verification condition timed out")


async def verify(args):
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        raise ValueError("label must be a single directory name")
    home = ROOT / ".local/native-kafka/kafka_2.13-3.9.1"
    if not (home / "libs").is_dir():
        raise ValueError("Run scripts/prepare_native_kafka.py first")
    java = args.java or shutil.which("java")
    if not java:
        raise ValueError("Java 17+ is required")
    java = java_executable(java)
    for port in (args.port, args.port + 1):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    state = ROOT / ".local/infra" / args.label
    evidence = ROOT / "docs/evidence" / args.label
    state.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    config = state / "server.properties"
    values = {
        "process.roles": "broker,controller", "node.id": "1",
        "controller.quorum.voters": f"1@127.0.0.1:{args.port + 1}",
        "listeners": f"PLAINTEXT://127.0.0.1:{args.port},CONTROLLER://127.0.0.1:{args.port + 1}",
        "advertised.listeners": f"PLAINTEXT://127.0.0.1:{args.port}",
        "controller.listener.names": "CONTROLLER", "inter.broker.listener.name": "PLAINTEXT",
        "listener.security.protocol.map": "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
        "log.dirs": (state / "data").as_posix(), "num.partitions": "1",
        "offsets.topic.replication.factor": "1", "transaction.state.log.replication.factor": "1",
        "transaction.state.log.min.isr": "1", "group.initial.rebalance.delay.ms": "0",
        "auto.create.topics.enable": "true",
    }
    config.write_text("\n".join(f"{key}={json.dumps(value, ensure_ascii=True)[1:-1]}" for key, value in values.items()), encoding="ascii")
    java_base = [str(java), "-Xms256m", "-Xmx512m",
                 f"-Dkafka.logs.dir={state / 'java-logs'}",
                 f"-Dlog4j.configuration={(home / 'config/log4j.properties').as_uri()}",
                 "-cp", str(home / "libs/*")]
    cluster = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
    formatted = subprocess.run([*java_base, "kafka.tools.StorageTool", "format", "-t", cluster, "-c", str(config)], capture_output=True, timeout=40)
    (evidence / "storage-format.log").write_bytes(formatted.stdout + formatted.stderr)
    if formatted.returncode:
        raise RuntimeError("Kafka storage formatting failed; inspect storage-format.log")
    address = f"127.0.0.1:{args.port}"
    topic = "assessment.verify." + uuid.uuid4().hex[:12]
    group = "assessment.verify." + uuid.uuid4().hex[:12]
    database_url = os.environ.get("ASSESSMENT_VERIFY_DATABASE_URL") or f"sqlite+aiosqlite:///{(state / 'jobs.sqlite3').as_posix()}"
    env = {**os.environ, "DATABASE_URL": database_url,
           "MODEL_MODE": "mock", "EMBEDDING_MODE": "test", "CREATE_SCHEMA": "false",
           "ENABLE_TEST_FAULTS": "true", "KAFKA_BOOTSTRAP_SERVERS": address,
           "KAFKA_TOPIC": topic, "KAFKA_CONSUMER_GROUP": group,
           "LEASE_SECONDS": "3", "HEARTBEAT_SECONDS": "1", "RETRY_DELAYS": "[1,1]"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    settings = Settings(_env_file=None, database_url=env["DATABASE_URL"], embedding_mode="test", model_mode="mock")
    database = Database(settings)
    await database.initialize(settings)
    catalog = Catalog(settings)
    jobs = Jobs(settings, database, catalog, Embedder(settings))
    async with database.sessions() as db:
        user_id = await db.scalar(select(User.id).where(User.username == "alice"))
    handles, workers = [], []
    broker = None
    checks = []
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "kafka_version": "3.9.1",
              "topic": topic, "consumer_group": group, "checks": checks,
              "database": database.engine.dialect.name,
              "scope": f"Real Kafka broker and independent Python Worker with {database.engine.dialect.name} and test vectors; Redis, actual chat model and Compose remain separate"}

    def launch_broker():
        log = (evidence / "broker.log").open("ab")
        handles.append(log)
        return subprocess.Popen([*java_base, "kafka.Kafka", str(config)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def launch_worker(crash=None, fault=None):
        worker_env = dict(env)
        worker_env.pop("ASSESSMENT_CRASH_AT", None)
        worker_env.pop("ASSESSMENT_JOB_FAULT", None)
        if crash:
            worker_env["ASSESSMENT_CRASH_AT"] = crash
        if fault:
            worker_env["ASSESSMENT_JOB_FAULT"] = fault
        log = (evidence / "worker.log").open("ab")
        handles.append(log)
        worker = subprocess.Popen([sys.executable, "-m", "backend.app.worker"], cwd=ROOT, env=worker_env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        workers.append(worker)
        return worker

    async def ready():
        if broker.poll() is not None:
            raise RuntimeError("Broker exited; inspect broker.log")
        try:
            with socket.create_connection(("127.0.0.1", args.port), timeout=0.2):
                return True
        except OSError:
            return False

    async def job_status(job_id, status):
        async with database.sessions() as db:
            row = await db.get(Job, job_id)
            return row if row.status == status else None

    async def committed_at_least(offset):
        consumer = Consumer({"bootstrap.servers": address, "group.id": group, "enable.auto.commit": False})
        try:
            partitions = await asyncio.to_thread(consumer.committed, [TopicPartition(topic, 0)], timeout=5)
            return partitions[0].offset if partitions[0].offset >= offset else None
        finally:
            consumer.close()

    async def fresh_job(key):
        return await jobs.create(user_id, catalog.active_id, key)

    try:
        broker = launch_broker()
        await until(ready, 45)
        admin = AdminClient({"bootstrap.servers": address})
        creation = admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        await asyncio.to_thread(creation[topic].result, 20)

        first = await fresh_job("crash-after-commit")
        worker = launch_worker(crash="after_business_commit")
        await until(lambda: job_status(first.id, "succeeded"))
        exit_code = await asyncio.to_thread(worker.wait, timeout=10)
        assert exit_code == 82
        consumer = Consumer({"bootstrap.servers": address, "group.id": group, "enable.auto.commit": False})
        before = (await asyncio.to_thread(consumer.committed, [TopicPartition(topic, 0)], timeout=10))[0].offset
        consumer.close()
        assert before < 1, "crash happened after committing the Kafka offset"
        worker = launch_worker()
        offset = await until(lambda: committed_at_least(1))
        async with database.sessions() as db:
            stored = await db.get(Job, first.id)
            chunks = await db.scalar(select(func.count()).select_from(IndexedChunk).where(IndexedChunk.job_id == first.id))
            assert stored.attempts == 1 and chunks == len(chunk_documents(catalog.documents))
        checks.append({"name": "crash_after_business_commit_before_offset", "job_id": first.id,
                       "exit_code": exit_code, "offset_before_restart": before, "offset_after_restart": offset,
                       "attempts": stored.attempts, "chunks": chunks, "passed": True})
        print("PASS real crash after database commit, before Kafka commit", flush=True)

        producer = Producer({"bootstrap.servers": address, "enable.idempotence": True})
        producer.produce(topic, key=first.id, value=json.dumps({"job_id": first.id, "expected_generation": 0}))
        assert await asyncio.to_thread(producer.flush, 10) == 0
        await until(lambda: committed_at_least(2))
        async with database.sessions() as db:
            stored = await db.get(Job, first.id)
            assert stored.attempts == 1
        checks.append({"name": "duplicate_delivery", "job_id": first.id, "attempts": 1, "passed": True})

        await asyncio.to_thread(stop_owned, worker)
        retry = await fresh_job("retry-exhaustion")
        worker = launch_worker(fault="temporary")
        exhausted = await until(lambda: job_status(retry.id, "failed"))
        assert exhausted.attempts == 3
        checks.append({"name": "durable_delayed_retry_exhaustion", "job_id": retry.id,
                       "attempts": exhausted.attempts, "error": exhausted.error, "passed": True})
        print("PASS real delayed retry exhaustion", flush=True)

        await asyncio.to_thread(stop_owned, worker)
        bad = await fresh_job("bad-input")
        async with database.sessions.begin() as db:
            row = await db.get(Job, bad.id)
            row.snapshot_id = "intentionally-invalid-fixture"
        good = await fresh_job("after-bad-input")
        worker = launch_worker()
        failed = await until(lambda: job_status(bad.id, "failed"))
        await until(lambda: job_status(good.id, "succeeded"))
        assert failed.attempts == 1
        checks.append({"name": "bad_input_does_not_block_next_job", "bad_job": bad.id, "next_job": good.id, "passed": True})
        print("PASS bad input retained, next job succeeds", flush=True)

        await asyncio.to_thread(stop_owned, worker)
        interrupted = await fresh_job("lease-recovery")
        worker = launch_worker(crash="after_claim")
        exit_code = await asyncio.to_thread(worker.wait, timeout=45)
        assert exit_code == 83
        worker = launch_worker()
        restored = await until(lambda: job_status(interrupted.id, "succeeded"))
        assert restored.attempts == 2
        checks.append({"name": "worker_exit_after_claim_lease_recovery", "job_id": restored.id,
                       "attempts": restored.attempts, "generation": restored.generation, "passed": True})
        print("PASS crashed running task recovered after lease expiry", flush=True)

        await asyncio.to_thread(stop_owned, broker)
        offline = await fresh_job("broker-offline-outbox")
        async with database.sessions() as db:
            assert (await db.get(Job, offline.id)).status == "queued"
            outbox = await db.scalar(select(Outbox).where(Outbox.job_id == offline.id))
            assert not outbox.delivered
        broker = launch_broker()
        await until(ready, 45)
        await until(lambda: job_status(offline.id, "succeeded"))
        checks.append({"name": "broker_offline_submission_outbox_restart", "job_id": offline.id, "passed": True})
        print("PASS broker unavailable submission, restart delivery", flush=True)
        report["passed"] = True
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        for worker in workers:
            await asyncio.to_thread(stop_owned, worker)
        await asyncio.to_thread(stop_owned, broker)
        await database.close()
        for handle in handles:
            handle.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "checks": len(checks), "evidence": str(evidence)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--java")
    parser.add_argument("--port", type=int, default=19092)
    asyncio.run(verify(parser.parse_args()))
