import type { LoginError } from '../auth/redirect';
import type { SourceKind } from '../chat/sources';
import type { ThemePreference } from './themes';
import { de } from './translations/de';
import { en } from './translations/en';
import { es } from './translations/es';
import { fr } from './translations/fr';
import { it } from './translations/it';
import { pl } from './translations/pl';
import { uk } from './translations/uk';

// Interface language code - the same languages as the KSI Keycloak. Also the
// value of <html lang>, the answer language sent to the API and ui_locales
// passed to the KSI login page.
export type HtmlLang = 'pl' | 'en' | 'de' | 'es' | 'fr' | 'it' | 'uk';

export interface Translation {
  // value of <html lang>
  htmlLang: HtmlLang;
  // name of the language in itself, for the settings menu
  languageName: string;
  // the "follow the browser" option in the language menu
  systemLanguage: string;
  appTitle: string;
  loading: string;
  ksiWebsite: string;
  // login screen
  authorization: string;
  logIn: string;
  tryAgain: string;
  redirecting: string;
  loginErrors: Record<LoginError, string>;
  // sidebar
  newChat: string;
  recent: string;
  noChats: string;
  untitled: string;
  deleteChat: string;
  deleteConfirm: string;
  historyNote: (max: number, days: number) => string;
  historyError: string;
  language: string;
  theme: string;
  themeNames: Record<ThemePreference, string>;
  settings: string;
  back: string;
  logout: string;
  openMenu: string;
  closeMenu: string;
  // conversation
  greeting: string;
  inputPlaceholder: string;
  waitingPlaceholder: string;
  send: string;
  stop: string;
  disclaimer: string;
  copy: string;
  copied: string;
  retry: string;
  stopped: string;
  error: string;
  loadError: string;
  sources: (count: number) => string;
  sourceKinds: Record<SourceKind, string>;
}

export const translations: Record<HtmlLang, Translation> = { pl, en, de, es, fr, it, uk };

// Order of the KSI Keycloak language menu (alphabetical by code).
export const LANGUAGES: readonly HtmlLang[] = ['de', 'en', 'es', 'fr', 'it', 'pl', 'uk'];

// "system" follows the browser language, like the "systemowy" theme.
export type LanguagePreference = 'system' | HtmlLang;

// Options of the settings menu: "system" first, then the languages.
export const LANGUAGE_PREFERENCES: readonly LanguagePreference[] = ['system', ...LANGUAGES];

// Used when "system" finds none of the supported languages in the browser.
export const FALLBACK_LANGUAGE: HtmlLang = 'en';

export const LANGUAGE_STORAGE_KEY = 'chatLanguage';

// Values stored by versions that had only Polish, English and French.
// (a Map, so stored junk like "constructor" never hits Object.prototype)
const LEGACY_PREFERENCES: ReadonlyMap<string, HtmlLang> = new Map([
  ['polski', 'pl'],
  ['angielski', 'en'],
  ['francuski', 'fr'],
]);

function asLanguage(value: string): HtmlLang | null {
  return LANGUAGES.find((key) => key === value) ?? null;
}

export function parseLanguagePreference(value: string | null): LanguagePreference {
  if (value === null || value === 'system') return 'system';
  return asLanguage(value) ?? LEGACY_PREFERENCES.get(value) ?? 'system';
}

// Language to render: the chosen one, or for "system" the first browser
// language we support (matched by its primary tag, e.g. "pl-PL" -> "pl").
export function resolveLanguage(preference: LanguagePreference, browserLanguages: readonly string[]): HtmlLang {
  if (preference !== 'system') return preference;
  for (const tag of browserLanguages) {
    const language = asLanguage(tag.toLowerCase().split('-')[0]);
    if (language !== null) return language;
  }
  return FALLBACK_LANGUAGE;
}
