import { describe, expect, it } from 'vitest';
import {
  DARK_CLASS,
  DEFAULT_THEME_PREFERENCE,
  THEME_KEYS,
  THEME_PREFERENCES,
  applyTheme,
  isDarkTheme,
  parseThemePreference,
  resolveTheme,
} from './themes';
import { translations } from './languages';

describe('parseThemePreference', () => {
  it('defaults to the system theme when nothing was chosen', () => {
    expect(DEFAULT_THEME_PREFERENCE).toBe('systemowy');
    expect(parseThemePreference(null)).toBe('systemowy');
  });

  it('keeps a theme the user picked earlier', () => {
    expect(parseThemePreference('ciemny')).toBe('ciemny');
    expect(parseThemePreference('jasny')).toBe('jasny');
  });

  it('falls back to the default for unknown or removed themes', () => {
    expect(parseThemePreference('neon')).toBe('systemowy');
    expect(parseThemePreference('')).toBe('systemowy');
  });
});

describe('resolveTheme', () => {
  it('follows the device for the system preference', () => {
    expect(resolveTheme('systemowy', true)).toBe('ciemny');
    expect(resolveTheme('systemowy', false)).toBe('jasny');
  });

  it('ignores the device for an explicit choice', () => {
    expect(resolveTheme('jasny', true)).toBe('jasny');
    expect(resolveTheme('ciemny', false)).toBe('ciemny');
  });
});

describe('theme options', () => {
  it('lists the system option first and every concrete theme after it', () => {
    expect(THEME_PREFERENCES[0]).toBe('systemowy');
    expect([...THEME_PREFERENCES.slice(1)].sort()).toEqual([...THEME_KEYS].sort());
  });

  it('has a label for every option in every language', () => {
    for (const lang of Object.values(translations)) {
      for (const option of THEME_PREFERENCES) {
        expect(lang.themeNames[option]).toBeTruthy();
      }
    }
  });

  it('marks only the dark theme as dark', () => {
    expect(isDarkTheme('ciemny')).toBe(true);
    expect(isDarkTheme('jasny')).toBe(false);
  });
});

describe('applyTheme', () => {
  const makeRoot = (initial: string[] = []) => {
    const classes = new Set(initial);
    const classList = {
      toggle: (name: string, force?: boolean) => {
        const on = force ?? !classes.has(name);
        if (on) classes.add(name);
        else classes.delete(name);
        return on;
      },
    };
    return { root: { classList }, classes };
  };

  it('adds the dark class for the dark theme', () => {
    const { root, classes } = makeRoot();
    applyTheme(root, 'ciemny');
    expect(classes.has(DARK_CLASS)).toBe(true);
  });

  it('removes the dark class for the light theme', () => {
    const { root, classes } = makeRoot([DARK_CLASS, 'other']);
    applyTheme(root, 'jasny');
    expect(classes.has(DARK_CLASS)).toBe(false);
    expect(classes.has('other')).toBe(true);
  });
});
