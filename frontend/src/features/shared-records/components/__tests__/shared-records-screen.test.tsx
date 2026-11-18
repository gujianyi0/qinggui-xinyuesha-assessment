import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AppQueryProvider from '@/lib/query/provider'
import SharedRecordsScreen from '../shared-records-screen'

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})
it('reads owner history, citations and feedback without offering writes', async () => {
  window.history.replaceState({}, '', '/?page=shared')
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      expect(options?.method || 'GET').toBe('GET')
      calls.push(url)
      const items = url.includes('/messages')
        ? [
            {
              id: 'm',
              role: 'assistant',
              content: '公开历史回答',
              citations: [
                {
                  id: 'source',
                  title: '来源',
                  path: 'rule.md',
                  snapshot_id: 'snapshot',
                  excerpt: '原文',
                },
              ],
            },
          ]
        : url.includes('/feedback')
          ? [
              {
                id: 'f',
                revision: 2,
                status: 'submitted',
                created_at: '2026-11-18T00:00:00',
                payload: { actual: '主人反馈', steps: '复现步骤' },
              },
            ]
          : [
              {
                id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                title: '主人历史',
                created_at: '2026-11-18T00:00:00',
              },
            ]
      return new Response(
        JSON.stringify({
          items,
          total: 1,
          limit: 20,
          offset: 0,
          readonly: true,
        }),
      )
    }),
  )
  render(<SharedRecordsScreen userId="visitor" token="token" />, {
    wrapper: AppQueryProvider,
  })
  fireEvent.click(await screen.findByRole('button', { name: /主人历史/ }))
  expect(await screen.findByText('公开历史回答')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '查看来源 1：来源' }))
  expect(await screen.findByText('原文', { selector: 'p' })).toBeVisible()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: /确认|保存|发送/ }),
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '已提交反馈' }))
  expect(await screen.findByRole('heading', { name: '主人反馈' })).toBeVisible()
  expect(screen.getByText('复现步骤', { selector: 'dd' })).toBeVisible()
  expect(calls.some((url) => url.includes('kind=submitted'))).toBe(true)
})
