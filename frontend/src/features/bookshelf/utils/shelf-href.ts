import type { ShelfDocument } from '@/types/bookshelf'

export function shelfHref({
  href,
  current,
  records,
  evidenceLinks,
}: {
  href: string
  current: ShelfDocument
  records: ShelfDocument[]
  evidenceLinks: Record<string, string>
}) {
  if (/^(?:https?:|mailto:|#)/i.test(href)) return href
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//'))
    return undefined
  if (href.startsWith('/?page=bookshelf') || href.startsWith('/bookshelf/'))
    return href
  let target: URL
  try {
    target = new URL(href, `https://shelf.local/${current.sourcePath}`)
  } catch {
    return undefined
  }
  let path: string
  try {
    path = decodeURIComponent(target.pathname.slice(1))
  } catch {
    return undefined
  }
  const record = records.find((item) => item.sourcePath === path)
  if (record)
    return `/?page=bookshelf&shelf=${record.kind === 'learning' ? 'learning' : 'review'}&document=${record.id}`
  if (current.kind === 'learning') return undefined
  const evidence = evidenceLinks[path.replace(/\/$/, '')]
  return evidence ? `${evidence}${target.hash}` : undefined
}
