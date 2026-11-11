"""Verify migrated history, live continuation, workers, ledger and cold restart.

Run from the project root: python -m scripts.verify_docker_cutover --label ...
"""
import argparse
import json
import math
import socket
import subprocess
import time
from datetime import datetime, timezone

import httpx

from backend.app.config import ROOT, Settings
from backend.app.database_transfer import assert_same_database
from backend.app.deployment import read_deployment
from scripts.audit_eval_sources import audit_citation, fingerprint, sources_in
from scripts.docker_live import run_compose


def main(label):
    if not label or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in label):
        raise ValueError("Use a unique lowercase ASCII label")
    state = read_deployment()
    if state.get("primary") != "docker" or state.get("phase") != "active":
        raise ValueError("Docker must be the checked active primary")
    source_dir = ROOT / ".local/migrations" / state["label"]
    source = json.loads((source_dir / "fingerprint.json").read_text(encoding="utf-8"))
    probes = json.loads((source_dir / "http-probes.json").read_text(encoding="utf-8"))
    output = ROOT / "docs/evidence" / label
    output.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "source_budget": source["budget"],
              "scope": "Actual Docker primary, one additional paid continuation in an old migrated session; raw secret/backup not published"}
    client = httpx.Client(base_url="http://127.0.0.1:15174/api/", timeout=150, trust_env=False)

    def save():
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def passed(name, **values):
        report["checks"].append({"name": name, "passed": True, **values})
        save()
        print("PASS " + name, flush=True)

    def request(method, path, status=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def command(*args, timeout=180):
        result = run_compose(*args, timeout=timeout)
        (output / f"docker-{len(list(output.glob('docker-*.log')))+1:02d}.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Docker verification command failed; inspect local evidence")
        return result.stdout.decode("utf-8").strip()

    def wait(action, timeout=240):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = action()
            if value:
                return value
            time.sleep(0.5)
        raise TimeoutError("Cutover verification condition timed out")

    def inspect_ledger():
        script = """import asyncio,json
import asyncpg
from sqlalchemy.engine import make_url
from backend.app.config import Settings
async def main():
 c=await asyncpg.connect(make_url(Settings().database_url).set(drivername='postgresql').render_as_string(hide_password=False))
 try:
  result={'budget':dict(await c.fetchrow('SELECT id,spent,reserved FROM budget_account WHERE id=1')),'charged_sum':float(await c.fetchval('SELECT COALESCE(sum(charged_cny),0) FROM usage_records')),'usage_count':await c.fetchval('SELECT count(*) FROM usage_records'),'unsettled':await c.fetchval('SELECT count(*) FROM usage_records WHERE NOT settled'),'outbox_pending':await c.fetchval('SELECT count(*) FROM outbox WHERE NOT delivered')}
  print(json.dumps(result))
 finally: await c.close()
asyncio.run(main())
"""
        return json.loads(command("exec", "-T", "api", "python", "-c", script))

    try:
        settings = Settings()
        alice = request("POST", "auth/token", json={"username": "alice", "password": settings.demo_password})
        bob = request("POST", "auth/token", json={"username": "bob", "password": settings.demo_password})
        client.headers["Authorization"] = "Bearer " + alice["access_token"]
        bob_header = {"Authorization": "Bearer " + bob["access_token"]}
        old_session = next(p for p in probes["sessions"] if p["user_id"] == alice["user"]["id"])
        old_messages = request("GET", f"sessions/{old_session['id']}/messages")
        assert len(old_messages) == old_session["messages"]
        assert request("GET", f"runs/{probes['run']['id']}")["status"] == "completed"
        request("GET", f"sessions/{old_session['id']}/messages", status=404, headers=bob_header)
        request("GET", f"runs/{probes['run']['id']}", status=404, headers=bob_header)
        passed("migrated_history_and_original_two_identities", session_id=old_session["id"], old_messages=len(old_messages), old_run_id=probes["run"]["id"], cross_identity_status=404)

        rejected = subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/start_native.ps1")], cwd=ROOT, capture_output=True, timeout=20)
        (output / "stale-native-start-blocked.log").write_bytes(rejected.stdout + rejected.stderr)
        assert rejected.returncode != 0
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", 15433)) != 0
        passed("stale_native_writer_blocked_and_source_postgres_stopped")

        message = "在当前固定资料快照中，诸葛亮的观星和空城各是什么？请给出来源。"
        with client.stream("POST", f"sessions/{old_session['id']}/runs", json={"message": message}) as response:
            assert response.status_code == 200
            events = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
        identifier = next(e["run_id"] for e in events if "run_id" in e)
        continuation = request("GET", "runs/" + identifier)
        assert continuation["status"] == "completed" and all(term in continuation["text"] for term in ("观星", "空城")) and continuation["citations"]
        receipts = {fingerprint(s) for call in continuation["tool_calls"] for s in sources_in(call.get("result"))}
        issues = [item for s in continuation["citations"] for item in audit_citation(s, receipts, user_messages=[message], session_id=old_session["id"])]
        assert not issues, issues
        after_messages = request("GET", f"sessions/{old_session['id']}/messages")
        by_id = {m["id"]: m for m in after_messages}
        assert all(by_id[m["id"]] == m for m in old_messages) and len(after_messages) == len(old_messages) + 2
        (output / "old-session-live-continuation.json").write_text(json.dumps({"input": message, "run": continuation}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        passed("old_migrated_session_live_continuation_preserves_old_messages", run_id=identifier, citation_count=len(continuation["citations"]), citation_issues=0)

        health = request("GET", "health")
        job = request("POST", "jobs", status=202, json={"snapshot_id": health["snapshot_id"], "idempotency_key": label + ":import"})
        def job_done():
            row = request("GET", "jobs/" + job["id"])
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                assert row["status"] == "succeeded", row.get("error")
                return row
        complete = wait(job_done)
        assert complete["result"]["chunks"] == 659 and complete["attempts"] == 1
        passed("new_live_kafka_worker_import_after_migration", job_id=job["id"], result=complete["result"], attempts=1)
        command("stop", "worker")
        cancelled = request("POST", "jobs", status=202, json={"snapshot_id": health["snapshot_id"], "idempotency_key": label + ":cancel"})
        row = request("POST", "jobs/" + cancelled["id"] + "/cancel")
        assert row["status"] == "cancelled" and row["attempts"] == 0
        command("start", "worker")
        wait(lambda: inspect_ledger()["outbox_pending"] == 0)
        passed("new_job_cancel_and_outbox_progress_after_migration", job_id=cancelled["id"])

        ledger = inspect_ledger()
        assert ledger["unsettled"] == 0 and abs(ledger["budget"]["reserved"]) < 1e-8
        assert ledger["budget"]["spent"] > source["budget"]["spent"] and ledger["budget"]["spent"] < 200
        assert math.isclose(ledger["charged_sum"], ledger["budget"]["spent"], abs_tol=1e-8)
        before = json.loads(command("exec", "-T", "api", "python", "scripts/fingerprint_database.py"))
        command("down")  # Never remove the named volumes.
        command("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=220)
        after = json.loads(command("exec", "-T", "api", "python", "scripts/fingerprint_database.py"))
        assert_same_database(before, after)
        assert request("GET", "runs/" + identifier)["text"] == continuation["text"]
        assert request("GET", "jobs/" + job["id"])["status"] == "succeeded"
        request("GET", f"sessions/{old_session['id']}/messages", status=404, headers=bob_header)
        passed("cold_down_up_preserves_all_current_tables_history_and_fees", tables=len(before["tables"]), ledger=ledger, database_content_equal=True)
        assert inspect_ledger() == ledger
        report.update(passed=True, final_health=request("GET", "health"), ledger=ledger,
                      additional_estimate_cny=ledger["budget"]["spent"]-source["budget"]["spent"])
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        client.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({"passed": True, "checks": len(report["checks"]), "spent_cny": report["ledger"]["budget"]["spent"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    main(parser.parse_args().label)
