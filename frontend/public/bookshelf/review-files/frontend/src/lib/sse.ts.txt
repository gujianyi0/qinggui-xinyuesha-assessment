import type { StreamEvent } from '@/types/domain'

/** Frames may split inside UTF-8 text, CRLF, or a JSON value. Only complete frames are emitted. */
export async function readEventStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  function consume(final = false) {
    let boundary = /\r?\n\r?\n/.exec(pending)
    while (boundary) {
      const frame = pending.slice(0, boundary.index)
      pending = pending.slice(boundary.index + boundary[0].length)
      emit(frame)
      boundary = /\r?\n\r?\n/.exec(pending)
    }
    if (final && pending.trim()) {
      emit(pending)
      pending = ''
    }
  }
  function emit(frame: string) {
    let event = 'message'
    const lines: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) lines.push(line.slice(5).trimStart())
    }
    if (!lines.length) return
    const value: unknown = JSON.parse(lines.join('\n'))
    if (!value || typeof value !== 'object' || Array.isArray(value))
      throw new Error('服务返回了无法识别的流式事件')
    onEvent({ event, data: value as Record<string, unknown> })
  }
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        pending += decoder.decode()
        consume(true)
        break
      }
      pending += decoder.decode(value, { stream: true })
      consume()
    }
  } finally {
    reader.releaseLock()
  }
}
