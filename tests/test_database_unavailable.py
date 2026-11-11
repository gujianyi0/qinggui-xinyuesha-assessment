import socket

import asyncpg
import httpx
import pytest

from backend.app.config import Settings
from backend.app.db import Database


async def unavailable_requests(app, database):
    original = app.state.database.sessions
    app.state.database.sessions = database.sessions
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/health", "/sessions"):
                response = await client.get(path, headers={"Authorization": "Bearer test"})
                assert response.status_code == 503
                assert response.json() == {"detail": "数据库暂时不可用，请稍后重试", "retryable": True}
                assert "should-not-leak" not in response.text
    finally:
        app.state.database.sessions = original
        await database.close()


async def test_actual_refused_postgres_socket_is_retryable_503(app):
    # Hold a loopback port without listening: no external server or DNS needed.
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
        database = Database(Settings(_env_file=None, database_url=f"postgresql+asyncpg://assessment:should-not-leak@127.0.0.1:{port}/assessment"))
        await unavailable_requests(app, database)


@pytest.mark.parametrize("error", [socket.gaierror(-3, "should-not-leak"), TimeoutError("should-not-leak")])
async def test_asyncpg_dns_and_timeout_are_retryable_503(app, monkeypatch, error):
    async def failed_connection(*args, **kwargs):
        raise error
    monkeypatch.setattr(asyncpg, "connect", failed_connection)
    database = Database(Settings(_env_file=None, database_url="postgresql+asyncpg://assessment@127.0.0.1:1/assessment"))
    await unavailable_requests(app, database)


async def test_non_database_file_error_is_not_mislabeled_as_retryable_database_failure(app):
    @app.get("/fixture/file-error")
    async def file_error():
        raise PermissionError("fixture file access error")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.get("/fixture/file-error")
        assert response.status_code == 500
        assert "retryable" not in response.text
