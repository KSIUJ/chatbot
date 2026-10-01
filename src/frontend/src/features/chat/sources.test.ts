import { describe, expect, it } from 'vitest';
import { parseSources, safeHttpUrl, sourceHref } from './sources';

describe('safeHttpUrl', () => {
  it('accepts absolute http and https URLs', () => {
    expect(safeHttpUrl('https://www.wmii.uj.edu.pl/studia')).toBe('https://www.wmii.uj.edu.pl/studia');
    expect(safeHttpUrl('http://usosweb.uj.edu.pl/kontroler.php?_action=x')).toBe(
      'http://usosweb.uj.edu.pl/kontroler.php?_action=x',
    );
  });

  it('rejects script and other non-web schemes', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
    expect(safeHttpUrl(' JavaScript:alert(1)')).toBeNull();
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(safeHttpUrl('file:///etc/passwd')).toBeNull();
    expect(safeHttpUrl('mailto:dziekanat@uj.edu.pl')).toBeNull();
  });

  it('rejects relative, malformed and missing URLs', () => {
    expect(safeHttpUrl('/studia')).toBeNull();
    expect(safeHttpUrl('www.wmii.uj.edu.pl')).toBeNull();
    expect(safeHttpUrl('')).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});

describe('parseSources', () => {
  it('keeps valid sources in order', () => {
    const sources = [
      { kind: 'strony', title: 'Rekrutacja', url: 'https://www.wmii.uj.edu.pl/rekrutacja' },
      { kind: 'mordor', title: 'Analiza 1 - notatki.pdf', url: null },
    ];

    expect(parseSources(sources)).toEqual(sources);
  });

  it('drops malformed entries and unknown kinds', () => {
    const result = parseSources([
      { kind: 'usos', title: 'dr Jan Kowalski', url: 42 },
      { kind: 'wikipedia', title: 'X', url: null },
      { kind: 'strony', title: '   ', url: null },
      { kind: 'strony' },
      'strony',
      null,
    ]);

    expect(result).toEqual([{ kind: 'usos', title: 'dr Jan Kowalski', url: null }]);
  });

  it('treats a missing list as no sources', () => {
    expect(parseSources(undefined)).toEqual([]);
    expect(parseSources({ kind: 'strony' })).toEqual([]);
  });
});

describe('sourceHref', () => {
  it('links website and USOS sources with a safe URL', () => {
    expect(sourceHref({ kind: 'strony', title: 'A', url: 'https://a.pl/' })).toBe('https://a.pl/');
    expect(sourceHref({ kind: 'usos', title: 'B', url: 'https://usos.pl/x' })).toBe('https://usos.pl/x');
  });

  it('never links Mordor sources or unsafe URLs', () => {
    expect(sourceHref({ kind: 'mordor', title: 'C', url: 'https://mordor.example/plik.pdf' })).toBeNull();
    expect(sourceHref({ kind: 'strony', title: 'D', url: 'javascript:alert(1)' })).toBeNull();
    expect(sourceHref({ kind: 'usos', title: 'E', url: null })).toBeNull();
  });
});
