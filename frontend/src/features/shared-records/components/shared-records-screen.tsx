import CitationList from '@/components/business/source-citations'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import { handleTabNavigation } from '@/components/ui/tab-navigation'
import { answerText } from '@/features/chat'
import { relativeDate } from '@/lib/date-time'
import { useQuery } from '@/lib/query'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import {
  getSharedFeedback,
  getSharedMessages,
  getSharedSessions,
} from '@/services/shared-records'
import type { DraftInput } from '@/types/domain'
import './shared-records-screen.css'

interface SharedRecordsScreenProps {
  userId: string
  token: string
}
const fields: { key: keyof DraftInput; label: string }[] = [
  { key: 'actual', label: '实际现象' },
  { key: 'expected', label: '预期结果' },
  { key: 'steps', label: '复现步骤' },
  { key: 'context', label: '局面与条件' },
  { key: 'platform', label: '平台' },
  { key: 'client_version', label: '客户端版本' },
]
const tabs = [
  { id: 'sessions', label: '历史对话' },
  { id: 'drafts', label: '反馈草稿' },
  { id: 'submitted', label: '已提交反馈' },
] as const
export default function SharedRecordsScreen({
  userId,
  token,
}: SharedRecordsScreenProps) {
  const params = new URLSearchParams(useUrlSearch())
  const tab =
    params.get('sharedTab') === 'drafts'
      ? 'drafts'
      : params.get('sharedTab') === 'submitted'
        ? 'submitted'
        : 'sessions'
  const offset = pageOffset(params.get('sharedOffset'))
  const messageOffset = pageOffset(params.get('sharedMessageOffset'))
  const sessionId = /^[a-f0-9-]{36}$/.test(params.get('sharedSession') || '')
    ? params.get('sharedSession') || ''
    : ''
  const sessions = useQuery({
    queryKey: ['shared-sessions', userId, offset],
    queryFn: ({ signal }) => getSharedSessions({ token, offset, signal }),
    enabled: tab === 'sessions',
  })
  const messages = useQuery({
    queryKey: ['shared-messages', userId, sessionId, messageOffset],
    queryFn: ({ signal }) =>
      getSharedMessages({ token, sessionId, offset: messageOffset, signal }),
    enabled: tab === 'sessions' && Boolean(sessionId),
  })
  const feedback = useQuery({
    queryKey: ['shared-feedback', userId, tab, offset],
    queryFn: ({ signal }) =>
      getSharedFeedback({
        token,
        kind: tab === 'drafts' ? 'drafts' : 'submitted',
        offset,
        signal,
      }),
    enabled: tab !== 'sessions',
  })
  const list = tab === 'sessions' ? sessions : feedback
  const error =
    list.error || (tab === 'sessions' && sessionId ? messages.error : null)
  return (
    <section className="shared-records" aria-label="公开历史与反馈">
      <div className="shared-heading">
        <div>
          <h1>公开历史与反馈</h1>
          <p>项目主人授权公开 · 只读检阅</p>
        </div>
        <button
          type="button"
          onClick={() => {
            void list.refetch()
            if (sessionId) void messages.refetch()
          }}
        >
          刷新记录
        </button>
      </div>
      <p className="muted">
        与本机同一份记录，刷新即可查看更新。这里的主人记录不可修改；你的新对话和“我的反馈”仍属于你自己的身份。
      </p>
      <div
        className="tab-row"
        role="tablist"
        aria-label="公开记录类型"
        onKeyDown={handleTabNavigation}
      >
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`shared-tab-${item.id}`}
            aria-controls="shared-content"
            className={tab === item.id ? 'active' : ''}
            aria-selected={tab === item.id}
            tabIndex={tab === item.id ? 0 : -1}
            onClick={() =>
              updateUrl({
                sharedTab: item.id,
                sharedOffset: null,
                sharedSession: null,
                sharedMessageOffset: null,
              })
            }
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id="shared-content"
        role="tabpanel"
        aria-labelledby={`shared-tab-${tab}`}
      >
        {list.isPending && <Spinner label="正在读取公开记录" />}
        {error && (
          <ErrorNotice
            message={displayError(error)}
            onRetry={() => {
              void list.refetch()
              if (sessionId) void messages.refetch()
            }}
          />
        )}
        {list.data && (
          <>
            <p className="muted">
              共 {list.data.total} 条
              {tabs.find((item) => item.id === tab)?.label}
            </p>
            {tab === 'sessions' ? (
              sessionId ? (
                <>
                  <button
                    type="button"
                    onClick={() =>
                      updateUrl({
                        sharedSession: null,
                        sharedMessageOffset: null,
                      })
                    }
                  >
                    返回公开会话列表
                  </button>
                  <p>
                    只读历史对话 ·{' '}
                    {sessions.data?.items.find((item) => item.id === sessionId)
                      ?.title || '主人已公开的会话'}
                  </p>
                  {messages.isPending && <Spinner label="正在读取历史消息" />}
                  {messages.data?.items.map((item) => (
                    <article
                      className="shared-message"
                      key={item.id}
                      aria-label={
                        item.role === 'user' ? '主人的提问' : '轻归的历史回答'
                      }
                    >
                      <h2>{item.role === 'user' ? '主人' : '轻归'}</h2>
                      <div className="shared-content">
                        {item.role === 'assistant'
                          ? answerText(item.content, item.citations)
                          : item.content}
                      </div>
                      {item.citations?.length > 0 && (
                        <CitationList items={item.citations} compact />
                      )}
                    </article>
                  ))}
                  {messages.data && (
                    <Pager
                      offset={messageOffset}
                      limit={messages.data.limit}
                      total={messages.data.total}
                      onPage={(value) =>
                        updateUrl({ sharedMessageOffset: String(value) })
                      }
                    />
                  )}
                  {messages.data?.total === 0 && (
                    <EmptyState
                      title="这份会话暂无消息"
                      detail="尚未生成历史对话。"
                    />
                  )}
                </>
              ) : (
                <div className="shared-session-list">
                  {sessions.data?.items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() =>
                        updateUrl({
                          sharedSession: item.id,
                          sharedMessageOffset: null,
                        })
                      }
                    >
                      <strong>{item.title}</strong>
                      <span>{relativeDate(item.created_at)}</span>
                    </button>
                  ))}
                </div>
              )
            ) : (
              feedback.data?.items.map((item) => (
                <article key={item.id} className="shared-message">
                  <h2>{item.payload.actual || '反馈记录'}</h2>
                  <p className="muted">
                    {item.status === 'submitted'
                      ? '已提交'
                      : item.status === 'confirmed'
                        ? '已确认草稿'
                        : '草稿'}{' '}
                    · 修订 {item.revision} · {relativeDate(item.created_at)}
                  </p>
                  <dl>
                    {fields.map((field) => (
                      <div key={field.key}>
                        <dt>{field.label}</dt>
                        <dd>{item.payload[field.key] || '未填写'}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))
            )}
            {!sessionId && (
              <Pager
                offset={offset}
                limit={list.data.limit}
                total={list.data.total}
                onPage={(value) => updateUrl({ sharedOffset: String(value) })}
              />
            )}
            {!list.data.total && (
              <EmptyState
                title="暂无公开记录"
                detail="主人尚未保存此类记录；不会用演示数据补齐。"
              />
            )}
          </>
        )}
      </div>
    </section>
  )
}
function pageOffset(value: string | null) {
  const number = Number(value)
  return Number.isSafeInteger(number) && number >= 0 ? number : 0
}
function Pager({
  offset,
  limit,
  total,
  onPage,
}: {
  offset: number
  limit: number
  total: number
  onPage: (offset: number) => void
}) {
  return (
    <nav className="shared-pagination" aria-label="公开记录分页">
      <button
        type="button"
        disabled={offset === 0}
        onClick={() => onPage(Math.max(0, offset - limit))}
      >
        上一页
      </button>
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + limit, total)} / ${total}`
          : '0 条'}
      </span>
      <button
        type="button"
        disabled={offset + limit >= total}
        onClick={() => onPage(offset + limit)}
      >
        下一页
      </button>
    </nav>
  )
}
