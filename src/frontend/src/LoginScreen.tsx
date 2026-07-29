import { Mail, Lock, ArrowRight } from 'lucide-react';
import facadeImage from './assets/facade_4-Dwl60qUz.svg'; 
import mojeLogo from './assets/logo-ksi-IBUoeAwm.svg'; 

interface LoginScreenProps {
  onLogin: () => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">
      
      {/* background */}
      <div className="absolute top-1/2 left-0 w-full -translate-y-1/2 opacity-30 pointer-events-none select-none flex justify-center">
        
        {/* colors */}
        <div 
          className="w-full max-w-7xl bg-blue-900" 
          style={{
            WebkitMaskImage: `url(${facadeImage})`,
            WebkitMaskSize: 'contain',
            WebkitMaskRepeat: 'no-repeat',
            WebkitMaskPosition: 'center',
            maskImage: `url(${facadeImage})`,
            maskSize: 'contain',
            maskRepeat: 'no-repeat',
            maskPosition: 'center'
          }}
        >
          {/* clear image for good proportions */}
          <img src={facadeImage} alt="Fasada" className="w-full opacity-0" />
        </div>

      </div>

      {/* Main login page */}
      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-5 space-y-5 border border-slate-100">
        
        {/* title */}
        <div className="text-center space-y-1">
          
          {/* KSI LOGO */}
          <img 
            src={mojeLogo} 
            alt="Logo Użytkownika" 
            className="h-16 w-auto mx-auto mb-4 object-contain" 
          />
          
          {/* Bigger on top */}
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            CHATBOT WMiI
          </h1>
          
          {/* Less opacity */}
          <p className="text-xs font-semibold text-slate-400/80 tracking-widest uppercase">
            Authorization
          </p>
        </div>

        {/* Form */}
        <form className="space-y-4 pt-2" onSubmit={(e) => {
          e.preventDefault();
          onLogin();
        }}>
          
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">Login</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Mail className="h-4 w-4" />
              </div>
              <input
                type="login"
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
      </div>
    </div>
  );
}