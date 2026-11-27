import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import { guestStartErrorOf, parseGuestMode } from './guest';

describe('parseGuestMode', () => {
  it('reads GET /auth/guest', () => {
    expect(parseGuestMode({ enabled: true, question_limit: 2 })).toEqual({ enabled: true, questionLimit: 2 });
  });

  it('treats a switched off mode as disabled', () => {
    expect(parseGuestMode({ enabled: false, question_limit: 2 })).toEqual({ enabled: false, questionLimit: 2 });
  });

  it('rejects malformed bodies', () => {
    expect(parseGuestMode(null)).toBeNull();
    expect(parseGuestMode({ enabled: 'yes', question_limit: 2 })).toBeNull();
    expect(parseGuestMode({ enabled: true, question_limit: 0 })).toBeNull();
    expect(parseGuestMode({ enabled: true, question_limit: 1.5 })).toBeNull();
  });
});

describe('guestStartErrorOf', () => {
  it('maps the per-address quota', () => {
    const error = new ApiRequestError(429, null, { code: 'guest_quota', message: 'x' });
    expect(guestStartErrorOf(error)).toBe('guest_quota');
  });

  it('maps the nginx rate limit (429 without a JSON body) to the quota message', () => {
    expect(guestStartErrorOf(new ApiRequestError(429, null, null))).toBe('guest_quota');
  });

  it('maps a switched off guest mode', () => {
    const error = new ApiRequestError(403, null, { code: 'guest_disabled', message: 'x' });
    expect(guestStartErrorOf(error)).toBe('guest_disabled');
  });

  it('keeps login error codes the backend sent', () => {
    expect(guestStartErrorOf(new ApiRequestError(403, 'forbidden_origin', { code: 'forbidden_origin' }))).toBe(
      'forbidden_origin',
    );
  });

  it('falls back to a generic failure', () => {
    expect(guestStartErrorOf(new ApiRequestError(500, null))).toBe('guest_failed');
    expect(guestStartErrorOf(new TypeError('network'))).toBe('guest_failed');
  });
});
