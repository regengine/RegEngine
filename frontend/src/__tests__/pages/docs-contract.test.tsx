import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import AlphaRedirect from '@/app/alpha/page';
import DevelopersPage from '@/app/developers/page';
import DocsHomePage from '@/app/docs/page';
import AuthenticationDocsPage from '@/app/docs/authentication/page';
import InflowLabConnectorPage from '@/app/docs/connectors/inflow-lab/page';
import ErrorCodesPage from '@/app/docs/errors/page';
import FSMA204GuidePage from '@/app/docs/fsma-204/page';
import QuickstartPage from '@/app/docs/quickstart/page';
import RateLimitsDocsPage from '@/app/docs/rate-limits/page';
import SDKsDocsPage, { metadata as sdksMetadata } from '@/app/docs/sdks/page';
import WalkthroughPage from '@/app/docs/walkthrough/page';
import WebhooksDocsPage, { metadata as webhooksMetadata } from '@/app/docs/webhooks/page';
import { ApiReferenceClient } from '@/app/docs/api/ApiReferenceClient';
import ingestReceiving from '@/lib/api-samples/ingest-receiving.json';
import {
  INGEST_CURL_SAMPLE,
  INGEST_JS_SAMPLE,
  INGEST_PYTHON_SAMPLE,
} from '@/lib/api-samples/ingest-samples';
import { publicOpenApiSpec } from '@/lib/public-openapi';

const redirect = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  redirect,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

const FORBIDDEN_PREFIXES = ['re_live_', 'rge_prod_', 'rge_dev_', 'rge_test_'];

