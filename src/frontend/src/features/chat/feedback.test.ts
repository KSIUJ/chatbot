import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import { translations } from '../preferences/languages';
import { toChatMessages, type ChatMessage } from './conversations';
import {
  EMPTY_FEEDBACK,
  MAX_REPORT_COMMENT_LENGTH,
  REPORT_REASONS,
  canGiveFeedback,
  parseFeedback,
  submitFeedback,
  toggleRating,
  withFeedback,
} from './feedback';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('parseFeedback', () => {
  it('reads the state sent by the server', () => {
    expect(parseFeedback({ rating: 1, reported: false })).toEqual({ rating: 1, reported: false });
    expect(parseFeedback({ rating: -1, reported: true })).toEqual({ rating: -1, reported: true });
    expect(parseFeedback({ rating: null, reported: true })).toEqual({ rating: null, reported: true });
  });

  it('treats malformed values as no feedback', () => {
    expect(parseFeedback(undefined)).toBeUndefined();
    expect(parseFeedback(null)).toBeUndefined();
    expect(parseFeedback('up')).toBeUndefined();
    expect(parseFeedback({ rating: 5, reported: 'yes' })).toEqual(EMPTY_FEEDBACK);
  });
});

describe('toggleRating', () => {
  it('sets a rating and switches between up and down', () => {
    expect(toggleRating(EMPTY_FEEDBACK, 1)).toEqual({ rating: 1, reported: false });
    expect(toggleRating({ rating: 1, reported: false }, -1)).toEqual({ rating: -1, reported: false });
  });

  it('clears the rating when the pressed button is clicked again, keeping the report', () => {
    expect(toggleRating({ rating: -1, reported: true }, -1)).toEqual({ rating: null, reported: true });
  });
});

describe('withFeedback', () => {
  const question: ChatMessage = { id: 'q', sender: 'user', text: 'Kiedy sesja?' };
  const answer: ChatMessage = { id: 'a', sender: 'bot', text: 'W lutym.' };

  it('updates only the given message and leaves the input untouched', () => {
    const before = [question, answer];

    const after = withFeedback(before, 'a', { rating: 1, reported: false });

    expect(after).toEqual([question, { ...answer, feedback: { rating: 1, reported: false } }]);
    expect(before[1].feedback).toBeUndefined();
    expect(after[0]).toBe(question);
  });

  it('returns the same messages when the id is gone (switched conversation)', () => {
    const before = [question, answer];

    expect(withFeedback(before, 'other', EMPTY_FEEDBACK)).toBe(before);
  });
});

describe('canGiveFeedback', () => {
  it('allows finished answers only', () => {
    expect(canGiveFeedback({ id: 'a', sender: 'bot', text: 'W lutym.' })).toBe(true);
    expect(canGiveFeedback({ id: 'q', sender: 'user', text: 'pytanie' })).toBe(false);
    expect(canGiveFeedback({ id: 's', sender: 'bot', text: 'W lu', status: 'streaming' })).toBe(false);
    expect(canGiveFeedback({ id: 's', sender: 'bot', text: 'W lu', status: 'stopped' })).toBe(false);
    expect(canGiveFeedback({ id: 'e', sender: 'bot', text: '', status: 'error' })).toBe(false);
  });
});

describe('toChatMessages with feedback', () => {
  it('keeps the feedback of answers after a reload', () => {
    const [answer] = toChatMessages([
      { id: 'a1', role: 'assistant', content: 'W lutym.', feedback: { rating: -1, reported: true } },
    ]);

    expect(answer).toEqual({ id: 'a1', sender: 'bot', text: 'W lutym.', feedback: { rating: -1, reported: true } });
  });

  it('leaves feedback out of questions and when the server sends none', () => {
    const result = toChatMessages([
      { id: 'q', role: 'user', content: 'pytanie', feedback: { rating: 1, reported: false } },
      { id: 'a', role: 'assistant', content: 'odp' },
    ]);

    expect(result).toEqual([
      { id: 'q', sender: 'user', text: 'pytanie' },
      { id: 'a', sender: 'bot', text: 'odp' },
    ]);
  });
});

describe('submitFeedback', () => {
  it('sends a PUT with the rating, report and language and returns the saved state', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ rating: null, reported: true }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const state = await submitFeedback('a/1', {
      rating: null,
      report: { reason: 'outdated', comment: 'stary termin' },
      language: 'pl',
    });

    expect(state).toEqual({ rating: null, reported: true });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/messages/a%2F1/feedback');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({
      rating: null,
      report: { reason: 'outdated', comment: 'stary termin' },
      language: 'pl',
    });
  });

  it('throws ApiRequestError when the server refuses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));

    await expect(submitFeedback('a', { rating: 1, language: 'en' })).rejects.toBeInstanceOf(ApiRequestError);
  });

  it('rejects a malformed answer from the server', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"rating": 7}', { status: 200 })));

    await expect(submitFeedback('a', { rating: 1, language: 'en' })).rejects.toThrow();
  });
});

describe('report translations', () => {
  it('name every report reason in every language', () => {
    for (const lang of Object.values(translations)) {
      for (const reason of REPORT_REASONS) expect(lang.reportReasons[reason].trim()).not.toBe('');
      expect(lang.reportTitle.trim()).not.toBe('');
      expect(lang.rateUp).not.toBe(lang.rateDown);
    }
  });

  it('matches the backend comment limit', () => {
    expect(MAX_REPORT_COMMENT_LENGTH).toBe(1000);
  });
});
