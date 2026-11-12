import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Chat from './Chat';

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  streamRun: vi.fn(async () => {}),
}));

it('focuses the real textarea when the composer padding is pressed', () => {
  render(<Chat token="test" sessionId={null} onCreate={vi.fn()} snapshots={[]} snapshotId="test"
    onSnapshotChange={vi.fn()} mockMode onFeedback={vi.fn()} />);
  const input = screen.getByLabelText('输入问题');
  fireEvent.mouseDown(input.closest('form')!);
  expect(input).toHaveFocus();
});

it('preserves native text selection and does not intercept right clicks', () => {
  render(<Chat token="test" sessionId={null} onCreate={vi.fn()} snapshots={[]} snapshotId="test"
    onSnapshotChange={vi.fn()} mockMode onFeedback={vi.fn()} />);
  const input = screen.getByLabelText<HTMLTextAreaElement>('输入问题');
  expect(fireEvent.mouseDown(input.closest('form')!, {button: 2})).toBe(true);
  expect(input).not.toHaveFocus();
  fireEvent.change(input, {target: {value: '保留中文输入'}});
  input.focus(); input.setSelectionRange(1, 4);
  expect(fireEvent.mouseDown(input)).toBe(true);
  expect(input.selectionStart).toBe(1);
  expect(input.selectionEnd).toBe(4);
  expect(fireEvent.mouseDown(screen.getByRole('button', {name: '发送问题'}))).toBe(true);
});

it('keeps IME and Shift+Enter from submitting, while ordinary Enter still sends', async () => {
  const create = vi.fn(async () => ({id: 'new', title: '测试', created_at: '2026-11-12T00:00:00Z'}));
  render(<Chat token="test" sessionId={null} onCreate={create} snapshots={[]} snapshotId="test"
    onSnapshotChange={vi.fn()} mockMode onFeedback={vi.fn()} />);
  const input = screen.getByLabelText('输入问题');
  fireEvent.mouseDown(input.closest('form')!);
  fireEvent.change(input, {target: {value: '中文问题'}});
  fireEvent.keyDown(input, {key: 'Enter', isComposing: true});
  fireEvent.keyDown(input, {key: 'Enter', shiftKey: true});
  expect(create).not.toHaveBeenCalled();
  fireEvent.keyDown(input, {key: 'Enter'});
  await waitFor(() => expect(create).toHaveBeenCalledExactlyOnceWith('中文问题'));
});
