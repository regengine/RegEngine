import type { EpcisIngestResponse, NormalizedEpcisResult } from '@/types/api';

export type ParsedEpcisJson =
  | { kind: 'batch'; events: Record<string, unknown>[] }
  | { kind: 'single'; event: Record<string, unknown> };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Sort uploaded EPCIS JSON into the shape the backend expects.
 *
 * An EPCISDocument carrying epcisBody.eventList and a bare JSON array of
 * events both go to POST /api/v1/epcis/events/batch; a single event object
 * goes to POST /api/v1/epcis/events. Anything else is a client error with
 * no request sent.
 */
export function parseEpcisJson(text: string): ParsedEpcisJson {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error('Could not parse the file as JSON. Upload a GS1 EPCIS 2.0 JSON document, a JSON array of events, or a single event object.');
  }
  if (Array.isArray(parsed)) {
    if (parsed.length === 0 || !parsed.every(isRecord)) {
      throw new Error('No EPCIS events found in the file. Upload a GS1 EPCIS 2.0 JSON document, a JSON array of events, or a single event object.');
    }
    return { kind: 'batch', events: parsed };
  }
  if (isRecord(parsed)) {
    const body = parsed.epcisBody;
    if (isRecord(body) && Array.isArray(body.eventList)) {
      if (body.eventList.length === 0 || !body.eventList.every(isRecord)) {
        throw new Error('No EPCIS events found in the file. The document epcisBody.eventList is empty.');
      }
      return { kind: 'batch', events: body.eventList as Record<string, unknown>[] };
    }
    return { kind: 'single', event: parsed };
  }
  throw new Error('No EPCIS events found in the file. Upload a GS1 EPCIS 2.0 JSON document, a JSON array of events, or a single event object.');
}

function detailToMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (typeof item === 'string' ? item : isRecord(item) ? detailToMessage(item.msg ?? item.message) : null))
      .filter((part): part is string => typeof part === 'string' && part.length > 0);
    return parts.length > 0 ? parts.join(': ') : null;
  }
  if (isRecord(detail)) {
    const message = detail.message;
    const errors = detail.errors;
    const parts: string[] = [];
    if (typeof message === 'string' && message.trim()) parts.push(message);
    const nested = detailToMessage(errors);
    if (nested) parts.push(nested);
    if (parts.length > 0) return parts.join(': ');
  }
  return null;
}

function resultItemMessage(item: { index?: number; detail?: unknown; errors?: unknown; message?: string }): string | null {
  const label = typeof item.index === 'number' ? `Event ${item.index + 1}` : 'Event';
  const message = detailToMessage(item.detail) ?? detailToMessage(item.errors)
    ?? (typeof item.message === 'string' && item.message.trim() ? item.message : null);
  return message ? `${label}: ${message}` : null;
}

/**
 * Normalize the batch, single-event and XML ingest responses into one
 * accepted/rejected count pair plus readable per-event error messages.
 */
export function normalizeEpcisIngestResult(data: EpcisIngestResponse | null | undefined): NormalizedEpcisResult {
  const record = (data ?? {}) as EpcisIngestResponse & Record<string, unknown>;
  const total = typeof record.total === 'number' && Number.isInteger(record.total) && record.total >= 0
    ? record.total
    : Array.isArray(record.results)
      ? record.results.length
      : 0;
  const accepted = typeof record.created === 'number'
    ? record.created
    : typeof record.accepted === 'number'
      ? record.accepted
      : 0;
  const rejected = typeof record.failed === 'number'
    ? record.failed
    : typeof record.rejected === 'number'
      ? record.rejected
      : Math.max(total - accepted, 0);
  const errorMessages: string[] = [];
  if (Array.isArray(record.errors)) {
    for (const entry of record.errors) {
      if (!entry || typeof entry !== 'object') continue;
      const message = resultItemMessage(entry as { index?: number; detail?: unknown });
      if (message) errorMessages.push(message);
    }
  }
  if (Array.isArray(record.results)) {
    for (const item of record.results) {
      if (!item || typeof item !== 'object') continue;
      const statusCode = (item as { status_code?: unknown }).status_code;
      const failed = typeof statusCode === 'number' && statusCode >= 400;
      if (!failed) continue;
      const message = resultItemMessage(item as { index?: number; detail?: unknown; errors?: unknown; message?: string });
      if (message && !errorMessages.includes(message)) errorMessages.push(message);
    }
  }
  return { total, accepted, rejected, errorMessages };
}

/** Render a backend or network failure the same terse way the CSV tab does. */
export function epcisErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const response = (error as Error & { response?: { data?: unknown } }).response;
    const detail = isRecord(response?.data)
      ? (response?.data as Record<string, unknown>).detail
      : undefined;
    const fromDetail = detailToMessage(detail);
    if (fromDetail) return fromDetail;
    if (error.message) return error.message;
  }
  return 'EPCIS upload failed';
}
