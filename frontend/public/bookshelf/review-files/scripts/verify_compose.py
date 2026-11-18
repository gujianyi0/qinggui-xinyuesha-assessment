"""Verify real Linux Compose infrastructure using an isolated mock-chat profile.

Requires built images and the pinned model in this project's named models volume.
Never uses the native preview database, model credentials or QQ. Leaves volumes
and containers for review; use the printed Compose command to stop them.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


class Verification:
    def __init__(self, args):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,65}", args.label):
            raise ValueError("label must contain only lowercase ASCII letters, digits and hyphens")
        if not args.project.startswith("qinggui-assessment-verify") or not re.fullmatch(r"[a-z0-9-]+", args.project):
            raise ValueError("only a qinggui-assessment-verify project may be fault-tested")
        self.args = args
        self.output = ROOT / "docs/evidence" / args.label
        self.output.mkdir(parents=True, exist_ok=False)
        docker = shutil.which("docker")
        if not docker and os.name == "nt":
            docker = str(Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe")
        self.docker = docker or "docker"
        self.env = {**os.environ, "ASSESSMENT_ENV_FILE": ".env.example",
                    "PATH": str(Path(self.docker).parent) + os.pathsep + os.environ.get("PATH", "")}
        self.base = [self.docker, "compose", "--env-file", ".env.example", "-p", args.project,
                     "-f", "compose.yaml", "-f", "compose.verify.yaml"]
        self.commands = []
        self.report = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "project": args.project,
                       "scope": "Real Linux PostgreSQL/pgvector, Kafka, Redis, independent Worker and pinned CPU BGE; chat is a test double; no model fee or QQ", "checks": []}
        self.client = httpx.Client(base_url=args.url.rstrip("/") + "/api/", trust_env=False, timeout=150)
        self.phase, self.expected_outage = "startup", False
        self.finished = threading.Event()
        self.monitor = None

    def cli(self, *arguments, timeout=180, check=True, compose=True):
        command = [*(self.base if compose else [self.docker]), *arguments]
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, env=self.env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        number = len(self.commands) + 1
        record = {"command": command, "returncode": result.returncode,
                  "elapsed_seconds": round(time.monotonic() - started, 3)}
        self.commands.append(record)
        (self.output / f"command-{number:03d}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if check and result.returncode:
            raise RuntimeError(f"Docker command {number} failed ({result.returncode}); inspect command log")
        return result.stdout.strip()

    def check(self, name, **evidence):
        identifiers = self.cli("ps", "-q").splitlines()
        if identifiers:
            evidence["container_resources"] = [json.loads(row) for row in self.cli(
                "stats", "--no-stream", "--format", "{{json .}}", *identifiers, compose=False).splitlines()]
        self.report["checks"].append({"name": name, "passed": True, **evidence})
        print("PASS " + name, flush=True)
        self.save()

    def save(self):
        (self.output / "summary.json").write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self.output / "commands.json").write_text(json.dumps(self.commands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def wait(self, action, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = action()
            if value:
                return value
            time.sleep(0.5)
        raise TimeoutError(f"condition timed out during {self.phase}")

    def request(self, method, path, *, status=200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        assert response.status_code == status, (path, response.status_code, response.text[:500])
        return response

    def health(self):
        try:
            response = self.client.get("health", timeout=3)
            return response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    def observe(self):
        with httpx.Client(trust_env=False, timeout=4) as client, (self.output / "http-monitor.jsonl").open("w", encoding="utf-8") as handle:
            while not self.finished.is_set():
                row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "phase": self.phase,
                       "expected_outage": self.expected_outage}
                for key, url in (("web", self.args.url), ("api", self.args.url.rstrip("/") + "/api/health")):
                    try:
                        row[key] = client.get(url).status_code
                    except httpx.HTTPError as error:
                        row[key] = type(error).__name__
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                self.finished.wait(1)

    def sql(self, query):
        return self.cli("exec", "-T", "postgres", "psql", "-U", "assessment", "-d", "assessment", "-At", "-c", query)

    def python(self, script):
        return self.cli("exec", "-T", "api", "python", "-c", script)

    def inspect(self, service):
        identifier = self.cli("ps", "--all", "-q", service)
        assert identifier and "\n" not in identifier
        # Avoid dumping Config.Env, which may contain credentials in other profiles.
        raw = self.cli("inspect", "--format", '{{json .State}}|{{.RestartCount}}|{{.Id}}', identifier, compose=False)
        state, count, identifier = raw.split("|")
        return {**json.loads(state), "restart_count": int(count), "id": identifier}

    def kill(self, service):
        identifier = self.cli("ps", "--all", "-q", service)
        assert identifier and "\n" not in identifier
        state = self.inspect(service)
        assert state["Running"] and state["Pid"] > 1
        namespace = self.cli("exec", "-T", service, "python", "-c", "import os; print(os.readlink('/proc/1/ns/pid'))")
        # A peer signal can be ignored by namespace init; docker kill is an
        # operator stop and can suppress restart policy. Use a tightly scoped
        # helper in the daemon's PID namespace, checking the target namespace
        # again before signalling. The helper has no network or data mounts.
        helper = ("import os,signal; "
                  f"assert os.readlink('/proc/{state['Pid']}/ns/pid') == {namespace!r}; "
                  f"os.kill({state['Pid']},signal.SIGKILL)")
        self.cli("run", "--rm", "--network", "none", "--pid", "host", "--read-only",
                 "--cap-drop", "ALL", "--cap-add", "KILL", "--cap-add", "SYS_PTRACE", "--entrypoint", "python",
                 "qinggui-assessment-api:latest", "-c", helper, compose=False)

    def worker(self, *, crash=None, fault=None):
        override = ROOT / ".local" / (self.args.label + "-worker.json")
        extra = {"ENABLE_TEST_FAULTS": str(bool(crash or fault)).lower(),
                 "ASSESSMENT_CRASH_AT": crash or "", "ASSESSMENT_JOB_FAULT": fault or ""}
        override.write_text(json.dumps({"services": {"worker": {"restart": "no" if crash else "on-failure:5", "environment": extra}}}), encoding="utf-8")
        self.cli("-f", str(override), "up", "-d", "--no-deps", "--force-recreate", "worker")

    def submit(self, key):
        return self.request("POST", "jobs", status=202,
                            json={"snapshot_id": self.snapshot, "idempotency_key": self.args.label + ":" + key}).json()

    def job(self, identifier):
        return self.request("GET", f"jobs/{identifier}").json()

    def terminal(self, identifier, expected="succeeded", timeout=240):
        def ready():
            job = self.job(identifier)
            if job["status"] in {"failed", "succeeded", "cancelled"}:
                assert job["status"] == expected, job
                return job
        return self.wait(ready, timeout)

    def publication(self):
        return self.sql("SELECT job_id FROM published_indexes LIMIT 1")

    def offsets(self, *, end=False):
        expression = "c.get_watermark_offsets(TopicPartition(s.kafka_topic,0),timeout=10)[1]" if end else "c.committed([TopicPartition(s.kafka_topic,0)],timeout=10)[0].offset"
        return int(self.python("from confluent_kafka import Consumer,TopicPartition; from backend.app.config import Settings; s=Settings(); c=Consumer({'bootstrap.servers':s.kafka_bootstrap_servers,'group.id':s.kafka_consumer_group,'enable.auto.commit':False}); print(" + expression + "); c.close()"))

    def model_hashes(self):
        return json.loads(self.python("import hashlib,json; from backend.app.config import Settings; from backend.app.embedding_assets import pinned_model_path; p=pinned_model_path(Settings()); print(json.dumps({str(f.relative_to(p)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in sorted(p.rglob('*')) if f.is_file()}))"))

    def assert_chunks(self, job_id, attempts):
        row = json.loads(self.sql(f"SELECT json_build_object('attempts',j.attempts,'chunks',(SELECT count(*) FROM indexed_chunks c WHERE c.job_id=j.id AND c.generation=j.generation),'vectors',(SELECT count(*) FROM vector_chunks v WHERE v.job_id=j.id AND v.generation=j.generation),'dimensions',(SELECT min(vector_dims(embedding)) FROM vector_chunks v WHERE v.job_id=j.id AND v.generation=j.generation),'prior_staging_chunks',(SELECT count(*) FROM indexed_chunks c WHERE c.job_id=j.id AND c.generation<>j.generation),'publications',(SELECT count(*) FROM published_indexes p WHERE p.job_id=j.id AND p.generation=j.generation)) FROM jobs j WHERE j.id='{job_id}'"))
        assert all(row[key] == value for key, value in {"attempts": attempts, "chunks": 659, "vectors": 659, "dimensions": 512, "publications": 1}.items()), row
        return row

    def search(self, query, *, cache_probe=False):
        script = """import asyncio, hashlib, json
