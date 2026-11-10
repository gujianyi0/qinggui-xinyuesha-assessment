"""Validate every recorded citation against tool receipts and local frozen files.

This is a source-integrity audit, not a semantic answer judge.
"""
import argparse
import hashlib
import json
from pathlib import Path

from backend.app.config import ROOT


def sources_in(value):
    if isinstance(value, dict):
        if all(key in value for key in ("id", "path", "snapshot_id")):
            yield value
        if isinstance(value.get("source"), dict):
            yield value["source"]
        for child in value.values():
            yield from sources_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from sources_in(child)


def fingerprint(source):
    return tuple(source.get(key) for key in ("id", "path", "snapshot_id", "sha256"))


def audit_citation(source, receipts, root=ROOT, *, user_messages=(), session_id=None):
    issues = []
    path = source.get("path", "")
    snapshot = source.get("snapshot_id", "")
    if not path or not snapshot:
        return ["missing_path_or_snapshot"]
    if fingerprint(source) not in receipts:
        issues.append("citation_not_bound_to_tool_receipt")
    if source.get("evidence_type") == "user_statement":
        if not path.startswith(f"conversation/{session_id}/"):
            issues.append("conversation_scope_mismatch")
        if source.get("excerpt") not in user_messages or source.get("sha256") != hashlib.sha256(source.get("excerpt", "").encode()).hexdigest():
            issues.append("user_statement_not_in_recorded_input")
        return issues
    base = root / "data/sources" / snapshot if path.startswith("runtime/") else root
    if not base.resolve().is_relative_to(root.resolve()):
        return issues + ["file_missing_or_outside_root"]
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        return issues + ["file_missing_or_outside_root"]
    raw = resolved.read_bytes()
    if source.get("sha256") != hashlib.sha256(raw).hexdigest():
        issues.append("source_hash_mismatch")
    start, end = source.get("line_start"), source.get("line_end")
    if start is not None or end is not None:
        count = len(raw.decode("utf-8").splitlines())
        if not isinstance(start, int) or not isinstance(end, int) or not (1 <= start <= end <= count):
            issues.append("line_range_invalid")
    return issues


def audit_folder(folder: Path):
    records = [json.loads(line) for line in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = []
    for record in records:
        user_messages = [turn["input"] for turn in record.get("turns", [])]
        turns = []
        for turn in record.get("turns", []):
            run = turn["run"]
            receipts = {fingerprint(source) for call in run.get("tool_calls", []) for source in sources_in(call.get("result"))}
            citations = [{"id": c.get("id"), "path": c.get("path"), "issues": audit_citation(c, receipts, user_messages=user_messages, session_id=run["session_id"])} for c in run.get("citations", [])]
            turns.append({"run_id": run["id"], "run_status": run["status"], "citations": citations,
                          "issues": [issue for c in citations for issue in c["issues"]]})
        cases.append({"case_id": record["case_id"], "turns": turns})
    return {"scope": "Citation file/hash/line/tool-binding integrity only; semantic review is separate",
            "case_count": len(cases), "citation_count": sum(len(t["citations"]) for c in cases for t in c["turns"]),
            "issues_count": sum(len(t["issues"]) for c in cases for t in c["turns"]), "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    folder = (ROOT / "evaluations/results" / args.label).resolve()
    if not folder.is_relative_to((ROOT / "evaluations/results").resolve()):
        raise ValueError("Evaluation path must stay inside project")
    result = audit_folder(folder)
    (folder / "citation-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("case_count", "citation_count", "issues_count")}))


if __name__ == "__main__":
    main()
