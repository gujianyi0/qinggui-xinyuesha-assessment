import type { StreamEvent } from './types';

export const publicMode = import.meta.env.VITE_PUBLIC_MODE === '1';
export const apiBase = import.meta.env.VITE_API_BASE || (publicMode && ['localhost', '127.0.0.1'].includes(location.hostname) ? 'https://qinggui-assessment.c2115259095.workers.dev/api' : '/api');

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}

function errorText(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === 'string' ? item.msg : String(item)).join('；');
  return '请求未完成，请稍后重试';
}

export async function request<T>(path: string, token?: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  if (!response.ok) {
    if (response.status === 401 && token) window.dispatchEvent(new Event('qinggui-auth-expired'));
    let message = `请求失败（${response.status}）`;
    try { message = errorText((await response.json()).detail); } catch { /* HTTP status remains actionable. */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Frames may split inside UTF-8 text, CRLF, or a JSON value. Only complete frames are emitted. */
export async function readEventStream(stream: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  function consume(final = false) {
    let boundary: RegExpExecArray | null;
    while ((boundary = /\r?\n\r?\n/.exec(pending))) {
      const frame = pending.slice(0, boundary.index);
      pending = pending.slice(boundary.index + boundary[0].length);
      emit(frame);
    }
    if (final && pending.trim()) { emit(pending); pending = ''; }
  }
  function emit(frame: string) {
    let event = 'message';
    const lines: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      if (line.startsWith('data:')) lines.push(line.slice(5).trimStart());
    }
    if (!lines.length) return;
    const value: unknown = JSON.parse(lines.join('\n'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('服务返回了无法识别的流式事件');
    onEvent({ event, data: value as Record<string, unknown> });
  }
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) { pending += decoder.decode(); consume(true); break; }
      pending += decoder.decode(value, { stream: true });
      consume();
    }
  } finally { reader.releaseLock(); }
}

export async function streamRun(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  if (publicMode) return pollRun(sessionId, message, snapshotId, token, signal, onEvent);
  const response = await fetch(`${apiBase}/sessions/${encodeURIComponent(sessionId)}/runs`, {
    method: 'POST', signal,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, ...(snapshotId ? { snapshot_id: snapshotId } : {}) }),
  });
  if (!response.ok) {
    let message = `问答请求失败（${response.status}）`;
    try { message = errorText((await response.json()).detail); } catch { /* Preserve status. */ }
    throw new ApiError(message, response.status);
  }
  if (!response.body) throw new Error('浏览器未收到回答流，请查询会话结果');
  await readEventStream(response.body, onEvent);
}

export async function pollRun(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  const { run_id } = await request<{ run_id: string }>(`/sessions/${encodeURIComponent(sessionId)}/runs`, token, {
    method: 'POST', signal, body: JSON.stringify({ message, request_id: crypto.randomUUID(), ...(snapshotId ? { snapshot_id: snapshotId } : {}) }),
  });
  onEvent({ event: 'started', data: { run_id } });
  let terminal = false;
  let failures = 0;
  try {
    for (;;) {
      let run: Record<string, unknown>;
      try {
        run = await request<Record<string, unknown>>(`/runs/${encodeURIComponent(run_id)}`, token, { signal });
        failures = 0;
      } catch (error) {
        if (signal.aborted || (error instanceof ApiError && ![502, 503, 504].includes(error.status)) || ++failures > 3) throw error;
        onEvent({ event: 'progress', data: { message: '连接暂时中断，正在重新查询回答进度' } });
        await new Promise(resolve => setTimeout(resolve, 1500));
        continue;
      }
      if (run.status !== 'running') {
        terminal = true;
        onEvent({ event: String(run.status), data: { ...run, run_id } });
        return;
      }
      onEvent({ event: 'progress', data: { message: '正在核对资料并组织回答' } });
      await new Promise<void>((resolve, reject) => {
        const stop = () => { clearTimeout(timer); reject(new DOMException('回答已取消', 'AbortError')); };
        const timer = setTimeout(() => { signal.removeEventListener('abort', stop); resolve(); }, 1500);
        if (signal.aborted) stop(); else signal.addEventListener('abort', stop, { once: true });
      });
    }
  } finally {
    if (!terminal && signal.aborted) void request(`/runs/${encodeURIComponent(run_id)}/cancel`, token, { method: 'POST' }).catch(() => undefined);
  }
}

export function listResult<T>(value: T[] | { items: T[] }): T[] { return Array.isArray(value) ? value : value.items; }
export function displayError(error: unknown): string { return error instanceof Error ? error.message : '请求未完成，请稍后重试'; }
