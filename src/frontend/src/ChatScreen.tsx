import { useState, useEffect, useRef } from 'react';
import { Send, Bot, Plus, MessageSquare, Settings, UserCircle, Paperclip, Globe, Moon, ChevronRight, ArrowLeft, Check, X, FileText, Copy } from 'lucide-react';
import mojeLogo from './assets/logo-ksi-IBUoeAwm.svg'; 

// themes, only 4 for now - may add more later
const themeStyles = {
  jasny: {
    app: "bg-neutral-50",
    sidebar: "bg-white border-neutral-200",
    text: "text-neutral-900",
    textMuted: "text-neutral-500",
    hover: "hover:bg-neutral-100",
    active: "bg-neutral-200",
    botIcon: "bg-neutral-600",
    msgBox: "bg-white border-neutral-200 text-neutral-800",
    userMsgBox: "bg-neutral-800 text-white", // for user messages
    inputBox: "bg-white border-neutral-200 text-neutral-900 focus:ring-neutral-500/50",
    sendBtn: "bg-neutral-800 hover:bg-neutral-900 text-white",
    popover: "bg-white border-neutral-200 shadow-xl",
    copiedIcon: "text-neutral-800", // color for copied icon
  },
  ciemny: {
    app: "bg-[#121212]",
    sidebar: "bg-[#1a1a1a] border-neutral-800",
    text: "text-neutral-200",
    textMuted: "text-neutral-400",
    hover: "hover:bg-neutral-800",
    active: "bg-neutral-700",
    botIcon: "bg-neutral-500",
    msgBox: "bg-[#252525] border-0 text-neutral-100 shadow-md",
    userMsgBox: "bg-[#333333] border-0 text-neutral-100 shadow-md", 
    inputBox: "bg-[#1e1e1e] border-neutral-800 text-neutral-200 focus:ring-neutral-600/50",
    sendBtn: "bg-neutral-700 hover:bg-neutral-600 text-white",
    popover: "bg-[#2c2c2c] border-neutral-800 shadow-xl",
    copiedIcon: "text-blue-500", 
  },
  granatowy: {
    app: "bg-slate-900",
    sidebar: "bg-slate-950 border-slate-800",
    text: "text-slate-200",
    textMuted: "text-slate-400",
    hover: "hover:bg-slate-800",
    active: "bg-slate-700",
    botIcon: "bg-blue-600",
    msgBox: "bg-slate-800 border-0 text-slate-200",
    userMsgBox: "bg-blue-600 border-0 text-white",
    inputBox: "bg-slate-800 border-slate-700 text-slate-200 focus:ring-blue-500/50",
    sendBtn: "bg-blue-600 hover:bg-blue-500 text-white",
    popover: "bg-slate-800 border-slate-700 shadow-xl",
    copiedIcon: "text-blue-400", 
  },
  różowy: {
    app: "bg-pink-50",
    sidebar: "bg-pink-100 border-pink-200",
    text: "text-pink-950",
    textMuted: "text-pink-600",
    hover: "hover:bg-pink-200",
    active: "bg-pink-300",
    botIcon: "bg-pink-500",
    msgBox: "bg-white border-pink-200 text-pink-900",
    userMsgBox: "bg-pink-600 text-white",
    inputBox: "bg-white border-pink-200 text-pink-900 focus:ring-pink-400/50",
    sendBtn: "bg-pink-600 hover:bg-pink-500 text-white",
    popover: "bg-pink-50 border-pink-200 shadow-xl",
    copiedIcon: "text-pink-500", 
  }
};

