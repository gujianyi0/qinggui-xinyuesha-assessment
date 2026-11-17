import type { MouseEvent } from 'react'
import { createElement } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownDocumentProps {
  text: string
  variant?: 'reference' | 'document'
  resolveHref?: (href: string) => string | undefined
  onLink?: (href: string) => boolean
}
export default function MarkdownDocument({
  text,
  variant = 'reference',
  resolveHref,
  onLink,
}: MarkdownDocumentProps) {
  return createElement(
    Markdown,
    {
      remarkPlugins: [remarkGfm],
      skipHtml: true,
      components: {
        h1: ({ children }) =>
          createElement(variant === 'document' ? 'h1' : 'h4', null, children),
        h2: ({ children }) =>
          createElement(variant === 'document' ? 'h2' : 'h4', null, children),
        h3: ({ children }) =>
          createElement(variant === 'document' ? 'h3' : 'h5', null, children),
        h4: ({ children }) =>
          createElement(variant === 'document' ? 'h4' : 'h5', null, children),
        h5: ({ children }) =>
          createElement(variant === 'document' ? 'h5' : 'h6', null, children),
        h6: ({ children }) => createElement('h6', null, children),
        table: ({ children }) =>
          createElement(
            'section',
            {
              className: 'source-table',
              'aria-label': variant === 'document' ? '文档表格' : '引用表格',
            },
            createElement('table', null, children),
          ),
        a: ({ href, children }) => {
          const resolved = href && resolveHref ? resolveHref(href) : href
          return createElement(
            'a',
            {
              href: resolved,
              target:
                variant === 'reference' || /^https?:/.test(href || '')
                  ? '_blank'
                  : undefined,
              rel: 'noreferrer',
              onClick: (event: MouseEvent<HTMLAnchorElement>) => {
                if (
                  !event.ctrlKey &&
                  !event.metaKey &&
                  !event.shiftKey &&
                  !event.altKey &&
                  event.button === 0 &&
                  resolved &&
                  onLink?.(resolved)
                )
                  event.preventDefault()
              },
            },
            children,
          )
        },
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
