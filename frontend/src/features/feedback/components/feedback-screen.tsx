import {
  ArrowRight,
  Check,
  ClipboardCheck,
  FilePenLine,
  FileText,
  Info,
  Plus,
  Save,
  Send,
  X,
} from 'lucide-react'
import type { FormEvent } from 'react'
import { useState } from 'react'
import StatusTag from '@/components/business/status-tag'
import { EmptyState, ErrorNotice, Spinner } from '@/components/ui'
import Dialog from '@/components/ui/dialog'
import { focusTextControlSurface } from '@/components/ui/input-surface'
import { handleTabNavigation } from '@/components/ui/tab-navigation'
import { relativeDate } from '@/lib/date-time'
import { useQuery, useQueryClient } from '@/lib/query'
import { ApiError, displayError } from '@/services/api'
import {
  confirmDraft,
  listDrafts,
  listFeedback,
  saveDraft,
} from '@/services/feedback'
import type { Draft, DraftInput, Feedback } from '@/types/domain'

interface FeedbackScreenProps {
  userId?: string
  token: string
  sessionId: string | null
  initialActual?: string
  onViewShared?: () => void
}
const blankDraft = (sessionId: string | null, actual = ''): DraftInput => ({
  ...(sessionId ? { session_id: sessionId } : {}),
  category: 'rules',
  actual,
  expected: '',
  steps: '',
  context: '',
  platform: '',
  client_version: '',
})
const fieldLabels: Record<string, string> = {
  actual: '实际现象',
  expected: '预期结果',
  steps: '复现步骤',
  context: '局面与条件',
  platform: '平台',
  client_version: '客户端版本',
}
function draftFields(draft: Draft): DraftInput {
  return {
    session_id: draft.session_id,
    category: draft.category,
    actual: draft.actual ?? '',
    expected: draft.expected ?? '',
    steps: draft.steps ?? '',
    context: draft.context ?? '',
    platform: draft.platform ?? '',
    client_version: draft.client_version ?? '',
  }
}

