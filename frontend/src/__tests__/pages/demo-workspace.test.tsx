import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DemoWorkspacePage from '@/app/demo/page';
import { metadata } from '@/app/demo/layout';
import { scenarios } from '@/lib/demo-workspace/model';

vi.mock('@/lib/conversion-events', () => ({
  trackScenarioTab: vi.fn(),
  trackRowClick: vi.fn(),
  trackSendCorrectionLink: vi.fn(),
  trackResetDemo: vi.fn(),
  trackToggleRows: vi.fn(),
  trackBookCallClick: vi.fn(),
}));

const all = scenarios();

function nav() {
  return within(screen.getByRole('navigation', { name: /demo workspace/i }));
}

describe('/demo public workspace', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/demo');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('declares its own metadata and open graph card', () => {
    expect(metadata.title).toMatch(/demo workspace/i);
    expect(metadata.alternates?.canonical).toBe('/demo');
    const og = metadata.openGraph as { url?: string; images?: unknown[] };
    expect(og.url).toBe('https://regengine.co/demo');
    expect(og.images).toHaveLength(1);
  });

  it('opens on the overview with every chain needing one fix', () => {
    render(<DemoWorkspacePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Open fixes').nextElementSibling).toHaveTextContent('5');
    expect(nav().getByRole('button', { name: /fix queue/i })).toHaveTextContent('5');
    expect(screen.getAllByText('Needs correction')).toHaveLength(all.length);
    expect(screen.getByText(/demo workspace\./i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /book a 30-min call/i })).toHaveAttribute('href', '/contact');
  });

  it('switches views from the sidebar and mirrors the view to the location hash', () => {
    render(<DemoWorkspacePage />);
    fireEvent.click(nav().getByRole('button', { name: /ledger/i }));
    expect(screen.getByRole('heading', { level: 1, name: 'Evidence ledger' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#ledger');
    const total = all.reduce((sum, s) => sum + s.chain.length, 0);
    expect(screen.getByText(`${total - all.length} entries · chain verified`)).toBeInTheDocument();
  });

  it('jumps from an attention row to the import view with that record selected', () => {
    render(<DemoWorkspacePage />);
    const rows = screen.getAllByRole('row').filter((row) => within(row).queryByText('Needs correction'));
    fireEvent.keyDown(rows[1], { key: 'Enter' });
    expect(screen.getByRole('heading', { level: 1, name: /import/i })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')[1]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('button', { name: /send correction link to supplier/i })).toBeInTheDocument();
  });

  it('decrements the fix count and clears the attention row once a correction link is sent', () => {
    render(<DemoWorkspacePage />);
    fireEvent.click(nav().getByRole('button', { name: /fix queue/i }));
    const sendButtons = screen.getAllByRole('button', { name: /^send correction link$/i });
    expect(sendButtons).toHaveLength(all.length);
    fireEvent.click(sendButtons[0]);
    expect(screen.getByText('✓ Committed')).toBeInTheDocument();
    expect(nav().getByRole('button', { name: /fix queue/i })).toHaveTextContent('4');

    fireEvent.click(nav().getByRole('button', { name: /overview/i }));
    expect(screen.getAllByText('Needs correction')).toHaveLength(all.length - 1);
    expect(screen.getByText('Open fixes').nextElementSibling).toHaveTextContent('4');

    fireEvent.click(screen.getByRole('button', { name: /reset demo/i }));
    expect(screen.getAllByText('Needs correction')).toHaveLength(all.length);
  });

  it('shows the all-clear state when every chain is fixed', () => {
    render(<DemoWorkspacePage />);
    fireEvent.click(nav().getByRole('button', { name: /fix queue/i }));
    for (const button of screen.getAllByRole('button', { name: /^send correction link$/i })) fireEvent.click(button);
    fireEvent.click(nav().getByRole('button', { name: /overview/i }));
    expect(screen.getByText(/nothing needs attention/i)).toBeInTheDocument();
    expect(nav().getByRole('button', { name: /fix queue/i })).not.toHaveTextContent(/\d/);
  });

  it('hands the visitor a CSV from the export view', () => {
    const createObjectURL = vi.fn((_blob: Blob) => 'blob:demo');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(<DemoWorkspacePage />);
    fireEvent.click(screen.getByRole('button', { name: /export packages/i }));
    expect(screen.getByRole('heading', { level: 1, name: 'Export packages' })).toBeInTheDocument();
    expect(screen.getAllByText(`${all[0].chain.length - 1} OF ${all[0].chain.length} READY`).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole('button', { name: /download csv/i })[0]);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe('text/csv');
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});
