import Link from 'next/link';
import { Building2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';

export default async function MockSsoRedirectPage({
  searchParams,
}: {
  searchParams: Promise<{ organization_id?: string }>;
}) {
  const params = await searchParams;
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] px-4 py-12 text-[var(--re-text-primary)]">
      <section className="mx-auto flex min-h-[70vh] max-w-md items-center">
        <Card className="w-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg">
          <CardHeader>
            <div className="mb-2 inline-flex w-fit items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
              <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
              Single Sign-On
            </div>
            <h1 className="text-2xl font-semibold">Organization SSO required</h1>
            <CardDescription>
              This is the temporary SSO provider handoff screen for organization {params.organization_id || 'policy routing'}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link href="/login">Return to sign-in</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
