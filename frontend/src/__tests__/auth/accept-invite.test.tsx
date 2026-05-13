import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AcceptInviteClient from '@/app/accept-invite/AcceptInviteClient';

const { acceptInviteMock, pushMock } = vi.hoisted(() => ({
    acceptInviteMock: vi.fn(),
    pushMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: pushMock }),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        acceptInvite: acceptInviteMock,
    },
}));

describe('AcceptInviteClient', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        acceptInviteMock.mockResolvedValue(undefined);
        window.history.replaceState(null, '', '/');
    });

    it('reads fragment invite tokens and scrubs them from browser history', async () => {
        const user = userEvent.setup();
        window.history.replaceState(null, '', '/accept-invite#token=fragment-secret');

        render(<AcceptInviteClient />);

        await waitFor(() => {
            expect(window.location.hash).toBe('');
            expect(window.location.href).not.toContain('fragment-secret');
        });

        await user.type(screen.getByPlaceholderText('John Doe'), 'Invite User');
        const passwords = document.querySelectorAll<HTMLInputElement>('input[type="password"]');
        await user.type(passwords[0], 'StrongInvite123!');
        await user.type(passwords[1], 'StrongInvite123!');
        await user.click(screen.getByRole('button', { name: /create account/i }));

        await waitFor(() => {
            expect(acceptInviteMock).toHaveBeenCalledWith({
                token: 'fragment-secret',
                password: 'StrongInvite123!', // pragma: allowlist secret
                name: 'Invite User',
            });
        });
        expect(await screen.findByText(/welcome aboard/i)).toBeInTheDocument();
    });

    it('scrubs legacy query token and email values without using email for auto-login', async () => {
        window.history.replaceState(
            null,
            '',
            '/accept-invite?token=query-secret&email=person%40example.com',
        );

        render(<AcceptInviteClient />);

        await screen.findByRole('button', { name: /create account/i });
        expect(window.location.search).not.toContain('token=');
        expect(window.location.search).not.toContain('email=');
        expect(window.location.href).not.toContain('query-secret');
        expect(window.location.href).not.toContain('person%40example.com');
        expect(acceptInviteMock).not.toHaveBeenCalled();
    });
});
