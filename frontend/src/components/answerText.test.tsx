import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { answerText } from './answerText';
import { CitationList } from './ui';

const source = { id:'caocao', title:'曹操', path:'runtime/packages/standard/pkg/init.lua',
  line_start:17, line_end:21, snapshot_id:'fixed-snapshot', evidence_type:'implementation', excerpt:'体力4，技能奸雄、护驾。' };

it('shows readable facts while keeping source positions in the evidence object', () => {
  const content = '**结论：曹操体力4。**\n## 依据\n来自 `runtime/packages/standard/pkg/init.lua:17–21`。';
  const saved = JSON.stringify(source);
  const text = answerText(content,[source]);
  expect(text).toBe('结论：曹操体力4。\n依据\n来自 《曹操》。');
  expect(JSON.stringify(source)).toBe(saved);
  expect(content).toContain('**'); // Original stored text stays intact.
});

it('hides source paths during streaming before citations arrive, without changing facts or player paths', () => {
  expect(answerText('SC03：伤害2，当前3/上限4。runtime/packages/maneuvering/pkg/skills/fire_attack.lua'))
    .toBe('SC03：伤害2，当前3/上限4。来源资料');
  expect(answerText('错误日志在 C:\\Games\\client.log；技能标识 jianxiong，快照0.5.25。'))
    .toBe('错误日志在 C:\\Games\\client.log；技能标识 jianxiong，快照0.5.25。');
});

it('does not attribute a shared source file to the last cited skill', () => {
  expect(answerText(source.path,[source,{...source,id:'another',title:'护驾'}])).toBe('来源资料');
});

it('opens complete source evidence only from the answer-end button and can close it again', () => {
  render(<CitationList items={[source]} compact />);
  const button=screen.getByRole('button',{name:'查看来源 1：曹操'});
  expect(button).toHaveAttribute('aria-expanded','false');
  expect(screen.queryByText(/runtime\/packages/)).not.toBeInTheDocument();
  fireEvent.click(button);
  const detail=screen.getByRole('region',{name:'来源 1详情'});
  expect(detail).toHaveTextContent('runtime/packages/standard/pkg/init.lua:17–21');
  expect(detail).toHaveTextContent('fixed-snapshot');
  expect(detail).toHaveTextContent('体力4，技能奸雄、护驾。');
  expect(button).toHaveAttribute('aria-controls',detail.id);
  fireEvent.click(button);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
});
