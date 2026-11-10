import hashlib

from scripts.audit_eval_sources import audit_citation, fingerprint


def test_source_audit_rejects_fabricated_reference_bad_hash_and_line(tmp_path):
    (tmp_path / "proof.txt").write_text("first\nsecond\n", encoding="utf-8")
    source = {"id": "proof", "path": "proof.txt", "snapshot_id": "snapshot",
              "sha256": hashlib.sha256((tmp_path / "proof.txt").read_bytes()).hexdigest(), "line_start": 1, "line_end": 2}
    assert audit_citation(source, {fingerprint(source)}, tmp_path) == []
    assert "citation_not_bound_to_tool_receipt" in audit_citation(source, set(), tmp_path)
    changed = {**source, "sha256": "wrong", "line_end": 999}
    assert set(audit_citation(changed, {fingerprint(changed)}, tmp_path)) == {"source_hash_mismatch", "line_range_invalid"}


def test_source_audit_rejects_outside_path(tmp_path):
    source = {"id": "escape", "path": "../private.txt", "snapshot_id": "snapshot"}
    assert "file_missing_or_outside_root" in audit_citation(source, {fingerprint(source)}, tmp_path)
