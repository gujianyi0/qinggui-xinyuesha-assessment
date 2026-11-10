"""Use real Agno + OpenAI SDK with in-memory HTTP protocol fixtures, never a paid model."""
import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI


def sse_response(*, tool=None, arguments=None, answer=None, input_tokens=12, output_tokens=4):
    base = {"id":"fixture-completion", "object":"chat.completion.chunk", "created":1, "model":"protocol-fixture"}
    if tool:
        delta = {"role":"assistant", "tool_calls":[{"index":0, "id":"fixture-call", "type":"function", "function":{"name":tool, "arguments":json.dumps(arguments, ensure_ascii=False)}}]}
        finish = "tool_calls"
    else:
        delta, finish = {"role":"assistant", "content":answer}, "stop"
    chunks = [
        {**base, "choices":[{"index":0, "delta":delta, "finish_reason":None}]},
        {**base, "choices":[{"index":0, "delta":{}, "finish_reason":finish}],
         "usage":{"prompt_tokens":input_tokens, "completion_tokens":output_tokens, "total_tokens":input_tokens+output_tokens}},
    ]
    encoded = "".join("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"Content-Type":"text/event-stream"}, content=encoded.encode())


@pytest.fixture
def protocol_model(app, monkeypatch):
    import agno.models.openai.like as module
    original = module.OpenAILike

    def install(handler):
        settings = app.state.settings
        settings.model_mode = "live"
        settings.model_base_url = "https://protocol-fixture.invalid/v1"
        settings.model_id = "protocol-fixture"
        settings.model_api_key = "fixture-not-a-real-key"
        settings.model_input_cny_per_million = settings.model_output_cny_per_million = 1
        settings.model_timeout_seconds = 20
        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = AsyncOpenAI(api_key=settings.model_api_key, base_url=settings.model_base_url, http_client=http, max_retries=0)
        monkeypatch.setattr(module, "OpenAILike", lambda **kwargs: original(**kwargs, async_client=client))
        return client

    yield install


async def run_question(client, message):
    session = (await client.post("/sessions", json={})).json()
    response = await client.post(f"/sessions/{session['id']}/runs", json={"message":message})
    assert response.status_code == 200
    records = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    stored = await client.get(f"/runs/{records[0]['run_id']}")
    return response.text, stored.json()


async def test_real_agno_tool_stream_usage_and_context(client, app, protocol_model):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return sse_response(tool="query_game_data", arguments={"query":"诸葛亮", "kind":"general"})
        assert any(message["role"] == "tool" and "zhugeliang" in message["content"] for message in body["messages"])
        return sse_response(answer="诸葛亮属于蜀势力，体力为3，技能为观星和空城。")

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "诸葛亮的势力、体力和技能是什么？")
        assert "event: completed" in stream
        assert run["status"] == "completed"
        assert len(requests) == 2
        assert run["tool_calls"][0]["name"] == "query_game_data"
        assert run["tool_calls"][0]["status"] == "succeeded"
        assert run["citations"] and all(c["snapshot_id"] == run["snapshot_id"] for c in run["citations"])
        assert run["input_tokens"] == 24 and run["output_tokens"] == 8
        assert not run["usage"]["estimated"] and run["usage"]["settled"]
        assert run["usage"]["charged_cny"] == pytest.approx(0.000032)
        assert sdk.is_closed()
    finally:
        await sdk.close()


@pytest.mark.parametrize("matched", [True, False])
async def test_real_agno_verified_ruling_has_evidence_citation(client, app, protocol_model, matched):
    scene = app.state.catalog.rulings()[0]
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id":scene["id"], "conditions":scene["conditions"] if matched else {}})
        return sse_response(answer=scene["summary"] if matched else "请先补充场景必要条件。")

    sdk = protocol_model(handler)
    try:
        _, run = await run_question(client, "请核对SC01，必要条件与已验证场景完全一致")
        assert run["status"] == "completed"
        assert run["tool_calls"][0]["result"]["status"] == ("verified" if matched else "needs_clarification")
        assert any(source["path"] == scene["evidence_path"] for source in run["citations"]) == matched
    finally:
        await sdk.close()


