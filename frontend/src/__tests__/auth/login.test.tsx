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
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';

// Mock Next.js router
vi.mock('next/navigation', () => ({
    useRouter: vi.fn(),
}));

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

// Mock API client
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        login: vi.fn(),
    },
}));

describe('LoginPage', () => {
    const mockPush = vi.fn();
    const mockLogin = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        (useRouter as any).mockReturnValue({ push: mockPush });
        (useAuth as any).mockReturnValue({ login: mockLogin });
    });

    describe('Rendering', () => {
        it('renders login form with all fields', () => {
            render(<LoginPage />);

            expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
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
            let resolveLogin: any;
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
            let resolveLogin: any;
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
