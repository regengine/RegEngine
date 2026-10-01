'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ArrowLeft, Clock, Fingerprint } from 'lucide-react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/status-badge';
import { readOrganizationPolicy } from '@/lib/organization-policy';
import { useAuth } from '@/lib/auth-context';
import { registerPasskey } from '@/lib/passwordless-auth';

const SECURITY_CAPABILITIES = [
  {
    title: 'Passkey step-up',
    description:
      'Sensitive admin actions require WebAuthn or SSO-backed sessions. Email-code sessions are blocked until the user authenticates with a passkey.',
    eta: 'Active',
  },
  {
    title: 'Session management',
    description:
      'Active sessions are stored server-side and can be revoked centrally as session management expands.',
    eta: 'Next',
  },
  {
    title: 'Security audit log',
    description:
      'Security-relevant events such as logins, policy changes, and session revocation will be surfaced here.',
    eta: 'Planned',
  },
];

export default function SecuritySettingsPage() {
  const { tenantId, user, authMethod, sessionIdentityVersion } = useAuth();
  // A credential/tenant change disposes both pending checks and prior results.
  // Late responses belong to the unmounted content and cannot publish under B.
  const identity = JSON.stringify([tenantId, user?.id, authMethod, sessionIdentityVersion, user?.is_sysadmin, user?.permissions]);
  return <SecuritySettingsContent key={identity} />;
}

function SecuritySettingsContent() {
  const { authMethod, isHighAssuranceSession, tenantId } = useAuth();
  const [policyStatus, setPolicyStatus] = useState<string | null>(null);
  const [passkeyStatus, setPasskeyStatus] = useState<string | null>(null);
  const [isCheckingPolicy, setIsCheckingPolicy] = useState(false);
  const [isRegisteringPasskey, setIsRegisteringPasskey] = useState(false);

  const handleRegisterPasskey = async () => {
    setIsRegisteringPasskey(true);
    setPasskeyStatus(null);
    try {
      await registerPasskey();
      setPasskeyStatus('Passkey registered. You can now use it for high-assurance actions.');
    } catch (err: unknown) {
      setPasskeyStatus(err instanceof Error ? err.message : 'Passkey registration failed.');
    } finally {
      setIsRegisteringPasskey(false);
    }
  };

  const handleAdminPolicyAccessCheck = async () => {
    if (!tenantId) {
      setPolicyStatus('No active organization is available for this session.');
      return;
    }

    setIsCheckingPolicy(true);
    setPolicyStatus(null);
    try {
      const policy = await readOrganizationPolicy(tenantId);
      setPolicyStatus(`Organization policy read access confirmed. Current policy: ${policy.enforced_auth_policy}; domain ${policy.domain_verified ? 'verified' : 'unverified'}.`);
    } catch (err) {
      setPolicyStatus(err instanceof Error ? err.message : 'Policy access could not be confirmed. Please retry.');
    } finally {
      setIsCheckingPolicy(false);
    }
  };

  return (
    <PageContainer>
      {/* Back link — the shell owns the breadcrumb, this stays as the page's
          own return affordance. */}
      <Link
        href="/dashboard/settings"
        className="mb-4 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        Back to Settings
      </Link>

      <PageHeader
        title="Security Settings"
        description="Manage high-assurance access for your RegEngine account."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="min-w-0">
              <CardTitle>Passwordless authentication</CardTitle>
              <CardDescription>
                RegEngine now uses email codes, passkeys, and SSO routing instead of account passwords.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <Callout tone="info">
              You sign in with an email code or a passkey — there is no password to manage.
              Use a passkey when prompted for high-assurance routes.
            </Callout>
            <Button
              type="button"
              variant="outline"
              onClick={handleRegisterPasskey}
              disabled={isRegisteringPasskey || !isHighAssuranceSession}
              loading={isRegisteringPasskey}
              leadingIcon={<Fingerprint strokeWidth={1.75} aria-hidden="true" />}
            >
              {isRegisteringPasskey ? 'Registering passkey...' : 'Register Passkey'}
            </Button>
            {!isHighAssuranceSession && <Callout tone="info">Passkey enrollment requires an existing passkey or SSO session. Sign in with an enrolled passkey or your organization’s SSO; contact your administrator if neither is available.</Callout>}
            {passkeyStatus && (
              <Callout tone="info" role="status">
                {passkeyStatus}
              </Callout>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="min-w-0">
              <CardTitle>Enterprise policy access</CardTitle>
              <CardDescription>
                Organization SSO policy changes require a passkey or SSO-backed session.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                <dt className="text-label text-re-text-muted">
                  Current assurance
                </dt>
                <dd className="mt-1 font-mono text-[0.8125rem] text-re-text-primary">
                  {authMethod || 'Unknown'}
                </dd>
              </div>
              <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                <dt className="text-label text-re-text-muted">
                  Admin policy state
                </dt>
                <dd className="mt-1.5">
                  <StatusBadge
                    state={isHighAssuranceSession ? 'compliant' : 'at-risk'}
                    label={isHighAssuranceSession ? 'Assurance satisfied; access unverified' : 'Step-up required'}
                  />
                </dd>
              </div>
            </dl>

            {policyStatus && (
              <Callout tone="info" role="status">
                {policyStatus}
              </Callout>
            )}

            <Button
              type="button"
              onClick={handleAdminPolicyAccessCheck}
              disabled={isCheckingPolicy || !tenantId}
              loading={isCheckingPolicy}
              leadingIcon={<Fingerprint strokeWidth={1.75} aria-hidden="true" />}
            >
              {isCheckingPolicy ? 'Checking access...' : 'Verify admin policy access'}
            </Button>
          </CardContent>
        </Card>

        <section className="space-y-4">
          <div className="max-w-[70ch]">
            <h2 className="text-heading text-re-text-primary">Security capabilities</h2>
            <p className="mt-1 text-ui text-re-text-secondary">
              The account security surface is shifting to passwordless, server-side sessions, and enterprise policy enforcement.
            </p>
          </div>

          <div className="grid gap-4">
            {SECURITY_CAPABILITIES.map((feature) => (
              <Card key={feature.title}>
                <CardHeader>
                  <div className="min-w-0">
                    <CardTitle>{feature.title}</CardTitle>
                  </div>
                  <Badge size="sm" className="shrink-0">
                    <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                    {feature.eta}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <p className="max-w-[70ch] text-ui text-re-text-secondary">{feature.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </PageContainer>
  );
}
