import { useEffect, useState, useSyncExternalStore } from 'react';
import {
  LANGUAGE_STORAGE_KEY,
  parseLanguagePreference,
  resolveLanguage,
  translations,
  type LanguagePreference,
  type Translation,
} from './languages';
import {
  OCCASION_TOGGLE_KEY,
  applyOccasionStyle,
  effectiveTheme,
  occasionVars,
  parseOccasionToggle,
  themeColorFor,
  type Occasion,
} from '../occasion/occasion';
import { THEME_STORAGE_KEY, applyTheme, parseThemePreference, type ThemeKey, type ThemePreference } from './themes';
import { useResolvedTheme } from './useResolvedTheme';

export interface Preferences {
  languagePreference: LanguagePreference;
  setLanguagePreference: (preference: LanguagePreference) => void;
  themePreference: ThemePreference;
  setThemePreference: (preference: ThemePreference) => void;
  // occasion themes of ksi.sh (setting, on by default)
  occasionThemes: boolean;
  setOccasionThemes: (enabled: boolean) => void;
  // strings of the language to render ("system" already resolved)
  lang: Translation;
  // theme to render ("systemowy" resolved, a dark occasion applied)
  theme: ThemeKey;
  // the ksi.sh occasion shown now (null = normal look or switched off)
  occasion: Occasion | null;
  // a dark occasion overrides the theme the user picked
  themeForced: boolean;
}

function subscribeToBrowserLanguage(onChange: () => void): () => void {
  window.addEventListener('languagechange', onChange);
  return () => window.removeEventListener('languagechange', onChange);
}

// a stable string snapshot - navigator.languages may be a new array each read
function browserLanguagesSnapshot(): string {
  return (navigator.languages ?? [navigator.language]).join(',');
}

function setThemeColor(color: string): void {
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) meta.content = color;
}

// UI settings kept in the browser: interface language, theme preference and
// occasion themes; `occasion` is what ksi.sh shows now (useOccasion).
export function usePreferences(occasion: Occasion | null): Preferences {
  const [languagePreference, setLanguagePreference] = useState<LanguagePreference>(() =>
    parseLanguagePreference(localStorage.getItem(LANGUAGE_STORAGE_KEY)),
  );
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)),
  );
  const [occasionThemes, setOccasionThemes] = useState<boolean>(() =>
    parseOccasionToggle(localStorage.getItem(OCCASION_TOGGLE_KEY)),
  );
  // "system" follows the browser live (changing its language re-renders)
  const browserLanguages = useSyncExternalStore(subscribeToBrowserLanguage, browserLanguagesSnapshot, () => '');
  const shownOccasion = occasionThemes ? occasion : null;
  const theme = effectiveTheme(useResolvedTheme(themePreference), shownOccasion);
  const lang = translations[resolveLanguage(languagePreference, browserLanguages.split(','))];

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, languagePreference);
  }, [languagePreference]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, themePreference);
  }, [themePreference]);

  useEffect(() => {
    localStorage.setItem(OCCASION_TOGGLE_KEY, occasionThemes ? 'on' : 'off');
  }, [occasionThemes]);

  // the KSI colour tokens follow the resolved theme (.dark on <html>), the
  // occasion palette goes over the dark ones; public/theme-init.js already
  // did both before the first paint
  useEffect(() => {
    const root = document.documentElement;
    applyTheme(root, theme);
    applyOccasionStyle(root.style, occasionVars(shownOccasion, theme));
    setThemeColor(themeColorFor(theme, shownOccasion));
  }, [theme, shownOccasion]);

  // screen readers and spell checking follow the rendered language
  useEffect(() => {
    document.documentElement.lang = lang.htmlLang;
  }, [lang.htmlLang]);

  return {
    languagePreference,
    setLanguagePreference,
    themePreference,
    setThemePreference,
    occasionThemes,
    setOccasionThemes,
    lang,
    theme,
    occasion: shownOccasion,
    themeForced: shownOccasion?.dark ?? false,
  };
}
