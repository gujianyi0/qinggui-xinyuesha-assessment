import { useEffect, useState } from 'react'

export function useElapsedSeconds(running: boolean) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!running) {
      setSeconds(0)
      return
    }
    const started = performance.now()
    const timer = window.setInterval(
      () => setSeconds(Math.floor((performance.now() - started) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [running])
  return seconds
}
