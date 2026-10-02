import { describe, expect, it } from 'vitest';
import { EMPTY_UPLOADS, isUploading, readyAttachments, uploadsReducer, type UploadsState } from './uploads';

const META = { id: 'srv-1', name: 'plan.pdf', size: 100, type: 'pdf' as const };

function added(): UploadsState {
  return uploadsReducer(EMPTY_UPLOADS, { type: 'added', localId: 'l1', name: 'plan.pdf', size: 100, kind: 'pdf' });
}

describe('uploadsReducer', () => {
  it('adds an uploading chip with zero progress', () => {
    expect(added().items).toEqual([
      { localId: 'l1', name: 'plan.pdf', size: 100, kind: 'pdf', status: 'uploading', progress: 0 },
    ]);
    expect(EMPTY_UPLOADS.items).toEqual([]);
  });

  it('tracks progress without going backwards or past 1', () => {
    let state = uploadsReducer(added(), { type: 'progress', localId: 'l1', progress: 0.6 });
    state = uploadsReducer(state, { type: 'progress', localId: 'l1', progress: 0.4 });
    expect(state.items[0].progress).toBe(0.6);

    state = uploadsReducer(state, { type: 'progress', localId: 'l1', progress: 3 });
    expect(state.items[0].progress).toBe(1);
  });

  it('marks a finished upload with the server attachment', () => {
    const state = uploadsReducer(added(), { type: 'uploaded', localId: 'l1', attachment: META });

    expect(state.items[0]).toMatchObject({ status: 'done', progress: 1, attachment: META, name: 'plan.pdf' });
    expect(readyAttachments(state)).toEqual([META]);
    expect(isUploading(state)).toBe(false);
  });

  it('keeps a failed upload with its problem until removed', () => {
    const state = uploadsReducer(added(), {
      type: 'failed',
      localId: 'l1',
      problem: { code: 'unreadable', name: 'plan.pdf' },
    });

    expect(state.items[0]).toMatchObject({ status: 'failed', problem: { code: 'unreadable', name: 'plan.pdf' } });
    expect(readyAttachments(state)).toEqual([]);
    expect(isUploading(state)).toBe(false);
  });

  it('ignores events of removed uploads', () => {
    const removed = uploadsReducer(added(), { type: 'removed', localId: 'l1' });

    expect(removed.items).toEqual([]);
    expect(uploadsReducer(removed, { type: 'uploaded', localId: 'l1', attachment: META })).toBe(removed);
  });

  it('reports uploads in progress', () => {
    expect(isUploading(added())).toBe(true);
  });

  it('clears everything after sending', () => {
    const state = uploadsReducer(added(), { type: 'uploaded', localId: 'l1', attachment: META });

    expect(uploadsReducer(state, { type: 'cleared' })).toEqual(EMPTY_UPLOADS);
  });
});
