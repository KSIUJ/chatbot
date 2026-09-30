import { useEffect, useState } from 'react';
import { LANGUAGE_STORAGE_KEY, parseLanguage, type LangKey } from './languages';
import { THEME_STORAGE_KEY, parseThemePreference, type ThemePreference } from './themes';

// UI settings kept in the browser: interface language and theme preference.
export function usePreferences() {
  const [language, setLanguage] = useState<LangKey>(() =>
    parseLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY)),
  );
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)),
  );

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  }, [language]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, themePreference);
  }, [themePreference]);

  return { language, setLanguage, themePreference, setThemePreference };
}
