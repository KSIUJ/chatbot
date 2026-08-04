import LoginBackground from './LoginBackground';
import LoginHeader from './LoginHeader';
import LoginForm from './LoginForm';

interface LoginScreenProps {
  onLogin: (email: string) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">
      
      {/* Background Component */}
      <LoginBackground />
      
      {/* Main login page container */}
      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-5 space-y-5 border border-slate-100">
        <LoginHeader />
        <LoginForm onLogin={onLogin} />
      </div>

    </div>
  );
}