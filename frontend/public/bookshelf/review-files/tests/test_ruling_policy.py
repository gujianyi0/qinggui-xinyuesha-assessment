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


def test_record_disclaimer_does_not_turn_record_request_into_actual_position():
    policy = ruling_policy('请查看SC03固定测试记录，说明结果与前提，不代表我的实际局面。')
    assert policy.scenes == {'SC03'} and policy.reference_allowed
    assert policy.confirmed_conditions is None and not policy.fixed_conditions_confirmed


def test_actual_position_or_refused_reference_remains_blocked_despite_final_disclaimer():
    for message in ['请把SC03固定记录用于当前局面，不代表我的实际局面。',
                    'SC03不要用固定记录判断，不代表我的实际局面。',
                    '请查看SC03固定记录，不代表我的实际局面，但我当前局面会受多少伤害？']:
        assert not ruling_policy(message).reference_allowed
