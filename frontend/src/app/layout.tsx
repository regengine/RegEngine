import { headers } from 'next/headers'
import { Providers } from '@/lib/providers'
import './globals.css'
import { MarketingHeader } from '@/components/layout/marketing-header'
import { AuthAwareFooter } from '@/components/layout/auth-aware-footer'
import { AccessibilityWidget } from '@/components/accessibility/AccessibilityWidget'
import { CookieBanner } from '@/components/cookie-consent/CookieBanner'
import type { Metadata, Viewport } from 'next'

// Analytics are mounted by CookieBanner only after the user accepts consent (#552).
const enableVercelAnalytics = process.env.VERCEL === '1' || Boolean(process.env.NEXT_PUBLIC_VERCEL_ANALYTICS_ID)

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
}

export const metadata: Metadata = {
  metadataBase: new URL('https://www.regengine.co'),
  title: 'RegEngine — FSMA 204 Food Traceability Compliance',
  description: 'Meet FDA and retailer traceability deadlines. Ingest supplier data, verify chain of custody, and export audit-ready records in minutes.',
  icons: {
    icon: '/icon.png',
    apple: '/icon.png',
  },
  alternates: {
    canonical: './',
  },
  openGraph: {
    title: 'RegEngine — FSMA 204 Food Traceability Compliance',
    description: 'Meet FDA and retailer traceability deadlines. Ingest supplier data, verify chain of custody, and export audit-ready records in minutes.',
    siteName: 'RegEngine',
    url: 'https://www.regengine.co',
    type: 'website',
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Read the per-request nonce injected by middleware (#543).
  // The nonce is forwarded via the x-nonce request header so server components
  // can attach it to inline <script> tags, satisfying the enforced CSP.
  const nonce = (await headers()).get('x-nonce') ?? ''

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;1,9..144,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        {/* OpenDyslexic font is lazy-loaded by AccessibilityWidget when needed */}
        {/* nonce attr required for enforced CSP (unsafe-inline removed, #543) */}
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@type': 'Organization',
              name: 'RegEngine',
              url: 'https://www.regengine.co',
              logo: 'https://www.regengine.co/icon.png',
              description: 'FSMA 204 food traceability compliance platform. Ingest supplier data, verify chain of custody, and export audit-ready records.',
              sameAs: [],
            }),
          }}
        />
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@type': 'WebSite',
              name: 'RegEngine',
              url: 'https://www.regengine.co',
            }),
          }}
        />
      </head>
      <body
        className="min-h-screen flex flex-col bg-background text-foreground"
        suppressHydrationWarning
      >
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--re-brand)] focus:text-[var(--re-surface-base)] focus:text-sm focus:font-semibold focus:outline-none"
        >
          Skip to content
        </a>
        <Providers>
          <MarketingHeader />
          <main id="main-content" aria-label="Page content" className="flex-grow">
            {children}
          </main>
          <AuthAwareFooter />
        </Providers>
        <AccessibilityWidget />
        <CookieBanner enableAnalytics={enableVercelAnalytics} />
      </body>
    </html>
  )
}
