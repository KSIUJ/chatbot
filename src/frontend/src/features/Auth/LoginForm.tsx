import { useState } from 'react';
import { Mail, Lock, ArrowRight, AlertCircle, Loader2 } from 'lucide-react';
import RememberCheckbox from './RememberCheckbox';

interface LoginFormProps {
  onLogin: (email: string, remember: boolean) => void;
}

export default function LoginForm({ onLogin }: LoginFormProps) {
  // form states
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  // checkbox state
  const [rememberMe, setRememberMe] = useState(false);
  
  // error and loading states
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // reset previous error
    setError('');

    // basic check to ensure fields are not empty
    if (!email.trim() || !password.trim()) {
      setError('please enter email and password.');
      return;
    }

    // start loading state
    setIsLoading(true);

    // mock server request with 1 second delay
    setTimeout(() => {
      setIsLoading(false);

      // mock backend validation
      // for now password must be haslo123 to succeed!!!!!!
      if (password !== 'haslo123') {
        setError('invalid email or password.');
        return;
      }

      // if password is correct proceed to login passing remember state
      onLogin(email.trim(), rememberMe);
    }, 1000);
  };

  return (
    <form className="space-y-4 pt-2" onSubmit={handleSubmit}>
      
      <div className="space-y-1.5">
        <label className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">Login</label>
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Mail className="h-4 w-4" />
          </div>
          <input
            type="text"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setError(''); // clear error when user starts typing
            }}
            className="w-full pl-9 pr-3 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all text-sm"
            placeholder="@student.uj.edu.pl"
            disabled={isLoading}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">Password</label>
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Lock className="h-4 w-4" />
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError(''); // clear error when user starts typing
            }}
            className="w-full pl-9 pr-3 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all text-sm"
            placeholder="••••••••"
            disabled={isLoading}
          />
        </div>
        
        {/* remember me checkbox */}
        <div className="pt-1">
          <RememberCheckbox checked={rememberMe} onChange={setRememberMe} />
        </div>
      </div>

      {/* error message display */}
      {error && (
        <div className="flex items-center gap-2 p-3 mt-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl animate-in fade-in slide-in-from-top-2 duration-300">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full group rounded-xl bg-blue-700/80 px-4 py-2.5 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 flex items-center justify-center gap-2 mt-6 shadow-sm border border-transparent text-sm"
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin text-white/90" />
            logging in...
          </>
        ) : (
          <>
            Log In
            <ArrowRight className="w-4 h-4 text-white/90 group-hover:translate-x-1.5 transition-transform" />
          </>
        )}
      </button>
    </form>
  );
}