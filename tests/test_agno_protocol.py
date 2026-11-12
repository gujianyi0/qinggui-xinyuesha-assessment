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
        # Non-timing protocol assertions use the production request bound. The
        # explicit timeout test below still overrides this with 0.05 seconds.
        settings.model_timeout_seconds = 60
        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = AsyncOpenAI(api_key=settings.model_api_key, base_url=settings.model_base_url, http_client=http, max_retries=0)
        monkeypatch.setattr(module, "OpenAILike", lambda **kwargs: original(**kwargs, async_client=client))
        return client

    yield install


async def run_question(client, message, *, fault=None):
    session = (await client.post("/sessions", json={})).json()
    headers = {"X-Assessment-Fault": fault} if fault is not None else {}
    response = await client.post(f"/sessions/{session['id']}/runs", json={"message": message}, headers=headers)
    assert response.status_code == 200
    records = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    stored = await client.get(f"/runs/{records[0]['run_id']}")
    return response.text, stored.json()


async def test_followup_without_new_tool_preserves_checked_history_source(client, app, protocol_model):
    from backend.app.models import Message
    source = next(entity['source'] for entity in app.state.catalog.entities if entity['id'] == 'standard:skill:jianxiong')
    session = (await client.post('/sessions', json={})).json()
    async with app.state.database.sessions.begin() as db:
        previous = Message(session_id=session['id'], role='assistant', content='曹操的奸雄在受到伤害后发动。', citations=[source])
        db.add(previous)
        await db.flush()
        previous_id = previous.id
    model = protocol_model(lambda _: sse_response(answer='奸雄：当你受到伤害后，可以获得对你造成伤害的牌。'))
    response = await client.post(f"/sessions/{session['id']}/runs", json={'message':'继续解释刚才的奸雄时机'})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    run = (await client.get('/runs/' + events[0]['run_id'])).json()
    assert run['status'] == 'completed'
    assert [citation['id'] for citation in run['citations']] == [source['id']]
    receipt = next(call for call in run['tool_calls'] if call['name'] == 'reuse_conversation_sources')
    assert receipt['result']['items'][0]['from_message_id'] == previous_id
    assert events[-1]['text'] == run['text'] and '来源沿用本会话' in run['text']
    assert model.is_closed()


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
        assert run["prompt_version"].startswith("grounded-") and run["prompt_version"] != "grounded-v1"
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
        assert run["tool_calls"][0]["result"]["clarification_checklist"] == ""
        assert "结算反馈核对清单" not in run["text"]
        assert all(s["evidence_type"] == "user_statement" and s["path"].startswith(f"conversation/{run['session_id']}/") for s in run["citations"])
    finally:
        await sdk.close()


async def test_rule_feedback_keeps_concrete_questions_in_stream_history_and_audit(client, protocol_model):
    def handler(request):
        assert not json.loads(request.content).get("tools")
        return sse_response(answer="文字草稿：技能没生效。预期、步骤和版本待补充。尚未保存。")

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "技能没生效，帮我反馈。")
        assert run["status"] == "completed", run.get("error")
        assert all(word in run["text"] for word in ("武将", "技能名称", "卡牌名称", "触发阶段", "关键局面"))
        result = run["tool_calls"][0]["result"]
        assert result["clarification_checklist"] in run["text"]
        assert result["persisted"] is False
        deltas = [json.loads(line[6:])["text"] for event in stream.split("\n\n") if event.startswith("event: delta") for line in event.splitlines() if line.startswith("data: ")]
        assert "".join(deltas) == run["text"]
        messages = (await client.get(f"/sessions/{run['session_id']}/messages")).json()
        assert messages[-1]["content"] == run["text"]
        assert (await client.get("/feedback")).json() == []
    finally:
        await sdk.close()


async def test_rule_feedback_checklist_does_not_turn_empty_model_body_into_success(client, protocol_model):
    sdk = protocol_model(lambda _: sse_response(answer=""))
    try:
        _, run = await run_question(client, "技能没生效，帮我反馈。")
        assert run["status"] == "failed" and "未返回正文" in run["error"]
        assert not run["text"] and run["usage"]["settled"]
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


