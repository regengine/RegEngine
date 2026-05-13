import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import DocsHomePage from '@/app/docs/page';
import AuthenticationDocsPage from '@/app/docs/authentication/page';
import InflowLabConnectorPage from '@/app/docs/connectors/inflow-lab/page';

const FORBIDDEN_PREFIXES = ['re_live_', 'rge_prod_', 'rge_dev_'];

describe('docs index API contract copy', () => {
  it('keeps the first ingest call aligned with the backend webhook route and key prefix', () => {
    render(<DocsHomePage />);

    const pageText = document.body.textContent ?? '';

    expect(screen.getAllByText(/\/webhooks\/ingest/).length).toBeGreaterThan(0);
    expect(pageText).toContain('rge_live_');
    expect(pageText).not.toMatch(/\/records\/ingest(?!ion-runs)/);
    for (const bad of FORBIDDEN_PREFIXES) {
      expect(pageText).not.toContain(bad);
    }
  });
});

describe('docs API key prefix is unified across surfaces (issue #2309)', () => {
  it('authentication doc uses only rge_live_/rge_test_', () => {
    render(<AuthenticationDocsPage />);
    const pageText = document.body.textContent ?? '';
    expect(pageText).toContain('rge_live_');
    expect(pageText).toContain('rge_test_');
    for (const bad of FORBIDDEN_PREFIXES) {
      expect(pageText).not.toContain(bad);
    }
  });

  it('inflow-lab connector doc uses only rge_live_', () => {
    render(<InflowLabConnectorPage />);
    const pageText = document.body.textContent ?? '';
    expect(pageText).toContain('rge_live_');
    for (const bad of FORBIDDEN_PREFIXES) {
      expect(pageText).not.toContain(bad);
    }
  });
});
