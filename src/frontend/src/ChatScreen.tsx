import { useState, useEffect, useRef } from 'react';
import { Send, Bot, Plus, MessageSquare, Settings, UserCircle, Paperclip, Globe, Moon, ChevronRight, ArrowLeft, Check } from 'lucide-react';
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
    inputBox: "bg-white border-neutral-200 text-neutral-900 focus:ring-neutral-500/50",
    sendBtn: "bg-neutral-800 hover:bg-neutral-900 text-white",
    popover: "bg-white border-neutral-200 shadow-xl",
  },
  ciemny: {
    app: "bg-[#121212]",
    sidebar: "bg-[#1a1a1a] border-neutral-800",
    text: "text-neutral-200",
    textMuted: "text-neutral-400",
    hover: "hover:bg-neutral-800",
    active: "bg-neutral-700",
    botIcon: "bg-neutral-500",
    msgBox: "bg-[#1e1e1e] border-neutral-800 text-neutral-200",
    inputBox: "bg-[#1e1e1e] border-neutral-800 text-neutral-200 focus:ring-neutral-600/50",
    sendBtn: "bg-neutral-700 hover:bg-neutral-600 text-white",
    popover: "bg-[#2c2c2c] border-neutral-800 shadow-xl",
  },
  granatowy: {
    app: "bg-slate-900",
    sidebar: "bg-slate-950 border-slate-800",
    text: "text-slate-200",
    textMuted: "text-slate-400",
    hover: "hover:bg-slate-800",
    active: "bg-slate-700",
    botIcon: "bg-blue-600",
    msgBox: "bg-slate-800 border-slate-700 text-slate-200",
    inputBox: "bg-slate-800 border-slate-700 text-slate-200 focus:ring-blue-500/50",
    sendBtn: "bg-blue-600 hover:bg-blue-500 text-white",
    popover: "bg-slate-800 border-slate-700 shadow-xl",
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
    inputBox: "bg-white border-pink-200 text-pink-900 focus:ring-pink-400/50",
    sendBtn: "bg-pink-600 hover:bg-pink-500 text-white",
    popover: "bg-pink-50 border-pink-200 shadow-xl",
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
    inputPlaceholder: "Zapytaj Chatbota",
    disclaimer: "Chatbot to AI i może popełniać błędy. Zweryfikuj ważne informacje na stronie wydziału.",
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
    inputPlaceholder: "Ask Chatbot",
    disclaimer: "Chatbot is an AI and may make mistakes. Verify important information on the faculty website.",
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

export default function ChatScreen() {
  
  // STATES
  
  // setting menu either shown(true) or not(false)
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  
  // track in which submenu user is currently in
  const [settingsView, setSettingsView] = useState<'main' | 'language' | 'theme'>('main');
  
  // remembers choosen language, default: Polish - change to english??
  const [selectedLanguage, setSelectedLanguage] = useState<LangKey>('polski');
  
  // remembers choosen theme, default: light
  const [selectedTheme, setSelectedTheme] = useState<ThemeKey>('jasny');

  // REFS
  const menuRef = useRef<HTMLDivElement>(null);

  // EFFECTS
  // when the menuRef is shown and the user clicks outside if it, it automatically closes
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        // first close the menu, then switch to main view
        setShowSettingsMenu(false); 
        setSettingsView('main');    
      }
    }
    
    // only if the menu is shown, we check for mouse clicks outside of it
    if (showSettingsMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    
    // when the menu closes
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showSettingsMenu]); 

  const toggleSettings = () => {
    setShowSettingsMenu(!showSettingsMenu); 
    setSettingsView('main'); // resets to main view
  };

  // set correct theme and language
  const t = themeStyles[selectedTheme];
  const lang = translations[selectedLanguage];
  
  // helper function to check if dark theme is choosen - if yes, then KSI logo is shown on a white circle, otherwise it wont be visible
  const isDarkTheme = selectedTheme === 'ciemny' || selectedTheme === 'granatowy';

  return (
    <div className={`flex h-screen ${t.app} font-sans transition-colors duration-300`}>
      
      {/* left sidebar */}
      <div className={`hidden md:flex w-64 ${t.sidebar} flex-col border-r transition-colors duration-300`}>
        
        {/* logo + new chat button */}
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-2.5">
            <div className={`flex items-center justify-center shrink-0 transition-colors duration-300 ${isDarkTheme ? 'bg-white rounded-full p-1 shadow-sm' : ''}`}>
              <img src={mojeLogo} alt="Logo KSI" className="h-8 w-8 object-contain" />
            </div>
            
            <span className={`font-medium ${t.text} text-base tracking-tight transition-colors`}>{lang.appTitle}</span>
          </div>
          
          <button className={`w-full flex items-center gap-2 ${t.text} ${t.hover} transition-colors font-medium py-1.5 px-2 rounded-md`}>
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
      <div className="flex-1 flex flex-col h-screen relative">
        
        <main className="flex-1 p-4 pt-8 overflow-y-auto space-y-6">
          <div className="flex gap-4 max-w-4xl mx-auto w-full">
            {/* bot icon - TODO change for a different one, either sth simple or draw by hand, each theme has a different bot icon */}
            <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
              <Bot size={22} />
            </div>
            {/* messages icon */}
            <div className={`p-5 rounded-2xl rounded-tl-sm border shadow-sm text-[15px] leading-relaxed max-w-[60%] transition-colors duration-300 ${t.msgBox}`}>
              {lang.botGreeting}
            </div>
          </div>
        </main>
        
        <footer className="px-4 pb-8 bg-transparent">
          <div className="max-w-2xl mx-auto relative mb-4">
            <input 
              type="file" 
              id="file-upload" 
              className="hidden" 
              multiple 
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
              placeholder={lang.inputPlaceholder}
              className={`w-full pl-12 pr-14 py-4 border shadow-md rounded-full focus:ring-2 outline-none transition-all duration-300 ${t.inputBox}`}
            />
            
            {/* send button */}
            <button className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 z-10 ${t.sendBtn}`}>
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