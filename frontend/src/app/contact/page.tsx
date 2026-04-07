'use client';

import { useState } from 'react';
import Link from "next/link";
import { Mail, MessageSquare, Clock, Send, CheckCircle, AlertCircle } from "lucide-react";

export default function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '' });
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(prev => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('submitting');
    try {
      const res = await fetch('/api/v1/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(`API responded ${res.status}`);
      setStatus('success');
      setForm({ name: '', email: '', company: '', message: '' });
    } catch {
      setStatus('error');
    }
  };

  const inputClass =
    "w-full rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] px-3 py-2.5 text-sm text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:border-[var(--re-brand)] focus:ring-1 focus:ring-[var(--re-brand)] transition-colors";

  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[900px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Contact</p>
        <h1 className="font-display text-[clamp(32px,4.5vw,48px)] font-bold text-[var(--re-text-primary)] leading-tight tracking-tight">
          Talk with the RegEngine team
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] max-w-[620px] leading-relaxed">
          Reach out for FSMA 204 implementation support, pilot onboarding, or enterprise pricing.
        </p>

        {/* Gap Analysis Offer */}
        <div className="mt-6 inline-flex items-center gap-3 rounded-xl border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] px-5 py-3">
          <span className="text-sm text-[var(--re-text-primary)]">
            <strong className="text-[var(--re-brand)]">Book a free gap analysis call</strong>{' '}
            — 30 minutes with our founder to assess your FSMA 204 readiness.
          </span>
          <a
            href="https://cal.com/regengine/gap-analysis"
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-lg bg-[var(--re-brand)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--re-brand-dark)] transition-colors"
          >
            Book call
          </a>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* ── Contact Form Card ── */}
          <div className="md:col-span-2 p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
            <Mail className="h-5 w-5 text-[var(--re-brand)] mb-2" />
            <p className="text-sm font-semibold text-[var(--re-text-primary)]">Send us a message</p>

            {status === 'success' ? (
              <div className="mt-4 flex items-start gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
                <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-[var(--re-text-primary)]">Message sent</p>
                  <p className="text-sm text-[var(--re-text-muted)] mt-1">
                    We&apos;ll respond within one business day.
                  </p>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="Name"
                    required
                    value={form.name}
                    onChange={update('name')}
                    className={inputClass}
                  />
                  <input
                    type="email"
                    placeholder="Email"
                    required
                    value={form.email}
                    onChange={update('email')}
                    className={inputClass}
                  />
                </div>
                <input
                  type="text"
                  placeholder="Company"
                  value={form.company}
                  onChange={update('company')}
                  className={inputClass}
                />
                <textarea
                  placeholder="How can we help?"
                  required
                  rows={4}
                  value={form.message}
                  onChange={update('message')}
                  className={inputClass + " resize-none"}
                />

                {status === 'error' && (
                  <div className="flex items-center gap-2 text-sm text-red-400">
                    <AlertCircle className="h-4 w-4" />
                    Something went wrong. Please try again or email us directly.
                  </div>
                )}

                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="self-start flex items-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--re-brand-dark)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="h-4 w-4" />
                  {status === 'submitting' ? 'Sending\u2026' : 'Send message'}
                </button>

                <p className="text-xs text-[var(--re-text-disabled)] mt-1">
                  Or email us directly at{' '}
                  <a href="mailto:chris@regengine.co" className="text-[var(--re-brand)] hover:underline">
                    chris@regengine.co
                  </a>
                </p>
              </form>
            )}
          </div>

          {/* ── Side Cards ── */}
          <div className="flex flex-col gap-4">
            <div className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
              <MessageSquare className="h-5 w-5 text-[var(--re-brand)] mb-2" />
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">Assessment Intake</p>
              <p className="text-sm text-[var(--re-text-muted)] mt-1">Submit retailer readiness and receive founder review.</p>
              <Link href="/retailer-readiness" className="text-xs text-[var(--re-brand)] mt-3 inline-block">
                Open assessment
              </Link>
            </div>

            <div className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
              <Clock className="h-5 w-5 text-[var(--re-brand)] mb-2" />
              <p className="text-sm font-semibold text-[var(--re-text-primary)]">Talk to the Founder</p>
              <p className="text-sm text-[var(--re-text-muted)] mt-1">
                Christopher Sellers, founder and engineer. Typical response within one business day.
              </p>
              <a
                href="https://www.linkedin.com/in/christophersellers"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-[var(--re-brand)] mt-3 inline-block hover:underline"
              >
                Connect on LinkedIn
              </a>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
