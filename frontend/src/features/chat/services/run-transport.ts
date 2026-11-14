import { waitForObservation } from '@/lib/browser-lifecycle'
import { apiBase, isPublicMode } from '@/lib/runtime-config'
import { readEventStream } from '@/lib/sse'
import { ApiError, request } from '@/services/api'
import type { StreamEvent } from '@/types/domain'

export interface RunObservationOptions {
  sessionId: string
  message: string
  snapshotId: string
  token: string
  signal: AbortSignal
  onEvent: (event: StreamEvent) => void
  scope?: string
}
export interface PendingSubmission {
  request_id: string
  session_id: string
  message: string
  snapshot_id: string
  run_id?: string
  cancel_requested?: boolean
}
const pendingKey = (scope: string, session: string) =>
  `qinggui-pending:${scope}:${session}`
export function pendingSubmission(
  scope: string,
  session: string,
): PendingSubmission | null {
  try {
    const value = JSON.parse(
      localStorage.getItem(pendingKey(scope, session)) || 'null',
    )
    return value?.request_id &&
      value.session_id === session &&
      typeof value.message === 'string'
      ? value
      : null
  } catch {
    return null
  }
}
export function pendingSession(scope: string): string | null {
  const prefix = `qinggui-pending:${scope}:`
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index)
    if (key?.startsWith(prefix)) return key.slice(prefix.length)
  }
  return null
}
export function forgetSubmission(scope: string, session: string) {
  localStorage.removeItem(pendingKey(scope, session))
  window.dispatchEvent(new Event('qinggui-pending-changed'))
}
function remember(scope: string, value: PendingSubmission) {
  localStorage.setItem(
    pendingKey(scope, value.session_id),
    JSON.stringify(value),
  )
  window.dispatchEvent(new Event('qinggui-pending-changed'))
}
function temporary(error: unknown): boolean {
  return !(error instanceof ApiError) || [502, 503, 504].includes(error.status)
}

export async function lookupSubmission({
  sessionId: session,
  requestId,
  token,
  signal,
}: {
  sessionId: string
  requestId: string
  token: string
  signal?: AbortSignal
}) {
  return request<{ run_id: string; status: string }>(
    `/sessions/${encodeURIComponent(session)}/requests/${encodeURIComponent(requestId)}`,
    token,
    { signal },
  )
}

async function acceptSubmission({
  sessionId,
  message,
  snapshotId,
  token,
  signal,
  scope,
}: {
  sessionId: string
  message: string
  snapshotId: string
  token: string
  signal: AbortSignal
  scope: string
}): Promise<PendingSubmission> {
  let value = pendingSubmission(scope, sessionId)
  const recovering = Boolean(value)
  if (value && (value.message !== message || value.snapshot_id !== snapshotId))
    throw new ApiError(
      '此会话有待确认请求，请先恢复原请求；不会覆盖原编号。',
      409,
    )
  value ||= {
    request_id: crypto.randomUUID(),
    session_id: sessionId,
    message,
    snapshot_id: snapshotId,
  }
  remember(scope, value) // Must succeed before a paid request can be submitted.
  for (let attempt = 0; attempt < 3; attempt++) {
    if (recovering || attempt > 0) {
      try {
        const existing = await lookupSubmission({
          sessionId: sessionId,
          requestId: value.request_id,
          token: token,
          signal: signal,
        })
        value.run_id = existing.run_id
        remember(scope, value)
        return value
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) {
          if (signal.aborted || !temporary(error) || attempt === 2) throw error
          continue // An unavailable lookup never becomes a fresh submission.
        }
      }
    }
    try {
      const path = value.cancel_requested
        ? `/sessions/${encodeURIComponent(sessionId)}/requests/${encodeURIComponent(value.request_id)}/cancel`
        : `/sessions/${encodeURIComponent(sessionId)}/submissions`
      const result = await request<{ run_id: string }>(path, token, {
        method: 'POST',
        signal,
        body: JSON.stringify({
          message,
          request_id: value.request_id,
          ...(snapshotId ? { snapshot_id: snapshotId } : {}),
        }),
      })
      value.run_id = result.run_id
      remember(scope, value)
      return value
    } catch (error) {
      if (signal.aborted || !temporary(error) || attempt === 2) throw error
    }
  }
  throw new Error('请求回执尚未确认，请恢复同一请求编号。')
}

