import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StepUpModal } from '@/components/auth/StepUpModal';
import { STEP_UP_REQUIRED_EVENT } from '@/lib/step-up-events';

const mocks = vi.hoisted(() => ({ login: vi.fn(), seed: vi.fn() }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ user: { email: 'tester@example.com' } }) }));
vi.mock('@/lib/passwordless-auth', () => ({
    isValidEmail: () => true,
    performPasskeyLogin: mocks.login,
    seedPasswordlessClientUser: mocks.seed,
}));

describe('step-up error recovery', () => {
    beforeEach(() => { mocks.login.mockReset(); mocks.seed.mockReset(); });

    it('keeps the protected action blocked and allows recovery after a domain error', async () => {
        mocks.login.mockRejectedValue(new DOMException('Invalid relying party ID', 'SecurityError'));
        render(<StepUpModal />);
        act(() => window.dispatchEvent(new Event(STEP_UP_REQUIRED_EVENT)));
        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /authenticate with passkey/i }));
        expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable on this domain/i);
        expect(screen.getByRole('alert')).toHaveTextContent(/action remains blocked/i);
        expect(screen.getByRole('button', { name: /authenticate with passkey/i })).toBeEnabled();
        expect(mocks.seed).not.toHaveBeenCalled();
        expect(mocks.login).toHaveBeenCalledTimes(1);
    });

    it('preserves cancellation errors without claiming a domain misconfiguration', async () => {
        mocks.login.mockRejectedValue(new DOMException('User cancelled', 'NotAllowedError'));
        render(<StepUpModal />);
        act(() => window.dispatchEvent(new Event(STEP_UP_REQUIRED_EVENT)));
        await userEvent.setup().click(screen.getByRole('button', { name: /authenticate with passkey/i }));
        expect(await screen.findByRole('alert')).toHaveTextContent('User cancelled');
        expect(mocks.seed).not.toHaveBeenCalled();
    });
});
