import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FTLCheckerClient } from '@/app/tools/ftl-checker/components/FTLCheckerClient';
import { ToolsLandingClient } from '@/app/tools/components/ToolsLandingClient';

vi.mock('framer-motion', () => ({
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    motion: {
        div: ({ children, className }: { children?: ReactNode; className?: string }) => (
            <div className={className}>{children}</div>
        ),
    },
}));

const ENFORCEMENT_LINE = "FDA won't enforce before July 20, 2028";

function cardText(name: string): string {
    const label = screen.getByText(name);
    const card = label.closest('button');
    if (!card) {
        throw new Error(`No category card for ${name}`);
    }
    return card.textContent ?? '';
}

describe('FTL tools accuracy against the FDA Food Traceability List', () => {
    it('says FDA will not enforce before July 20, 2028 on the tools hub', () => {
        render(<ToolsLandingClient />);

        expect(screen.getByText(/FDA won't enforce before July 20, 2028/)).toBeInTheDocument();
        expect(screen.queryByText(/compliance date is July 20, 2028/i)).not.toBeInTheDocument();
    });

    it('uses the same enforcement wording on the FTL checker', () => {
        render(<FTLCheckerClient />);

        expect(screen.getByText(ENFORCEMENT_LINE)).toBeInTheDocument();
        expect(screen.queryByText(/FDA date:/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/compliance date is July 20, 2028/i)).not.toBeInTheDocument();
    });

    it('does not list collards as covered leafy greens', () => {
        render(<FTLCheckerClient />);

        const leafy = cardText('Leafy Greens (fresh, intact)');
        expect(leafy).not.toMatch(/collard greens/i);
        expect(leafy).toMatch(/collards, are exempt/i);
    });

    it('lists swordfish with histamine-producing finfish', () => {
        render(<FTLCheckerClient />);

        const histamine = cardText('Finfish, histamine-producing species');
        const other = cardText('Finfish, species not associated with histamine or ciguatoxin');

        expect(histamine.toLowerCase()).toContain('swordfish');
        expect(other.toLowerCase()).not.toContain('swordfish');
        expect(screen.queryByText(/Finfish\s*[\u2014\u2013]\s/)).not.toBeInTheDocument();
    });

    it('notes that the scallop adductor muscle alone is excluded', () => {
        render(<FTLCheckerClient />);

        const bivalves = cardText('Molluscan Shellfish (bivalves)');
        expect(bivalves).toMatch(/scallop adductor muscle alone is excluded/i);
    });

    it('does not add a laying-hen farm size to shell eggs', () => {
        render(<FTLCheckerClient />);

        const eggs = cardText('Shell Eggs');
        expect(eggs).not.toMatch(/3,000|3000|laying hens/i);
        expect(eggs).not.toMatch(/[\u2014\u2013]/);
        expect(eggs).toMatch(/domesticated chicken/i);
    });
});
