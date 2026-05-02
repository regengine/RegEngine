import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type React from 'react';
import FSMAChecklist from '@/components/fsma-checklist';
import { submitAssessment } from '@/app/actions/submit-assessment';

vi.mock('next/link', () => ({
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/app/actions/submit-assessment', () => ({
    submitAssessment: vi.fn(),
}));

const mockedSubmitAssessment = vi.mocked(submitAssessment);
let storage: Record<string, string>;

function installLocalStorageMock() {
    storage = {};
    Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
            getItem: vi.fn((key: string) => storage[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                storage[key] = String(value);
            }),
            removeItem: vi.fn((key: string) => {
                delete storage[key];
            }),
            clear: vi.fn(() => {
                storage = {};
            }),
        },
    });
}

describe('FSMAChecklist PII storage', () => {
    beforeEach(() => {
        installLocalStorageMock();
        mockedSubmitAssessment.mockReset();
    });

    it('submits gap analysis to the server action without persisting lead PII', async () => {
        mockedSubmitAssessment.mockResolvedValue({ success: true });
        const user = userEvent.setup();

        render(<FSMAChecklist />);

        await user.click(screen.getByRole('button', { name: /Harvest CTEs captured/i }));
        await user.click(screen.getByRole('button', { name: /See My Results/i }));
        await user.type(screen.getByPlaceholderText(/Company name/i), 'Acme Foods');
        await user.type(screen.getByPlaceholderText(/Work email/i), 'lead@example.com');
        await user.click(screen.getByRole('button', { name: /Get Free Gap Analysis/i }));

        await waitFor(() => expect(mockedSubmitAssessment).toHaveBeenCalledTimes(1));
        expect(mockedSubmitAssessment).toHaveBeenCalledWith(expect.objectContaining({
            email: 'lead@example.com',
            company: 'Acme Foods',
            source: 'fsma-checklist',
        }));

        expect(window.localStorage.getItem('fsma_gap_analysis_lead')).toBeNull();
        expect(JSON.stringify(storage)).not.toContain('lead@example.com');
        expect(JSON.stringify(storage)).not.toContain('Acme Foods');
        expect(window.localStorage.getItem('fsma_gap_analysis_submitted')).toBe('1');
    });

    it('stores only non-PII retry state when submission fails', async () => {
        mockedSubmitAssessment.mockResolvedValue({ success: false, error: 'Try again.' });
        const user = userEvent.setup();

        render(<FSMAChecklist />);

        await user.click(screen.getByRole('button', { name: /Harvest CTEs captured/i }));
        await user.click(screen.getByRole('button', { name: /See My Results/i }));
        await user.type(screen.getByPlaceholderText(/Company name/i), 'Acme Foods');
        await user.type(screen.getByPlaceholderText(/Work email/i), 'lead@example.com');
        await user.click(screen.getByRole('button', { name: /Get Free Gap Analysis/i }));

        expect(await screen.findByRole('alert')).toHaveTextContent('Try again.');

        const retry = window.localStorage.getItem('fsma_gap_analysis_retry') || '';
        expect(window.localStorage.getItem('fsma_gap_analysis_lead')).toBeNull();
        expect(retry).toContain('"pending":true');
        expect(retry).not.toContain('lead@example.com');
        expect(retry).not.toContain('Acme Foods');
    });
});
