import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import RecordsPage from '@/app/records/page';
import { apiError } from '@/lib/api-error';

const state = vi.hoisted(() => ({ error: null as unknown }));
const refetch = vi.fn();

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ tenantId: '', user: null }),
}));
vi.mock('@/hooks/use-control-plane', () => ({
  useCanonicalEvents: () => ({ data: undefined, error: state.error, isLoading: false, refetch }),
  useCanonicalEvent: () => ({ data: undefined }),
}));

describe('SEL-410 records load errors', () => {
  beforeEach(() => {
    refetch.mockClear();
  });

  it('shows the safe rate-limit message on 429 without Retry-After', () => {
    const requestId = crypto.randomUUID();
    const rawDetail = `rate-limit-detail-${crypto.randomUUID()}`;
    state.error = apiError(429, rawDetail, requestId);

    render(<RecordsPage />);

    expect(screen.getByRole('alert')).toHaveTextContent('Too many requests. Wait a moment before retrying.');
    expect(screen.queryByText(rawDetail)).not.toBeInTheDocument();
    expect(screen.queryByText(/total records/i)).not.toBeInTheDocument();
    expect(screen.getByText(`Request ID: ${requestId}`)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it('mentions the Retry-After seconds on 429 when the header shape carries them', () => {
    const requestId = crypto.randomUUID();
    const rawDetail = `rate-limit-detail-${crypto.randomUUID()}`;
    const error = apiError(429, rawDetail, requestId);
    error.response = { status: 429, headers: { 'retry-after': '45' }, requestId };
    state.error = error;

    render(<RecordsPage />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Too many requests. Wait a moment before retrying.');
    expect(alert).toHaveTextContent('Retry in 45 seconds.');
    expect(screen.queryByText(rawDetail)).not.toBeInTheDocument();
  });

  it('mentions the Retry-After seconds on 429 when the direct field carries them', () => {
    const error = apiError(429, 'Too Many Requests');
    error.retryAfter = 30;
    state.error = error;

    render(<RecordsPage />);

    expect(screen.getByRole('alert')).toHaveTextContent('Retry in 30 seconds.');
  });

  it('keeps the generic message for non-429 failures and hides raw detail', () => {
    const rawDetail = `backend-detail-${crypto.randomUUID()}`;
    state.error = apiError(500, rawDetail);

    render(<RecordsPage />);

    expect(screen.getByRole('alert')).toHaveTextContent('We could not load your records.');
    expect(screen.queryByText(rawDetail)).not.toBeInTheDocument();
    expect(screen.queryByText(/total records/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledOnce();
  });
});
