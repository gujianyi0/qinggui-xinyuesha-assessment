import { afterEach, expect, it, vi } from 'vitest';
import { pendingSubmission, pollRun } from './api';
import type { StreamEvent } from './types';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

it('leaving the page detaches observation and keeps the recoverable request without cancellation', async () => {
  const controller = new AbortController();
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (calls.length === 1) return new Response(JSON.stringify({run_id:'original'}), {status:202});
    controller.abort('detach'); throw new DOMException('detached','AbortError');
  }));
  await expect(pollRun('session1','原问题','','token',controller.signal,()=>undefined,'identity1')).rejects.toHaveProperty('name','AbortError');
  expect(calls).toHaveLength(2);
  expect(calls.some(url=>url.endsWith('/cancel'))).toBe(false);
  expect(pendingSubmission('identity1','session1')).toMatchObject({run_id:'original'});
});

it('reload retries an unacknowledged cancellation without creating a paid submission', async () => {
  localStorage.setItem('qinggui-pending:identity1:session1', JSON.stringify({
    session_id:'session1', request_id:'original-request', message:'原问题', snapshot_id:'', cancel_requested:true,
  }));
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (calls.length === 1) return new Response(JSON.stringify({detail:'not found'}), {status:404});
    return new Response(JSON.stringify(url.endsWith('/cancel') ? {run_id:'cancelled-run',status:'cancelled'} : {status:'cancelled'}));
  }));
  await pollRun('session1','原问题','','token',new AbortController().signal,()=>undefined,'identity1');
  expect(calls[1]).toBe('/api/sessions/session1/requests/original-request/cancel');
  expect(calls.some(url=>url.endsWith('/submissions'))).toBe(false);
  expect(pendingSubmission('identity1','session1')).toBeNull();
});

it('lost submission receipt is recovered without a second paid POST', async () => {
  const calls: { url: string; options?: RequestInit }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    calls.push({ url, options });
    if (calls.length === 1) throw new TypeError('response lost after server commit');
    if (url.includes('/requests/')) return new Response(JSON.stringify({ run_id: 'original', status: 'running' }));
    return new Response(JSON.stringify({ status: 'completed', text: '原回答', citations: [] }));
  }));
  await pollRun('session1', '原问题', 'snapshot1', 'token', new AbortController().signal, () => undefined, 'identity1');
  expect(calls.filter(call => call.options?.method === 'POST')).toHaveLength(1);
  expect(calls[1].url).toContain('/requests/');
  expect(pendingSubmission('identity1', 'session1')).toBeNull();
});

it('browser reload restores the saved request ID and never replaces it with a new message', async () => {
  const ids: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_: string, options?: RequestInit) => {
    if (options?.method === 'POST') ids.push(JSON.parse(String(options.body)).request_id);
    throw new TypeError('network down');
  }));
  await expect(pollRun('session1', '原问题', '', 'token', new AbortController().signal, () => undefined, 'identity1')).rejects.toThrow();
  const saved = pendingSubmission('identity1', 'session1');
  expect(saved?.request_id).toBe(ids[0]);
  expect(pendingSubmission('identity2', 'session1')).toBeNull();
  await expect(pollRun('session1', '不同问题', '', 'token', new AbortController().signal, () => undefined, 'identity1')).rejects.toThrow('原请求');
  const urls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(url);
    return new Response(JSON.stringify(url.includes('/requests/') ? { run_id:'original',status:'completed' } : { status:'completed',text:'已保存回答',citations:[] }));
  }));
  await pollRun('session1', '原问题', '', 'renewed-token', new AbortController().signal, () => undefined, 'identity1');
  expect(urls[0]).toContain(saved!.request_id);
  expect(urls.some(url => url.endsWith('/submissions'))).toBe(false);
});

it('cancellation before acknowledgement writes the original request cancellation marker', async () => {
  const controller = new AbortController();
  const calls: {url:string;options?:RequestInit}[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    calls.push({url,options});
    if (calls.length === 1) { controller.abort(); throw new DOMException('aborted','AbortError'); }
    return new Response(JSON.stringify({status:'cancelled'}));
  }));
  await expect(pollRun('session1','原问题','','token',controller.signal,()=>undefined,'identity1')).rejects.toHaveProperty('name','AbortError');
  const requestId = JSON.parse(String(calls[0].options?.body)).request_id;
  expect(calls[1].url).toBe(`/api/sessions/session1/requests/${requestId}/cancel`);
  expect(calls[1].options?.signal).toBeUndefined();
  expect(pendingSubmission('identity1','session1')).toBeNull();
});

it('transient progress failure retries the same run without sending cancellation or another paid POST', async () => {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (calls.length === 1) return new Response(JSON.stringify({ run_id: 'run1' }), { status: 202 });
    if (calls.length === 2) return new Response(JSON.stringify({ detail: '暂时不可用' }), { status: 503 });
    return new Response(JSON.stringify({ status: 'completed', text: '最终回答', citations: [] }), { status: 200 });
  }));
  const events: StreamEvent[] = [];
  await pollRun('session1', '问题', '', 'guest-token', new AbortController().signal, event => events.push(event), 'test-user');
  expect(calls).toEqual(['/api/sessions/session1/submissions', '/api/runs/run1', '/api/runs/run1']);
  expect(events.at(-1)?.event).toBe('completed');
});

it('public polling forwards the complete persisted answer and citations', async () => {
  const calls: { url: string; options?: RequestInit }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(calls.length === 1 ? { run_id: 'run1' } : {
      status: 'completed', text: '曹操拥有奸雄', citations: [{ id: 's1', path: 'source.lua' }],
    }), { status: calls.length === 1 ? 202 : 200 });
  }));
  const events: StreamEvent[] = [];
  await pollRun('session1', '曹操技能', 'snapshot1', 'guest-token', new AbortController().signal, event => events.push(event), 'test-user');
  expect(events.map(event => event.event)).toEqual(['started', 'completed']);
  expect(events[1].data.text).toBe('曹操拥有奸雄');
  expect(events[1].data.citations).toEqual([{ id: 's1', path: 'source.lua' }]);
  expect(JSON.parse(String(calls[0].options?.body))).toMatchObject({ message: '曹操技能', snapshot_id: 'snapshot1', request_id: expect.any(String) });
  expect(calls).toHaveLength(2);
});

it('aborted public polling requests cancellation without the aborted signal', async () => {
  const controller = new AbortController();
  const calls: { url: string; options?: RequestInit }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    calls.push({ url, options });
    if (calls.length === 1) return new Response(JSON.stringify({ run_id: 'run1' }), { status: 202 });
    if (calls.length === 2) { controller.abort(); throw new DOMException('aborted', 'AbortError'); }
    return new Response('{}', { status: 200 });
  }));
  await expect(pollRun('session1', '问题', '', 'guest-token', controller.signal, () => undefined, 'test-user')).rejects.toHaveProperty('name', 'AbortError');
  expect(calls[2].url).toMatch(/^\/api\/sessions\/session1\/requests\/.+\/cancel$/);
  expect(calls[2].options?.signal).toBeUndefined();
});
