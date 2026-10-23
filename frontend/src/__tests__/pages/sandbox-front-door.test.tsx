// #2757 — regression cover for the sandbox front door.
//
// Two failures this locks down:
//   1. /sandbox 404ing while three compare pages promise a CSV sandbox.
//   2. The #2730 shape — CTA copy promising a sandbox while the button goes
//      somewhere else, because copy and href were edited independently.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/posthog-provider', () => ({
    usePostHog: () => ({ capture: vi.fn() }),
}));

vi.mock('@/components/marketing/sandbox-grid/SandboxPdfReport', () => ({
    generateComplianceReport: vi.fn(),
}));

import { SandboxClient, validateSandboxFile, describeSandboxFailure } from '@/app/sandbox/SandboxClient';
import { sandboxCta } from '@/lib/sandbox-cta';

const RESULT = {
    total_events: 2,
    compliant_events: 1,
    non_compliant_events: 1,
    total_kde_errors: 1,
    total_rule_failures: 1,
    submission_blocked: false,
    blocking_reasons: [],
    normalizations: [],
    events: [
        {
            event_index: 0,
            cte_type: 'shipping',
            traceability_lot_code: 'SV-20260115-001',
            product_description: 'Romaine Lettuce',
            kde_errors: [],
            rules_evaluated: 4,
            rules_passed: 4,
            rules_failed: 0,
            rules_warned: 0,
            compliant: true,
            blocking_defects: [],
            all_results: [],
        },
        {
            event_index: 1,
            cte_type: 'transformation',
            traceability_lot_code: 'FC-20260116-A',
            product_description: 'Chopped Romaine',
            kde_errors: ['Missing reference_document'],
            rules_evaluated: 4,
            rules_passed: 3,
            rules_failed: 1,
            rules_warned: 0,
            compliant: false,
            blocking_defects: [],
            all_results: [
                {
                    rule_title: 'Reference document required',
                    severity: 'error',
                    result: 'fail',
                    why_failed: 'No reference document on the transformation event',
                    citation: '§1.1350',
                    remediation: 'Add the work order number',
                    category: 'kde_presence',
                },
            ],
        },
    ],
};

function csvFile(name = 'events.csv', size = 1_000) {
    const file = new File(['cte_type\nshipping\n'], name, { type: 'text/csv' });
    Object.defineProperty(file, 'size', { value: size });
    file.text = () => Promise.resolve('cte_type\nshipping\n');
    return file;
}

describe('sandbox CTA resolver (#2757)', () => {
    it('never promises a CSV sandbox while pointing somewhere that is not the sandbox', () => {
        const cta = sandboxCta();
        const promisesSandbox = /sandbox/i.test(cta.blurb);
        if (promisesSandbox) {
            expect(cta.href).toBe('/sandbox');
        } else {
            expect(cta.href).not.toBe('/sandbox');
        }
    });

    it('marks the destination as a real route in both states', () => {
        expect(['/sandbox', '/walkthrough']).toContain(sandboxCta().href);
    });

    it('fallback copy matches the walkthrough destination', () => {
        const cta = sandboxCta();
        if (!cta.enabled) {
            expect(cta.href).toBe('/walkthrough');
            expect(cta.blurb).not.toMatch(/sandbox|csv/i);
        }
    });

    it('points at /sandbox and promises CSV evaluation once the surface is enabled', () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
        try {
            const cta = sandboxCta();
            expect(cta.enabled).toBe(true);
            expect(cta.href).toBe('/sandbox');
            expect(cta.blurb).toMatch(/CSV/i);
        } finally {
            vi.unstubAllEnvs();
        }
    });

    it('falls back to the walkthrough when the surface is off', () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
        vi.stubEnv('NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS', '');
        try {
            const cta = sandboxCta();
            expect(cta.enabled).toBe(false);
            expect(cta.href).toBe('/walkthrough');
            expect(cta.blurb).not.toMatch(/drop your csv/i);
        } finally {
            vi.unstubAllEnvs();
        }
    });

    it('honors the per-tool override without the whole experimental surface', () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
        vi.stubEnv('NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS', 'sandbox');
        try {
            expect(sandboxCta().href).toBe('/sandbox');
        } finally {
            vi.unstubAllEnvs();
        }
    });
});

