// Where an answer came from: faculty website, USOS (staff) or Mordor (student
// materials). Only strony/usos may be links; Mordor files are not public.
export const SOURCE_KINDS = ['strony', 'usos', 'mordor'] as const;

export type SourceKind = (typeof SOURCE_KINDS)[number];

export interface Source {
  kind: SourceKind;
  title: string;
  url: string | null;
}

function isSourceKind(value: unknown): value is SourceKind {
  return typeof value === 'string' && (SOURCE_KINDS as readonly string[]).includes(value);
}

function parseSource(value: unknown): Source | null {
  if (typeof value !== 'object' || value === null) return null;
  const { kind, title, url } = value as Record<string, unknown>;
  if (!isSourceKind(kind) || typeof title !== 'string' || title.trim() === '') return null;
  return { kind, title, url: typeof url === 'string' ? url : null };
}

// Server data is not trusted: malformed entries are dropped, a missing list is empty.
export function parseSources(value: unknown): Source[] {
  if (!Array.isArray(value)) return [];
  return value.map(parseSource).filter((source): source is Source => source !== null);
}

// The URL to put in href, or null when it is not an absolute http(s) URL
// (blocks javascript:, data: and the like).
export function safeHttpUrl(url: string | null): string | null {
  if (url === null) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    // not an absolute URL
    return null;
  }
}

// Link target for a source: only website / USOS sources with a safe URL.
export function sourceHref(source: Source): string | null {
  return source.kind === 'mordor' ? null : safeHttpUrl(source.url);
}
