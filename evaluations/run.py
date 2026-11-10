"""Run a fixed suite through the real HTTP API; never label mocks as live models."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def read_sse(response: httpx.Response) -> list[dict[str, Any]]:
    events, name, data = [], "message", []
    async for line in response.aiter_lines():
        if line == "":
            if data:
                try:
                    payload = json.loads("\n".join(data))
                except json.JSONDecodeError:
                    payload = {"unparseable": True}
                events.append({"event": name, "data": payload})
            name, data = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        events.append({"event": name, "data": json.loads("\n".join(data))})
    return events


def final_text(events: list[dict[str, Any]], run: dict[str, Any]) -> str:
    for item in reversed(events):
        if item["event"] == "completed" and isinstance(item["data"], dict):
            text = item["data"].get("text") or item["data"].get("content")
            if text:
                return str(text)
    return str(run.get("text") or run.get("content") or run.get("result") or "")


def tool_names(run: dict[str, Any]) -> set[str]:
    calls = run.get("tool_calls") or run.get("tools") or []
    return {str(item.get("name") or item.get("tool_name")) for item in calls if isinstance(item, dict)}


def mechanical_checks(case: dict[str, Any], events: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
    text = final_text(events, run)
    names = tool_names(run)
    wanted = set(case["expected"].get("tools_any", []))
    citations = run.get("citations") or []
    for item in events:
        if item["event"] == "citations" and isinstance(item["data"], dict):
            citations = item["data"].get("items", citations)
        elif item["event"] == "completed" and isinstance(item["data"], dict):
            citations = item["data"].get("citations", citations)
    # Transparent lexical aliases; this still does not evaluate logic or negation.
    aliases = {"自己": ("自己", "本人", "自救")}
    term_matches = {term: next((word for word in aliases.get(term, (term,)) if word in text), None)
                    for term in case["expected"].get("terms_all", [])}
    return {
        "terminal_event_received": any(item["event"] in {"completed", "failed", "cancelled"} for item in events),
        "expected_tool_observed": bool(names & wanted) if wanted else None,
        "citation_present": bool(citations) if case["expected"].get("citations_required") else None,
        "expected_terms_present": all(value is not None for value in term_matches.values()),
        "literal_terms_present": all(term in text for term in case["expected"].get("terms_all", [])),
        "term_matches": term_matches,
        "observed_tools": sorted(names),
        "human_review_pending": True,
    }


async def run_case(client, case, snapshot_id, *, fault_enabled=False):
    if case.get("fault") and not fault_enabled:
        return {"case_id": case["id"], "status": "blocked",
                "reason": "backend_fault_injection_not_enabled", "human_review_pending": True}
    created = await client.post("/sessions", json={"title": f"固定评测 {case['id']}"})
    created.raise_for_status()
    session_id = created.json()["id"]
    turns, started = [], time.perf_counter()
    for message in case["messages"]:
        headers = {"X-Assessment-Fault": case["fault"]} if case.get("fault") else {}
        body = {"message": message}
        if snapshot_id:
            body["snapshot_id"] = snapshot_id
        async with client.stream("POST", f"/sessions/{session_id}/runs", json=body, headers=headers) as response:
            response.raise_for_status()
            events = await read_sse(response)
        run_id = next((item["data"].get("run_id") for item in events
                       if isinstance(item["data"], dict) and item["data"].get("run_id")), None)
        run = {}
        if run_id:
            stored = await client.get(f"/runs/{run_id}")
            stored.raise_for_status()
            run = stored.json()
        turns.append({"input": message, "events": events, "run_id": run_id, "run": run})
    last = turns[-1]
    return {"case_id": case["id"], "category": case["category"], "session_id": session_id,
            "status": "recorded", "elapsed_seconds": round(time.perf_counter() - started, 3),
            "turns": turns, "automatic_checks": mechanical_checks(case, last["events"], last["run"]),
            "human_review": {"status": "pending", "expected_judgment": case["expected"]["judgment"],
                             "source_checks": case["sources"]}}


async def execute(args):
    case_bytes = args.cases.read_bytes()
    suite = json.loads(case_bytes)
    selected = set(args.only.split(",")) if args.only else None
    cases = [row for row in suite["cases"] if not selected or row["id"] in selected]
    if not cases:
        raise ValueError("No cases selected")
    output_dir = args.output / args.label
    output_dir.mkdir(parents=True, exist_ok=False)
    async with httpx.AsyncClient(base_url=args.api_url.rstrip("/"), timeout=args.timeout,
                                 follow_redirects=False) as client:
        health_response = await client.get("/health")
        health_response.raise_for_status()
        health = health_response.json()
        actual_mode = health.get("model_mode")
        if actual_mode != args.mode:
            raise ValueError(f"Requested mode {args.mode!r}, backend reports {actual_mode!r}; refusing mislabeled evidence")
        authenticated = await client.post("/auth/token", json={"username": args.username, "password": args.password})
        authenticated.raise_for_status()
        client.headers["Authorization"] = f"Bearer {authenticated.json()['access_token']}"
        metadata = {"label": args.label, "mode": actual_mode, "backend": health,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "case_set": suite["case_set"], "cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
                    "selected_cases": [row["id"] for row in cases], "concurrency": args.concurrency,
                    "checker_version": "lexical-alias-v2", "semantic_status": "awaiting_human_review"}
        (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        records = []
        with (output_dir / "results.jsonl").open("w", encoding="utf-8") as file:
            semaphore = asyncio.Semaphore(args.concurrency)

            async def evaluate(case):
                async with semaphore:
                    try:
                        record = await run_case(client, case, args.snapshot,
                                                fault_enabled=health.get("fault_injection_enabled") is True)
                    except Exception as exc:
                        record = {"case_id": case["id"], "status": "error", "error_type": type(exc).__name__,
                                  "human_review_pending": True}
                    records.append(record)
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    file.flush()
                    print(f"{case['id']}: {record['status']}", flush=True)

            await asyncio.gather(*(evaluate(case) for case in cases))
        summary = {"case_set": suite["case_set"], "mode": actual_mode, "case_count": len(cases),
                   "status_counts": dict(Counter(row["status"] for row in records)),
                   "semantic_status": "awaiting_human_review", "billing_status": "see_recorded_usage",
                   "notice": "机械检查仅辅助核对；尚未完成逐条语义/来源人工审查，不代表真实模型通过。"}
        (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="固定样例HTTP评测，分别保存模型替身与真实模型证据")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", required=True, choices=["mock", "live"])
    parser.add_argument("--label", required=True, help="唯一目录名，例如 mock-baseline 或 live-before-01")
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluations/cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluations/results")
    parser.add_argument("--username", default="alice")
    parser.add_argument("--password", default=os.getenv("DEMO_PASSWORD", "local-demo-change-me"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--only", default="", help="逗号分隔样例ID；子集运行会明确标注覆盖范围")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        parser.error("--label must be a single directory name")
    try:
        asyncio.run(execute(args))
    except (ValueError, httpx.HTTPError) as exc:
        parser.exit(1, f"Evaluation stopped: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
