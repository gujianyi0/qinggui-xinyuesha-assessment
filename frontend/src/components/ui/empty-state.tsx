import { BookOpen } from 'lucide-react'

interface EmptyStateProps {
  title: string
  detail: string
}
export default function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-symbol">
        <BookOpen size={26} strokeWidth={1.4} />
      </div>
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  )
}
