import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

// Minimal EPCIS 2.0 request body for exercising the upload path in tests.
const epcisDocument = {
  '@context': ['https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld'],
  type: 'EPCISDocument',
  schemaVersion: '2.0',
  epcisBody: {
    eventList: [
      { type: 'ObjectEvent', action: 'OBSERVE', bizStep: 'shipping', eventTime: '2026-01-01T00:00:00Z', eventTimeZoneOffset: '+00:00' },
      { type: 'ObjectEvent', action: 'OBSERVE', bizStep: 'receiving', eventTime: '2026-01-02T00:00:00Z', eventTimeZoneOffset: '+00:00' },
    ],
  },
};

const mocks = vi.hoisted(() => ({
  ingestURL: vi.fn(),
  ingestFile: vi.fn(),
  ingestEpcisEvent: vi.fn(),
  ingestEpcisBatch: vi.fn(),
  ingestEpcisXml: vi.fn(),
  validateEpcis: vi.fn(),
  getIngestionJob: vi.fn(),
  refresh: vi.fn(),
  storeApiKey: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: mocks.storeApiKey }), // pragma: allowlist secret
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({ mutateAsync: mocks.ingestURL, reset: vi.fn(), isPending: false, isError: false }),
  useIngestFile: () => ({ mutateAsync: mocks.ingestFile, reset: vi.fn(), isPending: false, isError: false }),
  useIngestEpcisEvent: () => ({ mutateAsync: mocks.ingestEpcisEvent, reset: vi.fn(), isPending: false }),
  useIngestEpcisBatch: () => ({ mutateAsync: mocks.ingestEpcisBatch, reset: vi.fn(), isPending: false }),
  useIngestEpcisXml: () => ({ mutateAsync: mocks.ingestEpcisXml, reset: vi.fn(), isPending: false }),
  useValidateEpcisEvent: () => ({ mutateAsync: mocks.validateEpcis, reset: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/api-client', () => ({
  apiClient: { getIngestionJob: mocks.getIngestionJob },
}));
vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: mocks.refresh,
}));
vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
  NormalizedDocumentViewer: () => <div>Normalized document viewer</div>,
}));

const SINGLE_EVENT = {
  type: 'ObjectEvent',
  eventTime: '2026-03-01T06:00:00Z',
  eventTimeZoneOffset: '-08:00',
  action: 'OBSERVE',
  bizStep: 'urn:epcglobal:cbv:bizstep:harvesting',
};

const EPCIS_XML = `<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-03-01T06:00:00Z</eventTime>
        <action>OBSERVE</action>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>`;

async function openEpcisTab() {
  render(<IngestPage />);
  await userEvent.click(screen.getByRole('tab', { name: /epcis 2\.0/i }));
}

function uploadEpcisFile(name: string, contents: string, type: string) {
  const input = document.getElementById('epcis-file-upload') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File([contents], name, { type })] },
  });
}

