import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ControlsPage from '@/app/controls/page';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('next/navigation', () => ({
    useRouter: () => ({
        push: mockPush,
    }),
}));

describe('ControlsPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            isHydrated: true,
            apiKey: null,
        });
        vi.stubGlobal('confirm', vi.fn(() => true));
    });

    it('fetches controls through the same-origin proxy without browser auth headers', async () => {
        // #2835 `ok: true` is now load-bearing: the page checks response.ok
        // before deserializing. Previously the mock omitted it and the page
        // still rendered a normal empty state, which is precisely the bug —
        // a 404 was indistinguishable from "no controls yet".
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({ controls: [] }),
        });

        render(<ControlsPage />);

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalled();
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/controls/controls');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
    });

    it('deletes controls through the proxy without browser auth headers', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    controls: [{
                        id: 'control-1',
                        control_id: 'CTL-1',
                        title: 'Traceability Plan',
                        description: 'desc',
                        framework: 'FSMA 204',
                        created_at: '2026-05-07T00:00:00.000Z',
                    }],
                }),
            })
            .mockResolvedValueOnce({ ok: true })
            .mockResolvedValueOnce({ ok: true, json: async () => ({ controls: [] }) });

        const user = userEvent.setup();
        render(<ControlsPage />);

        await waitFor(() => {
            expect(screen.getByText('Traceability Plan')).toBeInTheDocument();
        });

        await user.click(screen.getByRole('button', { name: 'Delete' }));

        // Deletion now goes through a confirmation dialog instead of window.confirm
        const dialog = await screen.findByRole('dialog');
        await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledTimes(3);
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[1] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/controls/controls/control-1');
        expect(init.method).toBe('DELETE');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
    });

    // #2835 regression guards. The controls proxy pointed at /v1/admin/ while
    // the overlay router serving controls is mounted at /v1/overlay/
    // (services/admin/app/api_overlay.py:55), so every request 404'd — and
    // because the page never checked response.ok, the 404 rendered as an
    // ordinary "No controls found" empty state and mutations appeared to
    // succeed. These assert the failure is now visible.
    it('surfaces a load failure instead of rendering an empty state', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: false,
            status: 404,
            json: async () => ({ detail: 'Not Found' }),
        });

        render(<ControlsPage />);

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent('Controls unavailable');
        expect(alert).toHaveTextContent('HTTP 404');
        expect(alert).toHaveTextContent('Not Found');

        // The table must NOT invite the user to create a control against a
        // backend we could not reach.
        expect(screen.queryByText(/No controls found/)).not.toBeInTheDocument();
        expect(screen.getByText(/Controls could not be loaded/)).toBeInTheDocument();
    });

    it('surfaces a create failure instead of silently closing the form', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({ ok: true, json: async () => ({ controls: [] }) })
            .mockResolvedValueOnce({
                ok: false,
                status: 404,
                json: async () => ({ detail: 'Not Found' }),
            });

        const user = userEvent.setup();
        render(<ControlsPage />);

        await waitFor(() => {
            expect(screen.getByRole('button', { name: 'Create Control' })).toBeInTheDocument();
        });

        await user.click(screen.getByRole('button', { name: 'Create Control' }));

        await user.type(screen.getByPlaceholderText('e.g., CSF-AC-1'), 'CTL-9');
        await user.type(screen.getByPlaceholderText('e.g., Access Control Policy'), 'Title');
        await user.type(screen.getByPlaceholderText(/Detailed description/), 'Description');

        const form = document.querySelector('form') as HTMLFormElement;
        await user.click(within(form).getByRole('button', { name: 'Create Control' }));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent('Could not create control');
        expect(alert).toHaveTextContent('HTTP 404');

        // The form stays open so the user's input is not lost.
        expect(screen.getByPlaceholderText('e.g., CSF-AC-1')).toBeInTheDocument();
    });

    it('surfaces a delete failure instead of appearing to succeed', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    controls: [{
                        id: 'control-1',
                        control_id: 'CTL-1',
                        title: 'Traceability Plan',
                        description: 'desc',
                        framework: 'FSMA 204',
                        created_at: '2026-05-07T00:00:00.000Z',
                    }],
                }),
            })
            .mockResolvedValueOnce({
                ok: false,
                status: 404,
                json: async () => ({ detail: 'Not Found' }),
            });

        const user = userEvent.setup();
        render(<ControlsPage />);

        await waitFor(() => {
            expect(screen.getByText('Traceability Plan')).toBeInTheDocument();
        });

        await user.click(screen.getByRole('button', { name: 'Delete' }));
        const dialog = await screen.findByRole('dialog');
        await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent('Could not delete control');
        expect(alert).toHaveTextContent('HTTP 404');

        // The row is still there — the delete did not happen.
        expect(screen.getByText('Traceability Plan')).toBeInTheDocument();
    });
});
