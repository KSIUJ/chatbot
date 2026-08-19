import LoginBackground from './LoginBackground';
import LoginHeader from './LoginHeader';
import LoginForm from './LoginForm';

interface LoginScreenProps {
  onLogin: (email: string) => void;
  onContinueAsGuest: () => void;
  onGoToRegister: () => void;
}

export default function LoginScreen({ onLogin, onContinueAsGuest, onGoToRegister }: LoginScreenProps) {
  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">
      
      {/* background component */}
      <LoginBackground />
      
      {/* main login page container */}
      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-5 space-y-5 border border-slate-100">
        <LoginHeader />
        <LoginForm onLogin={onLogin} />
        
        {/* register link */}
        <div className="text-center pt-4 pb-2 border-b border-slate-100">
          <p className="text-sm text-slate-600">
            Don't have an account?{' '}
            <button 
              onClick={onGoToRegister}
              className="font-bold text-blue-600 hover:text-blue-700 cursor-pointer"
            >
              Sign up
            </button>
          </p>
        </div>

        {/* continue as guest button */}
        <div className="text-center pt-2">
          <button 
            onClick={onContinueAsGuest}
            className="text-sm text-slate-500 hover:text-slate-700 underline transition-colors cursor-pointer"
          >
            Continue without logging in
          </button>
        </div>
      </div>

    </div>
  );
}