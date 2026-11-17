import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AppQueryProvider from '@/lib/query/provider'
import type { ShelfCatalog, ShelfDocument } from '@/types/bookshelf'
import BookshelfScreen from '../bookshelf-screen'

function document(
  id: string,
  kind: ShelfDocument['kind'],
  title: string,
): ShelfDocument {
  return {
    id,
    kind,
    title,
    filename: `${title}.md`,
    sourcePath: `${kind === 'learning' ? 'learning' : 'docs/文档导航QA'}/${title}.md`,
    group: kind === 'learning' ? 6 : undefined,
    goal: kind === 'learning' ? '学习交互验证' : undefined,
    search: title,
    toc: [],
  }
}
const catalog: ShelfCatalog = {
  groups: [{ id: 6, title: '测试与部署', short: '测试与部署' }],
  records: [
    document('7-06', 'learning', '部署验证'),
    document('7-07', 'learning', '用户交互'),
  ],
  reviewDocuments: [
    document('8-01', 'assessment_reference', '考核导航'),
    document('8-02', 'assessment_reference', '修复记录'),
  ],
  evidenceLinks: {},
}
function mount(url = '/?page=bookshelf') {
  window.history.replaceState({}, '', url)
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (input: string) =>
        new Response(
          input.endsWith('data.json')
            ? JSON.stringify(catalog)
            : '# 正文\n\n原文内容\n\n[修复记录](修复记录.md)',
        ),
    ),
  )
  return render(<BookshelfScreen />, { wrapper: AppQueryProvider })
}
afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

it('keeps assessment references out of knowledge lists, search and categories', async () => {
  const { container } = mount()
  await screen.findByRole('button', { name: /用户交互/ })
  expect(screen.getByText('2 篇知识文档')).toBeVisible()
  expect(
    screen.queryByRole('button', { name: '考核导航' }),
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索知识文档' }), {
    target: { value: '考核' },
  })
  expect(screen.getByText('没有匹配的文档')).toBeVisible()
  fireEvent.keyDown(screen.getByRole('tab', { name: /知识文档/ }), {
    key: 'ArrowRight',
  })
  expect(await screen.findByRole('button', { name: '考核导航' })).toBeVisible()
  expect(
    screen.queryByRole('group', { name: '知识方向' }),
  ).not.toBeInTheDocument()
  expect(screen.getByText('2 份资料')).toBeVisible()
  expect(container.querySelector('iframe')).toBeNull()
  expect(screen.queryByText(/掌握|待学习|管理我的进度/)).not.toBeInTheDocument()
})

it('ends knowledge pagination at the last knowledge article', async () => {
  mount('/?page=bookshelf&document=7-07')
  await screen.findByText('原文内容')
  expect(screen.getByRole('heading', { name: '用户交互' })).toBeVisible()
  expect(screen.getByRole('button', { name: /下一篇/ })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: /返回知识目录/ }))
  expect(await screen.findByRole('button', { name: /部署验证/ })).toBeVisible()
  expect(
    screen.queryByRole('button', { name: '考核导航' }),
  ).not.toBeInTheDocument()
})

it('opens review deep links and follows review documents without joining the learning sequence', async () => {
  mount('/?page=bookshelf&document=8-01&shelf=learning')
  await screen.findByText('原文内容')
  expect(screen.getByRole('tab', { name: /文档导航QA/ })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const link = screen.getByRole('link', { name: '修复记录' })
  expect(link).toHaveAttribute(
    'href',
    '/?page=bookshelf&shelf=review&document=8-02',
  )
  fireEvent.click(link)
  expect(await screen.findByRole('heading', { name: '修复记录' })).toBeVisible()
  expect(screen.getByRole('button', { name: /下一篇/ })).toBeDisabled()
  expect(screen.queryByText('学习交互验证')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /返回文档导航/ }))
  expect(await screen.findByRole('button', { name: '考核导航' })).toBeVisible()
})
