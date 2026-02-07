/**
 * Tests for DemoIngestion component
 * 
 * This component handles the live demo ingestion flow:
 * - Auto-provisions demo credentials if not authenticated
 * - Ingests DORA regulation from EUR-Lex
 * - Shows loading states and error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DemoIngestion } from '@/components/onboarding/DemoIngestion';

// Mock the hooks
vi.mock('@/hooks/use-api', () => ({
    useIngestURL: () => ({
        mutateAsync: vi.fn().mockResolvedValue({ status: 'ok' }),
        isLoading: false,
    }),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({
        apiKey: null,
        setApiKey: vi.fn(),
        setTenantId: vi.fn(),
        completeOnboarding: vi.fn(),
    }),
}));

vi.mock('@/components/ui/use-toast', () => ({
    toast: vi.fn(),
}));

// Mock DemoProgressProvider context
vi.mock('@/components/onboarding/DemoProgress', () => ({
    useDemoProgress: () => ({
        isCompleted: false,
        isActive: false,
        completeStep: vi.fn(),
        resetProgress: vi.fn(),
        startDemo: vi.fn(),
        endDemo: vi.fn(),
    }),
    DemoProgressProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch as any;

describe('DemoIngestion', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockFetch.mockReset();
    });

    it('renders the demo ingestion component', () => {
        render(<DemoIngestion />);

        expect(screen.getByText('See It In Action')).toBeInTheDocument();
        expect(screen.getByText(/DORA/)).toBeInTheDocument();
        // Component has multiple buttons
        expect(screen.getAllByRole('button').length).toBeGreaterThan(0);
    });

    it('displays demo buttons initially', () => {
        render(<DemoIngestion />);

        // Check for the actual button texts in the component
        expect(screen.getByText('Start Full Demo Tour')).toBeInTheDocument();
        expect(screen.getByText('Quick Ingest Only')).toBeInTheDocument();
    });

    it('calls setup-demo API when clicking demo button', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ apiKey: 'test-key', tenantId: 'test-tenant' }),
        });

        render(<DemoIngestion />);

        // Get the first button (Start Full Demo Tour)
        const buttons = screen.getAllByRole('button');
        fireEvent.click(buttons[0]);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });
    });

    it('shows loading state during ingestion', async () => {
        mockFetch.mockImplementation(() =>
            new Promise(resolve => setTimeout(() => resolve({
                ok: true,
                json: () => Promise.resolve({ apiKey: 'key', tenantId: 'tenant' }),
            }), 100))
        );

        render(<DemoIngestion />);

        const buttons = screen.getAllByRole('button');
        fireEvent.click(buttons[0]);

        // Button should show loading state (may be disabled)
        await waitFor(() => {
            const allButtons = screen.getAllByRole('button');
            expect(allButtons.some(btn => btn.hasAttribute('disabled'))).toBe(true);
        }, { timeout: 200 });
    });

    it('shows error toast when setup fails', async () => {
        const { toast } = await import('@/components/ui/use-toast');

        mockFetch.mockResolvedValueOnce({
            ok: false,
        });

        render(<DemoIngestion />);

        const buttons = screen.getAllByRole('button');
        fireEvent.click(buttons[0]);

        await waitFor(() => {
            expect(toast).toHaveBeenCalled();
        });
    });
});

describe('DemoIngestion accessibility', () => {
    it('has accessible buttons', () => {
        render(<DemoIngestion />);

        const buttons = screen.getAllByRole('button');
        expect(buttons.length).toBeGreaterThan(0);
        buttons.forEach(button => {
            expect(button).toBeInTheDocument();
        });
    });

    it('buttons are disabled during loading', async () => {
        mockFetch.mockImplementation(() =>
            new Promise(resolve => setTimeout(resolve, 1000))
        );

        render(<DemoIngestion />);

        const buttons = screen.getAllByRole('button');
        fireEvent.click(buttons[0]);

        await waitFor(() => {
            const allButtons = screen.getAllByRole('button');
            expect(allButtons.some(btn => btn.hasAttribute('disabled'))).toBe(true);
        }, { timeout: 500 });
    });
});

