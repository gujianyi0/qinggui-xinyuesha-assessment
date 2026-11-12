import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Login from './components/Login';
import { request } from './api';

vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), publicMode: true, request: vi.fn() }));

it('public entry needs no owner password and reuses this browsers private visitor identity', async () => {
  localStorage.clear();
  const onLogin = vi.fn();
  vi.mocked(request).mockResolvedValue({ access_token: 'signed-guest', user: { id: 'public:one', username: '访客' } });
  render(<Login onLogin={onLogin} />);
  expect(screen.queryByLabelText('登录密码')).toBeNull();
  expect(screen.queryByRole('group', { name: '选择测试身份' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /进入工作区/ }));
  await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
  const first = JSON.parse(String(vi.mocked(request).mock.calls[0][2]?.body));
  expect(vi.mocked(request).mock.calls[0][0]).toBe('/auth/guest');
  expect(first.client_secret).toMatch(/^[a-f0-9]{64}$/);
  fireEvent.click(screen.getByRole('button', { name: /进入工作区/ }));
  await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(2));
  expect(JSON.parse(String(vi.mocked(request).mock.calls[1][2]?.body))).toEqual(first);
});
