import type { MouseEvent } from 'react'

// Clicking padding around an inline native control must focus that control,
// rather than leaving the document selection before its full-height box.
export function focusTextControlSurface(event: MouseEvent<HTMLElement>) {
  if (
    event.button !== 0 ||
    event.defaultPrevented ||
    !(event.target instanceof Element)
  )
    return
  if (
    event.target.closest(
      'input,textarea,select,button,a,[contenteditable="true"],[role="button"]',
    )
  )
    return
  const label = event.target.closest('label')
  if (label && label !== event.currentTarget) return
  const control = event.currentTarget.querySelector<
    HTMLInputElement | HTMLTextAreaElement
  >('textarea,input:not([type="hidden"]):not(.sr-only)')
  if (!control || control.matches(':disabled')) return
  event.preventDefault()
  control.focus()
}
