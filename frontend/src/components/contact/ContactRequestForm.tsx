'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState } from 'react';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { getConversionAttribution, trackContactFormSubmit } from '@/lib/conversion-events';

function contactErrorCode(status: number): 'validation' | 'rate_limited' | 'unavailable' | 'server' {
  if (status === 400 || status === 422) return 'validation';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'unavailable';
  return 'server';
}

export type ContactRequestFormProps = {
  idPrefix?: string;
  submitLabel?: string;
  messagePlaceholder?: string;
  /** Shown in the message box on first render. */
  initialMessage?: string;
  /**
   * Appended to the submitted message when it is not already there.
   * Used for plan and billing context that must survive an edited message.
   */
  messageAttachment?: string;
  showDirectEmail?: boolean;
};

export function ContactRequestForm({
  idPrefix = 'contact',
  submitLabel = 'Send message',
  messagePlaceholder = 'How can we help?',
  initialMessage = '',
  messageAttachment = '',
  showDirectEmail = true,
}: ContactRequestFormProps) {
  const [form, setForm] = useState({
    name: '',
    email: '',
    company: '',
    message: initialMessage,
    website: '',
  });
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(prev => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('submitting');
    const note = messageAttachment.trim();
    const message = form.message.trim();
    const submittedMessage = note && !message.includes(note)
      ? (message ? `${message}\n\n${note}` : note)
      : message;
    try {
      const res = await fetchWithCsrf('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          message: submittedMessage,
          ...getConversionAttribution(),
        }),
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

  if (status === 'success') {
    return (
      <Callout tone="success" role="status" className="mt-4">
        <p className="font-medium text-re-text-primary">Message sent</p>
        <p className="mt-1">
          We&apos;ll respond within one business day.
        </p>
      </Callout>
    );
  }

  return (
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
        <Field label="Name" htmlFor={`${idPrefix}-name`} required>
          <Input
            name="name"
            type="text"
            placeholder="Name"
            size="lg"
            value={form.name}
            onChange={update('name')}
          />
        </Field>
        <Field label="Email" htmlFor={`${idPrefix}-email`} required>
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
      <Field label="Company" htmlFor={`${idPrefix}-company`}>
        <Input
          name="company"
          type="text"
          placeholder="Company"
          size="lg"
          value={form.company}
          onChange={update('company')}
        />
      </Field>
      <Field label="Message" htmlFor={`${idPrefix}-message`} required>
        <Textarea
          name="message"
          placeholder={messagePlaceholder}
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
        {status === 'submitting' ? 'Sending…' : submitLabel}
      </Button>

      {showDirectEmail && (
        <p className="text-small text-re-text-muted">
          Or email us directly at{' '}
          <a href="mailto:chris@regengine.co" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">
            chris@regengine.co
          </a>
        </p>
      )}
    </form>
  );
}
