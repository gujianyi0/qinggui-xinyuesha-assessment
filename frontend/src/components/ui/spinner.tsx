import { LoaderCircle } from 'lucide-react'

interface SpinnerProps {
  label?: string
}
export default function Spinner({ label = '加载中' }: SpinnerProps) {
  return (
    <span className="inline-loading">
      <LoaderCircle size={16} className="spin" aria-hidden="true" />
      {label}
    </span>
  )
}
