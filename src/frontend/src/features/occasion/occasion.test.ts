import { describe, expect, it } from 'vitest';
import {
  CACHE_MAX_AGE_MS,
  OCCASION_TOKEN_NAMES,
  THEME_COLORS,
  applyOccasionStyle,
  cacheOccasion,
  contrastRatio,
  effectiveTheme,
  facadeUrl,
  occasionVars,
  parseOccasion,
  parseOccasionToggle,
  readCachedOccasion,
  sameOccasion,
  themeColorFor,
  type Occasion,
} from './occasion';

// Synthetic values only: the repo is public and the ksi.sh themes are secret.
const PL = '0123456789abcdef';
const EN = 'fedcba9876543210';

const PALETTE = {
  'night-950': '#0b1a2a',
  'night-900': '#11243a',
  'night-800': '#173049',
  'night-700': '#21405e',
  'night-600': '#2d5275',
  'night-400': '#7f9ab5',
  'night-300': '#a9bdd1',
  'night-200': '#cfdbe7',
  'night-100': '#e6eef6',
  accent: '#1d5c3a',
  'accent-hover': '#7fd6a4',
  'accent-light': '#b8ecd0',
};

const ACTIVE: Occasion = {
  dark: true,
  themeColor: '#0b1a2a',
  palette: PALETTE,
  facade: { pl: PL, en: EN },
};

const BODY = { active: true, dark: true, theme_color: '#0b1a2a', palette: PALETTE, facade: { pl: PL, en: EN } };

describe('parseOccasion', () => {
  it('reads an active occasion', () => {
    expect(parseOccasion(BODY)).toEqual(ACTIVE);
  });

  it('returns null when nothing is on', () => {
    expect(parseOccasion({ active: false, dark: false, theme_color: null, palette: {}, facade: null })).toBeNull();
  });

  it('keeps an occasion without facade or colour', () => {
    expect(parseOccasion({ ...BODY, dark: false, theme_color: null, facade: null })).toEqual({
      ...ACTIVE,
      dark: false,
      themeColor: null,
      facade: null,
    });
  });

  it('drops unknown palette entries and non-hex values', () => {
    const palette = { 'night-950': '#000000', accent: 'red', evil: '#111111', 'night-100': 'url(x)' };
    expect(parseOccasion({ ...BODY, palette })?.palette).toEqual({ 'night-950': '#000000' });
  });

  it.each([
    null,
    'x',
    [],
    { ...BODY, active: 'yes' },
    { ...BODY, dark: 1 },
    { ...BODY, theme_color: 'red' },
    { ...BODY, facade: { pl: 'short', en: EN } },
    { ...BODY, facade: { pl: '../../etc/passwd', en: EN } },
    { ...BODY, facade: { pl: PL } },
    { ...BODY, palette: 'x' },
  ])('rejects malformed answers (%#)', (value) => {
    expect(parseOccasion(value)).toBeUndefined();
  });
});

describe('effectiveTheme', () => {
  it('forces dark for a dark occasion whatever the user chose', () => {
    expect(effectiveTheme('jasny', ACTIVE)).toBe('ciemny');
    expect(effectiveTheme('ciemny', ACTIVE)).toBe('ciemny');
  });

  it('keeps the user theme without an occasion or for one that follows it', () => {
    expect(effectiveTheme('jasny', null)).toBe('jasny');
    expect(effectiveTheme('jasny', { ...ACTIVE, dark: false })).toBe('jasny');
  });
});

describe('contrastRatio', () => {
  it('matches the WCAG formula', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeCloseTo(21, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });
});

describe('occasionVars', () => {
  it('maps the ksi.sh night palette onto the dark chat tokens', () => {
    const vars = occasionVars(ACTIVE, 'ciemny');
    expect(vars['--ksi-bg']).toBe('#0b1a2a');
    expect(vars['--ksi-surface']).toBe('#11243a');
    expect(vars['--ksi-surface-hover']).toBe('#173049');
    expect(vars['--ksi-border']).toBe('#21405e');
    expect(vars['--ksi-text']).toBe('#e6eef6');
    expect(vars['--ksi-bg-accent']).toContain('color-mix');
  });

  it('uses the accent for buttons only with readable white text', () => {
    const vars = occasionVars(ACTIVE, 'ciemny');
    expect(vars['--ksi-btn-bg']).toBe('#1d5c3a');
    // the light hover fails 4.5:1 with white, so a darker mix of the accent is used
    expect(vars['--ksi-btn-bg-hover']).toBe('color-mix(in srgb, #1d5c3a 85%, #000000)');

    const pale = occasionVars({ ...ACTIVE, palette: { ...PALETTE, accent: '#f0f0a0' } }, 'ciemny');
    expect(pale['--ksi-btn-bg']).toBeUndefined();
    expect(pale['--ksi-btn-bg-hover']).toBeUndefined();
  });

  it('skips text colours that would be unreadable', () => {
    const vars = occasionVars({ ...ACTIVE, palette: { ...PALETTE, 'night-100': '#173049', 'night-300': '#21405e' } }, 'ciemny');
    expect(vars['--ksi-text']).toBeUndefined();
    expect(vars['--ksi-text-muted']).toBeUndefined();
  });

  it('changes nothing in the light theme or without an occasion', () => {
    expect(occasionVars(ACTIVE, 'jasny')).toEqual({});
    expect(occasionVars(null, 'ciemny')).toEqual({});
  });

  it('only ever sets known tokens', () => {
    for (const name of Object.keys(occasionVars(ACTIVE, 'ciemny'))) {
      expect(OCCASION_TOKEN_NAMES).toContain(name);
    }
  });
});

