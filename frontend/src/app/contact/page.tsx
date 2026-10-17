'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState } from 'react';
import Link from "next/link";
import { MessageSquare, Clock, Send } from "lucide-react";
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { getConversionAttribution, trackBookCallClick, trackContactFormSubmit } from '@/lib/conversion-events';

function contactErrorCode(status: number): 'validation' | 'rate_limited' | 'unavailable' | 'server' {
  if (status === 400 || status === 422) return 'validation';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'unavailable';
  return 'server';
}

export default function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '', website: '' });
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(prev => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('submitting');
    try {
      const res = await fetchWithCsrf('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, ...getConversionAttribution() }),
      });
      if (!res.ok) {
        trackContactFormSubmit('error', contactErrorCode(res.status));
        setStatus('error');
        return;
      }
      trackContactFormSubmit('success');
      setStatus('success');
      setForm({ name: '', email: '', company: '', message: '', website: '' });
    } catch {
      trackContactFormSubmit('error', 'server');
      setStatus('error');
    }
  };

  return (
    <div className="min-h-screen bg-re-surface-base">
      <Container as="section" width="marketing" className="py-12 sm:py-16">
        <PageHeader
          size="hero"
          eyebrow={<span className="font-mono uppercase">Contact</span>}
          title="Talk with the RegEngine team"
          description="Reach out for FSMA 204 implementation support, pilot onboarding, or enterprise pricing."
          className="border-b-0 pb-0"
        />

        {/* Gap Analysis Offer */}
        <Card padding="compact" className="mt-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <span className="text-ui text-re-text-secondary">
            <strong className="font-medium text-re-text-primary">Book a free gap-analysis call</strong>{' '}
            — 30 minutes with the founder to walk through your FSMA 204 posture and identify coverage gaps.
          </span>
          <Button asChild variant="secondary" size="lg" className="shrink-0">
            <a
              href="https://calendly.com/regengine/fsma-strategy-session"
              onClick={() => trackBookCallClick('contact_page')}
              target="_blank"
              rel="noopener noreferrer"
            >
              Book call
            </a>
          </Button>
        </Card>

        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* ── Contact Form Card ── */}
          <Card padding="spacious" className="md:col-span-2">
            <p className="text-subheading text-re-text-primary">Contact options</p>

            {status === 'success' ? (
              <Callout tone="success" role="status" className="mt-4">
                <p className="font-medium text-re-text-primary">Message sent</p>
                <p className="mt-1">
                  We&apos;ll respond within one business day.
                </p>
              </Callout>
            ) : (
              <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
                {/* Honeypot — hidden from humans; bots that auto-fill it are
                    dropped server-side (/api/contact). */}
                <input
                  type="text"
                  name="website"
                  tabIndex={-1}
                  autoComplete="off"
                  aria-hidden="true"
                  value={form.website}
                  onChange={update('website')}
                  style={{ position: 'absolute', left: '-9999px', width: 1, height: 1, opacity: 0 }}
                />
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Name" htmlFor="contact-name" required>
                    <Input
                      name="name"
                      type="text"
                      placeholder="Name"
                      size="lg"
                      value={form.name}
                      onChange={update('name')}
                    />
                  </Field>
                  <Field label="Email" htmlFor="contact-email" required>
                    <Input
                      name="email"
                      type="email"
                      placeholder="Email"
                      size="lg"
                      value={form.email}
                      onChange={update('email')}
                    />
                  </Field>
                </div>
                <Field label="Company" htmlFor="contact-company">
                  <Input
                    name="company"
                    type="text"
                    placeholder="Company"
                    size="lg"
                    value={form.company}
                    onChange={update('company')}
                  />
                </Field>
                <Field label="Message" htmlFor="contact-message" required>
                  <Textarea
                    name="message"
                    placeholder="How can we help?"
                    rows={4}
                    value={form.message}
                    onChange={update('message')}
                    className={`${fieldControlClasses} h-auto min-h-[7rem] resize-none py-2.5`}
                  />
                </Field>

                {status === 'error' && (
                  <Callout tone="danger" role="alert">
                    Something went wrong. Please try again or email us directly.
                  </Callout>
                )}

                <Button type="submit" size="lg" className="self-start" loading={status === 'submitting'} leadingIcon={<Send className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}>
                  {status === 'submitting' ? 'Sending…' : 'Send message'}
                </Button>

                <p className="text-small text-re-text-muted">
                  Or email us directly at{' '}
                  <a href="mailto:chris@regengine.co" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">
                    chris@regengine.co
                  </a>
                </p>
              </form>
            )}
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
              <p className="text-subheading text-re-text-primary">Talk to the Founder</p>
              <p className="mt-1 text-ui text-re-text-secondary">
                Christopher Sellers, founder and engineer. Typical response within one business day.
              </p>
              <a
                href="https://www.linkedin.com/in/christophersellers"
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block text-ui text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
              >
                Connect on LinkedIn
              </a>
            </Card>
          </div>
        </div>
      </Container>
    </div>
  );
}
