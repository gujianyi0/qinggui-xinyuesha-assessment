import json

import pytest
from test_agno_protocol import protocol_model as fixture_protocol_model
from test_agno_protocol import run_question, sse_response

protocol_model = fixture_protocol_model


async def test_no_tool_cannot_publish_a_ruling(client, protocol_model):
    protocol_model(lambda _: sse_response(answer='这个SC03局面必定造成999点伤害。'))
    stream, run = await run_question(client, '请核对SC03当前局面，我还没有提供完整条件。')
    assert run['status'] == 'completed'
    assert '999点' not in stream and '999点' not in run['text']
    assert '暂不能判断' in run['text'] and not run['citations']
    assert any(call['name'] == 'ruling_guard' for call in run['tool_calls'])


async def test_model_conditions_are_not_player_confirmation(client, app, protocol_model):
    scene = next(s for s in app.state.catalog.rulings() if s['id'] == 'SC03')
    calls = 0

    def handler(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool='get_verified_ruling', arguments={'scene_id':'SC03','conditions':scene['conditions']})
        return sse_response(answer='无需确认，也能确定999点伤害。')
    protocol_model(handler)
    stream, run = await run_question(client, '请裁定SC03当前局面，还缺少必要前提。')
    assert '999点' not in stream and not run['citations']
    assert run['tool_calls'][0]['result']['status'] == 'needs_clarification'


async def test_changed_conditions_cannot_be_replaced_with_fixed_record(client, app, protocol_model):
    scene = next(s for s in app.state.catalog.rulings() if s['id'] == 'SC03')
    protocol_model(lambda _: sse_response(tool='get_verified_ruling', arguments={'scene_id':'SC03','reference':True}))
    session = (await client.post('/sessions', json={})).json()['id']
    response = await client.post(f'/sessions/{session}/runs', json={'message':'请查看SC03固定测试记录。'})
    assert 'event: completed' in response.text
    calls = 0
    def stale(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool='get_verified_ruling', arguments={'scene_id':'SC03','reference':True, 'conditions':scene['conditions']})
        return sse_response(answer='沿用旧裁定，必定999点。')
    protocol_model(stale)
    response = await client.post(f'/sessions/{session}/runs', json={'message':'那当前局面换成仁王盾，而且不喝酒呢？'})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    run = (await client.get('/runs/'+events[0]['run_id'])).json()
    assert '999点' not in response.text and '暂不能判断' in run['text']
    assert not run['citations']


@pytest.mark.parametrize('matched', [True, False])
async def test_explicit_player_fields_control_actual_verification(client, app, protocol_model, matched):
    scene = next(s for s in app.state.catalog.rulings() if s['id'] == 'SC03')
    conditions = dict(scene['conditions'])
    if not matched:
        conditions['first_armor'] = 'nioh_shield'
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool='get_verified_ruling', arguments={'scene_id':'SC03','conditions':scene['conditions']})
        return sse_response(answer='999点')
    protocol_model(handler)
    session = (await client.post('/sessions', json={})).json()['id']
    response = await client.post(f'/sessions/{session}/runs', json={'message':'核对当前局面','ruling_scene_id':'SC03','ruling_conditions':conditions})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    run = (await client.get('/runs/'+events[0]['run_id'])).json()
    assert '999点' not in response.text
    assert run['tool_calls'][0]['result']['status'] == ('verified' if matched else 'needs_clarification')
    assert bool(run['citations']) == matched


async def test_ruling_feedback_remains_feedback(client, protocol_model):
    protocol_model(lambda _: sse_response(answer='尚未保存，请补充实际现象和复现步骤。'))
    _, run = await run_question(client, '我想反馈SC03酒火杀连环的结算异常。')
    assert run['tool_calls'][0]['name'] == 'prepare_feedback_context'
    assert '暂不能判断' not in run['text']
