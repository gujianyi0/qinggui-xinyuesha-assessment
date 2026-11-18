import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AppQueryProvider from '@/lib/query/provider'
import type { ShelfCatalog } from '@/types/bookshelf'
import EvidencePreview from '../evidence-preview'

const catalog: ShelfCatalog = {
  groups: [],
  records: [],
  reviewDocuments: [],
  evidenceLinks: {},
  evidenceFiles: {
    'tests/test_api.py': {
      url: '/bookshelf/review-files/tests/test_api.py',
      bytes: 1000,
      sha256: 'test',
    },
    'docs/example.md': {
      url: '/bookshelf/review-files/docs/example.md',
      bytes: 20,
      sha256: 'markdown',
    },
  },
}
afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})
it('previews a source line in the workspace and leaves downloading as an explicit action', async () => {
  window.history.replaceState(
    {},
    '',
    '/?page=bookshelf&file=tests/test_api.py&line=105',
  )
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          Array.from({ length: 205 }, (_, i) => `source_line_${i + 1}`).join(
            '\n',
          ),
        ),
    ),
  )
  const { container } = render(
    <EvidencePreview path="tests/test_api.py" catalog={catalog} />,
    { wrapper: AppQueryProvider },
  )
  expect(await screen.findByText('source_line_105')).toBeVisible()
  expect(container.querySelector('[data-line="105"]')).toHaveClass(
    'highlighted',
  )
  expect(container.querySelectorAll('.evidence-line')).toHaveLength(100)
  expect(screen.getByRole('link', { name: '下载此文件' })).toHaveAttribute(
    'download',
    'test_api.py',
  )
  fireEvent.click(screen.getByRole('button', { name: '下一段' }))
  expect(await screen.findByText('source_line_205')).toBeVisible()
  expect(screen.queryByText('source_line_105')).not.toBeInTheDocument()
})
it('lists only exported files and never fetches an unlisted private path', async () => {
  vi.stubGlobal('fetch', vi.fn())
  const view = render(<EvidencePreview path="tests" catalog={catalog} />, {
    wrapper: AppQueryProvider,
  })
  expect(screen.getByRole('button', { name: /test_api.py/ })).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  view.rerender(<EvidencePreview path=".env.docker-live" catalog={catalog} />)
  expect(screen.getByText('该位置未收录')).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
})
it('renders Markdown evidence rather than triggering a file download', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('# 验证报告\n\n## 实际结果\n\n完成检查')),
  )
  render(<EvidencePreview path="docs/example.md" catalog={catalog} />, {
    wrapper: AppQueryProvider,
  })
  expect(await screen.findByRole('heading', { name: '实际结果' })).toBeVisible()
  expect(screen.getByText('完成检查')).toBeVisible()
})
