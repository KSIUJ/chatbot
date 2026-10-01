import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError, SESSION_LOST_EVENT, apiFetch, apiJson, isAuthErrorCode, isSessionLost } from './api';

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const errorBody = (code: string) => ({ detail: { code } });

describe('isAuthErrorCode', () => {
  it('accepts known codes and rejects anything else', () => {
    expect(isAuthErrorCode('session_expired')).toBe(true);
    expect(isAuthErrorCode('forbidden_origin')).toBe(true);
    expect(isAuthErrorCode('something_else')).toBe(false);
    expect(isAuthErrorCode(401)).toBe(false);
  });
});

describe('ApiRequestError.sessionLost', () => {
  it('is true only for 401/403 with a session-lost code', () => {
    expect(new ApiRequestError(401, 'session_expired').sessionLost).toBe(true);
    expect(new ApiRequestError(403, 'not_member').sessionLost).toBe(true);
    expect(new ApiRequestError(403, 'forbidden_origin').sessionLost).toBe(false);
    expect(new ApiRequestError(401, null).sessionLost).toBe(false);
    expect(new ApiRequestError(503, 'provider_unavailable').sessionLost).toBe(false);
  });

  it('is checked by isSessionLost for any thrown value', () => {
    expect(isSessionLost(new ApiRequestError(401, 'not_authenticated'))).toBe(true);
    expect(isSessionLost(new ApiRequestError(500, null))).toBe(false);
    expect(isSessionLost(new TypeError('Failed to fetch'))).toBe(false);
  });
});

describe('apiFetch', () => {
  const fetchMock = vi.fn<typeof fetch>();
  const sessionLostCodes: unknown[] = [];

  beforeEach(() => {
    sessionLostCodes.length = 0;
    const target = new EventTarget();
    target.addEventListener(SESSION_LOST_EVENT, (event) => sessionLostCodes.push((event as CustomEvent).detail));
    vi.stubGlobal('window', target);
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it('calls the API under /api with the session cookie', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }));

    await apiFetch('/conversations', { method: 'DELETE' });

    expect(fetchMock).toHaveBeenCalledWith('/api/conversations', { credentials: 'include', method: 'DELETE' });
  });

  it('announces a lost session and marks the error', async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, errorBody('session_expired')));

    const error = await apiFetch('/chat').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({ status: 401, code: 'session_expired', sessionLost: true });
    expect(sessionLostCodes).toEqual(['session_expired']);
  });

  it('does not announce a rejected origin - the session is still valid', async () => {
    fetchMock.mockResolvedValue(jsonResponse(403, errorBody('forbidden_origin')));

    const error = await apiFetch('/chat').catch((e: unknown) => e);

    expect(error).toMatchObject({ status: 403, code: 'forbidden_origin', sessionLost: false });
    expect(sessionLostCodes).toEqual([]);
  });

  it('does not announce a 401 without a JSON code', async () => {
    fetchMock.mockResolvedValue(new Response('Unauthorized', { status: 401 }));

    const error = await apiFetch('/chat').catch((e: unknown) => e);

    expect(error).toMatchObject({ status: 401, code: null, sessionLost: false });
    expect(sessionLostCodes).toEqual([]);
  });

  it('ignores unknown codes in the error body', async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, errorBody('database_down')));

    await expect(apiFetch('/chat')).rejects.toMatchObject({ status: 500, code: null });
  });
});

describe('apiJson', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the parsed body of a successful response', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(200, { id: 'u1' })));

    await expect(apiJson<{ id: string }>('/auth/me')).resolves.toEqual({ id: 'u1' });
  });
});
