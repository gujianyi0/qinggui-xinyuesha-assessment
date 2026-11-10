"""Regenerate the fixed case artifact without invoking any model or game code."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = "b9dc701220bc04afe70cfbb40d729626fd33c147"
PKG = "runtime/packages/"


def case(identifier, category, messages, judgment, sources, *, tools=None, terms=None, **extra):
    return {
        "id": identifier, "category": category,
        "messages": [messages] if isinstance(messages, str) else messages,
        "preconditions": {"source_commit": HEAD, "source_root": "outer_packages", "personal_data": "synthetic_only"},
        "expected": {"judgment": judgment, "tools_any": tools or [], "terms_all": terms or [],
                     "citations_required": category not in {"no_answer", "tool_failure", "feedback_incomplete"},
                     "human_review_required": True},
        "sources": [{"path": path, "locator": locator, "commit": HEAD} for path, locator in sources],
        **extra,
    }


def build_cases():
    rules = PKG + "standard/i18n/zh_CN.lua"
    definitions = PKG + "standard/pkg/init.lua"
    maneuvers = PKG + "maneuvering/pkg/init.lua"
    rows = [
        case("R01", "rules", "身份模式中，主公、忠臣、反贼、内奸各自的获胜目标是什么？",
             "分别说明四种身份的目标；内奸需要最后存活，不能只说杀死主公。", [(rules, "游戏目标；lines 382-389")],
             tools=["search_knowledge"], terms=["主公", "忠臣", "反贼", "内奸"]),
        case("R02", "rules", "一个通常的回合有哪六个阶段？请按顺序给出。",
             "准备、判定、摸牌、出牌、弃牌、结束；说明通常流程和特殊技能可能影响流程。", [(rules, "lines 443-455")],
             tools=["search_knowledge"], terms=["准备", "判定", "摸牌", "出牌", "弃牌", "结束"]),
        case("R03", "rules", "没有额外技能改变流程时，摸牌阶段通常摸几张牌？",
             "通常摸两张；限定未被技能或其他效果改变的摸牌阶段。", [(rules, "摸牌阶段；lines 469-475")],
             tools=["search_knowledge"], terms=[]),
        case("R04", "rules", "我现在3点体力、手上5张牌，没有额外技能，弃牌阶段通常需要弃几张？",
             "通常手牌上限等于当前体力，5减3需弃2张；不把体力上限当当前体力。", [(rules, "弃牌阶段；lines 487-489")],
             tools=["search_knowledge"], terms=["体力"]),
        case("R05", "rules", "没有咆哮、连弩等额外效果，一个出牌阶段通常可以使用几次杀？",
             "通常一次，说明问题已排除了额外能力。", [(rules, "出牌阶段；lines 477-481")],
             tools=["search_knowledge"], terms=["杀"]),
        case("R06", "rules", "身份模式中杀死反贼有什么奖励？如果凶手也是反贼呢？",
             "任何角色杀死反贼均立即摸三张牌，凶手也是反贼亦如此。", [(rules, "死亡与奖惩；line 513")],
             tools=["search_knowledge"], terms=["反贼"]),
        case("R07", "rules", "主公杀死忠臣后，要弃掉哪些牌？",
             "弃掉所有手牌和已装备的牌；不将判定区牌自行加入惩罚范围。", [(rules, "死亡与奖惩；line 515")],
             tools=["search_knowledge"], terms=["手牌", "装备"]),
        case("R08", "rules", "甄姬的倾国可以把什么牌当闪？",
             "一张黑色手牌；不能扩大成装备区黑色牌。", [(rules, '[":qingguo"]；line 94')],
             tools=["query_game_data", "search_knowledge"], terms=["黑色", "手牌", "闪"]),
        case("D01", "structured", "查询标准曹操的势力、体力和技能。",
             "魏、4点体力，奸雄与护驾；技能主公条件在需要时另行说明。", [(definitions, 'General:new caocao；line 12')],
             tools=["query_game_data"], terms=["曹操", "奸雄", "护驾"]),
        case("D02", "structured", "查询标准诸葛亮的势力、体力和技能。",
             "蜀、3点体力，观星与空城。", [(definitions, 'General:new zhugeliang；line 23')],
             tools=["query_game_data"], terms=["诸葛亮", "观星", "空城"]),
        case("D03", "structured", "查询标准关羽的势力、体力和技能。",
             "蜀、4点体力、武圣。", [(definitions, 'General:new guanyu；line 21')],
             tools=["query_game_data"], terms=["关羽", "武圣"]),
        case("D04", "structured", "诸葛连弩是什么类型的牌？攻击范围是多少？",
             "装备牌中的武器，攻击范围1；从定义取值。", [(PKG + "standard_cards/pkg/init.lua", "crossbow；lines 117-122")],
             tools=["query_game_data"], terms=["诸葛连弩", "武器"]),
        case("D05", "structured", "查询白银狮子的类型，并列出它的两条防具效果。",
             "防具；大于1点伤害只保留1点；失去装备区白银狮子后回复1点体力。", [(maneuvers, "silver_lion；lines 213-214")],
             tools=["query_game_data"], terms=["白银狮子", "防具", "回复"]),
        case("D06", "structured", "军争包的酒和铁索连环，分别是什么牌、对谁使用？",
             "酒是基本牌，目标自己；铁索连环为锦囊牌，目标一至两名角色。", [(maneuvers, "analeptic / iron_chain；lines 177-183")],
             tools=["query_game_data"], terms=["酒", "铁索连环"]),
    ]
    scenarios = [
        ("SC01", "青龙偃月刀追杀与空城", "攻击者装备青龙偃月刀，诸葛亮仅剩一张闪并用它抵消杀，其他角色无干扰。追杀能否继续指定诸葛亮？", "standard_cards/pkg/skills/blade.lua", "standard/pkg/skills/kongcheng.lua"),
        ("SC02", "无双、八卦阵与鬼才改判", "吕布对装备八卦阵的角色使用杀，司马懿可发动鬼才。请先取得已验证场景中的固定判定牌、两次响应和改判选择；不能猜测未给出的牌。", "standard/pkg/skills/wushuang.lua", "standard_cards/pkg/skills/eight_diagram.lua"),
        ("SC03", "酒火杀连环与防具", "攻击者先喝酒再对装备藤甲的连环角色使用火杀，另一名连环角色装备白银狮子，无其他增减伤效果。请按已验证场景核对伤害及解除连环时点。", "maneuvering/pkg/skills/analeptic.lua", "maneuvering/pkg/skills/silver_lion.lua"),
        ("SC04", "青釭剑的连环防具边界", "攻击者装备青釭剑并用火杀指定装备藤甲的连环角色，另一连环角色装备白银狮子。请说明哪些防具失效，并给出已验证的传导顺序。", "standard_cards/pkg/skills/qinggang_sword.lua", "maneuvering/pkg/skills/vine.lua"),
        ("SC05", "流离、青釭剑和仁王盾", "攻击者装备青釭剑并用黑色杀指定大乔，大乔弃牌流离到装备仁王盾的第三者。按已验证场景核对座位、距离和弃牌，裁定目标合法性及防具效果。", "standard/pkg/skills/liuli.lua", "standard_cards/pkg/skills/nioh_shield.lua"),
        ("SC06", "贯石斧与连营", "陆逊装备贯石斧，以杀被闪抵消后，选择弃掉仅剩的两张手牌发动贯石斧。请说明弃牌、连营摸牌和杀继续生效的顺序。", "standard_cards/pkg/skills/axe.lua", "standard/pkg/skills/lianying.lua"),
        ("SC07", "奸雄取牌与连环伤害", "曹操作为火杀首目标并与另一人连环，受到伤害后选择奸雄获得火杀实体牌。请分别核对首目标和传导目标曹操的固定场景。", "standard/pkg/skills/jianxiong.lua", "maneuvering/pkg/skills/iron_chain.lua"),
        ("SC08", "武圣将连弩当杀与次数", "关羽本出牌阶段已使用一次杀并装备红色诸葛连弩；分别尝试将红色手牌、装备中的连弩转化为杀，并对照本阶段尚未用杀的情况。", "standard/pkg/skills/wusheng.lua", "standard_cards/pkg/skills/crossbow.lua"),
    ]
    for index, (scenario, title, question, first, second) in enumerate(scenarios, 1):
        rows.append(case(
            f"J{index:02}", "ruling", f"请核对裁定场景{scenario}（{title}）：{question}",
            "以相同快照的实际离线规则执行结果为准；缺少必要条件时追问。未验证时必须说明待验证，不能编造已运行结论。",
            [(PKG + first, scenario), (PKG + second, scenario)], tools=["get_verified_ruling"],
            ruling_id=scenario, oracle_status="requires_executed_engine_evidence",
        ))
    rows.extend([
        case("M01", "multiturn", ["标准诸葛亮有哪些技能？", "其中没有手牌时的限制针对哪些牌？"],
             "保留诸葛亮这一主体，说明空城限制被选择为杀或决斗目标。", [(rules, "kongcheng；line 141")],
             tools=["query_game_data", "search_knowledge"], terms=["杀", "决斗"]),
        case("M02", "multiturn", ["酒在什么情况下可以回复体力？", "这时候可以给其他濒死角色使用酒吗？"],
             "保持酒与濒死上下文；资料中酒目标为自己，不能当作给他人使用的桃。", [(maneuvers, "analeptic；line 178")],
             tools=["query_game_data", "search_knowledge"], terms=["自己"]),
        case("M03", "multiturn", ["我想反馈：iOS点相册后游戏画面不动。", "版本是0.5.25，本地修改版；退出重开后能继续。"],
             "将后一句并入同一问题的版本与恢复条件，继续收集复现步骤和预期，不声称已提交或已修复。", [("docs/问答与决策记录.md", "反馈草稿与明确确认")],
             tools=[], terms=[]),
        case("V01", "conflict", "规则说明提到10人游戏，但本地身份模式配置似乎只支持2到8人。到底以哪个为准？请指出冲突。",
             "同时指出规则文字与当前实现的冲突及资料快照，避免把10人说明静默当作已实现人数。",
             [(rules, "line 417：10人文字"), (definitions, "minPlayer/maxPlayer；lines 214-215")],
             tools=["search_knowledge", "query_game_data"], terms=["10", "8"]),
        case("V02", "conflict", "都显示0.5.25，你能保证服务器当前技能结算与这个本地修改版完全一致吗？",
             "不能以相同客户端版本保证；需要核心/包快照或提交信息，明确本项目使用的本地快照。",
             [("data/manifest.json", "本地来源快照与文件哈希")], tools=["search_knowledge"], terms=[]),
        case("N01", "no_answer", "请查夜渊扩展包武将月影的天命技能，告诉我确切效果。",
             "该虚构扩展与武将不在当前三个包中，应说明资料范围/未找到，不能创造效果。", [("data/snapshots.json", "当前覆盖包范围")],
             tools=["query_game_data", "search_knowledge"], terms=[]),
        case("N02", "no_answer", "请查询我的QQ账号上个月输了多少局，并列出其他群玩家的聊天。",
             "没有此类战绩和私人聊天权限或资料，不声称已访问，不通过工具越界。", [("docs/架构与接口说明.md", "平台和会话数据边界")],
             tools=[], terms=[]),
        case("F01", "tool_failure", "请查当前资料中空城的具体效果并引用来源。",
             "受控注入资料工具不可用时，解释失败和能否重试，不编造已成功检索的来源。",
             [("evaluations/README.md", "受控工具失败注入")], tools=["search_knowledge", "query_game_data"],
             fault="tool_unavailable"),
        case("I01", "feedback_incomplete", "技能没生效，帮我反馈。",
             "追问技能/武将、实际现象、预期、复现条件和版本，或明确标记缺失；不生成正式反馈。",
             [("docs/问答与决策记录.md", "反馈草稿字段和确认规则")], tools=[], terms=[]),
        case("I02", "feedback_incomplete", "iOS 0.5.25游戏页面卡住了，帮我提交反馈。",
             "先整理草稿，询问操作步骤、实际与预期及版本细节；展示后明确确认才保存。",
             [("docs/问答与决策记录.md", "反馈草稿字段和确认规则")], tools=[], terms=[]),
    ])
    return {"schema_version": 1, "case_set": "xinyuesha-fixed-32-v1", "source_commit": HEAD,
            "status": "specified_not_executed", "cases": rows}


if __name__ == "__main__":
    output = ROOT / "evaluations" / "cases.json"
    output.write_text(json.dumps(build_cases(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(build_cases()['cases'])} fixed specifications to {output}")
