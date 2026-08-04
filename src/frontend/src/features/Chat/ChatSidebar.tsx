import { Plus, Settings, UserCircle, Globe, Moon, ChevronRight, ArrowLeft, Check, Sliders, LogOut } from 'lucide-react';
import mojeLogo from "../../assets/logo-ksi-IBUoeAwm.svg"; 

interface ChatSidebarProps {
  isDarkTheme: boolean;
  t: any;
  lang: any;
  handleNewChat: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>; 
  showSettingsMenu: boolean;
  settingsView: string;
  setSettingsView: any; 
  selectedLanguage: string;
  setSelectedLanguage: any; 
  selectedTheme: string;
  setSelectedTheme: any; 
  ragCount: number;
  setRagCount: (count: number) => void;
  toggleSettings: () => void;
  onOpenProfile?: () => void;
  handleLogout: () => void;
}

export default function ChatSidebar(props: ChatSidebarProps) {
  const {
    isDarkTheme, t, lang, handleNewChat, menuRef, showSettingsMenu, settingsView,
    setSettingsView, selectedLanguage, setSelectedLanguage, selectedTheme, setSelectedTheme,
    ragCount, setRagCount, toggleSettings, onOpenProfile, handleLogout
  } = props;

  return (
    <div className={`hidden md:flex w-64 ${t.sidebar} flex-col border-r transition-colors duration-300`}>
      {/* logo + new chat button */}
      <div className="p-4 space-y-4">
        {/* clickable logo wrapper */}
        <a 
          href="https://ksi.sh"  // link to KSI website
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity"
          title="KSI website"
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

            {/* RAG contexts options */}
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
        
        <button 
          onClick={onOpenProfile}
          className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs text-left font-medium ${t.text} ${t.hover}`}
        >
            <UserCircle size={15} />
            <span>{lang.account}</span>
        </button>

        {/* logout button */}
        <button 
          onClick={handleLogout}
          className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md transition-colors text-xs text-left font-medium text-red-500 hover:bg-red-500/10`}
        >
            <LogOut size={15} />
            <span>{lang.logout}</span>
        </button>
      </div>
    </div>
  );
}