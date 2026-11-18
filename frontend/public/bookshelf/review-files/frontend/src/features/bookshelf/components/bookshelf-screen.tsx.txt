import { ArrowRight, Search } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import { handleTabNavigation } from '@/components/ui/tab-navigation'
import { useQuery, useQueryClient } from '@/lib/query'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import {
  getShelfCatalog,
  getShelfProgress,
  getShelfSearchIndex,
  setShelfMastery,
} from '@/services/bookshelf'
import { useShelfBookmarks } from '../hooks/use-shelf-bookmarks'
import EvidencePreview from './evidence-preview'
import ShelfReader from './shelf-reader'
import './bookshelf-screen.css'

interface BookshelfScreenProps {
  userId?: string
  token?: string
}
export default function BookshelfScreen({
  userId = 'test-workspace',
  token = '',
}: BookshelfScreenProps) {
  const params = new URLSearchParams(useUrlSearch())
  const selected = params.get('document') || ''
  const isReview = selected
    ? selected.startsWith('8-')
    : params.get('shelf') === 'review'
  const group = params.get('shelfGroup')
  const file = params.get('file')
  const [search, setSearch] = useState('')
  const [onlySaved, setOnlySaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState('')
  const client = useQueryClient()
  const progress = useQuery({
    queryKey: ['shelf-progress', userId],
    queryFn: ({ signal }) => getShelfProgress(token, signal),
    enabled: Boolean(token && !isReview),
    refetchInterval: 15000,
  })
  const bookmarks = useShelfBookmarks({
    userId,
    importLegacy: progress.data?.can_edit === true,
  })
  const catalog = useQuery({
    queryKey: ['bookshelf'],
    queryFn: ({ signal }) => getShelfCatalog(signal),
  })
  const searchIndex = useQuery({
    queryKey: ['bookshelf-search'],
    queryFn: ({ signal }) => getShelfSearchIndex(signal),
    enabled: Boolean(search.trim()),
  })
  const searching = Boolean(search.trim())
  const records = isReview
    ? catalog.data?.reviewDocuments || []
    : catalog.data?.records || []
  const document = records.find((item) => item.id === selected)
  const visible = records.filter(
    (item) =>
      (isReview || !group || String(item.group) === group) &&
      (isReview || !onlySaved || bookmarks.saved.includes(item.id)) &&
      `${item.title} ${item.goal || ''} ${searchIndex.data?.[item.id] || item.search}`
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  )
  function changeSection(section: string) {
    setSearch('')
    updateUrl({
      shelf: section,
      document: null,
      shelfGroup: null,
      file: null,
      line: null,
      anchor: null,
      filePage: null,
    })
  }
  async function toggleMastery() {
    if (document?.kind !== 'learning' || !progress.data?.can_edit || saving)
      return
    setSaving(true)
    setActionError('')
    try {
      const updated = await setShelfMastery({
        token,
        id: document.id,
        learned: !progress.data.ids.includes(document.id),
        revision: progress.data.revision,
      })
      client.setQueryData(['shelf-progress', userId], updated)
    } catch (error) {
      setActionError(displayError(error))
      await progress.refetch()
    } finally {
      setSaving(false)
    }
  }
  const mastered =
    catalog.data?.records.filter((item) => progress.data?.ids.includes(item.id))
      .length ?? 0
  return (
    <section className="shelf-module" aria-label="知识书架＆QA">
      <div
        className="tab-row"
        role="tablist"
        aria-label="书架内容"
        onKeyDown={handleTabNavigation}
      >
        <button
          type="button"
          role="tab"
          id="shelf-learning"
          aria-controls="shelf-content"
          aria-selected={!isReview}
          className={isReview ? '' : 'active'}
          tabIndex={isReview ? -1 : 0}
          onClick={() => changeSection('learning')}
        >
          知识文档 <span>{catalog.data?.records.length ?? '…'}</span>
        </button>
        <button
          type="button"
          role="tab"
          id="shelf-review"
          aria-controls="shelf-content"
          aria-selected={isReview}
          className={isReview ? 'active' : ''}
          tabIndex={isReview ? 0 : -1}
          onClick={() => changeSection('review')}
        >
          文档导航QA <span>{catalog.data?.reviewDocuments.length ?? '…'}</span>
        </button>
      </div>
      <div
        id="shelf-content"
        role="tabpanel"
        aria-labelledby={isReview ? 'shelf-review' : 'shelf-learning'}
      >
        {catalog.isPending && <Spinner label="正在读取书架" />}
        {catalog.error && (
          <ErrorNotice
            message={displayError(catalog.error)}
            onRetry={() => void catalog.refetch()}
          />
        )}
        {(actionError || bookmarks.error) && (
          <ErrorNotice message={actionError || bookmarks.error} />
        )}
        {!isReview && progress.error && (
          <ErrorNotice
            message={displayError(progress.error)}
            onRetry={() => void progress.refetch()}
          />
        )}
        {!file && selected && !document && !catalog.isPending ? (
          <EmptyState
            title="没有找到这份文档"
            detail="请选择目录中已有的资料。"
          />
        ) : null}
        {file && catalog.data ? (
          <EvidencePreview path={file} catalog={catalog.data} />
        ) : document && catalog.data ? (
          <ShelfReader
            document={document}
            catalog={catalog.data}
            learning={
              document.kind === 'learning'
                ? {
                    learned: progress.data?.initialized
                      ? progress.data.ids.includes(document.id)
                      : undefined,
                    canEdit: Boolean(
                      progress.data?.can_edit && !progress.error,
                    ),
                    saved: bookmarks.saved.includes(document.id),
                    busy: saving,
                    onMastery: () => void toggleMastery(),
                    onSave: () => bookmarks.toggle(document.id),
                  }
                : undefined
            }
          />
        ) : (
          !selected &&
          catalog.data && (
            <>
              <div className="shelf-list-toolbar">
                <label className="shelf-search">
                  <Search size={16} />
                  <span className="sr-only">
                    {isReview ? '搜索考核文档' : '搜索知识文档'}
                  </span>
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder={
                      isReview
                        ? '查找实现、测试和修复记录…'
                        : '搜索标题、学习目标或正文…'
                    }
                  />
                </label>
                <span className="shelf-count">
                  {visible.length} {isReview ? '份资料' : '篇知识文档'}
                  {!isReview && (
                    <span className="shelf-progress-summary">
                      {progress.data?.initialized
                        ? `共享进度 · 已掌握 ${mastered}/${catalog.data.records.length}（${Math.round((mastered / catalog.data.records.length) * 100)}%）`
                        : '共享进度 · 尚未取得'}
                      {progress.data?.initialized && (
                        <progress
                          aria-label="共享学习进度"
                          value={mastered}
                          max={catalog.data.records.length}
                        />
                      )}
                    </span>
                  )}
                </span>
              </div>
              {!isReview && (
                <fieldset className="shelf-groups" aria-label="知识方向">
                  <button
                    type="button"
                    aria-pressed={!group}
                    onClick={() => updateUrl({ shelfGroup: null })}
                  >
                    全部方向
                  </button>
                  {catalog.data.groups.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      aria-pressed={group === String(item.id)}
                      onClick={() => updateUrl({ shelfGroup: String(item.id) })}
                    >
                      {item.short}
                    </button>
                  ))}
                  <button
                    type="button"
                    aria-pressed={onlySaved}
                    onClick={() => setOnlySaved((value) => !value)}
                  >
                    只看收藏
                  </button>
                </fieldset>
              )}
              <div className="shelf-document-list">
                {visible.map((item) => (
                  <button
                    className="shelf-document"
                    type="button"
                    key={item.id}
                    onClick={() => updateUrl({ document: item.id })}
                  >
                    <span>
                      <strong>{item.title}</strong>
                      {!isReview && progress.data?.ids.includes(item.id) && (
                        <span className="shelf-mastered-label">已掌握</span>
                      )}
                      {!isReview && bookmarks.saved.includes(item.id) && (
                        <span className="shelf-saved-label">已收藏</span>
                      )}
                      {!isReview && item.goal && (
                        <span className="shelf-document-goal">{item.goal}</span>
                      )}
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
              {searching && searchIndex.isPending && (
                <Spinner label="正在读取全文搜索索引" />
              )}
              {searching && searchIndex.error && (
                <ErrorNotice
                  message={displayError(searchIndex.error)}
                  onRetry={() => void searchIndex.refetch()}
                />
              )}
              {!visible.length && (!searching || searchIndex.isSuccess) && (
                <EmptyState
                  title="没有匹配的文档"
                  detail="试试更短的关键词，或切换知识方向。"
                />
              )}
            </>
          )
        )}
      </div>
    </section>
  )
}
