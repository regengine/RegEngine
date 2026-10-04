/**
 * The portal pages are static: they read the signed-in session from useAuth
 * and make no network calls. Every link they offer must land on a real page.
 *
 * The key create / revoke / step-up state machine that used to be tested here
 * belonged to the Supabase key page, which is replaced by a static card. It
 * stays in git history (5239d3c3) for a later keys screen.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApiKeysPage from '@/app/developer/portal/keys/page';
import DeveloperPortalPage from '@/app/developer/portal/page';

const mocks = vi.hoisted(() => ({
    authValue: {
        user: { id: 'dev-1', email: 'dev@example.com', role_name: 'Owner' } as
            { id: string; email: string; role_name?: string } | null,
        tenantId: '11111111-2222-4333-8444-555555555555' as string | null,
    },
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mocks.authValue,
}));

describe('developer portal page', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        mocks.authValue.user = { id: 'dev-1', email: 'dev@example.com', role_name: 'Owner' };
        mocks.authValue.tenantId = '11111111-2222-4333-8444-555555555555';
    });

    it('shows the email, role and workspace from the session', () => {
        render(<DeveloperPortalPage />);

        expect(screen.getByText('dev@example.com')).toBeInTheDocument();
        expect(screen.getByText('Owner')).toBeInTheDocument();
        expect(screen.getByText('Workspace')).toBeInTheDocument();
        expect(screen.getByText('11111111-2222-4333-8444-555555555555')).toBeInTheDocument();
        expect(screen.queryByText(/tenant/i)).not.toBeInTheDocument();
    });

    it('states the API base URL and key header, and sends key requests to /contact', () => {
        render(<DeveloperPortalPage />);

        expect(screen.getByText('https://regengine.co/api/v1')).toBeInTheDocument();
        expect(screen.getByText('X-RegEngine-API-Key')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /request a live key/i })).toHaveAttribute('href', '/contact');
    });

    it('shows the no-workspace message when the account has no single workspace', () => {
        mocks.authValue.tenantId = null;

        render(<DeveloperPortalPage />);

        expect(screen.getByText(/this account has no single workspace/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /contact support/i })).toHaveAttribute('href', '/contact');
        expect(screen.queryByText('Workspace')).not.toBeInTheDocument();
    });

    it('never calls the network, with or without a workspace', () => {
        const first = render(<DeveloperPortalPage />);
        first.unmount();
        mocks.authValue.tenantId = null;
        render(<DeveloperPortalPage />);

        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('does not invent usage numbers, plan names or limits', () => {
        render(<DeveloperPortalPage />);

        expect(screen.queryByText(/requests per/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/rate limit/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/uptime/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/steps? complete/i)).not.toBeInTheDocument();
    });

    it('offers only real links: no "#" placeholders and no retired portal sub-pages', () => {
        render(<DeveloperPortalPage />);

        const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
        expect(hrefs.length).toBeGreaterThan(0);
        for (const href of hrefs) {
            expect(href).toBeTruthy();
            expect(href).not.toBe('#');
            expect(href).not.toMatch(/\/developer\/portal\/(playground|codegen|usage|docs)/);
        }
        expect(hrefs).toEqual(expect.arrayContaining(['/contact', '/docs/quickstart', '/docs/authentication', '/docs/api']));
    });
});

describe('developer portal keys page', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
    });

    it('says live keys are issued by RegEngine and links to /contact', () => {
        render(<ApiKeysPage />);

        expect(screen.getByRole('heading', { name: /live keys are issued by regengine/i })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /request a live key/i })).toHaveAttribute('href', '/contact');
    });

    it('has no create control, no key list and no network call', () => {
        render(<ApiKeysPage />);

        expect(screen.queryByRole('button')).not.toBeInTheDocument();
        expect(screen.queryByRole('table')).not.toBeInTheDocument();
        expect(screen.queryByPlaceholderText(/./)).not.toBeInTheDocument();
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