from backend.app.config import Settings
from backend.app.catalog import Catalog, Embedder, KnowledgeSearch
from backend.app.db import Database
from backend.app.models import PublishedIndex
async def main():
 s=Settings(); d=Database(s); c=Catalog(s); e=Embedder(s); k=KnowledgeSearch(c,d,e,s)
 count=0
 original=e.encode
 async def encode(*args,**kwargs):
  nonlocal count
  count+=1
  return await original(*args,**kwargs)
 e.encode=encode
 try:
  first=await k.search(QUERY,c.active_id)
  initial=count
  if PROBE:
   second=await k.search(QUERY,c.active_id)
   assert second==first and count==initial
  async with d.sessions() as db:
   p=await db.get(PublishedIndex,c.active_id)
  raw=f'policy-v2:{c.active_id}:{p.job_id}:{p.generation}:{s.embedding_mode}:{s.embedding_revision}:{QUERY}:5'
  key='retrieval:'+hashlib.sha256(raw.encode()).hexdigest()
  ttl=None
  try: ttl=await k.cache.ttl(key)
  except Exception: pass
  assert first['mode']=='pgvector' and first['items']
  print(json.dumps({'mode':first['mode'],'sources':[x['source']['id'] for x in first['items']], 'encode_calls':count,'ttl':ttl,'cache_key':key}))
 finally:
  await k.close(); await d.close()
