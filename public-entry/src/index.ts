import { DurableObject } from 'cloudflare:workers';
import { isLocalClientOrigin } from './policy.mjs';

async function sameSecret(received: string, expected: string): Promise<boolean> {
  if (!expected) return false;
  const [a, b] = await Promise.all([received, expected].map(value => crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))));
  const left = new Uint8Array(a), right = new Uint8Array(b);
  let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left[i] ^ right[i];
  return difference === 0;
}
async function boundedBody(request: Request, limit: number): Promise<Uint8Array> {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const parts: Uint8Array[] = [];
  let length = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    length += value.length;
    if (length > limit) { await reader.cancel(); throw new Error('body_limit'); }
    parts.push(value);
  }
  const body = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) { body.set(part, offset); offset += part.length; }
  return body;
}

// Each object coordinates one owner computer. Business state remains in the
// owner's database. Short HTTPS pulls avoid a long-lived upgraded connection.
type RelayMessage = { id: string; method: string; path: string; authorization: string; body: string };
type PullResult = { reconnect: boolean; messages: RelayMessage[] };
export class OwnerRelay extends DurableObject<Env> {
  private pending = new Map<string, (response: Response) => void>();
  private queued: RelayMessage[] = [];
  private receiver: ((batch: PullResult) => void) | null = null;
  private lastPoll = 0;

  status(): { connected: boolean; pending: number } {
    return { connected: Date.now() - this.lastPoll < 30000, pending: this.pending.size };
  }
  disconnect(): void {
    this.lastPoll = 0;
    this.receiver?.({ reconnect: true, messages: [] });
    this.receiver = null;
    this.queued = [];
    for (const complete of [...this.pending.values()]) complete(Response.json({ detail: '本机连接中断，请稍后重试' }, { status: 503 }));
  }
  async pull(): Promise<PullResult> {
    this.lastPoll = Date.now();
    if (this.queued.length) return { reconnect: false, messages: this.queued.splice(0, 16) };
    // There is one guarded owner process. Replace a stale pull after a network
    // failure rather than leaving its promise or timer behind.
    this.receiver?.({ reconnect: false, messages: [] });
    return new Promise<PullResult>(resolve => {
      const timer = setTimeout(() => { this.receiver = null; resolve({ reconnect: false, messages: [] }); }, 8000);
      this.receiver = result => { clearTimeout(timer); this.receiver = null; resolve(result); };
    });
  }
  reply(value: { id: string; status: number; body: string }): void {
    if (typeof value.id !== 'string' || !Number.isInteger(value.status) || value.status < 200 || value.status > 599 || typeof value.body !== 'string') throw new Error('invalid_response');
    this.pending.get(value.id)?.(new Response(value.body, { status: value.status, headers: { 'Content-Type': 'application/json' } }));
  }
  async forward(message: Omit<RelayMessage, 'id'>): Promise<Response> {
    if (!this.status().connected) return Response.json({ detail: '提供者电脑暂时离线，请稍后再试' }, { status: 503 });
    if (this.pending.size >= 32) return Response.json({ detail: '服务正在处理其他请求，请稍后重试' }, { status: 503 });
    const id = crypto.randomUUID();
    return new Promise<Response>(resolve => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.queued = this.queued.filter(item => item.id !== id);
        resolve(Response.json({ detail: '本机入口响应超时，请查看会话记录后重试' }, { status: 504 }));
      }, 45000);
      this.pending.set(id, response => { clearTimeout(timer); this.pending.delete(id); resolve(response); });
      this.queued.push({ ...message, id });
      if (this.receiver) this.receiver({ reconnect: false, messages: this.queued.splice(0, 16) });
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const relay = env.RELAYS.getByName('owner-pc');
    if (['/__poll', '/__reply', '/__status', '/__disconnect'].includes(url.pathname)) {
      if (!await sameSecret(request.headers.get('Authorization') ?? '', 'Bearer ' + env.CONTROL_TOKEN)) return Response.json({ detail: '无权操作' }, { status: 401 });
      if (url.pathname === '/__poll' && request.method === 'GET') return Response.json(await relay.pull(), { headers: { 'Cache-Control': 'no-store' } });
      if (url.pathname === '/__reply' && request.method === 'POST') {
        try {
          const value = JSON.parse(new TextDecoder().decode(await boundedBody(request, 4000000))) as { id: string; status: number; body: string };
          await relay.reply(value);
          return Response.json({ status: 'accepted' });
        } catch { return Response.json({ detail: '无效响应' }, { status: 400 }); }
      }
      if (url.pathname === '/__status' && request.method === 'GET') return Response.json(await relay.status(), { headers: { 'Cache-Control': 'no-store' } });
      if (url.pathname === '/__disconnect' && request.method === 'POST') { await relay.disconnect(); return Response.json({ status: 'disconnected' }); }
      return new Response(null, { status: 405 });
    }
    if (!url.pathname.startsWith('/api/')) {
      const asset = await env.ASSETS.fetch(request);
      const headers = new Headers(asset.headers);
      headers.set('X-Content-Type-Options', 'nosniff');
      headers.set('Referrer-Policy', 'same-origin');
      headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'");
      return new Response(asset.body, { status: asset.status, headers });
    }
    const origin = request.headers.get('Origin');
    if (origin && origin !== url.origin && !isLocalClientOrigin(origin)) return Response.json({ detail: '客户端来源不允许' }, { status: 403 });
    const headers = new Headers({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Vary': 'Origin' });
    if (origin) headers.set('Access-Control-Allow-Origin', origin);
    if (request.method === 'OPTIONS') {
      headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH');
      headers.set('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept');
      return new Response(null, { status: 204, headers });
    }
    if (!['GET', 'POST', 'PATCH'].includes(request.method)) return new Response(null, { status: 405, headers });
    try {
      const body = request.method === 'GET' ? '' : new TextDecoder().decode(await boundedBody(request, 48000));
      const upstream = await relay.forward({ method: request.method, path: url.pathname + url.search, authorization: request.headers.get('Authorization') ?? '', body });
      return new Response(upstream.body, { status: upstream.status, headers });
    } catch (error) {
      return Response.json({ detail: error instanceof Error && error.message === 'body_limit' ? '提交内容过长' : '本机入口暂时不可用，请稍后再试' }, { status: error instanceof Error && error.message === 'body_limit' ? 413 : 503, headers });
    }
  },
} satisfies ExportedHandler<Env>;
