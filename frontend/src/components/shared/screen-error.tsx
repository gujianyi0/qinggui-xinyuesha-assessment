import { AlertCircle } from 'lucide-react'

interface ScreenErrorProps {
  onRetry: () => void
}
export default function ScreenError({ onRetry }: ScreenErrorProps) {
  return (
    <section className="screen-error" role="alert">
      <AlertCircle size={30} />
      <h1>这个页面暂时没能打开</h1>
      <p>已保存的记录仍在。可以重新加载本页，或切换到其他页面。</p>
      <button type="button" className="button primary" onClick={onRetry}>
        重新加载页面
      </button>
    </section>
  )
}
