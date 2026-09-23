import Link from 'next/link';

import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';

export default async function MockSsoRedirectPage({
  searchParams,
}: {
  searchParams: Promise<{ organization_id?: string }>;
}) {
  const params = await searchParams;
  return (
    // `showHomeLink={false}`: src/__tests__/lib/prod-inert-gates.test.ts asserts
    // this screen's only link is /login, so the shell's wordmark stays inert.
    <AuthShell
      title="Organization SSO required"
      description={`This is the temporary SSO provider handoff screen for organization ${params.organization_id || 'policy routing'}.`}
      showHomeLink={false}
    >
      <Button asChild className="w-full" size="lg">
        <Link href="/login">Return to sign-in</Link>
      </Button>
    </AuthShell>
  );
}
