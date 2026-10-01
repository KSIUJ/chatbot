import { describe, expect, it } from 'vitest';
import { LANGUAGES, parseLanguage, translations } from './languages';

describe('parseLanguage', () => {
  it('defaults to Polish when nothing was chosen', () => {
    expect(parseLanguage(null)).toBe('polski');
  });

  it('keeps a language the user picked earlier', () => {
    expect(parseLanguage('angielski')).toBe('angielski');
    expect(parseLanguage('polski')).toBe('polski');
  });

  it('falls back to Polish for unknown values', () => {
    expect(parseLanguage('english')).toBe('polski');
  });
});

describe('language options', () => {
  it('lists every translation exactly once', () => {
    expect([...LANGUAGES].sort()).toEqual(Object.keys(translations).sort());
  });

  it('uses the same product name in every language', () => {
    for (const key of LANGUAGES) expect(translations[key].appTitle).toBe('Chatbot WMiI UJ');
  });
});
