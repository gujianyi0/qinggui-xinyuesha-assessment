import copy
import json

import pytest
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
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User).where(User.username == "alice"))
    job = await app.state.jobs.create(user.id, app.state.catalog.active_id, "old-model")
    await app.state.jobs.process(await app.state.jobs.claim(job.id, 0))
    await app.state.search.search("诸葛亮", job.snapshot_id)
    app.state.settings.embedding_revision = "different-revision"
    with pytest.raises(ValueError, match="重新导入"):
        await app.state.search.search("诸葛亮", job.snapshot_id)


@pytest.mark.parametrize(
    "corruption",
    ["json_object", "json_list", "snapshot", "source_snapshot", "mode", "items", "hash", "line_range", "too_many"],
)
async def test_bad_but_valid_json_cache_is_ignored_and_repaired(app, corruption):
    search = app.state.search
    await search.cache.aclose()
    search.cache = cache = MemoryCache()
    snapshot = app.state.catalog.active_id
    original = await search.search("诸葛亮空城", snapshot)
    key = next(iter(cache.values))
    bad = copy.deepcopy(original)
    if corruption == "json_object":
        bad = {"stale_canary": True}
    elif corruption == "json_list":
        bad = []
    elif corruption == "snapshot":
        bad["snapshot_id"] = "other-snapshot"
    elif corruption == "source_snapshot":
        bad["items"][0]["source"]["snapshot_id"] = "other-snapshot"
    elif corruption == "mode":
        bad["mode"] = "pgvector"
    elif corruption == "items":
        bad["items"] = "not-a-list"
    elif corruption == "hash":
        bad["items"][0]["source"]["sha256"] = "missing-hash"
    elif corruption == "line_range":
        bad["items"][0]["source"]["line_end"] = 0
    elif corruption == "too_many":
        bad["items"] = original["items"] * 10
    cache.values[key] = json.dumps(bad)
    assert await search.search("诸葛亮空城", snapshot) == original
    assert json.loads(cache.values[key]) == original


async def test_valid_cache_hit_does_not_rescan_catalog(app):
    search = app.state.search
    await search.cache.aclose()
    search.cache = MemoryCache()
    original = await search.search("诸葛亮空城", app.state.catalog.active_id)
    app.state.catalog.documents = []
    assert await search.search("诸葛亮空城", app.state.catalog.active_id) == original
