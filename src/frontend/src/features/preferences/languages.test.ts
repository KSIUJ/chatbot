import { describe, expect, it } from 'vitest';
import {
  FALLBACK_LANGUAGE,
  LANGUAGES,
  LANGUAGE_PREFERENCES,
  parseLanguagePreference,
  resolveLanguage,
  translations,
} from './languages';

describe('parseLanguagePreference', () => {
  it('follows the system language when nothing was chosen', () => {
    expect(parseLanguagePreference(null)).toBe('system');
  });

  it('keeps a language the user picked', () => {
    expect(parseLanguagePreference('system')).toBe('system');
    expect(parseLanguagePreference('uk')).toBe('uk');
    expect(parseLanguagePreference('de')).toBe('de');
  });

  it('migrates the values stored by earlier versions', () => {
    expect(parseLanguagePreference('polski')).toBe('pl');
    expect(parseLanguagePreference('angielski')).toBe('en');
    expect(parseLanguagePreference('francuski')).toBe('fr');
  });

  it('falls back to the system language for unknown values', () => {
    expect(parseLanguagePreference('klingon')).toBe('system');
    expect(parseLanguagePreference('constructor')).toBe('system');
  });
});

describe('resolveLanguage', () => {
  it('uses the chosen language as is', () => {
    expect(resolveLanguage('it', ['pl-PL'])).toBe('it');
  });

  it('takes the first supported browser language for "system"', () => {
    expect(resolveLanguage('system', ['pl-PL', 'en-US'])).toBe('pl');
    expect(resolveLanguage('system', ['ru-RU', 'uk-UA', 'en'])).toBe('uk');
    expect(resolveLanguage('system', ['ES'])).toBe('es');
  });

  it('falls back to English when no browser language is supported', () => {
    expect(resolveLanguage('system', ['ru-RU', 'ja'])).toBe('en');
    expect(resolveLanguage('system', [])).toBe(FALLBACK_LANGUAGE);
    expect(FALLBACK_LANGUAGE).toBe('en');
  });
});

describe('language options', () => {
  it('offers the same languages as the KSI Keycloak, in its order', () => {
    expect(LANGUAGES).toEqual(['de', 'en', 'es', 'fr', 'it', 'pl', 'uk']);
  });

  it('puts "system" first in the settings menu', () => {
    expect(LANGUAGE_PREFERENCES).toEqual(['system', ...LANGUAGES]);
  });

  it('has a translation for every language with matching <html lang>', () => {
    expect(Object.keys(translations).sort()).toEqual([...LANGUAGES].sort());
    for (const key of LANGUAGES) expect(translations[key].htmlLang).toBe(key);
  });

  it('uses the same product name in every language', () => {
    for (const key of LANGUAGES) expect(translations[key].appTitle).toBe('Chatbot WMiI UJ');
  });

  it('has no empty strings in any translation', () => {
    for (const key of LANGUAGES) {
      const strings = JSON.stringify(translations[key], (_name, value: unknown) =>
        typeof value === 'function' ? 'fn' : value,
      );
      expect(strings).not.toMatch(/""/);
    }
  });
});
