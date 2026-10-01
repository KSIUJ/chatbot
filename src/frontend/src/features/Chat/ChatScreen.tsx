import type { AuthUser } from '../auth/useAuth';
import { themeStyles } from '../preferences/themes';
import type { Preferences } from '../preferences/usePreferences';
import { useChat } from './useChat';
import ChatSidebar from './ChatSidebar';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';

interface ChatScreenProps {
  user: AuthUser;
  preferences: Preferences;
  onLogout: () => void;
}

export default function ChatScreen({ user, preferences, onLogout }: ChatScreenProps) {
  const chat = useChat();
  const { lang } = preferences;
  const t = themeStyles[preferences.theme];

  const reloadConversation = () => {
    if (chat.activeId !== null) void chat.openConversation(chat.activeId);
  };

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      <ChatSidebar
        t={t}
        preferences={preferences}
        user={user}
        conversations={chat.conversations}
        activeId={chat.activeId}
        limits={chat.limits}
        historyError={chat.historyError}
        onNewChat={chat.startNewChat}
        onOpen={(id) => void chat.openConversation(id)}
        onDelete={(id) => void chat.removeChat(id)}
        onLogout={onLogout}
      />

      <div className="flex-1 flex flex-col h-screen relative overflow-hidden">
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
