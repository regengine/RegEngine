import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import { TimedSkeleton } from '@/components/ui/timed-skeleton';
import { ErrorState } from '@/components/ui/error-state';

describe('TimedSkeleton', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the skeleton, then "Still loading" after ~5s', () => {
    render(<TimedSkeleton><div>skeleton</div></TimedSkeleton>);
    expect(screen.getByText('skeleton')).toBeInTheDocument();
    expect(screen.queryByText(/still loading/i)).not.toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(5_000); });
    expect(screen.getByText(/still loading/i)).toBeInTheDocument();
    expect(screen.getByText('skeleton')).toBeInTheDocument();
  });

  it('swaps to the shared error state with Retry on timeout, and retry restarts the clock', () => {
    const onRetry = vi.fn();
    render(
      <TimedSkeleton onRetry={onRetry} errorMessage="Metrics did not respond.">
        <div>skeleton</div>
      </TimedSkeleton>,
    );

    act(() => { vi.advanceTimersByTime(20_000); });
    expect(screen.queryByText('skeleton')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Metrics did not respond.');

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByText('skeleton')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('renders the message and a Retry button only when onRetry is given', () => {
    const { rerender } = render(<ErrorState message="Failed." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed.');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    const onRetry = vi.fn();
    rerender(<ErrorState message="Failed." onRetry={onRetry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalled();
  });
});
