import type { ShelfCatalog, ShelfProgress } from '@/types/bookshelf'
import { request } from './api'

async function shelfResource(path: string, signal?: AbortSignal) {
  const response = await fetch(`/bookshelf/${path}`, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
  })
  if (!response.ok)
    throw new Error(`书架资料暂时无法读取（${response.status}）`)
  return response
}
export async function getShelfCatalog(
  signal?: AbortSignal,
): Promise<ShelfCatalog> {
  return (await shelfResource('data.json', signal)).json()
}
export async function getShelfDocument(id: string, signal?: AbortSignal) {
  if (!/^[1-8]-\d{2}$/.test(id)) throw new Error('文档编号无效')
  return (await shelfResource(`originals/${id}.md`, signal)).text()
}
export function getShelfProgress(token: string, signal?: AbortSignal) {
  return request<ShelfProgress>('/bookshelf/progress', token, { signal })
}
export function setShelfMastery({
  token,
  id,
  learned,
  revision,
}: {
  token: string
  id: string
  learned: boolean
  revision: number
}) {
  return request<ShelfProgress>('/bookshelf/progress', token, {
    method: 'PATCH',
    body: JSON.stringify({ id, learned, revision }),
  })
}
export async function getShelfEvidence(url: string, signal?: AbortSignal) {
  if (
    !url.startsWith('/bookshelf/review-files/') ||
    url.split('/').includes('..')
  )
    throw new Error('资料地址无效')
  return (await shelfResource(url.slice('/bookshelf/'.length), signal)).text()
}
