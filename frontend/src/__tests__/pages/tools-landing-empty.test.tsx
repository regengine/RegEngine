import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ToolsLandingClient } from '@/app/tools/components/ToolsLandingClient';

/**
 * SEL-585 F5: when the active category yields zero tools, the landing
 * shows an empty state, never sample or fake tool cards.
 */

// Em dash or en dash, written as escapes so the source itself stays dash free.
const DASH = /[\u2014\u2013]/;

describe('tools landing empty state (SEL-585 F5)', () => {
    it('renders an empty state with no tool cards when a category has no tools', () => {
        render(<ToolsLandingClient />);

        // No tool in the curated list uses the Simulate category.
        fireEvent.click(screen.getByRole('button', { name: 'Simulate' }));

        const emptyState = screen.getByRole('status');
        expect(emptyState).toHaveTextContent(/no tools in this category/i);
        expect(emptyState.textContent).not.toMatch(DASH);
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('renders an empty state for the Operate category too', () => {
        render(<ToolsLandingClient />);

        fireEvent.click(screen.getByRole('button', { name: 'Operate' }));

        expect(screen.getByRole('status')).toHaveTextContent(/no tools in this category/i);
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('returns to the tool grid when a populated category is selected', () => {
        render(<ToolsLandingClient />);

        fireEvent.click(screen.getByRole('button', { name: 'Simulate' }));
        expect(screen.getByRole('status')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'All' }));
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
        expect(screen.getByText('FTL List Checker')).toBeInTheDocument();
    });
});
