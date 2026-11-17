"""Regress old-SC contamination through the real Agno/OpenAI protocol adapter."""
import json

from test_agno_protocol import protocol_model as fixture_protocol_model
from test_agno_protocol import sse_response

from backend.app.models import Message

protocol_model = fixture_protocol_model


async def test_entity_questions_after_a_ruling_use_only_the_current_data_tools(client, app, protocol_model):
    session = (await client.post('/sessions', json={})).json()['id']
    async with app.state.database.sessions.begin() as db:
        db.add(Message(session_id=session, role='user', content='请查看SC03固定测试记录。', citations=[]))
        db.add(Message(session_id=session, role='assistant', content='仅在固定前提下适用。', citations=[]))
    for name, answer in [('孙权', '孙权有制衡和救援。'), ('刘备', '刘备有仁德和激将。'), ('曹操', '曹操有奸雄和护驾。')]:
        requests = []

        def handler(request):
            body = json.loads(request.content)
            tools = {tool['function']['name'] for tool in body.get('tools', [])}
            assert tools == {'search_knowledge', 'query_game_data'}
            requests.append(body)
            if len(requests) == 1:
                return sse_response(tool='query_game_data', arguments={'query': name, 'kind': 'general'})
            return sse_response(answer=answer)

        sdk = protocol_model(handler)
        try:
            response = await client.post(f'/sessions/{session}/runs', json={'message': name + '技能'})
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            run = (await client.get('/runs/' + events[0]['run_id'])).json()
            assert run['status'] == 'completed' and answer in run['text']
            assert '暂不能判断' not in response.text
            assert [call['name'] for call in run['tool_calls']] == ['query_game_data']
            assert run['citations'] and all(c['snapshot_id'] == run['snapshot_id'] for c in run['citations'])
        finally:
            await sdk.close()
