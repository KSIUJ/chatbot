import { describe, expect, it } from 'vitest';
import { ACTIVE_CONVERSATION_KEY, rememberActiveConversation } from './chatStorage';

class MemoryStorage {
  readonly items = new Map<string, string>();
  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
  removeItem(key: string): void {
    this.items.delete(key);
  }
}

const storageWith = (id: string): MemoryStorage => {
  const storage = new MemoryStorage();
  storage.setItem(ACTIVE_CONVERSATION_KEY, id);
  return storage;
};

describe('rememberActiveConversation', () => {
  it('stores the open conversation', () => {
    const storage = storageWith('old');

    rememberActiveConversation('new', false, storage);

    expect(storage.items.get(ACTIVE_CONVERSATION_KEY)).toBe('new');
  });

  it('keeps the remembered conversation while the initial load has not succeeded', () => {
    const storage = storageWith('old');

    rememberActiveConversation(null, false, storage);

    expect(storage.items.get(ACTIVE_CONVERSATION_KEY)).toBe('old');
  });

  it('forgets it once nothing is open on purpose', () => {
    const storage = storageWith('old');

    rememberActiveConversation(null, true, storage);

    expect(storage.items.has(ACTIVE_CONVERSATION_KEY)).toBe(false);
  });
});
