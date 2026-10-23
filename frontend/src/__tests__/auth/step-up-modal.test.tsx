import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StepUpModal } from '@/components/auth/StepUpModal';
import { DEFAULT_STEP_UP_REASON, STEP_UP_REQUIRED_EVENT, requestStepUp } from '@/lib/step-up-events';

const mocks = vi.hoisted(() => ({ login: vi.fn(), seed: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ user: { email: 'tester@example.com' } }) }));
vi.mock('@/lib/passwordless-auth', () => ({
    isValidEmail: () => true,
    performPasskeyLogin: mocks.login,
    seedPasswordlessClientUser: mocks.seed,
}));

describe('step-up error recovery', () => {
    beforeEach(() => { mocks.login.mockReset(); mocks.seed.mockReset(); mocks.push.mockReset(); });

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

describe('step-up prompt reason and cancel', () => {
    beforeEach(() => { mocks.login.mockReset(); mocks.push.mockReset(); });

    it('stays closed until a protected action asks for step-up', () => {
        render(<StepUpModal />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('states the action the prompt protects', () => {
        render(<StepUpModal />);
        act(() => requestStepUp({ reason: "Confirm it's you to view this sensitive page." }));
        expect(screen.getByRole('dialog')).toHaveTextContent("Confirm it's you to view this sensitive page.");
    });

    it('falls back to a generic action sentence when the event carries no reason', () => {
        render(<StepUpModal />);
        act(() => window.dispatchEvent(new Event(STEP_UP_REQUIRED_EVENT)));
        expect(screen.getByRole('dialog')).toHaveTextContent(DEFAULT_STEP_UP_REASON);
    });

    it('cancel closes the prompt and returns to the safe page', async () => {
        render(<StepUpModal />);
        act(() => requestStepUp({ reason: "Confirm it's you to view QA Health.", returnTo: '/dashboard' }));
        await userEvent.setup().click(screen.getByRole('button', { name: /^cancel$/i }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(mocks.push).toHaveBeenCalledWith('/dashboard');
        expect(mocks.login).not.toHaveBeenCalled();
    });

    it('cancel without a return path keeps the user on the current page', async () => {
        render(<StepUpModal />);
        act(() => requestStepUp({ reason: "Confirm it's you to complete this action." }));
        await userEvent.setup().click(screen.getByRole('button', { name: /^cancel$/i }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(mocks.push).not.toHaveBeenCalled();
    });
});
