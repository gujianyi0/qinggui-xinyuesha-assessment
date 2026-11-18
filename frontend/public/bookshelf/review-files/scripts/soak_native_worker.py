"""Real-clock soak of the owned native preview; never calls a paid chat model.

Intentionally kills only this preview's Worker, while probing web/API continuously.
"""
import argparse
import asyncio
import ctypes
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx

from backend.app.config import ROOT
from backend.app.resource_metrics import process_tree, system_memory

STATE = ROOT / ".local/native-demo/status.json"


def state():
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if value["owner"] != "qinggui-assessment-native-demo" or Path(value["project"]).resolve() != ROOT.resolve():
        raise ValueError("Refusing to control a process outside this project")
    return value


async def until(check, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = await check()
        if value:
            return value
        await asyncio.sleep(0.5)
    raise TimeoutError("soak condition not reached")


async def run(args):
    if Path(args.label).name != args.label:
        raise ValueError("label must be a single directory name")
    output = ROOT / "docs/evidence" / args.label
    output.mkdir(exist_ok=False)
    start = time.monotonic()
    initial = state()
    assert initial.get("worker", {}).get("state") == "running"
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "planned_seconds": args.seconds,
              "scope": "Real native PostgreSQL/Kafka/Worker/local BGE; web/API probes; no paid model calls",
              "initial_state": initial, "checks": [], "probe_failures": [], "jobs": []}
    stop = asyncio.Event()
    samples = []
    async with httpx.AsyncClient(base_url=initial["url"], trust_env=False, timeout=5) as client:
        login = await client.post("/api/auth/token", json={"username": "alice", "password": "local-demo-change-me"})
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        snapshot = (await client.get("/api/health")).json()["snapshot_id"]

        async def probe():
            with (output / "samples.jsonl").open("w", encoding="utf-8") as file:
                while not stop.is_set():
                    row = {"at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic()-start, 3)}
                    try:
                        web, api = await asyncio.gather(client.get("/"), client.get("/api/health"))
                        row.update(web_status=web.status_code, api_status=api.status_code)
                        current = state()
                        row.update(worker=current.get("worker"), processes=process_tree(current["worker_pid"]), system=system_memory())
                        assert web.status_code == api.status_code == 200
                        assert all(current[key] == initial[key] for key in ("web_pid", "api_pid", "postgres_pid"))
                    except Exception as error:
                        row["error_type"] = type(error).__name__
                        report["probe_failures"].append(row.copy())
                    samples.append(row)
                    file.write(json.dumps(row, ensure_ascii=False) + "\n")
                    file.flush()
                    with (output / "progress.json").open("w", encoding="utf-8") as progress:
                        json.dump({"elapsed_seconds": row["elapsed_seconds"], "samples": len(samples),
                                   "probe_failures": len(report["probe_failures"]), "checks": report["checks"],
                                   "worker": row.get("worker")}, progress, ensure_ascii=False, indent=2)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=2)
                    except TimeoutError:
                        pass

        async def get_job(identifier, *, wanted=None, progress=False):
            response = await client.get("/api/jobs/"+identifier)
            response.raise_for_status()
            job = response.json()
            if wanted and job["status"] not in wanted:
                return None
            if progress and not (job["status"] == "running" and 0 < job["progress"] < 95):
                return None
            return job

        async def new_job(key):
            response = await client.post("/api/jobs", json={"snapshot_id": snapshot, "idempotency_key": args.label+":"+key})
            response.raise_for_status()
            return response.json()

        async def kill_worker():
            current = state()
            pid = current["worker_pid"]
            assert current["supervisor_pid"] == initial["supervisor_pid"]
            result = await asyncio.to_thread(subprocess.run, ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20)
            if result.returncode:
                raise RuntimeError("Could not terminate owned Worker tree")
            async def replaced():
                next_state = state()
                return next_state if next_state["worker_pid"] != pid and next_state["worker"]["state"] == "running" else None
            restored = await until(replaced, 30)
            report["checks"].append({"name": "worker_replaced_website_preserved", "old_pid": pid,
                                     "new_pid": restored["worker_pid"], "elapsed_seconds": round(time.monotonic()-start, 2), "passed": True})

        async def lock_status():
            # Real Windows sharing denial, reproducing the failed 02 run without stopping services.
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateFileW(str(STATE), 0x80000000, 1, None, 3, 0, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            before = state()["updated_at"]
            try:
                await asyncio.sleep(12)
                assert state()["updated_at"] == before, "lock did not deny replacement"
            finally:
                kernel.CloseHandle(handle)
            async def resumed():
                return state()["updated_at"] != before
            await until(resumed, 15)
            report["checks"].append({"name": "status_file_real_lock_survived_and_resumed", "lock_seconds": 12, "passed": True})

        async def restart_broker():
            current = state()
            old = current["kafka_pid"]
            killed = await asyncio.to_thread(subprocess.run, ["taskkill", "/PID", str(old), "/T", "/F"],
                                            capture_output=True, timeout=20)
            assert killed.returncode == 0
            queued = await new_job("broker-restart")
            async def replaced():
                new = state()
                return new if new["kafka_pid"] != old and new["kafka"]["state"] == "running" else None
            new = await until(replaced, 30)
            queued = await until(lambda: get_job(queued["id"], wanted={"succeeded"}), 180)
            report["jobs"].append(queued)
            await released()
            report["checks"].append({"name": "broker_crash_outbox_delivery_website_preserved", "old_pid": old,
                                     "new_pid": new["kafka_pid"], "passed": True})

        async def released():
            await asyncio.sleep(3)
            rows = process_tree(state()["worker_pid"])
            private = sum(item.get("private_bytes", 0) for item in rows)
            assert private < 192 * 1024**2, f"Worker retained {private} bytes after job"
            report["checks"].append({"name": "job_memory_released", "private_bytes": private,
                                     "elapsed_seconds": round(time.monotonic()-start, 2), "passed": True})

        async def wait_at(fraction):
            while time.monotonic()-start < args.seconds*fraction:
                await asyncio.sleep(1)

        async def published():
            connection = await asyncpg.connect(host="127.0.0.1", port=initial["ports"]["postgres"], user="assessment", database="assessment")
            try:
                return dict(await connection.fetchrow("SELECT job_id,generation FROM published_indexes WHERE snapshot_id=$1", snapshot))
            finally:
                await connection.close()

        task = asyncio.create_task(probe())
        try:
            first = await new_job("crash-running")
            await until(lambda: get_job(first["id"], progress=True))
            await kill_worker()
            first = await until(lambda: get_job(first["id"], wanted={"succeeded"}), 240)
            assert first["attempts"] == 2
            report["jobs"].append(first)
            report["checks"].append({"name": "active_job_lease_recovery", "attempts": first["attempts"], "passed": True})
            await released()
            print("PASS active Worker crash, lease recovery and model memory release", flush=True)

            await lock_status()
            print("PASS real status-file sharing lock without website shutdown", flush=True)
            await restart_broker()
            print("PASS Kafka crash/restart and durable queued import", flush=True)

            for number, fraction in enumerate((1/6, 1/2), 1):
                await wait_at(fraction)
                job = await new_job(f"repeat-{number}")
                job = await until(lambda: get_job(job["id"], wanted={"succeeded"}), 180)
                report["jobs"].append(job)
                await released()
                print(f"PASS repeat import {number}", flush=True)

            await wait_at(2/3)
            previous = await published()
            job = await new_job("cancel-running")
            await until(lambda: get_job(job["id"], progress=True))
            cancelled = await client.post("/api/jobs/"+job["id"]+"/cancel")
            cancelled.raise_for_status()
            job = await until(lambda: get_job(job["id"], wanted={"cancelled"}), 60)
            assert await published() == previous
            report["jobs"].append(job)
            report["checks"].append({"name": "cancel_releases_model_and_preserves_publication", "passed": True})
            await released()
            print("PASS cancellation and publication fence", flush=True)

            await wait_at(5/6)
            await kill_worker()
            await released()
            print("PASS idle Worker crash without website restart", flush=True)
            await wait_at(1)
            report["passed"] = not report["probe_failures"]
            assert report["passed"], "web/API availability regression"
        except BaseException as error:
            report.update(passed=False, error_type=type(error).__name__, error=str(error))
            raise
        finally:
            stop.set()
            await task
            report.update(finished_at=datetime.now(timezone.utc).isoformat(), actual_seconds=round(time.monotonic()-start, 3),
                          sample_count=len(samples), final_state=state())
            (output/"summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            print(json.dumps({k: report[k] for k in ("passed", "actual_seconds", "sample_count")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--seconds", type=int, default=3600)
    arguments = parser.parse_args()
    if arguments.seconds < 900:
        parser.error("Use at least 900 real seconds; shorter runs are not a soak")
    asyncio.run(run(arguments))
