import { describe, expect, it } from 'vitest';
import source from '../../../public/theme-init.js?raw';
import { CACHE_MAX_AGE_MS, cacheOccasion, type Occasion } from './occasion';

// public/theme-init.js mirrors occasion.ts by hand (it runs before the bundle);
// these tests run the real file against fake browser objects.

const OCCASION: Occasion = {
  dark: true,
  themeColor: '#0b1a2a',
  palette: { 'night-950': '#0b1a2a', 'night-900': '#11243a', 'night-100': '#e6eef6' },
  facade: null,
};

interface Run {
  dark: boolean;
  vars: Record<string, string>;
  meta: string[];
}

function runInit(storage: Record<string, string>, { osDark = false } = {}): Run {
  const classes = new Set<string>();
  const vars: Record<string, string> = {};
  const metas = [{ content: '#eef0f4' }, { content: '#14151f' }];
  const fakeWindow = {
    localStorage: { getItem: (key: string) => storage[key] ?? null },
    matchMedia: () => ({ matches: osDark }),
  };
  const fakeDocument = {
    documentElement: {
      classList: { toggle: (name: string, on: boolean) => void (on ? classes.add(name) : classes.delete(name)) },
      style: { setProperty: (name: string, value: string) => void (vars[name] = value) },
    },
    querySelectorAll: () => metas,
  };
  new Function('window', 'document', source)(fakeWindow, fakeDocument);
  return { dark: classes.has('dark'), vars, meta: metas.map((m) => m.content) };
}

describe('theme-init.js', () => {
  it('forces dark and applies the cached tokens for a dark occasion', () => {
    const result = runInit({ chatTheme: 'jasny', chatOccasion: cacheOccasion(OCCASION, Date.now()) });
    expect(result.dark).toBe(true);
    expect(result.vars['--ksi-bg']).toBe('#0b1a2a');
    expect(result.vars['--ksi-surface']).toBe('#11243a');
    expect(result.meta).toEqual(['#0b1a2a', '#0b1a2a']);
  });

  it('falls back to the occasion background for the browser bar, like themeColorFor()', () => {
    const occasion = { ...OCCASION, themeColor: null };
    const result = runInit({ chatTheme: 'jasny', chatOccasion: cacheOccasion(occasion, Date.now()) });
    expect(result.meta).toEqual(['#0b1a2a', '#0b1a2a']);
  });

  it('keeps the user theme for an occasion that does not force dark', () => {
    const occasion = { ...OCCASION, dark: false, themeColor: null };
    const result = runInit({ chatTheme: 'jasny', chatOccasion: cacheOccasion(occasion, Date.now()) });
    expect(result).toEqual({ dark: false, vars: {}, meta: ['#eef0f4', '#14151f'] });
  });

  it.each([
    ['switched off', { chatOccasionThemes: 'off', chatOccasion: cacheOccasion(OCCASION, Date.now()) }],
    ['expired', { chatOccasion: cacheOccasion(OCCASION, Date.now() - CACHE_MAX_AGE_MS - 1000) }],
    ['saved in the future', { chatOccasion: cacheOccasion(OCCASION, Date.now() + 60_000) }],
    ['broken', { chatOccasion: '{' }],
    ['nothing on', { chatOccasion: cacheOccasion(null, Date.now()) }],
  ])('ignores the cache when %s', (_name, storage) => {
    expect(runInit({ chatTheme: 'jasny', ...storage })).toEqual({ dark: false, vars: {}, meta: ['#eef0f4', '#14151f'] });
  });

  it('still follows the device without a usable cache', () => {
    expect(runInit({ chatOccasion: '{' }, { osDark: true }).dark).toBe(true);
  });

  it('sets only --ksi-* tokens with plain colour values', () => {
    const entry = JSON.stringify({
      v: 1,
      savedAt: Date.now(),
      occasion: { dark: true, themeColor: 'red;x', palette: {}, facade: null },
      vars: {
        '--ksi-bg': '#000000',
        '--ksi-text': 'url(https://evil.test/x)',
        '--ksi-border': 'url(x.png)',
        '--ksi-border-strong': 'attr(data-x)',
        color: '#ffffff',
        '--other': '#ffffff',
        '--ksi-surface': 'color-mix(in srgb, #000000 50%, #111111)',
      },
    });
    const result = runInit({ chatOccasion: entry });
    expect(result.vars).toEqual({
      '--ksi-bg': '#000000',
      '--ksi-surface': 'color-mix(in srgb, #000000 50%, #111111)',
    });
    expect(result.meta).toEqual(['#eef0f4', '#14151f']);
  });
});
