import { API_BASE_URL } from '../../lib/api';
import type { HtmlLang } from '../preferences/languages';
import type { ThemeKey } from '../preferences/themes';

// Occasion themes of ksi.sh (the KSI badge contest): GET /api/occasion says
// what the KSI homepage shows right now. Nothing about the themes or their
// dates lives in this repo - the backend reads it from ksi.sh at runtime.

export const PALETTE_KEYS = [
  'night-950',
  'night-900',
  'night-800',
  'night-700',
  'night-600',
  'night-400',
  'night-300',
  'night-200',
  'night-100',
  'accent',
  'accent-hover',
  'accent-light',
] as const;

export type PaletteKey = (typeof PALETTE_KEYS)[number];
export type OccasionPalette = Partial<Record<PaletteKey, string>>;

export interface FacadeVersions {
  pl: string;
  en: string;
}

// An occasion that is on now; "nothing is on" is null.
export interface Occasion {
  // ksi.sh switches to its dark theme for it - so does the chat
  dark: boolean;
  // browser bar colour of ksi.sh during the occasion
  themeColor: string | null;
  palette: OccasionPalette;
  facade: FacadeVersions | null;
}

// Also read by public/theme-init.js (before the first paint) - keep in sync.
export const OCCASION_CACHE_KEY = 'chatOccasion';
export const OCCASION_TOGGLE_KEY = 'chatOccasionThemes';
export const CACHE_MAX_AGE_MS = 12 * 60 * 60 * 1000;
const CACHE_VERSION = 1;

// Browser bar colours of the normal look (the --ksi-bg of each theme).
export const THEME_COLORS: Record<ThemeKey, string> = { jasny: '#eef0f4', ciemny: '#14151f' };

// Dark tokens of src/index.css, used when the palette lacks a background.
const DEFAULT_DARK_BG = '#14151f';
const DEFAULT_DARK_SURFACE = '#1e2030';
const WHITE = '#ffffff';
const MIN_TEXT_CONTRAST = 4.5;
const MIN_LABEL_CONTRAST = 3;

// Every token an occasion may set on <html> (theme-init.js accepts only --ksi-*).
export const OCCASION_TOKEN_NAMES = [
  '--ksi-bg',
  '--ksi-bg-accent',
  '--ksi-surface',
  '--ksi-surface-sunken',
  '--ksi-surface-hover',
  '--ksi-border',
  '--ksi-border-strong',
  '--ksi-text',
  '--ksi-text-muted',
  '--ksi-text-faint',
  '--ksi-btn-bg',
  '--ksi-btn-bg-hover',
] as const;

export type OccasionTokenName = (typeof OCCASION_TOKEN_NAMES)[number];
export type OccasionVars = Partial<Record<OccasionTokenName, string>>;

const HEX_COLOR = /^#[0-9a-f]{6}$/i;
const VERSION = /^[0-9a-f]{16}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isHex(value: unknown): value is string {
  return typeof value === 'string' && HEX_COLOR.test(value);
}

function parsePalette(value: unknown): OccasionPalette | undefined {
  if (!isRecord(value)) return undefined;
  const palette: OccasionPalette = {};
  for (const key of PALETTE_KEYS) {
    const color = value[key];
    if (isHex(color)) palette[key] = color.toLowerCase();
  }
  return palette;
}

function parseFacade(value: unknown): FacadeVersions | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const { pl, en } = value;
  if (typeof pl !== 'string' || typeof en !== 'string' || !VERSION.test(pl) || !VERSION.test(en)) return undefined;
  return { pl, en };
}

function parseActive(dark: unknown, themeColor: unknown, palette: unknown, facade: unknown): Occasion | undefined {
  const parsedPalette = parsePalette(palette);
  const parsedFacade = parseFacade(facade);
  if (typeof dark !== 'boolean' || !(themeColor === null || isHex(themeColor))) return undefined;
  if (parsedPalette === undefined || parsedFacade === undefined) return undefined;
  return { dark, themeColor: themeColor === null ? null : themeColor.toLowerCase(), palette: parsedPalette, facade: parsedFacade };
}

// GET /occasion body: an Occasion, null when nothing is on, undefined when
// malformed (the caller keeps what it had - server data is not trusted).
export function parseOccasion(value: unknown): Occasion | null | undefined {
  if (!isRecord(value) || typeof value.active !== 'boolean') return undefined;
  const active = parseActive(value.dark, value.theme_color, value.palette, value.facade);
  if (active === undefined) return undefined;
  return value.active ? active : null;
}

// Theme to render: a dark occasion overrides "jasny" and "systemowy" alike.
export function effectiveTheme(theme: ThemeKey, occasion: Occasion | null): ThemeKey {
  return occasion?.dark ? 'ciemny' : theme;
}

