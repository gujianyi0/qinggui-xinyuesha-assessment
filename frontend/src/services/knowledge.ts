import type { Entity, Health, Ruling, Snapshot } from '@/types/domain'
import { listResult, request } from './api'

interface KnowledgeRequest {
  token: string
  signal?: AbortSignal
}
export async function listSnapshots({ token, signal }: KnowledgeRequest) {
  return listResult(
    await request<Snapshot[] | { items: Snapshot[] }>(
      '/catalog/snapshots',
      token,
      { signal },
    ),
  )
}
export function getHealth({ token, signal }: KnowledgeRequest) {
  return request<Health>('/health', token, { signal })
}
export async function listEntities({
  token,
  signal,
  snapshotId,
  kind,
  search,
}: KnowledgeRequest & { snapshotId: string; kind: string; search: string }) {
  const query = new URLSearchParams({
    snapshot_id: snapshotId,
    kind,
    query: search,
  })
  return listResult(
    await request<Entity[] | { items: Entity[] }>(
      `/catalog/entities?${query}`,
      token,
      { signal },
    ),
  )
}
export async function listRulings({
  token,
  signal,
  snapshotId,
}: KnowledgeRequest & { snapshotId: string }) {
  return listResult(
    await request<Ruling[] | { items: Ruling[] }>(
      `/catalog/rulings?snapshot_id=${encodeURIComponent(snapshotId)}`,
      token,
      { signal },
    ),
  )
}
