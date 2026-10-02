import { useEffect, useId, useRef, useState } from 'react';
import { ArrowLeft, Check, ChevronRight, Globe, Moon, Settings } from 'lucide-react';
import { LANGUAGE_PREFERENCES, translations } from '../preferences/languages';
import { THEME_PREFERENCES, type ThemeStyle } from '../preferences/themes';
import type { Preferences } from '../preferences/usePreferences';

type SettingsView = 'closed' | 'main' | 'language' | 'theme';

interface SettingsMenuProps {
  t: ThemeStyle;
  preferences: Preferences;
}

// "Settings" button in the sidebar with a popover for language and theme.
export default function SettingsMenu({ t, preferences }: SettingsMenuProps) {
  const { lang, languagePreference, setLanguagePreference, themePreference, setThemePreference } = preferences;
  const [view, setView] = useState<SettingsView>('closed');
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();
  const isOpen = view !== 'closed';

  // close on a click outside or on Escape (focus goes back to the button)
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setView('closed');
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      // handled: the mobile drawer around this menu stays open
      event.preventDefault();
      setView('closed');
      buttonRef.current?.focus();
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [isOpen]);

  const menuItem = `w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`;

  const submenuHeader = (title: string) => (
    <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.border}`}>
      <button
        type="button"
        onClick={() => setView('main')}
        className={`p-1 ${t.hover} rounded-full`}
        aria-label={lang.back}
      >
        <ArrowLeft size={16} className={t.textMuted} />
      </button>
      <span className="text-sm font-medium">{title}</span>
    </div>
  );

  return (
    <div className="relative" ref={containerRef}>
      {isOpen && (
        <div
          id={popoverId}
          className={`absolute bottom-full left-0 mb-5 w-56 ${t.popover} border rounded-2xl py-2 z-50 ${t.text}`}
        >
          {view === 'main' && (
            <>
              <button type="button" onClick={() => setView('language')} className={menuItem}>
                <span className="flex items-center gap-3">
                  <Globe size={18} className={t.textMuted} />
                  {lang.language}
                </span>
                <ChevronRight size={16} className={t.textMuted} />
              </button>
              <button type="button" onClick={() => setView('theme')} className={menuItem}>
                <span className="flex items-center gap-3">
                  <Moon size={18} className={t.textMuted} />
                  {lang.theme}
                </span>
                <ChevronRight size={16} className={t.textMuted} />
              </button>
            </>
          )}

          {view === 'language' && (
            <div className="flex flex-col">
              {submenuHeader(lang.language)}
              {LANGUAGE_PREFERENCES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setLanguagePreference(option)}
                  className={menuItem}
                >
                  {option === 'system' ? (
                    <span>{lang.systemLanguage}</span>
                  ) : (
                    <span lang={translations[option].htmlLang}>{translations[option].languageName}</span>
                  )}
                  {languagePreference === option && <Check size={16} />}
                </button>
              ))}
            </div>
          )}

          {view === 'theme' && (
            <div className="flex flex-col">
              {submenuHeader(lang.theme)}
              {THEME_PREFERENCES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setThemePreference(option)}
                  className={`${menuItem} capitalize`}
                >
                  <span>{lang.themeNames[option]}</span>
                  {themePreference === option && <Check size={16} />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <button
        ref={buttonRef}
        type="button"
        onClick={() => setView(isOpen ? 'closed' : 'main')}
        aria-haspopup="true"
        aria-expanded={isOpen}
        aria-controls={isOpen ? popoverId : undefined}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs font-medium ${
          isOpen ? `${t.active} ${t.text}` : `${t.text} ${t.hover}`
        }`}
      >
        <Settings size={15} />
        {lang.settings}
      </button>
    </div>
  );
}
