import { describe, expect, it } from 'vitest';
import {
  AUTO_REDIRECT_COOLDOWN_MS,
  clearRedirectMark,
  markRedirect,
  readLastRedirect,
  shouldAutoRedirect,
} from './redirect';

class MemoryStorage {
  private readonly items = new Map<string, string>();
  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
  removeItem(key: string): void {
    this.items.delete(key);
  }
}

const NOW = 1_000_000;

describe('shouldAutoRedirect', () => {
  it('redirects a visitor without a session straight to KSI login', () => {
    expect(shouldAutoRedirect(null, null, NOW)).toBe(true);
    expect(shouldAutoRedirect('not_authenticated', null, NOW)).toBe(true);
  });

  it('redirects when the session expired, so SSO can renew it silently', () => {
    expect(shouldAutoRedirect('session_expired', null, NOW)).toBe(true);
  });

  it.each([
    'not_member',
    'access_denied',
    'provider_unavailable',
    'invalid_state',
    'login_failed',
    'forbidden_origin',
  ] as const)('shows the error instead of redirecting for %s (would loop)', (code) => {
    expect(shouldAutoRedirect(code, null, NOW)).toBe(false);
  });

  it('stops after a recent auto-redirect that did not produce a session', () => {
    expect(shouldAutoRedirect(null, NOW - 5_000, NOW)).toBe(false);
  });

  it('redirects again once the cooldown has passed', () => {
    expect(shouldAutoRedirect(null, NOW - AUTO_REDIRECT_COOLDOWN_MS - 1, NOW)).toBe(true);
  });

  it('ignores a mark from the future (clock change)', () => {
    expect(shouldAutoRedirect(null, NOW + 10_000, NOW)).toBe(true);
  });
});

describe('redirect mark', () => {
  it('round-trips through storage and can be cleared', () => {
    const storage = new MemoryStorage();
    expect(readLastRedirect(storage)).toBeNull();

    markRedirect(storage, NOW);
    expect(readLastRedirect(storage)).toBe(NOW);

    clearRedirectMark(storage);
    expect(readLastRedirect(storage)).toBeNull();
  });

  it('treats a corrupted mark as missing', () => {
    const storage = new MemoryStorage();
    storage.setItem('authAutoRedirectAt', 'not-a-number');
    expect(readLastRedirect(storage)).toBeNull();
  });
});
