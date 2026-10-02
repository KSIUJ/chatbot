import { describe, expect, it } from 'vitest';
import type { ChatMessage } from './conversations';
import { appendDelta, attachmentMarker, dropUnsentQuestion, rateLimitMarker, stopStreaming, userQuestion } from './useChat';

const question: ChatMessage = { id: 'q', sender: 'user', text: 'Kiedy sesja?' };

describe('appendDelta', () => {
  it('starts a streaming bubble on the first delta', () => {
    expect(appendDelta([question], 's', 'W ')).toEqual([
      question,
      { id: 's', sender: 'bot', text: 'W ', status: 'streaming' },
    ]);
  });

  it('grows the streaming bubble without changing the input', () => {
    const before: ChatMessage[] = [question, { id: 's', sender: 'bot', text: 'W ', status: 'streaming' }];

    const after = appendDelta(before, 's', 'lutym.');

    expect(after.at(-1)).toEqual({ id: 's', sender: 'bot', text: 'W lutym.', status: 'streaming' });
    expect(before.at(-1)?.text).toBe('W ');
  });
});

describe('stopStreaming', () => {
  it('keeps the partial answer and marks it as stopped', () => {
    const streaming: ChatMessage = { id: 's', sender: 'bot', text: 'W lu', status: 'streaming' };

    expect(stopStreaming([question, streaming], 'm')).toEqual([
      question,
      { id: 's', sender: 'bot', text: 'W lu', status: 'stopped' },
    ]);
  });

  it('adds an empty stopped marker when nothing arrived yet', () => {
    expect(stopStreaming([question], 'm')).toEqual([question, { id: 'm', sender: 'bot', text: '', status: 'stopped' }]);
  });
});

describe('rateLimitMarker', () => {
  it('is an error marker carrying the daily limit info', () => {
    const info = { limit: 10, resetAt: '2026-10-02T22:00:00+00:00' };

    expect(rateLimitMarker('m', info)).toEqual({ id: 'm', sender: 'bot', text: '', status: 'error', rateLimit: info });
  });
});

describe('dropUnsentQuestion', () => {
  it('removes the trailing local question that the server refused', () => {
    const answer: ChatMessage = { id: 'a', sender: 'bot', text: 'W lutym.' };
    const unsent: ChatMessage = { id: 'local-1', sender: 'user', text: 'Kiedy sesja?' };

    expect(dropUnsentQuestion([question, answer, unsent], 'Kiedy sesja?')).toEqual([question, answer]);
  });

  it('keeps everything when the last message is not that question', () => {
    const answer: ChatMessage = { id: 'a', sender: 'bot', text: 'W lutym.' };

    expect(dropUnsentQuestion([question, answer], 'Kiedy sesja?')).toEqual([question, answer]);
    expect(dropUnsentQuestion([question], 'Inne pytanie')).toEqual([question]);
  });
});

describe('attachments in chat bubbles', () => {
  const file = { id: 'f1', name: 'plan.pdf', size: 10, type: 'pdf' as const };

  it('keeps the attachments of a question', () => {
    expect(userQuestion('q', 'Streszcz', [file])).toEqual({ id: 'q', sender: 'user', text: 'Streszcz', attachments: [file] });
  });

  it('adds no attachment field to a plain question', () => {
    expect(userQuestion('q', 'Kiedy sesja?', [])).toEqual({ id: 'q', sender: 'user', text: 'Kiedy sesja?' });
  });

  it('marks a question refused because of its attachments', () => {
    expect(attachmentMarker('m', { code: 'images_unsupported' })).toEqual({
      id: 'm',
      sender: 'bot',
      text: '',
      status: 'error',
      attachmentProblem: { code: 'images_unsupported' },
    });
  });
});
