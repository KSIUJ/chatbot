import { describe, expect, it } from 'vitest';
import { inputHeight } from './inputHeight';

describe('inputHeight', () => {
  it('adds the border that scrollHeight leaves out', () => {
    // one line: 20px line + 2 * 12px padding, 1px border top and bottom
    expect(inputHeight(44, 2)).toBe(46);
  });

  it('never subtracts (a scrollbar or a zero border)', () => {
    expect(inputHeight(44, 0)).toBe(44);
    expect(inputHeight(44, -3)).toBe(44);
  });
});
