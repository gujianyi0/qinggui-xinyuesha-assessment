"""Force one relay disconnect, then check automatic recovery without paid calls."""
import datetime as dt
import json
import time

import httpx

from backend.app.config import ROOT


def main():
    folder = ROOT / ".local/public-entry"
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    visitor = json.loads((folder / "browser-check.json").read_text(encoding="utf-8"))
    output = ROOT / "docs/evidence/v18-public-service/recovery.json"
    control = {"Authorization": "Bearer " + config["control_token"]}
    started = time.monotonic()
    with httpx.Client(timeout=30) as client, httpx.Client(trust_env=False, timeout=15) as owner:
        auth = client.post(config["public_url"] + "/api/auth/guest", json={"client_secret": visitor["client_secret"]})
        auth.raise_for_status()
        headers = {"Authorization": "Bearer " + auth.json()["access_token"]}
        sessions_before = client.get(config["public_url"] + "/api/sessions", headers=headers).json()
        budget_before = owner.get("http://127.0.0.1:18081/health").json()["budget"]
        state_before = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        response = client.post(config["public_url"] + "/__disconnect", headers=control)
        response.raise_for_status()
        probes = []
        recovered_at = None
        for _ in range(30):
            try:
                response = client.get(config["public_url"] + "/api/health", headers=headers)
                status = response.status_code
            except httpx.HTTPError:
                status = "transport_error"
            probes.append({"elapsed_seconds": round(time.monotonic() - started, 3), "phase": "recovering", "status": status})
            if status == 200:
                recovered_at = time.monotonic() - started
                break
            time.sleep(1)
        assert recovered_at is not None, "Relay did not reconnect"
        # Two minutes exercise short HTTPS pulls and repeated RPC.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            public = client.get(config["public_url"] + "/api/health", headers=headers)
            local = owner.get("http://127.0.0.1:18081/health")
            web = client.get(config["public_url"])
            probes.append({"elapsed_seconds": round(time.monotonic() - started, 3), "phase": "stable", "status": public.status_code,
                           "owner_status": local.status_code, "web_status": web.status_code})
            time.sleep(5)
        sessions_after = client.get(config["public_url"] + "/api/sessions", headers=headers).json()
        budget_after = owner.get("http://127.0.0.1:18081/health").json()["budget"]
        remote = client.get(config["public_url"] + "/__status", headers=control).json()
    state_after = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    summary = {"finished_utc": dt.datetime.now(dt.UTC).isoformat(), "duration_seconds": round(time.monotonic() - started, 3),
               "recovery_seconds_including_setup": round(recovered_at, 3), "probes": probes, "budget_before": budget_before,
               "budget_after": budget_after, "sessions_unchanged": sessions_before == sessions_after,
               "state_before": state_before, "state_after": state_after, "remote_status": remote,
               "paid_requests": 0, "passed": remote["connected"] and sessions_before == sessions_after and budget_before == budget_after
               and state_after["reconnects"] >= state_before["reconnects"] + 1
               and all(row["status"] == row["owner_status"] == row["web_status"] == 200 for row in probes if row["phase"] == "stable")}
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert summary["passed"], summary
    print(json.dumps({key: summary[key] for key in ("passed", "duration_seconds", "recovery_seconds_including_setup", "paid_requests")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
