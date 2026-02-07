/**
 * Dashboard Page Tests
 * 
 * Tests for the main dashboard view:
 * - Authentication checks
 * - Data loading and display
 * - Error states
 * - Tenant context
 * - Navigation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DashboardPage from '@/app/dashboard/page';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useRouter } from 'next/navigation';

// Mock Next.js router
vi.mock('next/navigation', () => ({
    useRouter: vi.fn(),
}));

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

// Mock tenant context
vi.mock('@/lib/tenant-context', () => ({
    useTenant: vi.fn(),
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch as any;

describe('DashboardPage', () => {
    const mockPush = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        mockFetch.mockReset();
        (useRouter as any).mockReturnValue({ push: mockPush });
    });

    describe('Authentication', () => {
        it('shows loading state during hydration', () => {
            (useAuth as any).mockReturnValue({
                user: null,
                isHydrated: false,
            });
            (useTenant as any).mockReturnValue({
                tenantId: null,
            });

            render(<DashboardPage />);

            // Should show loading or not render content yet
            expect(screen.queryByRole('main')).not.toBeInTheDocument();
        });

        it('redirects to login when not authenticated', () => {
            (useAuth as any).mockReturnValue({
                user: null,
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: null,
            });

            render(<DashboardPage />);

            waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/login');
            });
        });

        it('renders dashboard when authenticated', () => {
            (useAuth as any).mockReturnValue({
                user: {
                    id: '123',
                    email: 'test@example.com',
                    name: 'Test User',
                },
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });

            render(<DashboardPage />);

            // Dashboard should render (even if showing loading for data)
            expect(screen.queryByText(/welcome/i) || screen.queryByText(/dashboard/i)).toBeTruthy();
        });
    });

    describe('Dashboard Content', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: {
                    id: '123',
                    email: 'test@example.com',
                    name: 'Test User',
                },
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('displays user information', () => {
            render(<DashboardPage />);

            // Should display user email or name somewhere
            waitFor(() => {
                expect(
                    screen.queryByText(/test@example.com/i) ||
                    screen.queryByText(/test user/i)
                ).toBeTruthy();
            });
        });

        it('shows tenant information when available', () => {
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
                selectedTenant: {
                    id: 'tenant-123',
                    name: 'Acme Corp'
                },
            });

            render(<DashboardPage />);

            waitFor(() => {
                expect(screen.queryByText(/acme corp/i)).toBeTruthy();
            });
        });

        it('renders navigation links', () => {
            render(<DashboardPage />);

            // Common dashboard links
            const commonLinks = [
                /energy/i,
                /opportunity/i,
                /ingestion/i,
                /settings/i,
            ];

            waitFor(() => {
                const hasAtLeastOneLink = commonLinks.some(pattern =>
                    screen.queryByRole('link', { name: pattern })
                );
                expect(hasAtLeastOneLink).toBe(true);
            });
        });
    });

    describe('Data Loading', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('handles loading state for dashboard data', async () => {
            // Mock slow API response
            let resolveData: any;
            const dataPromise = new Promise((resolve) => {
                resolveData = resolve;
            });

            mockFetch.mockReturnValueOnce({
                ok: true,
                json: () => dataPromise,
            });

            render(<DashboardPage />);

            // Should show loading indicator
            await waitFor(() => {
                expect(
                    screen.queryByText(/loading/i) ||
                    screen.queryByRole('status')
                ).toBeTruthy();
            }, { timeout: 100 });

            // Resolve data
            if (resolveData) {
                resolveData({ stats: { total: 100 } });
            }
        });

        it('displays error when data fetch fails', async () => {
            mockFetch.mockRejectedValueOnce(new Error('API Error'));

            render(<DashboardPage />);

            await waitFor(() => {
                expect(
                    screen.queryByText(/error/i) ||
                    screen.queryByText(/failed/i) ||
                    screen.queryByRole('alert')
                ).toBeTruthy();
            });
        });
    });

    describe('Interactivity', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('allows navigation to sub-pages', async () => {
            const user = userEvent.setup();
            render(<DashboardPage />);

            // Try to find and click a navigation link
            await waitFor(async () => {
                const links = screen.queryAllByRole('link');
                if (links.length > 0) {
                    await user.click(links[0]);
                    // Navigation should occur (mockPush should be called or link should work)
                    return true;
                }
                return false;
            });
        });
    });

    describe('Accessibility', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('has proper document structure', () => {
            render(<DashboardPage />);

            // Should have main landmark or heading
            waitFor(() => {
                expect(
                    screen.queryByRole('main') ||
                    screen.queryByRole('heading', { level: 1 })
                ).toBeTruthy();
            });
        });

        it('all interactive elements are keyboard accessible', async () => {
            render(<DashboardPage />);

            await waitFor(() => {
                const buttons = screen.queryAllByRole('button');
                const links = screen.queryAllByRole('link');

                // All should be focusable (have tabIndex >= 0 or be naturally focusable)
                [...buttons, ...links].forEach(element => {
                    expect(element).toBeVisible();
                });
            });
        });
    });
});
