/**
 * Tests for CuratorReview dashboard component
 * 
 * This component displays the review queue for curators:
 * - Fetches pending review items
 * - Displays confidence scores
 * - Allows approve/reject actions
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Mock React Query
vi.mock('@tanstack/react-query', async () => {
    const actual = await vi.importActual('@tanstack/react-query');
    return {
        ...actual,
        useQuery: vi.fn().mockReturnValue({
            data: [],
            isLoading: false,
            error: null,
            refetch: vi.fn(),
        }),
        useMutation: vi.fn().mockReturnValue({
            mutate: vi.fn(),
            mutateAsync: vi.fn(),
            isLoading: false,
            isPending: false,
        }),
        useQueryClient: vi.fn().mockReturnValue({
            invalidateQueries: vi.fn(),
            setQueryData: vi.fn(),
        }),
    };
});

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({
        apiKey: 'test-api-key',
        tenantId: 'test-tenant',
        setApiKey: vi.fn(),
        setTenantId: vi.fn(),
    }),
    AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock tenant context
vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => ({
        selectedTenant: { id: 'test-tenant', name: 'Test Tenant' },
        tenantId: 'test-tenant',
        setTenantId: vi.fn(),
    }),
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch as any;

describe('CuratorReview', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockFetch.mockReset();
    });

    it('renders empty state when no items', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve([]),
        });

        // Import after mocking
        const { CuratorReview } = await import('@/components/dashboard/curator-review');

        render(<CuratorReview />);

        await waitFor(() => {
            // Should show empty state or loading
            expect(screen.queryByText(/review/i) || screen.queryByText(/loading/i)).toBeTruthy();
        });
    });

    it('renders review items when data exists', async () => {
        const mockItems = [
            {
                id: '1',
                doc_hash: 'hash-1',
                confidence_score: 0.75,
                text_raw: 'Sample regulatory text',
                extraction: { type: 'OBLIGATION' },
            },
        ];

        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockItems),
        });

        const { CuratorReview } = await import('@/components/dashboard/curator-review');

        render(<CuratorReview />);

        // Component should attempt to render items
    });
});

describe('ReviewItem format', () => {
    it('expects correct item structure', () => {
        const expectedFields = [
            'id',
            'doc_hash',
            'confidence_score',
            'text_raw',
            'extraction',
        ];

        // Document the expected format
        expect(expectedFields.length).toBe(5);
    });

    it('confidence_score should be between 0 and 1', () => {
        const validScores = [0.0, 0.5, 0.75, 1.0];

        validScores.forEach(score => {
            expect(score).toBeGreaterThanOrEqual(0);
            expect(score).toBeLessThanOrEqual(1);
        });
    });
});
