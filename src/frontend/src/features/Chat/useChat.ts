import { useState, useEffect, useRef } from 'react';
import { type ThemeKey } from './themes'; 
import { translations, type LangKey } from './languages'; 
import type { Message } from './types';

export function useChat(onLogout?: () => void) {
  // states
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [settingsView, setSettingsView] = useState<'main' | 'language' | 'theme' | 'rag'>('main');
  
  const [selectedLanguage, setSelectedLanguage] = useState<LangKey>(() => {
    const saved = localStorage.getItem('chatLanguage');
    return (saved as LangKey) || 'polski';
  });
  
  const [selectedTheme, setSelectedTheme] = useState<ThemeKey>(() => {
    const saved = localStorage.getItem('chatTheme');
    return (saved as ThemeKey) || 'jasny';
  });

  const [ragCount, setRagCount] = useState<number>(() => {
    const saved = localStorage.getItem('chatRagCount');
    return saved ? parseInt(saved, 10) : 5;
  });

  // chat states
  const [inputText, setInputText] = useState('');
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = localStorage.getItem('chatMessages');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error("Could not load messages", e);
      }
    }
    const lang = (localStorage.getItem('chatLanguage') as LangKey) || 'polski';
    return [{ id: '1', sender: 'bot', text: translations[lang].botGreeting }];
  });
  
  const [copiedIds, setCopiedIds] = useState<string[]>([]);
  const [reactions, setReactions] = useState<Record<string, 'up' | 'down'>>({});

  // refs
  const menuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const responseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // local storage
  useEffect(() => {
    localStorage.setItem('chatLanguage', selectedLanguage);
  }, [selectedLanguage]);

  useEffect(() => {
    localStorage.setItem('chatTheme', selectedTheme);
  }, [selectedTheme]);

  useEffect(() => {
    localStorage.setItem('chatRagCount', ragCount.toString());
  }, [ragCount]);

  useEffect(() => {
    const messagesToSave = messages.map(msg => ({
      id: msg.id,
      sender: msg.sender,
      text: msg.text,
      isStopped: msg.isStopped
    }));
    localStorage.setItem('chatMessages', JSON.stringify(messagesToSave));
  }, [messages]);

  // other effects
  useEffect(() => {
    if (messages.length === 1 && messages[0].id === '1') {
      setMessages([{ id: '1', sender: 'bot', text: translations[selectedLanguage].botGreeting }]);
    }
  }, [selectedLanguage]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowSettingsMenu(false); 
        setSettingsView('main');    
      }
    }
    
    if (showSettingsMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showSettingsMenu]); 

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // helpers
  const toggleSettings = () => {
    setShowSettingsMenu(!showSettingsMenu);
    setSettingsView('main'); 
  };

  const handleLogout = () => {
    localStorage.removeItem('isLoggedIn');
    if (onLogout) {
      onLogout();
    } else {
      window.location.reload(); 
    }
  };

  const handleNewChat = () => {
    if (responseTimeoutRef.current) {
      clearTimeout(responseTimeoutRef.current);
      responseTimeoutRef.current = null;
    }

    setMessages([
      { id: Date.now().toString(), sender: 'bot', text: translations[selectedLanguage].botGreeting }
    ]);
    setInputText('');
    setStagedFiles([]);
    setCopiedIds([]); 
    setReactions({}); 
    setIsTyping(false);
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    if (!copiedIds.includes(id)) {
      setCopiedIds(prev => [...prev, id]);
    }
  };

  const handleReaction = (id: string, type: 'up' | 'down') => {
    setReactions(prev => ({ ...prev, [id]: type }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const filesArray = Array.from(e.target.files);
      setStagedFiles(prev => [...prev, ...filesArray]);
    }
    e.target.value = ''; 
  };

  const removeStagedFile = (index: number) => {
    setStagedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // stop generating response
  const handleStopGenerating = () => {
    if (responseTimeoutRef.current) {
      clearTimeout(responseTimeoutRef.current);
      responseTimeoutRef.current = null;
    }
    setIsTyping(false);
    
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      sender: 'bot',
      text: selectedLanguage === 'angielski' ? 'Response stopped.' : 'Odpowiedź zatrzymana.',
      isStopped: true
    }]);
  };

  // regenerate response
  const handleRegenerate = () => {
    setIsTyping(true);
    if (responseTimeoutRef.current) clearTimeout(responseTimeoutRef.current);
    
    responseTimeoutRef.current = setTimeout(() => {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: translations[selectedLanguage].botReply
      }]);
    }, 3000);
  };

  const handleSendMessage = () => {
    if (!inputText.trim() && stagedFiles.length === 0) return; 

    const newUserMsg: Message = { 
      id: Date.now().toString(), 
      sender: 'user', 
      text: inputText.trim(),
      files: stagedFiles.length > 0 ? stagedFiles : undefined
    };
    
    setMessages(prev => [...prev, newUserMsg]);
    setInputText('');
    setStagedFiles([]);
    setIsTyping(true);

    // simulation
    responseTimeoutRef.current = setTimeout(() => {
      setIsTyping(false); // stop the animation after receiving reply
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: translations[selectedLanguage].botReply
      }]);
    }, 3000); 
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSendMessage();
  };

  return {
    showSettingsMenu,
    settingsView,
    setSettingsView,
    selectedLanguage,
    setSelectedLanguage,
    selectedTheme,
    setSelectedTheme,
    ragCount,
    setRagCount,
    inputText,
    setInputText,
    stagedFiles,
    messages,
    copiedIds,
    reactions,
    isTyping, 
    menuRef,
    messagesEndRef,
    toggleSettings,
    handleLogout,
    handleNewChat,
    handleCopy,
    handleReaction,
    handleFileChange,
    removeStagedFile,
    handleSendMessage,
    handleKeyDown,
    handleStopGenerating,
    handleRegenerate
  };
}