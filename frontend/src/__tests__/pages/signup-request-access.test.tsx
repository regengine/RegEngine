import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import SignupPage from '@/app/signup/page';

const mocks = vi.hoisted(() => ({
  fetchWithCsrf: vi.fn(),
  search: 'plan=base&billing=annual',
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
  fetchWithCsrf: (...args: unknown[]) => mocks.fetchWithCsrf(...args),
}));

describe('/signup request access', () => {
  beforeEach(() => {
    mocks.search = 'plan=base&billing=annual';
    mocks.fetchWithCsrf.mockResolvedValue({ ok: true, status: 200 });
  });

  it('renders a request-access form and posts name, email, and company to /api/contact', async () => {
    const user = userEvent.setup();
    render(<SignupPage />);

    expect(screen.getByRole('heading', { name: /create your regengine workspace/i })).toBeInTheDocument();
    expect(screen.getByText(/usually within one business day/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^company/i)).toBeInTheDocument();
    expect(document.querySelector('input[name="website"]')).not.toBeNull();
    expect(screen.getByLabelText(/^message/i)).toHaveValue('Requested plan: base (annual).');

    await user.type(screen.getByLabelText(/^name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/^email/i), 'ada@example.com');
    await user.type(screen.getByLabelText(/^company/i), 'Analytical Engines');
    await user.clear(screen.getByLabelText(/^message/i));
    await user.type(screen.getByLabelText(/^message/i), 'Need FSMA 204 exports.');
    await user.click(screen.getByRole('button', { name: /request access/i }));

    expect(mocks.fetchWithCsrf).toHaveBeenCalledWith('/api/contact', expect.objectContaining({
      method: 'POST',
    }));
    const init = mocks.fetchWithCsrf.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      company: 'Analytical Engines',
      website: '',
      source: 'signup',
    });
    expect(body.message).toContain('Need FSMA 204 exports.');
    expect(body.message).toContain('Requested plan: base (annual).');
  });

  it('does not attach a plan note when the query has no plan or billing', () => {
    mocks.search = '';
    render(<SignupPage />);
    expect(screen.getByLabelText(/^message/i)).toHaveValue('');
  });
});
