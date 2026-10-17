import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { submitAssessment } from '@/app/actions/submit-assessment';
import type { ToolConfig } from '@/types/fsma-tools';

const { capture } = vi.hoisted(() => ({ capture: vi.fn() }));

vi.mock('@/lib/posthog-provider', () => ({
    usePostHog: () => ({ capture }),
}));

vi.mock('@/app/actions/submit-assessment', () => ({
    submitAssessment: vi.fn(),
}));

vi.mock('next/navigation', () => ({
    useSearchParams: () => new URLSearchParams(
        'utm_source=newsletter&utm_medium=email&utm_campaign=fall' +
        '&utm_content=lead%40example.com&utm_term=exemptions'
    ),
}));

const config: ToolConfig = {
    id: 'test-tool',
    title: 'Test Tool',
    description: 'A sample tool.',
    icon: 'TestTube',
    stages: {
        questions: [{ id: 'choice', text: 'Choose one', type: 'select', options: [{ label: 'Yes', value: 'yes' }] }],
        leadGate: { title: 'Get results', description: 'Enter your email.', cta: 'Show Results' },
    },
};

const mockedSubmitAssessment = vi.mocked(submitAssessment);

async function captureLead() {
    const user = userEvent.setup();
    render(<FSMAToolShell config={config} renderResults={() => <div>Tool result</div>} />);
    await user.click(screen.getByRole('button', { name: 'Start Tool' }));
    await user.click(await screen.findByRole('button', { name: 'Yes' }));
    await user.type(await screen.findByRole('textbox', { name: 'Work email' }), 'lead@example.com');
    await user.click(await screen.findByRole('button', { name: 'Show Results' }));
}

describe('FSMAToolShell lead capture', () => {
    beforeEach(() => {
        capture.mockReset();
        mockedSubmitAssessment.mockReset();
    });

    it('saves the lead through the assessment RPC helper and excludes PII from PostHog', async () => {
        mockedSubmitAssessment.mockResolvedValue({ success: true });

        await captureLead();

        await waitFor(() => expect(mockedSubmitAssessment).toHaveBeenCalledTimes(1));
        expect(mockedSubmitAssessment).toHaveBeenCalledWith(expect.objectContaining({
            name: 'FSMA tool lead',
            email: 'lead@example.com',
            company: 'Unknown (FSMA tool)',
            source: 'test-tool',
            utmSource: 'newsletter',
            utmMedium: 'email',
            utmCampaign: 'fall',
            toolInputs: { utm_content: 'lead@example.com', utm_term: 'exemptions' },
        }));
        expect(capture).toHaveBeenCalledWith('test-tool_LEAD_CAPTURE', { tool_id: 'test-tool' });
        expect(JSON.stringify(capture.mock.calls)).not.toContain('lead@example.com');
        expect(JSON.stringify(capture.mock.calls)).not.toContain('utm_source');
        expect(await screen.findByText('Tool result')).toBeInTheDocument();
    });

    it('shows results even when the save rejects', async () => {
        mockedSubmitAssessment.mockRejectedValue(new Error('save failed'));

        await captureLead();

        expect(await screen.findByText('Tool result')).toBeInTheDocument();
        await waitFor(() => expect(mockedSubmitAssessment).toHaveBeenCalledTimes(1));
    });
});
