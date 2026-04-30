/**
 * Login Page Component Tests
 * 
 * Tests the authentication flow including:
 * - Form rendering and validation
 * - Successful login and redirect
 * - Error handling (401, 403, 500)
 * - Loading states
 * - Accessibility features
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '@/app/login/page';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';

// Mock Next.js router
vi.mock('next/navigation', () => ({
    useRouter: vi.fn(),
    useSearchParams: vi.fn(),
}));

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

// Mock API client
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        login: vi.fn(),
        getOnboardingStatus: vi.fn(),
    },
}));

// Mock Supabase session sync so login tests stay local and deterministic.
vi.mock('@/lib/supabase/client', () => ({
    createSupabaseBrowserClient: vi.fn(() => ({
        auth: {
            signInWithPassword: vi.fn().mockResolvedValue({ error: null }),
        },
    })),
}));

describe('LoginPage', () => {
    const mockPush = vi.fn();
    const mockReplace = vi.fn();
    const mockRefresh = vi.fn();
    const mockSearchParamGet = vi.fn();

    // Track the current auth state so mockLogin can trigger user update
    let authState: { user: any; login: any; isHydrated: boolean };
    const mockLogin = vi.fn().mockImplementation(async (_token: string, user: any, _tenantId?: string) => {
        // Simulate what the real login does: update user state
        authState.user = user;
        // useAuth mock will return updated user on next render
        (useAuth as any).mockReturnValue({ ...authState });
    });

    beforeEach(() => {
        vi.clearAllMocks();
        (useRouter as any).mockReturnValue({
            push: mockPush,
            replace: mockReplace,
            refresh: mockRefresh,
            back: vi.fn(),
            forward: vi.fn(),
            prefetch: vi.fn(),
        });
        mockSearchParamGet.mockReturnValue(null);
        (useSearchParams as any).mockReturnValue({ get: mockSearchParamGet });
        authState = { login: mockLogin, user: null, isHydrated: true };
        (useAuth as any).mockReturnValue(authState);
        (apiClient.getOnboardingStatus as any).mockResolvedValue({ is_complete: true });
        if (typeof window !== 'undefined' && window.localStorage?.clear) {
            window.localStorage.clear();
        }
    });

    describe('Rendering', () => {
        it('renders login form with all fields', () => {
            render(<LoginPage />);

            expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument();
            expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
            expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
            expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
        });

        it('has proper autocomplete attributes', () => {
            render(<LoginPage />);

            const emailInput = screen.getByLabelText(/email/i);
            const passwordInput = screen.getByLabelText(/password/i);

            expect(emailInput).toHaveAttribute('autocomplete', 'email');
            expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');
        });

        it('renders return to public site link', () => {
            render(<LoginPage />);

            const link = screen.getByRole('link', { name: /return to public site/i });
            expect(link).toBeInTheDocument();
            expect(link).toHaveAttribute('href', '/');
        });

        it('does not render hardcoded QA passwords in UI', () => {
            render(<LoginPage />);

            expect(screen.queryByText(/Trace204!User/i)).not.toBeInTheDocument();
            expect(screen.queryByText(/Trace204!Apex/i)).not.toBeInTheDocument();
        });

        it('applies QA preset email without populating password', async () => {
            const user = userEvent.setup();
            mockSearchParamGet.mockImplementation((key: string) => {
                if (key === 'qa') return '1';
                return null;
            });
            render(<LoginPage />);

            const passwordInput = screen.getByLabelText(/password/i);
            await user.type(passwordInput, 'temporary-password');

            await user.click(screen.getByRole('button', { name: /qa tester/i }));

            expect(screen.getByLabelText(/email/i)).toHaveValue('test@example.com');
            expect(screen.getByLabelText(/password/i)).toHaveValue('');
        });
    });

    describe('Form Validation', () => {
        it('requires email field', async () => {
            const user = userEvent.setup();
            render(<LoginPage />);

            const submitButton = screen.getByRole('button', { name: /sign in/i });
            await user.click(submitButton);

            const emailInput = screen.getByLabelText(/email/i) as HTMLInputElement;
            expect(emailInput.validity.valid).toBe(false);
        });

        it('requires password field', async () => {
            const user = userEvent.setup();
            render(<LoginPage />);

            const emailInput = screen.getByLabelText(/email/i);
            await user.type(emailInput, 'test@example.com');

            const submitButton = screen.getByRole('button', { name: /sign in/i });
            await user.click(submitButton);

            const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
            expect(passwordInput.validity.valid).toBe(false);
        });

        it('accepts email input', async () => {
            const user = userEvent.setup();
            render(<LoginPage />);

            const emailInput = screen.getByLabelText(/email/i);
            await user.type(emailInput, 'test@example.com');

            expect(emailInput).toHaveValue('test@example.com');
        });

        it('accepts password input', async () => {
            const user = userEvent.setup();
            render(<LoginPage />);

            const passwordInput = screen.getByLabelText(/password/i);
            await user.type(passwordInput, 'SecurePassword123!');

            expect(passwordInput).toHaveValue('SecurePassword123!');
        });
    });

    describe('Successful Login', () => {
        it('calls API with correct credentials', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'test-token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            };

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password123');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(apiClient.login).toHaveBeenCalledWith('test@example.com', 'password123');
            });
        });

        it('updates auth context on successful login', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'test-token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            };

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password123');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(mockLogin).toHaveBeenCalledWith(
                    'test-token',
                    mockResponse.user,
                    'tenant-123'
                );
            });
        });

        it('redirects to dashboard for regular users', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'test-token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            };

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password123');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/dashboard');
            });
        });

        it('redirects to provided safe next path for regular users', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'test-token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            };

            mockSearchParamGet.mockImplementation((key: string) => {
                if (key === 'next') return '/dashboard/fsma';
                return null;
            });

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password123');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/dashboard/fsma');
            });
        });

        it('falls back to dashboard when next path is unsafe', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'test-token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            };

            mockSearchParamGet.mockImplementation((key: string) => {
                if (key === 'next') return 'https://example.com/phish';
                return null;
            });

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password123');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/dashboard');
            });
        });

        it('redirects to sysadmin dashboard for admin users', async () => {
            const user = userEvent.setup();
            const mockResponse = {
                access_token: 'admin-token',
                user: { id: '456', email: 'admin@example.com', is_sysadmin: true },
                tenant_id: 'tenant-456',
            };

            (apiClient.login as any).mockResolvedValueOnce(mockResponse);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'admin@example.com');
            await user.type(screen.getByLabelText(/password/i), 'adminpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/sysadmin');
            });
        });

        it('redirects authenticated users away from login on mount', async () => {
            (useAuth as any).mockReturnValue({
                login: mockLogin,
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                isHydrated: true,
            });

            render(<LoginPage />);

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/dashboard');
            });
        });
    });

    describe('Error Handling', () => {
        it('shows error message for invalid credentials (401)', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 401 } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'wrong@example.com');
            await user.type(screen.getByLabelText(/password/i), 'wrongpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toHaveTextContent(/invalid email or password/i);
            });
        });

        it('shows error message for disabled account (403)', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 403 } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'disabled@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toHaveTextContent(/account access disabled/i);
            });
        });

        it('shows generic error for server errors (500)', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 500 } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toHaveTextContent(/unexpected error occurred/i);
            });
        });

        it('shows string error detail when backend returns plain text', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 500, data: '  Upstream admin auth timeout  ' } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toHaveTextContent('Upstream admin auth timeout');
            });
        });

        it('shows generic error for network failures', async () => {
            const user = userEvent.setup();
            const error = new Error('Network error');

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toHaveTextContent(/unexpected error occurred/i);
            });
        });

        it('clears error when submitting again', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 401 } };

            (apiClient.login as any)
                .mockRejectedValueOnce(error)
                .mockResolvedValueOnce({
                    access_token: 'token',
                    user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                    tenant_id: 'tenant-123',
                });

            render(<LoginPage />);

            // First attempt - fails
            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'wrongpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByRole('alert')).toBeInTheDocument();
            });

            // Second attempt - succeeds
            await user.clear(screen.getByLabelText(/password/i));
            await user.type(screen.getByLabelText(/password/i), 'correctpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.queryByRole('alert')).not.toBeInTheDocument();
            });
        });
    });

    describe('Loading States', () => {
        it('shows loading state during login', async () => {
            const user = userEvent.setup();
            let resolveLogin!: (value: unknown) => void;
            const loginPromise = new Promise((resolve) => {
                resolveLogin = resolve;
            });

            (apiClient.login as any).mockReturnValue(loginPromise);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            // Check loading state
            await waitFor(() => {
                expect(screen.getByRole('button', { name: /signing in/i })).toBeInTheDocument();
                expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
            });

            // Resolve login
            resolveLogin({
                access_token: 'token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            });

            await waitFor(() => {
                expect(screen.queryByRole('button', { name: /signing in/i })).not.toBeInTheDocument();
            });
        });

        it('disables inputs during login', async () => {
            const user = userEvent.setup();
            let resolveLogin!: (value: unknown) => void;
            const loginPromise = new Promise((resolve) => {
                resolveLogin = resolve;
            });

            (apiClient.login as any).mockReturnValue(loginPromise);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'test@example.com');
            await user.type(screen.getByLabelText(/password/i), 'password');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            // Check inputs disabled
            await waitFor(() => {
                expect(screen.getByLabelText(/email/i)).toBeDisabled();
                expect(screen.getByLabelText(/password/i)).toBeDisabled();
            });

            // Resolve login
            resolveLogin({
                access_token: 'token',
                user: { id: '123', email: 'test@example.com', is_sysadmin: false },
                tenant_id: 'tenant-123',
            });
        });
    });

    describe('Accessibility', () => {
        it('associates error with inputs via aria-invalid', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 401 } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'wrong@example.com');
            await user.type(screen.getByLabelText(/password/i), 'wrongpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                expect(screen.getByLabelText(/email/i)).toHaveAttribute('aria-invalid', 'true');
                expect(screen.getByLabelText(/password/i)).toHaveAttribute('aria-invalid', 'true');
            });
        });

        it('announces errors to screen readers', async () => {
            const user = userEvent.setup();
            const error = { response: { status: 401 } };

            (apiClient.login as any).mockRejectedValueOnce(error);

            render(<LoginPage />);

            await user.type(screen.getByLabelText(/email/i), 'wrong@example.com');
            await user.type(screen.getByLabelText(/password/i), 'wrongpass');
            await user.click(screen.getByRole('button', { name: /sign in/i }));

            await waitFor(() => {
                const alert = screen.getByRole('alert');
                expect(alert).toHaveAttribute('aria-live', 'polite');
            });
        });
    });
});
