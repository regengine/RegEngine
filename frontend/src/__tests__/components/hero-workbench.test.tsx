import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HeroWorkbench } from '@/components/marketing/HeroWorkbench';
import { gapIndex, scenarios } from '@/lib/demo-workspace/model';

vi.mock('@/lib/conversion-events', () => ({
  trackScenarioTab: vi.fn(),
  trackRowClick: vi.fn(),
  trackSendCorrectionLink: vi.fn(),
  trackResetDemo: vi.fn(),
  trackToggleRows: vi.fn(),
  trackBookCallClick: vi.fn(),
}));

import * as events from '@/lib/conversion-events';

const first = scenarios()[0];

function gapRow() {
  return screen.getByText('missing').closest('tr') as HTMLTableRowElement;
}

describe('HeroWorkbench', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows four rows around the gap and a guided caption until a row is clicked', () => {
    render(<HeroWorkbench />);
    expect(screen.getAllByRole('row')).toHaveLength(5); // header + 4
    expect(screen.getByText(/one record is missing a required field/i)).toBeInTheDocument();
    expect(screen.getByText(/show \d+ more records? in this chain/i)).toBeInTheDocument();

    fireEvent.click(gapRow());
    expect(screen.queryByText(/one record is missing a required field/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send correction link to supplier/i })).toBeInTheDocument();
    expect(events.trackRowClick).toHaveBeenCalledWith('landing', first.id, first.chain[gapIndex(first)].cte, true);
  });

  it('commits the record when the correction link is sent and restores it on reset', () => {
    render(<HeroWorkbench />);
    expect(screen.getByText(/of \d+ ready/i)).toBeInTheDocument();

    // The status strip names the file the Export view downloads for this chain.
    expect(screen.getByText(`fda_sortable_${first.id}.csv`)).toBeInTheDocument();
    // Each food tab controls the labelled panel that holds the records.
    const panel = screen.getByRole('tabpanel');
    expect(screen.getAllByRole('tab')[0]).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', screen.getAllByRole('tab')[0].id);

    const gapButton = within(gapRow()).getByRole('button');
    expect(gapButton).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(gapButton);
    expect(within(gapRow()).getByRole('button')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: /send correction link to supplier/i }));

    expect(screen.getByText(/supplier corrected the record/i)).toBeInTheDocument();
    expect(screen.getByText('Ready to export')).toBeInTheDocument();
    expect(screen.getByText('Corrected')).toBeInTheDocument();
    expect(screen.queryByText('missing')).not.toBeInTheDocument();
    const correctedRow = screen.getByText('Corrected').closest('tr') as HTMLTableRowElement;
    expect(correctedRow).toHaveTextContent(first.lot);
    expect(events.trackSendCorrectionLink).toHaveBeenCalledWith('landing', first.id, first.chain[gapIndex(first)].cte);

    fireEvent.click(screen.getByRole('button', { name: /reset demo/i }));
    expect(screen.getByText('missing')).toBeInTheDocument();
    expect(screen.queryByText('Ready to export')).not.toBeInTheDocument();
    expect(events.trackResetDemo).toHaveBeenCalledWith('landing', first.id);
  });

  it('expands to the whole chain and switches chains from the food tabs', () => {
    render(<HeroWorkbench />);
    fireEvent.click(screen.getByText(/show \d+ more records? in this chain/i));
    expect(screen.getAllByRole('row')).toHaveLength(first.chain.length + 1);
    expect(screen.getByText(/show fewer records/i)).toBeInTheDocument();
    expect(events.trackToggleRows).toHaveBeenCalledWith('landing', first.id);

    const tabs = screen.getAllByRole('tab');
    fireEvent.click(tabs[2]);
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true');
    expect(events.trackScenarioTab).toHaveBeenCalledWith('landing', scenarios()[2].id);
    // switching chains collapses the table again
    expect(screen.getAllByRole('row')).toHaveLength(5);
  });
});
