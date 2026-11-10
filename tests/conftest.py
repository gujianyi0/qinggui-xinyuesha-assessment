import httpx
import pytest
import pytest_asyncio

from backend.app.config import Settings
from backend.app.main import create_app


@pytest_asyncio.fixture
async def app(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        create_schema=True, embedding_mode="test", model_mode="mock",
        redis_url="redis://127.0.0.1:1/0", enable_test_faults=True,
        model_timeout_seconds=0.08,
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/token", json={"username": "alice", "password": "local-demo-change-me"})
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


@pytest.fixture
def snapshot(app):
    return app.state.catalog.active_id
