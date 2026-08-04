import { Check } from 'lucide-react';

interface RememberCheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export default function RememberCheckbox({ checked, onChange }: RememberCheckboxProps) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group w-fit mt-1">
      {/* hidden actual input */}
      <input 
        type="checkbox" 
        className="hidden" 
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      
      {/* custom styled checkbox box */}
      <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
        checked 
          ? 'bg-blue-600 border-blue-600' 
          : 'bg-white border-slate-300 group-hover:border-blue-400'
      }`}>
        {checked && <Check size={12} className="text-white" />}
      </div>
      
      {/* label text */}
      <span className="text-[11px] font-semibold text-slate-600 tracking-wide uppercase">
        remember me
      </span>
    </label>
  );
}