import type { Translation } from '../preferences/languages';
import type { AttachmentProblem } from './attachments';
import { formatResetTime } from './usage';

// The translated message for a refused file or a refused question.
export function describeAttachmentProblem(problem: AttachmentProblem, lang: Translation, now?: Date): string {
  const text = lang.attachments.problems;
  switch (problem.code) {
    case 'too_large':
      return text.tooLarge(problem.name ?? null, problem.maxMb ?? null);
    case 'empty':
      return text.empty(problem.name);
    case 'unsupported_type':
      return text.unsupportedType(problem.name);
    case 'unreadable':
      return text.unreadable(problem.name);
    case 'upload_failed':
      return text.uploadFailed(problem.name);
    case 'images_unsupported':
      return text.imagesUnsupported;
    case 'too_many':
      return text.tooMany(problem.maxFiles);
    case 'daily_limit':
      return text.dailyLimit(problem.limit, formatResetTime(problem.resetAt, lang.htmlLang, now));
    case 'disabled':
      return text.disabled;
    case 'not_found':
      return text.notFound;
    case 'chat_disabled':
      return lang.chatOffDefault;
    case 'upload_timeout':
      return text.uploadTimeout(problem.name);
    case 'busy':
      return text.busy;
    case 'storage_full':
      return text.storageFull;
    case 'storage_unavailable':
      return text.storageUnavailable;
  }
}
