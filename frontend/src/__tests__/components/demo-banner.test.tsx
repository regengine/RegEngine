/**
 * DemoBanner Component Tests
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DemoBanner } from '@/components/control-plane/demo-banner';

describe('DemoBanner Component', () => {
    it('renders when visible=true', () => {
        render(<DemoBanner visible={true} />);
        expect(screen.getByText('No data yet')).toBeInTheDocument();
    });

    it('shows the empty-state text and a next-step link', () => {
        render(<DemoBanner visible={true} />);
        expect(screen.getByText('No data yet')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /connect real data/i })).toHaveAttribute('href', '/ingest');
    });

    it('does not render when visible=false', () => {
        const { container } = render(<DemoBanner visible={false} />);
        expect(container.firstChild).toBeNull();
    });
});
