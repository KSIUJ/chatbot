import { Loader2 } from 'lucide-react';
import ChatScreen from './features/Chat/ChatScreen';
import LoginScreen from './features/Auth/LoginScreen';
import { useAuth } from './features/Auth/useAuth';

export default function App() {
  // session lives in an HttpOnly cookie - the backend is the only source of truth
  const { state, login, logout } = useAuth();

  // checking the session with the backend, or already redirecting to KSI login
  // (dark: variant follows the device, so there is no white flash in dark mode)
  if (state.status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-[#121212]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" aria-label="Loading" />
      </div>
    );
  }

  // only reached on login errors - no session alone redirects straight to KSI
  if (state.status === 'unauthenticated') {
    return <LoginScreen error={state.error} onLogin={login} />;
  }

  return <ChatScreen user={state.user} onLogout={() => void logout()} />;
}
