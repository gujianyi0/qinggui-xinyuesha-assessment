import { ArrowRight, CheckCircle2, Clock3, Database, FileStack, History, Layers3, RefreshCw, Square } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { displayError, listResult, request } from '../api';
import type { Job, Snapshot } from '../types';
import { EmptyState, ErrorNotice, relativeDate, Spinner, StatusTag } from './ui';

const activeStatuses = ['queued', 'pending', 'running', 'retry_wait', 'cancel_requested'];
function progressOf(job: Job): number {
  if (['succeeded', 'completed'].includes(job.status)) return 100;
  if (typeof job.progress === 'number') return Math.max(0, Math.min(100, job.progress <= 1 ? job.progress * 100 : job.progress));
  const record = job.progress ?? {};
  const current = Number(record.current ?? record.completed ?? record.processed ?? 0);
  const total = Number(record.total ?? 0);
  return total > 0 ? Math.max(0, Math.min(100, current / total * 100)) : 0;
}

export default function JobsPanel({ token, snapshots, snapshotId }: { token: string; snapshots: Snapshot[]; snapshotId: string }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedSnapshot, setSelectedSnapshot] = useState(snapshotId);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [error, setError] = useState('');
  const submissionKey = useRef<string | null>(null);
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try { setJobs(listResult(await request<Job[] | { items: Job[] }>('/jobs', token))); }
    catch (error) { setError(displayError(error)); }
    finally { if (!silent) setLoading(false); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!selectedSnapshot && snapshotId) setSelectedSnapshot(snapshotId); }, [snapshotId, selectedSnapshot]);
  const activeCount = jobs.filter(job => activeStatuses.includes(job.status)).length;
  useEffect(() => {
    if (!activeCount) return;
    const interval = window.setInterval(() => { void load(true); }, 3000);
    return () => clearInterval(interval);
  }, [activeCount, load]);
  async function submit() {
    if (!selectedSnapshot || submitting) return;
    setSubmitting(true); setError('');
    submissionKey.current ??= crypto.randomUUID();
    try {
      const job = await request<Job>('/jobs', token, { method: 'POST', body: JSON.stringify({ snapshot_id: selectedSnapshot, idempotency_key: submissionKey.current }) });
      setJobs(current => [job, ...current.filter(item => item.id !== job.id)]); submissionKey.current = null;
    } catch (error) { setError(displayError(error)); }
    finally { setSubmitting(false); }
  }
  async function cancel(job: Job) {
    setCancelling(job.id); setError('');
    try {
      const updated = await request<Job>(`/jobs/${encodeURIComponent(job.id)}/cancel`, token, { method: 'POST' });
      setJobs(current => current.map(item => item.id === job.id ? updated : item));
    } catch (error) { setError(displayError(error)); }
    finally { setCancelling(null); }
  }
  return <section className="standard-page jobs-page"><div className="page-heading"><div><span className="section-kicker">耗时处理，也能看清进度</span><h1>后台任务</h1><p>导入指定资料快照，查看状态、结果和失败原因</p></div><button className="button secondary" onClick={() => { setError(''); void load(); }} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} />刷新记录</button></div>{error && <ErrorNotice message={error} onDismiss={() => setError('')} />}
    <div className="import-panel"><div className="import-intro"><div className="overview-icon"><Layers3 size={28} strokeWidth={1.4} /></div><div><span className="eyebrow">KNOWLEDGE PIPELINE</span><h2>更新可检索的游戏资料</h2><p>解析来源 → 提取结构化数据 → 生成向量 → 发布完整快照</p></div></div><div className="import-controls"><label htmlFor="import-snapshot">选择资料快照</label><select id="import-snapshot" value={selectedSnapshot} onChange={e => { setSelectedSnapshot(e.target.value); submissionKey.current = null; }} disabled={submitting}>{!snapshots.length && <option value="">还没有可导入的快照</option>}{snapshots.map(snapshot => <option key={snapshot.id} value={snapshot.id}>{snapshot.label}</option>)}</select><button className="button primary" onClick={() => void submit()} disabled={submitting || !selectedSnapshot}>{submitting ? <Spinner label="正在提交" /> : <><Database size={15} />开始导入<ArrowRight size={15} /></>}</button></div><div className="import-footnote"><Clock3 size={13} />任务在后台运行，你可以离开本页；取消会在当前处理步骤结束后生效</div></div>
    <div className="jobs-summary"><div><span className="summary-icon"><FileStack size={18} /></span><strong>{jobs.length}</strong><span>任务记录</span></div><div><span className="summary-icon active"><Clock3 size={18} /></span><strong>{activeCount}</strong><span>进行中</span></div><div><span className="summary-icon complete"><CheckCircle2 size={18} /></span><strong>{jobs.filter(job => ['succeeded', 'completed'].includes(job.status)).length}</strong><span>已完成</span></div></div>
    <div className="section-title-row"><h2><History size={17} />任务记录</h2><span>{activeCount ? '每 3 秒更新状态' : '当前没有运行中的任务'}</span></div>
    {loading ? <div className="panel-loading"><Spinner label="加载任务记录" /></div> : !jobs.length ? <EmptyState title="还没有后台任务" detail="选择已配置的资料快照，开始第一次导入" /> : <div className="job-list">{jobs.map(job => <article className="job-card" key={job.id}><div className="job-card-top"><div className="job-kind-icon"><Database size={20} strokeWidth={1.4} /></div><div><h3>资料导入与索引</h3><p className="mono">{job.id}</p></div><StatusTag status={job.status} /></div><div className="job-progress"><div className="job-progress-track" role="progressbar" aria-label={`任务 ${job.id} 进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressOf(job))}><span style={{ width: `${progressOf(job)}%` }} /></div><span>{Math.round(progressOf(job))}%</span></div><div className="job-metadata"><span>尝试 <strong>{job.attempts}</strong> 次</span><span>{relativeDate(job.created_at)}</span>{activeStatuses.includes(job.status) && job.status !== 'cancel_requested' && <button className="text-button" disabled={cancelling === job.id} onClick={() => void cancel(job)}>{cancelling === job.id ? <Spinner label="取消中" /> : <><Square size={11} />取消任务</>}</button>}</div>{job.error && <div className="job-error"><strong>处理说明</strong><p>{job.error}</p></div>}{job.result != null && <details className="job-result"><summary>查看任务结果</summary><pre>{typeof job.result === 'string' ? job.result : JSON.stringify(job.result, null, 2)}</pre></details>}{job.status === 'cancelled' && <p className="muted job-cancel-note">任务已取消；已经完成的调用费用等副作用仍会保留记录</p>}</article>)}</div>}
  </section>;
}
