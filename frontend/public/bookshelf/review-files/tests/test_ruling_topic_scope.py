import pytest

from backend.app.ruling_policy import ruling_policy


@pytest.mark.parametrize('question', ['孙权技能', '刘备技能', '曹操技能', '曹操的技能是什么？', '那刘备的技能呢？', '你好', '你是谁？', '今天星期几？', '这款游戏的获胜条件是什么？'])
def test_independent_question_does_not_inherit_an_old_ruling(question):
    assert not ruling_policy(question, ['请查看SC03固定测试记录。']).required


@pytest.mark.parametrize('question', ['会造成几滴伤害？', '那如果改成仁王盾呢？', '如果不喝酒呢？', '为什么？', '继续解释刚才的结算。', '当前体力3，手牌2张。', 'A装备藤甲，B装备白银狮子。'])
def test_contextual_followup_still_inherits_the_ruling_boundary(question):
    policy = ruling_policy(question, ['请查看SC03固定测试记录。'])
    assert policy.scenes == {'SC03'}
    assert not policy.reference_allowed


def test_independent_turn_is_a_barrier_for_later_pronoun_followups():
    assert not ruling_policy('另一个技能呢？', ['曹操技能', '刘备技能', '孙权技能', '请查看SC03固定测试记录。']).required


def test_explicit_scene_is_guarded_even_when_the_same_message_mentions_a_skill_query():
    assert ruling_policy('SC03当前局面中曹操技能能生效吗？').required