// languages
const translations = {
  polski: {
    appTitle: "Chatbot WMiI",
    newChat: "Nowy czat",
    recent: "Ostatnie",
    chat1: "Zasady przyznawania stypendiów...",
    chat2: "Regulamin studiów WMiI",
    chat3: "Kontakt do dziekanatu",
    language: "Język",
    theme: "Motyw",
    settings: "Ustawienia",
    account: "Konto",
    botGreeting: "Cześć! Jestem wirtualnym asystentem Wydziału Matematyki i Informatyki. W czym mogę Ci dzisiaj pomóc?",
    botReply: "Jestem na razie wersją testową. Niedługo zyskam prawdziwą inteligencję! 🤖 (Oto długa wiadomość testowa, żebyś mogła sprawdzić, jak działa przypięty na górze przycisk kopiowania podczas przewijania ekranu w dół, a także drugi przycisk pojawiający się na samym końcu. Spróbuj dodać więcej takich wiadomości, by strona zrobiła się naprawdę bardzo długa!)", // test reply
    inputPlaceholder: "Zapytaj Chatbota",
    disclaimer: "Chatbot to AI i może popełniać błędy. Zweryfikuj ważne informacje na stronie wydziału.",
    copy: "Kopiuj",
    copied: "Skopiowano",
    themeNames: {
      jasny: "jasny",
      ciemny: "ciemny",
      granatowy: "granatowy",
      różowy: "różowy"
    }
  },
  angielski: {
    appTitle: "WMiI Chatbot",
    newChat: "New chat",
    recent: "Recent",
    chat1: "Scholarship rules...",
    chat2: "WMiI study regulations",
    chat3: "Dean's office contact",
    language: "Language",
    theme: "Theme",
    settings: "Settings",
    account: "Account",
    botGreeting: "Hello! I am the virtual assistant of the Faculty of Mathematics and Computer Science. How can I help you today?",
    botReply: "I am a test version for now. I will gain real intelligence soon! 🤖 (Here is a long test message so you can check how the sticky copy button works when scrolling down the screen, and the second one appearing at the very end. Try adding more messages like this to make the page really long!)", // test reply
    inputPlaceholder: "Ask Chatbot",
    disclaimer: "Chatbot is an AI and may make mistakes. Verify important information on the faculty website.",
    copy: "Copy",
    copied: "Copied",
    themeNames: {
      jasny: "light",
      ciemny: "dark",
      granatowy: "navy",
      różowy: "pink"
    }
  }
};

type ThemeKey = keyof typeof themeStyles;
type LangKey = keyof typeof translations;

// single message type with optional files array
type Message = {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  files?: File[];
};

