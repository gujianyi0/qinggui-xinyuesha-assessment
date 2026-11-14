import type { Citation } from '../types';

/** Presentation only: stored answers and citation evidence remain untouched. */
export function answerText(content: string, citations: Citation[] = []): string {
  const sourceNames = new Map<string, Set<string>>();
  for (const item of citations) {
    const titles = sourceNames.get(item.path) ?? new Set<string>();
    if (item.title) titles.add(item.title);
    sourceNames.set(item.path, titles);
  }
  const readableSource = (path: string) => {
    const titles = sourceNames.get(path.replace(/:\d+(?:[-–]\d+)?$/, ''));
    const title = titles?.size === 1 ? [...titles][0] : undefined;
    return title ? `《${title}》` : '来源资料';
  };
  return content
    .replace(/\*\*/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/`([^`\n]+)`/g, '$1')
    // Only source locations, never arbitrary player paths or game numbers.
    .replace(/\b(?:runtime\/(?:packages|lua)|rulings\/(?:evidence|scenarios)|data)\/(?:[\w.\-]+\/)*[\w.\-]+\.(?:lua|md|json|jsonl|txt)(?::\d+(?:[-–]\d+)?)?/g, readableSource);
}
