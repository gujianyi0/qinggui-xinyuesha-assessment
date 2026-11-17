/** Observers pause, while the accepted server run remains recoverable. */
export function waitForObservation(signal: AbortSignal): Promise<void> {
  if (signal.aborted)
    return Promise.reject(new DOMException('观察已停止', 'AbortError'))
  if (document.visibilityState !== 'hidden' && navigator.onLine)
    return Promise.resolve()
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      document.removeEventListener('visibilitychange', check)
      window.removeEventListener('online', check)
      signal.removeEventListener('abort', stop)
    }
    const check = () => {
      if (document.visibilityState !== 'hidden' && navigator.onLine) {
        cleanup()
        resolve()
      }
    }
    const stop = () => {
      cleanup()
      reject(new DOMException('观察已停止', 'AbortError'))
    }
    document.addEventListener('visibilitychange', check)
    window.addEventListener('online', check)
    signal.addEventListener('abort', stop, { once: true })
    if (signal.aborted) stop()
    else check()
  })
}
