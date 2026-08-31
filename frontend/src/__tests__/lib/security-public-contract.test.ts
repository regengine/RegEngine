import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(process.cwd());
const securityTxt = readFileSync(
  resolve(frontendRoot, 'public/.well-known/security.txt'),
  'utf8',
);

describe('public security disclosure contract', () => {
  it('publishes a canonical, unexpired security.txt with a real policy route', () => {
    expect(securityTxt).toContain('Contact: mailto:security@regengine.co');
    expect(securityTxt).toContain(
      'Canonical: https://regengine.co/.well-known/security.txt',
    );
    expect(securityTxt).toContain(
      'Policy: https://regengine.co/legal/vulnerability-disclosure',
    );
    expect(securityTxt).not.toContain('Acknowledgments:');

    const expiry = securityTxt.match(/^Expires:\s*(.+)$/m)?.[1];
    expect(expiry).toBeTruthy();
    expect(new Date(String(expiry)).getTime()).toBeGreaterThan(
      Date.now() + 30 * 24 * 60 * 60 * 1000,
    );

    expect(
      readFileSync(
        resolve(frontendRoot, 'src/app/legal/vulnerability-disclosure/page.tsx'),
        'utf8',
      ),
    ).toContain('security@regengine.co');
  });
});
