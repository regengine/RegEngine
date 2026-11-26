/**
 * SEL-585 F6 + F7: skipping or finishing exemptions must not leave the
 * exemption questions as the only interactive UI. The checker switches to
 * the results step with an aria-busy loading skeleton (no invented numbers),
 * and the categories step button reads `Continue to exemptions`.
 */
import type { ReactNode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FTLCheckerClient } from '@/app/tools/ftl-checker/components/FTLCheckerClient';

const { capture, trackToolRunStarted, trackToolRunCompleted } = vi.hoisted(() => ({
    capture: vi.fn(),
    trackToolRunStarted: vi.fn(),
    trackToolRunCompleted: vi.fn(),
}));

vi.mock('@/lib/posthog-provider', () => ({
    usePostHog: () => ({ capture }),
}));

vi.mock('@/lib/conversion-events', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/conversion-events')>()),
    trackToolRunStarted,
    trackToolRunCompleted,
}));

vi.mock('@/app/actions/submit-assessment', () => ({
    submitAssessment: vi.fn().mockResolvedValue({ success: true }),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ user: null, isAuthenticated: false, isLoading: false }),
}));

vi.mock('framer-motion', () => ({
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    motion: new Proxy({}, {
        get: () => ({ children, className }: { children?: ReactNode; className?: string }) => (
            <div className={className}>{children}</div>
        ),
    }),
}));

function eventsNamed(name: string) {
    return capture.mock.calls.filter(([event]) => event === name);
}

async function goToExemptions(user: ReturnType<typeof userEvent.setup>) {
    render(<FTLCheckerClient />);
    await user.click(screen.getByText('Shell Eggs').closest('button') as HTMLElement);
    await user.click(screen.getByRole('button', { name: 'Continue to exemptions' }));
    await screen.findByRole('button', { name: 'Skip Exemptions' });
}

describe('SEL-585 F6 + F7 exemptions transition and button label', () => {
    beforeEach(() => {
        capture.mockReset();
        trackToolRunStarted.mockReset();
        trackToolRunCompleted.mockReset();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('F7: categories step button reads Continue to exemptions', () => {
        render(<FTLCheckerClient />);

        expect(screen.getByRole('button', { name: 'Continue to exemptions' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Check Listed Groupings/i })).not.toBeInTheDocument();
    });

    it('F6: Skip Exemptions shows an aria-busy results skeleton with no invented numbers', async () => {
        let rafCallback: ((time: number) => void) | null = null;
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
            rafCallback = callback;
            return 1;
        });
        const user = userEvent.setup();
        await goToExemptions(user);

        await user.click(screen.getByRole('button', { name: 'Skip Exemptions' }));

        const skeleton = screen.getByTestId('results-loading');
        expect(skeleton).toHaveAttribute('aria-busy', 'true');
        expect(skeleton.textContent).not.toMatch(/\d/);
        expect(screen.queryByRole('button', { name: 'Skip Exemptions' })).not.toBeInTheDocument();

        act(() => {
            rafCallback?.(16);
        });
        await waitFor(() =>
            expect(screen.queryByTestId('results-loading')).not.toBeInTheDocument(),
        );
    });

    it('F6: See Results never leaves the exemption questions interactive with an enabled Skip', async () => {
        const user = userEvent.setup();
        await goToExemptions(user);

        await user.click(screen.getByRole('button', { name: 'See Results' }));

        const skipAfter = screen.queryByRole('button', { name: 'Skip Exemptions' });
        const loadingAfter = screen.queryByTestId('results-loading');
        const leftInteractive =
            skipAfter !== null &&
            (skipAfter as HTMLButtonElement).disabled === false &&
            loadingAfter === null;
        expect(leftInteractive).toBe(false);

        await waitFor(() =>
            expect(eventsNamed('tool_completed')).toEqual([['tool_completed', { tool_id: 'ftl-checker', status: 'success' }]]),
        );
    });

    it('F1 intact: continuing from categories still captures tool_started', async () => {
        const user = userEvent.setup();
        await goToExemptions(user);

        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'ftl-checker' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('ftl-checker');
    });
});
