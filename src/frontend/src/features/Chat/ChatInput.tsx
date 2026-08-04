import { FileText, Paperclip, Send, Square, X } from 'lucide-react';
import { useEffect } from 'react';

interface ChatInputProps {
  t: any;
  lang: any;
  selectedLanguage: string; 
  stagedFiles: File[];
  removeStagedFile: (index: number) => void;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  inputText: string;
  setInputText: (text: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  isTyping: boolean;
  handleStopGenerating: () => void;
  handleSendMessage: () => void;
}

export default function ChatInput(props: ChatInputProps) {
  const {
    t, lang, selectedLanguage, stagedFiles, removeStagedFile, handleFileChange,
    inputRef, inputText, setInputText, handleKeyDown,
    isTyping, handleStopGenerating, handleSendMessage
  } = props;

  useEffect(() => {
    if (inputRef.current) {
      
      inputRef.current.style.height = '0px';
      const scrollHeight = inputRef.current.scrollHeight;
      
      inputRef.current.style.height = inputText === '' ? 'auto' : `${scrollHeight}px`;
    }
  }, [inputText, inputRef]);

  return (
    <footer className="px-4 pb-8 bg-transparent z-20">
      <div className="max-w-2xl mx-auto relative mb-4">
        
        {/* staged files preview */}
        {stagedFiles.length > 0 && (
          <div className="absolute bottom-full left-0 mb-3 flex flex-wrap gap-2 z-10 w-full">
            {stagedFiles.map((file: File, i: number) => (
              <div key={i} className={`flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-full border shadow-sm text-xs font-medium ${t.msgBox}`}>
                {file.type.startsWith('image/') ? (
                  <div className="h-5 w-5 rounded overflow-hidden shrink-0">
                    <img src={URL.createObjectURL(file)} alt="preview" className="h-full w-full object-cover" />
                  </div>
                ) : (
                  <FileText size={14} className="shrink-0" />
                )}
                <span className="truncate max-w-30">{file.name}</span>
                <button onClick={() => removeStagedFile(i)} className={`p-1 rounded-full ${t.hover} transition-colors`}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <input 
          type="file" 
          id="file-upload" 
          className="hidden" 
          multiple 
          onChange={handleFileChange}
        />

        <label 
          htmlFor="file-upload"
          className={`absolute left-2 top-1/2 -translate-y-1/2 p-2.5 ${t.textMuted} hover:${t.text} ${t.hover} rounded-full cursor-pointer transition-colors z-10`}
          title="Dołącz plik"
        >
          <Paperclip size={20} />
        </label>

        {/* auto-expanding textarea */}
        <textarea 
          ref={inputRef} 
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
        
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault(); 
              handleSendMessage();
            } else {
              handleKeyDown(e);
            }
          }}

          placeholder={isTyping ? (selectedLanguage.toLowerCase().includes('n') ? "Answering..." : "Odpowiada...") : lang.inputPlaceholder}
          rows={1}
          style={{ maxHeight: '200px' }}
          className={`w-full pl-12 pr-14 py-3 border shadow-md rounded-3xl focus:ring-2 outline-none transition-all duration-100 disabled:opacity-70 disabled:cursor-not-allowed resize-none overflow-hidden ${t.inputBox}`}
        />
        
        {/* send or stop button */}
        {isTyping ? (
          <button 
            onClick={handleStopGenerating}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 z-10 text-neutral-400 hover:text-red-500 hover:bg-red-500/10`}
            title="stop"
          >
            <Square size={18} fill="currentColor" />
          </button>
        ) : (
          <button 
            onClick={handleSendMessage}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 z-10 ${t.sendBtn}`}
          >
            <Send size={18} className="-translate-x-px translate-y-px" />
          </button>
        )}
        
      </div>
      
      <div className={`text-center text-[10px] ${t.textMuted} font-medium transition-colors`}>
        {lang.disclaimer}
      </div>
    </footer>
  );
}