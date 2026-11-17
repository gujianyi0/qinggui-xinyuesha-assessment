import { ChevronRight, Menu } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import Dialog from '@/components/ui/dialog'
import Chat, { pendingSession } from '@/features/chat'
import { useMediaQuery } from '@/hooks/use-media-query'
import { useOnlineStatus } from '@/hooks/use-online-status'
import { useQuery, useQueryClient } from '@/lib/query'
import { isPublicMode } from '@/lib/runtime-config'
import ScreenBoundary from '@/lib/screen-boundary'
import { updateUrl, useUrlSearch } from '@/lib/url-state'
import { displayError } from '@/services/api'
import { getHealth, listSnapshots } from '@/services/knowledge'
import {
  createSession as createStoredSession,
  listSessions,
} from '@/services/sessions'
import type { Auth, Session } from '@/types/domain'

const Library = lazy(() => import('@/features/library'))
const FeedbackPanel = lazy(() => import('@/features/feedback'))
const JobsPanel = lazy(() => import('@/features/jobs'))

import { ErrorNotice } from '@/components/ui'
import type { Page } from '../navigation'
import { NAVIGATION } from '../navigation'
import type { WorkspaceDestination } from './workspace-sidebar'
import WorkspaceSidebar from './workspace-sidebar'

interface WorkspaceScreenProps {
  auth: Auth
  onLogout: () => void
}
export default function WorkspaceScreen({
  auth,
  onLogout,
}: WorkspaceScreenProps) {
  const params = new URLSearchParams(useUrlSearch())
  const requestedPage = params.get('page')
  const page: Page = ['library', 'feedback', 'jobs'].includes(
    requestedPage || '',
  )
    ? (requestedPage as Page)
    : 'chat'
  const requestedSession = params.get('session')
  const selected =
    requestedSession && /^[a-zA-Z0-9:_-]{1,100}$/.test(requestedSession)
      ? requestedSession
      : null
  const [feedbackActual, setFeedbackActual] = useState('')
  const [isMobileNavOpen, setMobileNavOpen] = useState(false)
  const token = auth.access_token
  const client = useQueryClient()
  const sessionQuery = useQuery({
    queryKey: ['sessions', auth.user.id],
    queryFn: ({ signal }) => listSessions({ token, signal }),
  })
  const snapshotQuery = useQuery({
    queryKey: ['snapshots', auth.user.id],
    queryFn: ({ signal }) => listSnapshots({ token, signal }),
  })
  const healthQuery = useQuery({
    queryKey: ['health', auth.user.id],
    queryFn: ({ signal }) => getHealth({ token, signal }),
  })
  const sessions = sessionQuery.data ?? []
  const snapshots = snapshotQuery.data ?? []
  const health = healthQuery.data
  const snapshotId =
    params.get('snapshot') ||
    snapshots.find((item) => item.active)?.id ||
    snapshots[0]?.id ||
    ''
  const isOnline = useOnlineStatus()
  const isMobile = useMediaQuery('(max-width:650px)')
  const isRefreshing =
    sessionQuery.isFetching ||
    snapshotQuery.isFetching ||
    healthQuery.isFetching
  const error =
    [sessionQuery.error, snapshotQuery.error, healthQuery.error]
      .filter(Boolean)
      .map(displayError)[0] || ''
  const setSelected = (id: string | null) =>
    updateUrl({ page: 'chat', session: id })
  const setSnapshotId = (id: string) => updateUrl({ snapshot: id })
  async function load() {
    await Promise.allSettled([
      sessionQuery.refetch(),
      snapshotQuery.refetch(),
      healthQuery.refetch(),
    ])
  }
  useEffect(() => {
    if (selected || page !== 'chat' || !sessionQuery.data) return
    const pending = pendingSession(auth.user.id)
    if (pending && sessionQuery.data.some((item) => item.id === pending))
      updateUrl({ session: pending }, { replace: true })
  }, [selected, page, sessionQuery.data, auth.user.id])
  useEffect(() => {
    const expire = () => onLogout()
    window.addEventListener('qinggui-auth-expired', expire)
    return () => window.removeEventListener('qinggui-auth-expired', expire)
  }, [onLogout])

  async function createSession(title: string) {
    const session = await createStoredSession({ token, title })
    client.setQueryData<Session[]>(['sessions', auth.user.id], (current) => [
      session,
      ...(current ?? []),
    ])
    setSelected(session.id)
    return session
  }
  function handleNavigate(destination: WorkspaceDestination) {
    updateUrl({
      page: destination.page,
      ...(destination.sessionId !== undefined
        ? { session: destination.sessionId }
        : {}),
    })
    setMobileNavOpen(false)
  }
  const navigate = (page: Page) => handleNavigate({ page })
  const handleNewConversation = () =>
    handleNavigate({ page: 'chat', sessionId: null })
  const sidebar = (
    <WorkspaceSidebar
      user={auth.user}
      sessions={sessions}
      page={page}
      selected={selected}
      isMobile={isMobile}
      onNavigate={handleNavigate}
      onClose={() => setMobileNavOpen(false)}
      onLogout={onLogout}
    />
  )
  const currentSnapshot = snapshots.find((item) => item.id === snapshotId)
  const isMockMode =
    health?.model_mode && /mock|stub|fake|offline/i.test(health.model_mode)

  return (
    <div className="workspace">
      <a className="skip-link" href="#workspace-content">
        跳到主要内容
      </a>
      {isMobile
        ? isMobileNavOpen && (
            <Dialog
              className="workspace-drawer"
              label="工作区导航"
              onClose={() => setMobileNavOpen(false)}
            >
              {sidebar}
            </Dialog>
          )
        : sidebar}
      <main className="workspace-main">
        <header className="workspace-header">
          <div className="breadcrumb">
            <button
              type="button"
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span>我的工作区</span>
            {isRefreshing && (
              <span
                className="refresh-indicator"
                role="status"
                aria-label="正在更新工作区"
              >
                更新中
              </span>
            )}
            <ChevronRight size={13} />
            <strong>
              {NAVIGATION.find((item) => item.id === page)?.label}
            </strong>
          </div>
          <div className="header-actions">
            <span className={`connection-label ${health ? 'connected' : ''}`}>
              <span className="status-dot" />
              {isOnline && !healthQuery.isError && health
                ? isPublicMode
                  ? '真实问答服务已连接'
                  : '本机服务已连接'
                : isOnline
                  ? '连接暂时中断'
                  : '当前离线'}
            </span>
            {isMockMode && <span className="mode-badge">模型替身模式</span>}
            <span className="preview-badge">v2.0.1 · 本地内测</span>
          </div>
        </header>
        {error && (
          <div className="global-notice">
            <ErrorNotice message={error} onRetry={() => void load()} />
          </div>
        )}
        {!isOnline && (
          <div className="offline-notice" role="status">
            网络已断开，已加载的内容仍可查看。联网后恢复更新。
          </div>
        )}
        <div className="page-content" id="workspace-content" tabIndex={-1}>
          <ScreenBoundary resetKey={page}>
            <Suspense
              fallback={
                <div className="panel-loading">
                  <Spinner label="正在打开页面" />
                </div>
              }
            >
              {page === 'chat' && (
                <Chat
                  userId={auth.user.id}
                  token={token}
                  sessionId={selected}
                  onCreate={createSession}
                  snapshots={snapshots}
                  snapshotId={snapshotId}
                  onSnapshotChange={setSnapshotId}
                  isMockMode={Boolean(isMockMode)}
                  onFeedback={(actual) => {
                    setFeedbackActual(actual)
                    navigate('feedback')
                  }}
                />
              )}
              {page === 'library' && (
                <Library
                  userId={auth.user.id}
                  token={token}
                  snapshots={snapshots}
                  snapshotId={snapshotId}
                  onSnapshotChange={setSnapshotId}
                  onAsk={(question) => {
                    handleNewConversation()
                    sessionStorage.setItem(
                      `qinggui-next-question:${auth.user.id}`,
                      question,
                    )
                  }}
                />
              )}
              {page === 'feedback' && (
                <FeedbackPanel
                  userId={auth.user.id}
                  token={token}
                  sessionId={selected}
                  initialActual={feedbackActual}
                />
              )}
              {page === 'jobs' && (
                <JobsPanel
                  userId={auth.user.id}
                  token={token}
                  snapshots={snapshots}
                  snapshotId={snapshotId}
                />
              )}
            </Suspense>
          </ScreenBoundary>
        </div>
        <footer className="workspace-footer">
          <span>
            <span className="status-dot" />
            来源可追溯 · 版本有边界
          </span>
          <span>
            {currentSnapshot?.label ?? '等待资料快照'}
            {currentSnapshot?.commit
              ? ` · ${currentSnapshot.commit.slice(0, 8)}`
              : ''}
          </span>
        </footer>
      </main>
    </div>
  )
}
