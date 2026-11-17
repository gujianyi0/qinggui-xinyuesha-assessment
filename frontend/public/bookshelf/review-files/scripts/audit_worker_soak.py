"""Independently verify the finished real-clock soak before preparing release docs."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone

from backend.app.config import ROOT


def audit(label):
    folder = (ROOT / "docs/evidence" / label).resolve()
    if not folder.is_relative_to((ROOT / "docs/evidence").resolve()):
        raise ValueError("Evidence directory must stay inside project")
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (folder / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
    assert summary["passed"] is True and summary["actual_seconds"] >= 3600
    implementation = json.loads((folder / "implementation.json").read_text(encoding="utf-8"))
    assert len(rows) == summary["sample_count"] and not summary["probe_failures"]
    assert all(r.get("web_status") == r.get("api_status") == 200 and not r.get("error_type") for r in rows)
    elapsed = [r["elapsed_seconds"] for r in rows]
    gaps = [b-a for a, b in zip(elapsed, elapsed[1:])]
    assert all(gap > 0 for gap in gaps)
    assert max(gaps) < 10, "A long sampling interruption must not be hidden"
    assert elapsed[0] < 10 and summary["actual_seconds"] - elapsed[-1] < 10
    for name, expected in implementation["code_hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    checks = summary["checks"]
    required = {"worker_replaced_website_preserved", "active_job_lease_recovery", "job_memory_released",
                "status_file_real_lock_survived_and_resumed", "broker_crash_outbox_delivery_website_preserved",
                "cancel_releases_model_and_preserves_publication"}
    assert required.issubset({c["name"] for c in checks}) and all(c["passed"] for c in checks)
    assert sum(c["name"] == "worker_replaced_website_preserved" for c in checks) == 2
    assert sum(j["status"] == "succeeded" for j in summary["jobs"]) == 4
    assert sum(j["status"] == "cancelled" for j in summary["jobs"]) == 1
    for key in ("supervisor_pid", "web_pid", "api_pid", "postgres_pid"):
        assert summary["initial_state"][key] == summary["final_state"][key]
    released = [c["private_bytes"] for c in checks if c["name"] == "job_memory_released"]
    assert all(v < 192 * 1024**2 for v in released)
    memory = [sum(p.get("private_bytes", 0) for p in r.get("processes", [])) for r in rows]
    local = timezone(timedelta(hours=8))
    audit_result = {"label": label, "passed": True, "actual_seconds": summary["actual_seconds"],
                    "start_beijing": datetime.fromisoformat(summary["started_at"]).astimezone(local).isoformat(),
                    "finish_beijing": datetime.fromisoformat(summary["finished_at"]).astimezone(local).isoformat(),
                    "pairs": len(rows), "successful_http_probes": 2 * len(rows), "failures": 0,
                    "max_sample_gap_seconds": round(max(gaps), 3), "worker_tree_peak_private_bytes": max(memory),
                    "released_private_bytes": released, "final_private_bytes": memory[-1],
                    "checks": checks, "job_ids": [j["id"] for j in summary["jobs"]],
                    "code_hashes_match": True, "scope": summary["scope"],
                    "notice": "One observed hour, not an unlimited uptime or leak-free guarantee; no deliberate host memory exhaustion"}
    (folder / "audit.json").write_text(json.dumps(audit_result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit_result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    audit(parser.parse_args().label)
