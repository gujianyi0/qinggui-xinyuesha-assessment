"""Render verified rule facts without asking the model to reinterpret numeric assertions."""


def card_text(card: dict) -> str:
    suits = {"heart": "红桃", "spade": "黑桃", "club": "梅花", "diamond": "方块"}
    names = {"slash": "杀", "peach": "桃", "jink": "闪"}
    return f"{suits.get(card['suit'], card['suit'])}{card['number']}【{names.get(card['name'], card['name'])}】"


def render_ruling(record: dict) -> str:
    reference = record["status"] == "reference"
    parts = []
    if reference:
        parts.append("以下引用固定快照中已执行的测试记录，仅在列出的前提下适用；不表示你的完整局面已经匹配。")

    def section(item: dict, heading: str):
        parts.append(f"## {heading}\n{item['summary']}")
        parts.append("记录前提（全部成立才可套用该记录的具体结果）：\n" + "\n".join(f"- {c}" for c in item["required_conditions"]))
        if item.get("chronology"):
            parts.append("来源核对的时间顺序：\n" + "\n".join(f"{n}. {step}" for n, step in enumerate(item["chronology"], 1)))
        parts.append("核对项目（断言条目，不表示时间顺序）：\n" + "\n".join(f"- {step}" for step in item.get("steps", [])))
        details = item.get("scenario_details", {})
        if details.get("judgment_cards"):
            parts.append("固定判定牌依次为：" + " → ".join(card_text(c) for c in details["judgment_cards"]))
        if details.get("guicai_cost"):
            parts.append("第一次鬼才改判所用手牌：" + card_text(details["guicai_cost"]))
        if details.get("cost_card"):
            parts.append("固定测试弃牌：" + card_text(details["cost_card"]))
        if details.get("seats"):
            parts.append("固定测试座位：" + "、".join(map(str, details["seats"])))
        result = item.get("result", {})
        parts.append(f"执行证据：{item['evidence_path']}；{result.get('tests_run', 0)} 个测试，{result.get('failures', 0)} 个失败。")

    section(record, f"{record['id']} {record['title']}")
    if reference:
        for variant in record.get("variants", []):
            section(variant, f"已验证对照：{variant['variant_id']}")
        parts.append("不同记录的饮酒、防具位置、选择及用牌次数等前提不能混用。只有部分前提相同的局面仍须补充信息或另行验证；这里列出的是测试记录，未把缺失条件当成玩家事实。")
    parts.append(f"资料快照：{record['snapshot_id']}；验证范围：固定快照 Lua 规则 / fake_backend，非完整客户端或线上对局。")
    return "\n\n".join(parts)
