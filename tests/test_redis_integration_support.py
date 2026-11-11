import hashlib
import json

import pytest

from backend.app.redis_assets import SHA256, VERSION, prepared_redis


def test_unprepared_redis_is_optional(tmp_path):
    assert prepared_redis(tmp_path) is None


@pytest.mark.parametrize("invalid", [None, "version", "archive", "binary", "path"])
def test_prepared_redis_requires_pinned_archive_and_exact_executable(tmp_path, invalid):
    folder = tmp_path / ".local/native-redis"
    folder.mkdir(parents=True)
    server = folder / "redis-server.exe"
    server.write_bytes(b"not executable: fixture checksum only")
    manifest = {
        "server": str(server),
        "version": VERSION,
        "sha256": SHA256,
        "server_sha256": hashlib.sha256(server.read_bytes()).hexdigest(),
    }
    if invalid == "version":
        manifest["version"] = "other"
    elif invalid == "archive":
        manifest["sha256"] = "wrong"
    elif invalid == "binary":
        manifest["server_sha256"] = "wrong"
    elif invalid == "path":
        manifest["server"] = str(tmp_path / "outside.exe")
    (folder / "dependency.json").write_text(json.dumps(manifest), encoding="utf-8")
    if invalid:
        with pytest.raises(ValueError):
            prepared_redis(tmp_path)
    else:
        assert prepared_redis(tmp_path) == server.resolve()


async def test_cache_health_is_separate_from_api_and_database_health(client, app, monkeypatch):
    async def down():
        raise ConnectionError("fixture")

    async def up():
        return True

    monkeypatch.setattr(app.state.search.cache, "ping", down)
    response = await client.get("/health")
    assert response.status_code == 200 and response.json()["cache"] == "unavailable_fallback"
    assert response.json()["status"] == "ok" and response.json()["database"] == "sqlite"
    monkeypatch.setattr(app.state.search.cache, "ping", up)
    assert (await client.get("/health")).json()["cache"] == "available"
