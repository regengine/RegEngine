'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';

// Everything here comes from the signed-in session (useAuth) or is a fixed
// fact about the public API. No network calls, no placeholder numbers.
const ROW = 'grid gap-x-6 gap-y-3 text-ui sm:grid-cols-[8rem_minmax(0,1fr)]';
const MONO = 'min-w-0 break-all font-mono text-small text-re-text-primary';
const LINK = 'text-re-text-primary underline underline-offset-[3px]';

export default function DeveloperPortalPage() {
    const { user, tenantId } = useAuth();

    return (
        <PageContainer className="space-y-6">
            <PageHeader
                title="Developer portal"
                description="How to reach the RegEngine API from your workspace."
                className="mb-0"
            />

            <Card>
                <CardHeader><CardTitle>Your session</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                    <dl className={ROW}>
                        <dt className="text-re-text-tertiary">Email</dt>
                        <dd className="min-w-0 break-all text-re-text-primary">{user?.email ?? 'Not available'}</dd>
                        <dt className="text-re-text-tertiary">Role</dt>
                        <dd className="min-w-0 text-re-text-primary">{user?.role_name ?? 'Not reported'}</dd>
                        {tenantId && (
                            <>
                                <dt className="text-re-text-tertiary">Workspace</dt>
                                <dd className={MONO}>{tenantId}</dd>
                            </>
                        )}
                    </dl>
                    {!tenantId && (
                        <Callout tone="warning">
                            This account has no single workspace. <Link href="/contact" className={LINK}>Contact support</Link>.
                        </Callout>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle>API access</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                    <dl className={ROW}>
                        <dt className="text-re-text-tertiary">Base URL</dt>
                        <dd className={MONO}>https://regengine.co/api/v1</dd>
                        <dt className="text-re-text-tertiary">Key header</dt>
                        <dd className={MONO}>X-RegEngine-API-Key</dd>
                    </dl>
                    <p className="max-w-[70ch] text-small text-re-text-tertiary">
                        Live API keys are issued by RegEngine for your workspace. Signing in here does not create or reveal a key.
                    </p>
                    <Button asChild>
                        <Link href="/contact" className="no-underline">Request a live key</Link>
                    </Button>
                    <p className="text-small text-re-text-tertiary">
                        Read the <Link href="/docs/quickstart" className={LINK}>quickstart</Link>,{' '}
                        <Link href="/docs/authentication" className={LINK}>authentication</Link> and{' '}
                        <Link href="/docs/api" className={LINK}>API reference</Link>, or see{' '}
                        <Link href="/developer/portal/keys" className={LINK}>how keys are issued</Link>.
                    </p>
                </CardContent>
            </Card>
        </PageContainer>
    );
}
