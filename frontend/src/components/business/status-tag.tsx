import { Check } from 'lucide-react'

const STATUS_LABELS: Record<string, string> = {
  queued: '等待处理',
  pending: '等待处理',
  running: '正在处理',
  retry_wait: '等待重试',
  cancel_requested: '正在取消',
  succeeded: '已完成',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  draft: '待确认',
  confirmed: '已确认',
  submitted: '已提交',
  verified: '引擎已验证',
  unverified: '待引擎验证',
  pending_verification: '待引擎验证',
}
interface StatusTagProps {
  status: string
}
export default function StatusTag({ status }: StatusTagProps) {
  const tone = [
    'succeeded',
    'completed',
    'confirmed',
    'submitted',
    'verified',
  ].includes(status)
    ? 'success'
    : status === 'failed'
      ? 'danger'
      : ['running', 'retry_wait', 'cancel_requested'].includes(status)
        ? 'working'
        : 'neutral'
  return (
    <span className={`status-tag ${tone}`}>
      {tone === 'success' ? (
        <Check size={12} />
      ) : (
        <span className="status-dot" />
      )}
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
