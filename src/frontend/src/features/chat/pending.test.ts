import { describe, expect, it } from 'vitest';
import { parsePending, updatePendingText, withPendingAnswer } from './pending';

describe('parsePending', () => {
  it('reads answers in progress and skips invalid entries', () => {
    const answers = parsePending({
      items: [
        { conversation_id: 'c1', question: 'Kto prowadzi ASD?', text: 'Wykład', started_at: '2026-10-26T10:00:00Z' },
        { conversation_id: 'c2', question: 'Hej', text: null },
        { question: 'bez rozmowy' },
        'nie obiekt',
      ],
    });

    expect(answers).toEqual([
      { conversationId: 'c1', question: 'Kto prowadzi ASD?', text: 'Wykład', startedAt: '2026-10-26T10:00:00Z' },
      { conversationId: 'c2', question: 'Hej', text: '', startedAt: '' },
    ]);
  });

  it('gives an empty list for a malformed body', () => {
    expect(parsePending(null)).toEqual([]);
    expect(parsePending({ items: 'x' })).toEqual([]);
  });
});

describe('withPendingAnswer', () => {
  const pending = { conversationId: 'c1', question: 'Kiedy sesja?', text: 'Sesja', startedAt: '' };

  it('shows the question and the text so far after the saved messages', () => {
    const saved = [
      { id: 'm1', role: 'user' as const, content: 'Hej', created_at: '2026-10-26T09:00:00Z' },
      { id: 'm2', role: 'assistant' as const, content: 'Cześć', created_at: '2026-10-26T09:00:01Z' },
    ];

    const messages = withPendingAnswer(saved as never, pending, 'q', 'b');

    expect(messages.map((m) => [m.sender, m.text, m.status])).toEqual([
      ['user', 'Hej', undefined],
      ['bot', 'Cześć', undefined],
      ['user', 'Kiedy sesja?', undefined],
      ['bot', 'Sesja', 'streaming'],
    ]);
  });

  it('works for a new conversation that is not saved yet', () => {
    expect(withPendingAnswer(null, pending, 'q', 'b').map((m) => m.id)).toEqual(['q', 'b']);
  });

  it('updates only the streaming bubble', () => {
    const messages = withPendingAnswer(null, pending, 'q', 'b');
    const updated = updatePendingText(messages, 'b', 'Sesja zimowa');

    expect(updated[1].text).toBe('Sesja zimowa');
    expect(updated[0]).toBe(messages[0]);
  });
});
