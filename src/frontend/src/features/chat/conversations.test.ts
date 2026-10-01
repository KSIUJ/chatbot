import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  deleteConversation,
  fetchConversationMessages,
  newConversationId,
  shouldRegenerate,
  toChatMessages,
  type ApiMessage,
} from './conversations';

const msg = (role: ApiMessage['role'], content: string, id = content): ApiMessage => ({ id, role, content });

describe('toChatMessages', () => {
  it('maps server roles to chat senders and keeps order', () => {
    const result = toChatMessages([msg('user', 'Kiedy sesja?'), msg('assistant', 'W lutym.')]);

    expect(result).toEqual([
      { id: 'Kiedy sesja?', sender: 'user', text: 'Kiedy sesja?' },
      { id: 'W lutym.', sender: 'bot', text: 'W lutym.' },
    ]);
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

describe('conversation requests', () => {
  const respondWith = (status: number, body: unknown = null) => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(body), { status })));
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the messages of an existing conversation', async () => {
    respondWith(200, { messages: [msg('user', 'pytanie')] });

    await expect(fetchConversationMessages('abc')).resolves.toEqual([msg('user', 'pytanie')]);
  });

  it('returns null for a conversation that no longer exists', async () => {
    respondWith(404);

    await expect(fetchConversationMessages('abc')).resolves.toBeNull();
  });

  it('rethrows other failures', async () => {
    respondWith(500);

    await expect(fetchConversationMessages('abc')).rejects.toMatchObject({ status: 500 });
  });

  it('treats deleting an already deleted conversation as success', async () => {
    respondWith(404);

    await expect(deleteConversation('abc')).resolves.toBeUndefined();
  });

  it('reports a failed delete', async () => {
    respondWith(502);

    await expect(deleteConversation('abc')).rejects.toMatchObject({ status: 502 });
  });
});
