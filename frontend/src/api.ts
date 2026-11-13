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

export interface PendingSubmission { request_id: string; session_id: string; message: string; snapshot_id: string; run_id?: string; cancel_requested?: boolean }
const pendingKey = (scope: string, session: string) => `qinggui-pending:${scope}:${session}`;
export function pendingSubmission(scope: string, session: string): PendingSubmission | null {
  try {
    const value = JSON.parse(localStorage.getItem(pendingKey(scope, session)) || 'null');
    return value?.request_id && value.session_id === session && typeof value.message === 'string' ? value : null;
  } catch { return null; }
}
export function pendingSession(scope: string): string | null {
  const prefix = `qinggui-pending:${scope}:`;
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index);
    if (key?.startsWith(prefix)) return key.slice(prefix.length);
  }
  return null;
}
export function forgetSubmission(scope: string, session: string) {
  localStorage.removeItem(pendingKey(scope, session));
  window.dispatchEvent(new Event('qinggui-pending-changed'));
}
function remember(scope: string, value: PendingSubmission) {
  localStorage.setItem(pendingKey(scope, value.session_id), JSON.stringify(value));
  window.dispatchEvent(new Event('qinggui-pending-changed'));
}
function temporary(error: unknown): boolean { return !(error instanceof ApiError) || [502, 503, 504].includes(error.status); }

export async function lookupSubmission(session: string, requestId: string, token: string, signal?: AbortSignal) {
  return request<{ run_id: string; status: string }>(`/sessions/${encodeURIComponent(session)}/requests/${encodeURIComponent(requestId)}`, token, { signal });
}

async function acceptSubmission(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, scope: string): Promise<PendingSubmission> {
  let value = pendingSubmission(scope, sessionId);
  const recovering = Boolean(value);
  if (value && (value.message !== message || value.snapshot_id !== snapshotId)) throw new ApiError('此会话有待确认请求，请先恢复原请求；不会覆盖原编号。', 409);
  value ||= { request_id: crypto.randomUUID(), session_id: sessionId, message, snapshot_id: snapshotId };
  remember(scope, value); // Must succeed before a paid request can be submitted.
  for (let attempt = 0; attempt < 3; attempt++) {
    if (recovering || attempt > 0) {
      try {
        const existing = await lookupSubmission(sessionId, value.request_id, token, signal);
        value.run_id = existing.run_id; remember(scope, value); return value;
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) {
          if (signal.aborted || !temporary(error) || attempt === 2) throw error;
          continue; // An unavailable lookup never becomes a fresh submission.
        }
      }
    }
    try {
      const path = value.cancel_requested
        ? `/sessions/${encodeURIComponent(sessionId)}/requests/${encodeURIComponent(value.request_id)}/cancel`
        : `/sessions/${encodeURIComponent(sessionId)}/submissions`;
      const result = await request<{ run_id: string }>(path, token, {
        method: 'POST', signal, body: JSON.stringify({ message, request_id: value.request_id, ...(snapshotId ? { snapshot_id: snapshotId } : {}) }),
      });
      value.run_id = result.run_id; remember(scope, value); return value;
    } catch (error) {
      if (signal.aborted || !temporary(error) || attempt === 2) throw error;
    }
  }
  throw new Error('请求回执尚未确认，请恢复同一请求编号。');
}

async function observeRun(runId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  let failures = 0;
  for (;;) {
    let run: Record<string, unknown>;
    try { run = await request<Record<string, unknown>>(`/runs/${encodeURIComponent(runId)}`, token, { signal }); failures = 0; }
    catch (error) {
      if (signal.aborted || !temporary(error) || ++failures > 3) throw error;
      onEvent({ event: 'progress', data: { message: '连接暂时中断，正在重新查询原回答' } });
      await new Promise(resolve => setTimeout(resolve, 1500)); continue;
    }
    if (run.status !== 'running') { onEvent({ event: String(run.status), data: { ...run, run_id: runId } }); return; }
    onEvent({ event: 'progress', data: { message: '正在核对资料并组织回答' } });
    await new Promise<void>((resolve, reject) => {
      const stop = () => { clearTimeout(timer); reject(new DOMException('回答已取消', 'AbortError')); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', stop); resolve(); }, 1500);
      if (signal.aborted) stop(); else signal.addEventListener('abort', stop, { once: true });
    });
  }
}

async function durableRun(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void, scope: string, useStream: boolean) {
  if (!scope) throw new Error('尚未取得工作区身份，不能提交付费请求。');
  let value: PendingSubmission | null = null;
  try {
    value = await acceptSubmission(sessionId, message, snapshotId, token, signal, scope);
    onEvent({ event: 'started', data: { run_id: value.run_id } });
    if (value.cancel_requested) await request(`/runs/${encodeURIComponent(value.run_id!)}/cancel`, token, { method: 'POST' });
    const deliver = (event: StreamEvent) => { onEvent(event); if (['completed', 'failed', 'cancelled'].includes(event.event)) forgetSubmission(scope, sessionId); };
    if (useStream) {
      let terminal = false;
      try {
        const response = await fetch(`${apiBase}/runs/${encodeURIComponent(value.run_id!)}/events`, { signal, headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' } });
        if (!response.ok || !response.body) throw new ApiError('回答流暂时不可用', response.status);
        await readEventStream(response.body, event => { deliver(event); terminal ||= ['completed', 'failed', 'cancelled'].includes(event.event); });
      } catch (error) { if (signal.aborted || !temporary(error)) throw error; }
      if (terminal) return;
    }
    await observeRun(value.run_id!, token, signal, deliver);
  } finally {
    if (signal.aborted && signal.reason !== 'detach') {
      const pending = value || pendingSubmission(scope, sessionId);
      if (pending) {
        pending.cancel_requested = true; remember(scope, pending);
        try {
          const cancelled = await request<{ status: string }>(`/sessions/${encodeURIComponent(sessionId)}/requests/${encodeURIComponent(pending.request_id)}/cancel`, token, {
            method: 'POST', body: JSON.stringify({ message: pending.message, snapshot_id: pending.snapshot_id || null, request_id: pending.request_id }),
          });
          if (cancelled.status !== 'running') forgetSubmission(scope, sessionId);
        } catch { /* Keep the original request so a later recovery can locate/cancel it. */ }
      }
    }
  }
}

export async function streamRun(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void, scope = '') {
  return durableRun(sessionId, message, snapshotId, token, signal, onEvent, scope, !publicMode);
}
export async function pollRun(sessionId: string, message: string, snapshotId: string, token: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void, scope = '') {
  return durableRun(sessionId, message, snapshotId, token, signal, onEvent, scope, false);
}

export function listResult<T>(value: T[] | { items: T[] }): T[] { return Array.isArray(value) ? value : value.items; }
export function displayError(error: unknown): string { return error instanceof Error ? error.message : '请求未完成，请稍后重试'; }
