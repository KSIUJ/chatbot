import { describe, expect, it } from 'vitest';
import {
  conversationTitle,
  newConversationId,
  removeConversation,
  shouldRegenerate,
  toChatMessages,
  type ApiMessage,
  type ConversationSummary,
} from './conversations';

const msg = (role: ApiMessage['role'], content: string, id = content): ApiMessage => ({
  id,
  role,
  content,
  created_at: '2026-10-01T10:00:00Z',
  sources: [],
});

const summary = (id: string, title: string | null = id): ConversationSummary => ({
  id,
  title,
  last_message_at: '2026-10-01T10:00:00Z',
});

describe('toChatMessages', () => {
  it('maps server roles to chat senders and keeps order', () => {
    const result = toChatMessages([msg('user', 'Kiedy sesja?'), msg('assistant', 'W lutym.')]);

    expect(result).toEqual([
      { id: 'Kiedy sesja?', sender: 'user', text: 'Kiedy sesja?' },
      { id: 'W lutym.', sender: 'bot', text: 'W lutym.' },
    ]);
  });
});

describe('removeConversation', () => {
  it('drops only the given conversation without mutating the list', () => {
    const list = [summary('a'), summary('b'), summary('c')];

    const result = removeConversation(list, 'b');

    expect(result.map((c) => c.id)).toEqual(['a', 'c']);
    expect(list).toHaveLength(3);
  });
});

describe('conversationTitle', () => {
  it('falls back when a conversation has no title', () => {
    expect(conversationTitle(summary('a', null), 'Nowa rozmowa')).toBe('Nowa rozmowa');
    expect(conversationTitle(summary('a', 'Sesja'), 'Nowa rozmowa')).toBe('Sesja');
  });
});

describe('newConversationId', () => {
  it('produces 32 lowercase hex characters, as the backend requires', () => {
    const ids = new Set(Array.from({ length: 50 }, () => newConversationId()));

    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{32}$/);
    expect(ids.size).toBe(50);
  });
});

describe('shouldRegenerate', () => {
  it('regenerates when the question was saved but no answer came back', () => {
    expect(shouldRegenerate([msg('assistant', 'hej'), msg('user', 'pytanie')], 'pytanie')).toBe(true);
  });

  it('regenerates when the last exchange is that question with an answer (e.g. after stop)', () => {
    expect(shouldRegenerate([msg('user', 'pytanie'), msg('assistant', 'odp')], 'pytanie')).toBe(true);
  });

  it('sends normally when the question never reached the server', () => {
    // regenerating here would delete the previous, unrelated answer
    expect(shouldRegenerate([msg('user', 'stare'), msg('assistant', 'stara odp')], 'nowe pytanie')).toBe(false);
    expect(shouldRegenerate([], 'pytanie')).toBe(false);
  });
});
