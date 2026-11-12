import httpx
import pytest

from scripts.public_service import handle_request


@pytest.mark.parametrize('path', ['https://example.com/api/health', '//example.com/api/health', '/internal/public/identity', '/api/health#fragment'])
async def test_owner_relay_cannot_select_an_arbitrary_origin(path):
    def unexpected(_):
        raise AssertionError('No upstream request expected')
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await handle_request({'id':'request','method':'GET','path':path}, client, {'edge_token':'test'})
    assert result['status'] == 400


async def test_owner_relay_targets_loopback_and_supplies_local_gateway_identity():
    def upstream(request):
        assert str(request.url) == 'http://127.0.0.1:18083/api/sessions'
        assert request.headers['X-Public-Edge'] == 'local-edge-key'
        assert request.headers['Authorization'] == 'Bearer guest'
        assert request.content == '{"title":"测试"}'.encode()
        return httpx.Response(201, json={'id':'session'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        result = await handle_request({'id':'request','method':'POST','path':'/api/sessions','authorization':'Bearer guest','body':'{"title":"测试"}'}, client, {'edge_token':'local-edge-key'})
    assert result['status'] == 201 and result['id'] == 'request'


async def test_owner_relay_keeps_connection_errors_actionable_and_does_not_replay_posts():
    calls = 0
    def upstream(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError('test unavailable', request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        result = await handle_request({'id':'request','method':'POST','path':'/api/sessions','body':'{}'}, client, {'edge_token':'test'})
    assert result['status'] == 503 and calls == 1


async def test_owner_relay_rejects_oversized_body_before_forwarding():
    def unexpected(_):
        raise AssertionError('No upstream request expected')
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await handle_request({'id':'request','method':'POST','path':'/api/sessions','body':'字'*16001}, client, {'edge_token':'test'})
    assert result['status'] == 413
