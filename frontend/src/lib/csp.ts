/**
 * Content-Security-Policy builder (#543).
 *
 * CSP is enforced (not report-only) and uses a per-request nonce to allow
 * Next.js inline scripts without falling back to unsafe-inline or unsafe-eval.
 *
 * 'strict-dynamic' propagates trust from the nonce-bearing parent script to
 * dynamically-loaded scripts (required for Next.js hydration bundles).
 *
 * style-src retains 'unsafe-inline' — Tailwind and inline style attributes
 * are not executable and carry no XSS risk at this level.
 */
export function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    // Next.js hydration uses inline scripts. 'strict-dynamic' propagates the nonce
    // to child scripts so dynamically-injected bundles also execute.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    // Tailwind/CSS-in-JS requires unsafe-inline; styles cannot execute JS
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    // Google Fonts stylesheet is loaded via a <link> (handled by style-src self).
    // The fonts themselves are served from fonts.gstatic.com.
    "font-src 'self' https://fonts.gstatic.com",
    // API backends, Supabase realtime, Sentry tunnel
    [
      "connect-src 'self'",
      "https://*.supabase.co",
      "wss://*.supabase.co",
      "https://*.railway.app",
      "https://*.vercel.app",
      "https://*.sentry.io",
      "https://vitals.vercel-insights.com",
      "https://va.vercel-scripts.com",
    ].join(' '),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ];

  return directives.join('; ');
}
