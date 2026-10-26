import { apiFetch, apiJson } from '../../lib/api';
import { toChatMessages, type ApiMessage, type ChatMessage } from './conversations';

// Answers still being written on the server (GET /chat/pending) and the Stop
// request (POST /chat/stop). A reload or a closed tab does not stop an answer:
// the server keeps writing and saves it, and the page shows it again with the
// text so far, polling until it is saved. Only Stop ends it early.

export const PENDING_POLL_MS = 1000;

export interface PendingAnswer {
  conversationId: string;
  question: string;
  // answer text written so far
  text: string;
  startedAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// Invalid entries are skipped; a malformed body gives an empty list.
export function parsePending(value: unknown): PendingAnswer[] {
  if (!isRecord(value) || !Array.isArray(value.items)) return [];
  const answers: PendingAnswer[] = [];
  for (const item of value.items) {
    if (!isRecord(item)) continue;
    const { conversation_id: conversationId, question, text, started_at: startedAt } = item;
    if (typeof conversationId !== 'string' || typeof question !== 'string') continue;
    answers.push({
      conversationId,
      question,
      text: typeof text === 'string' ? text : '',
      startedAt: typeof startedAt === 'string' ? startedAt : '',
    });
  }
  return answers;
}

export async function fetchPending(): Promise<PendingAnswer[]> {
  return parsePending(await apiJson<unknown>('/chat/pending'));
}

// Asks the server to end the answer of the conversation (Stop button). Best
// effort: a failure only means the answer is written to the end.
export async function requestStop(conversationId: string): Promise<void> {
  await apiFetch('/chat/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
}

// Messages of a conversation with an answer in progress: the saved messages
// (none for a new conversation), the pending question and the answer so far as
// a streaming bubble with the given id.
export function withPendingAnswer(
  saved: readonly ApiMessage[] | null,
  pending: PendingAnswer,
  questionId: string,
  bubbleId: string,
): ChatMessage[] {
  return [
    ...toChatMessages(saved ?? []),
    { id: questionId, sender: 'user', text: pending.question },
    { id: bubbleId, sender: 'bot', text: pending.text, status: 'streaming' },
  ];
}

// The streaming bubble with the latest text from the server.
export function updatePendingText(messages: readonly ChatMessage[], bubbleId: string, text: string): ChatMessage[] {
  return messages.map((m) => (m.id === bubbleId && m.text !== text ? { ...m, text } : m));
}
