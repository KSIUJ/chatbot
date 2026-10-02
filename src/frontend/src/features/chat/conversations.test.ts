import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import {
  STREAM_ERROR_INTERRUPTED,
  STREAM_ERROR_INVALID_EVENT,
  STREAM_ERROR_INVALID_RESPONSE,
  deleteConversation,
  fetchConversationMessages,
  newConversationId,
  parseSseChunk,
  shouldRegenerate,
  streamMessage,
  toChatMessages,
  toStreamEvent,
  type ApiMessage,
  type ChatMessage,
  type SseEvent,
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

  it('keeps valid sources of answers and drops broken ones', () => {
    const source = { kind: 'strony', title: 'Harmonogram', url: 'https://www.wmii.uj.edu.pl/h' };
    const answer = { ...msg('assistant', 'W lutym.', 'a1'), sources: [source, { kind: '?', title: 'x' }] };

    expect(toChatMessages([answer])).toEqual([{ id: 'a1', sender: 'bot', text: 'W lutym.', sources: [source] }]);
  });

  it('leaves out sources when there are none or the field is missing', () => {
    const [withEmpty] = toChatMessages([{ ...msg('assistant', 'odp', 'a1'), sources: [] }]);
    const [withoutField] = toChatMessages([msg('assistant', 'odp', 'a2')]);

    expect(withEmpty).not.toHaveProperty('sources');
    expect(withoutField).not.toHaveProperty('sources');
  });
});

// Feeds chunks through the parser like the stream reader does.
function parseAll(chunks: readonly string[]): { events: SseEvent[]; rest: string } {
  return chunks.reduce<{ events: SseEvent[]; rest: string }>(
    (acc, chunk) => {
      const parsed = parseSseChunk(acc.rest, chunk);
      return { events: [...acc.events, ...parsed.events], rest: parsed.rest };
    },
    { events: [], rest: '' },
  );
}

describe('parseSseChunk', () => {
  it('parses several events from one chunk', () => {
    const { events, rest } = parseAll(['event: delta\ndata: {"text":"Ala"}\n\nevent: delta\ndata: {"text":" ma"}\n\n']);

    expect(events).toEqual([
      { event: 'delta', data: '{"text":"Ala"}' },
      { event: 'delta', data: '{"text":" ma"}' },
    ]);
    expect(rest).toBe('');
  });

  it('joins an event split across chunks at any position', () => {
    const raw = 'event: delta\r\ndata: {"text":"kota"}\r\n\r\n';
    for (let cut = 1; cut < raw.length; cut += 1) {
      const { events } = parseAll([raw.slice(0, cut), raw.slice(cut)]);
      expect(events).toEqual([{ event: 'delta', data: '{"text":"kota"}' }]);
    }
  });

  it('accepts CRLF and CR line endings, also when CR and LF land in different chunks', () => {
    const { events } = parseAll(['event: done\r\ndata: {}\r', '\n\r', '\nevent: delta\rdata: 1\r\r']);

    expect(events).toEqual([
      { event: 'done', data: '{}' },
      { event: 'delta', data: '1' },
    ]);
  });

  it('keeps an unfinished event for the next chunk', () => {
    const { events, rest } = parseAll(['event: delta\ndata: {"te']);

    expect(events).toEqual([]);
    expect(rest).toBe('event: delta\ndata: {"te');
  });

  it('ignores comments, unknown fields and events without data', () => {
    const { events } = parseAll([': keep-alive\n\nid: 7\nretry: 100\nevent: delta\ndata: x\n\nevent: ping\n\n']);

    expect(events).toEqual([{ event: 'delta', data: 'x' }]);
  });

  it('joins multi-line data and defaults the event name to message', () => {
    const { events } = parseAll(['data: a\ndata:b\n\n']);

    expect(events).toEqual([{ event: 'message', data: 'a\nb' }]);
  });
});

describe('toStreamEvent', () => {
  const answer = { id: 'm1', role: 'assistant', content: 'Ala ma kota', created_at: '2026-10-01T10:00:00Z', sources: [] };

  it('reads delta, done and error events', () => {
    expect(toStreamEvent({ event: 'delta', data: '{"text":"Ala "}' })).toEqual({ type: 'delta', text: 'Ala ' });
    expect(toStreamEvent({ event: 'done', data: JSON.stringify({ conversation_id: 'c', message: answer }) })).toEqual({
      type: 'done',
      message: { id: 'm1', sender: 'bot', text: 'Ala ma kota' },
    });
    expect(toStreamEvent({ event: 'error', data: '{"code":"llm_failed","message":"x"}' })).toEqual({
      type: 'error',
      code: 'llm_failed',
    });
  });

  it('ignores unknown events', () => {
    expect(toStreamEvent({ event: 'message', data: '{}' })).toBeNull();
    expect(toStreamEvent({ event: 'progress', data: 'not json' })).toBeNull();
  });

  it('turns a malformed known event into an error', () => {
    const invalid = { type: 'error', code: STREAM_ERROR_INVALID_EVENT };
    expect(toStreamEvent({ event: 'delta', data: 'not json' })).toEqual(invalid);
    expect(toStreamEvent({ event: 'delta', data: '{"text":5}' })).toEqual(invalid);
    expect(toStreamEvent({ event: 'done', data: '{"message":{"id":"m1","role":"user","content":"x"}}' })).toEqual(invalid);
    expect(toStreamEvent({ event: 'done', data: '[]' })).toEqual(invalid);
    expect(toStreamEvent({ event: 'error', data: '{}' })).toEqual(invalid);
  });
});