async def test_invalid_ruling_id_cannot_override_grounded_basic_rule(client, protocol_model):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id": "SC01-08"})
        if len(requests) == 2:
            return sse_response(tool="search_knowledge", arguments={"query": "主公杀死忠臣"})
        return sse_response(answer="主公杀死忠臣须立即弃置所有手牌和已装备的牌。")

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "主公误杀忠臣需要弃哪些牌？")
        assert run["status"] == "completed", run.get("error")
        assert "所有手牌和已装备的牌" in run["text"]
        assert "暂不能判断" not in stream
        assert run["citations"]
        assert all(call["name"] != "get_verified_ruling" for call in run["tool_calls"])
        tool = next(t for t in requests[0]["tools"] if t["function"]["name"] == "get_verified_ruling")
        assert tool["function"]["parameters"]["properties"]["scene_id"]["enum"] == [f"SC{i:02}" for i in range(1, 9)]
    finally:
        await sdk.close()


async def test_prompt_revision_tracks_instructions_not_player_text(client, protocol_model):
    runs = []
    for question in ("诸葛亮的势力是什么？", "曹操的技能是什么？", "iOS页面卡住，帮我整理反馈"):
        sdk = protocol_model(lambda _: sse_response(answer="仅用于协议测试的正文。"))
        try:
            _, run = await run_question(client, question)
            assert run["status"] == "completed", run.get("error")
            runs.append(run)
        finally:
            await sdk.close()
    assert runs[0]["prompt_version"] == runs[1]["prompt_version"]
    assert runs[0]["prompt_version"] != runs[2]["prompt_version"]


async def test_real_agno_tool_failure_retains_error_without_fabricated_citation(client, protocol_model):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return sse_response(tool="search_knowledge", arguments={"query": "未收录技能"})
        body = json.loads(request.content)
        assert any(m["role"] == "tool" and "error" in m["content"] for m in body["messages"])
        return sse_response(answer="资料查询工具暂时不可用，请稍后重试，当前无法确认技能效果。")

    sdk = protocol_model(handler)
    try:
        stream, run = await run_question(client, "请核对未收录技能", fault="tool_unavailable")
        assert run["status"] == "completed", run.get("error")
        assert "稍后重试" in stream and not run["citations"]
        assert run["tool_calls"][0]["status"] == "failed"
        assert run["tool_calls"][0]["result"].get("error")
        assert calls == 2 and sdk.is_closed() and run["usage"]["settled"]
    finally:
        await sdk.close()


@pytest.mark.parametrize("clarify_first", [False, True])
async def test_verified_ruling_finishes_without_second_model_request(client, app, protocol_model, clarify_first):
    calls = 0
    expected_calls = 2 if clarify_first else 1
    scene = next(s for s in app.state.catalog.rulings() if s["id"] == "SC06")

    def handler(request):
        nonlocal calls
        calls += 1
        if clarify_first and calls == 1:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id": "SC06", "conditions": {}})
        if calls == expected_calls:
            return sse_response(tool="get_verified_ruling", arguments={"scene_id": "SC06", "reference": not clarify_first, "conditions": scene["conditions"] if clarify_first else {}})
        return httpx.Response(503, json={"error": {"message": "unnecessary second request", "type": "server_error"}})

    sdk = protocol_model(handler)
    try:
        _, run = await run_question(client, "核对SC06，已明确提供全部条件：" + json.dumps(scene["conditions"], ensure_ascii=False))
        assert run["status"] == "completed", run.get("error")
        assert calls == expected_calls and "连营" in run["text"] and run["citations"]
        assert run["input_tokens"] == 12 * expected_calls and run["output_tokens"] == 4 * expected_calls
        assert not run["usage"]["estimated"] and run["usage"]["settled"]
        assert sdk.is_closed()
    finally:
        await sdk.close()
