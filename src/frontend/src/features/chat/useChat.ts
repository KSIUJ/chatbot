import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError, isSessionLost } from '../../lib/api';
import { ACTIVE_CONVERSATION_KEY, rememberActiveConversation } from '../../lib/chatStorage';
import type { HtmlLang } from '../preferences/languages';
import {
  deleteConversation,
  fetchConversationMessages,
  fetchConversations,
  newConversationId,
  shouldRegenerate,
  streamMessage,
  toChatMessages,
  type ChatMessage,
  type ConversationList,
  type ConversationSummary,
} from './conversations';
import { describeStop, waitForStoppedExchange, type StoppedExchange } from './stopSync';

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

function errorMarker(): ChatMessage {
  return { id: localId(), sender: 'bot', text: '', status: 'error' };
}

// Ends the answer being streamed: a partial answer becomes a "stopped" bubble
// that keeps its text; without any text a plain marker is added.
export function stopStreaming(messages: readonly ChatMessage[], markerId: string): ChatMessage[] {
  const last = messages.at(-1);
  if (last?.status === 'streaming') return [...messages.slice(0, -1), { ...last, status: 'stopped' }];
  return [...messages, { id: markerId, sender: 'bot', text: '', status: 'stopped' }];
}

// Appends a delta to the streaming bubble `id`, creating it on the first delta.
export function appendDelta(messages: readonly ChatMessage[], id: string, text: string): ChatMessage[] {
  const last = messages.at(-1);
  if (last?.id === id) return [...messages.slice(0, -1), { ...last, text: last.text + text }];
  return [...messages, { id, sender: 'bot', text, status: 'streaming' }];
}

// Chat state: sidebar history from the server, the open conversation, sending,
// stop and retry. Only the id of the open conversation is kept in localStorage.
// `language` is the interface language the answers should be written in.
export function useChat(language: HtmlLang) {
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
  // after Stop: waiting until the server has saved the stopped exchange
  const stopSyncRef = useRef<{ conversationId: string; done: Promise<void>; controller: AbortController } | null>(null);

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

  const cancelStopSync = useCallback(() => {
    stopSyncRef.current?.controller.abort();
    stopSyncRef.current = null;
  }, []);

  useEffect(() => cancelStopSync, [cancelStopSync]);

  // Polls until the stopped exchange is saved (or times out), then refreshes
  // the sidebar. A switch to another conversation cancels it.
  const startStopSync = useCallback((conversationId: string, stopped: StoppedExchange) => {
    cancelStopSync();
    const token = loadTokenRef.current;
    const controller = new AbortController();
    const done = waitForStoppedExchange({ conversationId, ...stopped, signal: controller.signal }).then(() => {
      if (stopSyncRef.current?.controller === controller) stopSyncRef.current = null;
      if (!controller.signal.aborted && token === loadTokenRef.current) void refreshHistory();
    });
    stopSyncRef.current = { conversationId, done, controller };
  }, [cancelStopSync, refreshHistory]);

  const openConversation = useCallback(async (id: string) => {
    cancelPending();
    cancelStopSync();
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
  }, [cancelPending, cancelStopSync]);

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
    cancelStopSync();
    loadTokenRef.current += 1;
    setIsRestored(true);
    setActiveId(null);
    setMessages([]);
    setLoadError(false);
    setIsLoadingConversation(false);
  }, [cancelPending, cancelStopSync]);

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
    const { signal } = controller;
    // id of the bot bubble that grows while the answer streams in
    const streamId = localId();
    const replaceStream = (message: ChatMessage) =>
      setMessages((prev) => [...prev.filter((m) => m.id !== streamId), message]);
    try {
      await streamMessage({ message: question, conversationId, regenerate, language, signal }, {
        onDelta: (text) => {
          if (!signal.aborted && text !== '') setMessages((prev) => appendDelta(prev, streamId, text));
        },
        onDone: (reply) => {
          if (signal.aborted) return;
          replaceStream(reply);
          void refreshHistory();
        },
        onError: () => {
          if (!signal.aborted) replaceStream(errorMarker());
        },
      });
    } catch (error) {
      if (signal.aborted || isSessionLost(error)) return;
      if (error instanceof ApiRequestError && error.status === 404) {
        // id taken by another account (practically impossible): retry under a fresh id
        setActiveId(newConversationId());
      }
      replaceStream(errorMarker());
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsWaiting(false);
      }
    }
  }, [language, refreshHistory]);

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
    // a new question supersedes the stopped one (its answer refreshes the list)
    cancelStopSync();
    void ask(question, conversationId, false, beginRequest());
    return true;
  }, [activeId, ask, beginRequest, cancelStopSync, isLoadingConversation, isWaiting]);

  const stop = useCallback(() => {
    if (abortRef.current === null) return;
    cancelPending();
    const markerId = localId();
    setMessages((prev) => stopStreaming(prev, markerId));
    // the server saves the question and the partial answer once it notices
    // the disconnect - refresh the list after that
    const stopped = describeStop(messages);
    if (activeId === null || stopped === null) {
      void refreshHistory();
      return;
    }
    startStopSync(activeId, stopped);
  }, [activeId, cancelPending, messages, refreshHistory, startStopSync]);

  const retry = useCallback(async () => {
    const lastQuestion = [...messages].reverse().find((m) => m.sender === 'user');
    if (lastQuestion === undefined || isWaiting) return;
    const conversationId = activeId ?? newConversationId();
    const token = loadTokenRef.current;
    const controller = beginRequest();
    setActiveId(conversationId);
    setMessages((prev) => prev.filter((m) => m.status === undefined));

    // right after Stop the partial answer may not be saved yet
    const pendingSync = stopSyncRef.current;
    if (pendingSync?.conversationId === conversationId) await pendingSync.done;
    if (controller.signal.aborted || token !== loadTokenRef.current) return;

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
