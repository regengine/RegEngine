import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ContactRequestForm } from '@/components/contact/ContactRequestForm';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { ph } from '@/lib/posthog-provider';

vi.mock('@/lib/fetch-with-csrf', () => ({ fetchWithCsrf: vi.fn() }));
vi.mock('@/lib/conversion-events', () => ({
    getConversionAttribution: () => ({}),
    trackContactFormSubmit: vi.fn(),
}));
vi.mock('@/lib/posthog-provider', () => ({
    identifyUser: vi.fn(),
    ph: { requestAccess: vi.fn(), signup: vi.fn() },
}));

async function submit(props: Parameters<typeof ContactRequestForm>[0] = {}) {
    render(<ContactRequestForm {...props} />);
    fireEvent.change(screen.getByPlaceholderText('Name'), { target: { value: 'Jane Doe' } });
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'jane@example.com' } });
    fireEvent.change(screen.getByPlaceholderText('How can we help?'), { target: { value: 'Hello' } });
    fireEvent.click(screen.getByRole('button', { name: /send message/i }));
}

describe('ContactRequestForm request_access event', () => {
    beforeEach(() => vi.clearAllMocks());

    it('fires request_access with no form fields after a successful /contact submit', async () => {
        vi.mocked(fetchWithCsrf).mockResolvedValue(new Response('{}', { status: 200 }));
        await submit();
        await waitFor(() => expect(ph.requestAccess).toHaveBeenCalledTimes(1));
        expect(ph.requestAccess).toHaveBeenCalledWith();
    });

    it('does not fire when the submit fails', async () => {
        vi.mocked(fetchWithCsrf).mockResolvedValue(new Response('{}', { status: 500 }));
        await submit();
        await screen.findByRole('alert');
        expect(ph.requestAccess).not.toHaveBeenCalled();
    });

    it('does not fire for the signup form', async () => {
        vi.mocked(fetchWithCsrf).mockResolvedValue(new Response('{}', { status: 200 }));
        await submit({ source: 'signup' });
        await waitFor(() => expect(ph.signup).toHaveBeenCalledTimes(1));
        expect(ph.requestAccess).not.toHaveBeenCalled();
    });
});
