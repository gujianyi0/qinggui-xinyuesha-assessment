import {
  ChevronRight,
  LogOut,
  MessageCircle,
  MoonStar,
  Plus,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { relativeDate } from '@/lib/date-time'
import { isPublicMode } from '@/lib/runtime-config'
import type { Session, User } from '@/types/domain'
import type { Page } from '../navigation'
import { NAVIGATION } from '../navigation'

export interface WorkspaceDestination {
  page: Page
  sessionId?: string | null
}
interface WorkspaceSidebarProps {
  user: User
  sessions: Session[]
  page: Page
  selected: string | null
  isMobile: boolean
  onNavigate: (destination: WorkspaceDestination) => void
  onClose: () => void
  onLogout: () => void
}
export default function WorkspaceSidebar({
  user,
  sessions,
  page,
  selected,
  isMobile,
  onNavigate,
  onClose,
  onLogout,
}: WorkspaceSidebarProps) {
  const [historyFilter, setHistoryFilter] = useState('')
  const [historyLimit, setHistoryLimit] = useState(30)
  const filteredSessions = sessions.filter((session) =>
    session.title
      .toLocaleLowerCase()
      .includes(historyFilter.toLocaleLowerCase()),
  )
  const visibleSessions = filteredSessions.slice(0, historyLimit)
  return (
    <aside className="sidebar">
      {isMobile && (
        <button
          type="button"
          data-initial-focus
          className="icon-button drawer-close"
          aria-label="关闭导航"
          onClick={() => onClose()}
        >
          <X size={20} />
        </button>
      )}
      <button
        type="button"
        className="brand brand-button"
        onClick={() => {
          onNavigate({ page: 'chat', sessionId: null })
        }}
      >
        <span className="brand-mark">
          <MoonStar size={25} strokeWidth={1.4} />
        </span>
        <span>
          轻归<small>新月杀 · 资料与反馈</small>
        </span>
        <span className="brand-badge">LAB</span>
      </button>
      <button
        type="button"
        className="new-chat-button"
        onClick={() => {
          onNavigate({ page: 'chat', sessionId: null })
        }}
      >
        <Plus size={18} />
        开始新对话<span>＋</span>
      </button>
      <div className="nav-label">工作区</div>
      <nav className="primary-nav" aria-label="主要导航">
        {NAVIGATION.filter((item) => !isPublicMode || item.id !== 'jobs').map(
          (item) => (
            <button
              type="button"
              key={item.id}
              className={page === item.id ? 'active' : ''}
              onClick={() => onNavigate({ page: item.id })}
              aria-current={page === item.id ? 'page' : undefined}
            >
              <item.icon size={18} strokeWidth={1.6} />
              <span>{item.label}</span>
              {page === item.id && <ChevronRight size={14} />}
            </button>
          ),
        )}
      </nav>
      <div className="history-heading">
        <span className="nav-label">最近对话</span>
        <span>{sessions.length}</span>
      </div>
      <label className="history-search">
        <span className="sr-only">搜索历史对话</span>
        <input
          type="search"
          aria-label="搜索历史对话"
          placeholder="查找历史对话"
          value={historyFilter}
          onChange={(event) => {
            setHistoryFilter(event.target.value)
            setHistoryLimit(30)
          }}
        />
      </label>
      <div className="session-list">
        {visibleSessions.length ? (
          visibleSessions.map((session) => (
            <button
              type="button"
              key={session.id}
              className={
                selected === session.id && page === 'chat' ? 'selected' : ''
              }
              onClick={() => {
                onNavigate({ page: 'chat', sessionId: session.id })
              }}
              title={session.title}
            >
              <MessageCircle size={14} />
              <span>
                {session.title || '未命名对话'}
                <small>{relativeDate(session.created_at)}</small>
              </span>
            </button>
          ))
        ) : (
          <p className="sidebar-empty">
            {historyFilter ? '没有匹配的历史对话' : '新的疑问，值得好好聊聊'}
          </p>
        )}
        {filteredSessions.length > historyLimit && (
          <button
            type="button"
            className="text-button history-more"
            onClick={() => setHistoryLimit((current) => current + 30)}
          >
            显示更多（剩余 {filteredSessions.length - historyLimit} 条）
          </button>
        )}
      </div>
      <div className="sidebar-bottom">
        <div className="scope-card">
          <ShieldCheck size={17} />
          <div>
            独立身份 · 独立记录
            <p>当前工作区属于 {user.username}</p>
          </div>
        </div>
        <div className="account-row">
          <span className={`avatar avatar-${user.username}`}>
            {user.username[0]?.toUpperCase()}
          </span>
          <span>
            {user.username}
            <small>{isPublicMode ? '独立访客身份' : '本地测试身份'}</small>
          </span>
          <button
            type="button"
            className="icon-button"
            onClick={onLogout}
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  )
}
