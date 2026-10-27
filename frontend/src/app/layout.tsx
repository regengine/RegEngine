import { Providers } from '@/lib/providers'
import './globals.css'
import { MarketingHeader } from '@/components/layout/marketing-header'
import { AuthAwareFooter } from '@/components/layout/auth-aware-footer'
import { AccessibilityWidget } from '@/components/accessibility/AccessibilityWidget'
import { CookieBanner } from '@/components/cookie-consent/CookieBanner'
import { StepUpModal } from '@/components/auth/StepUpModal'
import { JSONLD } from '@/components/seo/json-ld'
import type { Metadata, Viewport } from 'next'
import { headers } from 'next/headers'

// Analytics are mounted by CookieBanner only after the user accepts consent (#552).
const enableVercelAnalytics = process.env.VERCEL === '1' || Boolean(process.env.NEXT_PUBLIC_VERCEL_ANALYTICS_ID)

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
}

export const metadata: Metadata = {
  metadataBase: new URL('https://regengine.co'),
  title: 'FSMA 204 Recordkeeping Software | RegEngine',
  description: 'Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Not legal advice.',
  icons: {
    icon: '/icon.png',
    apple: '/icon.png',
  },
  alternates: {
    canonical: './',
  },
  openGraph: {
    title: 'FSMA 204 Recordkeeping Software | RegEngine',
    description: 'Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Not legal advice.',
    siteName: 'RegEngine',
    // Relative, like alternates.canonical above: pages that do not declare
    // their own openGraph inherit this block, and an absolute root URL made
    // every one of them claim og:url = the homepage.
    url: './',
    type: 'website',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'RegEngine FSMA 204 traceability compliance' }],
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const nonce = (await headers()).get('x-nonce') ?? undefined

  return (
    <html lang="en" suppressHydrationWarning data-scroll-behavior="smooth">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        {/* PWA manifest (#568) */}
        <link rel="manifest" href="/manifest.json" />
        {/* OpenDyslexic font is lazy-loaded by AccessibilityWidget when needed */}
        {/* nonce attr required for enforced CSP (unsafe-inline removed, #543) */}

        {/* Organization schema */}
        <JSONLD
          data={{
            '@context': 'https://schema.org',
            '@type': 'Organization',
            name: 'RegEngine',
            url: 'https://regengine.co',
            logo: 'https://regengine.co/icon.png',
            description: 'Pre-revenue FSMA 204 recordkeeping software for the Food Traceability Rule.',
          }}
        />

        {/* WebSite schema */}
        <JSONLD
          data={{
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            name: 'RegEngine',
            url: 'https://regengine.co',
          }}
        />

        {/* BreadcrumbList schema (#568) — top-level site sections */}
        <JSONLD
          data={{
            '@context': 'https://schema.org',
            '@type': 'BreadcrumbList',
            itemListElement: [
              { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://regengine.co' },
              { '@type': 'ListItem', position: 2, name: 'Pricing', item: 'https://regengine.co/pricing' },
              { '@type': 'ListItem', position: 3, name: 'Product', item: 'https://regengine.co/product' },
              { '@type': 'ListItem', position: 4, name: 'Docs', item: 'https://regengine.co/docs' },
              { '@type': 'ListItem', position: 5, name: 'FSMA 204 Guide', item: 'https://regengine.co/fsma-204' },
              { '@type': 'ListItem', position: 6, name: 'About', item: 'https://regengine.co/about' },
              { '@type': 'ListItem', position: 7, name: 'Free Tools', item: 'https://regengine.co/tools' },
            ],
          }}
        />

        {/* Software application. No offers or prices: RegEngine is pre-revenue. */}
        <JSONLD
          data={{
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            name: 'RegEngine',
            applicationCategory: 'BusinessApplication',
            operatingSystem: 'Web',
            url: 'https://regengine.co',
            description: 'Pre-revenue FSMA 204 recordkeeping software for the Food Traceability Rule. Not legal advice.',
          }}
        />
      </head>
      <body
        className="min-h-screen flex flex-col bg-background text-foreground re-page"
        suppressHydrationWarning
      >
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--re-brand)] focus:text-[var(--re-surface-base)] focus:text-sm focus:font-semibold focus:outline-none"
        >
          Skip to content
        </a>
        <Providers nonce={nonce}>
          <MarketingHeader />
          <main id="main-content" aria-label="Page content" className="flex-grow re-app-surface">
            {children}
          </main>
          <AuthAwareFooter />
          <StepUpModal />
        </Providers>
        <AccessibilityWidget />
        <CookieBanner enableAnalytics={enableVercelAnalytics} />
      </body>
    </html>
  )
}
