import type { ReactNode } from 'react'
import { createElement } from 'react'
import { ErrorBoundary } from 'react-error-boundary'
import ScreenError from '@/components/shared/screen-error'

interface ScreenBoundaryProps {
  children: ReactNode
  resetKey: string
}
export default function ScreenBoundary({
  children,
  resetKey,
}: ScreenBoundaryProps) {
  return createElement(
    ErrorBoundary,
    {
      resetKeys: [resetKey],
      fallbackRender: ({ resetErrorBoundary }) =>
        createElement(ScreenError, { onRetry: resetErrorBoundary }),
    },
    children,
  )
}
