import { ArrowDown, ArrowUp, BookOpen, Check, ChevronDown, Clipboard, Compass, CornerDownLeft, FilePenLine, Info, MessageCircle, MoonStar, ShieldCheck, Square, Swords, UserRound } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { displayError, forgetSubmission, listResult, lookupSubmission, pendingSubmission, request, streamRun } from '../api';
import type { Citation, Message, Session, Snapshot } from '../types';
import { CitationList, ErrorNotice, Spinner } from './ui';
import { focusTextControlSurface } from './inputSurface';

interface Props {
  userId?: string; token: string; sessionId: string | null; onCreate: (title: string) => Promise<Session>;
  snapshots: Snapshot[]; snapshotId: string; onSnapshotChange: (id: string) => void;
  mockMode: boolean; onFeedback: (actual: string) => void;
}
const prompts = [
  { icon: BookOpen, label: '查清一条规则', text: '新月杀身份模式中，主公和忠臣的获胜条件是什么？', tag: '规则问答' },
  { icon: Swords, label: '核对复杂结算', text: '请帮我核对酒火杀、藤甲、白银狮子与连环的伤害结算，需要补充哪些局面条件？', tag: '技能交互' },
  { icon: Compass, label: '找武将与卡牌', text: '诸葛亮有哪些技能？请给出技能说明与来源。', tag: '结构化查询' },
  { icon: FilePenLine, label: '整理一个问题', text: '我遇到了疑似技能结算异常，想整理一份可复现的反馈。', tag: '玩家反馈' },
];

