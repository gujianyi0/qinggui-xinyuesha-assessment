import json
from pathlib import Path

import httpx
import pytest

from backend.app.bookshelf_progress import LEARNING_IDS


@pytest.fixture
def upstream(app, monkeypatch):
    state = {'ids': ['1-01'], 'revision': 3, 'initialized': True, 'updatedAt': '2026-11-17T00:00:00Z'}
    app.state.settings.bookshelf_owner_key = 'fixture-owner-key-not-real'
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/api/session':
            assert request.headers['origin'] == app.state.settings.bookshelf_progress_url
            assert json.loads(request.content)['key'] == 'fixture-owner-key-not-real'
            return httpx.Response(200, json={'owner': True}, headers={'Set-Cookie': 'owner=fixture; Path=/; Secure'})
        if request.method == 'PATCH':
            assert 'owner=fixture' in request.headers['cookie']
            body = json.loads(request.content)
            if body['revision'] != state['revision']:
                return httpx.Response(409, json={'error': 'conflict'})
            state['ids'] = [body['id']] if body['learned'] else []
            state['revision'] += 1
        return httpx.Response(200, json=state)

    original = httpx.AsyncClient
    monkeypatch.setattr(app.state.shelf_progress, 'client', lambda: original(
        base_url=app.state.settings.bookshelf_progress_url,
        transport=httpx.MockTransport(handler),
        headers={'Origin': app.state.settings.bookshelf_progress_url},
    ))
    return state, calls


async def test_shared_progress_owner_write_and_secret_boundary(app, client, upstream):
    before = (await client.get('/bookshelf/progress')).json()
    assert before['ids'] == ['1-01'] and before['can_edit']
    response = await client.patch('/bookshelf/progress', json={'id': '7-07', 'learned': True, 'revision': 3})
    assert response.status_code == 200
    assert response.json()['ids'] == ['7-07'] and response.json()['revision'] == 4
    assert 'fixture-owner' not in response.text
    stale = await client.patch('/bookshelf/progress', json={'id': '1-01', 'learned': False, 'revision': 3})
    assert stale.status_code == 409
    assert (await client.get('/bookshelf/progress')).json()['ids'] == ['7-07']


async def test_shared_progress_other_identity_read_only(client, upstream):
    login = (await client.post('/auth/token', json={'username': 'bob', 'password': 'local-demo-change-me'})).json()
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    result = await client.get('/bookshelf/progress', headers=headers)
    assert result.status_code == 200 and not result.json()['can_edit']
    calls = len(upstream[1])
    response = await client.patch('/bookshelf/progress', headers=headers, json={'id': '1-01', 'learned': True, 'revision': 3})
    assert response.status_code == 403 and len(upstream[1]) == calls


async def test_review_and_invalid_progress_not_forwarded(client, upstream):
    for body in [{'id': '8-01', 'learned': True, 'revision': 3},
                 {'id': '1-01', 'learned': 'true', 'revision': 3},
                 {'id': '1-01', 'learned': True, 'revision': True}]:
        response = await client.patch('/bookshelf/progress', json=body)
        assert response.status_code == 422
    assert not upstream[1]
    data = json.loads(Path('tools/bookshelf/base/data.json').read_text(encoding='utf-8'))
    assert LEARNING_IDS == {record['id'] for record in data['records']}


async def test_progress_failure_is_not_an_empty_success(app, client, monkeypatch):
    def fail(request):
        raise httpx.ConnectError('private upstream failure')
    original = httpx.AsyncClient
    monkeypatch.setattr(app.state.shelf_progress, 'client', lambda: original(
        base_url=app.state.settings.bookshelf_progress_url, transport=httpx.MockTransport(fail)))
    response = await client.get('/bookshelf/progress')
    assert response.status_code == 503 and 'ids' not in response.json()
    assert 'private' not in response.text


async def test_transient_read_retries_once_without_repeating_a_write(app, client, monkeypatch):
    calls = []
    def flaky(request):
        calls.append(request.method)
        if len(calls) == 1:
            raise httpx.ConnectError('transient')
        return httpx.Response(200, json={'ids': ['1-01'], 'revision': 1, 'initialized': True})
    original = httpx.AsyncClient
    monkeypatch.setattr(app.state.shelf_progress, 'client', lambda: original(
        base_url=app.state.settings.bookshelf_progress_url, transport=httpx.MockTransport(flaky)))
    response = await client.get('/bookshelf/progress')
    assert response.status_code == 200 and response.json()['ids'] == ['1-01']
    assert calls == ['GET', 'GET']
