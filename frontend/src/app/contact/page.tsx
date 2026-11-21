'use client';

import Link from "next/link";
import { MessageSquare, Clock } from "lucide-react";
import { ContactRequestForm } from '@/components/contact/ContactRequestForm';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-re-surface-base">
      <Container as="section" width="marketing" className="py-12 sm:py-16">
        <PageHeader
          size="hero"
          eyebrow={<span className="font-mono uppercase">Contact</span>}
          title="Contact RegEngine"
          description="Reach out for FSMA 204 implementation support, pilot onboarding, or enterprise pricing."
          className="border-b-0 pb-0"
        />

        {/* Email only ask */}
        <Card padding="compact" className="mt-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <span className="text-ui text-re-text-secondary">
            <strong className="font-medium text-re-text-primary">Ask by email:</strong>{' '}
            Email the founder at christopher@regengine.co with your FSMA 204 questions and where your records have gaps. RegEngine is in Beta, and email is the way to reach the founder right now.
          </span>
          <Button asChild variant="secondary" size="lg" className="shrink-0">
            <a href="mailto:christopher@regengine.co">Email the founder</a>
          </Button>
        </Card>

        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* ── Contact Form Card ── */}
          <Card padding="spacious" className="md:col-span-2">
            <p className="text-subheading text-re-text-primary">Contact options</p>
            <ContactRequestForm />
          </Card>

          {/* ── Side Cards ── */}
          <div className="flex flex-col gap-4">
            <Card padding="spacious">
              <MessageSquare className="mb-2 h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <p className="text-subheading text-re-text-primary">Assessment Intake</p>
              <p className="mt-1 text-ui text-re-text-secondary">Submit retailer readiness and receive founder review.</p>
              <Link href="/retailer-readiness" className="mt-3 inline-block text-ui text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">
                Open assessment
              </Link>
            </Card>

            <Card padding="spacious">
              <Clock className="mb-2 h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <p className="text-subheading text-re-text-primary">Email the Founder</p>
              <p className="mt-1 text-ui text-re-text-secondary">
                Christopher Sellers, founder and engineer. Email is the way to reach him right now.
              </p>
              <a
                href="mailto:christopher@regengine.co"
                className="mt-3 inline-block text-ui text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
              >
                christopher@regengine.co
              </a>
            </Card>
          </div>
        </div>
      </Container>
    </div>
  );
}
