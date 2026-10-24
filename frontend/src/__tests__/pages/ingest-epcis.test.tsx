import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

// Data-free placeholder: the tests only check passthrough and event count.
const epcisDocument = { epcisBody: { eventList: Array.from({ length: 2 }, () => ({})) } };

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

// Data-free placeholders: the page only routes on shape (single object vs
// array vs .xml), so no event field values are needed. Real data only in tests.
const SINGLE_EVENT: Record<string, unknown> = {};

// What _validate_epcis (services/ingestion/app/epcis/validation.py) really
// returns for the {} placeholder, in order: each missing required field
// (type, eventTime, action, bizStep), then the unsupported type, then the
// missing lot code. Every {} event is invalid, so the batch path rejects each
// one with HTTPException(400, detail={"errors": [...]}) (persistence.py).
const REQUIRED_FIELDS = ['type', 'eventTime', 'action', 'bizStep'];
const BACKEND_EVENT_ERRORS = [
  ...REQUIRED_FIELDS.map((field) => `Missing required EPCIS field '${field}'`),
  'Unsupported EPCIS event type',
  'Missing traceability lot code (fsma:traceabilityLotCode or cbvmda:lotNumber)',
];
const BACKEND_VALIDATION_STATUS = 400;
// page.tsx and epcis-upload.ts both join an error list with ': '.
const JOINED_EVENT_ERRORS = BACKEND_EVENT_ERRORS.join(': ');

// The real batch response for a list of {} events: none created, all failed.
function rejectedBatchResponse(events: unknown[]) {
  const detail = { errors: BACKEND_EVENT_ERRORS };
  return {
    total: events.length,
    created: 0,
    failed: events.length,
    results: events.map((_, index) => ({ index, status_code: BACKEND_VALIDATION_STATUS, detail })),
    errors: events.map((_, index) => ({ index, detail })),
    mode: 'partial',
  };
}

function expectEveryEventRejected(count: number) {
  for (let index = 0; index < count; index += 1) {
    expect(screen.getByText(`Event ${index + 1}: ${JOINED_EVENT_ERRORS}`)).toBeInTheDocument();
  }
}

const EPCIS_XML = `<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2">
  <EPCISBody>
    <EventList />
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
    mocks.ingestEpcisBatch.mockResolvedValue(rejectedBatchResponse(eventList));

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
    expect(await screen.findByText('No events accepted')).toBeInTheDocument();
    expect(
      screen.getByText(`0 of ${eventList.length} events accepted; ${eventList.length} rejected.`),
    ).toBeInTheDocument();
    expectEveryEventRejected(eventList.length);
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('sends a bare JSON array of events to the batch endpoint', async () => {
    const events = [{ ...SINGLE_EVENT }, { ...SINGLE_EVENT }];
    mocks.ingestEpcisBatch.mockResolvedValue(rejectedBatchResponse(events));

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(events), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(mocks.ingestEpcisBatch).toHaveBeenCalledTimes(1);
    expect(mocks.ingestEpcisBatch).toHaveBeenCalledWith({
      apiKey: 'cookie-managed', // pragma: allowlist secret
      events,
    });
    expect(await screen.findByText('No events accepted')).toBeInTheDocument();
    expect(
      screen.getByText(`0 of ${events.length} events accepted; ${events.length} rejected.`),
    ).toBeInTheDocument();
    expectEveryEventRejected(events.length);
  });

  it('sends a single-event JSON to the single-event endpoint', async () => {
    mocks.ingestEpcisEvent.mockRejectedValue(
      Object.assign(new Error(`Request failed with status code ${BACKEND_VALIDATION_STATUS}`), {
        response: { status: BACKEND_VALIDATION_STATUS, data: { detail: { errors: BACKEND_EVENT_ERRORS } } },
      }),
    );

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
    expect(await screen.findByText('Ingestion Failed')).toBeInTheDocument();
    expect(screen.getByText(JOINED_EVENT_ERRORS)).toBeInTheDocument();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('sends an XML file to the XML endpoint untouched', async () => {
    // EPCIS_XML carries an empty EventList, so the backend parses no events.
    mocks.ingestEpcisXml.mockResolvedValue({
      total: 0,
      created: 0,
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
    // The page passes the response through unchanged.
    expect(await screen.findByText('No events accepted')).toBeInTheDocument();
    expect(screen.getByText('0 of 0 events accepted; 0 rejected.')).toBeInTheDocument();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('validate-only calls the validate endpoint and never ingests', async () => {
    mocks.validateEpcis.mockResolvedValue({ valid: false, errors: BACKEND_EVENT_ERRORS, normalized_cte: null });

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
    expect(await screen.findByText('Validation found issues')).toBeInTheDocument();
    expect(screen.getByText(`0 of ${[SINGLE_EVENT].length} events valid.`)).toBeInTheDocument();
    expectEveryEventRejected([SINGLE_EVENT].length);
  });

  it('validate-only reports per-event failures for a batch document', async () => {
    const events = [{ ...SINGLE_EVENT }, { ...SINGLE_EVENT }];
    mocks.validateEpcis.mockResolvedValue({ valid: false, errors: BACKEND_EVENT_ERRORS, normalized_cte: null });

    await openEpcisTab();
    uploadEpcisFile('events.json', JSON.stringify(events), 'application/json');
    await userEvent.click(screen.getByRole('button', { name: /^validate only$/i }));

    expect(mocks.validateEpcis).toHaveBeenCalledTimes(events.length);
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisEvent).not.toHaveBeenCalled();
    expect(mocks.ingestEpcisXml).not.toHaveBeenCalled();
    expect(await screen.findByText('Validation found issues')).toBeInTheDocument();
    expect(screen.getByText(`0 of ${events.length} events valid.`)).toBeInTheDocument();
    expectEveryEventRejected(events.length);
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
