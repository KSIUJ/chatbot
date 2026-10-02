import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { isSessionLost } from '../../lib/api';
import {
  attachmentProblemOf,
  checkFiles,
  deleteAttachment,
  kindOfFile,
  MAX_PARALLEL_UPLOADS,
  uploadAttachment,
  type AttachmentLimits,
  type AttachmentMeta,
  type AttachmentProblem,
} from './attachments';
import { EMPTY_UPLOADS, isUploading, readyAttachments, uploadsReducer, type PendingUpload } from './uploads';

let uploadCounter = 0;
function uploadId(): string {
  uploadCounter += 1;
  return `upload-${Date.now()}-${uploadCounter}`;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export interface AttachmentsController {
  items: PendingUpload[];
  // files refused before uploading (type, size, count) - shown above the chips
  problems: AttachmentProblem[];
  isUploading: boolean;
  ready: AttachmentMeta[];
  // null = attachments are off (or the limits are not known yet)
  limits: AttachmentLimits | null;
  addFiles: (files: readonly File[]) => void;
  remove: (localId: string) => void;
  // after a successful send: the chips belong to the sent question now
  clearSent: () => void;
  dismissProblems: () => void;
}

// Attachment chips of the question input: pre-checks, immediate uploads with
// progress, cancel / remove (unsent files are deleted on the server).
// `onUploaded` refreshes today's usage after each stored file.
export function useAttachments(limits: AttachmentLimits | null, onUploaded: () => void): AttachmentsController {
  const [state, dispatch] = useReducer(uploadsReducer, EMPTY_UPLOADS);
  const [problems, setProblems] = useState<AttachmentProblem[]>([]);
  const controllersRef = useRef(new Map<string, AbortController>());
  // the latest chips for callbacks (count check, delete on remove)
  const itemsRef = useRef<PendingUpload[]>(state.items);
  useEffect(() => {
    itemsRef.current = state.items;
  }, [state.items]);

  // leaving the chat screen cancels uploads still running
  useEffect(() => {
    const controllers = controllersRef.current;
    return () => {
      for (const controller of controllers.values()) controller.abort();
      controllers.clear();
    };
  }, []);

  // files waiting for a free upload slot (the server allows MAX_PARALLEL_UPLOADS)
  const queueRef = useRef<{ localId: string; file: File }[]>([]);

  const startUpload = useCallback((file: File) => {
    const kind = kindOfFile(file);
    if (kind === null) return;
    const localId = uploadId();
    dispatch({ type: 'added', localId, name: file.name, size: file.size, kind });
    queueRef.current.push({ localId, file });

    // starts queued uploads while there are free slots; each finished upload
    // pumps again (the queue and the running uploads are shared refs)
    const pump = () => {
      while (controllersRef.current.size < MAX_PARALLEL_UPLOADS && queueRef.current.length > 0) {
        const next = queueRef.current.shift();
        if (next === undefined) return;
        const controller = new AbortController();
        controllersRef.current.set(next.localId, controller);
        const onProgress = (progress: number) => dispatch({ type: 'progress', localId: next.localId, progress });
        uploadAttachment(next.file, onProgress, controller.signal)
          .then((attachment) => dispatch({ type: 'uploaded', localId: next.localId, attachment }))
          .catch((error: unknown) => {
            // cancelled by the user (chip already gone) or a lost session (login screen)
            if (isAbort(error) || isSessionLost(error)) return;
            const problem = attachmentProblemOf(error, next.file.name) ?? { code: 'upload_failed', name: next.file.name };
            dispatch({ type: 'failed', localId: next.localId, problem });
          })
          .finally(() => {
            controllersRef.current.delete(next.localId);
            // every upload attempt counts towards the daily limit
            onUploaded();
            pump();
          });
      }
    };
    pump();
  }, [onUploaded]);

  const addFiles = useCallback((files: readonly File[]) => {
    if (files.length === 0) return;
    if (limits === null) {
      setProblems([{ code: 'disabled' }]);
      return;
    }
    const { accepted, problems: refused } = checkFiles(files, itemsRef.current.length, limits);
    setProblems(refused);
    accepted.forEach(startUpload);
  }, [limits, startUpload]);

  const remove = useCallback((localId: string) => {
    const item = itemsRef.current.find((i) => i.localId === localId);
    queueRef.current = queueRef.current.filter((queued) => queued.localId !== localId);
    controllersRef.current.get(localId)?.abort();
    dispatch({ type: 'removed', localId });
    // best effort: the server deletes unsent files after a day anyway
    if (item?.status === 'done' && item.attachment) void deleteAttachment(item.attachment.id).catch(() => undefined);
  }, []);

  const clearSent = useCallback(() => {
    dispatch({ type: 'cleared' });
    setProblems([]);
  }, []);

  const dismissProblems = useCallback(() => setProblems([]), []);

  return {
    items: state.items,
    problems,
    isUploading: isUploading(state),
    ready: readyAttachments(state),
    limits: limits !== null && limits.maxPerDay > 0 ? limits : null,
    addFiles,
    remove,
    clearSent,
    dismissProblems,
  };
}
