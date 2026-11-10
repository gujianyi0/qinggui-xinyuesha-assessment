from backend.app.catalog import Catalog
from backend.app.config import Settings
from backend.app.ruling_text import render_ruling


def test_fixed_judgment_cards_and_response_facts_keep_their_units():
    catalog = Catalog(Settings(_env_file=None))
    text = render_ruling(catalog.ruling("SC02", catalog.active_id, reference=True))
    assert "黑桃6【杀】 → 红桃5【杀】" in text and "红桃3【桃】" in text
    assert "不表示你的完整局面已经匹配" in text
    assert "响应数=4" not in text and "伤害值" not in text


def test_armor_variants_are_separate_conditional_records():
    catalog = Catalog(Settings(_env_file=None))
    text = render_ruling(catalog.ruling("SC04", catalog.active_id, reference=True))
    assert "首目标装备白银狮子" in text and "首目标藤甲" in text
    assert "未饮酒" in text and "先用酒" in text
    assert "SC04V.json" in text and "全部成立" in text and "不能混用" in text


def test_both_crossbow_branches_are_visible_without_an_empty_model_answer():
    catalog = Catalog(Settings(_env_file=None))
    text = render_ruling(catalog.ruling("SC08", catalog.active_id, reference=True))
    assert "不再绕过次数" in text and "尚未用杀" in text
    assert len(text) > 300


def test_assertion_order_is_not_misrepresented_as_event_order():
    catalog = Catalog(Settings(_env_file=None))
    for scene_id in ("SC03", "SC06", "SC07"):
        record = catalog.ruling(scene_id, catalog.active_id, reference=True)
        text = render_ruling(record)
        assert "断言条目，不表示时间顺序" in text
        chronology = text.split("来源核对的时间顺序：", 1)[1].split("核对项目", 1)[0]
        assert all(step in chronology for step in record["chronology"])
    record = catalog.ruling("SC03", catalog.active_id, reference=True)
    assert "体力实际扣减之前" in record["chronology"][0]
    assert "体力实际扣减之前" in record["chronology"][2]
    record = catalog.ruling("SC06", catalog.active_id, reference=True)
    assert "连营" in record["chronology"][1] and "伤害" in record["chronology"][-1]
