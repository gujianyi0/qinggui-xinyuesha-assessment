import type { ShelfCatalog } from '@/types/bookshelf'

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
