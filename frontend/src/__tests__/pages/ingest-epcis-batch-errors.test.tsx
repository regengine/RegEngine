import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

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

// Data-free placeholders: two {} events. Shapes below are copied from the
// backend source; counts derive from EVENTS.length.
const EVENTS: Record<string, unknown>[] = [{}, {}];

// _validate_epcis (services/ingestion/app/epcis/validation.py) output for {},
// in order.
const BACKEND_EVENT_ERRORS = [
  ...['type', 'eventTime', 'action', 'bizStep'].map((field) => `Missing required EPCIS field '${field}'`),
  'Unsupported EPCIS event type',
  'Missing traceability lot code (fsma:traceabilityLotCode or cbvmda:lotNumber)',
];
const STATUS = 400;
const JOINED = BACKEND_EVENT_ERRORS.join(': ');
// Exact message from _ingest_batch_events_db_atomic (persistence.py).
const ATOMIC_MESSAGE =
  'One or more events failed pre-DB validation. No events were persisted. '
  + 'Use ?mode=partial to opt in to per-event processing with HTTP 207 semantics.';

function axiosRejection(status: number, data: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), { response: { status, data } });
}

// Atomic (default, _batch_transactional()): HTTPException(400, detail={...}).
function atomicRejection(events: unknown[]) {
  return axiosRejection(STATUS, {
    detail: {
      error: 'batch_validation_failed',
      mode: 'atomic',
      message: ATOMIC_MESSAGE,
      errors: events.map((_, index) => ({ index, status_code: STATUS, detail: { errors: BACKEND_EVENT_ERRORS } })),
    },
  });
}

// Partial (?mode=partial or EPCIS_BATCH_TRANSACTIONAL=false): router.py
// returns the payload itself with status 400, no detail wrapper.
function partialRejection(events: unknown[]) {
  return axiosRejection(STATUS, {
    total: events.length,
    created: 0,
    failed: events.length,
    results: [],
    errors: events.map((_, index) => ({ index, detail: { errors: BACKEND_EVENT_ERRORS } })),
    mode: 'partial',
  });
}

async function uploadBatch() {
  render(<IngestPage />);
  await userEvent.click(screen.getByRole('tab', { name: /epcis 2\.0/i }));
  const input = document.getElementById('epcis-file-upload') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File([JSON.stringify(EVENTS)], 'events.json', { type: 'application/json' })] },
  });
  await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));
}

function expectEveryEventListed() {
  for (let index = 0; index < EVENTS.length; index += 1) {
    expect(screen.getByText(`Event ${index + 1}: ${JOINED}`)).toBeInTheDocument();
  }
  expect(screen.getAllByText(/^Event \d+:/)).toHaveLength(EVENTS.length);
}

describe('EPCIS all-failed batch shows per-event errors', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists every event under the atomic message', async () => {
    mocks.ingestEpcisBatch.mockRejectedValue(atomicRejection(EVENTS));
    await uploadBatch();
    expect(await screen.findByText('Ingestion Failed')).toBeInTheDocument();
    expect(screen.getByText(ATOMIC_MESSAGE)).toBeInTheDocument();
    expectEveryEventListed();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('lists every event for a partial-mode 400 body', async () => {
    const rejection = partialRejection(EVENTS);
    mocks.ingestEpcisBatch.mockRejectedValue(rejection);
    await uploadBatch();
    expect(await screen.findByText('Ingestion Failed')).toBeInTheDocument();
    expect(screen.getByText(rejection.message)).toBeInTheDocument();
    expectEveryEventListed();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('shows the single-event 400 once, with no Event N: lines', async () => {
    // Single-event path: persistence.py raises
    // HTTPException(400, detail={"errors": [...]}) for {}.
    mocks.ingestEpcisEvent.mockRejectedValue(axiosRejection(STATUS, { detail: { errors: BACKEND_EVENT_ERRORS } }));
    render(<IngestPage />);
    await userEvent.click(screen.getByRole('tab', { name: /epcis 2\.0/i }));
    const input = document.getElementById('epcis-file-upload') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File([JSON.stringify(EVENTS[0])], 'event.json', { type: 'application/json' })] },
    });
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));
    expect(await screen.findByText('Ingestion Failed')).toBeInTheDocument();
    expect(screen.getAllByText(JOINED)).toHaveLength(1);
    expect(screen.queryAllByText(/^Event \d+:/)).toHaveLength(0);
    expect(mocks.ingestEpcisBatch).not.toHaveBeenCalled();
  });
});
