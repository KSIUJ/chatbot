import { useState, useEffect, useRef } from 'react';
import { Mail, Lock, Eye, EyeOff, AlertCircle, ArrowLeft, ArrowRight, Loader2, CheckCircle2, RefreshCw } from 'lucide-react';
import LoginBackground from './LoginBackground';
import { API_BASE_URL } from '../../lib/api';

interface RegisterScreenProps {
  onGoBackToLogin: () => void;
}

export default function RegisterScreen({ onGoBackToLogin }: RegisterScreenProps) {

  // form states
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  
  const [isLoading, setIsLoading] = useState(false);
  const [isCodeSent, setIsCodeSent] = useState(false);

  // 6-digit code state
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // timer state
  const [timeLeft, setTimeLeft] = useState(60);

  // handle countdown timer
  useEffect(() => {
    if (isCodeSent && timeLeft > 0) {
      const timerId = setInterval(() => {
        setTimeLeft((prev) => prev - 1);
      }, 1000);
      return () => clearInterval(timerId);
    }
  }, [isCodeSent, timeLeft]);

  // handle sending code
  const handleSendCode = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);
    setError('');
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/register/send-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'failed to send code');
      }

      setIsCodeSent(true); 
      setTimeLeft(60); // reset timer
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // handle code input changes
  const handleCodeChange = (index: number, value: string) => {
    // only allow numbers
    if (value && !/^\d+$/.test(value)) return;

    const newCode = [...code];
    // take only the last character if someone pastes
    newCode[index] = value.slice(-1);
    setCode(newCode);

    // move to next input automatically
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  // handle backspace to move previous
  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  // handle paste event for the whole code
  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text').slice(0, 6).split('');
    
    if (pastedData.some(char => !/^\d+$/.test(char))) return;

    const newCode = [...code];
    pastedData.forEach((char, i) => {
      if (i < 6) newCode[i] = char;
    });
    setCode(newCode);
    
    // focus last filled input
    const focusIndex = Math.min(pastedData.length, 5);
    inputRefs.current[focusIndex]?.focus();
  };

  // handle final verification
  const handleVerify = async () => {
    const fullCode = code.join('');
    if (fullCode.length !== 6 || !password.trim()) {
      setError('please enter the code and set a password.');
      return;
    }
    
    setIsLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/register/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          email: email.trim(),
          code: fullCode,
          password: password
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'verification failed');
      }

      // registration successful! redirect to login
      onGoBackToLogin();
      
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">
      
      {/* background component */}
      <LoginBackground />
      
      {/* main register page container */}
      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-6 space-y-5 border border-slate-100">
        
        {/* back button */}
        <button 
          onClick={onGoBackToLogin}
          className="flex items-center text-sm text-slate-500 hover:text-slate-800 transition-colors cursor-pointer mb-2"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to login
        </button>

        <div>
          <h2 className="text-2xl font-bold text-slate-900">Create Account</h2>
          <p className="text-sm text-slate-500 mt-1">
            {isCodeSent 
              ? "We've sent a verification code to your email." 
              : "Enter your email to receive a verification code."}
          </p>
        </div>

        {/* error message display */}
        {error && (
          <div className="flex items-center gap-2 p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl animate-in fade-in slide-in-from-top-2 duration-300">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {!isCodeSent ? (
          /* view 1: entering email */
          <form className="space-y-4 pt-2" onSubmit={handleSendCode}>
            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">
                Email address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Mail className="h-4 w-4" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError('');
                  }}
                  className="w-full pl-9 pr-3 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 placeholder-slate-400 outline-none transition-all text-sm"
                  placeholder="@student.uj.edu.pl"
                  disabled={isLoading}
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !email.trim()}
              className="w-full group rounded-xl bg-blue-700/80 px-4 py-2.5 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 flex items-center justify-center gap-2 mt-2 shadow-sm cursor-pointer"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> 
                  Sending...
                </>
              ) : (
                <>
                  Send code 
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>
        ) : (
          /* view 2: code sent confirmation & code input */
          <div className="pt-2 space-y-6">
            <div className="flex justify-center mb-2">
              <CheckCircle2 className="w-10 h-10 text-green-500" />
            </div>
            
            <p className="text-sm font-medium text-slate-700 text-center">
              Code sent to: <br/>
              <span className="font-bold text-slate-900">{email}</span>
            </p>

            {/* 6 digit code inputs */}
            <div className="flex justify-between gap-2" onPaste={handlePaste}>
              {code.map((digit, index) => (
                <input
                  key={index}
                  ref={(el) => { (inputRefs.current[index] = el) }}
                  type="text"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleCodeChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  className="w-10 h-12 text-center text-lg font-bold bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 outline-none transition-all"
                />
              ))}
            </div>

            {/* password setup */}
            <div className="space-y-1.5 pt-2">
              <label className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">Set Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-4 w-4" />
                </div>
                
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError('');
                  }}
                  className="w-full pl-9 pr-10 py-2.5 bg-white/90 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500/50 focus:border-blue-600 text-slate-900 outline-none transition-all text-sm"
                  placeholder="••••••••"
                  disabled={isLoading}
                />
                
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  disabled={isLoading}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors focus:outline-none cursor-pointer"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              onClick={handleVerify}
              disabled={code.join('').length !== 6 || !password.trim()}
              className="w-full group rounded-xl bg-blue-700/80 px-4 py-2.5 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 flex items-center justify-center gap-2 shadow-sm cursor-pointer"
            >
              Verify Code & Register
            </button>

            {/* resend timer */}
            <div className="text-center pt-2">
              {timeLeft > 0 ? (
                <p className="text-xs text-slate-500">
                  Resend code in {timeLeft}s
                </p>
              ) : (
                <button
                  onClick={() => handleSendCode()}
                  disabled={isLoading}
                  className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors flex items-center justify-center w-full gap-1 cursor-pointer"
                >
                  <RefreshCw className="w-3 h-3" />
                  Resend code now
                </button>
              )}
            </div>
          </div>
        )}
      </div>

    </div>
  );
}