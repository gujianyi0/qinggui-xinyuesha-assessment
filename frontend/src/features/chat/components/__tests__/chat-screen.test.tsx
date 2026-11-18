import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { flushSync } from 'react-dom'
import { expect, it, vi } from 'vitest'
import Chat from '@/features/chat/components/chat-screen'
import { streamRun } from '@/features/chat/services/run-transport'
import type { StreamEvent } from '@/types/domain'

vi.mock('@/features/chat/services/run-transport', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('@/features/chat/services/run-transport')
  >()),
  streamRun: vi.fn(async () => {}),
}))

it('keeps recovery disabled until the selected session history has loaded', async () => {
  localStorage.setItem(
    'qinggui-pending:test-workspace:pending-session',
    JSON.stringify({
      request_id: 'original',
      session_id: 'pending-session',
      message: '原问题',
      snapshot_id: 'test',
    }),
  )
  let finish!: (response: Response) => void
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        }),
    ),
  )
  try {
    render(
      <Chat
        token="test"
        sessionId="pending-session"
        onCreate={vi.fn()}
        snapshots={[]}
        snapshotId="test"
        onSnapshotChange={vi.fn()}
        isMockMode
        onFeedback={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: '恢复原请求' })).toBeDisabled()
    await act(async () => {
      finish(new Response('[]'))
    })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '恢复原请求' })).toBeEnabled(),
    )
  } finally {
    localStorage.clear()
    vi.unstubAllGlobals()
  }
})

it('focuses the real textarea when the composer padding is pressed', () => {
  render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={vi.fn()}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode
      onFeedback={vi.fn()}
    />,
  )
  const input = screen.getByLabelText('输入问题')
  fireEvent.mouseDown(requiredElement(input.closest('form')))
  expect(input).toHaveFocus()
})

it('cleans only assistant display text and keeps source details available at the answer end', async () => {
  const path = 'runtime/packages/standard/pkg/init.lua'
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify([
            {
              id: 'question',
              role: 'user',
              content: `查看 ${path}`,
              citations: [],
            },
            {
              id: 'answer',
              role: 'assistant',
              content: `**曹操体力4。** 依据：\`${path}\`。`,
              citations: [
                {
                  id: 'source',
                  title: '曹操',
                  path,
                  snapshot_id: 'test',
                  line_start: 17,
                  excerpt: '体力4。',
                },
              ],
            },
          ]),
        ),
    ),
  )
  try {
    render(
      <Chat
        token="test"
        sessionId="history"
        onCreate={vi.fn()}
        snapshots={[]}
        snapshotId="test"
        onSnapshotChange={vi.fn()}
        isMockMode={false}
        onFeedback={vi.fn()}
      />,
    )
    const answer = await screen.findByLabelText('轻归的回答')
    expect(answer.querySelector('.message-text')).toHaveTextContent(
      '曹操体力4。 依据：《曹操》。',
    )
    expect(answer.querySelector('.message-text')).not.toHaveTextContent(path)
    expect(screen.getByLabelText('你的问题')).toHaveTextContent(path)
    fireEvent.click(screen.getByRole('button', { name: '查看来源 1：曹操' }))
    expect(
      screen.getByRole('region', { name: '来源 1详情' }),
    ).toHaveTextContent(`${path}:17`)
  } finally {
    vi.unstubAllGlobals()
  }
})

it('preserves native text selection and does not intercept right clicks', () => {
  render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={vi.fn()}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode
      onFeedback={vi.fn()}
    />,
  )
  const input = screen.getByLabelText<HTMLTextAreaElement>('输入问题')
  expect(
    fireEvent.mouseDown(requiredElement(input.closest('form')), { button: 2 }),
  ).toBe(true)
  expect(input).not.toHaveFocus()
  fireEvent.change(input, { target: { value: '保留中文输入' } })
  input.focus()
  input.setSelectionRange(1, 4)
  expect(fireEvent.mouseDown(input)).toBe(true)
  expect(input.selectionStart).toBe(1)
  expect(input.selectionEnd).toBe(4)
  expect(
    fireEvent.mouseDown(screen.getByRole('button', { name: '发送问题' })),
  ).toBe(true)
})

