from backend.app.catalog import Catalog
from backend.app.config import Settings


def test_blade_rule_flags_are_not_required_from_player():
    catalog = Catalog(Settings(_env_file=None))
    source = next(s for s in catalog.rulings() if s["id"] == "SC01")
    player_input = {k: v for k, v in source["conditions"].items() if k not in {"bypass_times", "bypass_distances"}}
    result = catalog.ruling("SC01", catalog.active_id, player_input)
    assert result["status"] == "verified"
    assert result["conditions"]["bypass_times"] is True
    assert result["conditions"]["bypass_distances"] is True


def test_blade_player_state_still_must_match_verified_scene():
    catalog = Catalog(Settings(_env_file=None))
    wrong = {"attacker_weapon": "blade", "target_general": "caocao", "target_last_hand_card": "jink"}
    assert catalog.ruling("SC01", catalog.active_id, wrong)["status"] == "needs_clarification"
    assert catalog.ruling("SC01", catalog.active_id, {})["status"] == "needs_clarification"


def test_reference_exposes_record_without_asserting_user_state():
    catalog = Catalog(Settings(_env_file=None))
    record = catalog.ruling("SC02", catalog.active_id, reference=True)
    assert record["status"] == "reference" and record["record_status"] == "verified"
    assert record["scenario_details"]["guicai_cost"]["number"] == 3
    assert catalog.ruling("SC02", catalog.active_id, {})["status"] == "needs_clarification"
    assert catalog.ruling("SC02", "wrong-snapshot", reference=True)["status"] == "unverified"


def test_sc04_variant_and_sc08_control_match_only_executed_conditions():
    catalog = Catalog(Settings(_env_file=None))
    for scene_id in ("SC04", "SC08"):
        variant = next(s for s in catalog.rulings() if s["id"] == scene_id)["variants"][0]
        matched = catalog.ruling(scene_id, catalog.active_id, variant["conditions"])
        assert matched["status"] == "verified" and matched["variant_id"] == variant["variant_id"]
        wrong = {**variant["conditions"], "attacker_weapon": "unknown"}
        assert catalog.ruling(scene_id, catalog.active_id, wrong)["status"] == "needs_clarification"
