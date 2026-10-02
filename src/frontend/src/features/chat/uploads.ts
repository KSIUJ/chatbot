import type { AttachmentType } from '../admin/adminApi';
import type { AttachmentMeta, AttachmentProblem } from './attachments';

// State of the attachment chips above the question input: uploads in
// progress, finished (ready to send) and failed ones. Pure reducer.

export interface PendingUpload {
  // client-side id (the server id exists only after the upload)
  localId: string;
  name: string;
  size: number;
  kind: AttachmentType;
  status: 'uploading' | 'done' | 'failed';
  // 0..1
  progress: number;
  attachment?: AttachmentMeta;
  problem?: AttachmentProblem;
}

export interface UploadsState {
  items: PendingUpload[];
}

export type UploadsAction =
  | { type: 'added'; localId: string; name: string; size: number; kind: AttachmentType }
  | { type: 'progress'; localId: string; progress: number }
  | { type: 'uploaded'; localId: string; attachment: AttachmentMeta }
  | { type: 'failed'; localId: string; problem: AttachmentProblem }
  | { type: 'removed'; localId: string }
  | { type: 'cleared' };

export const EMPTY_UPLOADS: UploadsState = { items: [] };

function update(state: UploadsState, localId: string, change: (item: PendingUpload) => PendingUpload): UploadsState {
  if (!state.items.some((item) => item.localId === localId)) return state;
  return { items: state.items.map((item) => (item.localId === localId ? change(item) : item)) };
}

export function uploadsReducer(state: UploadsState, action: UploadsAction): UploadsState {
  switch (action.type) {
    case 'added':
      return {
        items: [
          ...state.items,
          { localId: action.localId, name: action.name, size: action.size, kind: action.kind, status: 'uploading', progress: 0 },
        ],
      };
    case 'progress':
      return update(state, action.localId, (item) => ({
        ...item,
        progress: Math.min(1, Math.max(item.progress, action.progress)),
      }));
    case 'uploaded':
      return update(state, action.localId, (item) => ({
        ...item,
        status: 'done',
        progress: 1,
        attachment: action.attachment,
      }));
    case 'failed':
      return update(state, action.localId, (item) => ({ ...item, status: 'failed', problem: action.problem }));
    case 'removed':
      return { items: state.items.filter((item) => item.localId !== action.localId) };
    case 'cleared':
      return EMPTY_UPLOADS;
  }
}

export function isUploading(state: UploadsState): boolean {
  return state.items.some((item) => item.status === 'uploading');
}

// Attachments ready to go with the next question.
export function readyAttachments(state: UploadsState): AttachmentMeta[] {
  return state.items.flatMap((item) => (item.status === 'done' && item.attachment ? [item.attachment] : []));
}
