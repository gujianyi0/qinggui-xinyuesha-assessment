import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useOnlineStatus } from '../use-online-status'

afterEach(() => vi.restoreAllMocks())
it('shares connectivity changes across screens and recovers when online', () => {
  const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  const first = renderHook(() => useOnlineStatus()),
    second = renderHook(() => useOnlineStatus())
  act(() => {
    online.mockReturnValue(false)
    window.dispatchEvent(new Event('offline'))
  })
  expect(first.result.current).toBe(false)
  expect(second.result.current).toBe(false)
  first.unmount()
  act(() => {
    online.mockReturnValue(true)
    window.dispatchEvent(new Event('online'))
  })
  expect(second.result.current).toBe(true)
  second.unmount()
})
