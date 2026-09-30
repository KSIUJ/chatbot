import type { AuthUser } from '../Auth/useAuth';
import { isDarkTheme, themeStyles } from './themes';
import { translations } from './languages';
import { useChat } from './useChat';
import { usePreferences } from './usePreferences';
import { useResolvedTheme } from './useResolvedTheme';
import ChatSidebar from './ChatSidebar';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';

interface ChatScreenProps {
  user: AuthUser;
  onLogout: () => void;
}

export default function ChatScreen({ user, onLogout }: ChatScreenProps) {
  const { language, setLanguage, themePreference, setThemePreference } = usePreferences();
  // "systemowy" becomes light/dark here, following the device
  const theme = useResolvedTheme(themePreference);
  const chat = useChat();

  const t = themeStyles[theme];
  const lang = translations[language];

  const reloadConversation = () => {
    if (chat.activeId !== null) void chat.openConversation(chat.activeId);
  };

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      <ChatSidebar
        t={t}
        lang={lang}
        isDark={isDarkTheme(theme)}
        user={user}
        conversations={chat.conversations}
        activeId={chat.activeId}
        limits={chat.limits}
        historyError={chat.historyError}
        language={language}
        themePreference={themePreference}
        onNewChat={chat.startNewChat}
        onOpen={(id) => void chat.openConversation(id)}
        onDelete={(id) => void chat.removeChat(id)}
        onLanguageChange={setLanguage}
        onThemeChange={setThemePreference}
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
