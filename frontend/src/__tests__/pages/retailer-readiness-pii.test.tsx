import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type React from 'react';
import RetailerSuppliersPage from '@/app/retailer-readiness/page';

vi.mock('@/components/fsma-checklist', () => ({ default: () => <div /> }));
vi.mock('@/components/tools/EmailGate', () => ({
    EmailGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/fsma-tools-data', () => ({
    FSMA_204_DEADLINE_ISO: '2028-01-20',
    daysUntilFSMA204: () => 100,
}));

vi.mock('@/app/retailer-readiness/components/constants', () => ({
    T: {
        bg: '#000',
        surface: '#111',
        border: '#333',
        text: '#ddd',
        textMuted: '#aaa',
        textDim: '#777',
        heading: '#fff',
        accent: '#2563eb',
        danger: '#dc2626',
    },
    TRACE_NODES_FORWARD: [],
    TRACE_NODES_BACKWARD: [],
    useScrollReveal: () => ({ ref: { current: null }, visible: false }),
    useTrackEvent: () => (event: string, data?: Record<string, unknown>) => {
        const events = JSON.parse(window.localStorage.getItem('retailer_analytics') || '[]');
        events.push({ event, data });
        window.localStorage.setItem('retailer_analytics', JSON.stringify(events));
    },
}));

vi.mock('@/app/retailer-readiness/components/ScrollProgressBar', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/StickyCTA', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/ExitIntentPopup', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/HeroSection', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/UrgencyBanner', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/ComplianceTimeline', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/TraceDemo', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/BeforeAfterComparison', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/RiskCalculator', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/PricingSection', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/FounderCredibility', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/CompetitorComparison', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/FaqAccordion', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/IntegrationsGrid', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/TrustBadges', () => ({ default: () => <div /> }));
vi.mock('@/app/retailer-readiness/components/PageStyles', () => ({ default: () => <div /> }));

let storage: Record<string, string>;

function installLocalStorageMock() {
    storage = {};
    Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
            getItem: vi.fn((key: string) => storage[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                storage[key] = String(value);
            }),
            removeItem: vi.fn((key: string) => {
                delete storage[key];
            }),
            clear: vi.fn(() => {
                storage = {};
            }),
        },
    });
}

function installMatchMediaMock() {
    Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: vi.fn().mockImplementation((query: string) => ({
            matches: false,
            media: query,
            onchange: null,
            addListener: vi.fn(),
            removeListener: vi.fn(),
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
            dispatchEvent: vi.fn(),
        })),
    });
}

describe('retailer readiness lead submission PII storage', () => {
    beforeEach(() => {
        installLocalStorageMock();
        installMatchMediaMock();
        vi.restoreAllMocks();
    });

    it('posts the lead to the server and persists only non-PII completion state', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
        const user = userEvent.setup();

        render(<RetailerSuppliersPage />);

        await user.type(screen.getByLabelText(/Company Name/i), 'Acme Foods');
        await user.type(screen.getByLabelText(/Work Email/i), 'lead@example.com');
        await user.click(screen.getByRole('button', { name: /Get Free Assessment/i }));

        await waitFor(() => expect(fetch).toHaveBeenCalledWith(
            '/api/v1/assessments/retailer-readiness',
            expect.objectContaining({
                method: 'POST',
                body: expect.stringContaining('lead@example.com'),
            }),
        ));

        expect(window.localStorage.getItem('retailer_supplier_lead')).toBeNull();
        expect(window.localStorage.getItem('retailer_supplier_lead_submitted')).toBe('1');
        expect(window.localStorage.getItem('retailer_analytics')).not.toContain('lead@example.com');
        expect(window.localStorage.getItem('retailer_analytics')).not.toContain('Acme Foods');
    });

    it('keeps entered details on-page and stores only non-PII retry state when posting fails', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
        const user = userEvent.setup();

        render(<RetailerSuppliersPage />);

        await user.type(screen.getByLabelText(/Company Name/i), 'Acme Foods');
        await user.type(screen.getByLabelText(/Work Email/i), 'lead@example.com');
        await user.click(screen.getByRole('button', { name: /Get Free Assessment/i }));

        expect(await screen.findByRole('alert')).toHaveTextContent(/could not send/i);
        expect(screen.getByLabelText(/Company Name/i)).toHaveValue('Acme Foods');
        expect(screen.getByLabelText(/Work Email/i)).toHaveValue('lead@example.com');

        const retry = window.localStorage.getItem('retailer_supplier_lead_retry') || '';
        expect(window.localStorage.getItem('retailer_supplier_lead')).toBeNull();
        expect(retry).toContain('"pending":true');
        expect(retry).not.toContain('lead@example.com');
        expect(retry).not.toContain('Acme Foods');
        expect(window.localStorage.getItem('retailer_analytics')).not.toContain('lead@example.com');
        expect(window.localStorage.getItem('retailer_analytics')).not.toContain('Acme Foods');
    });
});
