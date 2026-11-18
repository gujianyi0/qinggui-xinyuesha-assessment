import asyncio

import pytest
from sqlalchemy import select

from backend.app.models import BudgetAccount, ChatSession, Run, UsageRecord, User
from backend.app.runtime import ModelFailure


async def stored_run(app):
    async with app.state.database.sessions.begin() as db:
        user = await db.scalar(select(User).where(User.username == "alice"))
        session = ChatSession(user_id=user.id, title="runtime test")
        db.add(session)
        await db.flush()
        run = Run(user_id=user.id, session_id=session.id, model_mode="mock", snapshot_id=app.state.catalog.active_id)
        db.add(run)
        await db.flush()
        return run


async def test_cancel_during_generation_remains_terminal(app):
    run = await stored_run(app)
    app.state.runtime.start(run.id, "[test:timeout]")
    task = app.state.runtime.tasks[run.id]
    await app.state.runtime.cancel(run.id)
    await task
    async with app.state.database.sessions() as db:
        assert (await db.get(Run, run.id)).status == "cancelled"


async def test_concurrency_rejection_is_recorded(app):
    run = await stored_run(app)
    app.state.runtime.semaphore = asyncio.Semaphore(0)
    queue = app.state.runtime.start(run.id, "诸葛亮")
    await app.state.runtime.tasks[run.id]
    async with app.state.database.sessions() as db:
        saved = await db.get(Run, run.id)
        assert saved.status == "failed" and "并发" in saved.error
    assert not queue.empty()


async def test_budget_reservation_settlement_and_cap(app):
    run = await stored_run(app)
    settings = app.state.settings
    settings.model_api_key, settings.model_id = "test-only", "test-model"
    settings.model_input_cny_per_million = settings.model_output_cny_per_million = 1
    amount = await app.state.runtime.reserve_budget(run.id)
    assert amount > 0
    await app.state.runtime.settle_budget(run.id, 100, 50, True)
    await app.state.runtime.settle_budget(run.id, 100, 50, True)
    async with app.state.database.sessions.begin() as db:
        budget = await db.get(BudgetAccount, 1)
        assert budget.spent == pytest.approx(0.00015)
        assert budget.reserved == pytest.approx(0)
        budget.spent = 200
    with pytest.raises(ModelFailure, match="预算不足"):
        await app.state.runtime.reserve_budget((await stored_run(app)).id)


async def test_restart_releases_stuck_session_and_conservatively_settles(app):
    run = await stored_run(app)
    async with app.state.database.sessions.begin() as db:
        db.add(UsageRecord(run_id=run.id, reserved_cny=1))
        budget = await db.get(BudgetAccount, 1)
        budget.reserved = 1
    await app.state.runtime.recover_interrupted()
    await app.state.runtime.recover_interrupted()
    async with app.state.database.sessions() as db:
        saved = await db.get(Run, run.id)
        assert saved.status == "failed" and saved.retryable
        budget = await db.get(BudgetAccount, 1)
        assert budget.reserved == 0 and budget.spent == 1
