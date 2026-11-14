import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Chat from './Chat';
import { streamRun } from '../api';
import type { StreamEvent } from '../types';

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  streamRun: vi.fn(async () => {}),
}));

it('keeps recovery disabled until the selected session history has loaded', async () => {
  localStorage.setItem('qinggui-pending:test-workspace:pending-session', JSON.stringify({
    request_id:'original',session_id:'pending-session',message:'原问题',snapshot_id:'test',
  }));
  let finish!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  try {
    render(<Chat token="test" sessionId="pending-session" onCreate={vi.fn()} snapshots={[]} snapshotId="test"
      onSnapshotChange={vi.fn()} mockMode onFeedback={vi.fn()} />);
    expect(screen.getByRole('button',{name:'恢复原请求'})).toBeDisabled();
    await act(async () => { finish(new Response('[]')); });
    await waitFor(() => expect(screen.getByRole('button',{name:'恢复原请求'})).toBeEnabled());
  } finally { localStorage.clear(); vi.unstubAllGlobals(); }
});

it('focuses the real textarea when the composer padding is pressed', () => {
  render(<Chat token="test" sessionId={null} onCreate={vi.fn()} snapshots={[]} snapshotId="test"
    onSnapshotChange={vi.fn()} mockMode onFeedback={vi.fn()} />);
  const input = screen.getByLabelText('输入问题');
  fireEvent.mouseDown(input.closest('form')!);
  expect(input).toHaveFocus();
});

it('cleans only assistant display text and keeps source details available at the answer end', async () => {
  const path = 'runtime/packages/standard/pkg/init.lua';
  vi.stubGlobal('fetch',vi.fn(async () => new Response(JSON.stringify([
    {id:'question',role:'user',content:`查看 ${path}`,citations:[]},
    {id:'answer',role:'assistant',content:`**曹操体力4。** 依据：\`${path}\`。`,
      citations:[{id:'source',title:'曹操',path,snapshot_id:'test',line_start:17,excerpt:'体力4。'}]},
  ]))));
  try {
    render(<Chat token="test" sessionId="history" onCreate={vi.fn()} snapshots={[]} snapshotId="test"
      onSnapshotChange={vi.fn()} mockMode={false} onFeedback={vi.fn()} />);
    const answer = await screen.findByLabelText('轻归的回答');
    expect(answer.querySelector('.message-text')).toHaveTextContent('曹操体力4。 依据：《曹操》。');
    expect(answer.querySelector('.message-text')).not.toHaveTextContent(path);
    expect(screen.getByLabelText('你的问题')).toHaveTextContent(path);
    fireEvent.click(screen.getByRole('button',{name:'查看来源 1：曹操'}));
    expect(screen.getByRole('region',{name:'来源 1详情'})).toHaveTextContent(`${path}:17`);
  } finally { vi.unstubAllGlobals(); }
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

it('stops following streamed updates while reading above the bottom and resumes at the bottom', async () => {
  let emit!: (event: StreamEvent) => void;
  let finish!: () => void;
  vi.mocked(streamRun).mockImplementationOnce(async (_s,_m,_v,_t,_signal,onEvent) => {
    emit=onEvent; await new Promise<void>(resolve=>{finish=resolve;});
  });
  const create=vi.fn(async()=>({id:'stream-scroll',title:'滚动检查',created_at:'2026-11-14'}));
  const {container}=render(<Chat token="test" sessionId={null} onCreate={create} snapshots={[]} snapshotId="test"
    onSnapshotChange={vi.fn()} mockMode={false} onFeedback={vi.fn()} />);
  const pane=container.querySelector<HTMLDivElement>('.chat-scroll')!;
  Object.defineProperties(pane,{scrollHeight:{configurable:true,value:1200},clientHeight:{configurable:true,value:300}});
  fireEvent.change(screen.getByLabelText('输入问题'),{target:{value:'介绍曹操'}});
  fireEvent.click(screen.getByRole('button',{name:'发送问题'}));
  await waitFor(()=>expect(emit).toBeTypeOf('function'));
  act(()=>emit({event:'delta',data:{text:'第一段'}}));
  expect(pane.scrollTop).toBe(1200);
  pane.scrollTop=200;fireEvent.scroll(pane);
  act(()=>emit({event:'delta',data:{text:'第二段'}}));
  expect(pane.scrollTop).toBe(200);
  pane.scrollTop=900;fireEvent.scroll(pane);
  Object.defineProperty(pane,'scrollHeight',{configurable:true,value:1300});
  act(()=>emit({event:'delta',data:{text:'第三段'}}));
  expect(pane.scrollTop).toBe(1300);
  await act(async()=>{emit({event:'completed',data:{text:'完整回答',citations:[]}});finish();});
});

it('pauses follow-to-bottom when a source is opened during streaming', async () => {
  let emit!: (event: StreamEvent) => void;
  let finish!: () => void;
  vi.mocked(streamRun).mockImplementationOnce(async (_s,_m,_v,_t,_signal,onEvent) => {
    emit=onEvent;await new Promise<void>(resolve=>{finish=resolve;});
  });
  const {container}=render(<Chat token="test" sessionId={null} onCreate={vi.fn(async()=>({id:'source-stream',title:'来源',created_at:'2026-11-14'}))}
    snapshots={[]} snapshotId="test" onSnapshotChange={vi.fn()} mockMode={false} onFeedback={vi.fn()} />);
  const pane=container.querySelector<HTMLDivElement>('.chat-scroll')!;
  Object.defineProperties(pane,{scrollHeight:{configurable:true,value:1200},clientHeight:{configurable:true,value:300}});
  fireEvent.change(screen.getByLabelText('输入问题'),{target:{value:'来源检查'}});
  fireEvent.click(screen.getByRole('button',{name:'发送问题'}));
  await waitFor(()=>expect(emit).toBeTypeOf('function'));
  act(()=>emit({event:'citations',data:{items:[{id:'source',title:'曹操',path:'source.lua',snapshot_id:'test'}]}}));
  fireEvent.click(screen.getByRole('button',{name:'查看来源 1：曹操'}));
  pane.scrollTop=400;
  act(()=>emit({event:'delta',data:{text:'新增内容'}}));
  expect(pane.scrollTop).toBe(400);
  await act(async()=>{emit({event:'completed',data:{text:'完成',citations:[]}});finish();});
});
