import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TransformationProofPage from '@/app/proof/transformation/page';

describe('transformation proof without supplier records', () => {
    it('shows an empty state without invented evidence', () => {
        const { container } = render(<TransformationProofPage />);

        expect(screen.getByText(/No data yet/)).toBeInTheDocument();
        expect(container.querySelector('table')).toBeNull();
        expect(container.querySelector('a[download]')).toBeNull();
    });
});
