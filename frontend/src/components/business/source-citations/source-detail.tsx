import { FileText } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { Spinner } from '@/components/ui'
import type { Citation } from '@/types/domain'
import { sourceLabel } from './source-labels'

const SourceExcerpt = lazy(() => import('@/components/shared/source-excerpt'))
interface SourceDetailProps {
  source: Citation
  number: number
  id: string
}
export default function SourceDetail({
  source,
  number,
  id,
}: SourceDetailProps) {
  return (
    <section
      className="citation-detail"
      id={id}
      aria-label={`来源 ${number}详情`}
    >
      <div className="source-detail-heading">
        <strong>{source.title || `资料 ${number}`}</strong>
        <span>{sourceLabel(source.evidence_type)}</span>
      </div>
      <div className="source-metadata">
        <p>
          <FileText size={12} />
          <span>
            {source.path}
            {source.line_start
              ? `:${source.line_start}${source.line_end && source.line_end !== source.line_start ? `–${source.line_end}` : ''}`
              : ''}
          </span>
        </p>
        <p>
          资料快照 <span className="mono">{source.snapshot_id}</span>
        </p>
      </div>
      {source.excerpt && (
        <Suspense fallback={<Spinner label="正在排版原文" />}>
          <SourceExcerpt
            text={source.excerpt}
            code={['implementation', 'code'].includes(
              source.evidence_type ?? '',
            )}
          />
        </Suspense>
      )}
    </section>
  )
}
