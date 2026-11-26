/**
 * PostHog `tool_started` for the 9 gap tools: each start fires exactly one
 * `tool_started` with its own `tool_id`, next to the kept Vercel
 * `trackToolRunStarted` call. Scan's camera once-per-start guard is mirrored
 * for PostHog. Gating (cookieless before Accept, none after Decline) is
 * covered in `src/__tests__/lib/tool-started-gaps-gating.test.tsx`.
 */
import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AskPage from '@/app/tools/ask/page';
import { DataImportClient } from '@/app/tools/data-import/components/DataImportClient';
import { DrillSimulatorClient } from '@/app/tools/drill-simulator/components/DrillSimulatorClient';
import ExportPage from '@/app/tools/export/page';
import LabelScannerPage from '@/app/tools/label-scanner/page';
import NoticeValidatorPage from '@/app/tools/notice-validator/page';
import ScanPage from '@/app/tools/scan/page';
import { SOPGeneratorClient } from '@/app/tools/sop-generator/components/SOPGeneratorClient';
import { FSMA204Assessment } from '@/components/fsma/readiness-assessment';

const { capture, trackToolRunStarted, trackToolRunCompleted, ingestFile, toast, fetchWithCsrf } = vi.hoisted(() => ({
    capture: vi.fn(),
    trackToolRunStarted: vi.fn(),
    trackToolRunCompleted: vi.fn(),
    ingestFile: vi.fn(),
    toast: vi.fn(),
    fetchWithCsrf: vi.fn(),
}));

const qr = vi.hoisted(() => ({
    decode: null as null | ((text: string) => void),
}));

vi.mock('@/lib/posthog-provider', () => ({
    usePostHog: () => ({ capture }),
}));

vi.mock('@/lib/conversion-events', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/conversion-events')>()),
    trackToolRunStarted,
    trackToolRunCompleted,
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ apiKey: 'cookie-managed', tenantId: 'tenant-1', user: null, isAuthenticated: false, isLoading: false }), // pragma: allowlist secret
}));