async function observeRun({
  runId,
  token,
  signal,
  onEvent,
}: {
  runId: string
  token: string
  signal: AbortSignal
  onEvent: (event: StreamEvent) => void
}) {
  let failures = 0
  for (;;) {
    await waitForObservation(signal)
    let run: Record<string, unknown>
    try {
      run = await request<Record<string, unknown>>(
        `/runs/${encodeURIComponent(runId)}`,
        token,
        { signal },
      )
      failures = 0
    } catch (error) {
      if (signal.aborted || !temporary(error) || ++failures > 3) throw error
      onEvent({
        event: 'progress',
        data: { message: '连接暂时中断，正在重新查询原回答' },
      })
      await new Promise((resolve) => setTimeout(resolve, 1500))
      continue
    }
    if (run.status !== 'running') {
      onEvent({ event: String(run.status), data: { ...run, run_id: runId } })
      return
    }
    onEvent({ event: 'progress', data: { message: '正在核对资料并组织回答' } })
    await new Promise<void>((resolve, reject) => {
      const stop = () => {
        clearTimeout(timer)
        reject(new DOMException('回答已取消', 'AbortError'))
      }
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', stop)
        resolve()
      }, 1500)
      if (signal.aborted) stop()
      else signal.addEventListener('abort', stop, { once: true })
    })
  }
}

async function durableRun({
  sessionId,
  message,
  snapshotId,
  token,
  signal,
  onEvent,
  scope = '',
  useStream,
}: RunObservationOptions & { useStream: boolean }) {
  if (!scope) throw new Error('尚未取得工作区身份，不能提交付费请求。')
  let value: PendingSubmission | null = null
  try {
    value = await acceptSubmission({
      sessionId: sessionId,
      message: message,
      snapshotId: snapshotId,
      token: token,
      signal: signal,
      scope: scope,
    })
    const runId = value.run_id
    if (!runId) throw new Error('提交回执缺少运行编号，请恢复原请求核对。')
    onEvent({ event: 'started', data: { run_id: runId } })
    if (value.cancel_requested)
      await request(`/runs/${encodeURIComponent(runId)}/cancel`, token, {
        method: 'POST',
      })
    const deliver = (event: StreamEvent) => {
      onEvent(event)
      if (['completed', 'failed', 'cancelled'].includes(event.event))
        forgetSubmission(scope, sessionId)
    }
    if (useStream) {
      let terminal = false
      try {
        const response = await fetch(
          `${apiBase}/runs/${encodeURIComponent(runId)}/events`,
          {
            signal,
            headers: {
              Authorization: `Bearer ${token}`,
              Accept: 'text/event-stream',
            },
          },
        )
        if (!response.ok || !response.body)
          throw new ApiError('回答流暂时不可用', response.status)
        await readEventStream(response.body, (event) => {
          deliver(event)
          terminal ||= ['completed', 'failed', 'cancelled'].includes(
            event.event,
          )
        })
      } catch (error) {
        if (signal.aborted || !temporary(error)) throw error
      }
      if (terminal) return
    }
    await observeRun({
      runId: runId,
      token: token,
      signal: signal,
      onEvent: deliver,
    })
  } finally {
    if (signal.aborted && signal.reason !== 'detach') {
      const pending = value || pendingSubmission(scope, sessionId)
      if (pending) {
        pending.cancel_requested = true
        remember(scope, pending)
        try {
          const cancelled = await request<{ status: string }>(
            `/sessions/${encodeURIComponent(sessionId)}/requests/${encodeURIComponent(pending.request_id)}/cancel`,
            token,
            {
              method: 'POST',
              body: JSON.stringify({
                message: pending.message,
                snapshot_id: pending.snapshot_id || null,
                request_id: pending.request_id,
              }),
            },
          )
          if (cancelled.status !== 'running') forgetSubmission(scope, sessionId)
        } catch {
          /* Keep the original request so a later recovery can locate/cancel it. */
        }
      }
    }
  }
}

export async function streamRun(options: RunObservationOptions) {
  return durableRun({ ...options, useStream: !isPublicMode })
}
export async function pollRun(options: RunObservationOptions) {
  return durableRun({ ...options, useStream: false })
}
