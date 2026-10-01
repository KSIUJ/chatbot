import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import type { ApiMessage, ChatMessage } from './conversations';
import { abortableSleep, describeStop, hasStoppedExchange, waitForStoppedExchange } from './stopSync';

const msg = (role: ApiMessage['role'], content: string, id = content): ApiMessage => ({ id, role, content });

describe('hasStoppedExchange', () => {
  const known = new Set(['old-q', 'old-a']);

  it('detects the saved question with a new partial answer', () => {
    expect(hasStoppedExchange([msg('user', 'pytanie', 'q'), msg('assistant', 'czę', 'a')], 'pytanie', known)).toBe(true);
  });

  it('waits while only the previous exchange is there', () => {
    expect(hasStoppedExchange([msg('user', 'pytanie', 'old-q'), msg('assistant', 'odp', 'old-a')], 'pytanie', known)).toBe(
      false,
    );
    expect(hasStoppedExchange([msg('user', 'pytanie', 'q')], 'pytanie', known)).toBe(false);
    expect(hasStoppedExchange([], 'pytanie', known)).toBe(false);
  });

  it('ignores an answer to another question', () => {
    expect(hasStoppedExchange([msg('user', 'inne', 'q'), msg('assistant', 'odp', 'a')], 'pytanie', known)).toBe(false);
  });
});

describe('describeStop', () => {
  const question: ChatMessage = { id: 'q', sender: 'user', text: 'pytanie' };

  it('takes the last question, the known ids and whether text arrived', () => {
    const answer: ChatMessage = { id: 'a0', sender: 'bot', text: 'stara' };
    const streaming: ChatMessage = { id: 's', sender: 'bot', text: 'czę', status: 'streaming' };

    expect(describeStop([answer, question, streaming])).toEqual({
      question: 'pytanie',
      knownIds: new Set(['a0', 'q']),
      hadText: true,
    });
  });

  it('reports no text when stopped before the first delta', () => {
    expect(describeStop([question])?.hadText).toBe(false);
  });

  it('has nothing to wait for without a question', () => {
    expect(describeStop([])).toBeNull();
  });
});

describe('waitForStoppedExchange', () => {
  const base = { conversationId: 'c1', question: 'pytanie', knownIds: new Set<string>() };
  const saved = [msg('user', 'pytanie', 'q'), msg('assistant', 'czę', 'a')];

  const setup = (responses: ReadonlyArray<ApiMessage[] | null | Error>) => {
    let call = 0;
    const fetchMessages = vi.fn(async () => {
      const response = responses[Math.min(call, responses.length - 1)];
      call += 1;
      if (response instanceof Error) throw response;
      return response;
    });
    const sleep = vi.fn(async () => undefined);
    return { fetchMessages, sleep };
  };

  it('polls until the partial answer is saved', async () => {
    const { fetchMessages, sleep } = setup([[msg('user', 'pytanie', 'q')], null, saved]);

    await waitForStoppedExchange({ ...base, hadText: true, signal: new AbortController().signal, fetchMessages, sleep });

    expect(fetchMessages).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenCalledWith(300, expect.any(AbortSignal));
  });

  it('gives up after about 3 seconds', async () => {
    const { fetchMessages, sleep } = setup([[]]);

    await waitForStoppedExchange({ ...base, hadText: true, signal: new AbortController().signal, fetchMessages, sleep });

    expect(fetchMessages).toHaveBeenCalledTimes(10);
  });

  it('checks only once, after a second, when nothing arrived before Stop', async () => {
    const { fetchMessages, sleep } = setup([[]]);

    await waitForStoppedExchange({ ...base, hadText: false, signal: new AbortController().signal, fetchMessages, sleep });

    expect(sleep).toHaveBeenCalledExactlyOnceWith(1000, expect.any(AbortSignal));
    expect(fetchMessages).toHaveBeenCalledTimes(1);
  });

  it('keeps polling through temporary errors', async () => {
    const { fetchMessages, sleep } = setup([new ApiRequestError(502, null), saved]);

    await waitForStoppedExchange({ ...base, hadText: true, signal: new AbortController().signal, fetchMessages, sleep });

    expect(fetchMessages).toHaveBeenCalledTimes(2);
  });

  it('stops at once when the session is lost', async () => {
    const { fetchMessages, sleep } = setup([new ApiRequestError(401, 'session_expired')]);

    await waitForStoppedExchange({ ...base, hadText: true, signal: new AbortController().signal, fetchMessages, sleep });

    expect(fetchMessages).toHaveBeenCalledTimes(1);
  });

  it('stops polling when cancelled (conversation switched)', async () => {
    const controller = new AbortController();
    const { fetchMessages } = setup([[]]);
    const sleep = vi.fn(async () => {
      if (sleep.mock.calls.length === 2) controller.abort();
    });

    await waitForStoppedExchange({ ...base, hadText: true, signal: controller.signal, fetchMessages, sleep });

    expect(fetchMessages).toHaveBeenCalledTimes(1);
  });
});

describe('abortableSleep', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves after the delay', async () => {
    vi.useFakeTimers();
    let resolved = false;
    void abortableSleep(300, new AbortController().signal).then(() => {
      resolved = true;
    });

    await vi.advanceTimersByTimeAsync(299);
    expect(resolved).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(resolved).toBe(true);
  });

  it('resolves early on abort', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const sleeping = abortableSleep(10_000, controller.signal);

    controller.abort();

    await expect(sleeping).resolves.toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });
});
