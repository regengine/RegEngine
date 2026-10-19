'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

import { AuthShell } from '@/components/auth/AuthShell';
import { ContactRequestForm } from '@/components/contact/ContactRequestForm';

const SLUG = /^[a-z0-9][a-z0-9_-]{0,31}$/;

function slug(value: string | null): string {
  if (!value) return '';
  const cleaned = value.trim().toLowerCase();
  return SLUG.test(cleaned) ? cleaned : '';
}

/** Plan and billing from the pricing CTA, safe to put in the contact message. */
export function requestedPlanNote(plan: string | null, billing: string | null): string {
  const planSlug = slug(plan);
  const billingSlug = slug(billing);
  if (planSlug && billingSlug) return `Requested plan: ${planSlug} (${billingSlug}).`;
  if (planSlug) return `Requested plan: ${planSlug}.`;
  if (billingSlug) return `Requested billing: ${billingSlug}.`;
  return '';
}

export default function SignupRequestClient() {
  const searchParams = useSearchParams();
  const note = requestedPlanNote(searchParams.get('plan'), searchParams.get('billing'));

  return (
    <AuthShell
      title="Create your RegEngine workspace"
      description={
        <>
          Workspaces are set up by the RegEngine team, usually within one business day. Already invited?{' '}
          <Link
            href="/login"
            className="font-medium text-re-text-primary underline-offset-[3px] hover:underline"
          >
            Sign in
          </Link>
          .
        </>
      }
    >
      <ContactRequestForm
        idPrefix="signup"
        submitLabel="Request access"
        messagePlaceholder="What should we know before we set up the workspace?"
        initialMessage={note}
        messageAttachment={note}
        showDirectEmail={false}
      />
    </AuthShell>
  );
}
