import asyncio
import datetime as dt

import pytest
from sqlalchemy import func, select, update

from backend.app.chunking import chunk_documents
from backend.app.jobs import StaleExecution
from backend.app.models import IndexedChunk, Job, JobAttempt, Outbox, PublishedIndex, User, now


async def new_job(app, key="job"):
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User).where(User.username == "alice"))
    return await app.state.jobs.create(user.id, app.state.catalog.active_id, key)


async def test_concurrent_claim_duplicate_and_atomic_publish(app):
    job = await new_job(app)
    claimed = await asyncio.gather(*(app.state.jobs.claim(job.id, 0) for _ in range(4)))
    assert len([j for j in claimed if j]) == 1
    active = next(j for j in claimed if j)
    await app.state.jobs.process(active)
    assert await app.state.jobs.claim(job.id, 0) is None
    async with app.state.database.sessions() as db:
        saved = await db.get(Job, job.id)
        published = await db.get(PublishedIndex, job.snapshot_id)
        assert saved.status == "succeeded" and saved.attempts == 1
        assert published.job_id == job.id
        assert await db.scalar(select(func.count()).select_from(IndexedChunk)) == len(chunk_documents(app.state.catalog.documents))
    # A stale failure or cancel must not overwrite the successful terminal state.
    await app.state.jobs.fail(job.id, active.generation, ConnectionError())
    assert (await app.state.jobs.cancel(job.id)).status == "succeeded"


async def test_persisted_retry_exhaustion_does_not_block_other_job(app):
    job = await new_job(app)
    for attempt in range(3):
        async with app.state.database.sessions() as db:
            current = await db.get(Job, job.id)
        active = await app.state.jobs.claim(job.id, current.generation)
        with pytest.raises(ConnectionError):
            await app.state.jobs.process(active, fault="temporary")
        await app.state.jobs.fail(job.id, active.generation, ConnectionError())
        async with app.state.database.sessions.begin() as db:
            saved = await db.get(Job, job.id)
            assert saved.status == ("retry_wait" if attempt < 2 else "failed")
            assert await db.get(PublishedIndex, job.snapshot_id) is None
            saved.retry_at = now() - dt.timedelta(seconds=1)
        await app.state.jobs.recover()
    good = await new_job(app, "good")
    await app.state.jobs.process(await app.state.jobs.claim(good.id, 0))
    async with app.state.database.sessions() as db:
        assert (await db.get(Job, job.id)).attempts == 3
        assert (await db.get(Job, good.id)).status == "succeeded"


async def test_expired_lease_fences_old_execution(app):
    job = await new_job(app)
    old = await app.state.jobs.claim(job.id, 0)
    async with app.state.database.sessions.begin() as db:
        await db.execute(update(Job).where(Job.id == job.id).values(lease_until=now() - dt.timedelta(seconds=1)))
    await app.state.jobs.recover()
    with pytest.raises(StaleExecution):
        await app.state.jobs.process(old)
    async with app.state.database.sessions() as db:
        recovered = await db.get(Job, job.id)
        assert recovered.status == "queued"
        assert await db.scalar(select(func.count()).select_from(Outbox).where(Outbox.job_id == job.id)) == 2
    replacement = await app.state.jobs.claim(job.id, recovered.generation)
    await app.state.jobs.process(replacement)
    await app.state.jobs.fail(job.id, old.generation, ValueError("迟到"))
    async with app.state.database.sessions() as db:
        assert (await db.get(Job, job.id)).status == "succeeded"


async def test_cancel_before_publish_and_no_partial_visibility(app):
    job = await new_job(app)
    active = await app.state.jobs.claim(job.id, 0)
    original = app.state.jobs.embedder.encode
    cancelled = False

    async def cancel_during_encoding(texts):
        nonlocal cancelled
        vectors = await original(texts)
        if not cancelled:
            await app.state.jobs.cancel(job.id)
            cancelled = True
        return vectors

    app.state.jobs.embedder.encode = cancel_during_encoding
    with pytest.raises(StaleExecution):
        await app.state.jobs.process(active)
    await app.state.jobs.fail(job.id, active.generation, StaleExecution())
    async with app.state.database.sessions() as db:
        assert (await db.get(Job, job.id)).status == "cancelled"
        assert await db.get(PublishedIndex, job.snapshot_id) is None
    assert await app.state.jobs.claim(job.id, 0) is None


async def test_bad_input_retained_without_retry(app):
    job = await new_job(app)
    active = await app.state.jobs.claim(job.id, 0)
    app.state.jobs.catalog.documents = []
    with pytest.raises(ValueError) as error:
        await app.state.jobs.process(active)
    await app.state.jobs.fail(job.id, active.generation, error.value)
    async with app.state.database.sessions() as db:
        assert (await db.get(Job, job.id)).status == "failed"
        attempt = await db.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id))
        assert attempt.status == "failed" and attempt.error


async def test_cancelled_worker_lease_recovery(app):
    job = await new_job(app)
    await app.state.jobs.claim(job.id, 0)
    await app.state.jobs.cancel(job.id)
    async with app.state.database.sessions.begin() as db:
        await db.execute(update(Job).where(Job.id == job.id).values(lease_until=now() - dt.timedelta(seconds=1)))
    await app.state.jobs.recover()
    async with app.state.database.sessions() as db:
        assert (await db.get(Job, job.id)).status == "cancelled"
        assert (await db.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id))).status == "cancelled"


async def test_cache_down_falls_back_to_published_vectors(app):
    job = await new_job(app)
    await app.state.jobs.process(await app.state.jobs.claim(job.id, 0))
    result = await app.state.search.search("诸葛亮空城", job.snapshot_id)
    assert result["mode"] == "test_vectors" and result["items"]
