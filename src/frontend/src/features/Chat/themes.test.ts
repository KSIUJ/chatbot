import { describe, expect, it } from 'vitest';
import {
  DEFAULT_THEME_PREFERENCE,
  THEME_PREFERENCES,
  isDarkTheme,
  parseThemePreference,
  resolveTheme,
  themeStyles,
} from './themes';
import { translations } from './languages';

describe('parseThemePreference', () => {
  it('defaults to the system theme when nothing was chosen', () => {
    expect(DEFAULT_THEME_PREFERENCE).toBe('systemowy');
    expect(parseThemePreference(null)).toBe('systemowy');
  });

  it('keeps a theme the user picked earlier', () => {
    expect(parseThemePreference('granatowy')).toBe('granatowy');
    expect(parseThemePreference('różowy')).toBe('różowy');
  });

  it('falls back to the default for unknown stored values', () => {
    expect(parseThemePreference('neon')).toBe('systemowy');
  });
});

describe('resolveTheme', () => {
  it('follows the device for the system preference', () => {
    expect(resolveTheme('systemowy', true)).toBe('ciemny');
    expect(resolveTheme('systemowy', false)).toBe('jasny');
  });

  it('ignores the device for an explicit choice', () => {
    expect(resolveTheme('różowy', true)).toBe('różowy');
    expect(resolveTheme('ciemny', false)).toBe('ciemny');
  });
});

describe('theme options', () => {
  it('lists the system option first and every concrete theme after it', () => {
    expect(THEME_PREFERENCES[0]).toBe('systemowy');
    expect([...THEME_PREFERENCES.slice(1)].sort()).toEqual(Object.keys(themeStyles).sort());
  });

  it('has a label for every option in every language', () => {
    for (const lang of Object.values(translations)) {
      for (const option of THEME_PREFERENCES) {
        expect(lang.themeNames[option]).toBeTruthy();
      }
    }
  });

  it('marks dark backgrounds as dark', () => {
    expect(isDarkTheme('ciemny')).toBe(true);
    expect(isDarkTheme('granatowy')).toBe(true);
    expect(isDarkTheme('jasny')).toBe(false);
    expect(isDarkTheme('różowy')).toBe(false);
  });
});
