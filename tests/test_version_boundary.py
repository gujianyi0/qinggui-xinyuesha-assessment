from test_agno_protocol import protocol_model as fixture_protocol_model
from test_agno_protocol import run_question, sse_response

protocol_model = fixture_protocol_model


async def test_version_answer_has_prequeried_scope_even_when_model_skips_tool(client, protocol_model):
    def handler(request):
        body = request.read().decode()
        assert 'maintained_project_scope' in body
        return sse_response(answer='不能保证。版本号不足以证明服务器与本地快照一致，需要服务器核心及包提交。')
    protocol_model(handler)
    _, run = await run_question(client, '都显示0.5.25，能保证服务器与本地修改版完全一致吗？')
    assert run['status'] == 'completed'
    assert run['tool_calls'][0]['name'] == 'search_knowledge'
    assert run['citations'][0]['path'] == 'data/knowledge-boundaries.md'
    assert run['citations'][0]['evidence_type'] == 'project_scope'


async def test_injured_hand_limit_gets_sources_even_when_model_skips_tool(client, protocol_model):
    protocol_model(lambda _: sse_response(answer='弃2张。手牌上限按当前体力3计算，体力上限4不改变结论。'))
    _, run = await run_question(client, '我当前体力3点、体力上限4点，手上5张牌，无额外效果，弃牌阶段要弃几张？')
    assert run['status'] == 'completed' and run['citations']
    assert run['tool_calls'][0]['name'] == 'search_knowledge'
