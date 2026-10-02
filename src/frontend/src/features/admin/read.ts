// Strict readers for admin API responses: server data is not trusted, and a
// response of the wrong shape is a bug worth surfacing (the tab shows its
// load error) rather than a half-rendered page.

export class InvalidResponseError extends Error {
  constructor(path: string) {
    super(`Invalid admin API response at ${path}`);
    this.name = 'InvalidResponseError';
  }
}

export type JsonRecord = Record<string, unknown>;

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function record(value: unknown, path: string): JsonRecord {
  if (!isRecord(value)) throw new InvalidResponseError(path);
  return value;
}

export function str(source: JsonRecord, key: string): string {
  const value = source[key];
  if (typeof value !== 'string') throw new InvalidResponseError(key);
  return value;
}

export function optStr(source: JsonRecord, key: string): string | null {
  const value = source[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string') throw new InvalidResponseError(key);
  return value;
}

export function num(source: JsonRecord, key: string): number {
  const value = source[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new InvalidResponseError(key);
  return value;
}

export function optNum(source: JsonRecord, key: string): number | null {
  const value = source[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new InvalidResponseError(key);
  return value;
}

export function bool(source: JsonRecord, key: string): boolean {
  const value = source[key];
  if (typeof value !== 'boolean') throw new InvalidResponseError(key);
  return value;
}

export function list(source: JsonRecord, key: string): unknown[] {
  const value = source[key];
  if (!Array.isArray(value)) throw new InvalidResponseError(key);
  return value;
}

export function strings(source: JsonRecord, key: string): string[] {
  return list(source, key).filter((item): item is string => typeof item === 'string');
}

// The value if it is one of `options`, otherwise null (unknown enum values from
// a newer backend are shown as "unknown" instead of breaking the page).
export function oneOf<T extends string>(value: unknown, options: readonly T[]): T | null {
  return typeof value === 'string' && (options as readonly string[]).includes(value) ? (value as T) : null;
}
