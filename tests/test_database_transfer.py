import copy
import json

import pytest

from backend.app.database_transfer import assert_quiescent, assert_same_database, canonical_row
from backend.app.deployment import require_native_primary, write_deployment


def snapshot():
    return {"tables": {"sessions": {"rows": 246, "sha256": "unchanged"}},
            "budget": {"id": 1, "spent": 5.682864, "reserved": 0},
            "active": {"runs": 0, "jobs": 0, "usage": 0, "outbox": 0},
            "migration": "0001", "pgvector": "0.8.7"}


def test_transfer_rejects_budget_reset_even_when_row_counts_match():
    source = snapshot()
    target = copy.deepcopy(source)
    target["budget"]["spent"] = 0
    with pytest.raises(ValueError, match="账本"):
        assert_same_database(source, target)


def test_transfer_rejects_same_count_but_changed_conversation_content():
    source = snapshot()
    target = copy.deepcopy(source)
    target["tables"]["sessions"]["sha256"] = "changed"
    with pytest.raises(ValueError):
        assert_same_database(source, target)


@pytest.mark.parametrize("active", ["runs", "jobs", "usage", "outbox"])
def test_transfer_requires_all_work_and_usage_to_settle(active):
    value = snapshot()
    value["active"][active] = 1
    with pytest.raises(ValueError):
        assert_quiescent(value)


def test_transfer_rejects_reserved_fee_and_preserves_json_order_semantics():
    value = snapshot()
    value["budget"]["reserved"] = 1
    with pytest.raises(ValueError):
        assert_quiescent(value)
    assert canonical_row('{"b":2,"a":"中文"}') == canonical_row('{"a":"中文", "b":2}')
    assert canonical_row('{"a":[1,2]}') != canonical_row('{"a":[2,1]}')


@pytest.mark.parametrize("state", [{"primary": "frozen", "phase": "source_frozen"},
                                  {"primary": "docker", "phase": "active"}])
def test_old_native_writer_cannot_restart_after_handoff(tmp_path, state):
    write_deployment(state, tmp_path)
    with pytest.raises(RuntimeError, match="费用账本"):
        require_native_primary(tmp_path)


def test_handoff_guard_fails_closed_for_unknown_marker(tmp_path):
    require_native_primary(tmp_path)
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local/deployment.json").write_text(json.dumps({"owner": "unknown"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="不属于"):
        require_native_primary(tmp_path)
