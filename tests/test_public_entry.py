import asyncio
import secrets
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from backend.app.models import BudgetAccount, Message, Run, UsageRecord
from backend.app.runtime import DiscardEvents
from backend.public_gateway import GatewayConfig, create_gateway


@pytest_asyncio.fixture
async def public(app, tmp_path):
    config = GatewayConfig(edge_token=secrets.token_urlsafe(32), service_token=secrets.token_urlsafe(32),
                           signing_key=secrets.token_urlsafe(32))
    app.state.settings.public_service_token = config.service_token
    gateway = create_gateway(config, transport=httpx.ASGITransport(app=app))
    async with gateway.router.lifespan_context(gateway):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url='http://gateway',
                                     headers={'X-Public-Edge': config.edge_token}) as client:
            yield client, config


async def guest(client, secret=None):
    response = await client.post('/api/auth/guest', json={'client_secret': secret or secrets.token_urlsafe(32)})
    assert response.status_code == 200, response.text
    result = response.json()
    return {'Authorization': 'Bearer ' + result['access_token']}, result


async def finish(client, headers, run_id):
    for _ in range(200):
        response = await client.get('/api/runs/' + run_id, headers=headers)
        if response.json()['status'] != 'running':
            return response.json()
        await asyncio.sleep(.01)
    raise AssertionError('run did not finish')


@pytest.mark.asyncio
async def test_public_guest_isolation_deduplication_and_persisted_answer(public, app):
    client, _ = public
    first, a = await guest(client, 'a' * 64)
    second, b = await guest(client, 'b' * 64)
    assert a['user']['id'] != b['user']['id']
    session = (await client.post('/api/sessions', headers=first, json={'title': '公开入口测试'})).json()['id']
    body = {'message': '查询曹操的技能', 'request_id': str(uuid.uuid4())}
    response = await client.post(f'/api/sessions/{session}/runs', headers=first, json=body)
    assert response.status_code == 202
    run_id = response.json()['run_id']
    result = await finish(client, first, run_id)
    assert result['status'] == 'completed'
    assert result['text'] and result['citations']
    duplicate = await client.post(f'/api/sessions/{session}/runs', headers=first, json=body)
    assert duplicate.json() == {'run_id': run_id, 'duplicate': True}
    assert (await client.get('/api/sessions', headers=second)).json() == []
    for path in [f'/api/sessions/{session}/messages', f'/api/runs/{run_id}']:
        assert (await client.get(path, headers=second)).status_code == 404
    assert (await client.post(f'/api/runs/{run_id}/cancel', headers=second)).status_code == 404
    renewed, again = await guest(client, 'a' * 64)
    assert again['user']['id'] == a['user']['id']
    assert len((await client.get('/api/sessions', headers=renewed)).json()) == 1
    history = (await client.get(f'/api/sessions/{session}/messages', headers=renewed)).json()
    assert len(history) == 2 and history[-1]['content'] == result['text']
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Run)) == 1
        assert await db.scalar(select(func.count()).select_from(Message)) == 2
        assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 0


@pytest.mark.asyncio
async def test_gateway_blocks_owner_login_internal_jobs_and_forged_tokens(public, client):
    gateway, _ = public
    for method, path in [('GET','/api/jobs'), ('POST','/api/jobs'), ('POST','/api/auth/token'),
                         ('GET','/api/docs'), ('GET','/api/openapi.json'), ('POST','/api/internal/public/identity'),
                         ('POST','/api/internal/qq/events')]:
        assert (await gateway.request(method, path, json={})).status_code == 404
    # An authentic owner API token is still invalid at the public gateway.
    assert (await gateway.get('/api/sessions', headers={'Authorization': client.headers['Authorization']})).status_code == 401
    assert (await gateway.get('/api/sessions', headers={'Authorization': 'Bearer bogus.invalid'})).status_code == 401
    assert (await gateway.get('/api/sessions', headers={'X-Public-Edge': 'wrong'})).status_code == 401
    assert (await client.post('/internal/public/identity', json={'client_secret': 'a'*64})).status_code == 401


