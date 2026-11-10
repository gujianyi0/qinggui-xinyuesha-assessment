"""Certify only executed, nonzero-test, hash-matched ruling evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path = ROOT):
    source = read(root / "data/manifest.json")
    engine_path = root / ".local/engine/engine-manifest.json"
    engine = read(engine_path) if engine_path.exists() else None
    catalog = []
    for spec in read(root / "rulings/specifications.json"):
        item = dict(spec)
        item.update({"status": "pending", "snapshot_id": source["snapshot_id"], "source_manifest_hash": source["manifest_hash"],
                     "summary": "尚未通过离线规则测试，不提供已验证裁定", "evidence_path": f"rulings/evidence/{spec['id']}.json", "steps": []})
        proof_path = root / item["evidence_path"]
        if proof_path.exists():
            proof = read(proof_path)
            hashes_match = (proof.get("scenario_sha256") == sha256(root / "rulings/scenes" / f"{spec['id']}.lua")
                            and proof.get("common_sha256") == sha256(root / "rulings/scenes/common.lua"))
            same_source = bool(engine and engine["source_commit"] == source["source_commit"])
            source_files = {f["path"].removeprefix("runtime/"): f["sha256"] for f in source["files"] if f["path"].startswith("runtime/")}
            engine_files = {f["path"]: f["sha256"] for f in engine["rule_files"]} if engine else {}
            same_source = same_source and all(engine_files.get(p) == h for p, h in source_files.items())
            checks = proof.get("trace", {}).get("assertions", [])
            passed = (proof.get("passed") is True and proof.get("tests_run", 0) >= 1
                      and proof.get("failures") == 0 and hashes_match and same_source
                      and len(checks) >= 3 and all(c.get("passed") is True for c in checks)
                      and proof.get("binary_sha256") == (engine or {}).get("binary_sha256"))
            item["status"] = "verified" if passed else "failed"
            item["scenario_sha256"] = proof.get("scenario_sha256")
            if passed:
                trace = proof["trace"]
                item["summary"] = trace["summary"]
                item["steps"] = [check["label"] for check in checks]
                item["result"] = {"assertions": checks, "tests_run": proof["tests_run"], "failures": proof["failures"],
                                  "event_count": len(trace.get("events", [])), "executed_at": proof["executed_at"],
                                  "binary_sha256": proof["binary_sha256"], "verification_scope": trace["scope"]}
        catalog.append(item)
    (root / "rulings/catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if engine:
        (root / "rulings/engine-manifest.json").write_text(json.dumps(engine, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return catalog


if __name__ == "__main__":
    result = build()
    print(json.dumps({"verified": sum(r["status"] == "verified" for r in result), "total": len(result)}))
