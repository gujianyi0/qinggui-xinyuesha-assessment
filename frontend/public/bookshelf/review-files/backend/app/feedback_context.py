"""Recognize explicit bug-report intent without confusing Sima Yi's skill name."""
import re

FEEDBACK_INTENT = r"(?:我想|帮我|我要|提交|整理|记录|问题|故障).{0,8}反馈|反馈[：:]"


def is_feedback_request(messages: list[str]) -> bool:
    if not messages:
        return False
    if re.search(r"反馈[的]?技能|技能[【‘]?反馈|司马懿.{0,6}反馈|反馈.{0,3}(?:效果|触发|怎么发动)", messages[-1]) and not re.search(r"(?:问题|故障|提交).{0,5}反馈|反馈[：:]", messages[-1]):
        return False
    explicit = FEEDBACK_INTENT
    if re.search(explicit, messages[-1]):
        return True
    continuation = r"版本|重开|复现|步骤|机型|系统|截图|卡住|画面|相册|退出|恢复|(?:武将|技能|卡牌)\s*(?:是|为|[:：])|我(?:的武将)?是(?!谁|什么)"
    return bool(any(re.search(explicit, m) for m in messages[:-1]) and re.search(continuation, messages[-1]))


def rules_feedback_checklist(messages: list[str]) -> str:
    """A conditional checklist, never inferred player facts or a save action."""
    if not is_feedback_request(messages):
        return ""
    start = max(i for i, m in enumerate(messages) if re.search(FEEDBACK_INTENT, m))
    if not re.search(r"技能|武将|卡牌|结算|伤害", "\n".join(messages[start:])):
        return ""
    return (
        "结算反馈核对清单（已说明的信息无需重复提供）：\n"
        "- 若尚未说明，请补充涉及的武将、具体技能名称或卡牌名称。\n"
        "- 请核对触发阶段/时机、目标和关键局面，例如手牌、装备、体力；未说明的请补充。\n"
        "- 实际现象、预期结果、操作顺序、游戏模式、平台和客户端版本仍有缺项时，请继续补充。"
    )
