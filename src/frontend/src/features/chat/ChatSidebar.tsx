import type { RefObject } from 'react';
import { LogOut, Plus, Trash2, X } from 'lucide-react';
import type { AuthUser } from '../auth/useAuth';
import type { Preferences } from '../preferences/usePreferences';
import type { ConversationSummary } from './conversations';
import type { HistoryLimits } from './useChat';
import SettingsMenu from './SettingsMenu';

interface ChatSidebarProps {
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
      className={`fixed inset-y-0 left-0 z-40 w-64 max-w-[85vw] flex flex-col bg-surface border-r border-line
        transition-[translate,visibility] duration-200 motion-reduce:transition-none
        ${isDrawerOpen ? 'translate-x-0 visible shadow-raised' : '-translate-x-full invisible'}
        md:static md:z-auto md:max-w-none md:translate-x-0 md:visible md:transition-none md:shadow-none`}
    >
      {/* logo + new chat */}
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <a
            href="https://ksi.sh"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 min-w-0 flex items-center gap-2.5 rounded-control"
            title={lang.ksiWebsite}
          >
            <span role="img" aria-label="KSI" className="ksi-logo block size-8 shrink-0" />
            <span className="font-head text-base font-semibold text-fg truncate">{lang.appTitle}</span>
          </a>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onCloseDrawer}
            className="md:hidden p-1.5 rounded-control text-muted transition-colors hover:bg-surface-hover hover:text-fg"
            title={lang.closeMenu}
            aria-label={lang.closeMenu}
          >
            <X size={18} />
          </button>
        </div>

        <button type="button" onClick={onNewChat} className="ksi-btn ksi-btn-secondary w-full justify-start">
          <Plus size={16} aria-hidden="true" />
          {lang.newChat}
        </button>
      </div>

      {/* history */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-3" aria-label={lang.recent}>
        <p className="px-2 pb-1.5 text-xs font-semibold uppercase tracking-[0.04em] text-muted">{lang.recent}</p>

        {historyError && <p className="px-2 py-1 text-label text-muted">{lang.historyError}</p>}
        {!historyError && conversations.length === 0 && (
          <p className="px-2 py-1 text-label text-muted">{lang.noChats}</p>
        )}

        <ul className="space-y-0.5">
          {conversations.map((conversation) => {
            const title = conversation.title ?? lang.untitled;
            const isActive = conversation.id === activeId;
            return (
              <li
                key={conversation.id}
                className={`group flex items-center rounded-control transition-colors ${
                  isActive ? 'bg-accent-soft' : 'hover:bg-surface-hover'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onOpen(conversation.id)}
                  className={`flex-1 min-w-0 text-left px-2 py-1.5 rounded-control text-sm truncate text-fg ${
                    isActive ? 'font-semibold' : ''
                  }`}
                  title={title}
                  aria-current={isActive ? 'true' : undefined}
                >
                  {title}
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(conversation.id)}
                  className="shrink-0 p-1.5 mr-1 rounded-control opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity text-muted hover:text-danger"
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
          <p className="px-2 pt-3 pb-2 text-[11px] leading-snug text-muted">
            {lang.historyNote(limits.maxPerUser, limits.retentionDays)}
          </p>
        )}
      </nav>

      {/* settings + account */}
      <div className="p-3 space-y-0.5">
        <SettingsMenu preferences={preferences} />

        {/* who is logged in */}
        <div className="px-2.5 pt-2 mt-1 border-t border-line">
          {displayName && (
            <p className="text-xs font-semibold truncate text-fg" title={displayName}>
              {displayName}
            </p>
          )}
          {user.email && user.email !== displayName && (
            <p className="text-[11px] truncate text-muted" title={user.email}>
              {user.email}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onLogout}
          className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-control transition-colors text-xs font-medium text-danger hover:bg-danger/10"
        >
          <LogOut size={15} aria-hidden="true" />
          {lang.logout}
        </button>
      </div>
    </div>
  );
}
