import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SandboxUpload } from '@/components/marketing/SandboxUpload';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

vi.mock('posthog-js/react', () => ({
  usePostHog: () => ({ capture: vi.fn() }),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
  fetchWithCsrf: vi.fn(),
}));

vi.mock('@/components/marketing/sandbox-grid/SandboxPdfReport', () => ({
  generateComplianceReport: vi.fn(),
}));

describe('Sandbox test-run handoff producer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    (fetchWithCsrf as any).mockResolvedValue(
      new Response(
        JSON.stringify({
          total_events: 1,
          compliant_events: 1,
          non_compliant_events: 0,
          total_kde_errors: 0,
          total_rule_failures: 0,
          submission_blocked: false,
          blocking_reasons: [],
          normalizations: [
            { field: 'traceability_lot_code', original: 'lot', normalized: 'traceability_lot_code', action_type: 'header_alias' },
          ],
          events: [
            {
              event_index: 0,
              cte_type: 'shipping',
              traceability_lot_code: 'LOT-1',
              product_description: 'Romaine',
              kde_errors: [],
              rules_evaluated: 1,
              rules_passed: 1,
              rules_failed: 0,
              rules_warned: 0,
              compliant: true,
              blocking_defects: [],
              all_results: [],
            },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
  });

  it('stores the plan handoff object in sessionStorage and navigates to ingest mapping', async () => {
    const user = userEvent.setup();
    render(<SandboxUpload />);

    await user.type(
      screen.getByRole('textbox'),
      'cte_type,lot,product_description\nshipping,LOT-1,Romaine',
    );
    await user.click(screen.getByRole('button', { name: /Evaluate Against FSMA 204 Rules/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/SANDBOX CHECKS CLEAR/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: /Save as test run/i }));

    const handoff = JSON.parse(window.sessionStorage.getItem('regengine:sandbox-handoff') || '{}');
    expect(handoff).toMatchObject({
      version: 1,
      source: 'free-sandbox',
      summary: {
        totalEvents: 1,
        passedChecks: 1,
        needsWork: 0,
        blockers: 0,
      },
      csv: expect.stringContaining('LOT-1'),
      detectedColumns: ['cte_type', 'lot', 'product_description'],
    });
    expect(handoff.createdAt).toEqual(expect.any(String));
  });
});
