import { Providers } from '@/lib/providers'
import './globals.css'
import { MarketingHeader } from '@/components/layout/marketing-header'
import { AuthAwareFooter } from '@/components/layout/auth-aware-footer'
import { Analytics } from '@vercel/analytics/react'
import { PWAElements } from '@/components/mobile/PWAElements'
import { AccessibilityWidget } from '@/components/accessibility/AccessibilityWidget'
import type { Metadata, Viewport } from 'next'

const enableVercelAnalytics = process.env.VERCEL === '1' || Boolean(process.env.NEXT_PUBLIC_VERCEL_ANALYTICS_ID)

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
}

export const metadata: Metadata = {
  title: 'RegEngine — API-First Regulatory Compliance',
  description: 'FSMA 204 compliance platform. Ingest, verify, and export traceability records with cryptographic proof.',
  icons: {
    icon: '/icon.png',
    apple: '/icon.png',
  },
  openGraph: {
    title: 'RegEngine',
    description: 'FSMA 204 compliance platform for food traceability, recall readiness, and FDA-ready exports.',
    siteName: 'RegEngine',
    url: 'https://regengine.co',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;1,9..144,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.cdnfonts.com/css/opendyslexic"
          rel="stylesheet"
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
        <PWAElements />
        {enableVercelAnalytics ? <Analytics /> : null}
      </body>
    </html>
  )
}
