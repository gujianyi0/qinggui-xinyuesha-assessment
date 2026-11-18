import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useMediaQuery } from '../use-media-query'

afterEach(() => vi.unstubAllGlobals())
it('updates the responsive mode and releases its change listener on unmount', () => {
  const events = new EventTarget()
  const media = {
    matches: false,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
  }
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  )
  const { result, unmount } = renderHook(() =>
    useMediaQuery('(max-width:650px)'),
  )
  expect(result.current).toBe(false)
  act(() => {
    media.matches = true
    events.dispatchEvent(new Event('change'))
  })
  expect(result.current).toBe(true)
  unmount()
  act(() => {
    media.matches = false
    events.dispatchEvent(new Event('change'))
  })
  expect(result.current).toBe(true)
})
