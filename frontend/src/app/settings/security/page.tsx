'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ArrowLeft, Clock, Fingerprint, Key, Loader2, Shield, ShieldCheck, Smartphone } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { registerPasskey } from '@/lib/passwordless-auth';

const SECURITY_CAPABILITIES = [
  {
    icon: Fingerprint,
    title: 'Passkey step-up',
    description:
      'Sensitive admin actions require WebAuthn or SSO-backed sessions. Email-code sessions are blocked until the user authenticates with a passkey.',
    eta: 'Active',
  },
  {
    icon: Key,
    title: 'Session management',
    description:
      'Active sessions are stored server-side and can be revoked centrally as session management expands.',
    eta: 'Next',
  },
  {
    icon: Shield,
    title: 'Security audit log',
    description:
      'Security-relevant events such as logins, policy changes, and session revocation will be surfaced here.',
    eta: 'Planned',
  },
];

export default function SecuritySettingsPage() {
  const { authMethod, isHighAssuranceSession, tenantId, user } = useAuth();
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
    const domainName = user?.email?.split('@')[1]?.toLowerCase() || 'example.test';
    if (!tenantId) {
      setPolicyStatus('No active organization is available for this session.');
      return;
    }

    setIsCheckingPolicy(true);
    setPolicyStatus(null);
    try {
      await apiClient.updateOrganizationSsoPolicy(tenantId, {
        domain_name: domainName,
        domain_verified: false,
        enforced_auth_policy: 'standard',
      });
      setPolicyStatus('High-assurance organization policy access confirmed.');
    } catch {
      setPolicyStatus('Passkey authentication is required to change organization policy.');
    } finally {
      setIsCheckingPolicy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
        <Link
          href="/dashboard/settings"
          className="mb-6 inline-flex items-center text-sm text-muted-foreground hover:text-primary"
        >
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          Back to Settings
        </Link>

        <div className="mb-8">
          <h1 className="mb-2 text-3xl font-bold sm:text-4xl">Security Settings</h1>
          <p className="text-muted-foreground">
            Manage high-assurance access for your RegEngine account.
          </p>
        </div>

        <Card className="mb-8 border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
              <CardTitle>Passwordless authentication</CardTitle>
            </div>
            <CardDescription>
              RegEngine now uses email codes, passkeys, and SSO routing instead of account passwords.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="border border-[var(--re-info-border)] bg-[var(--re-info-bg)] p-4 text-sm leading-6 text-[var(--re-text-secondary)]">
              Password changes are no longer available because passwords are no longer accepted for sign-in.
              Use a passkey when prompted for high-assurance routes.
            </div>
            <Button asChild className="gap-2">
              <Link href="/login">
                <Smartphone className="h-4 w-4" aria-hidden="true" />
                Manage sign-in from login
              </Link>
            </Button>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={handleRegisterPasskey}
              disabled={isRegisteringPasskey}
            >
              {isRegisteringPasskey ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Registering passkey...
                </>
              ) : (
                <>
                  <Fingerprint className="h-4 w-4" aria-hidden="true" />
                  Register Passkey
                </>
              )}
            </Button>
            {passkeyStatus && (
              <div role="status" className="border border-[var(--re-info-border)] bg-[var(--re-info-bg)] p-3 text-sm text-[var(--re-text-secondary)]">
                {passkeyStatus}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-8 border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Fingerprint className="h-5 w-5 text-primary" aria-hidden="true" />
              <CardTitle>Enterprise policy access</CardTitle>
            </div>
            <CardDescription>
              Organization SSO policy changes require a passkey or SSO-backed session.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-3">
                <div className="text-xs uppercase tracking-[0.12em] text-[var(--re-text-muted)]">
                  Current assurance
                </div>
                <div className="mt-1 font-medium text-[var(--re-text-primary)]">
                  {authMethod || 'Unknown'}
                </div>
              </div>
              <div className="border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-3">
                <div className="text-xs uppercase tracking-[0.12em] text-[var(--re-text-muted)]">
                  Admin policy state
                </div>
                <div className="mt-1 font-medium text-[var(--re-text-primary)]">
                  {isHighAssuranceSession ? 'Ready' : 'Step-up required'}
                </div>
              </div>
            </div>

            {policyStatus && (
              <div role="status" className="border border-[var(--re-info-border)] bg-[var(--re-info-bg)] p-3 text-sm text-[var(--re-text-secondary)]">
                {policyStatus}
              </div>
            )}

            <Button
              type="button"
              className="gap-2"
              onClick={handleAdminPolicyAccessCheck}
              disabled={isCheckingPolicy || !tenantId}
            >
              {isCheckingPolicy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Checking access...
                </>
              ) : (
                <>
                  <Fingerprint className="h-4 w-4" aria-hidden="true" />
                  Verify admin policy access
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="mb-6">
          <h2 className="mb-1 text-lg font-semibold">Security capabilities</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            The account security surface is shifting to passwordless, server-side sessions, and enterprise policy enforcement.
          </p>
        </div>

        <div className="grid gap-4">
          {SECURITY_CAPABILITIES.map((feature) => (
            <Card key={feature.title} className="border-dashed">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <feature.icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    <CardTitle className="text-base">{feature.title}</CardTitle>
                  </div>
                  <span className="inline-flex items-center gap-1 bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
                    <Clock className="h-3 w-3" aria-hidden="true" />
                    {feature.eta}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{feature.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
