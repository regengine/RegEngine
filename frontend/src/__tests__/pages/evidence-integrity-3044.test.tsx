import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AlertsPage from '@/app/dashboard/alerts/page';
import HeartbeatPage from '@/app/dashboard/heartbeat/page';
import IdentityPage from '@/app/identity/page';
import { NormalizedDocumentViewer } from '@/app/ingest/NormalizedDocumentViewer';
import { filterExperimentalLinks } from '@/lib/experimental-features';

afterEach(() => vi.unstubAllEnvs());

describe('evidence integrity', () => {
    it.each([AlertsPage, HeartbeatPage, IdentityPage])('does not mount disabled backend consumers', (Page) => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
        render(<Page />);
        expect(screen.getByTestId('feature-not-enabled')).toBeInTheDocument();
    });

    it('hides disabled routes from navigation', () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
        expect(filterExperimentalLinks([
            { href: '/identity' }, { href: '/dashboard/alerts' },
            { href: '/dashboard/heartbeat' }, { href: '/records' },
        ])).toEqual([{ href: '/records' }]);
    });

    it('shows a document receipt without fabricated extracted facts', () => {
        render(<NormalizedDocumentViewer documentId="document-123" />);
        expect(screen.getByText(/document-123/)).toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveTextContent('Extracted content is not available');
        expect(screen.queryByText('Maintain receiving records')).not.toBeInTheDocument();
        expect(screen.queryByText(/Successfully Normalized/)).not.toBeInTheDocument();
    });
});
