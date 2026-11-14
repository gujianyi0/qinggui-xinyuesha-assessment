import { afterEach, expect, it, vi } from 'vitest'
import { request } from '../api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
it('bounds an unavailable HTTP request and does not retry a write', async () => {
  vi.useFakeTimers()
  const fetcher = vi.fn(
    (_url: string, options?: RequestInit) =>
      new Promise<Response>((_resolve, reject) =>
        options?.signal?.addEventListener('abort', () =>
          reject(options.signal?.reason),
        ),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  const result = request('/jobs', 'token', { method: 'POST', body: '{}' })
  const assertion = expect(result).rejects.toThrow('超过15秒')
  await vi.advanceTimersByTimeAsync(15001)
  await assertion
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('retains caller cancellation without mistaking it for a timeout', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      (_url: string, options?: RequestInit) =>
        new Promise<Response>((_resolve, reject) =>
          options?.signal?.addEventListener('abort', () =>
            reject(options.signal?.reason),
          ),
        ),
    ),
  )
  const controller = new AbortController()
  const result = request('/sessions', 'token', { signal: controller.signal })
  controller.abort(new DOMException('离开页面', 'AbortError'))
  await expect(result).rejects.toMatchObject({ name: 'AbortError' })
})