async def test_real_agno_protocol_timeout_settles_and_closes_client(client, app, protocol_model):
    async def handler(request):
        await asyncio.sleep(2)
        return sse_response(answer="不会完成的响应")

    sdk = protocol_model(handler)
    app.state.settings.model_timeout_seconds = 0.05
    try:
        _, run = await run_question(client, "诸葛亮有哪些技能？")
        assert run["status"] == "failed" and "超时" in run["error"]
        assert run["usage"]["settled"] and run["usage"]["estimated"]
        assert sdk.is_closed()
    finally:
        await sdk.close()


async def test_real_agno_provider_failure_is_not_success_and_does_not_leak_key(client, protocol_model):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error":{"message":"fixture unavailable", "type":"server_error"}})

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "诸葛亮有哪些技能？")
        assert run["status"] == "failed" and "event: failed" in stream
        assert "fixture-not-a-real-key" not in json.dumps(run)
        assert len(requests) == 1
        assert run["usage"]["settled"] and run["usage"]["estimated"]
    finally:
        await sdk.close()


async def test_unverified_ruling_cannot_stream_or_store_model_speculation(client, protocol_model):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id":"SC01", "conditions":{}})
        return sse_response(answer="未经验证也可以确定造成999点伤害。")

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "请裁定SC01，但我还没有提供完整条件")
        assert run["status"] == "completed"
        assert "999" not in stream and "999" not in run["text"]
        assert "暂不能判断" in run["text"]
        assert not run["citations"]
        assert run["tool_calls"][0]["result"]["status"] == "needs_clarification"
    finally:
        await sdk.close()


@pytest.mark.parametrize("scene_id,evidence", [("SC02", "SC02.json"), ("SC04", "SC04V.json")])
async def test_fixed_record_reference_is_scoped_and_cites_executed_variants(client, protocol_model, scene_id, evidence):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id":scene_id, "reference":True})
        body = json.loads(request.content)
        assert any(message["role"] == "tool" and "reference" in message["content"] for message in body["messages"])
        return sse_response(answer="" if scene_id == "SC04" else "错误推测：两次响应数=4，饮酒或交换防具任一成立都造成999点伤害。")

    sdk = protocol_model(handler)
    try:
        _, run = await run_question(client, f"请读取{scene_id}的固定测试记录")
        assert run["status"] == "completed" and "不表示你的完整局面已经匹配" in run["text"]
        assert "999" not in run["text"] and "响应数=4" not in run["text"]
        assert run["tool_calls"][0]["result"]["status"] == "reference"
        assert any(source["path"].endswith(evidence) for source in run["citations"])
    finally:
        await sdk.close()


async def test_feedback_context_uses_own_statements_without_game_skill_search(client, protocol_model):
    def handler(request):
        body = json.loads(request.content)
        assert not body.get("tools")
        prompt = str(body["messages"])
        assert "iOS页面卡住" in prompt and "尚未保存" in prompt
        return sse_response(answer="文字草稿：iOS页面卡住；版本、复现步骤待补充。尚未保存或提交，请在我的反馈核对后确认。")

    sdk = protocol_model(handler)
    try:
        _, run = await run_question(client, "iOS页面卡住，帮我提交反馈")
        assert run["status"] == "completed"
        assert [c["name"] for c in run["tool_calls"]] == ["prepare_feedback_context"]
        assert run["tool_calls"][0]["result"]["persisted"] is False
        assert all(s["evidence_type"] == "user_statement" and s["path"].startswith(f"conversation/{run['session_id']}/") for s in run["citations"])
    finally:
        await sdk.close()


async def test_official_deepseek_request_explicitly_disables_unconsumed_thinking(client, app, protocol_model):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        if calls == 1:
            return sse_response(tool="query_game_data", arguments={"query":"诸葛亮", "kind":"general"})
        return sse_response(answer="诸葛亮属于蜀，体力3，技能观星、空城。")

    sdk = protocol_model(handler)
    app.state.settings.model_base_url = "https://api.deepseek.com"
    try:
        _, run = await run_question(client, "查询诸葛亮属性")
        assert run["status"] == "completed" and run["citations"]
        assert calls == 2
    finally:
        await sdk.close()


async def test_empty_provider_body_is_retryable_failure_not_completed(client, protocol_model):
    sdk = protocol_model(lambda _: sse_response(answer=""))
    try:
        _, run = await run_question(client, "通常摸几张牌")
        assert run["status"] == "failed" and "未返回正文" in run["error"]
        assert run["retryable"] and run["usage"]["settled"]
    finally:
        await sdk.close()
