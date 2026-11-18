import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  FileStack,
  History,
  Layers3,
  RefreshCw,
  Square,
} from 'lucide-react'
import { useRef, useState } from 'react'
import StatusTag from '@/components/business/status-tag'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import { relativeDate } from '@/lib/date-time'
import { useQuery, useQueryClient } from '@/lib/query'
import { displayError } from '@/services/api'
import { cancelJob, createJob, listJobs } from '@/services/jobs'
import type { Job, Snapshot } from '@/types/domain'

const ACTIVE_STATUSES = [
  'queued',
  'pending',
  'running',
  'retry_wait',
  'cancel_requested',
]
function progressOf(job: Job): number {
  if (['succeeded', 'completed'].includes(job.status)) return 100
  if (typeof job.progress === 'number')
    return Math.max(
      0,
      Math.min(100, job.progress <= 1 ? job.progress * 100 : job.progress),
    )
  const record = job.progress ?? {}
  const current = Number(
    record.current ?? record.completed ?? record.processed ?? 0,
  )
  const total = Number(record.total ?? 0)
  return total > 0 ? Math.max(0, Math.min(100, (current / total) * 100)) : 0
}
interface JobsScreenProps {
  userId: string
  token: string
  snapshots: Snapshot[]
  snapshotId: string
}
export default function JobsScreen({
  userId,
  token,
  snapshots,
  snapshotId,
}: JobsScreenProps) {
  const client = useQueryClient()
  const jobsKey = ['jobs', userId]
  const jobsQuery = useQuery({
    queryKey: jobsKey,
    queryFn: ({ signal }) => listJobs({ token, signal }),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((job) =>
        ACTIVE_STATUSES.includes(job.status),
      )
        ? 3000
        : false,
    refetchIntervalInBackground: false,
  })
  const jobs = jobsQuery.data ?? []
  const setJobs = (update: (previous: Job[]) => Job[]) =>
    client.setQueryData<Job[]>(jobsKey, (previous) => update(previous ?? []))
  const isLoading = jobsQuery.isPending
  const pendingKey = `qinggui-job-pending:${userId}`
  const [chosenSnapshot, setSelectedSnapshot] = useState('')
  const selectedSnapshot = chosenSnapshot || snapshotId
  const [isSubmitting, setSubmitting] = useState(false)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [error, setError] = useState('')
  const submissionKey = useRef<string | null>(null)
  const load = () => jobsQuery.refetch()
  const activeCount = jobs.filter((job) =>
    ACTIVE_STATUSES.includes(job.status),
  ).length
  async function handleSubmit() {
    if (!selectedSnapshot || isSubmitting) return
    setSubmitting(true)
    setError('')
    try {
      let pending: unknown
      try {
        pending = JSON.parse(localStorage.getItem(pendingKey) || 'null')
      } catch {
        throw new Error(
          '本地导入回执无法读取，请先核对任务记录，避免重复提交。',
        )
      }
      let savedKey: string | undefined
      if (pending !== null) {
        if (
          typeof pending !== 'object' ||
          !('snapshotId' in pending) ||
          !('key' in pending) ||
          typeof pending.key !== 'string'
        )
          throw new Error('本地导入回执损坏，请先核对任务记录，避免重复提交。')
        if (pending.snapshotId !== selectedSnapshot)
          throw new Error('上一次导入尚待核对，请切回对应快照后恢复原提交')
        savedKey = pending.key
      }
      const key = submissionKey.current ?? savedKey ?? crypto.randomUUID()
      submissionKey.current = key
      localStorage.setItem(
        pendingKey,
        JSON.stringify({ snapshotId: selectedSnapshot, key }),
      )
      const job = await createJob({
        token,
        snapshotId: selectedSnapshot,
        idempotencyKey: key,
      })
      setJobs((current) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ])
      submissionKey.current = null
      localStorage.removeItem(pendingKey)
    } catch (error) {
      setError(displayError(error))
    } finally {
      setSubmitting(false)
    }
  }
  async function handleCancel(job: Job) {
    setCancelling(job.id)
    setError('')
    try {
      const updated = await cancelJob({ token, jobId: job.id })
      setJobs((current) =>
        current.map((item) => (item.id === job.id ? updated : item)),
      )
    } catch (error) {
      setError(displayError(error))
    } finally {
      setCancelling(null)
    }
  }
  return (
    <section className="standard-page jobs-page">
      <div className="page-heading">
        <div>
          <span className="section-kicker">耗时处理，也能看清进度</span>
          <h1>后台任务</h1>
          <p>导入指定资料快照，查看状态、结果和失败原因</p>
        </div>
        <button
          type="button"
          className="button secondary"
          onClick={() => {
            setError('')
            void load()
          }}
          disabled={isLoading}
        >
          <RefreshCw size={15} className={isLoading ? 'spin' : ''} />
          刷新记录
        </button>
      </div>
      {(error || jobsQuery.error) && (
        <ErrorNotice
          message={error || displayError(jobsQuery.error)}
          onRetry={() => void load()}
          onDismiss={() => setError('')}
        />
      )}
      <div className="import-panel">
        <div className="import-intro">
          <div className="overview-icon">
            <Layers3 size={28} strokeWidth={1.4} />
          </div>
          <div>
            <span className="eyebrow">KNOWLEDGE PIPELINE</span>
            <h2>更新可检索的游戏资料</h2>
            <p>解析来源 → 提取结构化数据 → 生成向量 → 发布完整快照</p>
          </div>
        </div>
        <div className="import-controls">
          <label htmlFor="import-snapshot">选择资料快照</label>
          <select
            id="import-snapshot"
            value={selectedSnapshot}
            onChange={(e) => {
              setSelectedSnapshot(e.target.value)
              submissionKey.current = null
            }}
            disabled={isSubmitting}
          >
            {!snapshots.length && <option value="">还没有可导入的快照</option>}
            {snapshots.map((snapshot) => (
              <option key={snapshot.id} value={snapshot.id}>
                {snapshot.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button primary"
            onClick={() => void handleSubmit()}
            disabled={isSubmitting || !selectedSnapshot}
          >
            {isSubmitting ? (
              <Spinner label="正在提交" />
            ) : (
              <>
                <Database size={15} />
                开始导入
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </div>
        <div className="import-footnote">
          <Clock3 size={13} />
          任务在后台运行，你可以离开本页；取消会在当前处理步骤结束后生效
        </div>
      </div>
      <div className="jobs-summary">
        <div>
          <span className="summary-icon">
            <FileStack size={18} />
          </span>
          <strong>{jobs.length}</strong>
          <span>任务记录</span>
        </div>
        <div>
          <span className="summary-icon active">
            <Clock3 size={18} />
          </span>
          <strong>{activeCount}</strong>
          <span>进行中</span>
        </div>
        <div>
          <span className="summary-icon complete">
            <CheckCircle2 size={18} />
          </span>
          <strong>
            {
              jobs.filter((job) =>
                ['succeeded', 'completed'].includes(job.status),
              ).length
            }
          </strong>
          <span>已完成</span>
        </div>
      </div>
      <div className="section-title-row">
        <h2>
          <History size={17} />
          任务记录
        </h2>
        <span>
          {activeCount
            ? '前台每 3 秒更新 · 切到后台后暂停'
            : '当前没有运行中的任务'}
        </span>
      </div>
      {isLoading ? (
        <div className="panel-loading">
          <Spinner label="加载任务记录" />
        </div>
      ) : !jobs.length ? (
        <EmptyState
          title="还没有后台任务"
          detail="选择已配置的资料快照，开始第一次导入"
        />
      ) : (
        <div className="job-list">
          {jobs.map((job) => (
            <article className="job-card" key={job.id}>
              <div className="job-card-top">
                <div className="job-kind-icon">
                  <Database size={20} strokeWidth={1.4} />
                </div>
                <div>
                  <h3>资料导入与索引</h3>
                  <p className="mono">{job.id}</p>
                </div>
                <StatusTag status={job.status} />
              </div>
              <div className="job-progress">
                <div
                  className="job-progress-track"
                  role="progressbar"
                  aria-label={`任务 ${job.id} 进度`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(progressOf(job))}
                >
                  <span style={{ width: `${progressOf(job)}%` }} />
                </div>
                <span>{Math.round(progressOf(job))}%</span>
              </div>
              <div className="job-metadata">
                <span>
                  尝试 <strong>{job.attempts}</strong> 次
                </span>
                <span>{relativeDate(job.created_at)}</span>
                {ACTIVE_STATUSES.includes(job.status) &&
                  job.status !== 'cancel_requested' && (
                    <button
                      type="button"
                      className="text-button"
                      disabled={cancelling === job.id}
                      onClick={() => void handleCancel(job)}
                    >
                      {cancelling === job.id ? (
                        <Spinner label="取消中" />
                      ) : (
                        <>
                          <Square size={11} />
                          取消任务
                        </>
                      )}
                    </button>
                  )}
              </div>
              {job.error && (
                <div className="job-error">
                  <strong>处理说明</strong>
                  <p>{job.error}</p>
                </div>
              )}
              {job.result != null && (
                <details className="job-result">
                  <summary>查看任务结果</summary>
                  <pre>
                    {typeof job.result === 'string'
                      ? job.result
                      : JSON.stringify(job.result, null, 2)}
                  </pre>
                </details>
              )}
              {job.status === 'cancelled' && (
                <p className="muted job-cancel-note">
                  任务已取消；已经完成的调用费用等副作用仍会保留记录
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
