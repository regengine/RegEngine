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
 * are not executable and carry no XSS risk at this level. Google Fonts
 * stylesheets are explicitly allowed because the root layout preconnects and
 * loads fonts from fonts.googleapis.com.
 */
export const CSP_PROXY_MATCHER = '/((?!_next/static|_next/image|favicon.ico).*)';

const CSP_PROXY_EXCLUDED_PREFIXES = [
  '/_next/static',
  '/_next/image',
];

const CSP_PROXY_EXCLUDED_PATHS = new Set(['/favicon.ico']);

export function shouldApplyCspProxy(pathname: string): boolean {
  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return (
    !CSP_PROXY_EXCLUDED_PATHS.has(normalizedPath) &&
    !CSP_PROXY_EXCLUDED_PREFIXES.some((prefix) => normalizedPath.startsWith(prefix))
  );
}

export function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    // Next.js hydration uses inline scripts. 'strict-dynamic' propagates the nonce
    // to child scripts so dynamically-injected bundles also execute.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    // Tailwind/CSS-in-JS requires unsafe-inline; styles cannot execute JS
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https:",
    // Google Fonts stylesheet is loaded via a <link>; font files come from
    // fonts.gstatic.com.
    "font-src 'self' https://fonts.gstatic.com",
    // API backends, Supabase realtime, Sentry tunnel
    [
      "connect-src 'self'",
      "https://*.supabase.co",
      "wss://*.supabase.co",
      "https://*.railway.app",
      "https://*.vercel.app",
      "https://*.sentry.io",
      "https://app.posthog.com",
      "https://*.posthog.com",
      "https://vitals.vercel-insights.com",
      "https://va.vercel-scripts.com",
    ].join(' '),
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "upgrade-insecure-requests",
  ];

  return directives.join('; ');
}
