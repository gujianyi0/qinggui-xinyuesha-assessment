import { createElement } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownDocumentProps {
  text: string
}
export default function MarkdownDocument({ text }: MarkdownDocumentProps) {
  return createElement(
    Markdown,
    {
      remarkPlugins: [remarkGfm],
      skipHtml: true,
      components: {
        h1: ({ children }) => createElement('h4', null, children),
        h2: ({ children }) => createElement('h4', null, children),
        h3: ({ children }) => createElement('h5', null, children),
        h4: ({ children }) => createElement('h5', null, children),
        h5: ({ children }) => createElement('h6', null, children),
        h6: ({ children }) => createElement('h6', null, children),
        table: ({ children }) =>
          createElement(
            'section',
            { className: 'source-table', 'aria-label': '引用表格' },
            createElement('table', null, children),
          ),
        a: ({ href, children }) =>
          createElement(
            'a',
            { href, target: '_blank', rel: 'noreferrer' },
            children,
          ),
        // Reading source text must never load remote tracking images.
        img: ({ alt }) =>
          createElement(
            'span',
            { className: 'source-image-label' },
            alt ? `图示：${alt}` : '图示',
          ),
      },
    },
    text,
  )
}
