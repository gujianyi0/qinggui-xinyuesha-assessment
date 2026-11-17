import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import FeedbackPanel from '@/features/feedback/components/feedback-screen'
import AppQueryProvider from '@/lib/query/provider'

afterEach(() => vi.unstubAllGlobals())

it('edits a stored draft using its revision without changing session ownership', async () => {
  const draft = {
    id: 'draft-1',
    short_code: 'AABB1122',
    revision: 1,
    status: 'draft',
    session_id: 'session-1',
    category: 'rules',
    actual: '技能没有生效',
    expected: '',
    steps: '',
    context: '',
    platform: '',
    client_version: '',
    missing_fields: [],
  }
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith('/feedback-drafts') && !options?.method)
      return new Response(JSON.stringify([draft]), { status: 200 })
    if (options?.method === 'PATCH')
      return new Response(
        JSON.stringify({ ...draft, expected: '正常结算', revision: 2 }),
        { status: 200 },
      )
    return new Response('[]', { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<FeedbackPanel token="test" sessionId="session-1" />, {
    wrapper: AppQueryProvider,
  })
  fireEvent.click(await screen.findByText('技能没有生效'))
  const actual = screen.getByLabelText(/实际现象/)
  fireEvent.mouseDown(requiredElement(actual.closest('.form-field')))
  expect(actual).toHaveFocus()
  const version = screen.getByLabelText('客户端版本')
  fireEvent.mouseDown(requiredElement(version.closest('.form-field')))
  expect(version).toHaveFocus()
  fireEvent.change(screen.getByLabelText(/预期结果/), {
    target: { value: '正常结算' },
  })
  fireEvent.click(screen.getByRole('button', { name: '保存修改' }))
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH'),
    ).toBe(true),
  )
  const patchCall = fetchMock.mock.calls.find(
    ([, options]) => options?.method === 'PATCH',
  )
  if (!patchCall) throw new Error('缺少预期的 PATCH 请求')
  const [, options] = patchCall
  const payload = JSON.parse(String(options?.body))
  expect(payload).toMatchObject({ revision: 1, expected: '正常结算' })
  expect(payload).not.toHaveProperty('session_id')
})

function requiredElement<T extends Element>(element: T | null): T {
  if (!element) throw new Error('缺少预期的元素')
  return element
}

it('requires an explicit confirmation and submits the displayed draft revision only once', async () => {
  const draft = {
    id: 'draft-confirm',
    short_code: 'ABCD1234',
    revision: 3,
    status: 'draft',
    session_id: 'session-confirm',
    category: 'rules',
    actual: '连环伤害与预期不同',
    expected: '按固定测试结算',
    steps: '使用火杀',
    context: '两名角色横置',
    platform: '',
    client_version: '',
    missing_fields: [],
  }
  const confirmations: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/confirm')) {
        confirmations.push(String(options?.body))
        return new Response(
          JSON.stringify({ ...draft, id: 'feedback-1', status: 'confirmed' }),
        )
      }
      return new Response(
        JSON.stringify(url.endsWith('/feedback-drafts') ? [draft] : []),
      )
    }),
  )
  const user = (await import('@testing-library/user-event')).default.setup()
  render(<FeedbackPanel token="test" sessionId="session-confirm" />, {
    wrapper: AppQueryProvider,
  })
  await user.click(await screen.findByText('连环伤害与预期不同'))
  const review = screen.getByRole('button', { name: '核对并确认' })
  await user.click(review)
  expect(screen.getByRole('button', { name: '返回检查' })).toHaveFocus()
  expect(confirmations).toHaveLength(0)
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(review).toHaveFocus()
  await user.click(review)
  await user.click(screen.getByRole('button', { name: '确认保存反馈' }))
  await waitFor(() => expect(confirmations).toHaveLength(1))
  expect(JSON.parse(confirmations[0])).toEqual({ revision: 3 })
  await waitFor(() =>
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
  )
  expect(
    screen.queryByRole('button', { name: '核对并确认' }),
  ).not.toBeInTheDocument()
})