describe('applyOccasionStyle', () => {
  function fakeStyle() {
    const values = new Map<string, string>();
    return {
      values,
      setProperty: (name: string, value: string) => void values.set(name, value),
      removeProperty: (name: string) => {
        values.delete(name);
        return '';
      },
    };
  }

  it('sets the new tokens and removes the ones of a previous occasion', () => {
    const style = fakeStyle();
    applyOccasionStyle(style, { '--ksi-bg': '#000000', '--ksi-text': '#ffffff' });
    applyOccasionStyle(style, { '--ksi-bg': '#111111' });
    expect(Object.fromEntries(style.values)).toEqual({ '--ksi-bg': '#111111' });
  });
});

describe('themeColorFor', () => {
  it('uses the occasion colour when it forces dark', () => {
    expect(themeColorFor('ciemny', ACTIVE)).toBe('#0b1a2a');
  });

  it('uses the occasion background in dark mode and the defaults otherwise', () => {
    expect(themeColorFor('ciemny', { ...ACTIVE, dark: false, themeColor: null })).toBe('#0b1a2a');
    expect(themeColorFor('jasny', { ...ACTIVE, dark: false, themeColor: null })).toBe(THEME_COLORS.jasny);
    expect(themeColorFor('ciemny', null)).toBe(THEME_COLORS.ciemny);
  });
});

describe('facadeUrl', () => {
  it('picks the Polish facade for Polish and the English one for other languages', () => {
    expect(facadeUrl(ACTIVE, 'pl', 'jasny')).toBe(`/api/occasion/facade/${PL}?scheme=light`);
    expect(facadeUrl(ACTIVE, 'de', 'ciemny')).toBe(`/api/occasion/facade/${EN}?scheme=dark`);
  });

  it('is null without an occasion or facade', () => {
    expect(facadeUrl(null, 'pl', 'jasny')).toBeNull();
    expect(facadeUrl({ ...ACTIVE, facade: null }, 'pl', 'jasny')).toBeNull();
  });
});

describe('occasion cache', () => {
  const NOW = 1_800_000_000_000;

  it('round-trips a fresh entry with the dark tokens for theme-init.js', () => {
    const raw = cacheOccasion(ACTIVE, NOW);
    const parsed = JSON.parse(raw) as { vars: Record<string, string> };
    expect(parsed.vars['--ksi-bg']).toBe('#0b1a2a');
    expect(readCachedOccasion(raw, NOW + 1000)).toEqual(ACTIVE);
  });

  it('remembers that nothing is on', () => {
    expect(readCachedOccasion(cacheOccasion(null, NOW), NOW)).toBeNull();
  });

  it('ignores old, future, broken or foreign entries', () => {
    const raw = cacheOccasion(ACTIVE, NOW);
    expect(readCachedOccasion(raw, NOW + CACHE_MAX_AGE_MS + 1)).toBeNull();
    expect(readCachedOccasion(raw, NOW - 60_000)).toBeNull();
    expect(readCachedOccasion('{', NOW)).toBeNull();
    expect(readCachedOccasion(null, NOW)).toBeNull();
    expect(readCachedOccasion(JSON.stringify({ v: 2, savedAt: NOW, occasion: BODY }), NOW)).toBeNull();
    expect(readCachedOccasion(JSON.stringify({ v: 1, savedAt: NOW, occasion: { dark: 'x' } }), NOW)).toBeNull();
  });
});

describe('parseOccasionToggle', () => {
  it('is on unless switched off', () => {
    expect(parseOccasionToggle(null)).toBe(true);
    expect(parseOccasionToggle('on')).toBe(true);
    expect(parseOccasionToggle('off')).toBe(false);
  });
});

describe('sameOccasion', () => {
  it('compares by value', () => {
    expect(sameOccasion(ACTIVE, { ...ACTIVE, palette: { ...PALETTE } })).toBe(true);
    expect(sameOccasion(ACTIVE, { ...ACTIVE, facade: null })).toBe(false);
    expect(sameOccasion(null, null)).toBe(true);
    expect(sameOccasion(ACTIVE, null)).toBe(false);
  });
});
