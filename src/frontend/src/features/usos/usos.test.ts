import { describe, expect, it } from 'vitest';
import { LANGUAGES, translations } from '../preferences/languages';
import {
  USOS_ERROR_CODES,
  formatConnectedAt,
  isUsosVisible,
  parseAuthorizeUrl,
  parseUsosResult,
  parseUsosStatus,
  withoutLink,
  type UsosStatus,
} from './usos';

const connectedBody = {
  available: true,
  connected: true,
  needs_reconnect: false,
  name: 'Jan Kowalski',
  connected_at: '2026-10-26T12:00:00Z',
  scopes: ['studies', 'grades', 7],
};

const disconnected: UsosStatus = {
  available: true,
  connected: false,
  needsReconnect: false,
  name: null,
  connectedAt: null,
  scopes: [],
};

describe('parseUsosStatus', () => {
  it('reads a connected status', () => {
    expect(parseUsosStatus(connectedBody)).toEqual({
      available: true,
      connected: true,
      needsReconnect: false,
      name: 'Jan Kowalski',
      connectedAt: '2026-10-26T12:00:00Z',
      scopes: ['studies', 'grades'],
    });
  });

  it('reads the status without a link', () => {
    const body = { available: false, connected: false, needs_reconnect: false, name: null, connected_at: null, scopes: [] };
    expect(parseUsosStatus(body)).toEqual({ ...disconnected, available: false });
  });

  it('rejects responses of the wrong shape', () => {
    for (const body of [null, [], 'x', { ...connectedBody, available: 'yes' }, { ...connectedBody, connected_at: 'soon' }]) {
      expect(() => parseUsosStatus(body)).toThrow();
    }
    const older: Record<string, unknown> = { ...connectedBody };
    delete older.needs_reconnect;
    expect(() => parseUsosStatus(older)).toThrow();
  });
});

describe('isUsosVisible', () => {
  it('shows the item while connecting is possible or a link exists', () => {
    expect(isUsosVisible(null)).toBe(false);
    expect(isUsosVisible(disconnected)).toBe(true);
    expect(isUsosVisible({ ...disconnected, available: false })).toBe(false);
    expect(isUsosVisible({ ...disconnected, available: false, connected: true })).toBe(true);
    expect(isUsosVisible({ ...disconnected, available: false, needsReconnect: true })).toBe(true);
  });

  it('forgets the link after disconnecting', () => {
    const status = parseUsosStatus(connectedBody);
    expect(withoutLink(status)).toEqual(disconnected);
    expect(isUsosVisible(withoutLink({ ...status, available: false }))).toBe(false);
  });
});

describe('parseAuthorizeUrl', () => {
  it('accepts the https consent page', () => {
    const url = 'https://apps.usos.uj.edu.pl/services/oauth/authorize?oauth_token=abc123';
    expect(parseAuthorizeUrl({ authorize_url: url })).toBe(url);
  });

  it('refuses anything that is not an https address', () => {
    for (const url of ['javascript:alert(1)', 'http://apps.usos.uj.edu.pl/x', '/relative', 7, null]) {
      expect(() => parseAuthorizeUrl({ authorize_url: url })).toThrow();
    }
    expect(() => parseAuthorizeUrl(null)).toThrow();
  });
});

describe('parseUsosResult', () => {
  it('reads the redirect back from USOS', () => {
    expect(parseUsosResult('?usos=connected')).toBe('connected');
    expect(parseUsosResult('?usos_error=denied')).toBe('denied');
    expect(parseUsosResult('?foo=1&usos_error=mismatch')).toBe('mismatch');
  });

  it('treats unknown codes as a failure and ignores unrelated params', () => {
    expect(parseUsosResult('?usos_error=<script>')).toBe('failed');
    expect(parseUsosResult('?usos=maybe')).toBeNull();
    expect(parseUsosResult('?auth_error=login_failed')).toBeNull();
    expect(parseUsosResult('')).toBeNull();
  });
});

describe('USOS strings', () => {
  it('has a message for every result in every language', () => {
    for (const key of LANGUAGES) {
      const { results, consentData, consentNotes } = translations[key].usos;
      for (const code of ['connected', ...USOS_ERROR_CODES] as const) expect(results[code]).toBeTruthy();
      expect(consentData).toHaveLength(4);
      expect(consentNotes).toHaveLength(4);
    }
  });

  it('names the model provider and USOS revocation in the consent text', () => {
    for (const key of LANGUAGES) {
      const notes = translations[key].usos.consentNotes.join(' ');
      expect(notes).toContain('Anthropic');
      expect(notes).toContain('apps.usos.uj.edu.pl');
    }
  });

  it('formats the connection date in the interface language', () => {
    expect(formatConnectedAt('2026-10-26T12:00:00Z', 'pl')).toContain('2026');
  });
});
