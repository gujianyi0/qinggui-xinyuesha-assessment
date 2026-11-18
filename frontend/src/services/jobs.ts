import type { Job } from '@/types/domain'
import { listResult, request } from './api'

export async function listJobs({
  token,
  signal,
}: {
  token: string
  signal?: AbortSignal
}) {
  return listResult(
    await request<Job[] | { items: Job[] }>('/jobs', token, { signal }),
  )
}
export function createJob({
  token,
  snapshotId,
  idempotencyKey,
}: {
  token: string
  snapshotId: string
  idempotencyKey: string
}) {
  return request<Job>('/jobs', token, {
    method: 'POST',
    body: JSON.stringify({
      snapshot_id: snapshotId,
      idempotency_key: idempotencyKey,
    }),
  })
}
export function cancelJob({ token, jobId }: { token: string; jobId: string }) {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, token, {
    method: 'POST',
  })
}
