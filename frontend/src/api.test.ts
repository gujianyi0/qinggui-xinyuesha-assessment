import { describe, expect, it } from 'vitest';
import { readEventStream } from './api';
import type { StreamEvent } from './types';

describe('SSE transport', () => {
  it('preserves Chinese text across byte, CRLF and JSON boundaries', async () => {
    const bytes = new TextEncoder().encode(': heartbeat\r\n\r\nevent: delta\r\ndata: {"text":"诸葛亮"}\r\n\r\nevent: completed\ndata: {"run_id":"r1"}\n\n');
    const received: StreamEvent[] = [];
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
      controller.close();
    } });
    await readEventStream(stream, event => received.push(event));
    expect(received).toEqual([{ event: 'delta', data: { text: '诸葛亮' } }, { event: 'completed', data: { run_id: 'r1' } }]);
  });

  it('rejects malformed event payloads', async () => {
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
      controller.enqueue(new TextEncoder().encode('event: delta\ndata: []\n\n')); controller.close();
    } });
    await expect(readEventStream(stream, () => undefined)).rejects.toThrow('无法识别');
  });
});
