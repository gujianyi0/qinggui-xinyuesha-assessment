import type { Message, Session } from '@/types/domain'
import type { SharedFeedback, SharedPage } from '@/types/shared-records'
import { request } from './api'

interface SharedRequest {
  token: string
  offset: number
  signal?: AbortSignal
}
export function getSharedSessions({ token, offset, signal }: SharedRequest) {
  return request<SharedPage<Session>>(
    `/shared/sessions?offset=${offset}`,
    token,
    { signal },
  )
}
export function getSharedMessages({
  token,
  offset,
  signal,
  sessionId,
}: SharedRequest & { sessionId: string }) {
  return request<SharedPage<Message>>(
    `/shared/sessions/${encodeURIComponent(sessionId)}/messages?offset=${offset}`,
    token,
    { signal },
  )
}
export function getSharedFeedback({
  token,
  offset,
  signal,
  kind,
}: SharedRequest & { kind: 'drafts' | 'submitted' }) {
  return request<SharedPage<SharedFeedback>>(
    `/shared/feedback?kind=${kind}&offset=${offset}`,
    token,
    { signal },
  )
}
