import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/auth-context', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/lib/auth-context')>();
    return {
        ...actual,
        useAuth: vi.fn().mockReturnValue({
            isAuthenticated: false,
            isHydrated: true,
            tenantId: null,
        }),
    };
});

vi.mock('@/lib/tenant-context', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/lib/tenant-context')>();
    return {
        ...actual,
        useTenant: vi.fn().mockReturnValue({ tenantId: null }),
    };
});

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        (globalThis as unknown as { fetch: typeof fetch }).fetch(input, init),
    ),
}));

import DashboardInflowLabPage from '@/app/dashboard/inflow-lab/page';
import { AuthProvider } from '@/lib/auth-context';
import { TenantProvider } from '@/lib/tenant-context';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

const completeLot = '00614141000012-20260426-000001';
const partialLot = '00614141000012-20260426-000003';

function inflowRecord(sequence_no: number, lotCode: string, cteType: string) {
    return {
        sequence_no,
        destination_mode: 'mock',
        delivery_status: 'posted',
        delivery_attempts: 1,
        event: {
            cte_type: cteType,
            traceability_lot_code: lotCode,
            product_description: lotCode === partialLot ? 'Green Leaf Lettuce' : 'Spring Mix',
            location_name: `${cteType} station`,
            timestamp: '2026-04-26T18:12:00.000Z',
        },
    };
}

const completeLotRecords = [
    inflowRecord(5, completeLot, 'harvesting'),
    inflowRecord(4, completeLot, 'cooling'),
    inflowRecord(3, completeLot, 'initial_packing'),
    inflowRecord(2, completeLot, 'shipping'),
    inflowRecord(1, completeLot, 'receiving'),
];

const serviceRecords = [
    ...completeLotRecords,
    inflowRecord(7, partialLot, 'harvesting'),
    inflowRecord(6, partialLot, 'cooling'),
];

const sandboxEvaluation = {
    total_events: 1,
    compliant_events: 1,
    non_compliant_events: 0,
    total_kde_errors: 0,
    total_rule_failures: 0,
    submission_blocked: false,
    blocking_reasons: [],
    events: [
        {
            event_index: 0,
            cte_type: 'shipping',
            traceability_lot_code: 'TLC-FEED-001',
            product_description: 'Romaine Lettuce',
            kde_errors: [],
            rules_failed: 0,
            rules_warned: 0,
            compliant: true,
            all_results: [],
        },
    ],
};

const savedWorkbenchRun = {
    run_id: 'run-123456789abc',
    tenant_id: 'tenant-123',
    source: 'inflow-lab-data-feeder',
    csv: 'cte_type,traceability_lot_code\nshipping,TLC-FEED-001',
    result: sandboxEvaluation,
    readiness: {
        score: 94,
        label: 'export ready after authenticated commit',
        components: [],
    },
    fix_queue: [],
    commit_gate: {
        mode: 'staging',
        allowed: true,
        export_eligible: false,
        reasons: ['Ready to request authenticated production commit.'],
        next_state: 'production_evidence',
    },
    saved_at: '2026-05-06T18:00:00.000Z',
    input_hash: 'abc123',
    result_hash: 'def456',
    commit_decision_id: 'run-123456789abc:staging',
};

const savedWorkbenchSummary = {
    tenant_id: 'tenant-123',
    score: 94,
    label: 'export ready after authenticated commit',
    run_id: savedWorkbenchRun.run_id,
    saved_at: savedWorkbenchRun.saved_at,
    unresolved_fix_count: 0,
    export_eligible: false,
    source: savedWorkbenchRun.source,
};

function jsonResponse(payload: unknown, init?: ResponseInit) {
    return Promise.resolve(
        new Response(JSON.stringify(payload), {
            status: 200,
            headers: { 'content-type': 'application/json' },
            ...init,
        }),
    );
}

function renderDashboardInflowLabPage() {
    return render(
        <AuthProvider>
            <TenantProvider>
                <DashboardInflowLabPage />
            </TenantProvider>
        </AuthProvider>,
    );
}

