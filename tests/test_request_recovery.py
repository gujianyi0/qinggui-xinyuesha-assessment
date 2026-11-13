import asyncio
import uuid

from sqlalchemy import func, select

from backend.app.models import Message, Run, UsageRecord


async def test_lost_receipt_recovers_same_id_and_rejects_changed_payload(client, app):
    session = (await client.post('/sessions', json={})).json()['id']
    request_id = str(uuid.uuid4())
    body = {'message':'查询曹操技能','request_id':request_id}
    first = await client.post(f'/sessions/{session}/submissions', json=body)
    assert first.status_code == 202
    found = await client.get(f'/sessions/{session}/requests/{request_id}')
    assert found.json()['run_id'] == first.json()['run_id']
    responses = await asyncio.gather(*[client.post(f'/sessions/{session}/submissions', json=body) for _ in range(8)])
    assert all(r.status_code == 202 and r.json()['run_id']==first.json()['run_id'] and r.json()['duplicate'] for r in responses)
    assert (await client.post(f'/sessions/{session}/submissions', json=body | {'message':'换一个问题'})).status_code == 409
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Run)) == 1
        assert await db.scalar(select(func.count()).select_from(Message).where(Message.role=='user')) == 1


async def test_cancel_before_delayed_submission_never_starts_model(client, app):
    session = (await client.post('/sessions', json={})).json()['id']
    request_id = str(uuid.uuid4())
    body = {'message':'查询曹操技能','request_id':request_id}
    cancelled = await client.post(f'/sessions/{session}/requests/{request_id}/cancel', json=body)
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    delayed = await client.post(f'/sessions/{session}/submissions', json=body)
    assert delayed.status_code == 202 and delayed.json()['duplicate']
    assert (await client.get('/runs/'+delayed.json()['run_id'])).json()['status'] == 'cancelled'
    assert app.state.runtime.tasks == {}
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 0


async def test_recovery_and_cancel_request_check_ownership(client, app):
    session = (await client.post('/sessions', json={})).json()['id']
    request_id = str(uuid.uuid4())
    body = {'message':'曹操技能','request_id':request_id}
    await client.post(f'/sessions/{session}/submissions', json=body)
    token = (await client.post('/auth/token', json={'username':'bob','password':'local-demo-change-me'})).json()['access_token']
    headers = {'Authorization':'Bearer '+token}
    assert (await client.get(f'/sessions/{session}/requests/{request_id}', headers=headers)).status_code == 404
    assert (await client.post(f'/sessions/{session}/requests/{request_id}/cancel', headers=headers, json=body)).status_code == 404
    assert (await client.get(f'/sessions/{session}/requests/{uuid.uuid4()}')).status_code == 404


async def test_accepted_local_run_can_reconnect_to_stream_and_saved_result(client):
    session = (await client.post('/sessions', json={})).json()['id']
    result = await client.post(f'/sessions/{session}/submissions', json={'message':'曹操技能','request_id':str(uuid.uuid4())})
    identifier = result.json()['run_id']
    stream = await client.get(f'/runs/{identifier}/events')
    assert 'event: started' in stream.text and 'event: delta' in stream.text and 'event: completed' in stream.text
    again = await client.get(f'/runs/{identifier}/events')
    assert 'event: completed' in again.text
    assert (await client.get(f'/runs/{identifier}')).json()['status'] == 'completed'
