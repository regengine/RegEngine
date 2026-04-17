import { headers } from 'next/headers'
import { Providers } from '@/lib/providers'
import { stringifyForScript } from '@/lib/json-ld'
import './globals.css'
import { MarketingHeader } from '@/components/layout/marketing-header'
import { AuthAwareFooter } from '@/components/layout/auth-aware-footer'
import { AccessibilityWidget } from '@/components/accessibility/AccessibilityWidget'
import { CookieBanner } from '@/components/cookie-consent/CookieBanner'
import { GoogleAnalytics } from '@/components/analytics/GoogleAnalytics'
import type { Metadata, Viewport } from 'next'
import { Outfit, Inter, Fraunces, JetBrains_Mono, Instrument_Sans } from 'next/font/google'

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-outfit',
})

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-inter',
})

const fraunces = Fraunces({
  subsets: ['latin'],
  weight: ['300', '400', '500', '700'],
  style: ['normal', 'italic'],
  display: 'swap',
  variable: '--font-fraunces',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  display: 'swap',
  variable: '--font-jetbrains-mono',
})

const instrumentSans = Instrument_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-instrument-sans',
})

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
    url: 'https://regengine.co',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'RegEngine — FSMA 204 Food Traceability Compliance',
    description: 'Meet FDA and retailer traceability deadlines. Ingest supplier data, verify chain of custody, and export audit-ready records in minutes.',
  },
  verification: {
    google: 'AaGncRw3D_Qa40yoaX50kcpMvan5bTfHf5XzpHHzuFY',
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
        {/* PWA manifest (#568) */}
        <link rel="manifest" href="/manifest.json" />
        {/* OpenDyslexic font is lazy-loaded by AccessibilityWidget when needed */}
        {/* nonce attr required for enforced CSP (unsafe-inline removed, #543) */}

        {/* Organization schema */}
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: stringifyForScript({
              '@context': 'https://schema.org',
              '@type': 'Organization',
              name: 'RegEngine',
              url: 'https://regengine.co',
              logo: 'https://regengine.co/icon.png',
              description: 'FSMA 204 food traceability compliance platform. Ingest supplier data, verify chain of custody, and export audit-ready records.',
              sameAs: [],
            }),
          }}
        />

        {/* WebSite schema */}
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: stringifyForScript({
              '@context': 'https://schema.org',
              '@type': 'WebSite',
              name: 'RegEngine',
              url: 'https://regengine.co',
            }),
          }}
        />

        {/* BreadcrumbList schema (#568) — top-level site sections */}
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: stringifyForScript({
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
            }),
          }}
        />

        {/* Product schema (#568) */}
        <script
          nonce={nonce}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: stringifyForScript({
              '@context': 'https://schema.org',
              '@type': 'Product',
              name: 'RegEngine FSMA 204 Compliance Platform',
              description: 'FSMA 204 food traceability compliance software. Ingest supplier data, verify chain of custody, and produce FDA-ready audit exports in under 48 hours.',
              url: 'https://regengine.co',
              brand: {
                '@type': 'Brand',
                name: 'RegEngine',
              },
              offers: {
                '@type': 'AggregateOffer',
                priceCurrency: 'USD',
                lowPrice: '425',
                highPrice: '1499',
                offerCount: 3,
                offers: [
                  { '@type': 'Offer', name: 'Base Plan', price: '425', priceCurrency: 'USD', priceSpecification: { '@type': 'UnitPriceSpecification', referenceQuantity: { '@type': 'QuantitativeValue', value: 1, unitCode: 'MON' } } },
                  { '@type': 'Offer', name: 'Standard Plan', price: '549', priceCurrency: 'USD', priceSpecification: { '@type': 'UnitPriceSpecification', referenceQuantity: { '@type': 'QuantitativeValue', value: 1, unitCode: 'MON' } } },
                  { '@type': 'Offer', name: 'Premium Plan', price: '639', priceCurrency: 'USD', priceSpecification: { '@type': 'UnitPriceSpecification', referenceQuantity: { '@type': 'QuantitativeValue', value: 1, unitCode: 'MON' } } },
                ],
              },
            }),
          }}
        />
      </head>
      <body
        className={`min-h-screen flex flex-col bg-background text-foreground ${outfit.variable} ${inter.variable} ${fraunces.variable} ${jetbrainsMono.variable} ${instrumentSans.variable}`}
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
        <GoogleAnalytics />
        <script
          dangerouslySetInnerHTML={{
            __html: `if('serviceWorker' in navigator){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js')})}`,
          }}
        />
      </body>
    </html>
  )
}
