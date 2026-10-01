import { useId } from 'react';
import { Menu } from 'lucide-react';
import type { AuthUser } from '../auth/useAuth';
import { themeStyles } from '../preferences/themes';
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
  const t = themeStyles[preferences.theme];

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
    <div className={`flex h-dvh ${t.app} font-sans transition-colors duration-300`}>
      <ChatSidebar
        t={t}
        preferences={preferences}
        user={user}
        conversations={chat.conversations}
        activeId={chat.activeId}
        limits={chat.limits}
        historyError={chat.historyError}
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
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" aria-hidden="true" onClick={closeDrawer} />
      )}

      {/* inert while the drawer is open: focus and screen readers stay in the drawer */}
      <div className="flex-1 min-w-0 flex flex-col h-dvh relative overflow-hidden" inert={isDrawerOpen}>
        {/* mobile top bar: the sidebar is a drawer below md */}
        <header className={`md:hidden flex items-center gap-2 px-3 py-2 border-b ${t.sidebar}`}>
          <button
            ref={menuButtonRef}
            type="button"
            onClick={openDrawer}
            aria-label={lang.openMenu}
            aria-expanded={isDrawerOpen}
            aria-controls={drawerId}
            className={`p-2 rounded-md ${t.text} ${t.hover}`}
          >
            <Menu size={20} />
          </button>
          <span className={`font-medium ${t.text} text-base tracking-tight truncate`}>{lang.appTitle}</span>
        </header>

        <ChatMessageList
          t={t}
          lang={lang}
          messages={chat.messages}
          isWaiting={chat.isWaiting}
          isLoading={chat.isLoadingConversation}
          loadError={chat.loadError}
          copiedId={chat.copiedId}
          onCopy={chat.copy}
          onRetry={() => void chat.retry()}
          onReload={reloadConversation}
        />
        <ChatInput t={t} lang={lang} isWaiting={chat.isWaiting} onSend={chat.send} onStop={chat.stop} />
      </div>
    </div>
  );
}
