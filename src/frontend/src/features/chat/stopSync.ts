import { isSessionLost } from '../../lib/api';
import { fetchConversationMessages, type ApiMessage, type ChatMessage } from './conversations';

// After Stop the server saves the question + partial answer only once it
// notices the disconnect. These helpers wait for that before the history
// refresh and before a retry decides whether to regenerate.

// Partial answer received: poll until it is saved.
const POLL_INTERVAL_MS = 300;
const POLL_ATTEMPTS = 10;
// Nothing received: the server most likely saved nothing - one late check.
const NO_TEXT_DELAY_MS = 1000;

// True once the server has the stopped exchange: a NEW assistant message
// (unknown id - not an older answer to the same question) after the question.
export function hasStoppedExchange(
  messages: readonly ApiMessage[],
  question: string,
  knownIds: ReadonlySet<string>,
): boolean {
  const last = messages.at(-1);
  const beforeLast = messages.at(-2);
  return (
    last?.role === 'assistant' &&
    !knownIds.has(last.id) &&
    beforeLast?.role === 'user' &&
    beforeLast.content === question
  );
}

export interface StoppedExchange {
  question: string;
  // ids of the messages the client already had before the stop
  knownIds: ReadonlySet<string>;
  // whether any part of the answer arrived before the stop
  hadText: boolean;
}

// What to wait for after stopping, from the messages as they were at Stop.
export function describeStop(messages: readonly ChatMessage[]): StoppedExchange | null {
  const question = messages.findLast((m) => m.sender === 'user');
  if (question === undefined) return null;
  const last = messages.at(-1);
  return {
    question: question.text,
    knownIds: new Set(messages.filter((m) => m.status === undefined).map((m) => m.id)),
    hadText: last?.status === 'streaming' && last.text !== '',
  };
}

export function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener('abort', done);
  });
}

export interface StopSyncInput extends StoppedExchange {
  conversationId: string;
  signal: AbortSignal;
  fetchMessages?: (id: string) => Promise<ApiMessage[] | null>;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

// Resolves when the stopped exchange is saved, on timeout, on abort or when
// the session is lost. Never rejects.
export async function waitForStoppedExchange({
  conversationId,
  question,
  knownIds,
  hadText,
  signal,
  fetchMessages = fetchConversationMessages,
  sleep = abortableSleep,
}: StopSyncInput): Promise<void> {
  const attempts = hadText ? POLL_ATTEMPTS : 1;
  const interval = hadText ? POLL_INTERVAL_MS : NO_TEXT_DELAY_MS;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await sleep(interval, signal);
    if (signal.aborted) return;
    try {
      const messages = await fetchMessages(conversationId);
      if (signal.aborted) return;
      if (messages !== null && hasStoppedExchange(messages, question, knownIds)) return;
    } catch (error) {
      // a lost session already switched the app to login; other failures:
      // keep trying until the timeout
      if (isSessionLost(error)) return;
    }
  }
}
