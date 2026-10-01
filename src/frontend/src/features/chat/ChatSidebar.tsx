import type { RefObject } from 'react';
import { LogOut, Plus, Trash2, X } from 'lucide-react';
import ksiLogo from '../../assets/logo-ksi.svg';
import type { AuthUser } from '../auth/useAuth';
import { isDarkTheme, type ThemeStyle } from '../preferences/themes';
import type { Preferences } from '../preferences/usePreferences';
import type { ConversationSummary } from './conversations';
import type { HistoryLimits } from './useChat';
import SettingsMenu from './SettingsMenu';

interface ChatSidebarProps {
  t: ThemeStyle;
  preferences: Preferences;
  user: AuthUser;
  conversations: ConversationSummary[];
  activeId: string | null;
  limits: HistoryLimits | null;
  historyError: boolean;
  onNewChat: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  // below md the sidebar is an off-canvas drawer
  drawerId: string;
  isDrawerOpen: boolean;
  closeButtonRef: RefObject<HTMLButtonElement | null>;
  onCloseDrawer: () => void;
}

export default function ChatSidebar({
  t,
  preferences,
  user,
  conversations,
  activeId,
  limits,
  historyError,
  onNewChat,
  onOpen,
  onDelete,
  onLogout,
  drawerId,
  isDrawerOpen,
  closeButtonRef,
  onCloseDrawer,
}: ChatSidebarProps) {
  const { lang } = preferences;
  const isDark = isDarkTheme(preferences.theme);

  const handleDelete = (id: string) => {
    if (window.confirm(lang.deleteConfirm)) onDelete(id);
  };

  const displayName = user.name || user.username || user.email || '';

  return (
    // mobile: fixed drawer, slid out and invisible (hidden from focus and
    // screen readers) while closed; md+: the static column as before
    <div
      id={drawerId}
      role={isDrawerOpen ? 'dialog' : undefined}
      aria-modal={isDrawerOpen || undefined}
      aria-label={isDrawerOpen ? lang.appTitle : undefined}
      className={`fixed inset-y-0 left-0 z-40 w-64 max-w-[85vw] flex ${t.sidebar} flex-col border-r
        transition-[translate,visibility] duration-200 motion-reduce:transition-none
        ${isDrawerOpen ? 'translate-x-0 visible' : '-translate-x-full invisible'}
        md:static md:z-auto md:max-w-none md:translate-x-0 md:visible md:transition-none`}
    >
      {/* logo + new chat */}
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <a
            href="https://ksi.sh"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 min-w-0 flex items-center gap-2.5 hover:opacity-80 transition-opacity"
            title={lang.ksiWebsite}
          >
            <div className={`flex items-center justify-center shrink-0 ${isDark ? 'bg-white rounded-full p-1 shadow-sm' : ''}`}>
              <img src={ksiLogo} alt="KSI" className="h-8 w-8 object-contain" />
            </div>
            <span className={`font-medium ${t.text} text-base tracking-tight`}>{lang.appTitle}</span>
          </a>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onCloseDrawer}
            className={`md:hidden p-1.5 rounded-md ${t.textMuted} ${t.hover}`}
            title={lang.closeMenu}
            aria-label={lang.closeMenu}
          >
            <X size={18} />
          </button>
        </div>

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
            const title = conversation.title ?? lang.untitled;
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
      <div className="p-3 space-y-0.5">
        <SettingsMenu t={t} preferences={preferences} />

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
