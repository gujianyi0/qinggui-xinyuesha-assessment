import { BookOpen, ChevronRight, CircleHelp, Database, FolderClock, LogOut, Menu, MessageCircle, MoonStar, Plus, ShieldCheck, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { displayError, listResult, request } from './api';
import type { Auth, Health, Session, Snapshot } from './types';
import Login from './components/Login';
import Chat from './components/Chat';
import Library from './components/Library';
import FeedbackPanel from './components/Feedback';
import JobsPanel from './components/Jobs';
import { ErrorNotice, relativeDate } from './components/ui';

const STORAGE_KEY = 'qinggui-assessment-auth';
type Page = 'chat' | 'library' | 'feedback' | 'jobs';
const navigation = [
  { id: 'chat' as const, label: '问答工作台', icon: MessageCircle, sub: '规则与结算' },
  { id: 'library' as const, label: '游戏资料库', icon: BookOpen, sub: '资料与已验证裁定' },
  { id: 'feedback' as const, label: '我的反馈', icon: FolderClock, sub: '草稿与提交记录' },
  { id: 'jobs' as const, label: '后台任务', icon: Database, sub: '资料导入与索引' },
];

function readAuth(): Auth | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null');
    return value?.access_token && value?.user?.id ? value as Auth : null;
  } catch { return null; }
}

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(readAuth);
  const login = (value: Auth) => { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value)); setAuth(value); };
  const logout = useCallback(() => { sessionStorage.removeItem(STORAGE_KEY); setAuth(null); }, []);
  return auth ? <Workspace key={auth.user.id} auth={auth} onLogout={logout} /> : <Login onLogin={login} />;
}

function Workspace({ auth, onLogout }: { auth: Auth; onLogout: () => void }) {
  const [page, setPage] = useState<Page>('chat');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState('');
  const [feedbackActual, setFeedbackActual] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const token = auth.access_token;
  const load = useCallback(async () => {
    setError('');
    const result = await Promise.allSettled([
      request<Session[] | { items: Session[] }>('/sessions', token),
      request<Snapshot[] | { items: Snapshot[] }>('/catalog/snapshots', token),
      request<Health>('/health', token),
    ]);
    if (result[0].status === 'fulfilled') setSessions(listResult(result[0].value));
    if (result[1].status === 'fulfilled') {
      const items = listResult(result[1].value); setSnapshots(items);
      setSnapshotId(current => current || items.find(item => item.active)?.id || items[0]?.id || '');
    }
    if (result[2].status === 'fulfilled') setHealth(result[2].value);
    const failure = result.find(item => item.status === 'rejected');
    if (failure?.status === 'rejected') setError(displayError(failure.reason));
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const expire = () => onLogout();
    window.addEventListener('qinggui-auth-expired', expire);
    return () => window.removeEventListener('qinggui-auth-expired', expire);
  }, [onLogout]);

  async function createSession(title: string) {
    const session = await request<Session>('/sessions', token, { method: 'POST', body: JSON.stringify({ title }) });
    setSessions(current => [session, ...current]); setSelected(session.id); return session;
  }
  const navigate = (next: Page) => { setPage(next); setMobileNav(false); };
  const currentSnapshot = snapshots.find(item => item.id === snapshotId);
  const mockMode = health?.model_mode && /mock|stub|fake|offline/i.test(health.model_mode);

  return <div className="workspace">
    {mobileNav && <button aria-label="关闭导航遮罩" className="nav-backdrop" onClick={() => setMobileNav(false)} />}
    <aside className={`sidebar ${mobileNav ? 'is-open' : ''}`}>
      <button className="brand brand-button" onClick={() => { navigate('chat'); setSelected(null); }}><span className="brand-mark"><MoonStar size={25} strokeWidth={1.4} /></span><span>轻归<small>新月杀 · 资料与反馈</small></span><span className="brand-badge">LAB</span></button>
      <button className="new-chat-button" onClick={() => { setSelected(null); navigate('chat'); }}><Plus size={18} />开始新对话<span>＋</span></button>
      <div className="nav-label">工作区</div>
      <nav className="primary-nav" aria-label="主要导航">{navigation.map(item => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => navigate(item.id)} aria-current={page === item.id ? 'page' : undefined}><item.icon size={18} strokeWidth={1.6} /><span>{item.label}</span>{page === item.id && <ChevronRight size={14} />}</button>)}</nav>
      <div className="history-heading"><span className="nav-label">最近对话</span><span>{sessions.length}</span></div>
      <div className="session-list">{sessions.length ? sessions.map(session => <button key={session.id} className={selected === session.id && page === 'chat' ? 'selected' : ''} onClick={() => { setSelected(session.id); navigate('chat'); }} title={session.title}><MessageCircle size={14} /><span>{session.title || '未命名对话'}<small>{relativeDate(session.created_at)}</small></span></button>) : <p className="sidebar-empty">新的疑问，值得好好聊聊</p>}</div>
      <div className="sidebar-bottom"><div className="scope-card"><ShieldCheck size={17} /><div>独立身份 · 独立记录<p>当前工作区属于 {auth.user.username}</p></div></div><div className="account-row"><span className={`avatar avatar-${auth.user.username}`}>{auth.user.username[0]?.toUpperCase()}</span><span>{auth.user.username}<small>本地测试身份</small></span><button className="icon-button" onClick={onLogout} aria-label="退出登录" title="退出登录"><LogOut size={16} /></button></div></div>
    </aside>
    <main className="workspace-main">
      <header className="workspace-header"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>我的工作区</span><ChevronRight size={13} /><strong>{navigation.find(item => item.id === page)?.label}</strong></div><div className="header-actions"><span className={`connection-label ${health ? 'connected' : ''}`}><span className="status-dot" />{health ? '本机服务已连接' : '等待服务连接'}</span>{mockMode && <span className="mode-badge">模型替身模式</span>}<a className="help-link" href="/api/docs" target="_blank" rel="noreferrer" title="打开 API 文档"><CircleHelp size={17} /><span>API 文档</span></a></div></header>
      {error && <div className="global-notice"><ErrorNotice message={error} onRetry={() => void load()} onDismiss={() => setError('')} /></div>}
      <div className="page-content">
        {page === 'chat' && <Chat token={token} sessionId={selected} onCreate={createSession} snapshots={snapshots} snapshotId={snapshotId} onSnapshotChange={setSnapshotId} mockMode={Boolean(mockMode)} onFeedback={actual => { setFeedbackActual(actual); navigate('feedback'); }} />}
        {page === 'library' && <Library token={token} snapshots={snapshots} snapshotId={snapshotId} onSnapshotChange={setSnapshotId} onAsk={question => { setSelected(null); navigate('chat'); sessionStorage.setItem('qinggui-next-question', question); }} />}
        {page === 'feedback' && <FeedbackPanel token={token} sessionId={selected} initialActual={feedbackActual} />}
        {page === 'jobs' && <JobsPanel token={token} snapshots={snapshots} snapshotId={snapshotId} />}
      </div>
      <footer className="workspace-footer"><span><span className="status-dot" />来源可追溯 · 版本有边界</span><span>{currentSnapshot?.label ?? '等待资料快照'}{currentSnapshot?.commit ? ` · ${currentSnapshot.commit.slice(0, 8)}` : ''}</span></footer>
    </main>
    {mobileNav && <button className="close-mobile-nav icon-button" aria-label="关闭导航" onClick={() => setMobileNav(false)}><X size={20} /></button>}
  </div>;
}
