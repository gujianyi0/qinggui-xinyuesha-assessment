import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FeedbackPanel from './Feedback';

afterEach(() => vi.unstubAllGlobals());

it('edits a stored draft using its revision without changing session ownership', async () => {
  const draft = { id: 'draft-1', short_code: 'AABB1122', revision: 1, status: 'draft', session_id: 'session-1', category: 'rules', actual: '技能没有生效', expected: '', steps: '', context: '', platform: '', client_version: '', missing_fields: [] };
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith('/feedback-drafts') && !options?.method) return new Response(JSON.stringify([draft]), { status: 200 });
    if (options?.method === 'PATCH') return new Response(JSON.stringify({ ...draft, expected: '正常结算', revision: 2 }), { status: 200 });
    return new Response('[]', { status: 200 });
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<FeedbackPanel token="test" sessionId="session-1" />);
  fireEvent.click(await screen.findByText('技能没有生效'));
  fireEvent.change(screen.getByLabelText(/预期结果/), { target: { value: '正常结算' } });
  fireEvent.click(screen.getByRole('button', { name: '保存修改' }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(true));
  const [, options] = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!;
  const payload = JSON.parse(String(options?.body));
  expect(payload).toMatchObject({ revision: 1, expected: '正常结算' });
  expect(payload).not.toHaveProperty('session_id');
});
