import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import AppQueryProvider from '@/lib/query/provider'
import LibraryScreen from '../library-screen'

afterEach(() => vi.unstubAllGlobals())
it('supports keyboard tab navigation and restores selected filters from the URL', async () => {
  window.history.replaceState({}, '', '/?page=library&kind=skill&q=空城')
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('[]')),
  )
  render(
    <AppQueryProvider>
      <LibraryScreen
        userId="library-test"
        token="test"
        snapshots={[{ id: 'test', label: '测试', active: true }]}
        snapshotId="test"
        onSnapshotChange={() => {}}
        onAsk={() => {}}
      />
    </AppQueryProvider>,
  )
  expect(screen.getByRole('textbox', { name: '搜索资料' })).toHaveValue('空城')
  const user = userEvent.setup()
  screen.getByRole('tab', { name: '游戏图鉴' }).focus()
  await user.keyboard('{ArrowRight}')
  expect(screen.getByRole('tab', { name: '复杂裁定' })).toHaveFocus()
  expect(new URLSearchParams(location.search).get('tab')).toBe('rulings')
  await user.keyboard('{Home}')
  expect(screen.getByRole('tab', { name: '游戏图鉴' })).toHaveFocus()
  expect(screen.getByRole('textbox', { name: '搜索资料' })).toHaveValue('空城')
})