@pytest.mark.asyncio
async def test_public_has_no_question_quota_and_preserves_body_limit(public, app):
    client, _ = public
    headers, _ = await guest(client)
    session = (await client.post('/api/sessions', headers=headers, json={'title':'额度测试'})).json()['id']
    body = {'message':'曹操有哪些技能', 'request_id':str(uuid.uuid4())}
    response = await client.post(f'/api/sessions/{session}/runs', headers=headers, json=body)
    await finish(client, headers, response.json()['run_id'])
    assert (await client.post(f'/api/sessions/{session}/runs', headers=headers, json=body)).status_code == 202
    body['request_id'] = str(uuid.uuid4())
    response = await client.post(f'/api/sessions/{session}/runs', headers=headers, json=body)
    assert response.status_code == 202
    await finish(client, headers, response.json()['run_id'])
    for _ in range(10):
        body['request_id'] = str(uuid.uuid4())
        response = await client.post(f'/api/sessions/{session}/runs', headers=headers, json=body)
        assert response.status_code == 202
        await finish(client, headers, response.json()['run_id'])
    health = (await client.get('/api/health', headers=headers)).json()
    assert health['model_mode'] == 'mock' and 'budget' not in health and 'model_id' not in health
    assert (await client.post('/api/sessions', headers=headers, content=b'x'*48001)).status_code == 413


@pytest.mark.asyncio
async def test_owner_identity_rejected_at_public_run(public, client):
    _, config = public
    response = await client.post('/internal/public/sessions/' + str(uuid.uuid4()) + '/runs',
                                 headers={'X-Public-Service':config.service_token},
                                 json={'message':'a','request_id':str(uuid.uuid4())})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_polling_discards_unconsumed_events():
    queue = DiscardEvents()
    for _ in range(10000):
        await queue.put(('delta', {'text':'内容'}))
    assert queue.qsize() == 0


@pytest.mark.asyncio
async def test_public_still_uses_the_existing_global_monetary_budget(public, app):
    client, _ = public
    settings = app.state.settings
    settings.model_mode = 'live'
    settings.model_api_key = 'test-double-key'
    settings.model_id = 'test-double-model'
    settings.model_input_cny_per_million = 2
    settings.model_output_cny_per_million = 8
    async with app.state.database.sessions.begin() as db:
        account = await db.get(BudgetAccount, 1)
        account.spent = 199.99
    headers, _ = await guest(client)
    session = (await client.post('/api/sessions', headers=headers, json={'title':'预算测试'})).json()['id']
    response = await client.post(f'/api/sessions/{session}/runs', headers=headers,
                                 json={'message':'曹操技能','request_id':str(uuid.uuid4())})
    result = await finish(client, headers, response.json()['run_id'])
    assert result['status'] == 'failed' and '预算不足' in result['error']
    async with app.state.database.sessions() as db:
        account = await db.get(BudgetAccount, 1)
        assert account.spent == 199.99 and account.reserved == 0
        assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 0


@pytest.mark.asyncio
async def test_public_feedback_ownership_and_explicit_confirmation(public):
    client, _ = public
    a, _ = await guest(client)
    b, _ = await guest(client)
    draft = (await client.post('/api/feedback-drafts', headers=a, json={'actual':'点击按钮没有响应','category':'client'})).json()
    assert (await client.get('/api/feedback', headers=a)).json() == []
    identifier = draft['id']
    assert (await client.patch('/api/feedback-drafts/'+identifier, headers=b, json={'actual':'修改','revision':1})).status_code == 404
    assert (await client.post('/api/feedback-drafts/'+identifier+'/confirm', headers=b, json={'revision':1})).status_code == 404
    first = (await client.post('/api/feedback-drafts/'+identifier+'/confirm', headers=a, json={'revision':1})).json()
    again = (await client.post('/api/feedback-drafts/'+identifier+'/confirm', headers=a, json={'revision':1})).json()
    assert first['id'] == again['id'] and again['duplicate']
    assert (await client.get('/api/feedback', headers=b)).json() == []
