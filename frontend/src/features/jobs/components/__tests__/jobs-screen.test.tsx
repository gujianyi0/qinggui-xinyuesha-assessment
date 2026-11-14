import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import AppQueryProvider from '@/lib/query/provider'
import JobsScreen from '../jobs-screen'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem('qinggui-job-pending:jobs-test')
})
function mount() {
  render(
    <AppQueryProvider>
      <JobsScreen
        userId="jobs-test"
        token="test"
        snapshots={[{ id: 'test', label: '测试快照', active: true }]}
        snapshotId="test"
      />
    </AppQueryProvider>,
  )
}
it('recovers the submit button after a damaged local receipt and never starts a duplicate job', async () => {
  const fetcher = vi.fn(
    async (_url: string, _options?: RequestInit) =>
      new Response('[]', { status: 200 }),
  )
  vi.stubGlobal('fetch', fetcher)
  localStorage.setItem('qinggui-job-pending:jobs-test', '{broken')
  mount()
  const user = userEvent.setup()
  const button = screen.getByRole('button', { name: /开始导入/ })
  await user.click(button)
  expect(await screen.findByText(/本地导入回执无法读取/)).toBeVisible()
  expect(button).toBeEnabled()
  expect(
    fetcher.mock.calls.every(([, options]) => options?.method !== 'POST'),
  ).toBe(true)
})
it('reuses the original idempotency key when a submit response is lost', async () => {
  const writes: string[] = []
  let hasFailed = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === 'POST') {
        const body = JSON.parse(String(options.body))
        writes.push(body.idempotency_key)
        if (!hasFailed) {
          hasFailed = true
          throw new TypeError('连接中断')
        }
        return new Response(
          JSON.stringify({
            id: 'job1',
            status: 'succeeded',
            attempts: 1,
            progress: 100,
            created_at: new Date().toISOString(),
          }),
        )
      }
      return new Response('[]')
    }),
  )
  mount()
  const user = userEvent.setup()
  const button = screen.getByRole('button', { name: /开始导入/ })
  await user.click(button)
  await screen.findByText('连接中断')
  await user.click(button)
  await waitFor(() => expect(writes.length).toBe(2))
  expect(writes[0]).toBe(writes[1])
  expect(localStorage.getItem('qinggui-job-pending:jobs-test')).toBeNull()
})