export default function Chat({ userId = 'test-workspace', token, sessionId, onCreate, snapshots, snapshotId, onSnapshotChange, mockMode, onFeedback }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');
  const [cancelRequested, setCancelRequested] = useState(false);
  const [pending, setPending] = useState<ReturnType<typeof pendingSubmission>>(null);
  useEffect(() => {
    const refresh = () => setPending(sessionId ? pendingSubmission(userId, sessionId) : null);
    refresh(); window.addEventListener('qinggui-pending-changed', refresh);
    return () => window.removeEventListener('qinggui-pending-changed', refresh);
  }, [userId, sessionId]);
  const [copied, setCopied] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const runId = useRef<string | null>(null);
  const busyRef = useRef(false);
  const activeSession = useRef<string | null>(sessionId);
  const generation = useRef(0);

  useEffect(() => {
    const question = sessionStorage.getItem('qinggui-next-question');
    if (question) { setInput(question); sessionStorage.removeItem('qinggui-next-question'); }
    return () => {
      generation.current += 1; controller.current?.abort('detach');
    };
  }, [token]);

  useEffect(() => {
    if (busyRef.current && activeSession.current === sessionId) return;
    if (busyRef.current) {
      generation.current += 1; controller.current?.abort('detach');
      runId.current = null; busyRef.current = false; setBusy(false);
    }
    let ignore = false;
    setError(''); setProgress('');
    if (!sessionId) { setMessages([]); setLoading(false); return; }
    setLoading(true);
    request<Message[] | { items: Message[] }>(`/sessions/${encodeURIComponent(sessionId)}/messages`, token)
      .then(result => { if (!ignore) setMessages(listResult(result)); })
      .catch(error => { if (!ignore) setError(displayError(error)); })
      .finally(() => { if (!ignore) setLoading(false); });
    return () => { ignore = true; };
  }, [sessionId, token]);

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [messages, progress]);

  async function reload() {
    if (!sessionId || busy) return;
    setLoading(true); setError('');
    try { setMessages(listResult(await request<Message[] | { items: Message[] }>(`/sessions/${encodeURIComponent(sessionId)}/messages`, token))); }
    catch (error) { setError(displayError(error)); }
    finally { setLoading(false); }
  }

  async function send(event?: FormEvent, recovering = false) {
    event?.preventDefault();
    const saved = recovering && sessionId ? pendingSubmission(userId, sessionId) : null;
    const message = saved?.message || input.trim();
    if (!message || busyRef.current || loading) return;
    busyRef.current = true; setBusy(true); setError(''); setCancelRequested(false); setProgress('正在提交问题');
    const currentGeneration = ++generation.current;
    const currentController = new AbortController(); controller.current = currentController; runId.current = null;
    const assistantId = `answer-${crypto.randomUUID()}`;
    let terminal = false;
    try {
      const id = sessionId || (await onCreate(message.slice(0, 28))).id;
      if (saved) {
        try {
          const found = await lookupSubmission(id, saved.request_id, token, currentController.signal);
          if (found.status !== 'running') {
            forgetSubmission(userId, id);
            setMessages(listResult(await request<Message[] | { items: Message[] }>(`/sessions/${encodeURIComponent(id)}/messages`, token)));
            setProgress('已恢复上次请求结果'); return;
          }
        } catch (error) { if (!(error instanceof Error && 'status' in error && error.status === 404)) throw error; }
      }
      activeSession.current = id;
      if (currentGeneration !== generation.current) return;
      setInput('');
      setMessages(current => [...current, ...(saved && current.at(-1)?.role === 'user' && current.at(-1)?.content === message ? [] : [{ id: `question-${crypto.randomUUID()}`, role: 'user', content: message, citations: [] }]), { id: assistantId, role: 'assistant', content: '', citations: [] }]);
      await streamRun(id, message, saved?.snapshot_id ?? snapshotId, token, currentController.signal, ({ event, data }) => {
        if (currentGeneration !== generation.current) return;
        const update = (patch: Partial<Message>) => setMessages(current => current.map(item => item.id === assistantId ? { ...item, ...patch } : item));
        if (event === 'started') { runId.current = String(data.run_id); setProgress('正在理解问题'); }
        if (event === 'progress') setProgress(String(data.message ?? data.text ?? data.stage ?? '正在核对资料'));
        if (event === 'delta') {
          setProgress('正在组织回答');
          setMessages(current => current.map(item => item.id === assistantId ? { ...item, content: item.content + String(data.text ?? '') } : item));
        }
        if (event === 'citations') update({ citations: (data.items ?? []) as Citation[] });
        if (event === 'completed') {
          terminal = true; runId.current = null; setProgress('');
          setMessages(current => current.map(item => item.id === assistantId ? { ...item, content: typeof data.text === 'string' ? data.text : item.content, citations: (data.citations ?? item.citations) as Citation[] } : item));
        }
        if (event === 'failed') { terminal = true; runId.current = null; setProgress(''); setError(`${String(data.error ?? '本次回答未完成')}${data.retryable ? '，可以重试' : ''}`); }
        if (event === 'cancelled') { terminal = true; runId.current = null; setProgress('回答已取消'); }
      }, userId);
      if (!terminal) setError('回答连接提前结束，请刷新记录核对最终状态');
    } catch (error) {
      if (currentGeneration === generation.current && !(error instanceof Error && error.name === 'AbortError')) setError(displayError(error));
    } finally {
      if (currentGeneration === generation.current) { busyRef.current = false; setBusy(false); controller.current = null; if (!terminal) setProgress(''); }
    }
  }

  async function cancel() {
    setCancelRequested(true);
    try {
      if (runId.current) await request(`/runs/${encodeURIComponent(runId.current)}/cancel`, token, { method: 'POST' });
      controller.current?.abort(); runId.current = null; setProgress('回答已取消');
    } catch (error) { setError(displayError(error)); setCancelRequested(false); }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
  }

  async function copy(message: Message) {
    try { await navigator.clipboard.writeText(message.content); setCopied(message.id); window.setTimeout(() => setCopied(null), 1800); }
    catch { setError('未能复制，请选择文本后复制'); }
  }

  const latestAnswer = [...messages].reverse().find(item => item.role === 'assistant' && item.citations?.length);
  const lastQuestion = [...messages].reverse().find(item => item.role === 'user')?.content ?? '';

  return <div className="chat-layout">
    <section className="chat-main" aria-label="问答工作台">
      <div className="chat-toolbar"><div><span className="section-kicker">有据可循</span><h1>问答工作台</h1></div><div className="snapshot-control"><BookOpen size={14} /><label className="sr-only" htmlFor="chat-snapshot">资料快照</label><select id="chat-snapshot" value={snapshotId} onChange={e => onSnapshotChange(e.target.value)} disabled={busy || !snapshots.length}>{!snapshots.length && <option value="">等待资料导入</option>}{snapshots.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown size={13} /></div></div>
      <div className="chat-scroll">
        {loading ? <div className="loading-messages" aria-label="加载会话记录"><div className="skeleton skeleton-short" /><div className="skeleton" /><div className="skeleton" /><div className="skeleton skeleton-medium" /></div> : !messages.length ? <div className="chat-welcome"><div className="welcome-moon"><MoonStar size={43} strokeWidth={1.2} /><span /></div><div className="eyebrow">你好，我是轻归</div><h2>把疑问交给我，<br className="mobile-break" /><span>一起查清依据</span></h2><p>规则、卡牌、技能结算，或一个待整理的问题<br />我会保留出处，也会说明还缺少哪些条件</p><div className="prompt-grid">{prompts.map(item => <button key={item.tag} className="prompt-card" onClick={() => { setInput(item.text); inputRef.current?.focus(); }}><span className="prompt-icon"><item.icon size={19} strokeWidth={1.5} /></span><span className="prompt-tag">{item.tag}</span><strong>{item.label}</strong><span className="prompt-description">{item.text}</span><ArrowUp size={15} className="prompt-arrow" /></button>)}</div><div className="welcome-boundary"><ShieldCheck size={14} />复杂裁定仅针对已验证快照与明确条件</div></div> : <div className="message-list">{messages.map(item => <article className={`message message-${item.role}`} key={item.id} aria-label={item.role === 'user' ? '你的问题' : '轻归的回答'}><span className={`message-avatar ${item.role === 'user' ? 'user' : ''}`}>{item.role === 'user' ? <UserRound size={17} /> : <MoonStar size={19} />}</span><div className="message-body"><div className="message-author">{item.role === 'user' ? '你' : '轻归'}{item.role !== 'user' && <span>新月助手</span>}</div><div className="message-text">{item.content || (busy && item.id.startsWith('answer-') ? <Spinner label={progress || '正在准备回答'} /> : <span className="muted">本次没有生成完整回答，可查看请求状态或重试</span>)}</div>{item.role !== 'user' && <><CitationList items={item.citations ?? []} compact /><div className="message-actions">{item.content && <button className="text-button" onClick={() => void copy(item)}>{copied === item.id ? <Check size={13} /> : <Clipboard size={13} />}{copied === item.id ? '已复制' : '复制回答'}</button>}</div></>}</div></article>)}<div ref={endRef} /></div>}
      </div>
      <div className="composer-region">{pending && !busy && <div className="mock-notice">有一条待核对的原请求。恢复会沿用原编号，不会重新计费。<button className="text-button" type="button" disabled={loading} onClick={() => void send(undefined, true)}>恢复原请求</button></div>}{error && <ErrorNotice message={error} onRetry={() => void reload()} onDismiss={() => setError('')} />}{progress && !busy && <p className="composer-status" role="status">{progress}</p>}{mockMode && <div className="mock-notice"><Info size={13} />当前为模型替身验证，回答不代表真实模型效果</div>}<form className="composer" onMouseDown={focusTextControlSurface} onSubmit={e => void send(e)}><label className="sr-only" htmlFor="chat-message">输入问题</label><textarea id="chat-message" ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder="问一条规则，或描述你遇到的具体局面…" rows={2} maxLength={8000} disabled={busy} /><div className="composer-bottom"><span><MessageCircle size={13} />基于当前资料快照回答</span>{busy ? <button type="button" className="send-button cancel-button" onClick={() => void cancel()} disabled={cancelRequested} aria-label="取消回答"><Square size={14} />{cancelRequested ? '取消中' : '停止'}</button> : <button type="submit" className="send-button" disabled={!input.trim() || loading} aria-label="发送问题"><ArrowUp size={18} /></button>}</div></form><div className="composer-hint"><span><CornerDownLeft size={11} />Enter 发送 · Shift + Enter 换行</span><span>请勿填写账号密码等私人信息</span></div></div>
    </section>
    <aside className="context-rail" aria-label="问答依据与提示"><div className="rail-heading"><span className="eyebrow">CONTEXT</span><h2>回答的依据</h2><p>让结论经得起回看</p></div>{latestAnswer?.citations?.length ? <CitationList items={latestAnswer.citations} /> : <div className="rail-placeholder"><div className="source-illustration"><BookOpen size={32} strokeWidth={1} /><span /><span /></div><h3>来源会在这里出现</h3><p>提问后，可展开查看引用的资料片段、文件位置与快照版本</p></div>}<div className="rail-divider" /><div className="rail-checklist"><span className="section-kicker">一个好问题，包含这些</span><p><Check size={14} />使用的版本与游戏模式</p><p><Check size={14} />涉及的武将、卡牌与状态</p><p><Check size={14} />动作顺序与希望确认的结果</p></div><button className="feedback-invitation" onClick={() => onFeedback(lastQuestion)}><FilePenLine size={20} /><span><strong>遇到了不符合预期的情况？</strong><small>整理为反馈草稿，再确认提交</small></span><ArrowDown size={15} /></button><div className="rail-note"><ShieldCheck size={15} /><p>资料不足时会明确说明<br />尚未验证的结算不会标成已验证</p></div></aside>
  </div>;
}
