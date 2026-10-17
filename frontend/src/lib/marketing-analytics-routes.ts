import { getStoredConsent } from './cookie-consent';

/** Keep these exclusions aligned with the marketing analytics filter in #3401. */
export const MARKETING_APP_ROUTE_PREFIXES = [
  '/dashboard', '/login', '/signup', '/ingest', '/admin', '/audit',
  '/compliance', '/controls', '/developer/portal', '/exceptions',
  '/identity', '/incidents', '/onboarding', '/records', '/remediation',
  '/requests', '/reports', '/review', '/rules', '/settings',
  '/sysadmin', '/trace',
] as const;

const INTERNAL_STORAGE_KEY = 're_internal';
const SENSITIVE_ROUTE_PREFIXES = ['/sandbox/results', '/portal'] as const;
const PUBLIC_MARKETING_SECTIONS = new Set([
  '/about', '/alpha', '/blog', '/buyer-programs', '/case-studies',
  '/compare', '/contact', '/demo', '/design-system', '/developers',
  '/docs', '/dpa', '/fsma', '/fsma-204', '/integrations', '/legal',
  '/pricing', '/privacy', '/product', '/proof', '/retailer-readiness',
  '/sandbox', '/security', '/status', '/supplier-compliance', '/terms',
  '/tools', '/trust', '/trust-center', '/verify', '/verticals',
  '/walkthrough', '/why-regengine',
]);
const PUBLIC_TOOL_SLUGS = new Set([
  'anomaly-simulator', 'ask', 'cte-mapper', 'data-import', 'drill-simulator',
  'export', 'fsma-unified', 'ftl-checker', 'inflow-lab',
  'inflow-lab-dashboard-preview', 'kde-checker', 'knowledge-graph',
  'label-scanner', 'notice-validator', 'obligation-scanner',
  'readiness-assessment', 'recall-readiness', 'records-request-checklist',
  'retailer-readiness', 'roi-calculator', 'scan', 'self-reported-checklist',
  'sop-generator', 'tlc-validator',
]);

export function isMarketingAppRoute(pathname: string): boolean {
  return MARKETING_APP_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/** ?re_internal=1 persists suppression; ?re_internal=0 clears it. */
export function isInternalAnalyticsSession(url?: string): boolean {
  if (typeof window === 'undefined') return false;
  let directive: string | null = null;
  try {
    directive = new URL(url ?? window.location.href, window.location.origin)
      .searchParams.get(INTERNAL_STORAGE_KEY);
  } catch {
    // An invalid URL cannot change the stored browser setting.
  }
  try {
    if (directive === '1') window.localStorage.setItem(INTERNAL_STORAGE_KEY, '1');
    if (directive === '0') window.localStorage.removeItem(INTERNAL_STORAGE_KEY);
    return directive === '1' || (
      directive !== '0' && window.localStorage.getItem(INTERNAL_STORAGE_KEY) === '1'
    );
  } catch {
    return directive === '1';
  }
}

/** Only known public route labels can enter analytics; unknown segments are omitted. */
export function safeMarketingPath(pathname: unknown): string | null {
  if (typeof pathname !== 'string' || !pathname.startsWith('/')) return null;
  if (/@|%40|%2f|%3f|%23|:\/\/|\d{7,}/i.test(pathname)) return null;
  if (SENSITIVE_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  )) return null;
  if (pathname === '/') return pathname;
  const segments = pathname.split('/').filter(Boolean);
  const section = `/${segments[0]}`;
  if (!PUBLIC_MARKETING_SECTIONS.has(section)) return null;
  if (section === '/tools' && segments.length === 2 && PUBLIC_TOOL_SLUGS.has(segments[1])) {
    return pathname;
  }
  return section;
}

export function shouldTrackMarketingPageview(pathname: string, url?: string): boolean {
  return getStoredConsent() === 'accepted'
    && !isMarketingAppRoute(pathname)
    && safeMarketingPath(pathname) !== null
    && !isInternalAnalyticsSession(url);
}
