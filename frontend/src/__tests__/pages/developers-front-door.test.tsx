import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import DevelopersPage from '@/app/developers/page';

describe('/developers front door', () => {
  it('does not send visitors into the /developer/portal sign-in loop', () => {
    // Until the real-session gate for /developer/portal is deployed, that route
    // redirects to /login and the login page forwards straight back. Request
    // access and the docs are the front door; existing customers use /login.
    render(<DevelopersPage />);

    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));

    expect(hrefs).not.toContain('/developer/portal');
    expect(hrefs).toContain('/contact');
    expect(hrefs).toContain('/docs/quickstart');
    expect(hrefs).toContain('/login');
    expect(document.body.textContent).not.toMatch(/Already have an account/i);
  });
});
