'use client';

import { useState, useRef } from 'react';
import Link from 'next/link';
import { ArrowRight, Check, Loader2, AlertCircle } from 'lucide-react';
import { supabase } from '@/lib/supabase';

export default function OnboardingPage() {
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const formRef = useRef<HTMLFormElement>(null);

  const canSubmit = email.includes('@') && company.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || status === 'submitting') return;
    setStatus('submitting');
    setErrorMsg('');

    try {
      const { error } = await supabase
        .from('waitlist_leads')
        .insert({
          email: email.trim().toLowerCase(),
          company: company.trim(),
          source: 'onboarding',
        });

      if (error) {
        // Duplicate email — still treat as success (they're already on the list)
        if (error.code === '23505') {
          setStatus('success');
          return;
        }
        throw error;
      }

      setStatus('success');
    } catch (err) {
      console.error('Onboarding submission failed:', err);
      setStatus('error');
      setErrorMsg('Something went wrong. Please try again or email us directly at hello@regengine.co.');
    }
  }

  /* ── Success state ── */
  if (status === 'success') {
    return (
      <main className="min-h-[80vh] flex items-center justify-center px-4 sm:px-6">
        <div className="max-w-[440px] w-full text-center animate-[fadeUp_0.5s_ease-out]">
          <div className="mx-auto mb-6 h-14 w-14 rounded-full bg-[var(--re-brand)] flex items-center justify-center shadow-[0_0_30px_rgba(16,185,129,0.3)]">
            <Check className="h-7 w-7 text-white" strokeWidth={2.5} />
          </div>
          <h1 className="font-serif text-[clamp(1.5rem,4vw,1.75rem)] font-bold text-[var(--re-text-primary)] tracking-tight mb-3">
            Your workspace is ready.
          </h1>
          <p className="text-[0.9rem] sm:text-[1rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
            We&apos;ve created <strong className="text-[var(--re-text-primary)]">{company}</strong>&apos;s
            compliance workspace. A confirmation has been sent to <strong className="text-[var(--re-text-primary)]">{email}</strong>.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/dashboard"
              className="group inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-6 py-3 rounded-xl text-[0.9rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_6px_24px_rgba(16,185,129,0.25)] min-h-[48px] active:scale-[0.98]"
            >
              Go to Dashboard
              <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
            <Link
              href="/retailer-readiness"
              className="inline-flex items-center justify-center border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-6 py-3 rounded-xl text-[0.9rem] font-medium transition-all duration-300 hover:border-[var(--re-text-muted)] min-h-[48px] active:scale-[0.98]"
            >
              Run Free Assessment
            </Link>
          </div>
        </div>
      </main>
    );
  }

  /* ── Form state ── */
  return (
    <main className="min-h-[80vh] flex items-center justify-center px-4 sm:px-6">
      <div className="max-w-[440px] w-full animate-[fadeUp_0.4s_ease-out]">

        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-3">
          Get Started
        </p>
        <h1 className="font-serif text-[clamp(1.5rem,4vw,2rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-2">
          Start your workspace
        </h1>
        <p className="text-[0.95rem] text-[var(--re-text-secondary)] leading-relaxed mb-8">
          Tell us who you are and we&apos;ll set up your FSMA 204 compliance workspace.
        </p>

        {status === 'error' && (
          <div className="flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200 mb-5">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
            <p className="text-[0.875rem] text-red-700">{errorMsg}</p>
          </div>
        )}

        <form ref={formRef} onSubmit={handleSubmit} className="space-y-5">
          {/* Email */}
          <div>
            <label htmlFor="email" className="block font-mono text-[0.7rem] font-medium text-[var(--re-text-muted)] uppercase tracking-[0.06em] mb-2">
              Work Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full px-4 py-3 rounded-xl bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] text-[0.925rem] placeholder:text-[var(--re-text-muted)] outline-none transition-all duration-200 focus:border-[var(--re-brand)] focus:shadow-[0_0_0_3px_rgba(16,185,129,0.12)]"
            />
          </div>

          {/* Company */}
          <div>
            <label htmlFor="company" className="block font-mono text-[0.7rem] font-medium text-[var(--re-text-muted)] uppercase tracking-[0.06em] mb-2">
              Company Name
            </label>
            <input
              id="company"
              type="text"
              required
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Acme Foods Inc."
              className="w-full px-4 py-3 rounded-xl bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] text-[0.925rem] placeholder:text-[var(--re-text-muted)] outline-none transition-all duration-200 focus:border-[var(--re-brand)] focus:shadow-[0_0_0_3px_rgba(16,185,129,0.12)]"
            />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit || status === 'submitting'}
            className="group relative w-full inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none overflow-hidden min-h-[48px]"
          >
            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:group-enabled:translate-x-[200%] transition-transform duration-700 ease-in-out" />
            {status === 'submitting' ? (
              <>
                <Loader2 className="relative h-4 w-4 animate-spin" />
                <span className="relative">Setting up…</span>
              </>
            ) : (
              <>
                <span className="relative">Create Workspace</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:group-enabled:translate-x-1" />
              </>
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-[0.8rem] text-[var(--re-text-muted)]">
          Already have an account?{' '}
          <Link href="/login" className="text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors font-medium">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
