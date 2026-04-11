'use client';

import { useState } from 'react';
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';

/**
 * Lightweight hero newsletter signup (#567).
 * Submits to /api/newsletter and displays inline confirmation.
 */
export function HeroNewsletterSignup() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus('loading');
    try {
      const res = await fetch('/api/newsletter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });
      setStatus(res.ok ? 'success' : 'error');
    } catch {
      setStatus('error');
    }
  }

  if (status === 'success') {
    return (
      <div className="flex items-center gap-2 text-[0.82rem] text-[var(--re-brand)]">
        <CheckCircle2 className="w-4 h-4 shrink-0" />
        <span>You&apos;re on the list — we&apos;ll keep you updated on FSMA 204.</span>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2 max-w-[420px]">
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="flex-1 bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] rounded-lg px-3.5 py-2.5 text-[0.875rem] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:border-[var(--re-brand)] transition-colors min-h-[44px]"
        disabled={status === 'loading'}
      />
      <button
        type="submit"
        disabled={status === 'loading'}
        className="inline-flex items-center justify-center gap-1.5 bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[var(--re-text-secondary)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] px-4 py-2.5 rounded-lg text-[0.8rem] font-medium transition-colors whitespace-nowrap min-h-[44px]"
      >
        {status === 'loading' ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <>Stay updated <ArrowRight className="w-3.5 h-3.5" /></>
        )}
      </button>
      {status === 'error' && (
        <p className="text-[0.75rem] text-re-danger mt-1 sm:col-span-2">
          Something went wrong — email us at <a href="mailto:hello@regengine.co" className="underline">hello@regengine.co</a>
        </p>
      )}
    </form>
  );
}
