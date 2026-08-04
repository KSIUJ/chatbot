import { useEffect } from 'react';
import { themeStyles } from './themes';
import { translations } from './languages';
import { useChat } from './useChat';

import ChatSidebar from './ChatSidebar';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';

interface ChatScreenProps {
  onLogout?: () => void;
  onOpenProfile?: () => void;
}

export default function ChatScreen({ onLogout, onOpenProfile }: ChatScreenProps) {
  // states and logic extracted to custom hook
  const {
    showSettingsMenu, settingsView, setSettingsView, selectedLanguage, setSelectedLanguage,
    selectedTheme, setSelectedTheme, ragCount, setRagCount, inputText, setInputText,
    stagedFiles, messages, copiedIds, reactions, isTyping, menuRef, messagesEndRef,
    toggleSettings, handleLogout, handleNewChat, handleCopy, handleReaction,
    handleFileChange, removeStagedFile, handleSendMessage, handleKeyDown,
    handleStopGenerating, handleRegenerate, inputRef
  } = useChat(onLogout);

  // save theme to local storage
  useEffect(() => {
    localStorage.setItem('chat-theme', selectedTheme);
  }, [selectedTheme]);

  // get styles and texts based on states
  const t = themeStyles[selectedTheme];
  const lang = translations[selectedLanguage];
  
  // check if theme is dark to add white bg to logo
  const isDarkTheme = selectedTheme === 'ciemny' || selectedTheme === 'granatowy';

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      
      <ChatSidebar 
        isDarkTheme={isDarkTheme}
        t={t}
        lang={lang}
        handleNewChat={handleNewChat}
        menuRef={menuRef}
        showSettingsMenu={showSettingsMenu}
        settingsView={settingsView}
        setSettingsView={setSettingsView}
        selectedLanguage={selectedLanguage}
        setSelectedLanguage={setSelectedLanguage}
        selectedTheme={selectedTheme}
        setSelectedTheme={setSelectedTheme}
        ragCount={ragCount}
        setRagCount={setRagCount}
        toggleSettings={toggleSettings}
        onOpenProfile={onOpenProfile}
        handleLogout={handleLogout}
      />

      <div className="flex-1 flex flex-col h-screen relative overflow-hidden">
        <ChatMessageList 
          t={t}
          lang={lang}
          messages={messages}
          copiedIds={copiedIds}
          reactions={reactions}
          isTyping={isTyping}
          selectedLanguage={selectedLanguage}
          messagesEndRef={messagesEndRef}
          handleCopy={handleCopy}
          handleReaction={handleReaction}
          handleRegenerate={handleRegenerate}
        />
        
        <ChatInput 
          t={t}
          lang={lang}
          stagedFiles={stagedFiles}
          removeStagedFile={removeStagedFile}
          handleFileChange={handleFileChange}
          inputRef={inputRef}
          inputText={inputText}
          setInputText={setInputText}
          handleKeyDown={handleKeyDown}
          isTyping={isTyping}
          handleStopGenerating={handleStopGenerating}
          handleSendMessage={handleSendMessage}
        />
      </div>
    </div>
  );
}