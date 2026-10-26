import { useEffect, useId, useRef, useState } from 'react';
import { ArrowLeft, Check, ChevronRight, Globe, GraduationCap, Moon, Settings, ShieldCheck } from 'lucide-react';
import { LANGUAGE_PREFERENCES, translations } from '../preferences/languages';
import { THEME_PREFERENCES } from '../preferences/themes';
import type { Preferences } from '../preferences/usePreferences';
import UsosSettings from '../usos/UsosSettings';
import { isUsosVisible } from '../usos/usos';
import { useUsos } from '../usos/useUsos';

type SettingsView = 'closed' | 'main' | 'language' | 'theme' | 'usos';

interface SettingsMenuProps {
  preferences: Preferences;
  // only for the admin group: opens the admin panel
  onOpenAdmin?: () => void;
}

// "Settings" button in the sidebar with a popover for language, theme and the
// USOS link (and the admin panel entry for admins).
export default function SettingsMenu({ preferences, onOpenAdmin }: SettingsMenuProps) {
  const usos = useUsos();
  const {
    lang,
    languagePreference,
    setLanguagePreference,
    themePreference,
    setThemePreference,
    occasionThemes,
    setOccasionThemes,
    themeForced,
  } = preferences;
  const [view, setView] = useState<SettingsView>('closed');
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();
  const isOpen = view !== 'closed';
  // hidden while the feature is off and there is no link to remove
  const showUsos = isUsosVisible(usos.status);
  // after disconnecting with the feature off the submenu has nothing left - back to the main view
  const shownView: SettingsView = view === 'usos' && !showUsos ? 'main' : view;

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

  const menuItem = 'w-full flex items-center justify-between px-3.5 py-2 text-sm text-left text-fg transition-colors hover:bg-surface-hover';

  // focus goes back to the Settings button first, so closing the panel can return to it
  const openAdmin = () => {
    buttonRef.current?.focus();
    setView('closed');
    onOpenAdmin?.();
  };

  // a confirmation left open earlier does not come back on its own
  const openUsos = () => {
    if (usos.phase === 'confirmDisconnect') usos.cancelDisconnect();
    setView('usos');
  };

  const submenuHeader = (title: string) => (
    <div className="flex items-center gap-2 px-2.5 pb-1.5 pt-0.5 mb-1 border-b border-line">
      <button
        type="button"
        onClick={() => setView('main')}
        className="p-1 rounded-control text-muted transition-colors hover:bg-surface-hover hover:text-fg"
        aria-label={lang.back}
      >
        <ArrowLeft size={16} />
      </button>
      <span className="text-sm font-semibold">{title}</span>
    </div>
  );

  return (
    <div className="relative" ref={containerRef}>
      {isOpen && (
        <div
          id={popoverId}
          className={`absolute bottom-full left-0 mb-2 rounded-card border border-line bg-surface py-1.5 text-fg shadow-raised z-50 ${
            shownView === 'usos'
              ? 'w-[min(20rem,calc(100vw-1.5rem))] max-h-[calc(100dvh-6rem)] overflow-y-auto'
              : 'w-56'
          }`}
        >
          {shownView === 'main' && (
            <>
              <button type="button" onClick={() => setView('language')} className={menuItem}>
                <span className="flex items-center gap-3">
                  <Globe size={16} className="text-muted" aria-hidden="true" />
                  {lang.language}
                </span>
                <ChevronRight size={16} className="text-muted" aria-hidden="true" />
              </button>
              <button type="button" onClick={() => setView('theme')} className={menuItem}>
                <span className="flex items-center gap-3">
                  <Moon size={16} className="text-muted" aria-hidden="true" />
                  {lang.theme}
                </span>
                <ChevronRight size={16} className="text-muted" aria-hidden="true" />
              </button>
              {showUsos && (
                <button type="button" onClick={openUsos} className={menuItem}>
                  <span className="flex items-center gap-3">
                    <GraduationCap size={16} className="text-muted" aria-hidden="true" />
                    {lang.usos.title}
                  </span>
                  <ChevronRight size={16} className="text-muted" aria-hidden="true" />
                </button>
              )}
              {onOpenAdmin && (
                <button type="button" onClick={openAdmin} className={`${menuItem} border-t border-line mt-1 pt-2.5`}>
                  <span className="flex items-center gap-3">
                    <ShieldCheck size={16} className="text-muted" aria-hidden="true" />
                    {lang.admin.title}
                  </span>
                </button>
              )}
            </>
          )}

          {shownView === 'usos' && usos.status !== null && (
            <div className="flex flex-col">
              {submenuHeader(lang.usos.title)}
              <UsosSettings
                t={lang.usos}
                cancelLabel={lang.cancel}
                locale={lang.htmlLang}
                status={usos.status}
                phase={usos.phase}
                error={usos.error}
                onConnect={usos.connect}
                onAskDisconnect={usos.askDisconnect}
                onCancelDisconnect={usos.cancelDisconnect}
                onDisconnect={usos.disconnect}
              />
            </div>
          )}

          {shownView === 'language' && (
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
                  {languagePreference === option && <Check size={16} className="text-accent" aria-hidden="true" />}
                </button>
              ))}
            </div>
          )}

          {shownView === 'theme' && (
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
                  {themePreference === option && <Check size={16} className="text-accent" aria-hidden="true" />}
                </button>
              ))}
              {themeForced && <p className="px-3.5 pt-1 pb-1.5 text-xs text-muted">{lang.occasionForcedDark}</p>}
              <button
                type="button"
                onClick={() => setOccasionThemes(!occasionThemes)}
                aria-pressed={occasionThemes}
                className={`${menuItem} border-t border-line mt-1 pt-2.5`}
              >
                <span>{lang.occasionThemes}</span>
                {occasionThemes && <Check size={16} className="text-accent" aria-hidden="true" />}
              </button>
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
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-control transition-colors text-xs font-medium text-fg ${
          isOpen ? 'bg-accent-soft' : 'hover:bg-surface-hover'
        }`}
      >
        <Settings size={15} aria-hidden="true" />
        {lang.settings}
      </button>
    </div>
  );
}
