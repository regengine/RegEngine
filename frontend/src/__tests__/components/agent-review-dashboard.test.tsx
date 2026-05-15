import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AgentReviewDashboard } from '@/components/dashboard/agent-review-dashboard';
import type { AgentReviewItem } from '@/types/agent-review';

const mockUseAgentReviewItems = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseTenant = vi.hoisted(() => vi.fn());
const mockRefetch = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/use-agent-reviews', () => ({
    useAgentReviewItems: (...args: any[]) => mockUseAgentReviewItems(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: () => <div>Loading...</div>,
}));

const SHA256 = 'd'.repeat(64);

function makeItem(overrides: Partial<AgentReviewItem>): AgentReviewItem {
    return {
        artifact_id: '11111111-1111-4111-8111-111111111111',
        tenant_id: '22222222-2222-4222-8222-222222222222',
        artifact_type: 'field_mapping_suggestion',
        created_at: '2026-05-13T15:00:00Z',
        agent_name: 'fsma-risk-agent',
        suggestion: 'Map Supplier TLC to traceability_lot_code.',
        confidence: 0.82,
        requires_human_review: true,
        review_id: null,
        review_status: 'pending',
        reviewed_by: null,
        reviewed_at: null,
        risk_score: 72.2,
        risk_breakdown: {
            score: 72.2,
            uncapped_score: 72.2,
            confidence_risk: 7.2,
            review_risk: 25,
            artifact_type_risk: 15,
            evidence_gap_risk: 15,
            rule_gap_risk: 10,
        },
        compliance_gap_count: 4,
        compliance_gaps: [
            {
                code: 'low_confidence',
                message: 'Artifact confidence is below the human-review threshold (0.85).',
            },
        ],
        ingestion_run_id: '33333333-3333-4333-8333-333333333333',
        ingestion_run_status: 'processing',
        source_system: 'csv_upload',
        source_file_name: 'receiving.csv',
        advisory_receipt_id: '44444444-4444-4444-8444-444444444444',
        advisory_receipt_state: 'needs_review',
        receipt_hash: 'a'.repeat(64),
        chain_valid: true,
        evidence_ids: ['55555555-5555-4555-8555-555555555555'],
        canonical_event_ids: [],
        source_hashes: [SHA256],
        rule_id: null,
        rule_version: null,
        ...overrides,
    };
}

describe('AgentReviewDashboard', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            hasTenantSession: true,
            isAuthenticated: true,
            user: { is_sysadmin: false },
        });
        mockUseTenant.mockReturnValue({ tenantId: '22222222-2222-4222-8222-222222222222' });
        mockUseAgentReviewItems.mockReturnValue({
            data: {
                items: [
                    makeItem({
                        artifact_id: 'low-risk',
                        suggestion: 'Accept export readiness summary.',
                        risk_score: 20,
                        compliance_gap_count: 0,
                        compliance_gaps: [],
                        requires_human_review: false,
                        review_status: 'accepted',
                        created_at: '2026-05-13T10:00:00Z',
                    }),
                    makeItem({
                        artifact_id: 'high-risk',
                        suggestion: 'Investigate missing receiving evidence.',
                        risk_score: 90,
                        compliance_gap_count: 5,
                        requires_human_review: true,
                        review_status: 'pending',
                        chain_valid: false,
                    }),
                ],
                total: 2,
                limit: 100,
                offset: 0,
            },
            error: null,
            isFetching: false,
            isLoading: false,
            refetch: mockRefetch,
        });
    });

    it('renders the MVV columns and sorts human-review/high-risk items first', () => {
        render(<AgentReviewDashboard />);

        const table = screen.getByRole('table');
        [
            'Agent Suggestion',
            'Risk Score',
            'Gap Count',
            'Review Status',
            'Ingestion Run ID',
            'Evidence Anchors',
            'Advisory Receipt',
            'Chain Validity',
        ].forEach((header) => {
            expect(within(table).getByRole('columnheader', { name: header })).toBeInTheDocument();
        });

        const suggestionButtons = within(table).getAllByRole('button');
        expect(suggestionButtons[0]).toHaveTextContent('Investigate missing receiving evidence.');
        expect(suggestionButtons[1]).toHaveTextContent('Accept export readiness summary.');
        expect(screen.getByText('90.0')).toBeInTheDocument();
        expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('Broken')).toBeInTheDocument();
    });

    it('opens an audit detail view with evidence IDs, source hashes, and receipt data', async () => {
        const user = userEvent.setup();
        render(<AgentReviewDashboard />);

        await user.click(screen.getByRole('button', { name: /Investigate missing receiving evidence/i }));

        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('Agent artifact review');
        expect(dialog).toHaveTextContent('55555555-5555-4555-8555-555555555555');
        expect(dialog).toHaveTextContent(SHA256);
        expect(dialog).toHaveTextContent('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
        expect(dialog).toHaveTextContent('low_confidence');
    });

    it('passes sysadmin tenant filters to the V1 endpoint query hook', () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: false,
            isAuthenticated: true,
            user: { is_sysadmin: true },
        });

        render(<AgentReviewDashboard />);

        expect(mockUseAgentReviewItems).toHaveBeenCalledWith(
            expect.objectContaining({
                tenantId: '22222222-2222-4222-8222-222222222222',
                limit: 100,
                offset: 0,
            }),
            true,
        );
    });
});