it('keeps IME and Shift+Enter from submitting, while ordinary Enter still sends', async () => {
  const create = vi.fn(async () => ({
    id: 'new',
    title: '测试',
    created_at: '2026-11-12T00:00:00Z',
  }))
  render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={create}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode
      onFeedback={vi.fn()}
    />,
  )
  const input = screen.getByLabelText('输入问题')
  fireEvent.mouseDown(requiredElement(input.closest('form')))
  fireEvent.change(input, { target: { value: '中文问题' } })
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
  expect(create).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: 'Enter' })
  await waitFor(() =>
    expect(create).toHaveBeenCalledExactlyOnceWith('中文问题'),
  )
})

it('stops following streamed updates while reading above the bottom and resumes at the bottom', async () => {
  let emit!: (event: StreamEvent) => void
  let finish!: () => void
  vi.mocked(streamRun).mockImplementationOnce(async ({ onEvent }) => {
    emit = onEvent
    await new Promise<void>((resolve) => {
      finish = resolve
    })
  })
  const create = vi.fn(async () => ({
    id: 'stream-scroll',
    title: '滚动检查',
    created_at: '2026-11-14',
  }))
  const { container } = render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={create}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode={false}
      onFeedback={vi.fn()}
    />,
  )
  const pane = requiredElement(
    container.querySelector<HTMLDivElement>('.chat-scroll'),
  )
  Object.defineProperties(pane, {
    scrollHeight: { configurable: true, value: 1200 },
    clientHeight: { configurable: true, value: 300 },
  })
  fireEvent.change(screen.getByLabelText('输入问题'), {
    target: { value: '介绍曹操' },
  })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  await waitFor(() => expect(emit).toBeTypeOf('function'))
  act(() => emit({ event: 'delta', data: { text: '第一段' } }))
  expect(pane.scrollTop).toBe(1200)
  pane.scrollTop = 200
  fireEvent.scroll(pane)
  act(() => emit({ event: 'delta', data: { text: '第二段' } }))
  expect(pane.scrollTop).toBe(200)
  pane.scrollTop = 900
  fireEvent.scroll(pane)
  Object.defineProperty(pane, 'scrollHeight', {
    configurable: true,
    value: 1300,
  })
  act(() => emit({ event: 'delta', data: { text: '第三段' } }))
  expect(pane.scrollTop).toBe(1300)
  await act(async () => {
    emit({ event: 'completed', data: { text: '完整回答', citations: [] } })
    finish()
  })
})

it('pauses follow-to-bottom when a source is opened during streaming', async () => {
  let emit!: (event: StreamEvent) => void
  let finish!: () => void
  vi.mocked(streamRun).mockImplementationOnce(async ({ onEvent }) => {
    emit = onEvent
    await new Promise<void>((resolve) => {
      finish = resolve
    })
  })
  const { container } = render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={vi.fn(async () => ({
        id: 'source-stream',
        title: '来源',
        created_at: '2026-11-14',
      }))}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode={false}
      onFeedback={vi.fn()}
    />,
  )
  const pane = requiredElement(
    container.querySelector<HTMLDivElement>('.chat-scroll'),
  )
  Object.defineProperties(pane, {
    scrollHeight: { configurable: true, value: 1200 },
    clientHeight: { configurable: true, value: 300 },
  })
  fireEvent.change(screen.getByLabelText('输入问题'), {
    target: { value: '来源检查' },
  })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  await waitFor(() => expect(emit).toBeTypeOf('function'))
  act(() =>
    emit({
      event: 'citations',
      data: {
        items: [
          {
            id: 'source',
            title: '曹操',
            path: 'source.lua',
            snapshot_id: 'test',
          },
        ],
      },
    }),
  )
  fireEvent.click(screen.getByRole('button', { name: '查看来源 1：曹操' }))
  pane.scrollTop = 400
  act(() => emit({ event: 'delta', data: { text: '新增内容' } }))
  expect(pane.scrollTop).toBe(400)
  await act(async () => {
    emit({ event: 'completed', data: { text: '完成', citations: [] } })
    finish()
  })
})

function requiredElement<T extends Element>(element: T | null): T {
  if (!element) throw new Error('缺少预期的元素')
  return element
}

