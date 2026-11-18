import { useSyncExternalStore } from 'react'

const listeners = new Set<() => void>()
function notify() {
  for (const listener of listeners) listener()
}
function subscribe(listener: () => void) {
  if (!listeners.size) {
    window.addEventListener('online', notify)
    window.addEventListener('offline', notify)
  }
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (!listeners.size) {
      window.removeEventListener('online', notify)
      window.removeEventListener('offline', notify)
    }
  }
}
export function useOnlineStatus() {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  )
}
