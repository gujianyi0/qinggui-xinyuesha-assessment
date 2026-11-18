import { ArrowLeft, ArrowRight, Check, Download, Star } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ErrorNotice, Spinner } from '@/components/ui'
import MarkdownDocument from '@/lib/markdown/markdown-document'
import { useQuery } from '@/lib/query'
import { updateUrl } from '@/lib/url-state'
import { displayError } from '@/services/api'
import { getShelfDocument } from '@/services/bookshelf'
import type {
  LearningActions,
  ShelfCatalog,
  ShelfDocument,
} from '@/types/bookshelf'
import { shelfHref } from '../utils/shelf-href'

interface ShelfReaderProps {
  document: ShelfDocument
  catalog: ShelfCatalog
  learning?: LearningActions
}
export default function ShelfReader({
  document,
  catalog,
  learning,
}: ShelfReaderProps) {
  const [fontSize, setFontSize] = useState(16)
  const reader = useRef<HTMLDivElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const isReview = document.kind === 'assessment_reference'
  const records = isReview ? catalog.reviewDocuments : catalog.records
  const index = records.findIndex((item) => item.id === document.id)
  const content = useQuery({
    queryKey: ['bookshelf-document', document.id],
    queryFn: ({ signal }) => getShelfDocument(document.id, signal),
  })
  function openDocument(id: string | null) {
    updateUrl({
      document: id,
      shelf: id
        ? id.startsWith('8-')
          ? 'review'
          : 'learning'
        : isReview
          ? 'review'
          : 'learning',
      file: null,
    })
  }
  function handleLink(href: string) {
    const url = new URL(href, location.href)
    if (href.startsWith('#')) {
      let anchor: string
      try {
        anchor = decodeURIComponent(url.hash.slice(1))
      } catch {
        return false
      }
      const normalize = (value: string) =>
        value.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
      const node = [
        ...(reader.current?.querySelectorAll('h1,h2,h3,h4,h5,h6') || []),
      ].find(
        (item) =>
          item.id === anchor ||
          normalize(item.textContent || '') === normalize(anchor),
      )
      node?.scrollIntoView({ block: 'start' })
      return Boolean(node)
    }
    if (
      url.origin === location.origin &&
      url.searchParams.get('page') === 'bookshelf'
    ) {
      if (url.searchParams.has('file'))
        updateUrl({
          file: url.searchParams.get('file'),
          line: url.searchParams.get('line'),
          anchor: url.searchParams.get('anchor'),
          filePage: null,
        })
      else openDocument(url.searchParams.get('document'))
      return true
    }
    return false
  }
  useEffect(() => {
    if (!content.data) return
    const scroll = heading.current?.closest('.page-content')
    if (scroll) scroll.scrollTop = 0
    heading.current?.focus({ preventScroll: true })
    reader.current?.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((node, i) => {
      node.id = `section-${i + 1}`
    })
  }, [content.data])
  return (
    <>
      <div className="shelf-reader-toolbar">
        <button
          className="text-button"
          type="button"
          onClick={() => openDocument(null)}
        >
          <ArrowLeft size={15} />
          返回{isReview ? '文档导航' : '知识目录'}
        </button>
        <div className="shelf-reader-actions">
          {learning && (
            <>
              <button
                type="button"
                className={
                  learning.learned ? 'shelf-mastery mastered' : 'shelf-mastery'
                }
                disabled={
                  !learning.canEdit ||
                  learning.busy ||
                  learning.learned === undefined
                }
                aria-label={learning.learned ? '取消掌握标记' : '标记已掌握'}
                title={learning.canEdit ? undefined : '共享进度由书架主人维护'}
                onClick={learning.onMastery}
              >
                <Check size={14} />
                {learning.busy
                  ? '正在保存'
                  : learning.learned === undefined
                    ? '进度未取得'
                    : learning.learned
                      ? '已掌握'
                      : '标记掌握'}
              </button>
              <button
                type="button"
                aria-pressed={learning.saved}
                onClick={learning.onSave}
              >
                <Star
                  size={14}
                  fill={learning.saved ? 'currentColor' : 'none'}
                />
                {learning.saved ? '已收藏文章' : '收藏文章'}
              </button>
            </>
          )}
          <button
            type="button"
            aria-label="缩小正文字号"
            disabled={fontSize <= 14}
            onClick={() => setFontSize((size) => size - 1)}
          >
            A−
          </button>
          <button
            type="button"
            aria-label="放大正文字号"
            disabled={fontSize >= 20}
            onClick={() => setFontSize((size) => size + 1)}
          >
            A＋
          </button>
          <a
            href={`/bookshelf/originals/${document.id}.md`}
            download={document.filename}
          >
            <Download size={14} />
            下载原文
          </a>
        </div>
      </div>
      <h1 className="shelf-title" ref={heading} tabIndex={-1}>
        {document.title}
      </h1>
      {!isReview && document.goal && (
        <p className="shelf-goal">{document.goal}</p>
      )}
      {content.error && (
        <ErrorNotice
          message={displayError(content.error)}
          onRetry={() => void content.refetch()}
        />
      )}
      {content.isPending ? (
        <Spinner label="正在打开文档" />
      ) : (
        content.data && (
          <div className="shelf-reading-layout">
            <div
              className="shelf-article shelf-primary-document"
              ref={reader}
              style={{ fontSize }}
            >
              <MarkdownDocument
                text={content.data}
                variant="document"
                onLink={handleLink}
                resolveHref={(href) =>
                  shelfHref({
                    href,
                    current: document,
                    records: [...catalog.records, ...catalog.reviewDocuments],
                    evidenceLinks: catalog.evidenceLinks,
                  })
                }
              />
            </div>
            {document.toc.length > 0 && (
              <nav className="shelf-toc" aria-label="文档目录">
                {document.toc.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() =>
                      reader.current
                        ?.querySelector(`#${item.id}`)
                        ?.scrollIntoView({ block: 'start' })
                    }
                  >
                    {item.text}
                  </button>
                ))}
              </nav>
            )}
          </div>
        )
      )}
      <nav className="shelf-pagination" aria-label="同类文档翻页">
        <button
          type="button"
          className="text-button"
          disabled={index < 1}
          onClick={() => openDocument(records[index - 1]?.id || null)}
        >
          <ArrowLeft size={15} />
          上一篇
        </button>
        <button
          type="button"
          className="text-button"
          disabled={index < 0 || index >= records.length - 1}
          onClick={() => openDocument(records[index + 1]?.id || null)}
        >
          下一篇
          <ArrowRight size={15} />
        </button>
      </nav>
    </>
  )
}
