'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/next';
import { Cookie, X } from 'lucide-react';
import {
  getStoredConsent,
  setConsentCookie,
  type ConsentValue,
} from '@/lib/cookie-consent';
import { shouldHideMarketingChrome } from '@/lib/app-routes';

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
  const pathname = usePathname();
  const [consent, setConsent] = useState<ConsentValue | null | 'loading'>('loading');
  const [visible, setVisible] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const hideBanner = shouldHideMarketingChrome(pathname);

  // Read stored consent on mount
  useEffect(() => {
    const stored = getStoredConsent();
    queueMicrotask(() => {
      setConsent(stored);
      if (stored === null) setVisible(true);
    });
  }, []);

  // Listen for the "reopen preferences" event dispatched by the footer link
  useEffect(() => {
    const handler = () => setVisible(true);
    document.addEventListener('re:show-cookie-prefs', handler);
    return () => document.removeEventListener('re:show-cookie-prefs', handler);
  }, []);

  // Keep the first-visit banner from sitting above the mobile navigation drawer.
  useEffect(() => {
    const handler = (event: Event) => {
      const { open } = (event as CustomEvent<{ open?: boolean }>).detail ?? {};
      setMobileMenuOpen(Boolean(open));
    };

    window.addEventListener('re:mobile-menu-state', handler);
    return () => window.removeEventListener('re:mobile-menu-state', handler);
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
      {visible && !hideBanner && !mobileMenuOpen && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label="Cookie consent"
          className="fixed bottom-2 left-2 right-2 z-[9999] pointer-events-none sm:bottom-4 sm:left-auto sm:right-4"
        >
          <div
            className="pointer-events-auto w-full rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-[0_8px_32px_rgba(0,0,0,0.22)] sm:max-w-[620px]"
          >
            <div className="flex items-start gap-2.5 p-3 sm:items-center sm:gap-3 sm:p-3">
              {/* Icon */}
              <div className="flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] sm:h-8 sm:w-8">
                <Cookie className="h-3.5 w-3.5 text-[var(--re-brand)] sm:h-4 sm:w-4" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0 sm:flex sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2 mb-0.5 sm:mb-1">
                    <h2 className="text-sm font-semibold text-[var(--re-text-primary)]">
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

                  <p className="mb-2 text-[11px] leading-snug text-[var(--re-text-muted)] sm:mb-0 sm:text-xs sm:leading-relaxed">
                    <span className="sm:hidden">
                      Essential sessions. Analytics only if accepted.
                    </span>
                    <span className="hidden sm:inline">
                      Essential cookies keep sessions working. Analytics only run if you accept, with no
                      advertising tracking. Change this anytime in the footer.
                    </span>{' '}
                    <Link
                      href="/privacy"
                      className="text-[var(--re-brand)] underline hover:opacity-90"
                    >
                      Privacy Policy
                    </Link>
                    .
                  </p>
                </div>

                {/* Buttons — Accept first, Decline second (GDPR: no hierarchy via styling) */}
                <div className="grid grid-cols-2 gap-2 sm:w-[260px] sm:flex-shrink-0">
                  <button
                    onClick={handleAccept}
                    className="inline-flex min-h-8 items-center justify-center rounded-lg bg-[var(--re-brand)] px-2 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--re-brand)] sm:min-h-9 sm:px-3 sm:py-2"
                  >
                    <span className="sm:hidden">Accept</span>
                    <span className="hidden sm:inline">Accept analytics</span>
                  </button>
                  <button
                    onClick={handleDecline}
                    className="inline-flex min-h-8 items-center justify-center rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-2 py-1.5 text-xs font-semibold text-[var(--re-text-secondary)] transition-colors hover:border-[var(--re-text-muted)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--re-brand)] sm:min-h-9 sm:px-3 sm:py-2"
                  >
                    <span className="sm:hidden">Essential</span>
                    <span className="hidden sm:inline">Essential only</span>
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
