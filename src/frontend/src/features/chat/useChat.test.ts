import { describe, expect, it } from 'vitest';
import type { ChatMessage } from './conversations';
import { appendDelta, stopStreaming } from './useChat';

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
