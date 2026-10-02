import { describe, expect, it } from 'vitest';
import { formatBytes, formatDateTime, formatDuration, formatLatency, personLabel, usageLabel } from './format';

describe('formatBytes', () => {
  it('uses binary units with one decimal above KiB', () => {
    expect(formatBytes(512, 'en')).toBe('512 B');
    expect(formatBytes(1536, 'en')).toBe('1.5 KB');
    expect(formatBytes(5 * 1024 ** 3, 'en')).toBe('5 GB');
    expect(formatBytes(1536, 'pl')).toBe('1,5 KB');
  });
});

describe('formatDuration', () => {
  it('shows the two largest units', () => {
    expect(formatDuration(42)).toBe('42 s');
    expect(formatDuration(3 * 60 + 5)).toBe('3 min 5 s');
    expect(formatDuration(2 * 3600 + 15 * 60 + 9)).toBe('2 h 15 min');
    expect(formatDuration(3 * 86400 + 4 * 3600)).toBe('3 d 4 h');
  });
});

describe('formatLatency', () => {
  it('shows milliseconds below a second and seconds above', () => {
    expect(formatLatency(null, 'en')).toBe('—');
    expect(formatLatency(340.4, 'en')).toBe('340 ms');
    expect(formatLatency(2500, 'en')).toBe('2.5 s');
  });
});

describe('formatDateTime', () => {
  it('formats in the given locale and zone; invalid dates give a dash', () => {
    expect(formatDateTime('2026-10-02T10:05:00Z', 'pl', 'UTC')).toContain('10:05');
    expect(formatDateTime(null, 'pl')).toBe('—');
    expect(formatDateTime('nope', 'pl')).toBe('—');
  });
});

describe('personLabel', () => {
  it('prefers the name, then login, then e-mail', () => {
    expect(personLabel({ name: 'Anna', username: 'anna', email: 'a@x' })).toBe('Anna');
    expect(personLabel({ name: null, username: 'anna', email: 'a@x' })).toBe('anna');
    expect(personLabel({ name: null, username: null, email: 'a@x' })).toBe('a@x');
    expect(personLabel({ name: null, username: null, email: null })).toBe('');
  });
});

describe('usageLabel', () => {
  it('shows used / limit, or just the count without a limit', () => {
    expect(usageLabel(3, 10)).toBe('3 / 10');
    expect(usageLabel(3, null)).toBe('3 / ∞');
  });
});
