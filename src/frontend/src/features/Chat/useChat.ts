import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError, isSessionLost } from '../../lib/api';
import { ACTIVE_CONVERSATION_KEY, rememberActiveConversation } from '../../lib/chatStorage';
import {
  deleteConversation,
  fetchConversationMessages,
  fetchConversations,
  newConversationId,
  sendMessage,
  shouldRegenerate,
  toChatMessages,
  type ChatMessage,
  type ConversationList,
  type ConversationSummary,
} from './conversations';

export interface HistoryLimits {
  maxPerUser: number;
  retentionDays: number;
}

const COPIED_FEEDBACK_MS = 2000;

let localIdCounter = 0;
function localId(): string {
  localIdCounter += 1;
  return `local-${Date.now()}-${localIdCounter}`;
}

// Chat state: sidebar history from the server, the open conversation, sending,
// stop and retry. Only the id of the open conversation is kept in localStorage.
export function useChat() {
  // the conversation that was open before the reload
  const [rememberedId] = useState(() => localStorage.getItem(ACTIVE_CONVERSATION_KEY));
  // Storage mirrors activeId only once the initial load succeeded (or the user
  // started a new chat): a failed /conversations at startup must not forget
  // the remembered conversation while activeId is still the initial null.
  const [isRestored, setIsRestored] = useState(false);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [limits, setLimits] = useState<HistoryLimits | null>(null);
  const [historyError, setHistoryError] = useState(false);

  // id of the open conversation; a new chat gets its id at the first send
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // bumped on every switch, so work started for a previous conversation is ignored
  const loadTokenRef = useRef(0);

  useEffect(() => {
    rememberActiveConversation(activeId, isRestored);
  }, [activeId, isRestored]);

  const applyHistory = useCallback((list: ConversationList) => {
    setConversations(list.conversations);
    setLimits({ maxPerUser: list.max_per_user, retentionDays: list.retention_days });
    setHistoryError(false);
  }, []);

  const applyHistoryError = useCallback((error: unknown) => {
    // a lost session already switched the app to the login flow
    if (!isSessionLost(error)) setHistoryError(true);
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      applyHistory(await fetchConversations());
    } catch (error) {
      applyHistoryError(error);
    }
  }, [applyHistory, applyHistoryError]);

  const cancelPending = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsWaiting(false);
  }, []);

  const openConversation = useCallback(async (id: string) => {
    cancelPending();
    const token = ++loadTokenRef.current;
    setActiveId(id);
    setMessages([]);
    setLoadError(false);
    setIsLoadingConversation(true);
    try {
      const serverMessages = await fetchConversationMessages(id);
      if (token !== loadTokenRef.current) return;
      if (serverMessages === null) {
        // deleted or expired meanwhile - start fresh
        setActiveId(null);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        return;
      }
      setMessages(toChatMessages(serverMessages));
    } catch (error) {
      if (token === loadTokenRef.current && !isSessionLost(error)) setLoadError(true);
    } finally {
      if (token === loadTokenRef.current) setIsLoadingConversation(false);
    }
  }, [cancelPending]);

  // first load: history, then reopen the conversation that was open before
  useEffect(() => {
    let cancelled = false;
    fetchConversations().then(
      (list) => {
        if (cancelled) return;
        applyHistory(list);
        setIsRestored(true);
        if (rememberedId !== null && list.conversations.some((c) => c.id === rememberedId)) {
          void openConversation(rememberedId);
        }
      },
      (error: unknown) => {
        if (!cancelled) applyHistoryError(error);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [applyHistory, applyHistoryError, openConversation, rememberedId]);

  const startNewChat = useCallback(() => {
    cancelPending();
    loadTokenRef.current += 1;
    setIsRestored(true);
    setActiveId(null);
    setMessages([]);
    setLoadError(false);
    setIsLoadingConversation(false);
  }, [cancelPending]);

  const removeChat = useCallback(async (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) startNewChat();
    try {
      await deleteConversation(id);
    } catch (error) {
      // put the list back in sync with the server
      if (!isSessionLost(error)) void refreshHistory();
    }
  }, [activeId, startNewChat, refreshHistory]);

  // caller creates the controller and registers it in abortRef, so stop/switch
  // can cancel from the very first moment (retry awaits a fetch before this)
  const ask = useCallback(async (
    question: string,
    conversationId: string,
    regenerate: boolean,
    controller: AbortController,
  ) => {
    try {
      const reply = await sendMessage({ message: question, conversationId, regenerate, signal: controller.signal });
      if (controller.signal.aborted) return;
      setMessages((prev) => [...prev, reply]);
      void refreshHistory();
    } catch (error) {
      if (controller.signal.aborted || isSessionLost(error)) return;
      if (error instanceof ApiRequestError && error.status === 404) {
        // id taken by another account (practically impossible): retry under a fresh id
        setActiveId(newConversationId());
      }
      setMessages((prev) => [...prev, { id: localId(), sender: 'bot', text: '', status: 'error' }]);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsWaiting(false);
      }
    }
  }, [refreshHistory]);

  const beginRequest = useCallback((): AbortController => {
    const controller = new AbortController();
    abortRef.current = controller;
    setIsWaiting(true);
    return controller;
  }, []);

  const send = useCallback((text: string): boolean => {
    const question = text.trim();
    if (!question || isWaiting || isLoadingConversation) return false;
    const conversationId = activeId ?? newConversationId();
    setActiveId(conversationId);
    setMessages((prev) => [...prev, { id: localId(), sender: 'user', text: question }]);
    void ask(question, conversationId, false, beginRequest());
    return true;
  }, [activeId, ask, beginRequest, isLoadingConversation, isWaiting]);

  const stop = useCallback(() => {
    if (abortRef.current === null) return;
    cancelPending();
    setMessages((prev) => [...prev, { id: localId(), sender: 'bot', text: '', status: 'stopped' }]);
    // the server keeps going and saves the answer - show the chat in the list
    void refreshHistory();
  }, [cancelPending, refreshHistory]);

  const retry = useCallback(async () => {
    const lastQuestion = [...messages].reverse().find((m) => m.sender === 'user');
    if (lastQuestion === undefined || isWaiting) return;
    const conversationId = activeId ?? newConversationId();
    const token = loadTokenRef.current;
    const controller = beginRequest();
    setActiveId(conversationId);
    setMessages((prev) => prev.filter((m) => m.status === undefined));

    let regenerate = false;
    try {
      const serverMessages = await fetchConversationMessages(conversationId);
      regenerate = serverMessages !== null && shouldRegenerate(serverMessages, lastQuestion.text);
    } catch {
      // cannot tell what the server has - keep regenerate=false: a plain send
      // never deletes an answer
    }
    // stopped or switched to another conversation meanwhile
    if (controller.signal.aborted || token !== loadTokenRef.current) return;
    void ask(lastQuestion.text, conversationId, regenerate, controller);
  }, [activeId, ask, beginRequest, isWaiting, messages]);

  const copy = useCallback((message: ChatMessage) => {
    navigator.clipboard.writeText(message.text).then(
      () => {
        setCopiedId(message.id);
        setTimeout(() => setCopiedId((current) => (current === message.id ? null : current)), COPIED_FEEDBACK_MS);
      },
      // clipboard blocked (permissions / insecure context): the button just shows no confirmation
      () => setCopiedId(null),
    );
  }, []);

  return {
    conversations,
    limits,
    historyError,
    activeId,
    messages,
    isWaiting,
    isLoadingConversation,
    loadError,
    copiedId,
    openConversation,
    startNewChat,
    removeChat,
    send,
    stop,
    retry,
    copy,
  };
}
