import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string) {
  const subscribe = (listener: () => void) => {
    const media = window.matchMedia(query)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  )
}
