"""Supervise the local PostgreSQL/Kafka/BGE/Worker demo without Docker or system services."""
import argparse
import asyncio
import base64
import ctypes
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

import asyncpg
import httpx

from backend.app.config import ROOT, Settings
from backend.app.embedding_assets import pinned_model_path
from backend.app.native_process import WindowsJob, java_executable, stop_owned
from backend.app.resource_metrics import process_tree, system_memory, windows_processes
from backend.app.service_supervisor import WorkerSupervisor

STATE = ROOT / ".local/native-demo"
OWNER = "qinggui-assessment-native-demo"
PORTS = {"web":15174, "api":18081, "postgres":15433, "kafka":19094, "controller":19095}


async def run(*, evaluation_faults=False):
    settings = Settings()
    if not (pinned_model_path(settings) / "download-manifest.json").is_file():
        raise RuntimeError("Prepare the pinned BGE model first")
    pg = ROOT / ".local/native-postgres/pgsql"
    kafka = ROOT / ".local/native-kafka/kafka_2.13-3.9.1"
    if not (pg / "lib/vector.dll").is_file() or not (kafka / "libs").is_dir():
        raise RuntimeError("Prepare portable PostgreSQL/pgvector and Kafka first")
    node = shutil.which("node")
    java = java_executable(shutil.which("java"))
    if not node:
        raise RuntimeError("Node.js is required")
    for port in PORTS.values():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    STATE.mkdir(parents=True, exist_ok=True)
    stop_file = STATE / "stop.request"
    stop_file.unlink(missing_ok=True)
    status_file = STATE / "status.json"
    state = {"owner":OWNER, "project":str(ROOT), "supervisor_pid":os.getpid(),
             "started_at":datetime.now(timezone.utc).isoformat(), "ports":PORTS,
             "url":f"http://127.0.0.1:{PORTS['web']}", "stage":"starting",
             "model_mode":settings.model_mode, "embedding_mode":"local", "database":"postgresql", "redis":"unavailable_fallback",
             "evaluation_faults":evaluation_faults}

    def report(stage):
        changed = state["stage"] != stage
        state["stage"] = stage
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = status_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(status_file)
        if changed:
            print(stage, flush=True)

    processes, handles, containers = {}, {}, {}
    drive = None
    cluster = None

    def spawn(name, arguments, *, env=None, cwd=ROOT):
        if name in containers:
            containers.pop(name).close()
        if name in handles:
            handles.pop(name).close()
        log = (STATE / f"{name}.log").open("ab")
        handles[name] = log
        process = subprocess.Popen(arguments, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if name == "worker":
            container = WindowsJob()
            try:
                container.assign(process.pid)
            except BaseException:
                stop_owned(process)
                container.close()
                raise
            containers[name] = container
        processes[name] = process
        state[f"{name}_pid"] = process.pid
        return process

    def diagnostic(event):
        event = {"at": datetime.now(timezone.utc).isoformat(), **event}
        path = STATE / "resources.jsonl"
        if path.exists() and path.stat().st_size > 10 * 1024**2:
            path.replace(STATE / "resources.previous.jsonl")
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False) + "\n")

    async def http_ready(url, seconds=50):
        deadline = time.monotonic() + seconds
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            while time.monotonic() < deadline:
                for name, process in processes.items():
                    if name != "worker" and process.poll() is not None:
                        raise RuntimeError(f"{name} exited; inspect .local/native-demo/{name}.log")
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        return response
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.3)
        raise TimeoutError("Local service readiness timed out")

    try:
        report("initializing_postgres")
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drive = next((f"{letter}:" for letter in "RQPONMLKJIHG" if not mask & (1 << (ord(letter)-ord('A')))), None)
        if not drive:
            raise RuntimeError("No unused DOS drive available for PostgreSQL Unicode-path compatibility")
        subprocess.run(["subst", drive, str(ROOT / ".local")], capture_output=True, check=True)
        assert os.path.samefile(drive+"\\", ROOT / ".local")
        state["temporary_dos_drive"] = drive
        alias = Path(drive+"\\")
        pg = alias / "native-postgres/pgsql"
        cluster = alias / "native-demo/pgdata"
        if not (cluster / "PG_VERSION").is_file():
            result = await asyncio.to_thread(subprocess.run, [str(pg / "bin/initdb.exe"), "-D", str(cluster), "-U", "assessment", "-A", "trust", "--encoding=UTF8", "--locale=C"], capture_output=True, timeout=60)
            (STATE / "initdb.log").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("initdb failed; inspect .local/native-demo/initdb.log")
        spawn("postgres", [str(pg / "bin/postgres.exe"), "-D", str(cluster), "-p", str(PORTS["postgres"]), "-h", "127.0.0.1", "-c", "shared_buffers=32MB", "-c", "max_connections=30"])
        deadline = time.monotonic() + 40
        while True:
            try:
                connection = await asyncpg.connect(host="127.0.0.1", port=PORTS["postgres"], user="assessment", database="postgres", timeout=2)
                break
            except (OSError, asyncpg.PostgresError):
                if time.monotonic() > deadline:
                    raise TimeoutError("PostgreSQL startup timed out") from None
                await asyncio.sleep(0.3)
        if not await connection.fetchval("SELECT 1 FROM pg_database WHERE datname='assessment'"):
            await connection.execute("CREATE DATABASE assessment")
        await connection.close()
        env = {**os.environ, "DATABASE_URL":f"postgresql+asyncpg://assessment@127.0.0.1:{PORTS['postgres']}/assessment",
               "MODEL_MODE":settings.model_mode, "EMBEDDING_MODE":"local", "EMBEDDING_THREADS":"2",
               "CREATE_SCHEMA":"false", "SEED_USERS":"true", "DEMO_PASSWORD":"local-demo-change-me",
               "ENABLE_TEST_FAULTS":str(evaluation_faults).lower(), "REDIS_URL":"redis://127.0.0.1:1/0",
               "KAFKA_BOOTSTRAP_SERVERS":f"127.0.0.1:{PORTS['kafka']}",
               "KAFKA_TOPIC":"assessment.native.imports", "KAFKA_CONSUMER_GROUP":"assessment-native-worker",
               "PYTHONUNBUFFERED":"1", "PYTHONIOENCODING":"utf-8"}
        env.pop("ASSESSMENT_CRASH_AT", None)
        env.pop("ASSESSMENT_JOB_FAULT", None)
        result = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, timeout=40)
        (STATE / "migrate.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Migration failed; inspect .local/native-demo/migrate.log")
        report("starting_kafka")
        config = STATE / "kafka.properties"
        properties = {
            "process.roles":"broker,controller", "node.id":"1",
            "controller.quorum.voters":f"1@127.0.0.1:{PORTS['controller']}",
            "listeners":f"PLAINTEXT://127.0.0.1:{PORTS['kafka']},CONTROLLER://127.0.0.1:{PORTS['controller']}",
            "advertised.listeners":f"PLAINTEXT://127.0.0.1:{PORTS['kafka']}",
            "controller.listener.names":"CONTROLLER", "inter.broker.listener.name":"PLAINTEXT",
            "listener.security.protocol.map":"CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
            "log.dirs":(STATE / "kafka-data").as_posix(), "num.partitions":"1",
            "offsets.topic.replication.factor":"1", "transaction.state.log.replication.factor":"1",
            "transaction.state.log.min.isr":"1", "group.initial.rebalance.delay.ms":"0",
            "auto.create.topics.enable":"true", "num.network.threads":"2", "num.io.threads":"2"}
        config.write_text("\n".join(f"{key}={json.dumps(value, ensure_ascii=True)[1:-1]}" for key,value in properties.items()), encoding="ascii")
        base = [str(java), "-Xms128m", "-Xmx256m", f"-Dkafka.logs.dir={STATE / 'kafka-logs'}",
                f"-Dlog4j.configuration={(kafka / 'config/log4j.properties').as_uri()}", "-cp", str(kafka / "libs/*")]
        if not (STATE / "kafka-data/meta.properties").is_file():
            identifier = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
            result = await asyncio.to_thread(subprocess.run, [*base, "kafka.tools.StorageTool", "format", "-t", identifier, "-c", str(config)], capture_output=True, timeout=40)
            (STATE / "kafka-format.log").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("Kafka storage formatting failed")
        spawn("kafka", [*base, "kafka.Kafka", str(config)])
        report("starting_api_worker_web")
        spawn("api", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(PORTS["api"])], env=env)
        await http_ready(f"http://127.0.0.1:{PORTS['api']}/health")
        def spawn_worker():
            return spawn("worker", [sys.executable, "-m", "backend.app.worker"], env=env)
        async def stop_worker(process):
            containers["worker"].close()
            await asyncio.to_thread(stop_owned, process)
        worker = WorkerSupervisor(spawn_worker(), spawn_worker, stop_worker, diagnostic)
        web_env = {**env, "API_PROXY_TARGET":f"http://127.0.0.1:{PORTS['api']}"}
        spawn("web", [node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(PORTS["web"]), "--strictPort"], env=web_env, cwd=ROOT / "frontend")
        response = await http_ready(state["url"]+"/api/health")
        report("running")
        if not response.json()["index_published"]:
            async with httpx.AsyncClient(base_url=state["url"]+"/api", trust_env=False, timeout=10) as client:
                login = await client.post("/auth/token", json={"username":"alice", "password":"local-demo-change-me"})
                login.raise_for_status()
                client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
                job = await client.post("/jobs", json={"snapshot_id":response.json()["snapshot_id"], "idempotency_key":"native-demo-initial-index-v1"})
                job.raise_for_status()
                state["initial_index_job"] = job.json()["id"]
                report("running")
        next_sample = 0
        worker_private = 0
        while not stop_file.exists():
            sampled = False
            for name, process in processes.items():
                if name != "worker" and process.poll() is not None:
                    raise RuntimeError(f"{name} exited; inspect .local/native-demo/{name}.log")
            if time.monotonic() >= next_sample:
                entries = windows_processes()
                samples = {name: process_tree(process.pid, entries) for name, process in processes.items()}
                worker_private = sum(p.get("private_bytes", 0) for p in samples["worker"])
                diagnostic({"event": "resources", "processes": samples, "system": system_memory(), "worker": worker.status})
                next_sample = time.monotonic() + 5
                sampled = True
            previous_worker = (worker.status["state"], worker.status["pid"])
            await worker.tick(time.monotonic(), private_bytes=worker_private)
            state["worker"] = worker.status
            if worker.status["pid"] != previous_worker[1]:
                worker_private = 0
            if sampled or previous_worker != (worker.status["state"], worker.status["pid"]):
                report("running" if worker.status["state"] == "running" else "degraded")
            await asyncio.sleep(0.5)
    except Exception as error:
        state["error"] = str(error)
        report("failed")
        raise
    finally:
        report("stopping")
        for name in ("web", "worker", "api", "kafka"):
            if name in containers:
                containers.pop(name).close()
            if name in processes:
                await asyncio.to_thread(stop_owned, processes[name])
        if "postgres" in processes and processes["postgres"].poll() is None:
            result = await asyncio.to_thread(subprocess.run, [str(pg / "bin/pg_ctl.exe"), "-D", str(cluster), "-m", "fast", "-w", "stop"], capture_output=True, timeout=30)
            if result.returncode:
                await asyncio.to_thread(stop_owned, processes["postgres"])
        for handle in handles.values():
            handle.close()
        if drive and os.path.samefile(drive+"\\", ROOT / ".local"):
            subprocess.run(["subst", drive, "/D"], capture_output=True, check=True)
        report("stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-faults", action="store_true", help="Explicitly permit authenticated fault-case injection during evaluation")
    asyncio.run(run(evaluation_faults=parser.parse_args().evaluation_faults))
