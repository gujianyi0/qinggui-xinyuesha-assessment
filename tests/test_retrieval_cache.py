from sqlalchemy import select

from backend.app.models import User


class MemoryCache:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        assert ttl > 0
        self.values[key] = value

    async def aclose(self):
        pass


async def test_newly_published_index_does_not_reuse_unindexed_cached_answer(app):
    search = app.state.search
    await search.cache.aclose()
    search.cache = cache = MemoryCache()
    snapshot = app.state.catalog.active_id
    before = await search.search("诸葛亮空城", snapshot)
    assert before["mode"] == "lexical_unindexed"
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User).where(User.username == "alice"))
    job = await app.state.jobs.create(user.id, snapshot, "new-index")
    await app.state.jobs.process(await app.state.jobs.claim(job.id, 0))
    after = await search.search("诸葛亮空城", snapshot)
    assert after["mode"] == "test_vectors" and after["items"]
    assert len(cache.values) == 2


async def test_embedding_change_requires_reindex_even_when_old_result_cached(app):
    import pytest
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User).where(User.username == "alice"))
    job = await app.state.jobs.create(user.id, app.state.catalog.active_id, "old-model")
    await app.state.jobs.process(await app.state.jobs.claim(job.id, 0))
    await app.state.search.search("诸葛亮", job.snapshot_id)
    app.state.settings.embedding_revision = "different-revision"
    with pytest.raises(ValueError, match="重新导入"):
        await app.state.search.search("诸葛亮", job.snapshot_id)
