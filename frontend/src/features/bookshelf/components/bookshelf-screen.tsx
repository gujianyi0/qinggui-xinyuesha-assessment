import { ArrowRight, Search } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import { handleTabNavigation } from '@/components/ui/tab-navigation'
import { useQuery } from '@/lib/query'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import { getShelfCatalog } from '@/services/bookshelf'
import ShelfReader from './shelf-reader'
import './bookshelf-screen.css'

export default function BookshelfScreen() {
  const params = new URLSearchParams(useUrlSearch())
  const selected = params.get('document') || ''
  const isReview = selected
    ? selected.startsWith('8-')
    : params.get('shelf') === 'review'
  const group = params.get('shelfGroup')
  const [search, setSearch] = useState('')
  const catalog = useQuery({
    queryKey: ['bookshelf'],
    queryFn: ({ signal }) => getShelfCatalog(signal),
  })
  const records = isReview
    ? catalog.data?.reviewDocuments || []
    : catalog.data?.records || []
  const document = records.find((item) => item.id === selected)
  const visible = records.filter(
    (item) =>
      (isReview || !group || String(item.group) === group) &&
      `${item.title} ${item.goal || ''} ${item.search}`
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  )
  function changeSection(section: string) {
    setSearch('')
    updateUrl({ shelf: section, document: null, shelfGroup: null })
  }
  return (
    <section className="shelf-module" aria-label="知识书架">
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
        {selected && !document && !catalog.isPending ? (
          <EmptyState
            title="没有找到这份文档"
            detail="请选择目录中已有的资料。"
          />
        ) : null}
        {document && catalog.data ? (
          <ShelfReader document={document} catalog={catalog.data} />
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
                      {!isReview && item.goal && (
                        <span className="shelf-document-goal">{item.goal}</span>
                      )}
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
              {!visible.length && (
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
