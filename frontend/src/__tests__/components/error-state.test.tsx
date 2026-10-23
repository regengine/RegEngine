import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorState } from '@/components/ui/error-state';

describe('ErrorState', () => {
    it('keeps the callout style and shows retry progress with a caller class', () => {
        render(<ErrorState message="Could not load" onRetry={vi.fn()} retrying className="m-4" />);

        expect(screen.getByRole('alert')).toHaveClass('bg-re-danger-bg', 'm-4');
        expect(screen.getByRole('button', { name: 'Retrying…' })).toBeDisabled();
        expect(screen.getByText('Retrying…')).toBeInTheDocument();
    });
});
