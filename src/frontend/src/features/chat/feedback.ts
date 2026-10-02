import { apiJson } from '../../lib/api';
import type { HtmlLang } from '../preferences/languages';
import type { ChatMessage } from './conversations';

// Ratings (thumbs up / down) and reports of bot answers - PUT /messages/{id}/feedback.

export type Rating = 1 | -1;

// Same values as ReportReason in src/backend/feedback/schemas.py.
export const REPORT_REASONS = ['wrong', 'outdated', 'inappropriate', 'other'] as const;

export type ReportReason = (typeof REPORT_REASONS)[number];

// Same limit as the backend (MAX_COMMENT_LENGTH).
export const MAX_REPORT_COMMENT_LENGTH = 1000;

// The current user's feedback on one answer.
export interface MessageFeedback {
  rating: Rating | null;
  reported: boolean;
}

export const EMPTY_FEEDBACK: MessageFeedback = { rating: null, reported: false };

export interface ReportInput {
  reason: ReportReason;
  comment: string | null;
}

// A left-out `rating` keeps the stored one; `null` clears it.
export interface FeedbackUpdate {
  rating?: Rating | null;
  report?: ReportInput;
  language: HtmlLang;
}

function isRating(value: unknown): value is Rating {
  return value === 1 || value === -1;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// The exact shape the server sends ({rating: 1 | -1 | null, reported: boolean}), or null.
function readFeedback(value: unknown): MessageFeedback | null {
  if (!isRecord(value)) return null;
  const { rating, reported } = value;
  if ((rating !== null && !isRating(rating)) || typeof reported !== 'boolean') return null;
  return { rating, reported };
}

// Server data is not trusted: no object = no feedback, a broken one = empty.
export function parseFeedback(value: unknown): MessageFeedback | undefined {
  if (!isRecord(value)) return undefined;
  return readFeedback(value) ?? EMPTY_FEEDBACK;
}

// Clicking the pressed thumb again removes the rating; a report stays.
export function toggleRating(current: MessageFeedback, clicked: Rating): MessageFeedback {
  return { ...current, rating: current.rating === clicked ? null : clicked };
}

// Messages with `feedback` set on message `id` (the same array if it is gone).
export function withFeedback(messages: ChatMessage[], id: string, feedback: MessageFeedback): ChatMessage[] {
  if (!messages.some((m) => m.id === id)) return messages;
  return messages.map((m) => (m.id === id ? { ...m, feedback } : m));
}

// Only finished answers saved on the server can be rated - not questions,
// streaming answers or the local stopped / error markers.
export function canGiveFeedback(message: ChatMessage): boolean {
  return message.sender === 'bot' && message.status === undefined;
}

export async function submitFeedback(messageId: string, update: FeedbackUpdate): Promise<MessageFeedback> {
  const saved = await apiJson<unknown>(`/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
  const feedback = readFeedback(saved);
  if (feedback === null) throw new Error('Invalid feedback response');
  return feedback;
}
