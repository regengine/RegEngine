import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { submitAssessment } from '@/app/actions/submit-assessment';

vi.mock('@/app/actions/submit-assessment', () => ({
    submitAssessment: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ user: null }),
}));

const mockedSubmit = vi.mocked(submitAssessment);

function fillGateForm() {
    fireEvent.change(screen.getByPlaceholderText('Full Name'), {
        target: { value: 'Ada Lovelace' },
    });
    fireEvent.change(screen.getByPlaceholderText('Work Email'), {
        target: { value: 'ada@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('Company Name'), {
        target: { value: 'Analytical Engines' },
    });
    fireEvent.change(screen.getByRole('combobox'), {
        target: { value: 'operations' },
    });
}

function gateForm(): HTMLFormElement {
    const button = screen.getByRole('button', { name: /unlock full results/i });
    const form = button.closest('form');
    if (!form) throw new Error('gate form not found');
    return form;
}

describe('LeadGate double-submit guard', () => {
    it('submits the gate form only once on rapid double submit', async () => {
        mockedSubmit.mockReset();
        let resolveSubmit!: (value: { success: boolean }) => void;
        mockedSubmit.mockImplementation(
            () =>
                new Promise<{ success: boolean }>((resolve) => {
                    resolveSubmit = resolve;
                }),
        );
        localStorage.clear();

        render(
            <LeadGate source="test-source">
                <div>full results</div>
            </LeadGate>,
        );
        fillGateForm();

        const form = gateForm();
        // Two submit events before the first request resolves (double-click).
        fireEvent.submit(form);
        fireEvent.submit(form);

        expect(mockedSubmit).toHaveBeenCalledTimes(1);

        resolveSubmit({ success: true });
        await waitFor(() => {
            expect(screen.getByText('Results Unlocked')).toBeInTheDocument();
        });
        expect(mockedSubmit).toHaveBeenCalledTimes(1);
    });

    it('allows a retry after a failed submission', async () => {
        mockedSubmit.mockReset();
        mockedSubmit.mockResolvedValueOnce({ success: false, error: 'Try again.' });
        mockedSubmit.mockResolvedValueOnce({ success: true });
        localStorage.clear();

        render(
            <LeadGate source="test-source">
                <div>full results</div>
            </LeadGate>,
        );
        fillGateForm();

        fireEvent.submit(gateForm());
        await waitFor(() => {
            expect(screen.getByRole('alert')).toBeInTheDocument();
        });
        expect(mockedSubmit).toHaveBeenCalledTimes(1);

        // Guard must reset after failure so a retry can go through.
        fireEvent.submit(gateForm());
        await waitFor(() => {
            expect(screen.getByText('Results Unlocked')).toBeInTheDocument();
        });
        expect(mockedSubmit).toHaveBeenCalledTimes(2);
    });
});
