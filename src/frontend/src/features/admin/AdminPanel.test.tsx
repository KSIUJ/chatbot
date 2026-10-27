import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { translations } from '../preferences/languages';
import { StaleDataBanner } from './AdminPanel';

const lang = translations.pl;

describe('StaleDataBanner', () => {
  it('shows nothing when the data is fresh', () => {
    expect(renderToStaticMarkup(<StaleDataBanner lang={lang} sources={[]} />)).toBe('');
  });

  it('names the source, the last refresh and where to look', () => {
    const html = renderToStaticMarkup(
      <StaleDataBanner lang={lang} sources={[{ name: 'usos', collectedAt: '2026-10-24T03:40:00Z', maxAgeHours: 48 }]} />,
    );

    expect(html).toContain('Dane USOS nie były odświeżane od');
    expect(html).toContain('2026');
    expect(html).toContain('logs/refresh-usos.log');
  });

  it('says when the source is missing from the index', () => {
    const html = renderToStaticMarkup(
      <StaleDataBanner lang={lang} sources={[{ name: 'usos', collectedAt: null, maxAgeHours: 48 }]} />,
    );

    expect(html).toContain('Brak danych USOS w indeksie.');
  });
});