export default function FeedbackScreen({
  userId = 'test-workspace',
  token,
  sessionId,
  initialActual = '',
  onViewShared,
}: FeedbackScreenProps) {
  const client = useQueryClient()
  const draftsKey = ['feedback-drafts', userId],
    feedbackKey = ['feedback', userId]
  const draftsQuery = useQuery({
    queryKey: draftsKey,
    queryFn: ({ signal }) => listDrafts({ token, signal }),
  })
  const feedbackQuery = useQuery({
    queryKey: feedbackKey,
    queryFn: ({ signal }) => listFeedback({ token, signal }),
  })
  const drafts = draftsQuery.data ?? [],
    feedback = feedbackQuery.data ?? []
  const setDrafts = (handleFieldChange: (previous: Draft[]) => Draft[]) =>
    client.setQueryData<Draft[]>(draftsKey, (previous) =>
      handleFieldChange(previous ?? []),
    )
  const setFeedback = (
    handleFieldChange: (previous: Feedback[]) => Feedback[],
  ) =>
    client.setQueryData<Feedback[]>(feedbackKey, (previous) =>
      handleFieldChange(previous ?? []),
    )
  const isLoading = draftsQuery.isPending || feedbackQuery.isPending
  const load = () =>
    Promise.allSettled([draftsQuery.refetch(), feedbackQuery.refetch()])
  const [selected, setSelected] = useState<Draft | null>(null)
  const [form, setForm] = useState<DraftInput>(() =>
    blankDraft(sessionId, initialActual),
  )
  const [isBusy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [view, setView] = useState<'drafts' | 'submitted'>('drafts')
  const hasChanges = selected
    ? JSON.stringify(draftFields(selected)) !== JSON.stringify(form)
    : true
  const isConfirmed =
    selected && ['confirmed', 'submitted'].includes(selected.status)
  function handleChooseDraft(draft: Draft) {
    setSelected(draft)
    setForm(draftFields(draft))
    setNotice('')
    setError('')
    setShowConfirm(false)
  }
  function handleNewDraft() {
    setSelected(null)
    setForm(blankDraft(sessionId))
    setError('')
    setNotice('')
    setView('drafts')
  }
  async function handleSave(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const draft = await saveDraft({ token, draft: selected, form })
      setSelected(draft)
      setForm(draftFields(draft))
      setDrafts((current) => [
        draft,
        ...current.filter((item) => item.id !== draft.id),
      ])
      setNotice('草稿已保存，核对内容后再确认提交')
    } catch (error) {
      setError(displayError(error))
    } finally {
      setBusy(false)
    }
  }
  async function handleConfirm() {
    if (!selected || hasChanges || isBusy) return
    setBusy(true)
    setError('')
    try {
      const result = await confirmDraft({
        token,
        draftId: selected.id,
        revision: selected.revision,
      })
      const confirmed = { ...selected, status: 'confirmed' }
      setSelected(confirmed)
      setDrafts((current) =>
        current.map((item) => (item.id === selected.id ? confirmed : item)),
      )
      setFeedback((current) => [
        result,
        ...current.filter((item) => item.id !== result.id),
      ])
      setShowConfirm(false)
      setNotice(`反馈已保存，记录编号 ${result.id}`)
    } catch (error) {
      setError(
        error instanceof ApiError && error.status === 409
          ? '草稿版本已变化，请重新选择并核对最新内容后确认'
          : displayError(error),
      )
      setShowConfirm(false)
      if (error instanceof ApiError && error.status === 409) await load()
    } finally {
      setBusy(false)
    }
  }
  function handleFieldChange<K extends keyof DraftInput>(
    key: K,
    value: DraftInput[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }))
    setNotice('')
  }

  return (
    <section className="standard-page feedback-page">
      <div className="page-heading">
        <div>
          <span className="section-kicker">让问题更容易被理解和复现</span>
          <h1>我的反馈</h1>
          <p>先整理现象与条件，核对草稿后，再由你确认保存</p>
          {onViewShared && (
            <button
              type="button"
              className="text-button"
              onClick={onViewShared}
            >
              查看公开反馈 <ArrowRight size={14} />
            </button>
          )}
        </div>
        <button
          type="button"
          className="button secondary"
          onClick={handleNewDraft}
        >
          <Plus size={16} />
          新建反馈
        </button>
      </div>
      {(error || draftsQuery.error || feedbackQuery.error) && (
        <ErrorNotice
          message={
            error || displayError(draftsQuery.error || feedbackQuery.error)
          }
          onRetry={() => void load()}
          onDismiss={() => setError('')}
        />
      )}
      {notice && (
        <div className="success-notice" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      <div className="feedback-layout">
        <aside className="feedback-list-panel">
          <div
            className="tab-row compact-tabs"
            role="tablist"
            onKeyDown={handleTabNavigation}
            aria-label="反馈列表"
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === 'drafts'}
              tabIndex={view === 'drafts' ? 0 : -1}
              className={view === 'drafts' ? 'active' : ''}
              onClick={() => setView('drafts')}
            >
              草稿<span>{drafts.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'submitted'}
              tabIndex={view === 'submitted' ? 0 : -1}
              className={view === 'submitted' ? 'active' : ''}
              onClick={() => setView('submitted')}
            >
              已提交<span>{feedback.length}</span>
            </button>
          </div>
          {isLoading ? (
            <div className="panel-loading">
              <Spinner />
            </div>
          ) : view === 'drafts' ? (
            drafts.length ? (
              <div className="draft-list">
                {drafts.map((draft) => (
                  <button
                    type="button"
                    key={draft.id}
                    className={selected?.id === draft.id ? 'selected' : ''}
                    onClick={() => handleChooseDraft(draft)}
                  >
                    <div>
                      <code>
                        {draft.short_code} · v{draft.revision}
                      </code>
                      <StatusTag status={draft.status} />
                    </div>
                    <strong>{draft.actual || '待补充的问题现象'}</strong>
                    <span>
                      {draft.category === 'rules' ? '结算与规则' : '客户端体验'}
                      <ArrowRight size={13} />
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                title="还没有草稿"
                detail="描述遇到的问题，保存第一份反馈草稿"
              />
            )
          ) : feedback.length ? (
            <div className="submitted-list">
              {feedback.map((item) => (
                <article key={item.id}>
                  <ClipboardCheck size={18} />
                  <div>
                    <strong>
                      {item.payload?.actual || item.actual || '已确认反馈'}
                    </strong>
                    <small>记录 {item.id}</small>
                    {item.created_at && (
                      <time>{relativeDate(item.created_at)}</time>
                    )}
                  </div>
                  <Check size={14} />
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="还没有提交记录"
              detail="草稿经你明确确认后，会保存在这里"
            />
          )}
        </aside>
        <div className="feedback-editor">
          <div className="editor-heading">
            <span className="editor-icon">
              <FilePenLine size={22} />
            </span>
            <div>
              <h2>
                {selected
                  ? `反馈草稿 ${selected.short_code}`
                  : '把发生的事情说清楚'}
              </h2>
              <p>
                {selected
                  ? `修订 v${selected.revision}${hasChanges && !isConfirmed ? ' · 有未保存修改' : ''}`
                  : '不确定的信息可以留空，草稿会提示还缺少什么'}
              </p>
            </div>
            {selected && <StatusTag status={selected.status} />}
          </div>
          <form onSubmit={(e) => void handleSave(e)} className="feedback-form">
            <fieldset disabled={isBusy || Boolean(isConfirmed)}>
              <legend className="sr-only">反馈内容</legend>
              <label
                className="form-field"
                onMouseDown={focusTextControlSurface}
              >
                <span className="form-label">问题类型</span>
                <select
                  id="feedback-category"
                  value={form.category}
                  onChange={(e) =>
                    handleFieldChange(
                      'category',
                      e.target.value as DraftInput['category'],
                    )
                  }
                >
                  <option value="rules">技能结算与规则异常</option>
                  <option value="client">客户端与操作体验</option>
                </select>
              </label>
              <label
                className="form-field"
                onMouseDown={focusTextControlSurface}
              >
                <span className="form-label">
                  实际现象<span>发生了什么</span>
                </span>
                <textarea
                  id="feedback-actual"
                  rows={3}
                  value={form.actual}
                  onChange={(e) => handleFieldChange('actual', e.target.value)}
                  placeholder="例如：使用火杀后，另一名连环角色的伤害与预期不同…"
                  maxLength={8000}
                  required
                />
              </label>
              <label
                className="form-field"
                onMouseDown={focusTextControlSurface}
              >
                <span className="form-label">
                  预期结果<span>你原本认为会怎样</span>
                </span>
                <textarea
                  id="feedback-expected"
                  rows={2}
                  value={form.expected}
                  onChange={(e) =>
                    handleFieldChange('expected', e.target.value)
                  }
                  placeholder="可以写下判断依据；还不确定时也可以说明"
                  maxLength={8000}
                />
              </label>
              <label
                className="form-field"
                onMouseDown={focusTextControlSurface}
              >
                <span className="form-label">
                  复现步骤<span>按发生顺序记录</span>
                </span>
                <textarea
                  id="feedback-steps"
                  rows={3}
                  value={form.steps}
                  onChange={(e) => handleFieldChange('steps', e.target.value)}
                  placeholder="1. 进入某模式\n2. 准备武将、装备与状态\n3. 执行操作并观察结果"
                  maxLength={8000}
                />
              </label>
              <label
                className="form-field"
                onMouseDown={focusTextControlSurface}
              >
                <span className="form-label">局面与补充条件</span>
                <textarea
                  id="feedback-context"
                  rows={2}
                  value={form.context}
                  onChange={(e) => handleFieldChange('context', e.target.value)}
                  placeholder="武将、体力、手牌、装备、阶段、连环状态等"
                  maxLength={8000}
                />
              </label>
              <div className="form-grid">
                <label
                  className="form-field"
                  onMouseDown={focusTextControlSurface}
                >
                  <span className="form-label">平台</span>
                  <input
                    id="feedback-platform"
                    value={form.platform}
                    onChange={(e) =>
                      handleFieldChange('platform', e.target.value)
                    }
                    placeholder="Android / iOS / PC"
                    maxLength={120}
                  />
                </label>
                <label
                  className="form-field"
                  onMouseDown={focusTextControlSurface}
                >
                  <span className="form-label">客户端版本</span>
                  <input
                    id="feedback-version"
                    value={form.client_version}
                    onChange={(e) =>
                      handleFieldChange('client_version', e.target.value)
                    }
                    placeholder="如 0.5.25 / 本地修改版"
                    maxLength={120}
                  />
                </label>
              </div>
            </fieldset>
            {selected?.missing_fields?.length ? (
              <div className="missing-info">
                <Info size={16} />
                <div>
                  <strong>尚缺少这些信息</strong>
                  <p>
                    {selected.missing_fields
                      .map((field) => fieldLabels[field] ?? field)
                      .join('、')}
                  </p>
                </div>
              </div>
            ) : null}
            <div className="editor-actions">
              <span>
                <FileText size={13} />
                {isConfirmed ? '此草稿已经确认保存' : '保存草稿后仍需明确确认'}
              </span>
              <div>
                {!isConfirmed && (
                  <>
                    <button
                      className="button secondary"
                      type="submit"
                      disabled={
                        isBusy ||
                        !form.actual.trim() ||
                        Boolean(selected && !hasChanges)
                      }
                    >
                      {isBusy ? (
                        <Spinner label="处理中" />
                      ) : (
                        <>
                          <Save size={15} />
                          {selected ? '保存修改' : '保存草稿'}
                        </>
                      )}
                    </button>
                    <button
                      className="button primary"
                      type="button"
                      onClick={() => setShowConfirm(true)}
                      disabled={!selected || hasChanges || isBusy}
                      title={hasChanges ? '先保存修改，再核对确认' : undefined}
                    >
                      <Send size={15} />
                      核对并确认
                    </button>
                  </>
                )}
                {isConfirmed && (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => setView('submitted')}
                  >
                    <ClipboardCheck size={16} />
                    查看提交记录
                  </button>
                )}
              </div>
            </div>
          </form>
        </div>
      </div>
      {showConfirm && selected && (
        <Dialog
          className="confirmation-dialog"
          labelledBy="confirmation-title"
          onClose={() => setShowConfirm(false)}
          isDismissable={!isBusy}
        >
          <div className="dialog-heading">
            <div className="editor-icon">
              <ClipboardCheck size={22} />
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label="关闭确认窗口"
              onClick={() => setShowConfirm(false)}
              disabled={isBusy}
            >
              <X size={18} />
            </button>
          </div>
          <span className="section-kicker">最后核对一次</span>
          <h2 id="confirmation-title">确认保存这份反馈？</h2>
          <p className="muted">
            草稿 {selected.short_code} · 修订 v{selected.revision}
          </p>
          <div className="confirmation-summary">
            <span>实际现象</span>
            <p>{selected.actual}</p>
            <span>预期结果</span>
            <p>{selected.expected || '尚未填写'}</p>
            <span>复现步骤</span>
            <p>{selected.steps || '尚未填写'}</p>
          </div>
          {selected.missing_fields?.length ? (
            <p className="confirmation-note">
              仍有缺失信息，将按当前草稿保留标记
            </p>
          ) : null}
          <div className="dialog-actions">
            <button
              type="button"
              data-initial-focus
              className="button secondary"
              onClick={() => setShowConfirm(false)}
              disabled={isBusy}
            >
              返回检查
            </button>
            <button
              type="button"
              className="button primary"
              onClick={() => void handleConfirm()}
              disabled={isBusy}
            >
              {isBusy ? (
                <Spinner label="保存中" />
              ) : (
                <>
                  <Check size={16} />
                  确认保存反馈
                </>
              )}
            </button>
          </div>
        </Dialog>
      )}
    </section>
  )
}
