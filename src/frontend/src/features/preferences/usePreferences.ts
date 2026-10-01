import { useEffect, useState } from 'react';
import { LANGUAGE_STORAGE_KEY, parseLanguage, translations, type LangKey, type Translation } from './languages';
import { THEME_STORAGE_KEY, parseThemePreference, type ThemeKey, type ThemePreference } from './themes';
import { useResolvedTheme } from './useResolvedTheme';

export interface Preferences {
  language: LangKey;
  setLanguage: (language: LangKey) => void;
  themePreference: ThemePreference;
  setThemePreference: (preference: ThemePreference) => void;
  // strings of the chosen language
  lang: Translation;
  // theme to render ("systemowy" already resolved to light/dark)
  theme: ThemeKey;
}

// UI settings kept in the browser: interface language and theme preference.
export function usePreferences(): Preferences {
  const [language, setLanguage] = useState<LangKey>(() => parseLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY)));
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)),
  );
  const theme = useResolvedTheme(themePreference);
  const lang = translations[language];

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  }, [language]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, themePreference);
  }, [themePreference]);

  // screen readers and spell checking follow the chosen language
  useEffect(() => {
    document.documentElement.lang = lang.htmlLang;
  }, [lang.htmlLang]);

  return { language, setLanguage, themePreference, setThemePreference, lang, theme };
}
