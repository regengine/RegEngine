import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { GettingStartedCard } from '@/components/dashboard/getting-started-card';
import { useTenant } from '@/lib/tenant-context';
import { useOnboardingStatus, useUpdateOnboarding } from '@/hooks/use-onboarding';

vi.mock('@/lib/tenant-context', () => ({
  useTenant: vi.fn(),
}));

vi.mock('@/hooks/use-onboarding', () => ({
  useOnboardingStatus: vi.fn(),
  useUpdateOnboarding: vi.fn(),
}));

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

describe('GettingStartedCard', () => {
  it('uses shrink-safe layout and 44px minimum touch targets', () => {
    (useTenant as vi.Mock).mockReturnValue({ tenantId: 'tenant-123' });
    (useOnboardingStatus as vi.Mock).mockReturnValue({
      data: { onboarding: {} },
      isLoading: false,
    });
    (useUpdateOnboarding as vi.Mock).mockReturnValue({
      mutateAsync: vi.fn(),
    });

    const { container } = render(<GettingStartedCard />);

    const dismissButton = screen.getByRole('button', {
      name: 'Dismiss Getting Started',
    });
    expect(dismissButton).toHaveClass('h-11', 'w-11', 'flex-shrink-0');
    expect(dismissButton.className).not.toContain('-m-1');

    const header = dismissButton.parentElement;
    expect(header).toHaveClass('min-w-0', 'gap-3');
    expect(header?.firstElementChild).toHaveClass('min-w-0', 'flex-1');

    const checklistLinks = screen.getAllByRole('link').filter((link) =>
      [
        '#',
        '/onboarding/setup/facility',
        '/onboarding/setup/ftl-check',
        '/tools/data-import',
        '/dashboard/team',
        '/dashboard/recall-drills',
      ].includes(link.getAttribute('href') || ''),
    );
    expect(checklistLinks).toHaveLength(6);
    checklistLinks.forEach((link) => {
      expect(link).toHaveClass('min-h-12', 'min-w-0');
    });

    const guidedWalkthrough = screen.getByRole('link', {
      name: /prefer a guided tutorial/i,
    });
    expect(guidedWalkthrough).toHaveClass(
      'block',
      'min-h-12',
      'max-w-full',
      'whitespace-normal',
      'break-words',
    );
    expect(container.querySelector('.min-w-0')).toBeTruthy();
  });
});
