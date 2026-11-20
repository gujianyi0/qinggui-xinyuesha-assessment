import type { Citation } from '@/types/domain'

const mockLabel = '【模型替身演示，非真实模型结果】'
const mockAttributeLine = '\\r?\\n数据：[ \\t]*\\{[^\\r\\n]*\\}(?=\\r?$)'

export function answerCitations(
  content: string,
  citations: Citation[] = [],
): Citation[] {
  if (
    !content.startsWith(mockLabel) ||
    !new RegExp(mockAttributeLine, 'm').test(content)
  ) {
    return citations
  }
  // Old mock answers listed the rule, card construction, and deck configuration together.
  return citations.filter((source) => {
    if (
      source.evidence_type !== 'implementation' ||
      source.id.endsWith(':deck-spec')
    )
      return true
    const sameSnapshot = citations.filter(
      (item) => item.snapshot_id === source.snapshot_id,
    )
    return !(
      sameSnapshot.some((item) => item.id === `${source.id}:deck-spec`) &&
      sameSnapshot.some(
        (item) =>
          item.title === source.title &&
          item.evidence_type === 'skill_description' &&
          item.excerpt,
      )
    )
  })
}

/** Presentation only: stored answers and citation evidence remain untouched. */
export function answerText(
  content: string,
  citations: Citation[] = [],
): string {
  const sourceNames = new Map<string, Set<string>>()
  for (const item of citations) {
    const titles = sourceNames.get(item.path) ?? new Set<string>()
    if (item.title) titles.add(item.title)
    sourceNames.set(item.path, titles)
  }
  const readableSource = (path: string) => {
    const titles = sourceNames.get(path.replace(/:\d+(?:[-–]\d+)?$/, ''))
    const title = titles?.size === 1 ? [...titles][0] : undefined
    return title ? `《${title}》` : '来源资料'
  }
  const body = content.startsWith(mockLabel)
    ? content.replace(new RegExp(mockAttributeLine, 'gm'), '')
    : content
  return (
    body
      .replace(/\*\*/g, '')
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/`([^`\n]+)`/g, '$1')
      // Only source locations, never arbitrary player paths or game numbers.
      .replace(
        /\b(?:runtime\/(?:packages|lua)|rulings\/(?:evidence|scenarios)|data)\/(?:[\w.-]+\/)*[\w.-]+\.(?:lua|md|json|jsonl|txt)(?::\d+(?:[-–]\d+)?)?/g,
        readableSource,
      )
  )
}
