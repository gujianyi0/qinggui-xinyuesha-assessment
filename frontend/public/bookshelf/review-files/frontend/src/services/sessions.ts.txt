import type { Message, Session } from '@/types/domain'
import { listResult, request } from './api'

interface SessionRequest {
  token: string
  signal?: AbortSignal
}
export async function listSessions({ token, signal }: SessionRequest) {
  return listResult(
    await request<Session[] | { items: Session[] }>('/sessions', token, {
      signal,
    }),
  )
}
export function createSession({
  token,
  title,
}: SessionRequest & { title: string }) {
  return request<Session>('/sessions', token, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}
export async function listSessionMessages({
  token,
  sessionId,
  signal,
}: SessionRequest & { sessionId: string }) {
  return listResult(
    await request<Message[] | { items: Message[] }>(
      `/sessions/${encodeURIComponent(sessionId)}/messages`,
      token,
      { signal },
    ),
  )
}
export function cancelRun({
  token,
  runId,
}: SessionRequest & { runId: string }) {
  return request(`/runs/${encodeURIComponent(runId)}/cancel`, token, {
    method: 'POST',
  })
}
