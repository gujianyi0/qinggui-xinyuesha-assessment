"""Recognize explicit bug-report intent without confusing Sima Yi's skill name."""
import re


def is_feedback_request(messages: list[str]) -> bool:
    if not messages:
        return False
    if re.search(r"反馈[的]?技能|技能[【‘]?反馈|司马懿.{0,6}反馈|反馈.{0,3}(?:效果|触发|怎么发动)", messages[-1]) and not re.search(r"(?:问题|故障|提交).{0,5}反馈|反馈[：:]", messages[-1]):
        return False
    explicit = r"(?:我想|帮我|我要|提交|整理|记录|问题|故障).{0,8}反馈|反馈[：:]"
    if re.search(explicit, messages[-1]):
        return True
    continuation = r"版本|重开|复现|步骤|机型|系统|截图|卡住|画面|相册|退出|恢复"
    return bool(any(re.search(explicit, m) for m in messages[:-1]) and re.search(continuation, messages[-1]))
