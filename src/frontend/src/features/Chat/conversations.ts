import { ApiRequestError, apiFetch, apiJson } from '../../lib/api';

// Chat API: history list, single conversation, delete, send. The server is the
// source of truth for conversations; the browser only remembers the open one.

// One chat bubble. Messages from the server have no status; "stopped" and
// "error" are local markers shown with a retry button.
export interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  status?: 'stopped' | 'error';
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  last_message_at: string;
}

export interface ConversationList {
  conversations: ConversationSummary[];
  max_per_user: number;
  retention_days: number;
}

export interface ApiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface ConversationDetail {
  messages: ApiMessage[];
}

interface ChatReply {
  message: ApiMessage;
}

// Same limit as the backend (request.py MAX_MESSAGE_LENGTH).
export const MAX_MESSAGE_LENGTH = 4000;

// New conversations are named by the client (32 hex chars, like uuid4().hex on
// the server), so a retry after an error or stop continues the same conversation
// instead of creating a duplicate. getRandomValues also works on plain http.
export function newConversationId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function toChatMessages(messages: readonly ApiMessage[]): ChatMessage[] {
  return messages.map((m) => ({
    id: m.id,
    sender: m.role === 'user' ? 'user' : 'bot',
    text: m.content,
  }));
}

// Retrying a failed/stopped question: regenerate only if the server already
// has that question as the last exchange. If the request never reached the
// server, regenerating would delete the previous (unrelated) answer instead.
export function shouldRegenerate(serverMessages: readonly ApiMessage[], question: string): boolean {
  const last = serverMessages.at(-1);
  if (last === undefined) return false;
  if (last.role === 'user') return last.content === question;
  const beforeLast = serverMessages.at(-2);
  return beforeLast?.role === 'user' && beforeLast.content === question;
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}

export function fetchConversations(): Promise<ConversationList> {
  return apiJson<ConversationList>('/conversations');
}

// null = the conversation no longer exists (deleted, expired or someone else's)
export async function fetchConversationMessages(id: string): Promise<ApiMessage[] | null> {
  try {
    const detail = await apiJson<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`);
    return detail.messages;
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

export async function deleteConversation(id: string): Promise<void> {
  try {
    await apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
  } catch (error) {
    // already gone counts as deleted
    if (!isNotFound(error)) throw error;
  }
}

interface SendMessageInput {
  message: string;
  conversationId: string;
  regenerate: boolean;
  signal: AbortSignal;
}

// Returns the assistant's answer as a chat bubble.
export async function sendMessage(input: SendMessageInput): Promise<ChatMessage> {
  const data = await apiJson<ChatReply>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: input.message,
      conversation_id: input.conversationId,
      regenerate: input.regenerate,
    }),
    signal: input.signal,
  });
  const [reply] = toChatMessages([data.message]);
  return reply;
}
