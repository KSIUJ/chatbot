import { Bot, Check, Copy, FileText, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';

interface ChatMessageListProps {
  t: any;
  lang: any;
  messages: any[];
  copiedIds: string[];
  reactions: Record<string, string>;
  isTyping: boolean;
  selectedLanguage: string;
  messagesEndRef: React.RefObject<HTMLDivElement | null>; 
  handleCopy: (text: string, id: string) => void;
  handleReaction: (id: string, type: 'up' | 'down') => void; 
  handleRegenerate: () => void;
}

export default function ChatMessageList(props: ChatMessageListProps) {
  const { 
    t, lang, messages, copiedIds, reactions, isTyping, selectedLanguage, 
    messagesEndRef, handleCopy, handleReaction, handleRegenerate 
  } = props;

  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedMessages(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <main className="flex-1 p-4 pt-8 overflow-y-auto space-y-6 scroll-smooth">
      {/* map messages */}
      {messages.map((msg) => {
        const isCopied = copiedIds.includes(msg.id);
        const currentReaction = reactions[msg.id];
        
        // text cutting
        const TEXT_LIMIT = 350;
        const isLongMessage = msg.text && msg.text.length > TEXT_LIMIT;
        const isExpanded = expandedMessages.has(msg.id);
        const displayText = isLongMessage && !isExpanded 
          ? msg.text.slice(0, TEXT_LIMIT) + '...' 
          : msg.text;
        
        return (
          <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
            
            {/* bot icon - TODO: make a new one */}
            {msg.sender === 'bot' && (
              <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
                <Bot size={22} />
              </div>
            )}

            {/* message wrapper for text, files and top action bar */}
            <div className="flex flex-col gap-2 max-w-[70%]">
              
              {/* render files if any */}
              {msg.files && msg.files.length > 0 && (
                <div className={`flex flex-wrap gap-2 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.files.map((file: File, i: number) => {
                    const fileUrl = URL.createObjectURL(file);
                    return file.type.startsWith('image/') ? (
                      <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" className="block cursor-pointer hover:opacity-80 transition-opacity">
                        <img src={fileUrl} alt="attachment" className="max-w-50 max-h-50 object-cover rounded-xl border border-neutral-200/20 shadow-sm" />
                      </a>
                    ) : (
                      <a key={i} href={fileUrl} target="_blank" rel="noopener noreferrer" download={file.name} className={`flex items-center gap-2 p-3 rounded-xl shadow-sm cursor-pointer hover:opacity-80 transition-opacity ${msg.sender === 'user' ? t.userMsgBox : t.msgBox}`}>
                        <FileText size={18} />
                        <span className="text-sm font-medium truncate max-w-37.5">{file.name}</span>
                      </a>
                    );
                  })}
                </div>
              )}

              {/* render text and static copy button inside message box */}
              {msg.text && (
                <div className={`p-5 pr-14 relative rounded-2xl border shadow-sm text-[15px] leading-relaxed transition-colors duration-300 whitespace-pre-wrap break-words 
                  ${msg.sender === 'user' ? `${t.userMsgBox} rounded-tr-sm` : `${t.msgBox} rounded-tl-sm`}
                  ${msg.isStopped ? 'opacity-80 italic' : ''}`
                }>
                  {displayText}
                  
                  {/* show more/less */}
                  {isLongMessage && (
                    <button
                      onClick={() => toggleExpand(msg.id)}
                      className="block mt-2 text-[10px] font-bold uppercase tracking-wider opacity-60 hover:opacity-100 transition-opacity"
                    >
                      {isExpanded 
                        ? (selectedLanguage === 'angielski' ? 'Show less' : 'Zwiń') 
                        : (selectedLanguage === 'angielski' ? 'Show more' : 'Rozwiń')}
                    </button>
                  )}

                  {/* copy button fixed to top-right inside bot message box */}
                  {msg.sender === 'bot' && !msg.isStopped && (
                    <button 
                      onClick={() => handleCopy(msg.text, msg.id)}
                      className={`absolute top-3 right-3 transition-colors p-1.5 rounded-md ${
                        isCopied ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                      }`}
                      title={isCopied ? lang.copied : lang.copy}
                    >
                      {isCopied ? <Check size={16} /> : <Copy size={16} />}
                    </button>
                  )} 
                </div>
              )}

              {/* thumbs up/down with fill color on click */}
              {msg.sender === 'bot' && !msg.isStopped && (
                <div className="flex items-center gap-2 px-1 mt-0.5">
                  <button 
                    onClick={() => handleReaction(msg.id, 'up')}
                    className={`transition-colors p-1 rounded-md ${
                      currentReaction === 'up' ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                    }`}
                    title="useful"
                  >
                    <ThumbsUp size={15} fill={currentReaction === 'up' ? "currentColor" : "none"} />
                  </button>
                  
                  <button 
                    onClick={() => handleReaction(msg.id, 'down')}
                    className={`transition-colors p-1 rounded-md ${
                      currentReaction === 'down' ? t.copiedIcon : `${t.textMuted} hover:${t.text} ${t.hover}`
                    }`}
                    title="not useful"
                  >
                    <ThumbsDown size={15} fill={currentReaction === 'down' ? "currentColor" : "none"} />
                  </button>
                </div>
              )}

              {/* regenerate button for stopped messages */}
              {msg.sender === 'bot' && msg.isStopped && (
                <div className="flex items-center gap-2 px-1 mt-0.5">
                  <button
                    onClick={handleRegenerate}
                    disabled={isTyping}
                    className={`flex items-center gap-1.5 transition-colors p-1.5 rounded-md ${
                      isTyping ? 'opacity-50 cursor-not-allowed' : `${t.textMuted} hover:${t.text} ${t.hover}`
                    } text-[11px] font-bold uppercase tracking-wide`}
                  >
                    <RefreshCw size={13} />
                    <span>{selectedLanguage === 'angielski' ? 'Regenerate' : 'Ponów'}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}
      
      {/* render three dots when waiting for response */}
      {isTyping && (
        <div className="flex gap-4 max-w-4xl mx-auto w-full">
          {/* bot icon - TODO: make a new one */}
          <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5 transition-colors duration-300`}>
            <Bot size={22} />
          </div>
          <div className="flex flex-col gap-2 max-w-[70%]">
            <div className={`px-5 py-6 relative rounded-2xl border shadow-sm transition-colors duration-300 ${t.msgBox} rounded-tl-sm flex items-center h-13`}>
              <div className="flex gap-1.5 items-center justify-center h-full">
                <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* empty div for auto-scroll */}
      <div ref={messagesEndRef} />
    </main>
  );
}