import mojeLogo from "../../assets/logo-ksi-IBUoeAwm.svg";

export default function LoginHeader() {
  return (
    <div className="text-center space-y-1">
      <img 
        src={mojeLogo} 
        alt="Logo Użytkownika" 
        className="h-16 w-auto mx-auto mb-4 object-contain" 
      />
      <h1 className="text-2xl font-black text-slate-900 tracking-tight">
        CHATBOT WMiI
      </h1>
      <p className="text-xs font-semibold text-slate-400/80 tracking-widest uppercase">
        Authorization
      </p>
    </div>
  );
}