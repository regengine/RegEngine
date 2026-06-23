import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { DashboardErrorBoundary } from '@/components/dashboard/error-boundary';

function ThrowSensitiveError(): ReactNode {
    throw new Error('Database password leaked in stack details');
}

describe('DashboardErrorBoundary', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const preventExpectedErrorLog = (event: ErrorEvent) => {
        if (event.message.includes('Database password leaked in stack details')) {
            event.preventDefault();
        }
    };

    beforeEach(() => {
        consoleError.mockClear();
        window.addEventListener('error', preventExpectedErrorLog);
    });

    afterEach(() => {
        consoleError.mockClear();
        window.removeEventListener('error', preventExpectedErrorLog);
    });

    it('shows a user-friendly recovery message without leaking raw error text', () => {
        render(
            <DashboardErrorBoundary>
                <ThrowSensitiveError />
            </DashboardErrorBoundary>,
        );

        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        expect(screen.getByText(/unexpected error occurred while rendering this page/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /reload page/i })).toBeInTheDocument();
        expect(screen.queryByText(/database password leaked/i)).not.toBeInTheDocument();
    });
});
