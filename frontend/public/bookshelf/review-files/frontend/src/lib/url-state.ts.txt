import { useSyncExternalStore } from 'react'

const listeners = new Set<() => void>()
function notify() {
  for (const listener of listeners) listener()
}
function subscribe(listener: () => void) {
  if (!listeners.size) window.addEventListener('popstate', notify)
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (!listeners.size) window.removeEventListener('popstate', notify)
  }
}
export function useUrlSearch() {
  return useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => '',
  )
}
export function updateUrl(
  values: Record<string, string | null>,
  { replace = false }: { replace?: boolean } = {},
) {
  const url = new URL(window.location.href)
  for (const [key, value] of Object.entries(values)) {
    if (value) url.searchParams.set(key, value)
    else url.searchParams.delete(key)
  }
  if (url.href === window.location.href) return
  window.history[replace ? 'replaceState' : 'pushState']({}, '', url)
  notify()
}
