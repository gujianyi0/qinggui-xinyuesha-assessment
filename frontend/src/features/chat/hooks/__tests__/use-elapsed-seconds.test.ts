import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useElapsedSeconds } from '../use-elapsed-seconds'

it('measures elapsed time and clears the clock after completion and unmount', () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'performance'] })
  try {
    const { result, rerender, unmount } = renderHook(
      ({ running }) => useElapsedSeconds(running),
      { initialProps: { running: true } },
    )
    act(() => vi.advanceTimersByTime(3200))
    expect(result.current).toBe(3)
    rerender({ running: false })
    expect(result.current).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
    rerender({ running: true })
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  } finally {
    vi.useRealTimers()
  }
})
