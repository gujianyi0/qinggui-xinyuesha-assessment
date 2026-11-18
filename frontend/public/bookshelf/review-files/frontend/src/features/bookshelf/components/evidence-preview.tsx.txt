import { ArrowLeft, Download, FolderOpen } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import MarkdownDocument from '@/lib/markdown/markdown-document'
import { useQuery } from '@/lib/query'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import { getShelfEvidence } from '@/services/bookshelf'
import type { ShelfCatalog, ShelfDocument } from '@/types/bookshelf'
import { shelfHref } from '../utils/shelf-href'

interface EvidencePreviewProps {
  catalog: ShelfCatalog
  path: string
}
export default function EvidencePreview({
  catalog,
  path,
}: EvidencePreviewProps) {
  const params = new URLSearchParams(useUrlSearch())
  const key = path === '.' ? '' : path
  const metadata = catalog.evidenceFiles?.[key]
  const image = /\.png$/i.test(key)
  const files = Object.keys(catalog.evidenceFiles || {})
  const prefix = key ? `${key}/` : ''
  const directory =
    !metadata && (key === '' || files.some((item) => item.startsWith(prefix)))
  const children = [
    ...new Set(
      files
        .filter((item) => item.startsWith(prefix))
        .map((item) => item.slice(prefix.length).split('/')[0]),
    ),
  ].sort()
  const content = useQuery({
    queryKey: ['shelf-evidence', key, metadata?.sha256],
    queryFn: ({ signal }) => getShelfEvidence(metadata?.url || '', signal),
    enabled: Boolean(metadata && !image),
  })
  const reader = useRef<HTMLDivElement>(null)
  const line = Math.max(1, Number(params.get('line')) || 1)
  const anchor = params.get('anchor') || ''
  const lines = useMemo(
    () =>
      (content.data || '')
        .replace(/\r\n?/g, '\n')
        .split('\n')
        .map((text, index) => ({ number: index + 1, text })),
    [content.data],
  )
  const pageCount = Math.max(1, Math.ceil(lines.length / 100))
  const page = Math.min(
    pageCount - 1,
    Math.max(0, Number(params.get('filePage')) || Math.floor((line - 1) / 100)),
  )
  const markdown =
    /\.md$/i.test(key) &&
    (content.data?.length || 0) <= 200000 &&
    !params.has('line')
  const context: ShelfDocument = {
    id: '',
    kind: 'assessment_reference',
    title: key,
    filename: key,
    sourcePath: key,
    search: '',
    toc: [],
  }
  function openFile(next: string) {
    updateUrl({ file: next || '.', filePage: null, line: null, anchor: null })
  }
  function handleLink(href: string) {
    if (href.startsWith('#')) {
      updateUrl({ anchor: href.slice(1) })
      return true
    }
    const url = new URL(href, location.href)
    if (
      url.origin !== location.origin ||
      url.searchParams.get('page') !== 'bookshelf'
    )
      return false
    if (url.searchParams.has('file'))
      updateUrl({
        file: url.searchParams.get('file') || '.',
        line: url.searchParams.get('line'),
        anchor: url.searchParams.get('anchor'),
        filePage: null,
      })
    else
      updateUrl({
        file: null,
        document: url.searchParams.get('document'),
        shelf: url.searchParams.get('shelf'),
        filePage: null,
        line: null,
        anchor: null,
      })
    return true
  }
  useEffect(() => {
    if (!content.data) return
    const scroll = reader.current?.closest('.page-content')
    if (scroll) scroll.scrollTop = 0
    if (anchor) {
      const normalize = (value: string) =>
        value.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
      const headings = [
        ...(reader.current?.querySelectorAll('h1,h2,h3,h4,h5,h6') || []),
      ]
      headings.forEach((node, index) => {
        node.id = `section-${index + 1}`
      })
      headings
        .find(
          (node) =>
            node.id === anchor ||
            normalize(node.textContent || '') === normalize(anchor),
        )
        ?.scrollIntoView?.({ block: 'start' })
    }
    reader.current
      ?.querySelector(`[data-line="${line}"]`)
      ?.scrollIntoView?.({ block: 'center' })
  }, [content.data, line, anchor])
  return (
    <section className="shelf-evidence" aria-label="项目文件预览">
      <div className="shelf-reader-toolbar">
        <button
          className="text-button"
          type="button"
          onClick={() =>
            updateUrl({ file: null, filePage: null, line: null, anchor: null })
          }
        >
          <ArrowLeft size={15} />
          返回文档
        </button>
        {metadata && (
          <a
            className="text-button"
            href={metadata.url}
            download={key.split('/').at(-1)}
          >
            <Download size={14} />
            下载此文件
          </a>
        )}
      </div>
      <nav className="evidence-breadcrumb" aria-label="文件相对位置">
        <button type="button" onClick={() => openFile('.')}>
          项目文件
        </button>
        {key
          .split('/')
          .filter(Boolean)
          .map((part, index, parts) => (
            <span key={parts.slice(0, index + 1).join('/')}>
              <span aria-hidden="true"> / </span>
              <button
                type="button"
                onClick={() => openFile(parts.slice(0, index + 1).join('/'))}
              >
                {part}
              </button>
            </span>
          ))}
      </nav>
      {directory ? (
        <div className="shelf-document-list">
          {children.map((name) => {
            const child = prefix + name
            const isFile = Boolean(catalog.evidenceFiles?.[child])
            return (
              <button
                className="shelf-document"
                type="button"
                key={child}
                onClick={() => openFile(child)}
              >
                <span>
                  {!isFile && <FolderOpen size={15} />} {name}
                  {!isFile && '/'}
                </span>
              </button>
            )
          })}
        </div>
      ) : !metadata ? (
        <EmptyState
          title="该位置未收录"
          detail="只能查看本次检阅资料中已导出的项目文件。"
        />
      ) : image ? (
        <img
          className="evidence-image"
          src={metadata.url}
          alt={`证据图片：${key.split('/').at(-1)}`}
        />
      ) : content.isPending ? (
        <Spinner label="正在打开项目文件" />
      ) : content.error ? (
        <ErrorNotice
          message={displayError(content.error)}
          onRetry={() => void content.refetch()}
        />
      ) : (
        <div ref={reader}>
          {markdown ? (
            <div className="shelf-article">
              <MarkdownDocument
                text={content.data || ''}
                variant="document"
                onLink={handleLink}
                resolveHref={(href) =>
                  shelfHref({
                    href,
                    current: context,
                    records: [...catalog.records, ...catalog.reviewDocuments],
                    evidenceLinks: catalog.evidenceLinks,
                  })
                }
              />
            </div>
          ) : (
            <>
              <div className="evidence-page-control">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() =>
                    updateUrl({ filePage: String(page - 1), line: null })
                  }
                >
                  上一段
                </button>
                <span>
                  第 {page * 100 + 1}–{Math.min(lines.length, (page + 1) * 100)}{' '}
                  行 / 共 {lines.length} 行
                </span>
                <button
                  type="button"
                  disabled={page >= pageCount - 1}
                  onClick={() =>
                    updateUrl({ filePage: String(page + 1), line: null })
                  }
                >
                  下一段
                </button>
              </div>
              <section className="evidence-code" aria-label="文件内容">
                {lines.slice(page * 100, (page + 1) * 100).map((sourceLine) => (
                  <EvidenceLine
                    key={`${key}:${sourceLine.number}`}
                    number={sourceLine.number}
                    text={sourceLine.text}
                    highlighted={
                      sourceLine.number === line && params.has('line')
                    }
                  />
                ))}
              </section>
            </>
          )}
        </div>
      )}
    </section>
  )
}

function EvidenceLine({
  number,
  text,
  highlighted,
}: {
  number: number
  text: string
  highlighted: boolean
}) {
  const [limit, setLimit] = useState(8192)
  return (
    <div
      className={highlighted ? 'evidence-line highlighted' : 'evidence-line'}
      data-line={number}
    >
      <span className="evidence-line-number" aria-hidden="true">
        {number}
      </span>
      <code>
        {text.slice(0, limit) || ' '}
        {text.length > limit && (
          <button
            type="button"
            onClick={() => setLimit((value) => value + 8192)}
          >
            继续显示本行（尚余{text.length - limit}字符）
          </button>
        )}
      </code>
    </div>
  )
}
