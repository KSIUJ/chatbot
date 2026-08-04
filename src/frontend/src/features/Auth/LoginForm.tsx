import { useState } from 'react';
import { Mail, Lock, ArrowRight } from 'lucide-react';

interface LoginFormProps {
  onLogin: (email: string) => void;
}

export default function LoginForm({ onLogin }: LoginFormProps) {
  // state to hold input values
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // basic check to ensure email is provided
    if (email.trim()) {
      onLogin(email.trim());
    }
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
            onChange={(e) => setEmail(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all text-sm"
            placeholder="@student.uj.edu.pl"
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
            onChange={(e) => setPassword(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all text-sm"
            placeholder="••••••••"
          />
        </div>
      </div>

      <button
        type="submit"
        className="w-full group rounded-xl bg-blue-700/80 px-4 py-2.5 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] flex items-center justify-center gap-2 mt-6 shadow-sm border border-transparent text-sm"
      >
        Log In
        <ArrowRight className="w-4 h-4 text-white/90 group-hover:translate-x-1.5 transition-transform" />
      </button>
    </form>
  );
}