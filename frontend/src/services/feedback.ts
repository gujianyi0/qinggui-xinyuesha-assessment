import type { Draft, DraftInput, Feedback } from '@/types/domain'
import { listResult, request } from './api'

interface FeedbackRequest {
  token: string
  signal?: AbortSignal
}
export async function listDrafts({ token, signal }: FeedbackRequest) {
  return listResult(
    await request<Draft[] | { items: Draft[] }>('/feedback-drafts', token, {
      signal,
    }),
  )
}
export async function listFeedback({ token, signal }: FeedbackRequest) {
  return listResult(
    await request<Feedback[] | { items: Feedback[] }>('/feedback', token, {
      signal,
    }),
  )
}
export function saveDraft({
  token,
  draft,
  form,
}: {
  token: string
  draft: Draft | null
  form: DraftInput
}) {
  const { session_id: sessionId, ...editable } = form
  return request<Draft>(
    draft
      ? `/feedback-drafts/${encodeURIComponent(draft.id)}`
      : '/feedback-drafts',
    token,
    {
      method: draft ? 'PATCH' : 'POST',
      body: JSON.stringify(
        draft
          ? { ...editable, revision: draft.revision }
          : { ...editable, ...(sessionId ? { session_id: sessionId } : {}) },
      ),
    },
  )
}
export function confirmDraft({
  token,
  draftId,
  revision,
}: {
  token: string
  draftId: string
  revision: number
}) {
  return request<Feedback>(
    `/feedback-drafts/${encodeURIComponent(draftId)}/confirm`,
    token,
    { method: 'POST', body: JSON.stringify({ revision }) },
  )
}
