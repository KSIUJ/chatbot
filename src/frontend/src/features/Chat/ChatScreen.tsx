import { Send, Bot, Plus, Settings, UserCircle, Paperclip, Globe, Moon, ChevronRight, ArrowLeft, Check, X, FileText, Copy, ThumbsUp, ThumbsDown, Sliders, LogOut } from 'lucide-react';
import mojeLogo from "../../assets/logo-ksi-IBUoeAwm.svg"; 

import { themeStyles } from './themes';
import { translations } from './languages';
import { useChat } from './useChat';

interface ChatScreenProps {
  onLogout?: () => void;
}

export default function ChatScreen({ onLogout }: ChatScreenProps) {
  const {
    showSettingsMenu,
    settingsView,
    setSettingsView,
    selectedLanguage,
    setSelectedLanguage,
    selectedTheme,
    setSelectedTheme,
    ragCount,
    setRagCount,
    inputText,
    setInputText,
    stagedFiles,
    messages,
    copiedIds,
    reactions,
    isTyping, 
    menuRef,
    messagesEndRef,
    toggleSettings,
    handleLogout,
    handleNewChat,
    handleCopy,
    handleReaction,
    handleFileChange,
    removeStagedFile,
    handleSendMessage,
    handleKeyDown
  } = useChat(onLogout);

  const t = themeStyles[selectedTheme];
  const lang = translations[selectedLanguage];
  const isDarkTheme = selectedTheme === 'ciemny' || selectedTheme === 'granatowy';

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      
      {/* left sidebar */}
      <div className={`hidden md:flex w-64 ${t.sidebar} flex-col border-r transition-colors duration-300`}>
        
        <div className="p-4 space-y-4">
          <a 
            href="KSI_LOGO" 
            target="_blank" 
            rel="noopener noreferrer"
            className="flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity"
            title="Przejdź na stronę koła"
          >
            <div className={`flex items-center justify-center shrink-0 transition-colors duration-300 ${isDarkTheme ? 'bg-white rounded-full p-1 shadow-sm' : ''}`}>
              <img src={mojeLogo} alt="Logo KSI" className="h-8 w-8 object-contain" />
            </div>
            <span className={`font-medium ${t.text} text-base tracking-tight transition-colors`}>{lang.appTitle}</span>
          </a>
          
          <button 
            onClick={handleNewChat}
            className={`w-full flex items-center gap-2 ${t.text} ${t.hover} transition-colors font-medium py-1.5 px-2 rounded-md`}
          >
            <Plus size={16} />
            {lang.newChat}
          </button>
        </div>

        {/* setting and profile */}
        <div className="p-3 space-y-0.5 mt-auto relative" ref={menuRef}>
          
          {showSettingsMenu && (
            <div className={`absolute bottom-full left-3 mb-2 w-56 ${t.popover} border rounded-2xl py-2 z-50 ${t.text} transition-colors duration-200`}>
              
              {settingsView === 'main' && (
                <>
                  <button 
                    onClick={() => setSettingsView('language')}
                    className={`w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`}
                  >
                    <div className="flex items-center gap-3">
                      <Globe size={18} className={t.textMuted} />
                      <span>{lang.language}</span>
                    </div>
                    <ChevronRight size={16} className={t.textMuted} />
                  </button>
                  
                  <button 
                    onClick={() => setSettingsView('theme')}
                    className={`w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`}
                  >
                    <div className="flex items-center gap-3">
                      <Moon size={18} className={t.textMuted} />
                      <span>{lang.theme}</span>
                    </div>
                    <ChevronRight size={16} className={t.textMuted} />
                  </button>

                  <button 
                    onClick={() => setSettingsView('rag')}
                    className={`w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`}
                  >
                    <div className="flex items-center gap-3">
                      <Sliders size={18} className={t.textMuted} />
                      <span>{lang.ragContexts}</span>
                    </div>
                    <ChevronRight size={16} className={t.textMuted} />
                  </button>
                </>
              )}

              {settingsView === 'language' && (
                <div className="flex flex-col">
                  <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.sidebar.includes('border') ? t.sidebar.split(' ')[1] : 'border-neutral-200'}`}>
                    <button onClick={() => setSettingsView('main')} className={`p-1 ${t.hover} rounded-full transition-colors`}>
                      <ArrowLeft size={16} className={t.textMuted} />
                    </button>
                    <span className="text-sm font-medium">{lang.language}</span>
                  </div>
                  
                  <button onClick={() => setSelectedLanguage('polski')} className={`w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`}>
                    <span>Polski</span>
                    {selectedLanguage === 'polski' && <Check size={16} />}
                  </button>
                  <button onClick={() => setSelectedLanguage('angielski')} className={`w-full flex items-center justify-between px-4 py-2.5 ${t.hover} transition-colors text-sm text-left`}>
                    <span>English</span>
                    {selectedLanguage === 'angielski' && <Check size={16} />}
                  </button>
                </div>
              )}

              {settingsView === 'theme' && (
                <div className="flex flex-col">
                  <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.sidebar.includes('border') ? t.sidebar.split(' ')[1] : 'border-neutral-200'}`}>
                    <button onClick={() => setSettingsView('main')} className={`p-1 ${t.hover} rounded-full transition-colors`}>
                      <ArrowLeft size={16} className={t.textMuted} />
                    </button>
                    <span className="text-sm font-medium">{lang.theme}</span>
                  </div>
                  
                  {(['jasny', 'ciemny', 'granatowy', 'różowy'] as const).map((themeOption) => (
                    <button 
                      key={themeOption}
                      onClick={() => setSelectedTheme(themeOption)} 
                      className={`w-full flex items-center justify-between px-4 py-2 ${t.hover} transition-colors text-sm text-left capitalize`}
                    >
                      <span>{lang.themeNames[themeOption]}</span>
                      {selectedTheme === themeOption && <Check size={16} />}
                    </button>
                  ))}
                </div>
              )}

              {settingsView === 'rag' && (
                <div className="flex flex-col">
                  <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.sidebar.includes('border') ? t.sidebar.split(' ')[1] : 'border-neutral-200'}`}>
                    <button onClick={() => setSettingsView('main')} className={`p-1 ${t.hover} rounded-full transition-colors`}>
                      <ArrowLeft size={16} className={t.textMuted} />
                    </button>
                    <span className="text-sm font-medium">{lang.ragContexts}</span>
                  </div>
                  
                  <div className="px-4 py-3 flex flex-col gap-2">
                    <div className="flex justify-between text-xs font-medium">
                      <span>Liczba kontekstów:</span>
                      <span className="font-bold">{ragCount}</span>
                    </div>
                    <input 
                      type="range" 
                      min="1" 
                      max="15" 
                      value={ragCount}
                      onChange={(e) => setRagCount(parseInt(e.target.value, 10))}
                      className="w-full accent-neutral-500 cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] opacity-60">
                      <span>1</span>
                      <span>5 (default)</span>
                      <span>15</span>
                    </div>
                  </div>
                </div>
              )}

            </div>
          )}

          <button 
            onClick={toggleSettings}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs text-left font-medium ${
              showSettingsMenu ? `${t.active} ${t.text}` : `${t.text} ${t.hover}`
            }`}
          >
              <Settings size={15} />
              <span>{lang.settings}</span>
          </button>
          
          <button className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs text-left font-medium ${t.text} ${t.hover}`}>
              <UserCircle size={15} />
              <span>{lang.account}</span>
          </button>

          <button 
            onClick={handleLogout}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs text-left font-medium text-red-500 hover:bg-red-500/10`}
          >
              <LogOut size={15} />
              <span>{lang.logout}</span>
          </button>
        </div>
        
      </div>

      <div className="flex-1 flex flex-col h-screen relative overflow-hidden">
        
        <main className="flex-1 p-4 pt-8 overflow-y-auto space-y-6 scroll-smooth">
          {messages.map((msg) => {
            const isCopied = copiedIds.includes(msg.id);
            const currentReaction = reactions[msg.id];
            
            return (
              <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                
                {/* bot icon - TODO: make a new one */}
                {msg.sender === 'bot' && (
                  <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
                    <Bot size={22} />
                  </div>
                )}

                <div className="flex flex-col gap-2 max-w-[70%]">
                  
                  {msg.files && msg.files.length > 0 && (
                    <div className={`flex flex-wrap gap-2 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.files.map((file: File, i: number) => {
                        const fileUrl = URL.createObjectURL(file);
                        return file.type.startsWith('image/') ? (
                          <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" className="block cursor-pointer hover:opacity-80 transition-opacity">
                            <img src={fileUrl} alt="attachment" className="max-w-50 max-h-50 object-cover rounded-xl border border-neutral-200/20 shadow-sm" />
                          </a>
                        ) : (
                          <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" download={file.name} className={`flex items-center gap-2 p-3 rounded-xl shadow-sm cursor-pointer hover:opacity-80 transition-opacity ${msg.sender === 'user' ? t.userMsgBox : t.msgBox}`}>
                            <FileText size={18} />
                            <span className="text-sm font-medium truncate max-w-37.5">{file.name}</span>
                          </a>
                        );
                      })}
                    </div>
                  )}

                  {msg.text && (
                    <div className={`p-5 pr-14 relative rounded-2xl border shadow-sm text-[15px] leading-relaxed transition-colors duration-300 
                      ${msg.sender === 'user' ? `${t.userMsgBox} rounded-tr-sm` : `${t.msgBox} rounded-tl-sm`}`
                    }>
                      {msg.text}

                      {msg.sender === 'bot' && (
                        <button 
                          onClick={() => handleCopy(msg.text, msg.id)}
                          className={`absolute top-3 right-3 transition-colors p-1.5 rounded-md ${
                            isCopied ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                          }`}
                          title={isCopied ? lang.copied : lang.copy}
                        >
                          {isCopied ? <Check size={16} /> : <Copy size={16} />}
                        </button>
                      )} 
                    </div>
                  )}

                  {msg.sender === 'bot' && (
                    <div className="flex items-center gap-2 px-1 mt-0.5">
                      <button 
                        onClick={() => handleReaction(msg.id, 'up')}
                        className={`transition-colors p-1 rounded-md ${
                          currentReaction === 'up' ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                        }`}
                        title="To mi pomogło"
                      >
                        <ThumbsUp size={15} fill={currentReaction === 'up' ? "currentColor" : "none"} />
                      </button>
                      
                      <button 
                        onClick={() => handleReaction(msg.id, 'down')}
                        className={`transition-colors p-1 rounded-md ${
                          currentReaction === 'down' ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                        }`}
                        title="To mi nie pomogło"
                      >
                        <ThumbsDown size={15} fill={currentReaction === 'down' ? "currentColor" : "none"} />
                      </button>
                    </div>
                  )}
                  
                </div>
              </div>
            );
          })}

          {/* render three dots when waiting for response */}
          {isTyping && (
            <div className="flex gap-4 max-w-4xl mx-auto w-full">

              {/* bot icon - TODO: make a new one */}
              <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
                <Bot size={22} />
              </div>
              <div className="flex flex-col gap-2 max-w-[70%]">
                <div className={`px-5 py-6 relative rounded-2xl border shadow-sm transition-colors duration-300 ${t.msgBox} rounded-tl-sm flex items-center h-[52px]`}>
                  <div className="flex gap-1.5 items-center justify-center h-full">
                    <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                    <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                    <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '300ms' }}></span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </main>
        
        <footer className="px-4 pb-8 bg-transparent z-20">
          <div className="max-w-2xl mx-auto relative mb-4">
            
            {stagedFiles.length > 0 && (
              <div className="absolute bottom-full left-0 mb-3 flex flex-wrap gap-2 z-10 w-full">
                {stagedFiles.map((file: File, i: number) => (
                  <div key={i} className={`flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-full border shadow-sm text-xs font-medium ${t.msgBox}`}>
                    {file.type.startsWith('image/') ? (
                      <div className="h-5 w-5 rounded overflow-hidden shrink-0">
                        <img src={URL.createObjectURL(file)} alt="preview" className="h-full w-full object-cover" />
                      </div>
                    ) : (
                      <FileText size={14} className="shrink-0" />
                    )}
                    <span className="truncate max-w-30">{file.name}</span>
                    <button onClick={() => removeStagedFile(i)} className={`p-1 rounded-full ${t.hover} transition-colors`}>
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <input 
              type="file" 
              id="file-upload" 
              className="hidden" 
              multiple 
              onChange={handleFileChange}
            />

            <label 
              htmlFor="file-upload"
              className={`absolute left-2 top-1/2 -translate-y-1/2 p-2.5 ${t.textMuted} hover:${t.text} ${t.hover} rounded-full cursor-pointer transition-colors z-10`}
              title="Dołącz plik"
            >
              <Paperclip size={20} />
            </label>

            <input 
              type="text" 
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              
              placeholder={isTyping ? "Bot pisze..." : lang.inputPlaceholder}
              className={`w-full pl-12 pr-14 py-4 border shadow-md rounded-full focus:ring-2 outline-none transition-all duration-300 disabled:opacity-70 disabled:cursor-not-allowed ${t.inputBox}`}
            />
            
            <button 
              onClick={handleSendMessage}
              
              className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 z-10 disabled:opacity-50 disabled:cursor-not-allowed ${t.sendBtn}`}
            >
              <Send size={18} className="-translate-x-px translate-y-px" />
            </button>
            
          </div>
          
          <div className={`text-center text-[10px] ${t.textMuted} font-medium transition-colors`}>
            {lang.disclaimer}
          </div>
        </footer>

      </div>
    </div>
  );
}