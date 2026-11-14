import {
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  Database,
  FileCode2,
  Search,
  ShieldCheck,
  Swords,
  UsersRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import CitationList from '@/components/business/source-citations'
import StatusTag from '@/components/business/status-tag'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import { focusTextControlSurface } from '@/components/ui/input-surface'
import { handleTabNavigation } from '@/components/ui/tab-navigation'
import { useQuery } from '@/lib/query'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import { listEntities, listRulings } from '@/services/knowledge'
import type { Snapshot } from '@/types/domain'

interface LibraryScreenProps {
  userId: string
  token: string
  snapshots: Snapshot[]
  snapshotId: string
  onSnapshotChange: (id: string) => void
  onAsk: (question: string) => void
}
const ENTITY_KINDS = [
  { id: 'general', label: '武将', icon: UsersRound },
  { id: 'card', label: '卡牌', icon: Swords },
  { id: 'skill', label: '技能', icon: FileCode2 },
]
const PACKAGE_LABELS: Record<string, string> = {
  standard: '标准武将',
  standard_cards: '标准 / EX 牌',
  maneuvering: '军争',
}
const ATTRIBUTE_LABELS: Record<string, string> = {
  hp: '体力',
  max_hp: '体力上限',
  kingdom: '势力',
  gender: '性别',
  skills: '技能',
  card_type: '类型',
  subtype: '子类型',
  range: '攻击范围',
  suit: '花色',
  number: '点数',
}

export default function LibraryScreen({
  userId,
  token,
  snapshots,
  snapshotId,
  onSnapshotChange,
  onAsk,
}: LibraryScreenProps) {
  const params = new URLSearchParams(useUrlSearch())
  const requestedKind = params.get('kind')
  const kind =
    requestedKind === 'card' || requestedKind === 'skill'
      ? requestedKind
      : 'general'
  const tab = params.get('tab') === 'rulings' ? 'rulings' : 'entities'
  const query = params.get('q') || ''
  const [search, setSearch] = useState(query)
  const [expanded, setExpanded] = useState<string | null>(null)
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query), 250)
    return () => clearTimeout(timer)
  }, [query])
  const entitiesQuery = useQuery({
    queryKey: ['entities', userId, snapshotId, kind, search],
    queryFn: ({ signal }) =>
      listEntities({ token, signal, snapshotId, kind, search }),
    enabled: Boolean(snapshotId) && tab === 'entities',
  })
  const rulingsQuery = useQuery({
    queryKey: ['rulings', userId, snapshotId],
    queryFn: ({ signal }) => listRulings({ token, signal, snapshotId }),
    enabled: Boolean(snapshotId) && tab === 'rulings',
  })
  const entities = entitiesQuery.data ?? []
  const rulings = rulingsQuery.data ?? []
  const activeQuery = tab === 'entities' ? entitiesQuery : rulingsQuery
  const isLoading = Boolean(snapshotId) && activeQuery.isPending
  const error = activeQuery.error ? displayError(activeQuery.error) : ''
  const load = () => activeQuery.refetch()
  const setKind = (kind: string) => updateUrl({ kind })
  const setTab = (tab: string) => updateUrl({ tab })
  const setQuery = (q: string) => updateUrl({ q }, { replace: true })
  const snapshot = snapshots.find((item) => item.id === snapshotId)

  return (
    <section className="standard-page library-page">
      <div className="page-heading">
        <div>
          <span className="section-kicker">先找到依据，再形成结论</span>
          <h1>游戏资料库</h1>
          <p>查询武将、卡牌与技能，回看明确标注版本的规则证据</p>
        </div>
        <div className="snapshot-control">
          <Database size={14} />
          <label className="sr-only" htmlFor="library-snapshot">
            资料库快照
          </label>
          <select
            id="library-snapshot"
            value={snapshotId}
            onChange={(e) => onSnapshotChange(e.target.value)}
          >
            {!snapshots.length && <option value="">暂无快照</option>}
            {snapshots.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <ChevronDown size={13} />
        </div>
      </div>
      <div className="library-overview">
        <div className="overview-icon">
          <BookOpen size={28} strokeWidth={1.3} />
        </div>
        <div>
          <span className="eyebrow">CURRENT SNAPSHOT</span>
          <h2>{snapshot?.label ?? '资料快照等待导入'}</h2>
          <p>
            标准武将 <span>／</span> 标准与 EX 牌 <span>／</span> 军争
          </p>
        </div>
        <div className="snapshot-version">
          <span>源码标识</span>
          <code>{snapshot?.commit?.slice(0, 12) ?? '待记录'}</code>
          <small>每条资料保留独立来源</small>
        </div>
      </div>
      <div
        className="tab-row"
        role="tablist"
        onKeyDown={handleTabNavigation}
        aria-label="资料分类"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'entities'}
          tabIndex={tab === 'entities' ? 0 : -1}
          className={tab === 'entities' ? 'active' : ''}
          onClick={() => setTab('entities')}
        >
          <BookOpen size={16} />
          游戏图鉴
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'rulings'}
          tabIndex={tab === 'rulings' ? 0 : -1}
          className={tab === 'rulings' ? 'active' : ''}
          onClick={() => setTab('rulings')}
        >
          <ShieldCheck size={16} />
          复杂裁定
        </button>
      </div>
      {activeQuery.isFetching && !isLoading && (
        <p className="refresh-hint" role="status">
          正在更新资料，已显示的内容会保留
        </p>
      )}
      {error && <ErrorNotice message={error} onRetry={() => void load()} />}
      {tab === 'entities' ? (
        <>
          <div className="library-controls">
            <fieldset className="segmented-control" aria-label="实体类型">
              {ENTITY_KINDS.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={kind === item.id ? 'selected' : ''}
                  onClick={() => {
                    setKind(item.id)
                    setExpanded(null)
                  }}
                >
                  <item.icon size={14} />
                  {item.label}
                </button>
              ))}
            </fieldset>
            <label
              className="search-field"
              onMouseDown={focusTextControlSurface}
            >
              <Search size={16} />
              <span className="form-label">搜索资料</span>
              <input
                id="entity-search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索名称、技能或关键词"
              />
            </label>
          </div>
          {isLoading ? (
            <div className="panel-loading">
              <Spinner label="正在查找资料" />
            </div>
          ) : entities.length ? (
            <>
              <div className="results-meta">
                找到 <strong>{entities.length}</strong> 条资料
                <span>点击展开来源与属性</span>
              </div>
              <div className="entity-grid">
                {entities.map((entity) => (
                  <article
                    className={`entity-card ${expanded === entity.id ? 'expanded' : ''}`}
                    key={entity.id}
                  >
                    <button
                      type="button"
                      className="entity-heading"
                      aria-expanded={expanded === entity.id}
                      onClick={() =>
                        setExpanded(expanded === entity.id ? null : entity.id)
                      }
                    >
                      <span className={`entity-symbol ${entity.kind}`}>
                        {entity.name?.slice(0, 1) ?? '?'}
                      </span>
                      <span>
                        <small>
                          {PACKAGE_LABELS[entity.package] ?? entity.package}
                        </small>
                        <h3>{entity.name}</h3>
                      </span>
                      <ChevronDown
                        size={16}
                        className={expanded === entity.id ? 'rotated' : ''}
                      />
                    </button>
                    <p className="entity-description">
                      {entity.description || '展开查看结构化属性与原始资料'}
                    </p>
                    {expanded === entity.id && (
                      <div className="entity-expanded">
                        <dl>
                          {Object.entries(entity.attributes ?? {}).map(
                            ([key, value]) => (
                              <div key={key}>
                                <dt>{ATTRIBUTE_LABELS[key] ?? key}</dt>
                                <dd>
                                  {Array.isArray(value)
                                    ? value.join('、')
                                    : typeof value === 'object'
                                      ? JSON.stringify(value)
                                      : String(value)}
                                </dd>
                              </div>
                            ),
                          )}
                        </dl>
                        {entity.source && (
                          <CitationList items={[entity.source]} compact />
                        )}
                        <button
                          type="button"
                          className="text-button teal"
                          onClick={() =>
                            onAsk(
                              `请介绍${entity.name}的规则与使用条件，并提供来源。`,
                            )
                          }
                        >
                          问问轻归
                          <ArrowUpRight size={14} />
                        </button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title={query ? '没有找到匹配资料' : '当前还没有图鉴记录'}
              detail={
                query
                  ? '尝试更短的名称，或切换武将、卡牌、技能分类'
                  : '先在后台任务中导入已配置的资料快照'
              }
            />
          )}
        </>
      ) : (
        <>
          <div className="info-callout">
            <ShieldCheck size={18} />
            <p>
              只有附带规则引擎执行证据的场景才标为“引擎已验证”；裁定适用于所列前提和快照
            </p>
          </div>
          {isLoading ? (
            <div className="panel-loading">
              <Spinner label="加载裁定场景" />
            </div>
          ) : rulings.length ? (
            <div className="ruling-grid">
              {rulings.map((ruling) => (
                <article className="ruling-card" key={ruling.id}>
                  <div className="ruling-card-top">
                    <code>{ruling.id}</code>
                    <StatusTag status={ruling.status} />
                  </div>
                  <h3>{ruling.title}</h3>
                  <p>
                    {ruling.summary || '场景结论需结合完整条件与执行证据核对'}
                  </p>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      setExpanded(expanded === ruling.id ? null : ruling.id)
                    }
                    aria-expanded={expanded === ruling.id}
                  >
                    查看前提条件
                    <ChevronDown
                      size={13}
                      className={expanded === ruling.id ? 'rotated' : ''}
                    />
                  </button>
                  {expanded === ruling.id && (
                    <div className="ruling-conditions">
                      {Array.isArray(ruling.required_conditions) ? (
                        <ul>
                          {ruling.required_conditions.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <dl>
                          {Object.entries(ruling.required_conditions ?? {}).map(
                            ([key, value]) => (
                              <div key={key}>
                                <dt>{key}</dt>
                                <dd>
                                  {typeof value === 'object'
                                    ? JSON.stringify(value)
                                    : String(value)}
                                </dd>
                              </div>
                            ),
                          )}
                        </dl>
                      )}
                      <small>快照 {ruling.snapshot_id}</small>
                    </div>
                  )}
                  <button
                    type="button"
                    className="ruling-ask"
                    onClick={() =>
                      onAsk(
                        `请核对 ${ruling.id}「${ruling.title}」的结算，先告诉我需要补充哪些局面条件。`,
                      )
                    }
                  >
                    带着这个场景提问
                    <ArrowUpRight size={14} />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="裁定场景尚未载入"
              detail="请先检查规则场景和证据是否已导入；未执行场景不会显示为已验证"
            />
          )}
        </>
      )}
    </section>
  )
}
