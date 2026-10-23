import { describe, expect, it } from 'vitest';

import { deriveQASignal } from '@/hooks/use-qa-signal';
import type { QAHealthResponse, QAHealthStatus } from '@/types/api';

function response(status: QAHealthStatus): QAHealthResponse {
  return {
    schema_version: '1.0',
    generated_at: '2026-10-01T00:00:00Z',
    source: { kind: 'ci_artifact' },
    overall: { status, ready_percent: 0, blocking_count: 0, advisory_count: 0 },
    suites: [],
    clusters: [],
    decision_checks: [],
    artifact_refs: [],
  };
}

describe('deriveQASignal', () => {
  it('is disabled for users without QA access', () => {
    const qa = deriveQASignal({ enabled: false, isLoading: false, error: null, data: undefined });
    expect(qa.status).toBe('disabled');
    expect(qa.passing).toBe(false);
  });

  it('reports loading without inventing figures', () => {
    const qa = deriveQASignal({ enabled: true, isLoading: true, error: null, data: undefined });
    expect(qa.status).toBe('loading');
    expect(qa.readyPercent).toBeNull();
  });

  it('a failed load is failed and unknown — never passing, never 0%', () => {
    const qa = deriveQASignal({ enabled: true, isLoading: false, error: new Error('timeout'), data: undefined });
    expect(qa.status).toBe('failed');
    expect(qa.label).toBe('QA signal failed');
    expect(qa.passing).toBe(false);
    expect(qa.readyPercent).toBeNull();
    expect(qa.blockingCount).toBeNull();
  });

  it('an error wins over stale cached data', () => {
    const qa = deriveQASignal({ enabled: true, isLoading: false, error: new Error('500'), data: response('passing') });
    expect(qa.status).toBe('failed');
    expect(qa.passing).toBe(false);
  });

  it('a response with no overall block is failed, not passing', () => {
    const qa = deriveQASignal({
      enabled: true,
      isLoading: false,
      error: null,
      data: { overall: undefined } as unknown as QAHealthResponse,
    });
    expect(qa.status).toBe('failed');
  });

  it('only a "passing" gate counts as passing', () => {
    expect(deriveQASignal({ enabled: true, isLoading: false, error: null, data: response('passing') }).passing).toBe(true);
    for (const status of ['failing', 'degraded', 'unavailable', 'invalid_artifact'] as const) {
      expect(deriveQASignal({ enabled: true, isLoading: false, error: null, data: response(status) }).passing).toBe(false);
    }
  });

  it('an unrecognised status is treated as failing', () => {
    const qa = deriveQASignal({
      enabled: true,
      isLoading: false,
      error: null,
      data: response('mystery' as QAHealthStatus),
    });
    expect(qa.status).toBe('failing');
    expect(qa.passing).toBe(false);
  });

  it('maps each gate status to its label', () => {
    const labels: Record<QAHealthStatus, string> = {
      passing: 'Release gate passing',
      degraded: 'Advisory issues',
      unavailable: 'QA signal unavailable',
      invalid_artifact: 'QA artifact invalid',
      failing: 'Release gate failing',
    };
    for (const [status, label] of Object.entries(labels) as [QAHealthStatus, string][]) {
      expect(deriveQASignal({ enabled: true, isLoading: false, error: null, data: response(status) }).label).toBe(label);
    }
  });
});
