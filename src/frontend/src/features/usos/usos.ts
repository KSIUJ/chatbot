import { apiFetch, apiJson } from '../../lib/api';
import { InvalidResponseError, bool, optStr, record, strings } from '../admin/read';

// Linking the chat account with USOS (OAuth 1.0a on the backend):
// GET /usos/status, POST /usos/connect (then a full navigation to the USOS
// consent page), DELETE /usos/link. The backend comes back from USOS to
// /?usos=connected or /?usos_error=<code>.

export interface UsosStatus {
  // false = the feature is switched off (the settings item is hidden unless a link exists)
  available: boolean;
  // a working link
  connected: boolean;
  // a link USOS rejected (revoked in USOS, expired) - connect again
  needsReconnect: boolean;
  // first and last name from USOS
  name: string | null;
  // ISO time of connecting
  connectedAt: string | null;
  scopes: string[];
}

export const USOS_ERROR_CODES = ['unavailable', 'session', 'denied', 'expired', 'mismatch', 'failed'] as const;
export type UsosErrorCode = (typeof USOS_ERROR_CODES)[number];

// What the redirect back from USOS reported.
export type UsosResult = 'connected' | UsosErrorCode;

// Strict reader: a wrong shape is a bug, so the settings item stays hidden.
export function parseUsosStatus(value: unknown): UsosStatus {
  const body = record(value, 'usos/status');
  const connectedAt = optStr(body, 'connected_at');
  if (connectedAt !== null && Number.isNaN(Date.parse(connectedAt))) throw new InvalidResponseError('connected_at');
  return {
    available: bool(body, 'available'),
    connected: bool(body, 'connected'),
    needsReconnect: bool(body, 'needs_reconnect'),
    name: optStr(body, 'name'),
    connectedAt,
    scopes: strings(body, 'scopes'),
  };
}

// The settings item is shown while connecting is possible, and also while a
// link exists, so it can always be removed (even with the feature switched off).
export function isUsosVisible(status: UsosStatus | null): boolean {
  return status !== null && (status.available || status.connected || status.needsReconnect);
}

// "connected since" date in the interface language.
export function formatConnectedAt(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(iso));
}

// The status right after a successful DELETE /usos/link.
export function withoutLink(status: UsosStatus): UsosStatus {
  return { ...status, connected: false, needsReconnect: false, name: null, connectedAt: null, scopes: [] };
}

// The USOS consent page; only an https address is followed.
export function parseAuthorizeUrl(value: unknown): string {
  const url = record(value, 'usos/connect').authorize_url;
  if (typeof url !== 'string') throw new InvalidResponseError('authorize_url');
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new InvalidResponseError('authorize_url');
  }
  if (parsed.protocol !== 'https:') throw new InvalidResponseError('authorize_url');
  return parsed.href;
}

export async function fetchUsosStatus(): Promise<UsosStatus> {
  return parseUsosStatus(await apiJson<unknown>('/usos/status'));
}

// Starts linking: the backend sets a short-lived cookie and returns the consent page.
export async function startUsosConnect(): Promise<string> {
  return parseAuthorizeUrl(await apiJson<unknown>('/usos/connect', { method: 'POST' }));
}

export async function disconnectUsos(): Promise<void> {
  await apiFetch('/usos/link', { method: 'DELETE' });
}

function isErrorCode(value: string): value is UsosErrorCode {
  return (USOS_ERROR_CODES as readonly string[]).includes(value);
}

// ?usos=connected / ?usos_error=<code> from the redirect back; an unknown
// code counts as "failed".
export function parseUsosResult(search: string): UsosResult | null {
  const params = new URLSearchParams(search);
  const error = params.get('usos_error');
  if (error !== null) return isErrorCode(error) ? error : 'failed';
  return params.get('usos') === 'connected' ? 'connected' : null;
}

// Reads the result once and removes it from the address bar.
function takeUsosResultFromUrl(): UsosResult | null {
  const url = new URL(window.location.href);
  const result = parseUsosResult(url.search);
  if (!url.searchParams.has('usos') && !url.searchParams.has('usos_error')) return result;
  url.searchParams.delete('usos');
  url.searchParams.delete('usos_error');
  window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  return result;
}

// Read once per page load: StrictMode runs initializers twice in dev, and the
// first run strips the params - the second must still see the result.
let resultCache: UsosResult | null | undefined;
export function usosResultFromUrlOnce(): UsosResult | null {
  if (resultCache === undefined) resultCache = takeUsosResultFromUrl();
  return resultCache;
}
