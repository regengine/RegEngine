import { describe, expect, it } from 'vitest';
import {
  epcisErrorMessage,
  normalizeEpcisIngestResult,
  parseEpcisJson,
} from '@/lib/epcis-upload';

const EVENT_A = { type: 'ObjectEvent', action: 'OBSERVE' };
const EVENT_B = { type: 'ObjectEvent', action: 'ADD' };

describe('parseEpcisJson', () => {
  it('routes an EPCISDocument with epcisBody.eventList to batch', () => {
    const parsed = parseEpcisJson(
      JSON.stringify({ type: 'EPCISDocument', epcisBody: { eventList: [EVENT_A, EVENT_B] } }),
    );
    expect(parsed).toEqual({ kind: 'batch', events: [EVENT_A, EVENT_B] });
  });

  it('routes a bare JSON array of events to batch', () => {
    expect(parseEpcisJson(JSON.stringify([EVENT_A]))).toEqual({ kind: 'batch', events: [EVENT_A] });
  });

  it('routes a single event object to the single-event shape', () => {
    expect(parseEpcisJson(JSON.stringify(EVENT_A))).toEqual({ kind: 'single', event: EVENT_A });
  });

  it('throws a readable error for non-JSON text without a request shape', () => {
    expect(() => parseEpcisJson('not json{{{')).toThrow(/could not parse the file as json/i);
  });

  it('throws when the document carries no events', () => {
    expect(() => parseEpcisJson(JSON.stringify({ type: 'EPCISDocument', epcisBody: { eventList: [] } }))).toThrow(
      /no epcis events found/i,
    );
    expect(() => parseEpcisJson(JSON.stringify([]))).toThrow(/no epcis events found/i);
    expect(() => parseEpcisJson(JSON.stringify(42))).toThrow(/no epcis events found/i);
  });
});

describe('normalizeEpcisIngestResult', () => {
  it('reads created/failed counts and per-event error messages', () => {
    expect(
      normalizeEpcisIngestResult({
        total: 2,
        created: 1,
        failed: 1,
        results: [{ index: 1, status_code: 400, detail: 'Missing bizLocation' }],
        errors: [{ index: 1, detail: 'Missing bizLocation' }],
        mode: 'partial',
      }),
    ).toEqual({
      total: 2,
      accepted: 1,
      rejected: 1,
      errorMessages: ['Event 2: Missing bizLocation'],
    });
  });

  it('accepts the accepted/rejected naming too', () => {
    expect(
      normalizeEpcisIngestResult({ total: 1, accepted: 1, rejected: 0 }),
    ).toMatchObject({ total: 1, accepted: 1, rejected: 0, errorMessages: [] });
  });

  it('falls back to zeros for empty payloads', () => {
    expect(normalizeEpcisIngestResult(null)).toEqual({
      total: 0,
      accepted: 0,
      rejected: 0,
      errorMessages: [],
    });
  });
});

describe('epcisErrorMessage', () => {
  it('prefers the backend detail message', () => {
    const error = Object.assign(new Error('Bad Request'), {
      response: { status: 400, data: { detail: 'Tenant context required' } },
    });
    expect(epcisErrorMessage(error)).toBe('Tenant context required');
  });

  it('falls back to the error message and then to a default', () => {
    expect(epcisErrorMessage(new Error('Network Error'))).toBe('Network Error');
    expect(epcisErrorMessage(null)).toBe('EPCIS upload (Preview) failed');
  });
});
