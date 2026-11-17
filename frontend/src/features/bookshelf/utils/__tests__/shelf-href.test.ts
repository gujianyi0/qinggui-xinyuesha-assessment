import { expect, it } from 'vitest'
import type { ShelfDocument } from '@/types/bookshelf'
import { shelfHref } from '../shelf-href'

const current: ShelfDocument = {
  id: '8-01',
  kind: 'assessment_reference',
  title: '导航',
  filename: '导航.md',
  sourcePath: 'docs/文档导航QA/导航.md',
  search: '',
  toc: [],
}
it('only opens exported evidence and blocks absent private or malformed paths', () => {
  const resolve = (href: string) =>
    shelfHref({
      href,
      current,
      records: [],
      evidenceLinks: {
        'tests/test_api.py': '/bookshelf/review-files/tests/test_api.py',
      },
    })
  expect(resolve('../../tests/test_api.py')).toBe(
    '/?page=bookshelf&shelf=review&file=tests%2Ftest_api.py',
  )
  expect(resolve('../../.env.docker-live')).toBeUndefined()
  expect(resolve('../missing.md')).toBeUndefined()
  expect(resolve('javascript:alert(1)')).toBeUndefined()
  expect(resolve('%INVALID')).toBeUndefined()
})
