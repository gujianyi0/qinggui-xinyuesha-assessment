import { useSyncExternalStore } from 'react'

export interface QueuedQuestion {
  id: string
  message: string
  snapshotId: string
}

const changeEvent = 'qinggui-question-queue-changed'
function subscribe(onChange: () => void) {
  window.addEventListener(changeEvent, onChange)
  return () => window.removeEventListener(changeEvent, onChange)
}

export function useQuestionQueue(userId: string, sessionId: string | null) {
  const key = sessionId ? `qinggui-question-queue:${userId}:${sessionId}` : ''
  const read = () => (key ? sessionStorage.getItem(key) : null)
  const raw = useSyncExternalStore(subscribe, read, () => null)

  function update(change: (items: QueuedQuestion[]) => QueuedQuestion[]) {
    if (!key) return
    const items = change(parseQueue(read()))
    if (items.length) sessionStorage.setItem(key, JSON.stringify(items))
    else sessionStorage.removeItem(key)
    window.dispatchEvent(new Event(changeEvent))
  }

  return {
    questions: parseQueue(raw),
    enqueue: (question: QueuedQuestion) =>
      update((items) => [...items, question]),
    remove: (id: string) =>
      update((items) => items.filter((item) => item.id !== id)),
  }
}

function parseQueue(value: string | null): QueuedQuestion[] {
  if (!value) return []
  try {
    const items = JSON.parse(value)
    return Array.isArray(items) ? items : []
  } catch {
    return []
  }
}
