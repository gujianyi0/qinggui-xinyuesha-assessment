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
  const sourceDocument = {
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
  return sourceDocument
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
function mount(url = '/?page=bookshelf', token = '') {
  window.history.replaceState({}, '', url)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, options?: RequestInit) => {
      if (input.endsWith('/bookshelf/progress'))
        return new Response(
          JSON.stringify({
            ids: options?.method === 'PATCH' ? [] : ['7-06'],
            revision: options?.method === 'PATCH' ? 4 : 3,
            initialized: true,
            updatedAt: null,
            can_edit: token === 'owner',
          }),
        )
      return new Response(
        input.endsWith('search.json')
          ? JSON.stringify({ '7-06': '仅正文出现的关键词' })
          : input.endsWith('data.json')
            ? JSON.stringify(catalog)
            : '# 正文\n\n原文内容\n\n[修复记录](修复记录.md)',
      )
    }),
  )
  return render(<BookshelfScreen token={token} />, {
    wrapper: AppQueryProvider,
  })
}
afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
  localStorage.removeItem('qinggui-bookshelf-saved:test-workspace')
})

it('shows shared progress and owner mastery controls without merging review documents', async () => {
  mount('/?page=bookshelf', 'owner')
  expect(await screen.findByText('共享进度 · 已掌握 1/2（50%）')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: /部署验证/ }))
  const mastery = await screen.findByRole('button', { name: '取消掌握标记' })
  expect(mastery).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: '收藏文章' }))
  expect(screen.getByRole('button', { name: '已收藏文章' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(
    JSON.parse(
      localStorage.getItem('qinggui-bookshelf-saved:test-workspace') || '[]',
    ),
  ).toEqual(['7-06'])
  fireEvent.click(mastery)
  expect(
    await screen.findByRole('button', { name: '标记已掌握' }),
  ).toBeEnabled()
  const calls = vi.mocked(fetch).mock.calls
  const patch = calls.find(([, options]) => options?.method === 'PATCH')
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
    id: '7-06',
    learned: false,
    revision: 3,
  })
  expect(
    screen.queryByRole('link', { name: '下载原文' }),
  ).not.toBeInTheDocument()
  expect(screen.queryByText('学习交互验证')).not.toBeInTheDocument()
})

it('keeps shared mastery read only for a reviewer while allowing personal bookmarks', async () => {
  const view = mount('/?page=bookshelf&document=7-06', 'readonly')
  expect(
    await screen.findByRole('button', { name: '取消掌握标记' }),
  ).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '收藏文章' }))
  expect(screen.getByRole('button', { name: '已收藏文章' })).toBeEnabled()
  view.unmount()
  mount('/?page=bookshelf&document=7-06', 'readonly')
  expect(
    await screen.findByRole('button', { name: '已收藏文章' }),
  ).toHaveAttribute('aria-pressed', 'true')
  expect(
    vi
      .mocked(fetch)
      .mock.calls.some(([, options]) => options?.method === 'PATCH'),
  ).toBe(false)
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
  expect(await screen.findByText('没有匹配的文档')).toBeVisible()
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

it('loads full text only when searching and finds a body-only match', async () => {
  mount()
  await screen.findByRole('button', { name: /用户交互/ })
  expect(
    vi
      .mocked(fetch)
      .mock.calls.some(([url]) => String(url).endsWith('search.json')),
  ).toBe(false)
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索知识文档' }), {
    target: { value: '仅正文出现' },
  })
  expect(await screen.findByRole('button', { name: /部署验证/ })).toBeVisible()
  expect(
    screen.queryByRole('button', { name: /用户交互/ }),
  ).not.toBeInTheDocument()
})
