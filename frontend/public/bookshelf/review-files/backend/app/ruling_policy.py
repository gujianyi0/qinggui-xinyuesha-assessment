"""Application-owned ruling scope; model arguments never confirm player facts."""
import json
import re
from dataclasses import dataclass, field

SCENES = tuple(f'SC0{i}' for i in range(1, 9))
NEW_TOPIC = re.compile(r'^(?:换个问题|换个话题|另一个问题|查询|请查|查一下|介绍)|^标准.+有哪些技能')
BASIC_DATA_QUERY = re.compile(
    r'^(?:(?:那么|那|还有|请问|请|帮我|再问一下)\s*)*'
    r'(?P<subject>[^\s，,。！？?]{1,24}?)(?:的)?'
    r'(?:技能(?:说明)?|势力|体力(?:上限)?|性别|花色|点数|攻击范围)'
    r'(?:是什么|有哪些|有什么|是多少|如何|呢|吗)?[。？！?!]*$'
)
CONTEXTUAL_FOLLOWUP = re.compile(
    r'^(?:那|这样|这时|这个|这种|这次|这些|该|它|他|她|其中|另一个|'
    r'如果|假如|假设|改成|改为|换成|换为|仍|再|继续|还|为什么|为何|'
    r'会|能否|是否|可以吗|不喝|不饮|没有|未饮|当前|场上|武将是|是的|好[的吧]?$)'
    r'|刚才|上一(?:轮|次|个)|之前的|上述|同样|原来|伤害|结算|传导|装备|手牌'
)


def is_contextual_followup(message: str) -> bool:
    text = message.strip()
    if NEW_TOPIC.search(text):
        return False
    query = BASIC_DATA_QUERY.fullmatch(text)
    if query and not re.search(r'其中|这|那|该|他|她|它|刚才|之前|改成|换成|如果', query['subject']):
        return False
    return bool(CONTEXTUAL_FOLLOWUP.search(text))


def scenes_in(text: str) -> set[str]:
    explicit = set(re.findall(r'(?<![A-Za-z0-9])SC[0-9]{2}(?![A-Za-z0-9])', text.upper()))
    if explicit:
        return explicit
    found = set()
    if '青龙' in text and any(x in text for x in ('空城', '诸葛亮')):
        found.add('SC01')
    if '八卦' in text and any(x in text for x in ('无双', '鬼才')):
        found.add('SC02')
    if '连环' in text and '青釭' in text:
        found.add('SC04')
    elif '连环' in text and '火杀' in text and any(x in text for x in ('藤甲', '白银狮子')):
        found.add('SC03')
    if '流离' in text and any(x in text for x in ('青釭', '仁王盾')):
        found.add('SC05')
    if '贯石斧' in text and '连营' in text:
        found.add('SC06')
    if '奸雄' in text and '连环' in text:
        found.add('SC07')
    if '武圣' in text and '连弩' in text:
        found.add('SC08')
    if not found and re.search(r'裁定|技能交互|连锁.*结算|复杂.*结算', text):
        found.add('UNVERIFIED')
    return found


@dataclass
class RulingPolicy:
    scenes: set[str] = field(default_factory=set)
    reference_allowed: bool = False
    confirmed_conditions: dict | None = None
    fixed_conditions_confirmed: bool = False

    @property
    def required(self):
        return bool(self.scenes)


def ruling_policy(message: str, previous_user_messages=(), request_data=None) -> RulingPolicy:
    body = request_data or {}
    scenes = scenes_in(message)
    if body.get('ruling_scene_id'):
        scenes = {body['ruling_scene_id']}
    # Only a positively contextual follow-up inherits a scene. An independent
    # question also stops history scanning; an old SC record must not taint it.
    if not scenes and is_contextual_followup(message):
        for previous in previous_user_messages:
            scenes = scenes_in(previous)
            if scenes:
                break
            if not is_contextual_followup(previous):
                break
    reference = bool(re.search(r'固定|记录|已验证场景|对照|裁定场景\s*SC0[1-8]', message, re.I))
    # A final disclaimer excludes applying the record to a player position;
    # it must not turn an explicit record request into an actual-position query.
    scope_message = re.sub(r'[，,；;。]\s*不代表(?:我的|我)?(?:实际|当前)局面[。.!！]?\s*$', '', message)
    if re.search(r'没有提供|未提供|条件不全|缺少条件|实际局面|当前局面|(?:不要|不能|不是|别用).{0,12}(?:固定|对照|记录)', scope_message):
        reference = False
    if body.get('ruling_scene_id'):
        reference = body.get('ruling_mode') == 'reference'
    confirmed = body.get('ruling_conditions') if body.get('ruling_scene_id') and not reference else None
    if confirmed is None and '已明确提供全部条件：' in message:
        try:
            value = json.JSONDecoder().raw_decode(message.split('已明确提供全部条件：', 1)[1].strip())[0]
            if isinstance(value, dict):
                confirmed = value
        except ValueError:
            pass
    attested = bool(re.search(r'(必要条件|全部前提|所有前提).{0,16}(完全一致|全部一致)', message))
    if re.search(r'(?:不|未|并非).{0,5}(?:完全一致|全部一致)|条件不全|缺少条件', message):
        attested = False
    return RulingPolicy(scenes, reference, confirmed, attested)


def guarded_lookup(catalog, policy: RulingPolicy, scene_id, snapshot_id, conditions, reference):
    if scene_id not in policy.scenes or len(policy.scenes) != 1:
        return {'status': 'needs_clarification', 'message': '请先明确本轮要核对的单个裁定场景。'}
    if reference and not policy.reference_allowed:
        if policy.confirmed_conditions is not None:
            return catalog.ruling(scene_id, snapshot_id, policy.confirmed_conditions)
        return {'status': 'needs_clarification', 'message': '当前需要核验实际局面，不能改用固定记录确认当前结论。',
                'required_context': ['请补充当前局面的必要前提，或明确要求查看固定测试记录。']}
    if reference:
        return catalog.ruling(scene_id, snapshot_id, reference=True)
    declared = policy.confirmed_conditions
    if declared is None and policy.fixed_conditions_confirmed:
        declared = conditions or {}
    if declared is None:
        result = catalog.ruling(scene_id, snapshot_id, {})
        result['status'] = 'needs_clarification'
        result['message'] = '模型推测的条件不能替代玩家本轮确认。请核对必要前提；也可明确查看固定记录。'
        return result
    return catalog.ruling(scene_id, snapshot_id, declared)
