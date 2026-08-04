interface ProfileScreenProps {
  email: string;
  onClose: () => void;
  onLogout: () => void;
  selectedTheme: string;
}

export default function ProfileScreen({ email, onClose, onLogout, selectedTheme }: ProfileScreenProps) {
  // get name and surname from email
  const getNameFromEmail = (mail: string) => {
    if (!mail) return 'User';
    const localPart = mail.split('@')[0];
    const parts = localPart.split(/[._]/);
    
    return parts
      .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
  };

  const fullName = getNameFromEmail(email);

  // setup colors including outer page background for each theme
  const getThemeStyles = (theme: string) => {
    switch (theme) {
      case 'ciemny':
        return {
          pageBg: 'bg-black',
          bg: 'bg-neutral-900',
          text: 'text-neutral-100',
          headingText: 'text-white', // brighter text for heading
          muted: 'text-neutral-400',
          border: 'border-neutral-800',
          hover: 'hover:bg-neutral-800',
          avatarBg: 'bg-neutral-800',
          avatarText: 'text-white'
        };
      case 'różowy':
        return {
          pageBg: 'bg-pink-100',
          bg: 'bg-pink-50',
          text: 'text-pink-900',
          headingText: 'text-pink-950',
          muted: 'text-pink-600',
          border: 'border-pink-200',
          hover: 'hover:bg-pink-100',
          avatarBg: 'bg-pink-200',
          avatarText: 'text-pink-700'
        };
      case 'granatowy':
        return {
          pageBg: 'bg-slate-950',
          bg: 'bg-indigo-950',
          text: 'text-indigo-50',
          headingText: 'text-white', // brighter text for heading
          muted: 'text-indigo-300',
          border: 'border-indigo-800/50',
          hover: 'hover:bg-indigo-900',
          avatarBg: 'bg-indigo-900',
          avatarText: 'text-indigo-200'
        };
      case 'jasny':
      default:
        return {
          pageBg: 'bg-slate-50',
          bg: 'bg-white',
          text: 'text-slate-900',
          headingText: 'text-slate-900',
          muted: 'text-slate-500',
          border: 'border-slate-200',
          hover: 'hover:bg-slate-50',
          avatarBg: 'bg-indigo-100',
          avatarText: 'text-indigo-600'
        };
    }
  };

  const styles = getThemeStyles(selectedTheme);

  return (
    // main wrapper covering full screen with base background color
    <div className={`min-h-screen w-full transition-colors duration-300 ${styles.pageBg} ${styles.text}`}>
      
      {/* inner container to limit width and center content */}
      <div className="flex flex-col h-full w-full max-w-2xl mx-auto p-6">
        
        {/* top navigation bar - relative wrapper to perfectly center title */}
        <div className="relative flex items-center justify-center mb-8 w-full">
          <h2 className={`text-3xl font-bold tracking-tight ${styles.headingText}`}>Profile</h2>
          <button 
            onClick={onClose}
            className={`absolute right-0 p-2 rounded-lg ${styles.hover} transition-colors ${styles.muted}`}
          >
            {/* back or close icon */}
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* main profile card */}
        <div className={`flex flex-col rounded-2xl border ${styles.border} ${styles.bg} overflow-hidden shadow-sm`}>
          
          {/* profile header info */}
          <div className={`p-8 flex flex-col items-center border-b ${styles.border} text-center`}>
            {/* avatar */}
            <div className={`w-24 h-24 rounded-full ${styles.avatarBg} ${styles.avatarText} flex items-center justify-center text-3xl font-bold mb-4 shadow-inner`}>
              {fullName.charAt(0)}
            </div>
            
            <h3 className="text-xl font-semibold mb-1">{fullName}</h3>
            <p className={styles.muted}>{email}</p>
          </div>

          {/* links section */}
          <div className={`p-4 flex flex-col gap-2 border-b ${styles.border}`}>
            <p className={`text-sm font-semibold uppercase tracking-wider mb-2 px-4 ${styles.muted}`}>
              links
            </p>
            
            <a 
              href="https://www.usosweb.uj.edu.pl/kontroler.php?_action=news/default" 
              target="_blank" 
              rel="noopener noreferrer"
              className={`flex items-center justify-between p-4 rounded-xl ${styles.hover} transition-colors cursor-pointer`}
            >
              <span className="font-medium">USOS web</span>
              <svg className={`w-5 h-5 ${styles.muted}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>

            <a 
              href="https://ksi.sh" 
              target="_blank" 
              rel="noopener noreferrer"
              className={`flex items-center justify-between p-4 rounded-xl ${styles.hover} transition-colors cursor-pointer`}
            >
              <span className="font-medium">KSI website</span>
              <svg className={`w-5 h-5 ${styles.muted}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>

            <a 
              href="https://outlook.office.com/mail/" 
              target="_blank" 
              rel="noopener noreferrer"
              className={`flex items-center justify-between p-4 rounded-xl ${styles.hover} transition-colors cursor-pointer`}
            >
              <span className="font-medium">Outlook</span>
              <svg className={`w-5 h-5 ${styles.muted}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>

          {/* logout section */}
          <div className="p-4">
            <button 
              onClick={onLogout}
              className="w-full flex items-center justify-center gap-2 p-4 rounded-xl text-red-500 hover:bg-red-500/10 transition-colors font-semibold"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              Logout
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}