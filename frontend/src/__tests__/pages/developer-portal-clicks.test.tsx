/**
 * The portal pages are static: they read the signed-in session from useAuth
 * and make no network calls. Every link they offer must land on a real page.
 *
 * SEL-419: The developer portal features live JSON events API status,
 * endpoints dynamically derived from publicOpenApiSpec, and API keys list
 * with revocation action.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApiKeysPage from '@/app/developer/portal/keys/page';
import DeveloperPortalPage from '@/app/developer/portal/page';
import { publicOpenApiSpec } from '@/lib/public-openapi';

const mocks = vi.hoisted(() => ({
    authValue: {
        user: { id: 'dev-1', email: 'dev@example.com', role_name: 'Owner' } as
            { id: string; email: string; role_name?: string } | null,
        tenantId: '11111111-2222-4333-8444-555555555555' as string | null,
    },
    useAPIKeysValue: {
        data: [] as unknown[],
        isLoading: false,
        error: null,
    },
    revokeMutateAsync: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mocks.authValue,
}));

vi.mock('@/hooks/use-api', () => ({
    useAPIKeys: () => mocks.useAPIKeysValue,
    useRevokeAPIKey: () => ({
        mutateAsync: mocks.revokeMutateAsync,
        isPending: false,
    }),
}));

describe('developer portal page', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        mocks.authValue.user = { id: 'dev-1', email: 'dev@example.com', role_name: 'Owner' };
        mocks.authValue.tenantId = '11111111-2222-4333-8444-555555555555';
        mocks.useAPIKeysValue = {
            data: [],
            isLoading: false,
            error: null,
        };
        mocks.revokeMutateAsync.mockReset();
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

    it('renders the exact live header and labels EPCIS as (Preview)', () => {
        render(<DeveloperPortalPage />);

        expect(screen.getByRole('heading', { name: 'The JSON events API is live.' })).toBeInTheDocument();
        expect(screen.getByText('The JSON events API is live.')).toBeInTheDocument();
        expect(screen.getByText(/EPCIS \(Preview\)/)).toBeInTheDocument();

        const containerHtml = document.body.innerHTML;
        const invalidEpcisMatches = containerHtml.match(/\bEPCIS\b(?!\s*\(Preview\))/g);
        expect(invalidEpcisMatches).toBeNull();
    });

    it('renders the endpoint list dynamically generated from publicOpenApiSpec linking to /docs/api', () => {
        render(<DeveloperPortalPage />);

        const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'] as const;
        const expectedEndpoints: { method: string; path: string; summary: string }[] = [];

        for (const [pathStr, pathItem] of Object.entries(publicOpenApiSpec.paths)) {
            for (const [method, operation] of Object.entries(pathItem)) {
                if (HTTP_METHODS.includes(method.toLowerCase() as typeof HTTP_METHODS[number])) {
                    const op = operation as { summary?: string };
                    expectedEndpoints.push({
                        method: method.toUpperCase(),
                        path: pathStr,
                        summary: op.summary || '',
                    });
                }
            }
        }

        expect(expectedEndpoints.length).toBeGreaterThan(0);

        for (const ep of expectedEndpoints) {
            expect(screen.getAllByText(ep.method).length).toBeGreaterThan(0);
            expect(screen.getByText(ep.path)).toBeInTheDocument();
            if (ep.summary) {
                const expectedSummary = ep.summary.replace(/\btenant(s?)\b/gi, (match, plural) => {
                    const isPlural = Boolean(plural);
                    const base = isPlural ? 'workspaces' : 'workspace';
                    if (match === match.toUpperCase()) return base.toUpperCase();
                    if (match[0] === match[0].toUpperCase()) return isPlural ? 'Workspaces' : 'Workspace';
                    return base;
                });
                expect(screen.getByText(expectedSummary)).toBeInTheDocument();
            }
        }

        const endpointLinks = screen.getAllByRole('link').filter((link) => link.getAttribute('href') === '/docs/api');
        expect(endpointLinks.length).toBeGreaterThanOrEqual(expectedEndpoints.length);
    });

    it('displays the empty state "No keys yet" when no API keys exist', () => {
        mocks.useAPIKeysValue = {
            data: [],
            isLoading: false,
            error: null,
        };

        render(<DeveloperPortalPage />);

        expect(screen.getByText('No keys yet')).toBeInTheDocument();
    });

    it('shows existing API keys with name, key prefix, created, last used, and revoke action', async () => {
        mocks.useAPIKeysValue = {
            data: [
                {
                    id: 'key-test-1',
                    key_id: 'key-test-1',
                    name: 'Primary Ingest Key',
                    key_prefix: 'rge_live_prm1',
                    created_at: '2026-10-01T12:00:00Z',
                    last_used_at: '2026-10-15T15:00:00Z',
                    key: 'rge_live_super_secret_full_token_should_never_show',
                },
                {
                    id: 'key-test-2',
                    key_id: 'key-test-2',
                    name: 'Readonly Key',
                    key_prefix: 'rge_live_read2',
                    created_at: '2026-10-05T08:00:00Z',
                    last_used_at: null,
                },
            ],
            isLoading: false,
            error: null,
        };

        render(<DeveloperPortalPage />);

        expect(screen.getByText('Primary Ingest Key')).toBeInTheDocument();
        expect(screen.getByText('rge_live_prm1')).toBeInTheDocument();
        expect(screen.getByText('Readonly Key')).toBeInTheDocument();
        expect(screen.getByText('rge_live_read2')).toBeInTheDocument();
        expect(screen.getByText('Never')).toBeInTheDocument();

        // Never display full secrets
        expect(screen.queryByText(/rge_live_super_secret_full_token_should_never_show/)).not.toBeInTheDocument();

        const revokeButtons = screen.getAllByRole('button', { name: /revoke/i });
        expect(revokeButtons.length).toBe(2);

        fireEvent.click(revokeButtons[0]);
        expect(mocks.revokeMutateAsync).toHaveBeenCalledWith({ keyId: 'key-test-1' });
    });

    it('displays endpoint summaries with tenant replaced by workspace and renders error callout on failure', async () => {
        mocks.useAPIKeysValue = {
            data: [
                {
                    id: 'key-test-1',
                    key_id: 'key-test-1',
                    name: 'Test Key',
                    key_prefix: 'rge_live_prm1',
                    created_at: '2026-10-01T12:00:00Z',
                    last_used_at: null,
                },
            ],
            isLoading: false,
            error: null,
        };
        mocks.revokeMutateAsync.mockRejectedValueOnce(new Error('Revoke failed'));

        render(<DeveloperPortalPage />);

        expect(screen.getByText('Verify a workspace hash chain')).toBeInTheDocument();
        expect(screen.queryByText(/Verify a tenant hash chain/i)).not.toBeInTheDocument();

        const revokeBtn = screen.getByRole('button', { name: /revoke/i });
        fireEvent.click(revokeBtn);

        expect(await screen.findByText('Failed to revoke API key. Please try again.')).toBeInTheDocument();
    });

    it('contains no em dashes or en dashes in any user visible copy', () => {
        render(<DeveloperPortalPage />);

        const bodyHtml = document.body.innerHTML;
        // \u2014 is em dash, \u2013 is en dash
        expect(bodyHtml).not.toContain('\u2014');
        expect(bodyHtml).not.toContain('\u2013');
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

    it('contains no em dashes or en dashes on the keys page', () => {
        render(<ApiKeysPage />);

        const bodyHtml = document.body.innerHTML;
        expect(bodyHtml).not.toContain('\u2014');
        expect(bodyHtml).not.toContain('\u2013');
    });
});
