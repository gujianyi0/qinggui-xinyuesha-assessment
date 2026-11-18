import { afterEach, expect, it, vi } from 'vitest'
import { waitForObservation } from '../browser-lifecycle'

afterEach(() => vi.restoreAllMocks())
it('waits while hidden and resumes only after the page becomes visible', async () => {
  const visibility = vi
    .spyOn(document, 'visibilityState', 'get')
    .mockReturnValue('hidden')
  let isSettled = false
  const controller = new AbortController()
  const result = waitForObservation(controller.signal).then(() => {
    isSettled = true
  })
  await Promise.resolve()
  expect(isSettled).toBe(false)
  visibility.mockReturnValue('visible')
  document.dispatchEvent(new Event('visibilitychange'))
  await result
  expect(isSettled).toBe(true)
})
it('detaches a hidden observer without restarting server work', async () => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const controller = new AbortController()
  const result = waitForObservation(controller.signal)
  controller.abort('detach')
  await expect(result).rejects.toMatchObject({ name: 'AbortError' })
})
