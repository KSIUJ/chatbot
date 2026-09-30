import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, ChevronRight, Globe, LogOut, Moon, Plus, Settings, Trash2 } from 'lucide-react';
import ksiLogo from '../../assets/logo-ksi.svg';
import type { AuthUser } from '../Auth/useAuth';
import { conversationTitle, type ConversationSummary } from '../../lib/conversations';
import { THEME_PREFERENCES, type ThemePreference, type ThemeStyle } from './themes';
import type { LangKey, Translation } from './languages';
import type { HistoryLimits } from './useChat';

type SettingsView = 'closed' | 'main' | 'language' | 'theme';

const LANGUAGE_OPTIONS: readonly { key: LangKey; label: string }[] = [
  { key: 'polski', label: 'Polski' },
  { key: 'angielski', label: 'English' },
];

interface ChatSidebarProps {
  t: ThemeStyle;
  lang: Translation;
  isDark: boolean;
  user: AuthUser;
  conversations: ConversationSummary[];
  activeId: string | null;
  limits: HistoryLimits | null;
  historyError: boolean;
  language: LangKey;
  themePreference: ThemePreference;
  onNewChat: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onLanguageChange: (language: LangKey) => void;
  onThemeChange: (theme: ThemePreference) => void;
  onLogout: () => void;
}

export default function ChatSidebar({
  t, lang, isDark, user, conversations, activeId, limits, historyError, language, themePreference,
  onNewChat, onOpen, onDelete, onLanguageChange, onThemeChange, onLogout,
}: ChatSidebarProps) {
  const [settingsView, setSettingsView] = useState<SettingsView>('closed');
  const settingsRef = useRef<HTMLDivElement>(null);

  // close the settings popover on a click outside of it
  useEffect(() => {
    if (settingsView === 'closed') return;
    const handleClick = (event: MouseEvent) => {
      if (!settingsRef.current?.contains(event.target as Node)) setSettingsView('closed');
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [settingsView]);

  const handleDelete = (id: string) => {
    if (window.confirm(lang.deleteConfirm)) onDelete(id);
  };

  const displayName = user.name || user.username || user.email || '';
  const menuItem = `w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`;

  const submenuHeader = (title: string) => (
    <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.border}`}>
      <button type="button" onClick={() => setSettingsView('main')} className={`p-1 ${t.hover} rounded-full`} aria-label="Back">
        <ArrowLeft size={16} className={t.textMuted} />
      </button>
      <span className="text-sm font-medium">{title}</span>
    </div>
  );

  return (
    <div className={`hidden md:flex w-64 ${t.sidebar} flex-col border-r`}>
      {/* logo + new chat */}
      <div className="p-4 space-y-4">
        <a
          href="https://ksi.sh"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
          title="KSI"
        >
          <div className={`flex items-center justify-center shrink-0 ${isDark ? 'bg-white rounded-full p-1 shadow-sm' : ''}`}>
            <img src={ksiLogo} alt="KSI" className="h-8 w-8 object-contain" />
          </div>
          <span className={`font-medium ${t.text} text-base tracking-tight`}>{lang.appTitle}</span>
        </a>

        <button
          type="button"
          onClick={onNewChat}
          className={`w-full flex items-center gap-2 ${t.text} ${t.hover} transition-colors font-medium py-1.5 px-2 rounded-md`}
        >
          <Plus size={16} />
          {lang.newChat}
        </button>
      </div>

      {/* history */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-3" aria-label={lang.recent}>
        <p className={`px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider ${t.textMuted}`}>{lang.recent}</p>

        {historyError && <p className={`px-2 py-1 text-xs ${t.textMuted}`}>{lang.historyError}</p>}
        {!historyError && conversations.length === 0 && (
          <p className={`px-2 py-1 text-xs ${t.textMuted}`}>{lang.noChats}</p>
        )}

        <ul className="space-y-0.5">
          {conversations.map((conversation) => {
            const title = conversationTitle(conversation, lang.untitled);
            const isActive = conversation.id === activeId;
            return (
              <li key={conversation.id} className={`group flex items-center rounded-md ${isActive ? t.active : t.hover}`}>
                <button
                  type="button"
                  onClick={() => onOpen(conversation.id)}
                  className={`flex-1 min-w-0 text-left px-2 py-1.5 text-sm truncate ${t.text}`}
                  title={title}
                  aria-current={isActive ? 'true' : undefined}
                >
                  {title}
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(conversation.id)}
                  className={`shrink-0 p-1.5 mr-1 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity ${t.textMuted} hover:text-red-500`}
                  title={lang.deleteChat}
                  aria-label={`${lang.deleteChat}: ${title}`}
                >
                  <Trash2 size={14} />
                </button>
              </li>
            );
          })}
        </ul>

        {limits && (
          <p className={`px-2 pt-3 pb-2 text-[10px] leading-snug ${t.textMuted}`}>
            {lang.historyNote(limits.maxPerUser, limits.retentionDays)}
          </p>
        )}
      </nav>

      {/* settings + account */}
      <div className="p-3 space-y-0.5 relative" ref={settingsRef}>
        {settingsView !== 'closed' && (
          <div className={`absolute bottom-full left-3 mb-2 w-56 ${t.popover} border rounded-2xl py-2 z-50 ${t.text}`}>
            {settingsView === 'main' && (
              <>
                <button type="button" onClick={() => setSettingsView('language')} className={menuItem}>
                  <span className="flex items-center gap-3">
                    <Globe size={18} className={t.textMuted} />
                    {lang.language}
                  </span>
                  <ChevronRight size={16} className={t.textMuted} />
                </button>
                <button type="button" onClick={() => setSettingsView('theme')} className={menuItem}>
                  <span className="flex items-center gap-3">
                    <Moon size={18} className={t.textMuted} />
                    {lang.theme}
                  </span>
                  <ChevronRight size={16} className={t.textMuted} />
                </button>
              </>
            )}

            {settingsView === 'language' && (
              <div className="flex flex-col">
                {submenuHeader(lang.language)}
                {LANGUAGE_OPTIONS.map((option) => (
                  <button key={option.key} type="button" onClick={() => onLanguageChange(option.key)} className={menuItem}>
                    <span>{option.label}</span>
                    {language === option.key && <Check size={16} />}
                  </button>
                ))}
              </div>
            )}

            {settingsView === 'theme' && (
              <div className="flex flex-col">
                {submenuHeader(lang.theme)}
                {THEME_PREFERENCES.map((option) => (
                  <button key={option} type="button" onClick={() => onThemeChange(option)} className={`${menuItem} capitalize`}>
                    <span>{lang.themeNames[option]}</span>
                    {themePreference === option && <Check size={16} />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={() => setSettingsView(settingsView === 'closed' ? 'main' : 'closed')}
          className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs font-medium ${
            settingsView !== 'closed' ? `${t.active} ${t.text}` : `${t.text} ${t.hover}`
          }`}
        >
          <Settings size={15} />
          {lang.settings}
        </button>

        {/* who is logged in */}
        <div className={`px-2.5 pt-2 mt-1 border-t ${t.border}`}>
          {displayName && <p className={`text-xs font-medium truncate ${t.text}`} title={displayName}>{displayName}</p>}
          {user.email && user.email !== displayName && (
            <p className={`text-[11px] truncate ${t.textMuted}`} title={user.email}>{user.email}</p>
          )}
        </div>

        <button
          type="button"
          onClick={onLogout}
          className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs font-medium text-red-500 hover:bg-red-500/10"
        >
          <LogOut size={15} />
          {lang.logout}
        </button>
      </div>
    </div>
  );
}