it('allows composing the next question during a reply without submitting it or losing it at completion', async () => {
  let emit: (event: StreamEvent) => void = () => {}
  let finish: () => void = () => {}
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('[]')),
  )
  vi.mocked(streamRun).mockImplementationOnce(async ({ onEvent }) => {
    emit = onEvent
    await new Promise<void>((resolve) => {
      finish = resolve
    })
  })
  try {
    render(
      <Chat
        token="test"
        sessionId="draft-session"
        onCreate={vi.fn()}
        snapshots={[]}
        snapshotId="test"
        onSnapshotChange={vi.fn()}
        isMockMode={false}
        onFeedback={vi.fn()}
      />,
    )
    const input = screen.getByRole('textbox', { name: '输入问题' })
    fireEvent.change(input, { target: { value: '曹操技能' } })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '发送问题' })).toBeEnabled(),
    )
    const before = vi.mocked(streamRun).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
    await screen.findByRole('button', { name: '取消回答' })
    expect(input).toBeEnabled()
    fireEvent.change(input, { target: { value: '刘备技能\n补充说明' } })
    expect(fireEvent.keyDown(input, { key: 'Enter' })).toBe(true)
    expect(vi.mocked(streamRun).mock.calls.length).toBe(before + 1)
    act(() => emit({ event: 'delta', data: { text: '正在回答曹操' } }))
    expect(input).toHaveValue('刘备技能\n补充说明')
    await act(async () => {
      emit({
        event: 'completed',
        data: { text: '曹操有奸雄和护驾', citations: [] },
      })
      finish()
    })
    await screen.findByRole('button', { name: '发送问题' })
    expect(input).toHaveValue('刘备技能\n补充说明')
    vi.mocked(streamRun).mockImplementationOnce(async ({ onEvent }) =>
      onEvent({
        event: 'completed',
        data: { text: '刘备有仁德和激将', citations: [] },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
    await waitFor(() =>
      expect(vi.mocked(streamRun).mock.calls.at(-1)?.[0].message).toBe(
        '刘备技能\n补充说明',
      ),
    )
  } finally {
    finish()
    vi.unstubAllGlobals()
  }
})

it('does not erase a new draft when new-session creation finishes later', async () => {
  let finishCreate: (session: {
    id: string
    title: string
    created_at: string
  }) => void = () => {}
  let finish: () => void = () => {}
  const create = vi.fn(
    () =>
      new Promise<{ id: string; title: string; created_at: string }>(
        (resolve) => {
          finishCreate = resolve
        },
      ),
  )
  vi.mocked(streamRun).mockImplementationOnce(
    async () =>
      new Promise<void>((resolve) => {
        finish = resolve
      }),
  )
  render(
    <Chat
      token="test"
      sessionId={null}
      onCreate={create}
      snapshots={[]}
      snapshotId="test"
      onSnapshotChange={vi.fn()}
      isMockMode={false}
      onFeedback={vi.fn()}
    />,
  )
  const input = screen.getByRole('textbox', { name: '输入问题' })
  fireEvent.change(input, { target: { value: '第一条' } })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  expect(input).toBeEnabled()
  expect(input).toHaveValue('')
  fireEvent.change(input, { target: { value: '下一条草稿' } })
  await act(async () =>
    finishCreate({
      id: 'new-session',
      title: '第一条',
      created_at: '2026-11-17',
    }),
  )
  expect(input).toHaveValue('下一条草稿')
  await act(async () => finish())
  expect(input).toHaveValue('下一条草稿')
})

it.each([false, true])(
  'preserves the appropriate draft if creating a conversation fails (new draft: %s)',
  async (hasNewDraft) => {
    let rejectCreate: (error: Error) => void = () => {}
    const create = vi.fn(
      () =>
        new Promise<{ id: string; title: string; created_at: string }>(
          (_resolve, reject) => {
            rejectCreate = reject
          },
        ),
    )
    render(
      <Chat
        token="test"
        sessionId={null}
        onCreate={create}
        snapshots={[]}
        snapshotId="test"
        onSnapshotChange={vi.fn()}
        isMockMode={false}
        onFeedback={vi.fn()}
      />,
    )
    const input = screen.getByRole('textbox', { name: '输入问题' })
    fireEvent.change(input, { target: { value: '原始问题' } })
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
    if (hasNewDraft) fireEvent.change(input, { target: { value: '新草稿' } })
    await act(async () => rejectCreate(new Error('创建会话失败')))
    expect(input).toHaveValue(hasNewDraft ? '新草稿' : '原始问题')
    expect(input).toBeEnabled()
    expect(screen.getByText('创建会话失败')).toBeVisible()
  },
)

