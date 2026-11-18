import { useState, useSyncExternalStore } from 'react'

export function useShelfBookmarks({
  userId,
  importLegacy,
}: {
  userId: string
  importLegacy: boolean
}) {
  const key = `qinggui-bookshelf-saved:${userId}`
  const [error, setError] = useState('')
  function snapshot() {
    try {
      const stored = localStorage.getItem(key)
      if (stored !== null) return stored
      if (importLegacy) {
        const old = JSON.parse(
          localStorage.getItem('biteagle-knowledge-v1') || '{}',
        )
        return JSON.stringify(
          Object.entries(old)
            .filter(
              ([id, value]) =>
                /^[1-7]-\d{2}$/.test(id) &&
                value &&
                typeof value === 'object' &&
                'saved' in value &&
                value.saved === true,
            )
            .map(([id]) => id),
        )
      }
      return '[]'
    } catch {
      return 'unavailable'
    }
  }
  const raw = useSyncExternalStore(subscribe, snapshot, () => '[]')
  let saved: string[] = []
  try {
    const value: unknown = JSON.parse(raw)
    if (Array.isArray(value))
      saved = value.filter(
        (id): id is string =>
          typeof id === 'string' && /^[1-7]-\d{2}$/.test(id),
      )
  } catch {
    /* A storage error is displayed without replacing the old record. */
  }
  function toggle(id: string) {
    if (!/^[1-7]-\d{2}$/.test(id)) return
    const next = saved.includes(id)
      ? saved.filter((value) => value !== id)
      : [...saved, id]
    try {
      localStorage.setItem(key, JSON.stringify(next))
      window.dispatchEvent(new Event('qinggui-shelf-bookmarks'))
      setError('')
    } catch {
      setError('收藏未保存，浏览器存储暂时不可用')
    }
  }
  return {
    saved,
    toggle,
    error: raw === 'unavailable' ? '收藏暂时无法读取，原记录保留' : error,
  }
}

function subscribe(listener: () => void) {
  window.addEventListener('storage', listener)
  window.addEventListener('qinggui-shelf-bookmarks', listener)
  return () => {
    window.removeEventListener('storage', listener)
    window.removeEventListener('qinggui-shelf-bookmarks', listener)
  }
}
