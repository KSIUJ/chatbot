import { ApiRequestError, apiFetch, apiJson } from '../../lib/api';
import type { HtmlLang } from '../preferences/languages';
import { parseSources, type Source } from './sources';

// Chat API: history list, single conversation, delete, send. The server is the
// source of truth for conversations; the browser only remembers the open one.

// One chat bubble. Messages from the server have no status. "streaming" is an
// answer still arriving; "stopped" and "error" are local markers shown with a
// retry button (a stopped answer may keep the text received so far).
export interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  status?: 'streaming' | 'stopped' | 'error';
  sources?: Source[];
}

export function isMarker(message: ChatMessage): boolean {
  return message.status === 'stopped' || message.status === 'error';
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
  // validated by parseSources, so an older backend without it still works
  sources?: unknown;
}

interface ConversationDetail {
  messages: ApiMessage[];
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

function toChatMessage(m: ApiMessage): ChatMessage {
  if (m.role === 'user') return { id: m.id, sender: 'user', text: m.content };
  const sources = parseSources(m.sources);
  return { id: m.id, sender: 'bot', text: m.content, ...(sources.length > 0 ? { sources } : {}) };
}

export function toChatMessages(messages: readonly ApiMessage[]): ChatMessage[] {
  return messages.map(toChatMessage);
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

// ---- streaming answers (POST /chat/stream, server-sent events) ----

export interface SseEvent {
  event: string;
  data: string;
}

export interface SseParseResult {
  events: SseEvent[];
  // unfinished tail, passed back in with the next chunk (opaque to callers)
  rest: string;
}

// Marks a tail whose chunk ended with CR: that CR already ended a line, so a
// LF at the start of the next chunk is the second half of CRLF.
const PENDING_CR = '\r';

const SSE_LINE_BREAK = /\r\n|\r|\n/g;

function parseSseBlock(block: string): SseEvent | null {
  let event = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    // blank lines and ":" comments (keep-alives) carry nothing
    if (line === '' || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    const raw = colon === -1 ? '' : line.slice(colon + 1);
    const value = raw.startsWith(' ') ? raw.slice(1) : raw;
    if (field === 'event') event = value || 'message';
    else if (field === 'data') data.push(value);
  }
  // per the SSE spec an event without data is not dispatched
  return data.length === 0 ? null : { event, data: data.join('\n') };
}

// Pure SSE parser: feed decoded chunks one by one, they may split events or
// lines anywhere. Accepts LF, CRLF and CR line endings.
export function parseSseChunk(rest: string, chunk: string): SseParseResult {
  const afterCr = rest.endsWith(PENDING_CR);
  const carried = afterCr ? rest.slice(0, -1) : rest;
  const incoming = afterCr && chunk.startsWith('\n') ? chunk.slice(1) : chunk;
  // the tail is kept normalized, so only the new chunk can contain CRs
  const blocks = (carried + incoming.replace(SSE_LINE_BREAK, '\n')).split('\n\n');
  const tail = blocks.pop() ?? '';
  const events = blocks.map(parseSseBlock).filter((event): event is SseEvent => event !== null);
  return { events, rest: incoming.endsWith('\r') ? tail + PENDING_CR : tail };
}

export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; message: ChatMessage }
  | { type: 'error'; code: string };

// Error codes detected on the client (the server sends e.g. "llm_failed").
export const STREAM_ERROR_INVALID_EVENT = 'invalid_event';
export const STREAM_ERROR_INTERRUPTED = 'stream_interrupted';
export const STREAM_ERROR_INVALID_RESPONSE = 'invalid_response';

const INVALID_EVENT: StreamEvent = { type: 'error', code: STREAM_ERROR_INVALID_EVENT };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseDoneMessage(value: unknown): ChatMessage | null {
  if (!isRecord(value)) return null;
  const { id, role, content, sources } = value;
  if (typeof id !== 'string' || role !== 'assistant' || typeof content !== 'string') return null;
  return toChatMessage({ id, role, content, sources });
}

// Maps an SSE event to a chat stream event; unknown event names give null.
// Known events with a malformed payload become an error.
export function toStreamEvent(sse: SseEvent): StreamEvent | null {
  if (sse.event !== 'delta' && sse.event !== 'done' && sse.event !== 'error') return null;
  let payload: unknown;
  try {
    payload = JSON.parse(sse.data);
  } catch {
    return INVALID_EVENT;
  }
  if (!isRecord(payload)) return INVALID_EVENT;

  if (sse.event === 'delta') {
    return typeof payload.text === 'string' ? { type: 'delta', text: payload.text } : INVALID_EVENT;
  }
  if (sse.event === 'done') {
    const message = parseDoneMessage(payload.message);
    return message === null ? INVALID_EVENT : { type: 'done', message };
  }
  return { type: 'error', code: typeof payload.code === 'string' ? payload.code : STREAM_ERROR_INVALID_EVENT };
}

async function* readSseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let rest = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      const parsed = parseSseChunk(rest, done ? decoder.decode() : decoder.decode(value, { stream: true }));
      rest = parsed.rest;
      yield* parsed.events;
      if (done) return;
    }
  } finally {
    // the consumer stopped early (final event) or reading failed: release the
    // connection; a rejection here means it is already closed or aborted
    reader.cancel().catch(() => undefined);
  }
}

interface SendMessageInput {
  message: string;
  conversationId: string;
  regenerate: boolean;
  language: HtmlLang;
  signal: AbortSignal;
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (reply: ChatMessage) => void;
  onError: (code: string) => void;
}

// Sends a question and streams the answer. HTTP errors before the stream
// starts throw ApiRequestError (like every API call); an abort throws an
// AbortError. Otherwise exactly one of onDone / onError ends the stream - a
// stream that ends without either (network drop) is reported as an error.
export async function streamMessage(input: SendMessageInput, handlers: StreamHandlers): Promise<void> {
  const response = await apiFetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      message: input.message,
      conversation_id: input.conversationId,
      regenerate: input.regenerate,
      language: input.language,
    }),
    signal: input.signal,
  });
  const contentType = response.headers.get('content-type') ?? '';
  if (response.body === null || !contentType.includes('text/event-stream')) {
    handlers.onError(STREAM_ERROR_INVALID_RESPONSE);
    return;
  }

  for await (const sse of readSseEvents(response.body)) {
    input.signal.throwIfAborted();
    const event = toStreamEvent(sse);
    if (event === null) continue;
    if (event.type === 'delta') {
      handlers.onDelta(event.text);
      continue;
    }
    if (event.type === 'done') handlers.onDone(event.message);
    else handlers.onError(event.code);
    return;
  }
  input.signal.throwIfAborted();
  handlers.onError(STREAM_ERROR_INTERRUPTED);
}