describe('Dashboard Inflow Lab', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        window.HTMLElement.prototype.scrollIntoView = vi.fn();
        vi.mocked(useAuth).mockReturnValue({
            isAuthenticated: false,
            isHydrated: true,
            tenantId: null,
        } as ReturnType<typeof useAuth>);
        vi.mocked(useTenant).mockReturnValue({
            tenantId: null,
            setTenantId: vi.fn(),
            isSystemTenant: false,
        } as unknown as ReturnType<typeof useTenant>);
        const localStore: Record<string, string> = {};
        const sessionStore: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => localStore[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                localStore[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete localStore[key];
            }),
            clear: vi.fn(() => {
                Object.keys(localStore).forEach((key) => delete localStore[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
        vi.stubGlobal('sessionStorage', {
            getItem: vi.fn((key: string) => sessionStore[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                sessionStore[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete sessionStore[key];
            }),
            clear: vi.fn(() => {
                Object.keys(sessionStore).forEach((key) => delete sessionStore[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
        mockFetch.mockImplementation((input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('/api/ingestion/api/v1/inflow-workbench/readiness/summary')) {
                return jsonResponse({
                    tenant_id: 'tenant-123',
                    unresolved_fix_count: 0,
                    export_eligible: false,
                    source: 'none',
                });
            }
            if (url.includes(`/api/ingestion/api/v1/inflow-workbench/runs/${savedWorkbenchRun.run_id}`)) {
                return jsonResponse(savedWorkbenchRun);
            }
            if (url.endsWith('/api/ingestion/api/v1/sandbox/evaluate')) {
                return jsonResponse(sandboxEvaluation);
            }
            if (url.endsWith('/api/ingestion/api/v1/inflow-workbench/readiness/preview')) {
                return jsonResponse({
                    score: 94,
                    label: 'export ready after authenticated commit',
                    components: [],
                });
            }
            if (url.endsWith('/api/ingestion/api/v1/inflow-workbench/runs')) {
                return jsonResponse(savedWorkbenchRun);
            }
            if (url.endsWith('/api/healthz')) {
                return jsonResponse({ ok: true, build: { version: 'test-build' } });
            }
            if (url.endsWith('/api/simulate/status')) {
                return jsonResponse({
                    running: false,
                    stats: {
                        total_records: serviceRecords.length,
                        unique_lots: 2,
                        delivery: { posted: serviceRecords.length, failed: 0, generated: 0, attempts: serviceRecords.length },
                    },
                });
            }
            if (url.includes('/api/events')) {
                return jsonResponse({ events: serviceRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(completeLot)}`)) {
                return jsonResponse({ records: completeLotRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(partialLot)}`)) {
                return jsonResponse({
                    records: serviceRecords.filter(
                        (record) => record.event.traceability_lot_code === partialLot,
                    ),
                });
            }
            return jsonResponse({});
        });
        vi.stubGlobal('fetch', mockFetch);
    });

    it('renders the Inflow Lab header with one Sandbox chip and a single boundary banner', async () => {
        renderDashboardInflowLabPage();

        expect(screen.getByRole('heading', { name: 'Inflow Lab' })).toBeInTheDocument();

        const sandboxChips = screen.getAllByText('Sandbox');
        expect(sandboxChips).toHaveLength(1);

        const banner = screen.getByRole('status');
        expect(banner).toHaveTextContent('Sandbox preview only.');
        expect(banner).toHaveTextContent(
            /Production FDA-oriented exports stay sealed and review-ready — nothing here writes to them\./,
        );

        expect(screen.queryByText('Mock environment')).not.toBeInTheDocument();
        expect(screen.queryByText('Boundary active')).not.toBeInTheDocument();
        expect(screen.queryByText('Sandbox diagnosis')).not.toBeInTheDocument();
    });

    it('shows the business activity as a traced chain without exposing internal scoring details', async () => {
        renderDashboardInflowLabPage();

        const chain = await screen.findByTestId('inflow-evidence-chain');
        // The handoff is shown as evidence rather than described in prose: every
        // CTE from harvest to receive, ending in the consequence.
        // Matched loosely because each label carries an sr-only state suffix,
        // and the mock's location names ("cooling station") repeat the CTE word.
        for (const cte of ['Harvesting', 'Cooling', 'Initial packing', 'Shipping', 'DC receiving']) {
            expect(within(chain).getAllByText(cte, { exact: false }).length).toBeGreaterThan(0);
        }
        expect(within(chain).getByText('Export gate')).toBeInTheDocument();

        // The scoring recipe stays internal — the chain reports what is missing
        // and what to do about it, never how readiness is computed.
        expect(
            within(chain).queryByText(/weighting|coefficient|scoring model|formula/i),
        ).not.toBeInTheDocument();
    });

    it('reports one lead defect and one fix path', async () => {
        renderDashboardInflowLabPage();

        const chain = await screen.findByTestId('inflow-evidence-chain');
        expect(await within(chain).findByText(/records? never arrived\./)).toBeInTheDocument();
        expect(within(chain).getByText('Missing')).toBeInTheDocument();
        expect(within(chain).getByText('Pattern')).toBeInTheDocument();
        expect(within(chain).getByText('Lots affected')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Focus this defect' })).toBeInTheDocument();
    });

    it('uses the proof-lead action to select the blocked lot and open its story in the rail', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await user.click(await screen.findByRole('button', { name: 'Focus this defect' }));

        expect(await screen.findByText(/This proof lead is blocked on/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Show matching queue group' })).toBeInTheDocument();
        expect(document.querySelector('[data-exception-group="handoff"]')).toHaveClass('bg-rose-100/70');
        expect(document.querySelector('[data-selected-lot-panel]')).toHaveAttribute('data-proof-lead-highlight', 'true');
    });

    it('renders the 5-step funnel with a single Run sandbox test CTA in the active step', async () => {
        renderDashboardInflowLabPage();

        const funnel = await screen.findByTestId('inflow-funnel');
        expect(within(funnel).getByText('Loaded')).toBeInTheDocument();
        expect(within(funnel).getByText('Validated')).toBeInTheDocument();
        expect(within(funnel).getByText('Passing')).toBeInTheDocument();
        expect(within(funnel).getByText('Preview-ready')).toBeInTheDocument();
        expect(within(funnel).getByText('Production import')).toBeInTheDocument();

        const sandboxButtons = screen.getAllByRole('button', { name: /Run sandbox test/i });
        expect(sandboxButtons).toHaveLength(1);

        const activeStep = funnel.querySelector('[data-funnel-step="passing"]');
        expect(activeStep).not.toBeNull();
        expect(activeStep!).toContainElement(sandboxButtons[0]);
    });

    it('renders the readiness panel with five stacked-bar factors', async () => {
        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(screen.getByText('KDE completeness')).toBeInTheDocument();
        });
        expect(screen.getByText('CTE lifecycle')).toBeInTheDocument();
        expect(screen.getByText('Delivery quality')).toBeInTheDocument();
        expect(screen.getByText('Sandbox pass rate')).toBeInTheDocument();
        expect(screen.getByText('Connection health')).toBeInTheDocument();
        expect(screen.getByText('not run')).toBeInTheDocument();
    });

    it('renders exceptions as failure-pattern groups, hiding empty groups on the all filter', async () => {
        renderDashboardInflowLabPage();

        // The fixture has one handoff-style partial lot; the handoff group must
        // render. Anchor on the rendered group node directly instead of a
        // parent <section>, because the card structure around the Exceptions
        // heading is layout-driven and has changed over time.
        const handoffNode = await waitFor(() => {
            const node = document.querySelector('[data-exception-group="handoff"]');
            if (!node) throw new Error('handoff group not rendered');
            return node as HTMLElement;
        });
        expect(within(handoffNode as HTMLElement).getByText('Missing handoff evidence')).toBeInTheDocument();
        expect(screen.queryByText('Missing source evidence')).not.toBeInTheDocument();
        expect(screen.queryByText('Mixed / multi-cause')).not.toBeInTheDocument();
    });

    it('shows an empty-filter state when the active filter selects a group with 0 lots', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(screen.getByText('Exceptions')).toBeInTheDocument();
        });
        // Click the 'mixed' filter chip; the fixture has no mixed lots so the
        // section must surface a clear empty-filter state with a Clear filter
        // affordance.
        await user.click(screen.getByRole('button', { name: 'mixed' }));
        const empty = await waitFor(() => {
            const node = document.querySelector('[data-empty-filter-state]');
            if (!node) throw new Error('empty-filter state not rendered');
            return node as HTMLElement;
        });
        expect(empty).toHaveTextContent(/No lots match the/);
        expect(within(empty).getByRole('button', { name: 'Clear filter' })).toBeInTheDocument();
    });

    it('handoff group has a Fix all bulk CTA, mixed group never does', async () => {
        renderDashboardInflowLabPage();
        const handoff = await waitFor(() => {
            const node = document.querySelector('[data-exception-group="handoff"]');
            if (!node) throw new Error('handoff group not rendered');
            return node as HTMLElement;
        });
        // "Fix all" is a navigation into the fix queue, so it renders as a
        // link (role=link) rather than an inert button.
        const fixAll = within(handoff).getByRole('link', { name: /^Fix all /i });
        expect(fixAll).toHaveAttribute('href', '/exceptions');

        // The mixed group, even when populated, must never carry a Fix all
        // bulk CTA per the audit (per-lot triage only). Filter to mixed and
        // confirm the empty-filter card shows up rather than a Fix all.
        // (When the fixture produces mixed lots in a future test, the
        // assertion is the same: data-exception-group="mixed" never contains
        // a "Fix all" button.)
        const mixed = document.querySelector('[data-exception-group="mixed"]');
        if (mixed) {
            expect(within(mixed as HTMLElement).queryByText(/^Fix all /)).not.toBeInTheDocument();
        }
    });

    it('keeps the selected lot detail in a sticky right rail with Lifecycle and KDE tiles', async () => {
        renderDashboardInflowLabPage();

        // ``Selected lot`` is the section heading that renders even when no
        // lot is loaded yet. Wait for ``Lifecycle`` instead — it only appears
        // once selectedLotData is non-null (i.e. a lot has been picked from
        // the fetched events). Use findByText for built-in timeout.
        expect(await screen.findByText('Lifecycle')).toBeInTheDocument();
        expect(screen.getByText('Selected lot')).toBeInTheDocument();
        expect(screen.getByText('Lot KDE summary')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Fix this lot' })).toBeInTheDocument();
        expect(screen.getByText(/Proof lead lot .* is dragging down/i)).toBeInTheDocument();
    });

    it('triggers a sandbox evaluation when Run sandbox test is pressed in the funnel', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));
        expect(screen.getByText(/Paste CSV text or upload a CSV file before evaluating\./i)).toBeInTheDocument();
    });

    it('loads a realistic sample flow into the CSV drawer', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: 'Load realistic sample' }));

        const textarea = await screen.findByRole('textbox', { name: 'Inbound CSV data' });
        const textareaValue = (textarea as HTMLTextAreaElement).value;
        expect(textareaValue).toContain('Riverbend Organics');
        expect(textareaValue).toContain('GreenLeaf Shipping Dock');
        expect(textareaValue).toContain('North Bay DC');
    });

    it('runs the guided proof with sample data without saving until requested', async () => {
        const user = userEvent.setup();
        vi.mocked(useAuth).mockReturnValue({
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-123',
            user: {
                id: 'writer-1',
                email: 'writer@example.com',
                is_sysadmin: false,
                status: 'active',
                role_name: 'member',
                permissions: ['inflow.write'],
            },
        } as ReturnType<typeof useAuth>);
        vi.mocked(useTenant).mockReturnValue({ tenantId: 'tenant-123' } as ReturnType<typeof useTenant>);

        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run trace/ }));

        const textarea = await screen.findByRole('textbox', { name: 'Inbound CSV data' });
        const textareaValue = (textarea as HTMLTextAreaElement).value;
        expect(textareaValue).toContain('Riverbend Organics');
        expect(textareaValue).toContain('GreenLeaf Shipping Dock');
        expect(textareaValue).toContain('North Bay DC');

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/sandbox/evaluate',
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('Riverbend Organics'),
                }),
            );
        });
        expect(await screen.findByText(/Sandbox evaluator processed 1 event/i)).toBeInTheDocument();
        expect(
            mockFetch.mock.calls.filter(
                ([url]) => String(url) === '/api/ingestion/api/v1/inflow-workbench/runs',
            ),
        ).toHaveLength(0);

        await user.click(screen.getByRole('button', { name: 'Save test run' }));

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/inflow-workbench/runs',
                expect.objectContaining({ method: 'POST' }),
            );
        });
    });

    it('keeps public guided proof runs local without calling authenticated readiness preview', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run trace/ }));

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/sandbox/evaluate',
                expect.objectContaining({ method: 'POST' }),
            );
        });
        expect(
            mockFetch.mock.calls.some(
                ([url]) => String(url) === '/api/ingestion/api/v1/inflow-workbench/readiness/preview',
            ),
        ).toBe(false);
        expect(
            mockFetch.mock.calls.some(
                ([url]) => String(url) === '/api/ingestion/api/v1/inflow-workbench/runs',
            ),
        ).toBe(false);
    });

    it('loads the latest saved workbench run when the dashboard opens with an authenticated tenant session', async () => {
        vi.mocked(useAuth).mockReturnValue({
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-123',
            user: {
                id: 'reader-1',
                email: 'reader@example.com',
                is_sysadmin: false,
                status: 'active',
                role_name: 'member',
                permissions: ['inflow.read'],
            },
        } as ReturnType<typeof useAuth>);
        vi.mocked(useTenant).mockReturnValue({ tenantId: 'tenant-123' } as ReturnType<typeof useTenant>);
        mockFetch.mockImplementation((input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('/api/ingestion/api/v1/inflow-workbench/readiness/summary')) {
                return jsonResponse(savedWorkbenchSummary);
            }
            if (url.includes(`/api/ingestion/api/v1/inflow-workbench/runs/${savedWorkbenchRun.run_id}`)) {
                return jsonResponse(savedWorkbenchRun);
            }
            if (url.endsWith('/api/healthz')) {
                return jsonResponse({ ok: true, build: { version: 'test-build' } });
            }
            if (url.endsWith('/api/simulate/status')) {
                return jsonResponse({
                    running: false,
                    stats: {
                        total_records: serviceRecords.length,
                        unique_lots: 2,
                        delivery: { posted: serviceRecords.length, failed: 0, generated: 0, attempts: serviceRecords.length },
                    },
                });
            }
            if (url.includes('/api/events')) {
                return jsonResponse({ events: serviceRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(completeLot)}`)) {
                return jsonResponse({ records: completeLotRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(partialLot)}`)) {
                return jsonResponse({
                    records: serviceRecords.filter(
                        (record) => record.event.traceability_lot_code === partialLot,
                    ),
                });
            }
            return jsonResponse({});
        });

        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/inflow-workbench/readiness/summary?tenant_id=tenant-123',
                expect.objectContaining({ method: 'GET' }),
            );
        });
        expect(
            await screen.findByText(/Latest saved workbench run/i),
        ).toBeInTheDocument();
        expect(screen.getByText('run-123456789abc')).toBeInTheDocument();
        expect(screen.getByText(/0 open fixes remain in workbench\./i)).toBeInTheDocument();
        expect(screen.queryByText(/Last test run · never/i)).not.toBeInTheDocument();
    });

    it('keeps sandbox evaluation non-persistent until Save test run is pressed', async () => {
        const user = userEvent.setup();
        vi.mocked(useAuth).mockReturnValue({
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-123',
            user: {
                id: 'writer-1',
                email: 'writer@example.com',
                is_sysadmin: false,
                status: 'active',
                role_name: 'member',
                permissions: ['inflow.write'],
            },
        } as ReturnType<typeof useAuth>);
        vi.mocked(useTenant).mockReturnValue({ tenantId: 'tenant-123' } as ReturnType<typeof useTenant>);

        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));
        const textarea = await screen.findByRole('textbox', { name: 'Inbound CSV data' });
        await user.type(textarea, 'cte_type,traceability_lot_code\nshipping,TLC-FEED-001');
        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));

        await waitFor(() => {
            expect(screen.getByText(/Sandbox evaluator processed 1 event/i)).toBeInTheDocument();
        });
        expect(
            mockFetch.mock.calls.filter(
                ([url]) => String(url) === '/api/ingestion/api/v1/inflow-workbench/runs',
            ),
        ).toHaveLength(0);
        expect(screen.getByRole('button', { name: 'Save test run' })).toBeInTheDocument();
        expect(
            screen.getByText(/Sandbox evaluation is stateless until you explicitly save a test run\./i),
        ).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Save test run' }));

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/inflow-workbench/runs',
                expect.objectContaining({ method: 'POST' }),
            );
        });
        expect(await screen.findByText(/Saved to Inflow Workbench as/i)).toBeInTheDocument();
        expect(screen.getByText('run-123456789abc')).toBeInTheDocument();
        expect(screen.getByText(/0 open fixes remain for this saved test run\./i)).toBeInTheDocument();
        expect(screen.queryByText(/Last test run · never/i)).not.toBeInTheDocument();
    });

    it('disables saving when the session lacks inflow.write even if the role name looks privileged', async () => {
        const user = userEvent.setup();
        vi.mocked(useAuth).mockReturnValue({
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-123',
            user: {
                id: 'owner-readonly-1',
                email: 'readonly-owner@example.com',
                is_sysadmin: false,
                status: 'active',
                role_name: 'owner',
                permissions: ['inflow.read'],
            },
        } as ReturnType<typeof useAuth>);
        vi.mocked(useTenant).mockReturnValue({ tenantId: 'tenant-123' } as ReturnType<typeof useTenant>);

        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));
        const textarea = await screen.findByRole('textbox', { name: 'Inbound CSV data' });
        await user.type(textarea, 'cte_type,traceability_lot_code\nshipping,TLC-FEED-001');
        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));

        const saveButton = await screen.findByRole('button', { name: 'Save unavailable' });
        expect(saveButton).toBeDisabled();

        expect(
            await screen.findByText(
                /You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run\./i,
            ),
        ).toBeInTheDocument();
        expect(
            mockFetch.mock.calls.filter(
                ([url]) => String(url) === '/api/ingestion/api/v1/inflow-workbench/runs',
            ),
        ).toHaveLength(0);
        expect(screen.queryByText(/Saved to Inflow Workbench as/i)).not.toBeInTheDocument();
    });

    it('opens fix queue navigation from the section-level button', async () => {
        renderDashboardInflowLabPage();
        const link = await screen.findByRole('link', { name: 'Open fix queue' });
        // Canonical exceptions route is top-level /exceptions (mirrors the
        // dashboard sidebar entry); /dashboard/exceptions does not exist.
        expect(link).toHaveAttribute('href', '/exceptions');
    });

    it('shows a clickable tutorial banner that opens the step-by-step walkthrough', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        const banner = await screen.findByTestId('inflow-tutorial-banner');
        expect(banner).toHaveTextContent('New to Inflow Lab? Learn to operate it step by step');

        await user.click(
            within(banner).getByRole('button', { name: /Learn to operate it step by step/i }),
        );

        expect(await screen.findByText('Step 1 of 7')).toBeInTheDocument();
        expect(screen.getByText('What Inflow Lab is')).toBeInTheDocument();
    });

    it('walks forward through the tutorial steps', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        const banner = await screen.findByTestId('inflow-tutorial-banner');
        await user.click(
            within(banner).getByRole('button', { name: /Learn to operate it step by step/i }),
        );
        await screen.findByText('Step 1 of 7');

        await user.click(screen.getByRole('button', { name: /Next/i }));
        expect(await screen.findByText('Step 2 of 7')).toBeInTheDocument();
        expect(screen.getByText('Bring supplier data in')).toBeInTheDocument();
    });

    it('dismisses the tutorial banner without disabling the How to use entry point', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        const banner = await screen.findByTestId('inflow-tutorial-banner');
        await user.click(within(banner).getByRole('button', { name: 'Dismiss tutorial banner' }));

        await waitFor(() => {
            expect(screen.queryByTestId('inflow-tutorial-banner')).not.toBeInTheDocument();
        });

        // The walkthrough must stay reachable from the header after dismissal.
        await user.click(screen.getByRole('button', { name: /How to use/i }));
        expect(await screen.findByText('Step 1 of 7')).toBeInTheDocument();
    });

    it('exposes filter chips for all/handoff/source/mixed', async () => {
        renderDashboardInflowLabPage();
        await waitFor(() => {
            expect(screen.getByText('Filter')).toBeInTheDocument();
        });
        expect(screen.getByRole('button', { name: 'all' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'handoff' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'source' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'mixed' })).toBeInTheDocument();
    });
});
