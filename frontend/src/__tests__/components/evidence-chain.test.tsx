import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
    EvidenceChain,
    type EvidenceChainNode,
    type EvidenceChainProps,
} from '@/app/tools/inflow-lab/components/EvidenceChain';

const CTES = ['Harvesting', 'Cooling', 'Initial packing', 'Shipping', 'DC receiving'];

/** Mirrors `toLineage`: five slots, present events complete, the rest missing. */
function lineage(completeCount: number): EvidenceChainNode[] {
    return CTES.map((cte, index) => ({
        cte,
        location: index < completeCount ? `Facility ${index + 1}` : 'Not captured',
        time: index < completeCount ? `May 7, 2026, 10:0${index} AM` : 'Missing CTE',
        state: index < completeCount ? 'complete' : 'missing',
    }));
}

function renderChain(overrides: Partial<EvidenceChainProps> = {}) {
    const props: EvidenceChainProps = {
        nodes: lineage(3),
        hasData: true,
        isBlocked: true,
        isBusy: false,
        lot: { code: 'TLC-20260508-000022', product: 'Green Leaf Lettuce', supplier: 'Valley Fresh Farms', cases: 156 },
        missingEvidence: 'Shipping, DC receiving',
        patternLabel: 'Missing handoff evidence',
        fixPath: 'Map the missing handoff fields once, then re-run the lot group.',
        lotsAffected: 2,
        rowsRead: 11,
        lotCount: 3,
        runKey: 1,
        onRun: vi.fn(),
        onLoadSample: vi.fn(),
        onFocusDefect: null,
        ...overrides,
    };
    return { props, ...render(<EvidenceChain {...props} />) };
}

describe('EvidenceChain', () => {
    describe('with no data yet', () => {
        // `toLineage([])` returns five *missing* nodes. The chain must read that
        // as "not traced yet", never as five defects — the panel is not allowed
        // to invent a failure before an evaluation has run.
        const noData = { nodes: lineage(0), hasData: false, isBlocked: false, lot: null };

        it('holds the export gate open rather than reporting a block', () => {
            renderChain(noData);
            expect(screen.getByText('Awaiting trace')).toBeInTheDocument();
            expect(screen.queryByText('Blocked')).not.toBeInTheDocument();
        });

        it('does not invent a defect from an untraced chain', () => {
            renderChain(noData);
            expect(screen.queryByText(/records? never arrived/)).not.toBeInTheDocument();
            expect(screen.queryByText('Blocked now')).not.toBeInTheDocument();
            expect(screen.queryByText('no record received')).not.toBeInTheDocument();
            // Every CTE is announced as untraced, not as missing evidence.
            CTES.forEach((cte) => {
                expect(screen.getByText(cte).textContent).toContain('not yet traced');
            });
        });

        it('counts nothing as proven', () => {
            renderChain(noData);
            expect(screen.getByText('0/5')).toBeInTheDocument();
        });
    });

    describe('with a blocked lot', () => {
        it('names how many records are missing and what they were', () => {
            renderChain();
            expect(screen.getByText('2 records never arrived.')).toBeInTheDocument();
            expect(screen.getByText('Blocked')).toBeInTheDocument();
            expect(screen.getByText('Shipping, DC receiving')).toBeInTheDocument();
            expect(screen.getByText('Missing handoff evidence')).toBeInTheDocument();
        });

        it('singularises the heading for a single missing record', () => {
            renderChain({ nodes: lineage(4), missingEvidence: 'DC receiving' });
            expect(screen.getByText('One record never arrived.')).toBeInTheDocument();
        });

        it('reports proven links and the rows behind them', () => {
            renderChain();
            expect(screen.getByText('3/5')).toBeInTheDocument();
            expect(screen.getByText('11')).toBeInTheDocument();
        });

        it('marks the missing CTEs for assistive tech, not by colour alone', () => {
            renderChain();
            expect(screen.getByText('Shipping').textContent).toContain('missing');
            expect(screen.getByText('Harvesting').textContent).toContain('proven');
        });

        it('reports a shared pattern across lots', () => {
            renderChain({ lotsAffected: 2 });
            expect(screen.getByText('2 lots, same pattern')).toBeInTheDocument();
        });

        it('does not overstate the blast radius for a lone lot', () => {
            renderChain({ lotsAffected: 1 });
            expect(screen.getByText('This lot only')).toBeInTheDocument();
        });

        it('offers the defect jump only when there is a group to jump to', async () => {
            const onFocusDefect = vi.fn();
            const { unmount } = renderChain({ onFocusDefect });
            await userEvent.click(screen.getByRole('button', { name: 'Focus this defect' }));
            expect(onFocusDefect).toHaveBeenCalledOnce();
            unmount();

            renderChain({ onFocusDefect: null });
            expect(screen.queryByRole('button', { name: 'Focus this defect' })).not.toBeInTheDocument();
        });
    });

    describe('with a clean lot', () => {
        const clean = { nodes: lineage(5), isBlocked: false };

        it('clears the export gate and says so without hedging', () => {
            renderChain(clean);
            expect(screen.getByText('Preview-ready')).toBeInTheDocument();
            expect(screen.getByText('The chain closes end to end.')).toBeInTheDocument();
            expect(screen.getByText('5/5')).toBeInTheDocument();
        });

        it('reports no defect when there is none', () => {
            renderChain(clean);
            expect(screen.queryByText(/never arrived/)).not.toBeInTheDocument();
            expect(screen.queryByText('Blocked now')).not.toBeInTheDocument();
        });
    });

    describe('controls', () => {
        it('runs the trace and offers the sample', async () => {
            const onRun = vi.fn();
            const onLoadSample = vi.fn();
            renderChain({ onRun, onLoadSample });

            await userEvent.click(screen.getByRole('button', { name: /Run trace again/ }));
            expect(onRun).toHaveBeenCalledOnce();

            await userEvent.click(screen.getByRole('button', { name: 'Open sample in editor' }));
            expect(onLoadSample).toHaveBeenCalledOnce();
        });

        it('invites a first run before any data exists', () => {
            renderChain({ nodes: lineage(0), hasData: false, isBlocked: false, lot: null });
            expect(screen.getByRole('button', { name: /Run trace$/ })).toBeInTheDocument();
            expect(screen.getByText('Awaiting supplier rows')).toBeInTheDocument();
        });

        it('locks the run control while a trace is in flight', () => {
            renderChain({ isBusy: true });
            const chain = screen.getByTestId('inflow-evidence-chain');
            expect(within(chain).getByRole('button', { name: /Tracing/ })).toBeDisabled();
        });
    });
});