asyncio.run(main())
""".replace("QUERY", repr(query)).replace("PROBE", repr(cache_probe))
        return json.loads(self.python(script))

    def run(self):
        self.cli("config", "--quiet")
        self.cli("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=220)
        self.wait(self.health)
        health = self.health()
        assert health["database"] == "postgresql" and health["model_mode"] == "mock" and health["embedding_mode"] == "local"
        assert not health["fault_injection_enabled"] and health["cache"] == "available"
        assert health["budget"]["spent_cny"] == 0 and not health["index_published"], "use a fresh verification project"
        self.snapshot = health["snapshot_id"]
        self.phase = "baseline"
        self.monitor = threading.Thread(target=self.observe, daemon=True)
        self.monitor.start()
        package_version = self.python("from importlib.metadata import version; print(version('qinggui-xinyuesha-assessment'))")
        assert package_version == (ROOT / "VERSION").read_text(encoding="utf-8").strip() + ".0"
        database_sha = self.python("import hashlib; from pathlib import Path; import backend.app.db; print(hashlib.sha256(Path(backend.app.db.__file__).read_bytes()).hexdigest())")
        assert database_sha == hashlib.sha256((ROOT / "backend/app/db.py").read_bytes()).hexdigest()
        self.check("seven_service_start_and_migration", health=health,
                   package_version=package_version,
                   database_module_sha256=database_sha,
                   postgres_version=self.sql("SHOW server_version"),
                   pgvector_version=self.sql("SELECT extversion FROM pg_extension WHERE extname='vector'"),
                   migration=self.sql("SELECT version_num FROM alembic_version"))
        alice = self.request("POST", "auth/token", json={"username": "alice", "password": "local-demo-change-me"}).json()
        bob = self.request("POST", "auth/token", json={"username": "bob", "password": "local-demo-change-me"}).json()
        self.client.headers["Authorization"] = "Bearer " + alice["access_token"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            submitted = list(pool.map(lambda _: self.submit("concurrent"), range(8)))
        assert len({j["id"] for j in submitted}) == 1
        first = self.terminal(submitted[0]["id"])
        self.check("eight_concurrent_submissions_one_real_bge_index", job_id=first["id"], **self.assert_chunks(first["id"], 1))
        cached = self.search("空城无手牌的目标限制 " + self.args.label, cache_probe=True)
        assert 0 < cached["ttl"] <= 300 and cached["encode_calls"] == 1, cached
        cache_started = time.monotonic()
        self.check("pgvector_retrieval_and_redis_cache_hit", **cached)

        session = self.request("POST", "sessions", status=201, json={"title": "Docker持久化验收"}).json()
        stream = self.request("POST", f"sessions/{session['id']}/runs", json={"message": "诸葛亮有哪些技能？"}).text
        assert "event: completed" in stream and "诸葛亮" in stream
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        run_id = next(event["run_id"] for event in events if "run_id" in event)
        run = self.request("GET", "runs/" + run_id).json()
        assert run["status"] == "completed" and run["citations"]
        (self.output / "mock-chat-sse.txt").write_text(stream, encoding="utf-8")
        draft = self.request("POST", "feedback-drafts", status=201, json={"actual": "容器集成测试虚构反馈", "session_id": session["id"]}).json()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            confirmed = list(pool.map(lambda _: self.request("POST", f"feedback-drafts/{draft['id']}/confirm", json={"revision": 1}).json(), range(8)))
        assert len({r["id"] for r in confirmed}) == 1
        for path in (f"sessions/{session['id']}/messages", f"runs/{run_id}", f"jobs/{first['id']}"):
            self.request("GET", path, status=404, headers={"Authorization": "Bearer " + bob["access_token"]})
        self.request("PATCH", f"feedback-drafts/{draft['id']}", status=404,
                     json={"revision": 1, "actual": "不得改写其他身份的草稿"},
                     headers={"Authorization": "Bearer " + bob["access_token"]})
        self.check("mock_stream_citations_feedback_race_and_four_identity_boundaries", session_id=session["id"], run_id=run_id, feedback_id=confirmed[0]["id"])

        self.phase = "cancellation"
        self.cli("stop", "worker")
        queued = self.submit("queue-cancel")
        self.request("POST", f"jobs/{queued['id']}/cancel")
        assert self.terminal(queued["id"], "cancelled")["attempts"] == 0
        self.cli("start", "worker")
        active = self.submit("active-cancel")
        self.wait(lambda: (j if (j := self.job(active["id"]))["progress"] > 0 else None))
        self.request("POST", f"jobs/{active['id']}/cancel")
        self.terminal(active["id"], "cancelled")
        assert self.publication() == first["id"]
        self.check("queued_and_running_cancel_keep_published_index", queued=queued["id"], running=active["id"])

        self.phase = "worker-crash"
        active = self.submit("worker-crash")
        self.wait(lambda: (j if (j := self.job(active["id"]))["progress"] > 0 else None))
        before = self.inspect("worker")
        self.kill("worker")
        self.wait(lambda: (s if (s := self.inspect("worker"))["Running"] and s["restart_count"] > before["restart_count"] else None))
        restored = self.terminal(active["id"])
        self.check("docker_worker_sigkill_restart_and_60_second_lease_recovery", job_id=active["id"], generation=restored["generation"], **self.assert_chunks(active["id"], 2))

        self.phase = "business-before-offset"
        self.worker(crash="after_business_commit")
        self.wait(lambda: self.offsets() == self.offsets(end=True))
        before_offset = self.offsets()
        committed = self.submit("commit-before-offset")
        exited = self.wait(lambda: (s if not (s := self.inspect("worker"))["Running"] else None))
        assert exited["ExitCode"] == 82, exited
        self.terminal(committed["id"])
        assert self.offsets() == before_offset
        self.worker()
        after_offset = self.wait(lambda: (n if (n := self.offsets()) > before_offset else None))
        self.check("business_commit_before_kafka_offset_crash_and_replay", job_id=committed["id"], exit_code=82, offset_before=before_offset, offset_after=after_offset, **self.assert_chunks(committed["id"], 1))
        self.python("import json; from confluent_kafka import Producer; from backend.app.config import Settings; s=Settings(); p=Producer({'bootstrap.servers':s.kafka_bootstrap_servers}); p.produce(s.kafka_topic,key=" + repr(committed["id"]) + ",value=json.dumps({'job_id':" + repr(committed["id"]) + ",'expected_generation':0})); assert p.flush(10)==0")
        self.wait(lambda: self.offsets() > after_offset)
        self.check("duplicate_kafka_delivery_no_duplicate_result", job_id=committed["id"], **self.assert_chunks(committed["id"], 1))

        self.phase = "outbox-before-mark"
        self.worker(crash="after_publish")
        interrupted = self.submit("outbox-after-publish")
        exited = self.wait(lambda: (s if not (s := self.inspect("worker"))["Running"] else None))
        assert exited["ExitCode"] == 81
        assert self.sql(f"SELECT delivered FROM outbox WHERE job_id='{interrupted['id']}'") == "f"
        self.worker()
        self.terminal(interrupted["id"])
        self.check("outbox_sent_before_mark_crash_and_replay", job_id=interrupted["id"], exit_code=81, **self.assert_chunks(interrupted["id"], 1))

        self.phase = "retry-exhaustion"
        self.worker(fault="temporary")
        retry = self.submit("retry-exhaustion")
        failed = self.terminal(retry["id"], "failed")
        assert failed["attempts"] == 3 and failed["error"]
        timestamps = sorted(dt.datetime.fromisoformat(a["created_at"]) for a in failed["attempt_records"])
        gaps = [(b-a).total_seconds() for a, b in zip(timestamps, timestamps[1:])]
        assert len(gaps) == 2 and gaps[0] >= 10 and gaps[1] >= 30, gaps
        self.check("three_finite_retries_with_production_10_30_second_delays", job_id=retry["id"], attempts=failed["attempts"], error=failed["error"], attempt_gaps_seconds=gaps)
        self.cli("stop", "worker")
        bad = self.submit("bad-input")
        self.sql(f"UPDATE jobs SET snapshot_id='invalid-compose-fixture' WHERE id='{bad['id']}'")
        good = self.submit("after-bad")
        self.worker()
        assert self.terminal(bad["id"], "failed")["attempts"] == 1
        self.terminal(good["id"])
        self.check("bad_input_ends_without_blocking_next_job", bad_job=bad["id"], good_job=good["id"])

        self.phase = "natural-cache-expiry"
        remaining = max(0, 301 - (time.monotonic() - cache_started))
        deadline = time.monotonic() + remaining
        while time.monotonic() < deadline:
            print(f"WAIT natural Redis TTL {deadline-time.monotonic():.0f}s", flush=True)
            time.sleep(min(25, deadline - time.monotonic()))
        ttl = int(self.cli("exec", "-T", "redis", "redis-cli", "TTL", cached["cache_key"]))
        assert ttl == -2
        self.check("default_300_second_cache_natural_expiry", ttl_after=ttl, elapsed_seconds=round(time.monotonic()-cache_started, 3))

        self.phase = "redis-outage"
        self.cli("stop", "redis")
        health = self.health()
        assert health and health["cache"] == "unavailable_fallback"
        fallback = self.search("Redis停机回源 空城")
        self.cli("start", "redis")
        self.wait(lambda: (h if (h := self.health()) and h["cache"] == "available" else None))
        self.check("redis_outage_pgvector_fallback_and_reconnect", fallback=fallback)

        self.phase = "kafka-outage"
        self.cli("stop", "kafka")
        offline = self.submit("kafka-offline")
        assert self.job(offline["id"])["status"] == "queued"
        assert self.sql(f"SELECT delivered FROM outbox WHERE job_id='{offline['id']}'") == "f"
        assert self.health()
        self.cli("start", "kafka")
        self.terminal(offline["id"])
        self.check("kafka_outage_durable_outbox_and_recovery", job_id=offline["id"])

        self.phase, self.expected_outage = "postgres-outage", True
        self.cli("stop", "postgres")
        assert self.client.get("health").status_code == 503
        assert self.client.get("jobs").status_code == 503
        self.cli("start", "postgres")
        self.wait(self.health)
        self.expected_outage = False
        self.check("postgres_outage_explained_503_and_pool_reconnect")

        self.phase, self.expected_outage = "api-crash", True
        before = self.inspect("api")
        self.kill("api")
        self.wait(lambda: (s if (s := self.inspect("api"))["Running"] and s["restart_count"] > before["restart_count"] else None), 40)
        self.wait(self.health)
        self.expected_outage = False
        self.check("api_process_crash_automatic_restart")

        self.phase, self.expected_outage = "container-recreation", True
        self.wait(lambda: self.offsets() == self.offsets(end=True))
        kafka_before = self.offsets()
        model_before = self.model_hashes()
        assert model_before and "model.safetensors" in model_before
        old_pg = self.inspect("postgres")["id"]
        volumes_before = sorted(self.cli("volume", "ls", "--filter", "label=com.docker.compose.project=" + self.args.project, "--format", "{{.Name}}", compose=False).splitlines())
        self.cli("down", timeout=180)  # Deliberately never --volumes.
        self.cli("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=220)
        self.wait(self.health)
        assert self.inspect("postgres")["id"] != old_pg
        assert sorted(self.cli("volume", "ls", "--filter", "label=com.docker.compose.project=" + self.args.project, "--format", "{{.Name}}", compose=False).splitlines()) == volumes_before
        assert self.offsets() == kafka_before and self.model_hashes() == model_before
        assert self.request("GET", f"sessions/{session['id']}/messages").json()
        assert self.request("GET", f"runs/{run_id}").json()["text"] == run["text"]
        assert self.request("GET", "feedback").json()[0]["id"] == confirmed[0]["id"]
        assert self.job(first["id"])["status"] == "succeeded" and self.health()["index_published"]
        assert self.sql("SELECT count(*) FROM feedback") == "1"
        self.expected_outage = False
        self.check("down_up_new_containers_preserve_database_kafka_and_model_volumes", volumes=volumes_before, kafka_committed_offset=kafka_before, model_sha256=model_before, old_postgres_id=old_pg, new_postgres_id=self.inspect("postgres")["id"])
        self.phase = "final"
        self.report["final_health"] = self.health()
        assert self.report["final_health"]["budget"]["spent_cny"] == 0
        assert not self.report["final_health"]["fault_injection_enabled"]
        self.report["passed"] = True

    def close(self):
        self.finished.set()
        if self.monitor:
            self.monitor.join(timeout=10)
            rows = [json.loads(line) for line in (self.output / "http-monitor.jsonl").read_text(encoding="utf-8").splitlines()]
            failures = [row for row in rows if not row["expected_outage"] and (row["web"] != 200 or row["api"] != 200)]
            self.report["monitor"] = {"samples": len(rows), "unexpected_failures": len(failures), "failure_samples": failures[:20]}
            if failures:
                self.report["passed"] = False
        self.report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        for service in ("api", "worker", "kafka", "postgres", "redis"):
            try:
                self.cli("logs", "--no-color", "--tail", "200", service, check=False, timeout=20)
            except subprocess.SubprocessError:
                pass
        self.save()
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--project", default="qinggui-assessment-verify")
    parser.add_argument("--url", default="http://127.0.0.1:15175")
    args = parser.parse_args()
    verification = Verification(args)
    sources = [ROOT / "compose.yaml", ROOT / "compose.verify.yaml", ROOT / "backend/app/db.py", Path(__file__)]
    verification.report["source_sha256"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    try:
        verification.run()
    except Exception as error:
        verification.report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        verification.close()
    assert verification.report["passed"], "HTTP monitor failed; inspect summary"
    print(json.dumps({"passed": True, "checks": len(verification.report["checks"]), "evidence": str(verification.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
