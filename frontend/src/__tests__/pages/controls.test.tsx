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
        fetchWithCsrfMock.mockResolvedValue({
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
            .mockResolvedValueOnce({ json: async () => ({ controls: [] }) });

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
});
