/**
 * Ordered list of documentation pages.
 * Shared by DocSidebar and DocPrevNext components.
 */
export interface DocPage {
  title: string;
  href: string;
}

export const DOC_PAGES: DocPage[] = [
  { title: 'Quickstart', href: '/docs/quickstart' },
  { title: 'Authentication', href: '/docs/authentication' },
  { title: 'API Reference', href: '/docs/api' },
  { title: 'Webhooks', href: '/docs/webhooks' },
  { title: 'Error Codes', href: '/docs/errors' },
  { title: 'Rate Limits', href: '/docs/rate-limits' },
  { title: 'SDKs', href: '/docs/sdks' },
  { title: 'FSMA 204 Guide', href: '/docs/fsma-204' },
  { title: 'Changelog', href: '/docs/changelog' },
];
