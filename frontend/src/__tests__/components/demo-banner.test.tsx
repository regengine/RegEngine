/**
 * DemoBanner Component Tests
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DemoBanner } from '@/components/control-plane/demo-banner';

describe('DemoBanner Component', () => {
    it('renders when visible=true', () => {
        render(<DemoBanner visible={true} />);
        expect(screen.getByText('Sample Data')).toBeInTheDocument();
    });

    it('shows "Sample Data" text and description', () => {
        render(<DemoBanner visible={true} />);
        expect(screen.getByText('Sample Data')).toBeInTheDocument();
        expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    });

    it('does not render when visible=false', () => {
        const { container } = render(<DemoBanner visible={false} />);
        expect(container.firstChild).toBeNull();
    });
});