describe('EPCIS 2.0 import on /ingest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('offers an EPCIS 2.0 tab with a JSON/XML chooser and no sample file link', async () => {
    await openEpcisTab();
    expect(screen.getByText('CSV uploads skip bad rows. EPCIS files are all or nothing: if any event fails, nothing is saved.')).toBeInTheDocument();
    expect(document.getElementById('epcis-file-upload')).toHaveAttribute(
      'accept',
      '.json,application/json,.xml,application/xml,text/xml',
    );
    expect(screen.getByText('JSON or XML files up to 5MB')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /download a sample epcis file/i })).not.toBeInTheDocument();
  });

  it('sends an EPCIS JSON document to the batch endpoint once with all events', async () => {
    const eventList = (epcisDocument as { epcisBody: { eventList: unknown[] } }).epcisBody.eventList;
    expect(eventList.length).toBeGreaterThan(1);
    mocks.ingestEpcisBatch.mockResolvedValue({
      total: eventList.length,
      created: eventList.length,
      failed: 0,
      results: [],
      errors: [],
      mode: 'partial',
    });

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(epcisDocument), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(mocks.ingestEpcisBatch).toHaveBeenCalledTimes(1);
    expect(mocks.ingestEpcisBatch).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      events: eventList,
    });
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(mocks.validateEpcis).not.toHaveBeenCalled();
    expect(await screen.findByText('EPCIS processed')).toBeInTheDocument();
    expect(
      screen.getByText(`${eventList.length} of ${eventList.length} events accepted; 0 rejected.`),
    ).toBeInTheDocument();
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it('sends a bare JSON array of events to the batch endpoint', async () => {
    const events = [SINGLE_EVENT, { ...SINGLE_EVENT, eventTime: '2026-03-01T08:00:00Z' }];
    mocks.ingestEpcisBatch.mockResolvedValue({
      total: 2,
      created: 1,
      failed: 1,
      results: [{ index: 1, status_code: 400, detail: 'Missing bizLocation' }],
      errors: [{ index: 1, detail: 'Missing bizLocation' }],
      mode: 'partial',
    });

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(events), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(mocks.ingestEpcisBatch).toHaveBeenCalledTimes(1);
    expect(mocks.ingestEpcisBatch).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      events,
    });
    expect(await screen.findByText('EPCIS partially accepted')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 events accepted; 1 rejected.')).toBeInTheDocument();
    expect(screen.getByText('Event 2: Missing bizLocation')).toBeInTheDocument();
  });

  it('sends a single-event JSON to the single-event endpoint', async () => {
    mocks.ingestEpcisEvent.mockResolvedValue({ status: 201 });

    await openEpcisTab();
    uploadEpcisFile('event.json', JSON.stringify(SINGLE_EVENT), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(mocks.ingestEpcisEvent).toHaveBeenCalledTimes(1);
    expect(mocks.ingestEpcisEvent).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      event: SINGLE_EVENT,
    });
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(await screen.findByText('EPCIS processed')).toBeInTheDocument();
    expect(screen.getByText('1 of 1 events accepted; 0 rejected.')).toBeInTheDocument();
  });

  it('sends an XML file to the XML endpoint untouched', async () => {
    mocks.ingestEpcisXml.mockResolvedValue({
      total: 1,
      created: 1,
      failed: 0,
      results: [],
      errors: [],
      format: 'EPCIS_XML_2.0',
      mode: 'partial',
    });

    await openEpcisTab();
    uploadEpcisFile('events.xml', EPCIS_XML, 'application/xml');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(mocks.ingestEpcisXml).toHaveBeenCalledTimes(1);
    expect(mocks.ingestEpcisXml).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      xml: EPCIS_XML,
    });
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(await screen.findByText('EPCIS processed')).toBeInTheDocument();
  });

  it('validate-only calls the validate endpoint and never ingests', async () => {
    mocks.validateEpcis.mockResolvedValue({ valid: true, errors: [], normalized_cte: null });

    await openEpcisTab();
    uploadEpcisFile('event.json', JSON.stringify(SINGLE_EVENT), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /^validate only$/i }));

    expect(mocks.validateEpcis).toHaveBeenCalledTimes(1);
    expect(mocks.validateEpcis).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      event: SINGLE_EVENT,
    });
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
    expect(await screen.findByText('All events valid')).toBeInTheDocument();
    expect(screen.getByText('1 of 1 events valid.')).toBeInTheDocument();
  });

  it('validate-only reports per-event failures for a batch document', async () => {
    const events = [SINGLE_EVENT, { ...SINGLE_EVENT, eventTime: '2026-03-01T08:00:00Z' }];
    mocks.validateEpcis
      .mockResolvedValueOnce({ valid: true, errors: [], normalized_cte: null })
      .mockResolvedValueOnce({ valid: false, errors: ['Missing bizLocation'], normalized_cte: null });

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(events), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /^validate only$/i }));

    expect(mocks.validateEpcis).toHaveBeenCalledTimes(2);
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(await screen.findByText('Validation found issues')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 events valid.')).toBeInTheDocument();
    expect(screen.getByText('Event 2: Missing bizLocation')).toBeInTheDocument();
  });

  it('shows a parse error and makes no request for a non-JSON .json file', async () => {
    await openEpcisTab();
    uploadEpcisFile('events.json', 'this is not json{{{', 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(await screen.findByText(/could not parse the file as json/i)).toBeInTheDocument();
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(mocks.validateEpcis).not.toHaveBeenCalled();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
    expect(screen.queryByText('EPCIS processed')).not.toBeInTheDocument();
  });

  it('shows backend failures with the same error pattern as the CSV tab', async () => {
    mocks.ingestEpcisBatch.mockRejectedValue(new Error('Batch ingest failed'));

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(epcisDocument), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(await screen.findByText('Ingestion Failed')).toBeInTheDocument();
    expect(screen.getByText('Batch ingest failed')).toBeInTheDocument();
    expect(screen.queryByText('EPCIS processed')).not.toBeInTheDocument();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('leaves the URL and CSV tabs untouched', async () => {
    render(<IngestPage />);
    expect(screen.getByRole('tab', { name: /url ingestion/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /file upload/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
    expect(document.getElementById('file-upload')).toHaveAttribute('accept', '.csv,text/csv');
  });
});
