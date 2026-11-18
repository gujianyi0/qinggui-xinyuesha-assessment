import MarkdownDocument from '@/lib/markdown/markdown-document'

interface SourceExcerptProps {
  text: string
  code?: boolean
}
/** Format a copy for reading; the stored excerpt/hash remains the original. */
export default function SourceExcerpt({
  text,
  code = false,
}: SourceExcerptProps) {
  if (code)
    return (
      <section className="source-excerpt source-code" aria-label="引用代码">
        <pre>
          <code>{text}</code>
        </pre>
      </section>
    )
  // Chinese source headings occasionally omit the space after the marker.
  const readable = text
    .replace(/\r\n?/g, '\n')
    .replace(/^(#{1,6})(?=\p{Script=Han})/gmu, '$1 ')
  return (
    <section className="source-excerpt" aria-label="引用原文">
      <MarkdownDocument text={readable} />
      <details className="source-original">
        <summary>查看原始文本</summary>
        <pre>{text}</pre>
      </details>
    </section>
  )
}
