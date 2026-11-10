import { expect, it } from 'vitest';
import { relativeDate } from './ui';

it('shows database UTC timestamps in Shanghai time consistently', () => {
  expect(relativeDate('2026-11-10T05:21:58')).toContain('13:21');
  expect(relativeDate('2026-11-10T05:21:58Z')).toBe(relativeDate('2026-11-10T05:21:58'));
});
