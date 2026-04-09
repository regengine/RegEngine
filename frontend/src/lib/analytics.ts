// Safe wrapper around gtag that handles consent and missing gtag
declare global {
  interface Window {
    gtag?: (...args: any[]) => void;
    dataLayer?: any[];
  }
}

export function trackEvent(eventName: string, params?: Record<string, any>) {
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
