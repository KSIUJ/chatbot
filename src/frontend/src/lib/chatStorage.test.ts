import { describe, expect, it } from 'vitest';
import { claimChatStorage, clearChatStorage } from './chatStorage';

class MemoryStorage {
  readonly items = new Map<string, string>();
  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
  removeItem(key: string): void {
    this.items.delete(key);
  }
}

describe('claimChatStorage', () => {
  it('drops the conversation id older versions reopened and other leftovers', () => {
    const storage = new MemoryStorage();
    storage.setItem('chatOwner', 'u1');
    storage.setItem('chatConversationId', 'abc');
    storage.setItem('chatMessages', '[]');
    storage.setItem('chatTheme', 'ciemny');

    claimChatStorage('u1', storage);

    expect(storage.items.has('chatConversationId')).toBe(false);
    expect(storage.items.has('chatMessages')).toBe(false);
    // preferences stay
    expect(storage.items.get('chatTheme')).toBe('ciemny');
    expect(storage.items.get('chatOwner')).toBe('u1');
  });

  it('records a new owner after an account change', () => {
    const storage = new MemoryStorage();
    storage.setItem('chatOwner', 'u1');

    claimChatStorage('u2', storage);

    expect(storage.items.get('chatOwner')).toBe('u2');
  });
});

describe('clearChatStorage', () => {
  it('forgets the owner on logout', () => {
    const storage = new MemoryStorage();
    storage.setItem('chatOwner', 'u1');

    clearChatStorage(storage);

    expect(storage.items.has('chatOwner')).toBe(false);
  });
});