it('keeps a next-question draft while recovering the previous request', async () => {
  const key = 'qinggui-pending:test-workspace:recover-edit'
  localStorage.setItem(
    key,
    JSON.stringify({
      request_id: 'original',
      session_id: 'recover-edit',
      message: '原始问题',
      snapshot_id: 'test',
    }),
  )
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (url: string) =>
        new Response(
          url.includes('/requests/')
            ? JSON.stringify({ run_id: 'old-run', status: 'running' })
            : '[]',
        ),
    ),
  )
  vi.mocked(streamRun).mockImplementationOnce(async ({ onEvent }) =>
    onEvent({
      event: 'completed',
      data: { text: '恢复的原回答', citations: [] },
    }),
  )
  try {
    render(
      <Chat
        token="test"
        sessionId="recover-edit"
        onCreate={vi.fn()}
        snapshots={[]}
        snapshotId="test"
        onSnapshotChange={vi.fn()}
        isMockMode={false}
        onFeedback={vi.fn()}
      />,
    )
    const recover = screen.getByRole('button', { name: '恢复原请求' })
    await waitFor(() => expect(recover).toBeEnabled())
    const input = screen.getByRole('textbox', { name: '输入问题' })
    fireEvent.change(input, { target: { value: '下一条草稿' } })
    fireEvent.click(recover)
    await screen.findByText('恢复的原回答')
    expect(input).toHaveValue('下一条草稿')
    expect(vi.mocked(streamRun).mock.calls.at(-1)?.[0].message).toBe('原始问题')
  } finally {
    localStorage.removeItem(key)
    vi.unstubAllGlobals()
  }
})

it('sends the first question when selecting the newly created session commits immediately', async () => {
  const props = {
    userId: 'first-send',
    token: 'test',
    onCreate: vi.fn(async () => ({
      id: 'new-conversation',
      title: '1',
      created_at: '2026-11-18T00:00:00Z',
    })),
    snapshots: [],
    snapshotId: 'test',
    onSnapshotChange: vi.fn(),
    isMockMode: false,
    onFeedback: vi.fn(),
  }
  let finish!: (event: StreamEvent) => void
  const observe = vi.mocked(streamRun).mockImplementationOnce(
    ({ onEvent, signal }) =>
      new Promise<void>((resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), {
          once: true,
        })
        finish = (event) => {
          onEvent(event)
          resolve()
        }
      }),
  )
  const select = vi.fn((id: string) => {
    flushSync(() =>
      rerender(<Chat {...props} sessionId={id} onSessionCreated={select} />),
    )
  })
  const { rerender } = render(
    <Chat {...props} sessionId={null} onSessionCreated={select} />,
  )

  fireEvent.change(screen.getByRole('textbox', { name: '输入问题' }), {
    target: { value: '1' },
  })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  await waitFor(() =>
    expect(select).toHaveBeenCalledExactlyOnceWith('new-conversation'),
  )
  expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({
    sessionId: 'new-conversation',
    message: '1',
  })
  expect(observe.mock.calls.at(-1)?.[0].signal.aborted).toBe(false)
  act(() =>
    finish({
      event: 'completed',
      data: { text: '请补充想问的规则', citations: [] },
    }),
  )
  expect(await screen.findByText('请补充想问的规则')).toBeVisible()
})

it('restores the first question after a reload interrupts creating the session', async () => {
  const props = {
    userId: 'refresh-during-creation',
    token: 'test',
    sessionId: null,
    onCreate: vi.fn(() => new Promise<never>(() => {})),
    snapshots: [],
    snapshotId: 'test',
    onSnapshotChange: vi.fn(),
    isMockMode: false,
    onFeedback: vi.fn(),
  }
  const before = render(<Chat {...props} />)
  fireEvent.change(screen.getByRole('textbox', { name: '输入问题' }), {
    target: { value: '1' },
  })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  expect(props.onCreate).toHaveBeenCalledExactlyOnceWith('1')
  before.unmount()
  const after = render(<Chat {...props} />)
  try {
    expect(screen.getByRole('textbox', { name: '输入问题' })).toHaveValue('1')
    expect(
      screen.getByText('已找回刷新前的问题，点击发送即可继续'),
    ).toBeVisible()
    expect(props.onCreate).toHaveBeenCalledTimes(1)
  } finally {
    after.unmount()
    sessionStorage.removeItem('qinggui-first-question:refresh-during-creation')
  }
})
