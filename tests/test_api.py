import json

import httpx
import pytest

from backend.app.main import create_app


def events(response):
    response.raise_for_status()
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


async def test_stream_audit_and_restart(client, app):
    session = (await client.post("/sessions", json={})).json()
    response = await client.post(f"/sessions/{session['id']}/runs", json={"message": "诸葛亮有哪些技能"})
    data = events(response)
    run_id = data[0]["run_id"]
    assert data[-1]["citations"]
    run = (await client.get(f"/runs/{run_id}")).json()
    assert run["status"] == "completed"
    assert {t["name"] for t in run["tool_calls"]} == {"query_game_data", "search_knowledge"}
    assert "诸葛亮" in run["text"]
    second = create_app(app.state.settings)
    async with second.router.lifespan_context(second):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="http://test", headers=client.headers) as restarted:
            messages = (await restarted.get(f"/sessions/{session['id']}/messages")).json()
            assert [m["role"] for m in messages] == ["user", "assistant"]
            assert (await restarted.get(f"/runs/{run_id}")).json()["status"] == "completed"


async def test_two_identity_isolation(client, app, snapshot):
    session = (await client.post("/sessions", json={})).json()
    draft = (await client.post("/feedback-drafts", json={"actual": "异常", "session_id": session["id"]})).json()
    feedback = (await client.post(f"/feedback-drafts/{draft['id']}/confirm", json={"revision": 1})).json()
    job = (await client.post("/jobs", json={"snapshot_id": snapshot, "idempotency_key": "alice-only"})).json()
    run_id = events(await client.post(f"/sessions/{session['id']}/runs", json={"message": "诸葛亮"}))[0]["run_id"]
    bob = (await client.post("/auth/token", json={"username": "bob", "password": "local-demo-change-me"})).json()
    headers = {"Authorization": f"Bearer {bob['access_token']}"}
    for path in [f"/sessions/{session['id']}/messages", f"/runs/{run_id}", f"/jobs/{job['id']}"]:
        assert (await client.get(path, headers=headers)).status_code == 404
    for path, body in [(f"/feedback-drafts/{draft['id']}/confirm", {"revision": 1}),
                       (f"/jobs/{job['id']}/cancel", None), (f"/runs/{run_id}/cancel", None),
                       (f"/sessions/{session['id']}/runs", {"message": "读取记录"}),
                       ("/feedback-drafts", {"session_id": session["id"], "actual": "越权"})]:
        assert (await client.post(path, json=body, headers=headers)).status_code == 404
    for path in ["/sessions", "/feedback-drafts", "/feedback", "/jobs"]:
        assert (await client.get(path, headers=headers)).json() == []
    assert feedback["id"]


async def test_draft_revision_confirm_and_duplicate(client):
    draft = (await client.post("/feedback-drafts", json={"actual": "第一次异常"})).json()
    assert (await client.get("/feedback")).json() == []
    edited = await client.patch(f"/feedback-drafts/{draft['id']}", json={"revision": 1, "expected": "应正常结算"})
    assert edited.json()["revision"] == 2
    assert (await client.post(f"/feedback-drafts/{draft['id']}/confirm", json={"revision": 1})).status_code == 409
    first = (await client.post(f"/feedback-drafts/{draft['id']}/confirm", json={"revision": 2})).json()
    repeat = (await client.post(f"/feedback-drafts/{draft['id']}/confirm", json={"revision": 2})).json()
    assert first["id"] == repeat["id"] and repeat["duplicate"]
    assert len((await client.get("/feedback")).json()) == 1
    assert (await client.patch(f"/feedback-drafts/{draft['id']}", json={"revision": 2, "actual": "改写"})).status_code == 409


@pytest.mark.parametrize("message", ["", "   ", "长" * 8001])
async def test_input_rejected_before_stream(client, message):
    session = (await client.post("/sessions", json={})).json()
    assert (await client.post(f"/sessions/{session['id']}/runs", json={"message": message})).status_code == 422
    assert (await client.get(f"/sessions/{session['id']}/messages")).json() == []


@pytest.mark.parametrize("message,reason", [("[test:timeout]", "超时"), ("[test:format]", "格式")])
async def test_model_failures_persist(client, message, reason):
    session = (await client.post("/sessions", json={})).json()
    data = events(await client.post(f"/sessions/{session['id']}/runs", json={"message": message}))
    assert reason in data[-1]["error"]
    run = (await client.get(f"/runs/{data[0]['run_id']}")).json()
    assert run["status"] == "failed"
    assert len((await client.get(f"/sessions/{session['id']}/messages")).json()) == 1


async def test_tool_failure_audited(client):
    session = (await client.post("/sessions", json={})).json()
    data = events(await client.post(f"/sessions/{session['id']}/runs", json={"message": "诸葛亮"}, headers={"X-Assessment-Fault": "tool_unavailable"}))
    run = (await client.get(f"/runs/{data[0]['run_id']}")).json()
    assert all(t["status"] == "failed" for t in run["tool_calls"])
    assert run["citations"] == []


async def test_job_idempotency_and_invalid_snapshot(client, snapshot):
    body = {"snapshot_id": snapshot, "idempotency_key": "same"}
    one, two = await client.post("/jobs", json=body), await client.post("/jobs", json=body)
    assert one.status_code == two.status_code == 202
    assert one.json()["id"] == two.json()["id"]
    assert (await client.post("/jobs", json={**body, "snapshot_id": "unavailable"})).status_code == 422
    assert len((await client.get("/jobs")).json()) == 1


async def test_auth_and_unknown_fields(client):
    assert (await client.get("/sessions", headers={"Authorization": "Bearer invalid"})).status_code == 401
    assert (await client.post("/auth/token", json={"username": "alice", "password": "wrong"})).status_code == 401
    assert (await client.post("/feedback-drafts", json={"actual": "异常", "user_id": "bob"})).status_code == 422
