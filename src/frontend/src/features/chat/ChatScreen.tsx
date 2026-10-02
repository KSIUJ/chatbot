import { useEffect, useId, useRef, useState } from 'react';
import { Menu } from 'lucide-react';
import AdminPanel from '../admin/AdminPanel';
import type { AuthUser } from '../auth/useAuth';
import type { Preferences } from '../preferences/usePreferences';
import { useChat } from './useChat';
import { useDrawer } from './useDrawer';
import ChatSidebar from './ChatSidebar';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';

interface ChatScreenProps {
  user: AuthUser;
  preferences: Preferences;
  onLogout: () => void;
}

export default function ChatScreen({ user, preferences, onLogout }: ChatScreenProps) {
  const { lang } = preferences;
  const chat = useChat(lang.htmlLang);
  const { isOpen: isDrawerOpen, open: openDrawer, close: closeDrawer, menuButtonRef, closeButtonRef } = useDrawer();
  const drawerId = useId();
  // full-screen admin view over the chat (admins only; the API checks it again)
  const [isAdminOpen, setIsAdminOpen] = useState(false);
  // element to focus again after leaving the admin view
  const adminOpenerRef = useRef<HTMLElement | null>(null);
  const wasAdminOpenRef = useRef(false);

  useEffect(() => {
    if (!isAdminOpen && wasAdminOpenRef.current) {
      const opener = adminOpenerRef.current;
      // the opener in a closed mobile drawer is not focusable - use the menu button
      if (opener !== null && opener.checkVisibility()) opener.focus();
      else menuButtonRef.current?.focus();
    }
    wasAdminOpenRef.current = isAdminOpen;
  }, [isAdminOpen, menuButtonRef]);

  const openAdmin = () => {
    adminOpenerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeDrawer();
    setIsAdminOpen(true);
  };

  const reloadConversation = () => {
    if (chat.activeId !== null) void chat.openConversation(chat.activeId);
  };

  // on mobile, picking a chat also closes the drawer
  const handleNewChat = () => {
    chat.startNewChat();
    closeDrawer();
  };

  const handleOpen = (id: string) => {
    void chat.openConversation(id);
    closeDrawer();
  };

  return (
    <>
      {isAdminOpen && <AdminPanel lang={lang} onClose={() => setIsAdminOpen(false)} />}
      {/* hidden (not unmounted) behind the admin view: a streamed answer keeps going */}
      <div className="flex h-dvh bg-page text-fg font-sans" hidden={isAdminOpen}>
        <ChatSidebar
          preferences={preferences}
          user={user}
          conversations={chat.conversations}
          activeId={chat.activeId}
          limits={chat.limits}
          historyError={chat.historyError}
          usage={chat.usage}
          onOpenAdmin={user.is_admin ? openAdmin : undefined}
          onNewChat={handleNewChat}
          onOpen={handleOpen}
          onDelete={(id) => void chat.removeChat(id)}
          onLogout={onLogout}
          drawerId={drawerId}
          isDrawerOpen={isDrawerOpen}
          closeButtonRef={closeButtonRef}
          onCloseDrawer={closeDrawer}
        />

        {/* dimmed page behind the open mobile drawer */}
        {isDrawerOpen && (
          <div className="fixed inset-0 z-30 bg-backdrop md:hidden" aria-hidden="true" onClick={closeDrawer} />
        )}

        {/* inert while the drawer is open: focus and screen readers stay in the drawer */}
        <div className="flex-1 min-w-0 flex flex-col h-dvh relative overflow-hidden" inert={isDrawerOpen}>
          {/* mobile top bar: the sidebar is a drawer below md */}
          <header className="md:hidden flex items-center gap-2 px-3 py-2 border-b border-line bg-surface">
            <button
              ref={menuButtonRef}
              type="button"
              onClick={openDrawer}
              aria-label={lang.openMenu}
              aria-expanded={isDrawerOpen}
              aria-controls={drawerId}
              className="p-2 rounded-control text-fg transition-colors hover:bg-surface-hover"
            >
              <Menu size={20} />
            </button>
            <span className="font-head text-base font-semibold text-fg truncate">{lang.appTitle}</span>
          </header>

          <ChatMessageList
            lang={lang}
            messages={chat.messages}
            isWaiting={chat.isWaiting}
            isLoading={chat.isLoadingConversation}
            loadError={chat.loadError}
            copiedId={chat.copiedId}
            feedbackErrorId={chat.feedbackErrorId}
            onCopy={chat.copy}
            onRate={chat.rate}
            onReport={chat.report}
            onRetry={() => void chat.retry()}
            onReload={reloadConversation}
          />
          <ChatInput lang={lang} isWaiting={chat.isWaiting} onSend={chat.send} onStop={chat.stop} />
        </div>
      </div>
    </>
  );
}
