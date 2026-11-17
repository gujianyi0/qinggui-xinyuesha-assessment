import hashlib

import pytest

from backend.app.catalog import Catalog
from backend.app.config import Settings
from backend.app.feedback_context import is_feedback_request, rules_feedback_checklist
from scripts.audit_eval_sources import audit_citation, fingerprint


def test_entity_descriptions_have_their_own_translation_and_skill_sources():
    catalog = Catalog(Settings(_env_file=None))
    caocao = catalog.query("曹操", "general")[0]
    assert {s["title"] for s in caocao["description_sources"]} == {"奸雄", "护驾"}
    assert all(s["path"].endswith("i18n/zh_CN.lua") for s in caocao["description_sources"])
    crossbow = catalog.query("诸葛连弩", "card")[0]
    assert any(s["path"].endswith("i18n/zh_CN.lua") and "无次数限制" in s["excerpt"] for s in crossbow["description_sources"])
    assert any(s["line_start"] == 361 and s["line_end"] == 362 and 'Card.Diamond' in s['excerpt'] for s in crossbow["attribute_sources"])


def test_curated_conflict_does_not_invent_a_document_history():
    catalog = Catalog(Settings(_env_file=None))
    conflict = next(d for d in catalog.documents if d["id"] == "known-conflict:role-player-count")
    assert "minPlayer=2、maxPlayer=8" in conflict["text"]
    assert "没有历史证据" in conflict["text"] and "旧说明" not in conflict["text"]
    assert conflict["related_source"]["excerpt"] == "10人游戏时每人发2张"


async def test_base_slash_rule_is_not_crowded_out_by_exceptions(app):
    result = await app.state.search.search("每个出牌阶段 杀 次数 限制 咆哮 连弩", app.state.catalog.active_id)
    assert any("每个出牌阶段仅限使用一次【杀】" in d["text"] for d in result["items"])
    assert all(len(d["source"]["excerpt"]) <= 1000 for d in result["items"])


@pytest.mark.parametrize("messages,expected", [
    (["iOS页面卡住了，帮我提交反馈"], True),
    (["技能没生效，帮我反馈。"], True),
    (["我想反馈：iOS点相册画面不动", "版本0.5.25，退出重开恢复"], True),
    (["帮我查司马懿的反馈技能"], False),
    (["我想反馈：游戏卡住", "诸葛亮有哪些技能"], False),
])
def test_feedback_intent_does_not_confuse_skill_or_a_new_topic(messages, expected):
    assert is_feedback_request(messages) is expected


@pytest.mark.parametrize("messages,expected", [
    (["技能没生效，帮我反馈。"], True),
    (["技能没生效，帮我反馈。", "武将是曹操，技能是奸雄"], True),
    (["技能没生效，帮我反馈。", "我是曹操，技能是奸雄，受伤后没提示"], True),
    (["iOS页面卡住，帮我提交反馈", "版本0.5.25，重开恢复"], False),
    (["技能没生效，帮我反馈。", "我想反馈：iOS点相册画面不动"], False),
    (["技能没生效，帮我反馈。", "诸葛亮有哪些技能？"], False),
    (["技能没生效，帮我反馈。", "我是谁？"], False),
    (["司马懿的反馈技能是什么？"], False),
])
def test_rule_feedback_checklist_scope_and_topic_continuation(messages, expected):
    result = rules_feedback_checklist(messages)
    assert bool(result) is expected
    if expected:
        assert is_feedback_request(messages)
        assert all(word in result for word in ("武将", "技能名称", "卡牌名称", "触发阶段", "关键局面"))
        assert "已说明的信息无需重复提供" in result
        assert "曹操" not in result and "奸雄" not in result


def test_user_statement_citations_must_match_own_session_and_recorded_input(tmp_path):
    content = "版本0.5.25，退出重开恢复"
    source = {"id": "statement", "path": "conversation/owned/message", "snapshot_id": "snapshot", "evidence_type": "user_statement", "excerpt": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}
    receipts = {fingerprint(source)}
    assert audit_citation(source, receipts, tmp_path, user_messages=[content], session_id="owned") == []
    assert "conversation_scope_mismatch" in audit_citation(source, receipts, tmp_path, user_messages=[content], session_id="other")
    assert "user_statement_not_in_recorded_input" in audit_citation(source, receipts, tmp_path, user_messages=[], session_id="owned")
