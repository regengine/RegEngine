// Safe wrapper around gtag that handles consent and missing gtag.
//
// The gtag/dataLayer contract is intentionally heterogeneous — Google
// Analytics accepts (command: string, ...) tuples where the third+ args
// depend on the command. Use `unknown` (not `any`) so that every call
// site either narrows or uses the typed helpers below; this removes
// the silent-bug surface of `any` while preserving the flexibility
// the real gtag API requires.
type GtagParams = Record<string, unknown>;

declare global {
  interface Window {
    gtag?: (command: string, eventName: string, params?: GtagParams) => void;
    dataLayer?: unknown[];
  }
}

export function trackEvent(eventName: string, params?: GtagParams) {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', eventName, params);
  }
}

// Pre-defined events
export const analytics = {
  emailGateSubmit: (toolName: string) => trackEvent('email_gate_submit', { tool_name: toolName }),
  pricingPageView: () => trackEvent('pricing_page_view'),
  demoRequestClick: (source: string) => trackEvent('demo_request_click', { source }),
  toolUsage: (toolName: string) => trackEvent('tool_usage', { tool_name: toolName }),
  blogRead: (slug: string) => trackEvent('blog_read', { slug }),
  comparePageView: () => trackEvent('compare_page_view'),
};
