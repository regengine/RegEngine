/**
 * Identity Resolution Page Tests
 *
 * Tests for the identity resolution view:
 * - Entity list rendering
 * - Entity type badges
 * - Tabs (entities / reviews)
 * - Search filter
 * - Demo banner flag
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IdentityResolutionPage from '@/app/identity/page';

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn().mockReturnValue({
    apiKey: 'test-api-key',
    tenantId: 'tenant-123',
  }),
}));

// Mock control-plane hooks
const mockUseEntities = vi.fn();
const mockUseIdentityReviews = vi.fn();

vi.mock('@/hooks/use-control-plane', () => ({
  useEntities: (...args: any[]) => mockUseEntities(...args),
  useIdentityReviews: (...args: any[]) => mockUseIdentityReviews(...args),
}));

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => {
  const stub = (props: any) => <svg {...props} />;
  return {
    Building2: stub,
    CheckCircle: stub,
    GitMerge: stub,
    HelpCircle: stub,
    Link2: stub,
    MapPin: stub,
    Package: stub,
    Search: stub,
    Users: stub,
    XCircle: stub,
  };
});

const SAMPLE_ENTITIES = [
  {
    entity_id: 'e-1',
    entity_type: 'firm',
    canonical_name: 'Acme Foods Inc',
    gln: '1234567890123',
    gtin: null,
    verification_status: 'verified',
    confidence_score: 0.95,
  },
  {
    entity_id: 'e-2',
    entity_type: 'facility',
    canonical_name: 'Distribution Center Alpha',
    gln: '9876543210987',
    gtin: null,
    verification_status: 'pending',
    confidence_score: 0.72,
  },
  {
    entity_id: 'e-3',
    entity_type: 'product',
    canonical_name: 'Organic Romaine Lettuce',
    gln: null,
    gtin: '00012345678905',
    verification_status: 'verified',
    confidence_score: 0.99,
  },
];

const SAMPLE_REVIEWS = [
  {
    review_id: 'rev-1',
    match_type: 'ambiguous',
    match_confidence: 0.65,
    status: 'pending',
    entity_a_id: 'e-1',
    entity_a_name: 'Acme Foods Inc',
    entity_b_id: 'e-4',
    entity_b_name: 'ACME Foods',
  },
  {
    review_id: 'rev-2',
    match_type: 'likely',
    match_confidence: 0.82,
    status: 'confirmed_match',
    entity_a_id: 'e-2',
    entity_a_name: 'DC Alpha',
    entity_b_id: 'e-5',
    entity_b_name: 'Distribution Center Alpha',
  },
];

describe('IdentityResolutionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseIdentityReviews.mockReturnValue({
      data: { reviews: SAMPLE_REVIEWS },
      isLoading: false,
    });
  });

  function setupEntities(overrides: any = {}) {
    mockUseEntities.mockReturnValue({
      data: { entities: SAMPLE_ENTITIES, __isDemo: false },
      isLoading: false,
      ...overrides,
    });
  }

  it('renders entity list with canonical names', () => {
    setupEntities();
    render(<IdentityResolutionPage />);

    expect(screen.getByText('Acme Foods Inc')).toBeInTheDocument();
    expect(screen.getByText('Distribution Center Alpha')).toBeInTheDocument();
    expect(screen.getByText('Organic Romaine Lettuce')).toBeInTheDocument();
  });

  it('shows entity type labels in the table', () => {
    setupEntities();
    render(<IdentityResolutionPage />);

    expect(screen.getByText('Firm')).toBeInTheDocument();
    expect(screen.getByText('Facility')).toBeInTheDocument();
    expect(screen.getByText('Product')).toBeInTheDocument();
  });

  it('displays tabs for entities and reviews', () => {
    setupEntities();
    render(<IdentityResolutionPage />);

    expect(screen.getByRole('tab', { name: /entities/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /review queue/i })).toBeInTheDocument();
  });

  it('switches to review queue tab and shows reviews', async () => {
    setupEntities();
    const user = userEvent.setup();
    render(<IdentityResolutionPage />);

    const reviewTab = screen.getByRole('tab', { name: /review queue/i });
    await user.click(reviewTab);

    expect(screen.getByText('Ambiguous Match Review Queue')).toBeInTheDocument();
    expect(screen.getByText('ACME Foods')).toBeInTheDocument();
    expect(screen.getByText('65% confidence')).toBeInTheDocument();
  });

  it('filters entities by search query', async () => {
    setupEntities();
    const user = userEvent.setup();
    render(<IdentityResolutionPage />);

    const searchInput = screen.getByPlaceholderText(/search entities/i);
    await user.type(searchInput, 'Romaine');

    // Only the matching entity should appear in the table
    expect(screen.getByText('Organic Romaine Lettuce')).toBeInTheDocument();
    // Distribution Center Alpha should be filtered out from the table
    // (it may still appear in the stat cards, so check within the table)
    const table = screen.getByRole('table');
    expect(table).not.toHaveTextContent('Distribution Center Alpha');
  });

  it('shows pending review count badge', () => {
    setupEntities();
    render(<IdentityResolutionPage />);

    expect(screen.getByText(/1 Pending Reviews/)).toBeInTheDocument();
  });

  it('shows empty state when no entities', () => {
    mockUseEntities.mockReturnValue({
      data: { entities: [], __isDemo: false },
      isLoading: false,
    });
    render(<IdentityResolutionPage />);

    expect(screen.getByText('No entities registered')).toBeInTheDocument();
  });
});