export default function ChatScreen() {
  
  // states
  
  // setting menu either shown(true) or not(false)
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  
  // track in which submenu user is currently in
  const [settingsView, setSettingsView] = useState<'main' | 'language' | 'theme'>('main');
  
  // remembers choosen language, try to get from localStorage first
  const [selectedLanguage, setSelectedLanguage] = useState<LangKey>(() => {
    const saved = localStorage.getItem('chatLanguage');
    return (saved as LangKey) || 'polski';
  });
  
  // remembers choosen theme, try to get from localStorage first
  const [selectedTheme, setSelectedTheme] = useState<ThemeKey>(() => {
    const saved = localStorage.getItem('chatTheme');
    return (saved as ThemeKey) || 'jasny';
  });

  // chat states
  
  // input state
  const [inputText, setInputText] = useState('');
  
  // array of files waiting to be sent (preview area)
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  
  // array of messages - load from localStorage if exists!
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = localStorage.getItem('chatMessages');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error("Could not load messages", e);
      }
    }
    // fallback if nothing is saved
    const lang = (localStorage.getItem('chatLanguage') as LangKey) || 'polski';
    return [{ id: '1', sender: 'bot', text: translations[lang].botGreeting }];
  });
  
  // array to track ALL messages that have been copied
  const [copiedIds, setCopiedIds] = useState<string[]>([]);

  // refs
  const menuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null); // for auto-scrolling

  // local storage
  
  useEffect(() => {
    localStorage.setItem('chatLanguage', selectedLanguage);
  }, [selectedLanguage]);

  useEffect(() => {
    localStorage.setItem('chatTheme', selectedTheme);
  }, [selectedTheme]);

  useEffect(() => {
    // we map messages to remove actual File objects before saving to localStorage
    // (browsers can't easily stringify File objects)
    const messagesToSave = messages.map(msg => ({
      id: msg.id,
      sender: msg.sender,
      text: msg.text
      // skipping 'files' to avoid JSON errors
    }));
    localStorage.setItem('chatMessages', JSON.stringify(messagesToSave));
  }, [messages]);


  // other effects
  
  // update initial bot greeting if user changes language and no other messages exist
  useEffect(() => {
    if (messages.length === 1 && messages[0].id === '1') {
      setMessages([{ id: '1', sender: 'bot', text: translations[selectedLanguage].botGreeting }]);
    }
  }, [selectedLanguage]);

  // when the menuRef is shown and the user clicks outside if it, it automatically closes
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        // first close the menu, then switch to main view
        setShowSettingsMenu(false); 
        setSettingsView('main');    
      }
    }
    
    // add listener to the whole document if menu is open
    if (showSettingsMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    
    // cleanup function to remove listener
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showSettingsMenu]); 

  // auto-scroll to the bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);


  // helpers
  
  // toggle setting menu
  const toggleSettings = () => {
    setShowSettingsMenu(!showSettingsMenu);
    setSettingsView('main'); // always reset to main view on click
  };

  // new chat - resets messages array and staged files
  const handleNewChat = () => {
    setMessages([
      { id: Date.now().toString(), sender: 'bot', text: translations[selectedLanguage].botGreeting }
    ]);
    setInputText('');
    setStagedFiles([]);
    setCopiedIds([]); // clear copied states on new chat
  };

  // copy text to clipboard and permanently save its ID
  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    if (!copiedIds.includes(id)) {
      setCopiedIds(prev => [...prev, id]);
    }
  };

  // handle file input change
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const filesArray = Array.from(e.target.files);
      setStagedFiles(prev => [...prev, ...filesArray]);
    }
    e.target.value = ''; // reset input so same file can be selected again
  };

  // remove a file from staging area
  const removeStagedFile = (index: number) => {
    setStagedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // handle sending message
  const handleSendMessage = () => {
    if (!inputText.trim() && stagedFiles.length === 0) return; // do not send empty messages

    // add user message
    const newUserMsg: Message = { 
      id: Date.now().toString(), 
      sender: 'user', 
      text: inputText.trim(),
      files: stagedFiles.length > 0 ? stagedFiles : undefined
    };
    
    setMessages(prev => [...prev, newUserMsg]);
    setInputText('');
    setStagedFiles([]); // clear staging area

    // fake bot reply after 1 second
    setTimeout(() => {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: translations[selectedLanguage].botReply
      }]);
    }, 1000);
  };

  // allow sending with Enter key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSendMessage();
  };

  // get styles and texts based on states
  const t = themeStyles[selectedTheme];
  const lang = translations[selectedLanguage];
  
  // check if theme is dark to add white bg to logo
  const isDarkTheme = selectedTheme === 'ciemny' || selectedTheme === 'granatowy';

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      
      {/* left sidebar */}
      <div className={`hidden md:flex w-64 ${t.sidebar} flex-col border-r transition-colors duration-300`}>
        
        {/* logo + new chat button */}
        <div className="p-4 space-y-4">
          
          {/* clickable logo wrapper */}
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
          
          {/* new chat button with onClick */}
          <button 
            onClick={handleNewChat}
            className={`w-full flex items-center gap-2 ${t.text} ${t.hover} transition-colors font-medium py-1.5 px-2 rounded-md`}
          >
            <Plus size={16} />
            {lang.newChat}
          </button>
        </div>

        {/* 
        last chats
        <div className="flex-1 overflow-y-auto px-4 py-2">
            <p className={`text-[10px] tracking-wider ${t.textMuted} mb-2 uppercase font-medium`}>
              {lang.recent}
            </p>
            
            <div className="space-y-0.5">
            <button className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md ${t.text} ${t.hover} transition-colors text-xs text-left font-medium`}>
                <MessageSquare size={14} className="shrink-0" />
                <span className="truncate">{lang.chat1}</span>
            </button>
            
            <button className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md ${t.text} ${t.hover} transition-colors text-xs text-left font-medium`}>
                <MessageSquare size={14} className="shrink-0" />
                <span className="truncate">{lang.chat2}</span>
            </button>
            
            <button className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md ${t.text} ${t.hover} transition-colors text-xs text-left font-medium`}>
                <MessageSquare size={14} className="shrink-0" />
                <span className="truncate">{lang.chat3}</span>
            </button>
            </div>
        </div>
        */}

        {/* setting and profile */}
        <div className="p-3 space-y-0.5 mt-auto relative" ref={menuRef}>
          
          {/* settings menu */}
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
                </>
              )}

              {/* language options */}
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

              {/* theme options */}
              {settingsView === 'theme' && (
                <div className="flex flex-col">
                  <div className={`flex items-center gap-2 px-3 pb-2 pt-1 mb-1 border-b ${t.sidebar.includes('border') ? t.sidebar.split(' ')[1] : 'border-neutral-200'}`}>
                    <button onClick={() => setSettingsView('main')} className={`p-1 ${t.hover} rounded-full transition-colors`}>
                      <ArrowLeft size={16} className={t.textMuted} />
                    </button>
                    <span className="text-sm font-medium">{lang.theme}</span>
                  </div>
                  
                  {(['jasny', 'ciemny', 'granatowy', 'różowy'] as ThemeKey[]).map((themeOption) => (
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

            </div>
          )}

          {/* settings button */}
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
        </div>
        
      </div>

      {/* main chat view */}
      <div className="flex-1 flex flex-col h-screen relative overflow-hidden">
        
        <main className="flex-1 p-4 pt-8 overflow-y-auto space-y-6 scroll-smooth">
          {/* map messages */}
          {messages.map((msg) => {
            const isCopied = copiedIds.includes(msg.id);
            
            return (
              <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                
                {/* bot icon */}
                {msg.sender === 'bot' && (
                  <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
                    <Bot size={22} />
                  </div>
                )}

                {/* message wrapper for text, files and top action bar */}
                <div className="flex flex-col gap-2 max-w-[70%]">
                  
                  {/* render files if any */}
                  {msg.files && msg.files.length > 0 && (
                    <div className={`flex flex-wrap gap-2 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.files.map((file, i) => {
                        const fileUrl = URL.createObjectURL(file);
                        return file.type.startsWith('image/') ? (
                          <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" className="block cursor-pointer hover:opacity-80 transition-opacity">
                            <img src={fileUrl} alt="attachment" className="max-w-[200px] max-h-[200px] object-cover rounded-xl border border-neutral-200/20 shadow-sm" />
                          </a>
                        ) : (
                          <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" download={file.name} className={`flex items-center gap-2 p-3 rounded-xl shadow-sm cursor-pointer hover:opacity-80 transition-opacity ${msg.sender === 'user' ? t.userMsgBox : t.msgBox}`}>
                            <FileText size={18} />
                            <span className="text-sm font-medium truncate max-w-[150px]">{file.name}</span>
                          </a>
                        );
                      })}
                    </div>
                  )}

                  {/* render text and sticky/absolute copy button inside message box */}
                  {msg.text && (
                    <div className={`p-5 pr-14 relative rounded-2xl border shadow-sm text-[15px] leading-relaxed transition-colors duration-300 
                      ${msg.sender === 'user' ? `${t.userMsgBox} rounded-tr-sm` : `${t.msgBox} rounded-tl-sm`}`
                    }>
                      {msg.text}

                      {/* copy button fixed to top-right inside bot message box */}
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

                  {/* BOTTOM copy button - ONLY rendered if message is longer than 300 characters */}
                  {msg.sender === 'bot' && msg.text && msg.text.length > 300 && (
                    <div className="flex justify-end px-1 mt-1">
                      <button 
                        onClick={() => handleCopy(msg.text, msg.id)}
                        className={`transition-colors p-1.5 rounded-md ${
                          isCopied ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                        }`}
                        title={isCopied ? lang.copied : lang.copy}
                      >
                        {isCopied ? <Check size={16} /> : <Copy size={16} />}
                      </button>
                    </div>
                  )}
                  
                </div>

              </div>
            );
          })}
          {/* empty div for auto-scroll */}
          <div ref={messagesEndRef} />
        </main>
        
        <footer className="px-4 pb-8 bg-transparent">
          <div className="max-w-2xl mx-auto relative mb-4">
            
            {/* STAGED FILES PREVIEW (above input) */}
            {stagedFiles.length > 0 && (
              <div className="absolute bottom-full left-0 mb-3 flex flex-wrap gap-2 z-10 w-full">
                {stagedFiles.map((file, i) => (
                  <div key={i} className={`flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-full border shadow-sm text-xs font-medium ${t.msgBox}`}>
                    {file.type.startsWith('image/') ? (
                      <div className="h-5 w-5 rounded overflow-hidden shrink-0">
                        <img src={URL.createObjectURL(file)} alt="preview" className="h-full w-full object-cover" />
                      </div>
                    ) : (
                      <FileText size={14} className="shrink-0" />
                    )}
                    <span className="truncate max-w-[120px]">{file.name}</span>
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

            {/* input */}
            <input 
              type="text" 
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={lang.inputPlaceholder}
              className={`w-full pl-12 pr-14 py-4 border shadow-md rounded-full focus:ring-2 outline-none transition-all duration-300 ${t.inputBox}`}
            />
            
            {/* send button */}
            <button 
              onClick={handleSendMessage}
              className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 z-10 ${t.sendBtn}`}
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