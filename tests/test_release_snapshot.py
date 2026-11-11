import pytest

from scripts.snapshot_local_git import next_version, release_files, release_target


def test_release_sequence_is_1_0_then_minor_increments():
    assert next_version([]) == "1.0"
    assert next_version(["1.0", "1.9", "1.10", "other"]) == "1.11"


def test_complete_same_round_keeps_original_tags_and_next_round_sequence():
    tags = ["1.0", "v1.0"]
    assert release_target("1.0", tags, complete_current=True) == ("1.0", "1.0-verified")
    assert next_version(tags + ["1.0-verified"]) == "1.1"
    with pytest.raises(ValueError):
        release_target("1.0", tags + ["1.0-verified"], complete_current=True)
    with pytest.raises(ValueError):
        release_target("1.0", tags + ["1.1"], complete_current=True)
    with pytest.raises(ValueError):
        release_target("1.0", tags)


def test_snapshot_excludes_runtime_secrets_and_the_repository_itself(tmp_path):
    for name in [".env", ".env.example", "README.md", "git/old.md", ".local/state.json", ".venv/python.exe",
                 "frontend/node_modules/big.js", "backend/app.py", "local.sqlite3", "docs/evidence/result.log"]:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    assert {p.relative_to(tmp_path).as_posix() for p in release_files(tmp_path)} == {
        ".env.example", "README.md", "backend/app.py", "docs/evidence/result.log"}
