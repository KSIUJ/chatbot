import { Mail, Lock, ArrowRight } from 'lucide-react';

interface LoginScreenProps {
  onLogin: () => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      
      {/* Main card */}
      <div className="max-w-md w-full bg-white rounded-3xl shadow-lg p-8 space-y-10 border border-slate-100">
        
        {/* Header with logo placeholder */}
        <div className="text-center space-y-3">
          
          {/* Logo placeholder */}
          <div className="relative w-24 h-24 mx-auto mb-4 flex items-center justify-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-300">
            <span className="text-xs text-slate-400 font-medium text-center">
              Miejsce na<br/>logo
            </span>
            {/* Replace with: 
                <img src="/logo-ksi.png" alt="KSI UJ Logo" className="w-full h-full object-contain" /> 
            */}
          </div>
          
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tighter">
            (...)
          </h2>
          <p className="text-slate-600 text-lg font-medium">
            Autoryzacja Użytkownika
          </p>
        </div>

        {/* Form - ZMIANA B ZOSTAŁA WPROWADZONA PONIŻEJ */}
        <form className="space-y-6" onSubmit={(e) => {
          e.preventDefault(); // Zatrzymuje przeładowanie strony
          onLogin(); // Uruchamia funkcję logowania z App.tsx
        }}>
          
          <div className="space-y-3">
            <label className="text-sm font-semibold text-slate-700 tracking-wide">Login</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-5 flex items-center pointer-events-none text-slate-400">
                <Mail className="h-6 w-6" />
              </div>
              <input
                type="login"
                className="w-full pl-14 pr-5 py-4 bg-white border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all"
                placeholder="@student.uj.edu.pl"
              />
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-semibold text-slate-700 tracking-wide">Hasło dostępu</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-5 flex items-center pointer-events-none text-slate-400">
                <Lock className="h-6 w-6" />
              </div>
              <input
                type="password"
                className="w-full pl-14 pr-5 py-4 bg-white border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all"
                placeholder="••••••••"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full group rounded-xl bg-blue-600 px-6 py-4 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] flex items-center justify-center gap-2 mt-12 shadow-sm border border-transparent"
          >
            Zaloguj się
            <ArrowRight className="w-5 h-5 text-white/90 group-hover:translate-x-1.5 transition-transform" />
          </button>
        </form>

        {/* Footer */}
        <div className="text-center text-sm text-slate-600 pt-8 border-t border-slate-100">
          Brak dostępu do systemu?{' '}
          <a href="#" className="text-blue-600 hover:text-blue-700 hover:underline transition-colors font-semibold">
            Złóż wniosek o konto
          </a>
        </div>
        
      </div>
    </div>
  );
}