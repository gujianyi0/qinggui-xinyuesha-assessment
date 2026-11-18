import type { KeyboardEvent } from 'react'

/** Roving keyboard selection for the two independently rendered tab panels. */
export function handleTabNavigation(event: KeyboardEvent<HTMLElement>) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  const tabs = [
    ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
      '[role="tab"]:not([disabled])',
    ),
  ]
  if (!(event.target instanceof HTMLButtonElement)) return
  const current = tabs.indexOf(event.target)
  if (current < 0 || !tabs.length) return
  event.preventDefault()
  const index =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? tabs.length - 1
        : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) %
          tabs.length
  tabs[index]?.focus()
  tabs[index]?.click()
}
