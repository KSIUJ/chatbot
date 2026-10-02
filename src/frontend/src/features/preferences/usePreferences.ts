import { useEffect, useState, useSyncExternalStore } from 'react';
import {
  LANGUAGE_STORAGE_KEY,
  parseLanguagePreference,
  resolveLanguage,
  translations,
  type LanguagePreference,
  type Translation,
} from './languages';
import { THEME_STORAGE_KEY, applyTheme, parseThemePreference, type ThemeKey, type ThemePreference } from './themes';
import { useResolvedTheme } from './useResolvedTheme';

export interface Preferences {
  languagePreference: LanguagePreference;
  setLanguagePreference: (preference: LanguagePreference) => void;
  themePreference: ThemePreference;
  setThemePreference: (preference: ThemePreference) => void;
  // strings of the language to render ("system" already resolved)
  lang: Translation;
  // theme to render ("systemowy" already resolved to light/dark)
  theme: ThemeKey;
}

function subscribeToBrowserLanguage(onChange: () => void): () => void {
  window.addEventListener('languagechange', onChange);
  return () => window.removeEventListener('languagechange', onChange);
}

// a stable string snapshot - navigator.languages may be a new array each read
function browserLanguagesSnapshot(): string {
  return (navigator.languages ?? [navigator.language]).join(',');
}

// UI settings kept in the browser: interface language and theme preference.
export function usePreferences(): Preferences {
  const [languagePreference, setLanguagePreference] = useState<LanguagePreference>(() =>
    parseLanguagePreference(localStorage.getItem(LANGUAGE_STORAGE_KEY)),
  );
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)),
  );
  // "system" follows the browser live (changing its language re-renders)
  const browserLanguages = useSyncExternalStore(subscribeToBrowserLanguage, browserLanguagesSnapshot, () => '');
  const theme = useResolvedTheme(themePreference);
  const lang = translations[resolveLanguage(languagePreference, browserLanguages.split(','))];

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, languagePreference);
  }, [languagePreference]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, themePreference);
  }, [themePreference]);

  // the KSI colour tokens follow the resolved theme (.dark on <html>);
  // public/theme-init.js already set it before the first paint
  useEffect(() => {
    applyTheme(document.documentElement, theme);
  }, [theme]);

  // screen readers and spell checking follow the rendered language
  useEffect(() => {
    document.documentElement.lang = lang.htmlLang;
  }, [lang.htmlLang]);

  return { languagePreference, setLanguagePreference, themePreference, setThemePreference, lang, theme };
}
