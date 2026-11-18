import type { KeyboardEvent, ReactNode } from 'react'
import { useEffect, useRef } from 'react'

interface DialogProps {
  children: ReactNode
  onClose: () => void
  className?: string
  labelledBy?: string
  label?: string
  isDismissable?: boolean
}
const FOCUSABLE =
  'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

export default function Dialog({
  children,
  onClose,
  className,
  labelledBy,
  label,
  isDismissable = true,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    if (typeof node.showModal === 'function') node.showModal()
    else node.setAttribute('open', '')
    node.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    return () => {
      if (typeof node.close === 'function' && node.open) node.close()
      if (previous?.isConnected) previous.focus()
    }
  }, [])
  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      if (isDismissable) onClose()
      return
    }
    if (event.key !== 'Tab') return
    const elements = [
      ...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE),
    ]
    const first = elements[0],
      last = elements.at(-1)
    if (!first) {
      event.preventDefault()
      return
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
  return (
    <dialog
      ref={ref}
      className={className}
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-label={label}
      onCancel={(event) => {
        event.preventDefault()
        if (isDismissable) onClose()
      }}
      onKeyDown={handleKeyDown}
      onClick={(event) => {
        const r = event.currentTarget.getBoundingClientRect()
        if (
          event.target === event.currentTarget &&
          (event.clientX < r.left ||
            event.clientX > r.right ||
            event.clientY < r.top ||
            event.clientY > r.bottom) &&
          isDismissable
        )
          onClose()
      }}
    >
      {children}
    </dialog>
  )
}
