import { ChevronDown } from 'lucide-react'
import type { Citation } from '@/types/domain'
import { sourceLabel } from './source-labels'

interface SourceButtonProps {
  source: Citation
  number: number
  detailId: string
  isExpanded: boolean
  isCompact: boolean
  onToggle: () => void
}
export default function SourceButton({
  source,
  number,
  detailId,
  isExpanded,
  isCompact,
  onToggle,
}: SourceButtonProps) {
  return (
    <button
      type="button"
      className="citation-trigger"
      onClick={onToggle}
      aria-label={`查看来源 ${number}：${source.title || '资料'}`}
      aria-controls={detailId}
      aria-expanded={isExpanded}
    >
      <span className="citation-number">{number}</span>
      <span className="citation-name">
        {source.title || (isCompact ? `资料 ${number}` : source.path)}
        <small>{sourceLabel(source.evidence_type)}</small>
      </span>
      <ChevronDown size={14} className={isExpanded ? 'rotated' : ''} />
    </button>
  )
}