vi.mock('@/lib/api-client', () => ({ apiClient: { ingestFile } }));
vi.mock('@/lib/fetch-with-csrf', () => ({ fetchWithCsrf }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));
vi.mock('@/components/layout/FreeToolPageShell', () => ({
    FreeToolPageShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/lead-gate/LeadGate', () => ({
    LeadGate: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/tools/EmailGate', () => ({
    EmailGate: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock('framer-motion', () => ({
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    motion: new Proxy({}, {
        get: () => ({ children, className }: { children?: ReactNode; className?: string }) => (
            <div className={className}>{children}</div>
        ),
    }),
}));

vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: { children?: ReactNode; href: string }) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('html5-qrcode', () => ({
    Html5Qrcode: class {
        start(_config: unknown, _qrbox: unknown, onSuccess: (text: string) => void) {
            qr.decode = onSuccess;
            return Promise.resolve();
        }
        stop() {
            return Promise.resolve();
        }
        clear() {
            return Promise.resolve();
        }
    },
}));

function eventsNamed(name: string) {
    return capture.mock.calls.filter(([event]) => event === name);
}

const GS1_BARCODE = '(01)09506000123457(17)251231(10)LOT001';

describe('gap tools fire PostHog tool_started once per start', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        qr.decode = null;
        fetchWithCsrf.mockResolvedValue({ ok: true, json: async () => ({}) });
    });

    it('ask fires tool_started once and keeps the Vercel start', async () => {
        render(<AskPage />);
        fireEvent.change(screen.getByPlaceholderText(/Where did lot/), {
            target: { value: 'Where did lot LOT-2024-001 go?' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'ask' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('ask');
        await waitFor(() => expect(trackToolRunCompleted).toHaveBeenCalledWith('ask', 'success'));
    });

    it('data-import fires tool_started once per upload', async () => {
        ingestFile.mockResolvedValue({
            total: 1,
            accepted: 1,
            rejected: 0,
            ingestion_timestamp: '2026-08-31T12:00:00+00:00',
            events: [{
                traceability_lot_code: 'LOT-1',
                cte_type: 'shipping',
                status: 'accepted',
                event_id: 'evt-1',
                sha256_hash: 'sha-1',
                chain_hash: 'chain-1',
                errors: [],
            }],
        });
        render(<DataImportClient />);
        fireEvent.change(screen.getByLabelText('Upload CSV file'), {
            target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv', { type: 'text/csv' })] },
        });
        fireEvent.click(screen.getByRole('button', { name: /submit to ingestion pipeline/i }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'data-import' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('data-import');
        expect(await screen.findByText('CSV processed')).toBeInTheDocument();
    });

    it('drill-simulator fires tool_started once per analysis', () => {
        render(<DrillSimulatorClient />);
        fireEvent.click(screen.getByRole('button', { name: /Start Drill/ }));
        fireEvent.change(screen.getByLabelText('Upload Your Records'), {
            target: {
                files: [new File(
                    [['event_type,event_date,event_time,lot_code,product_name,quantity,unit,from_party,to_party,location',
                        'ship,2026-01-01,08:00,LOT-1,Romaine,10,cases,Farm A,DC B,Salinas'].join('\n')],
                    'records.csv',
                    { type: 'text/csv' },
                )],
            },
        });
        fireEvent.click(screen.getByRole('button', { name: /Analyze My Records/ }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'drill-simulator' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('drill-simulator');
    });

    it('export fires tool_started once per file upload', () => {
        render(<ExportPage />);
        fireEvent.change(screen.getByLabelText('Upload Your Records'), {
            target: {
                files: [new File(
                    [['tlc,product,quantity,uom,event_date,event_type,location',
                        'LOT-1,Romaine,10,cases,2026-01-01,receiving,Salinas'].join('\n')],
                    'records.csv',
                    { type: 'text/csv' },
                )],
            },
        });

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'export' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('export');
    });

    it('label-scanner fires tool_started once per image', async () => {
        fetchWithCsrf.mockResolvedValue({
            ok: false,
            status: 500,
            statusText: 'vision offline',
            json: async () => ({ detail: 'vision offline' }),
        });
        render(<LabelScannerPage />);
        fireEvent.change(screen.getByLabelText('Upload a label image'), {
            target: { files: [new File(['fake-bytes'], 'label.png', { type: 'image/png' })] },
        });

        expect(await screen.findByText('vision offline')).toBeInTheDocument();
        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'label-scanner' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('label-scanner');
    });

    it('notice-validator fires tool_started once per check', () => {
        render(<NoticeValidatorPage />);
        fireEvent.change(screen.getByLabelText(/Paste an FDA request response/), {
            target: { value: 'Our traceability lot code TLC-1 covers receiving and shipping with quantity and unit of measure.' },
        });
        fireEvent.click(screen.getByRole('button', { name: /Run keyword self-check/ }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'notice-validator' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('notice-validator');
    });

    it('scan manual parse fires tool_started once', () => {
        render(<ScanPage />);
        fireEvent.change(screen.getByLabelText(/Paste or type barcode/), { target: { value: GS1_BARCODE } });
        fireEvent.click(screen.getByRole('button', { name: 'Parse' }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'scan' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledTimes(1);
    });

    it('scan manual parses keep PostHog/Vercel parity per start', () => {
        render(<ScanPage />);
        fireEvent.change(screen.getByLabelText(/Paste or type barcode/), { target: { value: GS1_BARCODE } });
        fireEvent.click(screen.getByRole('button', { name: 'Parse' }));
        fireEvent.change(screen.getByLabelText(/Paste or type barcode/), {
            target: { value: '(01)09506000123457(10)LOT002' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Parse' }));

        expect(eventsNamed('tool_started')).toHaveLength(2);
        expect(trackToolRunStarted).toHaveBeenCalledTimes(2);
    });

    it('scan camera start + camera parse fire tool_started once for the one start', async () => {
        render(<ScanPage />);
        fireEvent.click(screen.getByRole('button', { name: 'Start Camera' }));
        await waitFor(() =>
            expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'scan' }]]),
        );

        expect(qr.decode).toBeTypeOf('function');
        qr.decode?.(GS1_BARCODE);

        expect(eventsNamed('tool_started')).toHaveLength(1);
        expect(trackToolRunStarted).toHaveBeenCalledTimes(1);
    });

    it('sop-generator fires tool_started once per generation', () => {
        const { container } = render(<SOPGeneratorClient />);
        // The Generate button stays disabled until the required fields pass.
        const byName = (name: string) => container.querySelector(`input[name="${name}"]`) as HTMLInputElement;
        fireEvent.change(byName('company_name'), { target: { value: 'Valley Fresh Produce' } });
        fireEvent.change(byName('primary_contact'), { target: { value: 'QA Manager' } });
        const freeText = () => Array.from(container.querySelectorAll('input')).filter(
            (el) => el.type === 'text' && !el.getAttribute('name'),
        );
        expect(freeText()).toHaveLength(2); // products[0], facilities[0]
        // Re-query before each fill: the mocked motion wrapper remounts on
        // every state change, so a pre-queried node goes stale after the
        // first fill.
        fireEvent.change(freeText()[0], { target: { value: 'Romaine lettuce' } });
        fireEvent.change(freeText()[1], { target: { value: 'Salinas packing shed' } });
        fireEvent.click(screen.getByRole('button', { name: /Generate Draft Template/ }));

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'sop-generator' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('sop-generator');
    });

    it('self-reported-checklist fires tool_started once no matter how many products are toggled', () => {
        window.history.replaceState({}, '', '/tools/self-reported-checklist');
        try {
            render(<FSMA204Assessment />);
            fireEvent.click(screen.getByRole('button', { name: /Shell Eggs/ }));
            fireEvent.click(screen.getByRole('button', { name: /Tomatoes/ }));

            expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'self-reported-checklist' }]]);
            expect(trackToolRunStarted).toHaveBeenCalledTimes(1);
        } finally {
            window.history.replaceState({}, '', '/');
        }
    });
});
