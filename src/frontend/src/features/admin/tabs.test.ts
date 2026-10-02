import { describe, expect, it } from 'vitest';
import { tabForKey } from './tabs';

describe('tabForKey', () => {
  it('moves with arrows and wraps around', () => {
    expect(tabForKey('limits', 'ArrowRight')).toBe('reports');
    expect(tabForKey('diagnostics', 'ArrowRight')).toBe('limits');
    expect(tabForKey('limits', 'ArrowLeft')).toBe('diagnostics');
  });

  it('jumps to the ends with Home / End and ignores other keys', () => {
    expect(tabForKey('incidents', 'Home')).toBe('limits');
    expect(tabForKey('reports', 'End')).toBe('diagnostics');
    expect(tabForKey('reports', 'Enter')).toBeNull();
  });
});