describe('compare-page CTAs (#2757)', () => {
    // The #2730 regression was copy and href drifting apart on these three
    // pages. Rendering them proves both come from the same resolver.
    it.each([
        ['tracegains', () => import('@/app/compare/tracegains/page')],
        ['repositrak', () => import('@/app/compare/repositrak/page')],
        ['foodlogiq', () => import('@/app/compare/foodlogiq/page')],
    ])('%s CTA copy and destination agree', async (_name, load) => {
        const { default: Page } = await load();
        const { container } = render(<Page />);

        const cta = sandboxCta();
        expect(screen.getByText(cta.blurb)).toBeInTheDocument();

        const link = container.querySelector(`a[href="${cta.href}"]`);
        expect(link).not.toBeNull();
        expect(link).toHaveTextContent(cta.label);

        // No page may claim a CSV sandbox while the sandbox surface is off.
        if (!cta.enabled) {
            expect(container.textContent).not.toMatch(/drop your csv in the sandbox/i);
        }
    });
});

describe('validateSandboxFile (#2757)', () => {
    it('tells spreadsheet users to export CSV instead of failing silently', () => {
        const problem = validateSandboxFile({ name: 'events.xlsx', size: 1_000 });
        expect(problem).toMatch(/CSV/);
        expect(problem).toMatch(/Save As|Export/i);
    });

    it('rejects files above the backend 2 MB cap before the round trip', () => {
        expect(validateSandboxFile({ name: 'big.csv', size: 3_000_000 })).toMatch(/2 MB/);
    });

    it('accepts csv, tsv and txt', () => {
        for (const name of ['a.csv', 'a.tsv', 'a.txt']) {
            expect(validateSandboxFile({ name, size: 10 })).toBeNull();
        }
    });

    it('rejects unrelated file types', () => {
        expect(validateSandboxFile({ name: 'photo.png', size: 10 })).toMatch(/Unsupported/);
    });
});

describe('describeSandboxFailure (#2757)', () => {
    it('says the service is not enabled on a 404 rather than blaming the file', () => {
        const msg = describeSandboxFailure(404);
        expect(msg).toMatch(/not enabled/i);
        expect(msg).toMatch(/not evaluated|nothing was uploaded/i);
    });

    it('surfaces the rate limit explicitly on 429', () => {
        expect(describeSandboxFailure(429)).toMatch(/Rate limit/i);
    });

    it('prefers the backend detail when one is supplied', () => {
        expect(describeSandboxFailure(400, 'CSV parsing error: no cte_type column')).toMatch(
            /no cte_type column/,
        );
    });
});

describe('SandboxClient (#2757)', () => {
    beforeEach(() => {
        vi.stubGlobal('fetch', vi.fn());
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('renders the diagnosis for an uploaded CSV', async () => {
        (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => RESULT,
        });

        render(<SandboxClient />);
        await userEvent.upload(screen.getByLabelText(/choose a csv/i), csvFile());

        await waitFor(() => {
            expect(screen.getByText('FSMA 204 Sandbox Diagnosis')).toBeInTheDocument();
        });
        expect(screen.getByText('SV-20260115-001')).toBeInTheDocument();
        expect(screen.getByText('FC-20260116-A')).toBeInTheDocument();
    });

    it('posts to the unauthenticated BFF proxy path, not the backend directly', async () => {
        (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => RESULT,
        });

        render(<SandboxClient />);
        await userEvent.upload(screen.getByLabelText(/choose a csv/i), csvFile());

        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
        expect(url).toBe('/api/ingestion/api/v1/sandbox/evaluate');
        expect(init.method).toBe('POST');
        // No auth header — the proxy allowlists this path unauthenticated.
        expect(Object.keys(init.headers)).toEqual(['Content-Type']);
    });

    it('states the service is unavailable when the router is not mounted', async () => {
        (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
            ok: false,
            status: 404,
            json: async () => ({}),
        });

        render(<SandboxClient />);
        await userEvent.upload(screen.getByLabelText(/choose a csv/i), csvFile());

        await waitFor(() => {
            expect(screen.getByRole('alert')).toHaveTextContent(/not enabled on this deployment/i);
        });
        expect(screen.queryByText('FSMA 204 Sandbox Diagnosis')).not.toBeInTheDocument();
    });

    it('does not call the backend for a spreadsheet upload', async () => {
        render(<SandboxClient />);
        await userEvent.upload(screen.getByLabelText(/choose a csv/i), csvFile('events.xlsx'));

        await waitFor(() => {
            expect(screen.getByRole('alert')).toHaveTextContent(/CSV/);
        });
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });
});