function luminance(hex: string): number {
  const channel = (offset: number) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

// WCAG 2 contrast ratio of two #rrggbb colours.
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

function readableOn(color: string | undefined, backgrounds: string[], minimum: number): color is string {
  return color !== undefined && backgrounds.every((background) => contrastRatio(color, background) >= minimum);
}

function buttonVars(palette: OccasionPalette): OccasionVars {
  const { accent, 'accent-hover': hover } = palette;
  if (!readableOn(accent, [WHITE], MIN_TEXT_CONTRAST)) return {};
  const readableHover = readableOn(hover, [WHITE], MIN_TEXT_CONTRAST);
  return {
    '--ksi-btn-bg': accent,
    '--ksi-btn-bg-hover': readableHover ? hover : `color-mix(in srgb, ${accent} 85%, #000000)`,
  };
}

// Dark chat tokens from the ksi.sh palette (mapping of its "night" scale).
// Text colours are used only when readable on the occasion's backgrounds.
export function occasionVars(occasion: Occasion | null, theme: ThemeKey): OccasionVars {
  if (occasion === null || theme !== 'ciemny') return {};
  const p = occasion.palette;
  const bg = p['night-950'];
  const surface = p['night-900'];
  const backgrounds = [bg ?? DEFAULT_DARK_BG, surface ?? DEFAULT_DARK_SURFACE];
  const vars: OccasionVars = {
    '--ksi-bg': bg,
    '--ksi-bg-accent': bg && `color-mix(in srgb, ${bg} 80%, #000000)`,
    '--ksi-surface': surface,
    '--ksi-surface-sunken': bg && surface && `color-mix(in srgb, ${bg} 50%, ${surface})`,
    '--ksi-surface-hover': p['night-800'],
    '--ksi-border': p['night-700'],
    '--ksi-border-strong': p['night-600'],
    '--ksi-text': readableOn(p['night-100'], backgrounds, MIN_TEXT_CONTRAST) ? p['night-100'] : undefined,
    '--ksi-text-muted': readableOn(p['night-300'], backgrounds, MIN_TEXT_CONTRAST) ? p['night-300'] : undefined,
    '--ksi-text-faint': readableOn(p['night-400'], backgrounds, MIN_LABEL_CONTRAST) ? p['night-400'] : undefined,
    ...buttonVars(p),
  };
  return Object.fromEntries(Object.entries(vars).filter(([, value]) => value !== undefined)) as OccasionVars;
}

type StyleTarget = Pick<CSSStyleDeclaration, 'setProperty' | 'removeProperty'>;

// Puts the occasion tokens on <html> (inline, over the .dark values) and
// removes the ones a previous occasion set. CSSOM changes are allowed by the
// CSP's style-src 'self' (only inline style attributes/elements are not).
export function applyOccasionStyle(style: StyleTarget, vars: OccasionVars): void {
  for (const name of OCCASION_TOKEN_NAMES) {
    const value = vars[name];
    if (value === undefined) style.removeProperty(name);
    else style.setProperty(name, value);
  }
}

// Browser bar colour: the occasion's own one, its background in dark mode,
// otherwise the normal background of the theme.
export function themeColorFor(theme: ThemeKey, occasion: Occasion | null): string {
  if (theme === 'ciemny' && occasion) return occasion.themeColor ?? occasion.palette['night-950'] ?? THEME_COLORS.ciemny;
  return THEME_COLORS[theme];
}

// Facade image of the occasion for the interface language and theme
// (Polish has its own variant when the drawing contains words).
export function facadeUrl(occasion: Occasion | null, lang: HtmlLang, theme: ThemeKey): string | null {
  if (occasion?.facade == null) return null;
  const version = lang === 'pl' ? occasion.facade.pl : occasion.facade.en;
  const scheme = theme === 'ciemny' ? 'dark' : 'light';
  return `${API_BASE_URL}/occasion/facade/${version}?scheme=${scheme}`;
}

// localStorage entry: the last known state, so a reload (and theme-init.js)
// shows the occasion before the API answers. `vars` are the dark tokens.
export function cacheOccasion(occasion: Occasion | null, now: number): string {
  return JSON.stringify({ v: CACHE_VERSION, savedAt: now, occasion, vars: occasionVars(occasion, 'ciemny') });
}

export function readCachedOccasion(raw: string | null, now: number): Occasion | null {
  if (raw === null) return null;
  let entry: unknown;
  try {
    entry = JSON.parse(raw);
  } catch {
    // a broken entry is the same as none
    return null;
  }
  if (!isRecord(entry) || entry.v !== CACHE_VERSION || typeof entry.savedAt !== 'number') return null;
  const age = now - entry.savedAt;
  if (age < 0 || age > CACHE_MAX_AGE_MS || !isRecord(entry.occasion)) return null;
  const { dark, themeColor, palette, facade } = entry.occasion;
  return parseActive(dark, themeColor, palette, facade) ?? null;
}

// Settings toggle: on unless the user switched occasion themes off.
export function parseOccasionToggle(value: string | null): boolean {
  return value !== 'off';
}

export function sameOccasion(a: Occasion | null, b: Occasion | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
