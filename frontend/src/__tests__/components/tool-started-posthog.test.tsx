/**
 * SEL-585 F1: tool starts and completions reach PostHog as one event name
 * (`tool_started` / `tool_completed` with `tool_id`) from both the shared
 * FSMA tool shell and the FTL Checker. The existing Vercel Analytics calls
 * and the legacy per-tool `<id>_TOOL_START` event are kept.
 */
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { FTLCheckerClient } from '@/app/tools/ftl-checker/components/FTLCheckerClient';
import type { ToolConfig } from '@/types/fsma-tools';

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

const shellConfig: ToolConfig = {
    id: 'kde-checker',
    title: 'KDE Checker',
    description: 'A sample tool.',
    icon: 'TestTube',
    stages: {
        questions: [{ id: 'choice', text: 'Choose one', type: 'select', options: [{ label: 'Yes', value: 'yes' }] }],
    },
};

function eventsNamed(name: string) {
    return capture.mock.calls.filter(([event]) => event === name);
}

describe('SEL-585 F1 tool_started and tool_completed in PostHog', () => {
    beforeEach(() => {
        capture.mockReset();
        trackToolRunStarted.mockReset();
        trackToolRunCompleted.mockReset();
    });

    it('FSMAToolShell sends tool_started and tool_completed with tool_id and keeps the old events', async () => {
        const user = userEvent.setup();
        render(<FSMAToolShell config={shellConfig} renderResults={() => <div>Tool result</div>} />);

        await user.click(screen.getByRole('button', { name: 'Start Tool' }));
        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'kde-checker' }]]);
        expect(capture).toHaveBeenCalledWith('kde-checker_TOOL_START', { tool_id: 'kde-checker' });
        expect(trackToolRunStarted).toHaveBeenCalledWith('kde-checker');

        await user.click(await screen.findByRole('button', { name: 'Yes' }));
        expect(await screen.findByText('Tool result')).toBeInTheDocument();
        await waitFor(() =>
            expect(eventsNamed('tool_completed')).toEqual([['tool_completed', { tool_id: 'kde-checker', status: 'success' }]]),
        );
        expect(trackToolRunCompleted).toHaveBeenCalledWith('kde-checker', 'success');
    });

    it('FTLCheckerClient sends tool_started once per run and tool_completed on results', async () => {
        const user = userEvent.setup();
        render(<FTLCheckerClient />);

        await user.click(screen.getByText('Shell Eggs').closest('button') as HTMLElement);
        await user.click(screen.getByRole('button', { name: 'Continue to exemptions' }));
        expect(eventsNamed('tool_started')).toEqual([['tool_started', { tool_id: 'ftl-checker' }]]);
        expect(trackToolRunStarted).toHaveBeenCalledWith('ftl-checker');

        await user.click(await screen.findByRole('button', { name: 'Skip Exemptions' }));
        await waitFor(() =>
            expect(eventsNamed('tool_completed')).toEqual([['tool_completed', { tool_id: 'ftl-checker', status: 'success' }]]),
        );
        expect(trackToolRunCompleted).toHaveBeenCalledWith('ftl-checker', 'success');
        expect(eventsNamed('tool_started')).toHaveLength(1);
    });
});
