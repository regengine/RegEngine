import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import DocsHomePage from '@/app/docs/page';

describe('docs index API contract copy', () => {
  it('keeps the first ingest call aligned with the backend webhook route and key prefix', () => {
    render(<DocsHomePage />);

    const pageText = document.body.textContent ?? '';

    expect(screen.getAllByText(/\/webhooks\/ingest/).length).toBeGreaterThan(0);
    expect(pageText).toContain('rge_live_');
    expect(pageText).not.toMatch(/\/records\/ingest(?!ion-runs)/);
    expect(pageText).not.toContain('re_live_');
    expect(pageText).not.toContain('rge_prod_');
    expect(pageText).not.toContain('rge_dev_');
  });
});
