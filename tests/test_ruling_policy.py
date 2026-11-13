from backend.app.ruling_policy import ruling_policy


def test_negated_reference_and_incomplete_attestation_do_not_authorize_fixed_conditions():
    policy = ruling_policy('SC03，不要用固定记录回答；必要条件并不完全一致。')
    assert policy.required and not policy.reference_allowed and not policy.fixed_conditions_confirmed


def test_followup_inherits_scene_but_never_previous_reference_permission():
    policy = ruling_policy('那如果改成仁王盾呢？', ['请查看SC03固定记录。'])
    assert policy.scenes == {'SC03'} and not policy.reference_allowed


def test_short_followup_cannot_bypass_boundary_but_explicit_new_subject_can():
    history = ['请查看SC03固定记录。']
    assert ruling_policy('会造成几滴伤害？', history).scenes == {'SC03'}
    assert not ruling_policy('查询标准曹操的技能。', history).required
    assert not ruling_policy('其中另一个技能呢？', ['查询标准曹操的技能。', *history]).required
