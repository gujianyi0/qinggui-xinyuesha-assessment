"""Exact-name lookups keep evidence, cancellation and zero-cost accounting."""
import asyncio
import json

import pytest

from backend.app.models import BudgetAccount, Run, UsageRecord


@pytest.mark.parametrize('message', ['闪', '杀', '桃', '【闪】'])
async def test_exact_card_avoids_model_and_fuzzy_neighbors(app, client, message, monkeypatch):
    app.state.settings.model_mode = 'live'
    app.state.runtime.semaphore = asyncio.Semaphore(0)

    async def forbidden(*args, **kwargs):
        raise AssertionError('Exact card must not invoke paid model or RAG')

    monkeypatch.setattr(app.state.runtime, 'reserve_budget', forbidden)
    monkeypatch.setattr(app.state.search, 'search', forbidden)
    session = (await client.post('/sessions', json={})).json()
    response = await client.post(f"/sessions/{session['id']}/runs", json={'message': message})
    records = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    saved = (await client.get(f"/runs/{records[0]['run_id']}")).json()
    assert saved['status'] == 'completed'
    assert saved['prompt_version'] == 'catalog-card-fast-v1'
    assert saved['input_tokens'] == saved['output_tokens'] == 0
    assert '未调用模型' in saved['text']
    assert '闪电' not in saved['text']
    assert saved['citations'] and all(c['snapshot_id'] == saved['snapshot_id'] for c in saved['citations'])
    assert all('牌堆配置' not in c['title'] for c in saved['citations'])
    assert [t['name'] for t in saved['tool_calls']] == ['query_game_data']
    assert saved['tool_calls'][0]['result']['model_called'] is False
    async with app.state.database.sessions() as db:
        usage = await db.get(UsageRecord, saved['id'])
        account = await db.get(BudgetAccount, 1)
        assert usage.settled and not usage.estimated and usage.charged_cny == 0
        assert account.spent == account.reserved == 0


@pytest.mark.parametrize('message', ['闪的使用时机是什么？', '闪和杀', '帮我反馈闪的异常', 'SC01 闪', '【闪', '不存在的牌'])
async def test_compound_and_feedback_do_not_enter_exact_path(app, message):
    assert app.state.catalog.exact_card(message, app.state.catalog.active_id) is None


async def test_cancelled_exact_run_stays_terminal(app, client):
    app.state.settings.model_mode = 'live'
    session = (await client.post('/sessions', json={})).json()
    async with app.state.database.sessions.begin() as db:
        from backend.app.models import ChatSession
        owner = await db.get(ChatSession, session['id'])
        run = Run(user_id=owner.user_id, session_id=owner.id, snapshot_id=app.state.catalog.active_id,
                  model_mode='live', status='cancelled')
        db.add(run)
        await db.flush()
        run_id = run.id
    app.state.runtime.start(run_id, '闪')
    await app.state.runtime.tasks[run_id]
    async with app.state.database.sessions() as db:
        assert (await db.get(Run, run_id)).status == 'cancelled'
        assert await db.get(UsageRecord, run_id) is None


async def test_warmup_failure_is_observable_without_crashing(app, monkeypatch):
    embedder = app.state.search.embedder

    async def fail(*args, **kwargs):
        raise RuntimeError('private path must not leak')

    monkeypatch.setattr(embedder, 'encode', fail)
    await embedder.warmup()
    assert embedder.diagnostics()['warmup'] == 'failed'
    assert 'private' not in str(embedder.diagnostics())


async def test_wrong_snapshot_or_ambiguous_card_is_not_shortcut(app):
    catalog = app.state.catalog
    assert catalog.exact_card('闪', 'wrong-snapshot') is None
    card = catalog.exact_card('闪', catalog.active_id)
    catalog.entities.append({**card, 'id': 'conflicting-card'})
    assert catalog.exact_card('闪', catalog.active_id) is None
