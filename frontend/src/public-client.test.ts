import { afterEach, expect, it, vi } from 'vitest';
import { pollRun } from './api';
import type { StreamEvent } from './types';

afterEach(() => vi.unstubAllGlobals());

it('transient progress failure retries the same run without sending cancellation or another paid POST', async () => {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (calls.length === 1) return new Response(JSON.stringify({ run_id: 'run1' }), { status: 202 });
    if (calls.length === 2) return new Response(JSON.stringify({ detail: '暂时不可用' }), { status: 503 });
    return new Response(JSON.stringify({ status: 'completed', text: '最终回答', citations: [] }), { status: 200 });
  }));
  const events: StreamEvent[] = [];
  await pollRun('session1', '问题', '', 'guest-token', new AbortController().signal, event => events.push(event));
  expect(calls).toEqual(['/api/sessions/session1/runs', '/api/runs/run1', '/api/runs/run1']);
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
  await pollRun('session1', '曹操技能', 'snapshot1', 'guest-token', new AbortController().signal, event => events.push(event));
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
  await expect(pollRun('session1', '问题', '', 'guest-token', controller.signal, () => undefined)).rejects.toHaveProperty('name', 'AbortError');
  expect(calls[2].url).toBe('/api/runs/run1/cancel');
  expect(calls[2].options?.signal).toBeUndefined();
});
