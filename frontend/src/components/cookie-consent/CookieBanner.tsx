'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/next';
import { Cookie, X } from 'lucide-react';
import {
  getStoredConsent,
  setConsentCookie,
  type ConsentValue,
} from '@/lib/cookie-consent';

interface CookieBannerProps {
  /** Only render Vercel Analytics + SpeedInsights when this is true (env gate). */
  enableAnalytics: boolean;
}

/**
 * GDPR-compliant cookie consent banner.
 *
 * - Shows on first visit (no stored consent).
 * - Accept / Decline — no pre-checked boxes, no tracking before Accept.
 * - Consent stored in `re_cookie_consent` cookie (not localStorage).
 * - Re-openable via the `re:show-cookie-prefs` DOM event (fired from footer link).
 * - Conditionally mounts Vercel Analytics only after "accepted".
 */
export function CookieBanner({ enableAnalytics }: CookieBannerProps) {
  const [consent, setConsent] = useState<ConsentValue | null | 'loading'>('loading');
  const [visible, setVisible] = useState(false);

  // Read stored consent on mount
  useEffect(() => {
    const stored = getStoredConsent();
    setConsent(stored);
    if (stored === null) setVisible(true);
  }, []);

  // Listen for the "reopen preferences" event dispatched by the footer link
  useEffect(() => {
    const handler = () => setVisible(true);
    document.addEventListener('re:show-cookie-prefs', handler);
    return () => document.removeEventListener('re:show-cookie-prefs', handler);
  }, []);

  const handleAccept = () => {
    setConsentCookie('accepted');
    setConsent('accepted');
    setVisible(false);
  };

  const handleDecline = () => {
    setConsentCookie('declined');
    setConsent('declined');
    setVisible(false);
  };

  const handleDismiss = () => {
    // Dismiss without changing consent: only hides if a preference was already set
    if (consent !== null && consent !== 'loading') {
      setVisible(false);
    }
  };

  return (
    <>
      {/* ── Analytics — only after explicit acceptance ── */}
      {enableAnalytics && consent === 'accepted' && (
        <>
          <Analytics />
          <SpeedInsights />
        </>
      )}

      {/* ── Cookie Banner ─────────────────────────────── */}
      {visible && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label="Cookie consent"
          className="fixed bottom-0 left-0 right-0 z-[9999] flex justify-center px-4 pb-4 sm:pb-6 pointer-events-none"
        >
          <div
            className="pointer-events-auto w-full max-w-[680px] rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-[0_8px_40px_rgba(0,0,0,0.24)] p-5 sm:p-6"
          >
            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
                <Cookie className="h-5 w-5 text-[var(--re-brand)]" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <h2 className="text-[15px] font-semibold text-[var(--re-text-primary)]">
                    We use cookies
                  </h2>
                  {/* Dismiss button — only shown when a preference is already stored */}
                  {consent !== null && consent !== 'loading' && (
                    <button
                      onClick={handleDismiss}
                      aria-label="Close cookie banner"
                      className="flex-shrink-0 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>

                <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-4">
                  We use essential cookies for authentication and session management. We&apos;d also
                  like to use analytics cookies (Vercel Analytics) to understand how the product is
                  used — no advertising or third-party tracking. You can change your preference at
                  any time from the footer.{' '}
                  <Link
                    href="/privacy"
                    className="text-[var(--re-brand)] underline hover:opacity-90"
                  >
                    Privacy Policy
                  </Link>
                  .
                </p>

                {/* Buttons — Accept first, Decline second (GDPR: no hierarchy via styling) */}
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleAccept}
                    className="inline-flex items-center px-4 py-2 rounded-lg bg-[var(--re-brand)] text-white text-[13px] font-semibold hover:opacity-90 transition-opacity focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--re-brand)]"
                  >
                    Accept analytics cookies
                  </button>
                  <button
                    onClick={handleDecline}
                    className="inline-flex items-center px-4 py-2 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-secondary)] text-[13px] font-semibold hover:border-[var(--re-text-muted)] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--re-brand)]"
                  >
                    Essential cookies only
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