describe('streamMessage', () => {
  const encoder = new TextEncoder();

  const bodyOf = (chunks: readonly Uint8Array[]) =>
    new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk);
        controller.close();
      },
    });

  const streamResponse = (chunks: readonly string[], contentType = 'text/event-stream; charset=utf-8') =>
    new Response(bodyOf(chunks.map((chunk) => encoder.encode(chunk))), {
      status: 200,
      headers: { 'Content-Type': contentType },
    });

  const run = async (response: Response, signal = new AbortController().signal) => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);
    const deltas: string[] = [];
    const done: ChatMessage[] = [];
    const errors: string[] = [];
    await streamMessage(
      { message: 'Kiedy sesja?', conversationId: 'c1', regenerate: false, language: 'en', signal },
      { onDelta: (text) => deltas.push(text), onDone: (reply) => done.push(reply), onError: (code) => errors.push(code) },
    );
    return { fetchMock, deltas, done, errors };
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts the question with the interface language to the stream endpoint', async () => {
    const { fetchMock } = await run(streamResponse([]));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/chat/stream');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      message: 'Kiedy sesja?',
      conversation_id: 'c1',
      regenerate: false,
      language: 'en',
    });
  });

  it('streams deltas and finishes with the saved message', async () => {
    const source = { kind: 'usos', title: 'dr Nowak', url: 'https://usosweb.uj.edu.pl/x' };
    const final = { id: 'm1', role: 'assistant', content: 'W lutym.', created_at: 'x', sources: [source] };
    const { deltas, done, errors } = await run(
      streamResponse([
        'event: delta\ndata: {"text":"W "}\n\nevent: del',
        'ta\ndata: {"text":"lutym."}\n\n: ping\n\n',
        `event: done\ndata: ${JSON.stringify({ conversation_id: 'c1', message: final })}\n\n`,
      ]),
    );

    expect(deltas).toEqual(['W ', 'lutym.']);
    expect(done).toEqual([{ id: 'm1', sender: 'bot', text: 'W lutym.', sources: [source] }]);
    expect(errors).toEqual([]);
  });

  it('decodes multi-byte characters split between chunks', async () => {
    const bytes = encoder.encode('event: delta\ndata: {"text":"źródło"}\n\n');
    const cut = bytes.indexOf(0xc5) + 1; // inside "ź"
    const response = new Response(bodyOf([bytes.slice(0, cut), bytes.slice(cut)]), {
      headers: { 'Content-Type': 'text/event-stream' },
    });

    const { deltas, errors } = await run(response);

    expect(deltas).toEqual(['źródło']);
    expect(errors).toEqual([STREAM_ERROR_INTERRUPTED]);
  });

  it('reports an error event from the server', async () => {
    const { deltas, done, errors } = await run(
      streamResponse(['event: delta\ndata: {"text":"W"}\n\nevent: error\ndata: {"code":"llm_failed","message":"x"}\n\n']),
    );

    expect(deltas).toEqual(['W']);
    expect(done).toEqual([]);
    expect(errors).toEqual(['llm_failed']);
  });

  it('reports a stream that ends without done or error as interrupted', async () => {
    const { errors } = await run(streamResponse(['event: delta\ndata: {"text":"W"}\n\nevent: done\ndata: {"mess']));

    expect(errors).toEqual([STREAM_ERROR_INTERRUPTED]);
  });

  it('rejects a response that is not an event stream', async () => {
    const { errors } = await run(streamResponse(['<html></html>'], 'text/html'));

    expect(errors).toEqual([STREAM_ERROR_INVALID_RESPONSE]);
  });

  it('throws HTTP errors before the stream like other API calls', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 422 })));
    const noop = () => undefined;

    const call = streamMessage(
      { message: 'x', conversationId: 'c1', regenerate: false, language: 'pl', signal: new AbortController().signal },
      { onDelta: noop, onDone: noop, onError: noop },
    );

    await expect(call).rejects.toBeInstanceOf(ApiRequestError);
    await expect(call).rejects.toMatchObject({ status: 422 });
  });

  it('stops with an AbortError once aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(run(streamResponse(['event: delta\ndata: {"text":"W"}\n\n']), controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    });
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

describe('attachments in conversations', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps valid attachments of user questions', () => {
    const question: ApiMessage = {
      ...msg('user', 'Streszcz plik', 'q1'),
      attachments: [{ id: 'f1', name: 'plan.pdf', size: 1200, type: 'pdf' }, { id: 'bad' }],
    };

    expect(toChatMessages([question])).toEqual([
      {
        id: 'q1',
        sender: 'user',
        text: 'Streszcz plik',
        attachments: [{ id: 'f1', name: 'plan.pdf', size: 1200, type: 'pdf' }],
      },
    ]);
  });

  it('sends attachment ids with the question', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response('', { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await streamMessage(
      {
        message: 'Streszcz',
        conversationId: 'c1',
        regenerate: false,
        language: 'pl',
        signal: new AbortController().signal,
        attachmentIds: ['f1', 'f2'],
      },
      { onDelta: () => undefined, onDone: () => undefined, onError: () => undefined },
    );

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({ attachment_ids: ['f1', 'f2'] });
  });
});
