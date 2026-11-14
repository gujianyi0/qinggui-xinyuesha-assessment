import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** Format a copy for reading; the stored excerpt/hash remains the original. */
export default function SourceExcerpt({ text, code = false }: { text: string; code?: boolean }) {
  if (code) return <div className="source-excerpt source-code" tabIndex={0} aria-label="引用代码"><pre><code>{text}</code></pre></div>;
  // Chinese source headings occasionally omit the space after the marker.
  const readable = text.replace(/\r\n?/g, '\n').replace(/^(#{1,6})(?=\p{Script=Han})/gmu, '$1 ');
  return <div className="source-excerpt" tabIndex={0} aria-label="引用原文">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
      h1: ({ children }) => <h4>{children}</h4>,
      h2: ({ children }) => <h4>{children}</h4>,
      h3: ({ children }) => <h5>{children}</h5>,
      h4: ({ children }) => <h5>{children}</h5>,
      h5: ({ children }) => <h6>{children}</h6>,
      h6: ({ children }) => <h6>{children}</h6>,
      table: ({ children }) => <div className="source-table" tabIndex={0} aria-label="引用表格"><table>{children}</table></div>,
      a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
      // Reading a quote must not load third-party tracking images.
      img: ({ alt }) => <span className="source-image-label">{alt ? `图示：${alt}` : '图示'}</span>,
    }}>{readable}</Markdown>
    <details className="source-original"><summary>查看原始文本</summary><pre>{text}</pre></details>
  </div>;
}
