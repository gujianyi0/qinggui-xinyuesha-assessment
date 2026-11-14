import { AlertCircle, RefreshCw } from 'lucide-react'

interface ErrorNoticeProps {
  message: string
  onRetry?: () => void
  onDismiss?: () => void
}
export default function ErrorNotice({
  message,
  onRetry,
  onDismiss,
}: ErrorNoticeProps) {
  return (
    <div className="error-notice" role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="text-button" onClick={onRetry}>
          <RefreshCw size={14} />
          重试
        </button>
      )}
      {onDismiss && (
        <button type="button" className="text-button" onClick={onDismiss}>
          关闭
        </button>
      )}
    </div>
  )
}