// The host that has no DNS. Spelled in parts so scripts/check_api_host_strings.py,
// which scans this directory for the literal, does not flag the test that guards it.
const DEAD_API_HOST = ['api', 'regengine', 'co'].join('.');

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
  it('authentication doc uses only rge_live_', () => {
    render(<AuthenticationDocsPage />);
    const pageText = document.body.textContent ?? '';
    expect(pageText).toContain('rge_live_');
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

/**
 * Pages whose copy and code samples must be true against the backend. Each one
 * is rendered and the visible text plus links are checked.
 */
const DEVELOPER_PAGES: [string, () => ReactElement][] = [
  ['docs index', () => <DocsHomePage />],
  ['quickstart', () => <QuickstartPage />],
  ['authentication', () => <AuthenticationDocsPage />],
  ['errors', () => <ErrorCodesPage />],
  ['rate limits', () => <RateLimitsDocsPage />],
  ['webhooks', () => <WebhooksDocsPage />],
  ['sdks', () => <SDKsDocsPage />],
  ['developers', () => <DevelopersPage />],
  ['FSMA 204 guide', () => <FSMA204GuidePage />],
  ['walkthrough', () => <WalkthroughPage />],
  ['Inflow Lab connector', () => <InflowLabConnectorPage />],
];

/** Pages that show a full ingest call. Each must render it from src/lib/api-samples, never carry its own payload. */
const INGEST_CALL_PAGES: [string, () => ReactElement][] = [
  ['quickstart', () => <QuickstartPage />],
  ['FSMA 204 guide', () => <FSMA204GuidePage />],
  ['walkthrough', () => <WalkthroughPage />],
  ['Inflow Lab connector', () => <InflowLabConnectorPage />],
];

/** The API reference hides endpoint detail until a card is opened. */
function renderApiReferenceWithIngestOpen() {
  render(<ApiReferenceClient />);
  fireEvent.click(screen.getByText('/ingest'));
}

describe('developer docs stay true against the backend', () => {
  it.each(DEVELOPER_PAGES)('%s: no /alpha link, no dead API host, no placeholder tenant, no self-serve key link', (_name, page) => {
    render(page());

    const pageText = document.body.textContent ?? '';
    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));

    expect(hrefs).not.toContain('/alpha');
    expect(hrefs).not.toContain('/api-keys');
    expect(pageText).not.toContain(DEAD_API_HOST);
    expect(pageText).not.toContain('11111111-1111-1111-1111-111111111111');
    for (const bad of FORBIDDEN_PREFIXES) {
      expect(pageText).not.toContain(bad);
    }
  });

  it.each(DEVELOPER_PAGES)('%s: no sample sends X-Tenant-ID or a fixed event timestamp', (_name, page) => {
    render(page());

    const pageText = document.body.textContent ?? '';

    expect(pageText).not.toMatch(/-H "X-Tenant-ID/);
    expect(pageText).not.toMatch(/"X-Tenant-ID"\s*:/);
    // An ingest sample must build its timestamp from the clock: a fixed date
    // goes stale after 90 days and the backend rejects the event.
    expect(pageText).not.toMatch(/"timestamp":\s*"\d{4}-\d{2}-\d{2}/);
    expect(pageText).not.toMatch(/\btimestamp:\s*"\d{4}-\d{2}-\d{2}/);
    // The same goes for the date KDEs (receive_date, ship_date, ...) in a payload.
    expect(pageText).not.toMatch(/"\w+_date":\s*"\d{4}-\d{2}-\d{2}"/);
  });

  it.each(INGEST_CALL_PAGES)('%s: the ingest call is the shared signed sample, not a hand-written payload', (_name, page) => {
    render(page());

    const pageText = document.body.textContent ?? '';

    expect(pageText).toContain('X-Webhook-Signature');
    expect(pageText).toContain('openssl dgst -sha256 -hmac');
    expect(pageText).toContain('--data-binary');
    expect(pageText).toContain('Idempotency-Key: $(uuidgen)');
    expect(pageText).toContain('"timestamp": "$NOW"');
    // The unsigned samples sent their payload with an inline -d '{...}'.
    expect(pageText).not.toMatch(/-d '\{/);
    // A created lot is permanent: every lot code in a sample carries the TEST- prefix.
    const lots = Array.from(pageText.matchAll(/"traceability_lot_code":\s*"([^"]+)"/g)).map((m) => m[1]);
    expect(lots.length).toBeGreaterThan(0);
    for (const lot of lots) {
      expect(lot.startsWith('TEST-'), lot).toBe(true);
    }
  });

  it('API reference: ingest is signed, has no X-Tenant-ID, and carries no fixed timestamp', () => {
    renderApiReferenceWithIngestOpen();

    const pageText = document.body.textContent ?? '';

    expect(pageText).toContain('X-Webhook-Signature');
    expect(pageText).not.toContain('X-Tenant-ID: tenant_uuid');
    expect(pageText).not.toMatch(/"timestamp":\s*"\d{4}-\d{2}-\d{2}/);
    expect(pageText).not.toContain(DEAD_API_HOST);
    expect(pageText).not.toContain('11111111-1111-1111-1111-111111111111');
    for (const bad of FORBIDDEN_PREFIXES) {
      expect(pageText).not.toContain(bad);
    }
  });

  it('API reference: lists no endpoint the backend does not serve', () => {
    render(<ApiReferenceClient />);
    expect(screen.queryByText('/health')).not.toBeInTheDocument();

    // The records section must not offer the removed /evaluations route.
    fireEvent.click(screen.getByRole('button', { name: /Records API/ }));
    expect(screen.queryByText('/{event_id}/evaluations')).not.toBeInTheDocument();
    expect(screen.getByText('/{event_id}/history')).toBeInTheDocument();
  });

  it('public OpenAPI example values carry no placeholder tenant id', () => {
    expect(JSON.stringify(publicOpenApiSpec)).not.toContain('11111111-1111-1111-1111-111111111111');
  });

  it('SDKs and webhooks pages say planned, not available', () => {
    expect(String(sdksMetadata.description)).toMatch(/planned/i);
    expect(String(sdksMetadata.description)).not.toMatch(/^Official/i);
    expect(String(webhooksMetadata.title)).toMatch(/planned/i);

    render(<WebhooksDocsPage />);
    expect(screen.getByRole('heading', { level: 1, name: /Outbound webhooks \(planned\)/i })).toBeInTheDocument();
    expect(document.querySelector('a[href="/docs/quickstart"]')).not.toBeNull();
  });

  it('request-access calls to action go to /contact', () => {
    render(<QuickstartPage />);
    expect(document.querySelector('a[href="/contact"]')).not.toBeNull();
  });

  it('/alpha redirects to /contact', () => {
    redirect.mockClear();
    AlphaRedirect();
    expect(redirect).toHaveBeenCalledWith('/contact');
  });
});

describe('shared ingest sample', () => {
  it('keeps placeholders in the JSON and a TEST- lot code (writes are permanent and billed)', () => {
    const raw = JSON.stringify(ingestReceiving);

    expect(raw).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(raw).toContain('{{EVENT_TIMESTAMP}}');
    expect(raw).toContain('{{EVENT_DATE}}');
    for (const event of ingestReceiving.events) {
      expect(event.traceability_lot_code.startsWith('TEST-')).toBe(true);
    }
  });

  it('renders every language from the same payload with a clock-derived timestamp', () => {
    const lot = ingestReceiving.events[0].traceability_lot_code;

    for (const sample of [INGEST_CURL_SAMPLE, INGEST_PYTHON_SAMPLE, INGEST_JS_SAMPLE]) {
      expect(sample).toContain(lot);
      expect(sample).not.toContain('{{');
      expect(sample).toContain('X-Webhook-Signature');
      expect(sample).toContain('Idempotency-Key');
      expect(sample).not.toMatch(/X-Tenant-ID/);
      expect(sample).not.toMatch(/"timestamp":\s*"\d{4}-\d{2}-\d{2}/);
    }

    expect(INGEST_CURL_SAMPLE).toContain('"timestamp": "$NOW"');
    expect(INGEST_CURL_SAMPLE).toContain('--data-binary');
    expect(INGEST_CURL_SAMPLE).toContain('openssl dgst -sha256 -hmac');
    expect(INGEST_PYTHON_SAMPLE).toContain('"timestamp": now.strftime');
    expect(INGEST_PYTHON_SAMPLE).toContain('hmac.new(');
    expect(INGEST_JS_SAMPLE).toContain('"timestamp": now');
    expect(INGEST_JS_SAMPLE).toContain('createHmac("sha256"');
  });

  it('quickstart signs and sends the same bytes, and warns that writes are permanent', () => {
    render(<QuickstartPage />);
    const pageText = document.body.textContent ?? '';

    expect(pageText).toContain('X-Webhook-Signature');
    expect(pageText).toContain('--data-binary');
    expect(pageText).toMatch(/permanent/i);
    expect(pageText).toContain('TEST-');
    expect(pageText).toMatch(/Idempotency-Key/);
    expect(pageText).toContain('/records?limit=1');
  });
});
