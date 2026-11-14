import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import SourceExcerpt from './SourceExcerpt';

it('renders Chinese headings, paragraphs and lists without exposing formatting markers', () => {
  const text='#规则说明\n\n第一段。\n继续这一段。\n\n## 生效条件\n\n- 体力为 **3**\n- 使用【杀】\n\n1. 先判定\n2. 再结算';
  const {container}=render(<SourceExcerpt text={text} />);
  expect(screen.getByRole('heading',{name:'规则说明'})).toHaveTextContent('规则说明');
  expect(screen.getByRole('heading',{name:'生效条件'})).toBeInTheDocument();
  expect(container.querySelector('.source-excerpt>p')?.textContent).toBe('第一段。\n继续这一段。');
  expect(container.querySelectorAll('li')).toHaveLength(4);
  expect(container.querySelector('strong')).toHaveTextContent('3');
  expect(container.querySelector('.source-original pre')?.textContent).toBe(text);
});

it('renders source tables as readable table cells rather than pipe-delimited text', () => {
  render(<SourceExcerpt text={'| 人数 | 主公 |\n| --- | --- |\n| 4 | 1 |\n| 5 | 1 |'} />);
  const table=screen.getByRole('table');
  expect(within(table).getAllByRole('columnheader')).toHaveLength(2);
  expect(within(table).getAllByRole('row')).toHaveLength(3);
  expect(within(table).getByRole('cell',{name:'4'})).toBeInTheDocument();
});

it('preserves Lua operators, indentation and line breaks when the source is code', () => {
  const text='local count = #cards\n  return count > 0 and "#skill"';
  const {container}=render(<SourceExcerpt text={text} code />);
  expect(container.querySelector('pre code')?.textContent).toBe(text);
  expect(screen.getByLabelText('引用代码')).toHaveAttribute('tabindex','0');
  expect(screen.queryByRole('heading')).not.toBeInTheDocument();
});

it('does not fetch quoted images or create executable HTML from source text', () => {
  const {container}=render(<SourceExcerpt text={'![规则图](https://example.invalid/track.png)\n\n<script>alert(1)</script>\n\n[来源](javascript:alert(1))'} />);
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('a')?.getAttribute('href')).not.toContain('javascript:');
  expect(screen.getByText('图示：规则图')).toBeInTheDocument();
});
