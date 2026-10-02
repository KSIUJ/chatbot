import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import { exhaustedUsage, formatResetTime, parseChatDisabled, parseRateLimit, parseUsage } from './usage';

const RESET = '2026-10-02T22:00:00+00:00';

describe('parseUsage', () => {
  it('reads the /usage body', () => {
    expect(parseUsage({ used: 3, limit: 10, reset_at: RESET })).toMatchObject({ used: 3, limit: 10, resetAt: RESET });
  });

  it('keeps null as unlimited', () => {
    expect(parseUsage({ used: 7, limit: null, reset_at: RESET })).toMatchObject({ used: 7, limit: null, resetAt: RESET });
  });

  it('rejects malformed bodies', () => {
    expect(parseUsage(null)).toBeNull();
    expect(parseUsage({ used: '3', limit: 10, reset_at: RESET })).toBeNull();
    expect(parseUsage({ used: 3, limit: 10 })).toBeNull();
    expect(parseUsage({ used: 3, limit: 10, reset_at: 'yesterday' })).toBeNull();
    expect(parseUsage({ used: -1, limit: 10, reset_at: RESET })).toBeNull();
  });
});

describe('parseRateLimit', () => {
  const detail = { code: 'rate_limited', message: 'limit', limit: 10, reset_at: RESET };

  it('reads limit and reset time from a 429 rate_limited error', () => {
    const error = new ApiRequestError(429, null, detail, '7200');

    expect(parseRateLimit(error)).toEqual({ limit: 10, resetAt: RESET });
  });

  it('falls back to Retry-After when the body has no reset time', () => {
    const now = new Date('2026-10-02T20:00:00Z');
    const error = new ApiRequestError(429, null, { code: 'rate_limited', limit: 5 }, '120');

    expect(parseRateLimit(error, now)).toEqual({ limit: 5, resetAt: '2026-10-02T20:02:00.000Z' });
  });

  it('ignores other errors', () => {
    expect(parseRateLimit(new ApiRequestError(429, null, { code: 'something_else' }, null))).toBeNull();
    expect(parseRateLimit(new ApiRequestError(500, null, detail, null))).toBeNull();
    expect(parseRateLimit(new TypeError('Failed to fetch'))).toBeNull();
  });

  it('ignores a 429 without a usable reset time', () => {
    expect(parseRateLimit(new ApiRequestError(429, null, { code: 'rate_limited', limit: 5 }, null))).toBeNull();
    expect(parseRateLimit(new ApiRequestError(429, null, { code: 'rate_limited', limit: 5 }, 'soon'))).toBeNull();
  });
});

describe('exhaustedUsage', () => {
  it('marks the whole limit as used', () => {
    expect(exhaustedUsage({ limit: 10, resetAt: RESET })).toEqual({
      used: 10,
      limit: 10,
      resetAt: RESET,
      chatEnabled: true,
      chatDisabledMessage: null,
    });
  });
});

describe('formatResetTime', () => {
  const now = new Date('2026-10-02T12:00:00Z');

  it('shows only the time for a reset within a day', () => {
    expect(formatResetTime(RESET, 'pl', now, 'Europe/Warsaw')).toBe('00:00');
    expect(formatResetTime(RESET, 'en', now, 'UTC')).toBe('10:00 PM');
  });

  it('adds the date when the reset is further away', () => {
    const later = '2026-10-05T22:00:00+00:00';

    const text = formatResetTime(later, 'en', now, 'UTC');

    expect(text).toContain('10:00 PM');
    expect(text).toContain('Oct');
  });

  it('returns an empty string for an invalid date', () => {
    expect(formatResetTime('not a date', 'pl', now, 'UTC')).toBe('');
  });
});

describe('chat availability', () => {
  it('reads the kill switch from /usage', () => {
    expect(parseUsage({ used: 1, limit: 10, reset_at: RESET, chat_enabled: false, chat_disabled_message: 'Awaria' }))
      .toMatchObject({ chatEnabled: false, chatDisabledMessage: 'Awaria' });
  });

  it('treats a missing switch (older backend) as enabled', () => {
    expect(parseUsage({ used: 1, limit: 10, reset_at: RESET })).toMatchObject({
      chatEnabled: true,
      chatDisabledMessage: null,
    });
  });

  it('maps a 503 chat_disabled error to the admin message (null = default text)', () => {
    const custom = new ApiRequestError(503, null, { code: 'chat_disabled', message: 'x', admin_message: 'Awaria' }, null);
    const plain = new ApiRequestError(503, null, { code: 'chat_disabled', message: 'x', admin_message: null }, null);

    expect(parseChatDisabled(custom)).toEqual({ adminMessage: 'Awaria' });
    expect(parseChatDisabled(plain)).toEqual({ adminMessage: null });
  });

  it('ignores other 503s and other errors', () => {
    expect(parseChatDisabled(new ApiRequestError(503, 'provider_unavailable', { code: 'provider_unavailable' }, null))).toBeNull();
    expect(parseChatDisabled(new ApiRequestError(500, null, { code: 'chat_disabled' }, null))).toBeNull();
    expect(parseChatDisabled(new TypeError('Failed to fetch'))).toBeNull();
  });
});
