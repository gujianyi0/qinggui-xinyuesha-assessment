import { BookOpen } from 'lucide-react'
import { useId, useState } from 'react'
import type { Citation } from '@/types/domain'
import SourceButton from './source-button'
import SourceDetail from './source-detail'

interface CitationListProps {
  items: Citation[]
  compact?: boolean
  onInteract?: () => void
}
export default function CitationList({
  items,
  compact = false,
  onInteract,
}: CitationListProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const id = useId()
  if (!items.length) return null
  const active = items.findIndex(
    (item, index) => expanded === `${item.id}-${index}`,
  )
  function handleToggle(key: string) {
    onInteract?.()
    setExpanded((current) => (current === key ? null : key))
  }
  return (
    <div className={`citation-list ${compact ? 'compact' : ''}`}>
      <div className="eyebrow citation-heading">
        <BookOpen size={13} />
        {compact ? '参考来源' : '依据与来源'} <span>{items.length}</span>
      </div>
      <div className={compact ? 'citation-buttons' : 'citation-cards'}>
        {items.map((item, index) => (
          <div
            className="citation-item"
            key={`${item.id}:${item.path}:${item.line_start ?? 0}`}
          >
            <SourceButton
              source={item}
              number={index + 1}
              detailId={`${id}-${index}`}
              isExpanded={active === index}
              isCompact={compact}
              onToggle={() => handleToggle(`${item.id}-${index}`)}
            />
            {!compact && active === index && (
              <SourceDetail
                source={item}
                number={index + 1}
                id={`${id}-${index}`}
              />
            )}
          </div>
        ))}
      </div>
      {compact && active >= 0 && (
        <SourceDetail
          source={items[active]}
          number={active + 1}
          id={`${id}-${active}`}
        />
      )}
    </div>
  )
}
