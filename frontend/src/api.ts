import type { StreamEvent } from './types';

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
  const response = await fetch(`/api${path}`, { ...options, headers });
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
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/runs`, {
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

export function listResult<T>(value: T[] | { items: T[] }): T[] { return Array.isArray(value) ? value : value.items; }
export function displayError(error: unknown): string { return error instanceof Error ? error.message : '请求未完成，请稍后重试'; }
