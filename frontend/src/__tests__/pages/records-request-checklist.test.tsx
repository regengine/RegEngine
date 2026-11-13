import { StrictMode, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RecordsRequestChecklistClient } from '@/app/tools/records-request-checklist/components/RecordsRequestChecklistClient';

vi.mock('@/app/actions/submit-assessment', () => ({ submitAssessment: vi.fn() }));

// Exercise the results render path without entering any assessment or lead data.
vi.mock('@/components/fsma/FSMAToolShell', () => ({
    FSMAToolShell: ({ renderResults }: { renderResults: (answers: Record<string, unknown>) => ReactNode }) => (
        <>{renderResults({})}</>
    ),
}));

vi.mock('framer-motion', () => ({
    useReducedMotion: () => true,
    motion: {
        div: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
    },
}));

describe('records request checklist results', () => {
    it('renders and rerenders results without render-time state updates', () => {
        const errors = vi.spyOn(console, 'error').mockImplementation((message) => {
            throw new Error(String(message));
        });
        try {
            const view = render(<StrictMode><RecordsRequestChecklistClient /></StrictMode>);
            expect(screen.getByRole('heading', { name: 'What You Reported' })).toBeInTheDocument();
            expect(() => view.rerender(<StrictMode><RecordsRequestChecklistClient /></StrictMode>)).not.toThrow();
            expect(errors).not.toHaveBeenCalled();
        } finally {
            errors.mockRestore();
        }
    });

    // Note: Lead submission payload (score, grade, answers in toolInputs) is verified
    // by the FSMAToolShell integration test suite (fsma-tool-shell-lead.test.tsx).
    // The handleLeadSubmit implementation derives score/grade from answers via calcScore()
    // and includes all three in toolInputs.answers for submitAssessment.
});
