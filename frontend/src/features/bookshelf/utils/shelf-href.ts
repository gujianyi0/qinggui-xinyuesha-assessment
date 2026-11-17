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
  if (href.startsWith('/?page=bookshelf')) return href
  if (href.startsWith('/bookshelf/review-files/')) {
    const [path, hash] = href.split('#')
    const match = Object.entries(evidenceLinks).find(([, url]) => url === path)
    return match ? evidenceHref(match[0], hash || '') : undefined
  }
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
  return evidence
    ? evidenceHref(path.replace(/\/$/, ''), target.hash.slice(1))
    : undefined
}

function evidenceHref(path: string, hash: string) {
  const query = new URLSearchParams({
    page: 'bookshelf',
    shelf: 'review',
    file: path || '.',
  })
  const line = /^L?(\d+)(?:-L?\d+)?$/.exec(hash)
  if (line) query.set('line', line[1])
  else if (hash) query.set('anchor', hash)
  return `/?${query}`
}
